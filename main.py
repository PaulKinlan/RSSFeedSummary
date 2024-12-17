import logging
from app import app, scheduler
from feed_processor import schedule_tasks
from flask_login import LoginManager
from models import User

# Configure logging
logger = logging.getLogger(__name__)

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize scheduled tasks
def init_scheduler():
    try:
        if not scheduler.running:
            logger.info("Initializing scheduler...")
            schedule_tasks()
            if not scheduler.running:
                scheduler.start()
                logger.info("Scheduler started successfully")
        else:
            logger.info("Scheduler already running")
            
        # Verify scheduler state
        jobs = scheduler.get_jobs()
        logger.info(f"Active scheduled jobs: {len(jobs)}")
        for job in jobs:
            logger.info(f"Job: {job.id} - Next run: {job.next_run_time}")
            
    except Exception as e:
        logger.error(f"Failed to initialize scheduler: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        with app.app_context():
            # Initialize the scheduler
            init_scheduler()
        
        # Run the Flask application
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False  # Disable debug mode in production
        )
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        raise