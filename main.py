import logging
import time
from app import app, scheduler
from feed_processor import schedule_tasks
from flask_login import LoginManager
from models import User
from db_migration import run_migration
from db_migration_webhook import run_webhook_id_migration

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
    """Initialize and configure the scheduler with proper monitoring."""
    try:
        if scheduler.running:
            logger.info("Scheduler is already running, verifying state...")
            jobs = scheduler.get_jobs()
            logger.info(f"Found {len(jobs)} active jobs")
            for job in jobs:
                logger.info(f"Active job: {job.id} - Next run: {job.next_run_time}")
            return
        
        logger.info("Initializing scheduler...")
        
        # Start scheduler first
        scheduler.start()
        time.sleep(2)  # Wait for scheduler to initialize
        
        if not scheduler.running:
            raise RuntimeError("Scheduler failed to start")
        
        logger.info("Scheduler started successfully")
        
        # Schedule tasks with proper application context
        with app.app_context():
            schedule_tasks()
            
            # Verify scheduled tasks
            jobs = scheduler.get_jobs()
            logger.info(f"Scheduled {len(jobs)} jobs:")
            for job in jobs:
                logger.info(
                    f"Job ID: {job.id}\n"
                    f"  Function: {job.func.__name__}\n"
                    f"  Next run: {job.next_run_time}\n"
                    f"  Trigger: {job.trigger}"
                )
                
    except Exception as e:
        logger.error(f"Failed to initialize scheduler: {str(e)}")
        if scheduler.running:
            try:
                scheduler.shutdown(wait=False)
                logger.info("Scheduler shutdown completed during error handling")
            except Exception as shutdown_error:
                logger.error(f"Error shutting down scheduler: {str(shutdown_error)}")
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
        # Configure logging for startup
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        
        logger.info("Starting RSS Feed Monitor application...")
        
        # Run database migrations
        with app.app_context():
            logger.info("Running database migrations...")
            migration_success = run_migration()
            if not migration_success:
                raise RuntimeError("Database migration failed")
                
            # Run webhook ID constraint migration
            logger.info("Running webhook ID constraint migration...")
            webhook_migration_success = run_webhook_id_migration()
            if not webhook_migration_success:
                raise RuntimeError("Webhook ID constraint migration failed")
                
            logger.info("Database migrations completed successfully")
        
        # Initialize scheduler before starting Flask
        with app.app_context():
            init_scheduler()
        
        # Try port 5000 with fallback to 5001 to avoid conflicts
        try:
            import socket
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.bind(('0.0.0.0', 5000))
            test_socket.close()
            port = 5000
        except OSError:
            # Port 5000 is in use, fall back to 5001
            port = 5001
        logger.info(f"Starting Flask application on port {port}")
        
        # Run the Flask application
        app.run(
            host="0.0.0.0",
            port=port,
            debug=False,  # Disable debug mode in production
            use_reloader=False  # Prevent duplicate scheduler initialization
        )
        
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        # Attempt graceful shutdown
        if scheduler and scheduler.running:
            try:
                scheduler.shutdown(wait=False)
                logger.info("Scheduler shutdown completed during error handling")
            except Exception as shutdown_error:
                logger.error(f"Error shutting down scheduler: {shutdown_error}")
        raise
    finally:
        # Ensure scheduler is properly shutdown
        if scheduler and scheduler.running:
            try:
                scheduler.shutdown(wait=False)
                logger.info("Scheduler shutdown completed")
            except Exception as e:
                logger.error(f"Error during final scheduler shutdown: {str(e)}")