from app import app, db
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

def run_migration():
    """Run database migrations to update schema."""
    with app.app_context():
        try:
            # Check if the webhook_id column exists
            result = db.session.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='feed' AND column_name='webhook_id'"))
            webhook_column_exists = result.fetchone() is not None
            
            if not webhook_column_exists:
                logger.info("Adding webhook_id column to feed table")
                db.session.execute(text("ALTER TABLE feed ADD COLUMN webhook_id VARCHAR(100) UNIQUE"))
                db.session.commit()
                logger.info("Migration complete: Added webhook_id column to feed table")
            else:
                logger.info("webhook_id column already exists in feed table")
            
            # Check if the type column exists in the user table
            result = db.session.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='user' AND column_name='type'"))
            type_column_exists = result.fetchone() is not None
            
            if not type_column_exists:
                logger.info("Adding type column to user table")
                db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN type VARCHAR(20) NOT NULL DEFAULT 'user'"))
                db.session.commit()
                logger.info("Migration complete: Added type column to user table")
            else:
                logger.info("type column already exists in user table")
                
            logger.info("Database migration completed successfully")
            return True
        except Exception as e:
            logger.error(f"Error during database migration: {str(e)}")
            db.session.rollback()
            return False

def set_user_as_admin(user_id):
    """Set a user as admin by their ID."""
    with app.app_context():
        try:
            from models import User
            user = User.query.get(user_id)
            if not user:
                logger.error(f"User ID {user_id} not found")
                return False
            
            user.type = 'admin'
            db.session.commit()
            logger.info(f"User {user.username} (ID: {user_id}) is now an admin")
            return True
        except Exception as e:
            logger.error(f"Error setting user as admin: {str(e)}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'set_admin':
        if len(sys.argv) < 3:
            print("Usage: python db_migration.py set_admin <user_id>")
            sys.exit(1)
        
        user_id = int(sys.argv[2])
        success = set_user_as_admin(user_id)
        if success:
            print(f"User ID {user_id} is now an admin")
        else:
            print(f"Failed to set User ID {user_id} as admin")
    else:
        run_migration()