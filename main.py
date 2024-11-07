from app import app, scheduler
from feed_processor import schedule_tasks
from flask_login import LoginManager
from models import User

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize scheduled tasks
def init_scheduler():
    if not scheduler.running:
        schedule_tasks()
        scheduler.start()

if __name__ == "__main__":
    with app.app_context():
        # Initialize the scheduler
        init_scheduler()
    
    # Run the Flask application
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False  # Disable debug mode in production
    )
