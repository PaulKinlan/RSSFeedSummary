import os
import time
from datetime import datetime, timedelta
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import (
    EVENT_JOB_ERROR, EVENT_JOB_MISSED, EVENT_JOB_EXECUTED,
    EVENT_JOB_ADDED, EVENT_JOB_REMOVED, EVENT_JOB_SUBMITTED,
    EVENT_JOB_MAX_INSTANCES
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

# Initialize scheduler with optimized settings
scheduler = BackgroundScheduler({
    'apscheduler.jobstores.default': {
        'type': 'memory'
    },
    'apscheduler.executors.default': {
        'class': 'apscheduler.executors.pool:ThreadPoolExecutor',
        'max_workers': 20
    },
    'apscheduler.job_defaults': {
        'coalesce': True,
        'max_instances': 3,
        'misfire_grace_time': 1800
    },
    'apscheduler.timezone': 'UTC'
})

def monitor_job_states():
    """Monitor and log current state of all jobs."""
    try:
        jobs = scheduler.get_jobs()
        logger.info(f"Current scheduler state - Active jobs: {len(jobs)}")

        for job in jobs:
            next_run = job.next_run_time
            if next_run:
                # Convert to UTC for consistent comparison
                current_time = datetime.now(next_run.tzinfo)
                time_until_next = (next_run - current_time).total_seconds()
            else:
                time_until_next = None

            logger.info(
                f"Job: {job.id}\n"
                f"  State: {'Running' if job.pending else 'Waiting'}\n"
                f"  Next run: {next_run}\n"
                f"  Time until next run: {time_until_next:.0f}s" if time_until_next else "N/A"
            )

    except Exception as e:
        logger.error(f"Error monitoring job states: {str(e)}")

def cleanup_stale_jobs():
    """Clean up any stale or zombie jobs."""
    try:
        jobs = scheduler.get_jobs()
        
        for job in jobs:
            if hasattr(job, 'next_run_time') and job.next_run_time:
                # Get current time with the same timezone as job's next_run_time
                current_time = datetime.now(job.next_run_time.tzinfo)
                
                time_diff = current_time - job.next_run_time
                if time_diff > timedelta(hours=1):
                    logger.warning(f"Found stale job {job.id}, removing and rescheduling")
                    try:
                        scheduler.remove_job(job.id)
                        if isinstance(job.trigger, (IntervalTrigger, CronTrigger)):
                            # Use timezone-aware datetime for new job
                            scheduler.add_job(
                                func=job.func,
                                trigger=job.trigger,
                                id=job.id,
                                name=job.name,
                                misfire_grace_time=1800,
                                coalesce=True,
                                next_run_time=datetime.now(job.next_run_time.tzinfo) + timedelta(minutes=5)
                            )
                    except Exception as e:
                        logger.error(f"Error cleaning up stale job {job.id}: {str(e)}")
    except Exception as e:
        logger.error(f"Error in cleanup_stale_jobs: {str(e)}")

def handle_max_instances(event):
    """Handle cases where jobs hit max instances limit."""
    logger.warning(f"Job {event.job_id} hit maximum instances limit")
    try:
        job = scheduler.get_job(event.job_id)
        if job:
            logger.info(
                f"Max instances hit for job:\n"
                f"  Name: {job.name}\n"
                f"  Max instances: {job.max_instances}\n"
                f"  Next run: {job.next_run_time}"
            )
            # Force cleanup of any stuck instances
            cleanup_stale_jobs()
    except Exception as e:
        logger.error(f"Error handling max instances event: {str(e)}")

def handle_scheduler_error(event):
    """Enhanced error handler for scheduler job failures."""
    logger.error(f"Scheduler error: Job {event.job_id} failed with {event.exception}")

    try:
        cleanup_stale_jobs()
        job = scheduler.get_job(event.job_id)
        if job:
            logger.error(
                f"Failed job details:\n"
                f"  Name: {job.name}\n"
                f"  Trigger: {job.trigger}\n"
                f"  Next run: {job.next_run_time}\n"
                f"  Function: {job.func.__name__}"
            )

            if not job.next_run_time:
                new_run_time = datetime.now() + timedelta(minutes=5)
                try:
                    scheduler.reschedule_job(
                        job_id=event.job_id,
                        trigger='date',
                        run_date=new_run_time
                    )
                    logger.info(f"Rescheduled failed job {event.job_id} for {new_run_time}")
                except Exception as e:
                    logger.error(f"Failed to reschedule job {event.job_id}: {str(e)}")
    except Exception as e:
        logger.error(f"Error handling job failure for {event.job_id}: {str(e)}")

def handle_job_executed(event):
    """Monitor successful job executions with enhanced tracking."""
    try:
        job = scheduler.get_job(event.job_id)
        if job:
            runtime = getattr(event, 'retval', 0) or 0
            logger.info(
                f"Job completed successfully:\n"
                f"  ID: {event.job_id}\n"
                f"  Runtime: {runtime:.2f}s\n"
                f"  Next run: {job.next_run_time}\n"
                f"  Function: {job.func.__name__}"
            )

            # Monitor job states after successful execution
            monitor_job_states()
    except Exception as e:
        logger.error(f"Error handling job execution event: {str(e)}")

def handle_job_missed(event):
    """Handle missed job executions with recovery."""
    logger.warning(f"Job missed: {event.job_id} scheduled at {event.scheduled_run_time}")

    try:
        cleanup_stale_jobs()
        job = scheduler.get_job(event.job_id)
        if job:
            logger.warning(
                f"Missed job details:\n"
                f"  Name: {job.name}\n"
                f"  Trigger: {job.trigger}\n"
                f"  Scheduled time: {event.scheduled_run_time}"
            )

            if not job.next_run_time:
                if isinstance(job.trigger, IntervalTrigger):
                    next_run = datetime.now() + timedelta(minutes=1)
                elif isinstance(job.trigger, CronTrigger):
                    next_run = job.trigger.get_next_fire_time(None, event.scheduled_run_time)
                else:
                    next_run = datetime.now() + timedelta(minutes=5)

                try:
                    scheduler.reschedule_job(
                        job_id=event.job_id,
                        trigger='date',
                        run_date=next_run
                    )
                    logger.info(f"Rescheduled missed job {event.job_id} for {next_run}")
                except Exception as e:
                    logger.error(f"Failed to reschedule missed job: {str(e)}")
    except Exception as e:
        logger.error(f"Error handling missed job: {str(e)}")

# Base class for SQLAlchemy models
class Base(DeclarativeBase):
    pass

# Initialize Flask extensions
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

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
        scheduler.add_listener(handle_max_instances, EVENT_JOB_MAX_INSTANCES)

        logger.info("Scheduler event listeners initialized with enhanced monitoring")

        # Schedule monitoring job
        scheduler.add_job(
            monitor_job_states,
            trigger='interval',
            minutes=5,
            id='monitor_job_states',
            coalesce=True,
            max_instances=1
        )

        # Start scheduler if not already running
        if not scheduler.running:
            try:
                logger.info("Starting scheduler initialization...")
                scheduler.start()
                logger.info("APScheduler started successfully")

                # Wait for scheduler to stabilize
                time.sleep(1)

                if not scheduler.running:
                    raise RuntimeError("Scheduler failed to maintain running state")

                # Schedule initial tasks
                with app.app_context():
                    schedule_tasks()
                    logger.info("Initial tasks scheduled successfully")

                    # Verify initial state
                    monitor_job_states()

            except Exception as e:
                logger.error(f"Scheduler initialization failed: {str(e)}")
                if scheduler.running:
                    scheduler.shutdown(wait=False)
                raise
        else:
            logger.info("Scheduler already running, verifying state...")
            monitor_job_states()

    except Exception as e:
        logger.error(f"Error during initialization: {e}")
        raise

# Register cleanup handler
atexit.register(lambda: scheduler.shutdown(wait=False) if scheduler.running else None)