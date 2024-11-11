import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR
from sqlalchemy.orm import DeclarativeBase
import atexit
import logging

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

# Configure scheduler with proper settings
scheduler = BackgroundScheduler({
    'apscheduler.timezone': 'UTC',
    'apscheduler.job_defaults.coalesce': True,
    'apscheduler.job_defaults.max_instances': 1
})

def handle_scheduler_error(event):
    logging.error(f"Scheduler error: Job {event.job_id} failed with {event.exception}")

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a secret key"
    
    # Database configuration
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    
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
        print("Database tables initialized successfully")
        
        # Add error listener to scheduler
        scheduler.add_listener(handle_scheduler_error, EVENT_JOB_ERROR)
        
        # Start scheduler if not already running
        if not scheduler.running:
            scheduler.start()
            # Schedule initial tasks
            schedule_tasks()
            print("Scheduler started and tasks initialized")
            
            # Register shutdown handler
            atexit.register(lambda: scheduler.shutdown(wait=False))
            
    except Exception as e:
        print(f"Error during initialization: {e}")
        raise
