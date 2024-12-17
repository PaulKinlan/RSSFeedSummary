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

def find_free_port(start_port=5000, max_port=5100):
    """Find a free port to use for the Flask application."""
    import socket
    for port in range(start_port, max_port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                return port
        except OSError:
            continue
    raise RuntimeError("Could not find a free port")

if __name__ == "__main__":
    try:
        # Initialize scheduler within app context
        with app.app_context():
            init_scheduler()
            logger.info("Scheduler initialized successfully")
        
        # Find an available port
        port = find_free_port()
        logger.info(f"Starting Flask application on port {port}")
        
        # Run the Flask application
        app.run(
            host="0.0.0.0",
            port=port,
            debug=False  # Disable debug mode in production
        )
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        if scheduler and scheduler.running:
            try:
                scheduler.shutdown(wait=False)
                logger.info("Scheduler shutdown completed during error handling")
            except Exception as shutdown_error:
                logger.error(f"Error shutting down scheduler: {shutdown_error}")
        raise