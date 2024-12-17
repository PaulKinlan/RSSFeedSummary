import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from sqlalchemy.orm import DeclarativeBase
import atexit
import logging
import logging.config

# Configure logging
logging_config = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': {
        'default': {
            'level': 'DEBUG',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
        },
    },
    'loggers': {
        '': {  # root logger
            'handlers': ['default'],
            'level': 'DEBUG',
            'propagate': True
        }
    }
}

logging.config.dictConfig(logging_config)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

# Enhanced scheduler configuration
scheduler = BackgroundScheduler({
    'apscheduler.timezone': 'UTC',
    'apscheduler.job_defaults.coalesce': True,
    'apscheduler.job_defaults.max_instances': 1,
    'apscheduler.job_defaults.misfire_grace_time': 15 * 60,  # 15 minutes grace time
    'apscheduler.executors.default': {
        'class': 'apscheduler.executors.pool:ThreadPoolExecutor',
        'max_workers': '20'
    }
})

def handle_scheduler_error(event):
    logger.error(f"Scheduler error: Job {event.job_id} failed with {event.exception}")
    # Log additional context about the failed job
    try:
        job = scheduler.get_job(event.job_id)
        if job:
            logger.error(f"Failed job details - Name: {job.name}, Trigger: {job.trigger}, "
                        f"Next run: {job.next_run_time}")
    except Exception as e:
        logger.error(f"Error getting failed job details: {str(e)}")
    
def handle_job_missed(event):
    logger.warning(f"Job missed: {event.job_id} scheduled at {event.scheduled_run_time}")
    # Reschedule missed jobs if needed
    try:
        job = scheduler.get_job(event.job_id)
        if job:
            logger.warning(f"Missed job details - Name: {job.name}, Trigger: {job.trigger}, "
                          f"Next run: {job.next_run_time}")
            if not job.next_run_time:
                job.reschedule()
                logger.info(f"Rescheduled missed job {event.job_id} for next run at {job.next_run_time}")
    except Exception as e:
        logger.error(f"Error rescheduling missed job {event.job_id}: {str(e)}")

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
        
        # Add scheduler event listeners with enhanced monitoring
        scheduler.add_listener(handle_scheduler_error, EVENT_JOB_ERROR)
        scheduler.add_listener(handle_job_missed, EVENT_JOB_MISSED)
        
        # Start scheduler if not already running
        if not scheduler.running:
            try:
                scheduler.start()
                # Schedule initial tasks
                schedule_tasks()
                
                # Log scheduler state and jobs
                jobs = scheduler.get_jobs()
                logger.info(f"Scheduler started successfully with {len(jobs)} jobs")
                for job in jobs:
                    logger.info(f"Active job: {job.id} - Next run: {job.next_run_time}")
                    
                # Verify feed processing job is scheduled
                feed_job = scheduler.get_job('process_feeds')
                if feed_job:
                    logger.info(f"Feed processing scheduled to run next at: {feed_job.next_run_time}")
                else:
                    logger.error("Feed processing job not found in scheduler!")
                    
            except Exception as e:
                logger.error(f"Failed to start scheduler: {str(e)}")
                raise
        else:
            logger.info("Scheduler already running, skipping initialization")
            
            # Register shutdown handler with proper cleanup
            def cleanup():
                if scheduler.running:
                    scheduler.shutdown(wait=True)
                    logger.info("Scheduler shutdown completed")
            
            atexit.register(cleanup)
            
    except Exception as e:
        logger.error(f"Error during initialization: {e}")
        raise
