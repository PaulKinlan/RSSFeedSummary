import os
import time
from datetime import datetime, timedelta
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import (
    EVENT_JOB_ERROR, EVENT_JOB_MISSED, EVENT_JOB_EXECUTED,
    EVENT_JOB_ADDED, EVENT_JOB_REMOVED
)
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import DeclarativeBase
import atexit
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

# Base class for SQLAlchemy models
class Base(DeclarativeBase):
    pass

# Initialize Flask extensions
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

# Initialize APScheduler with enhanced error handling
scheduler = BackgroundScheduler({
    'apscheduler.jobstores.default': {
        'type': 'memory'  # Use memory jobstore for reliability
    },
    'apscheduler.executors.default': {
        'class': 'apscheduler.executors.pool:ThreadPoolExecutor',
        'max_workers': 10  # Reduced for better stability
    },
    'apscheduler.job_defaults': {
        'coalesce': True,
        'max_instances': 1,
        'misfire_grace_time': 900  # 15 minutes
    },
    'apscheduler.timezone': 'UTC'
})

def handle_scheduler_error(event):
    """Enhanced error handler for scheduler job failures."""
    logger.error(f"Scheduler error: Job {event.job_id} failed with {event.exception}")
    
    try:
        job = scheduler.get_job(event.job_id)
        if job:
            # Log comprehensive job details
            logger.error(
                f"Failed job details:\n"
                f"  Name: {job.name}\n"
                f"  Trigger: {job.trigger}\n"
                f"  Next run: {job.next_run_time}\n"
                f"  Function: {job.func.__name__}\n"
                f"  Args: {job.args}\n"
                f"  Kwargs: {job.kwargs}\n"
                f"  Max instances: {job.max_instances}\n"
                f"  Misfire grace time: {job.misfire_grace_time}"
            )
            
            # Check if job needs to be rescheduled
            if not job.next_run_time and isinstance(job.trigger, IntervalTrigger):
                new_run_time = datetime.now() + timedelta(minutes=5)  # 5-minute delay
                try:
                    job.reschedule(trigger='date', run_date=new_run_time)
                    logger.info(f"Rescheduled failed job {event.job_id} for {new_run_time}")
                except Exception as reschedule_error:
                    logger.error(f"Failed to reschedule job {event.job_id}: {str(reschedule_error)}")
    except Exception as e:
        logger.error(f"Error handling job failure for {event.job_id}: {str(e)}")

def handle_job_executed(event):
    """Monitor successful job executions and track performance metrics."""
    try:
        job = scheduler.get_job(event.job_id)
        if job:
            runtime = (event.retval or 0) if hasattr(event, 'retval') else 0
            with app.app_context():
                logger.info(
                    f"Job completed successfully:\n"
                    f"  ID: {event.job_id}\n"
                    f"  Name: {job.name}\n"
                    f"  Runtime: {runtime:.2f}s\n"
                    f"  Next run: {job.next_run_time}\n"
                    f"  Function: {job.func.__name__}"
                )
    except Exception as e:
        logger.error(f"Error handling job execution event for {event.job_id}: {str(e)}")

def handle_job_missed(event):
    """Enhanced handler for missed job executions."""
    logger.warning(f"Job missed: {event.job_id} scheduled at {event.scheduled_run_time}")
    
    try:
        job = scheduler.get_job(event.job_id)
        if job:
            # Log detailed missed job information
            logger.warning(
                f"Missed job details:\n"
                f"  Name: {job.name}\n"
                f"  Trigger: {job.trigger}\n"
                f"  Next run: {job.next_run_time}\n"
                f"  Scheduled time: {event.scheduled_run_time}\n"
                f"  Time difference: {datetime.now() - event.scheduled_run_time}"
            )
            
            # Implement smart rescheduling logic
            if not job.next_run_time:
                if isinstance(job.trigger, IntervalTrigger):
                    # For interval triggers, schedule next run with a short delay
                    next_run = datetime.now() + timedelta(minutes=1)
                elif isinstance(job.trigger, CronTrigger):
                    # For cron triggers, keep original schedule
                    next_run = job.trigger.get_next_fire_time(None, event.scheduled_run_time)
                else:
                    next_run = datetime.now() + timedelta(minutes=5)
                
                job.reschedule(trigger='date', run_date=next_run)
                logger.info(f"Rescheduled missed job {event.job_id} for next run at {next_run}")
    except Exception as e:
        logger.error(f"Error handling missed job {event.job_id}: {str(e)}")

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a secret key"
    
    # Database configuration
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    
    # Configure URL generation
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    
    # Set SERVER_NAME only in production environment
    if os.environ.get('FLASK_ENV') == 'production':
        if os.environ.get('SERVER_NAME'):
            app.config['SERVER_NAME'] = os.environ.get('SERVER_NAME')
            logger.info(f"Production environment: Using SERVER_NAME={os.environ.get('SERVER_NAME')}")
        else:
            logger.warning("Production environment but no SERVER_NAME configured")
    else:
        logger.info(f"Development environment: Using default URL generation")
    
    # Make environment variables available to templates
    app.jinja_env.globals['RECAPTCHA_SITE_KEY'] = os.environ.get('RECAPTCHA_SITE_KEY')
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    
    # Register cleanup handler at application creation
    def cleanup():
        try:
            if scheduler and scheduler.running:
                scheduler.shutdown(wait=False)
                logger.info("Scheduler shutdown completed")
        except Exception as e:
            logger.error(f"Error during scheduler shutdown: {e}")
    
    atexit.register(cleanup)
    return app

app = create_app()

# Initialize database and load routes
with app.app_context():
    import models
    import routes
    from feed_processor import schedule_tasks
    
    try:
        # Create tables only if they don't exist
        db.create_all()
        logger.info("Database tables initialized successfully")
        
        # Add comprehensive scheduler event monitoring
        scheduler.add_listener(handle_scheduler_error, EVENT_JOB_ERROR)
        scheduler.add_listener(handle_job_missed, EVENT_JOB_MISSED)
        scheduler.add_listener(handle_job_executed, EVENT_JOB_EXECUTED)
        
        logger.info("Scheduler event listeners initialized with enhanced monitoring")
        
        # Start scheduler if not already running
        if not scheduler.running:
            try:
                logger.info("Starting scheduler initialization...")
                
                # Start scheduler with proper error handling
                scheduler.start()
                logger.info("APScheduler started successfully")
                
                # Wait for scheduler to stabilize
                time.sleep(1)
                
                if not scheduler.running:
                    raise RuntimeError("Scheduler failed to maintain running state")
                
                # Schedule initial tasks
                with app.app_context():
                    try:
                        schedule_tasks()
                        logger.info("Initial tasks scheduled successfully")
                    except Exception as task_error:
                        logger.error(f"Failed to schedule initial tasks: {str(task_error)}")
                        raise
                
            except Exception as e:
                logger.error(f"Scheduler initialization failed: {str(e)}")
                if scheduler.running:
                    try:
                        scheduler.shutdown(wait=False)
                        logger.info("Scheduler shutdown completed after initialization failure")
                    except Exception as shutdown_error:
                        logger.error(f"Error during scheduler shutdown: {str(shutdown_error)}")
                raise
        else:
            logger.info("Scheduler already running, verifying state...")
            jobs = scheduler.get_jobs()
            logger.info(f"Found {len(jobs)} active jobs")
            for job in jobs:
                logger.info(f"Active job: {job.id} - Next run: {job.next_run_time}")
            
    except Exception as e:
        logger.error(f"Error during initialization: {e}")
        raise
