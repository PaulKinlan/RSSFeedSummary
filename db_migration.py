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
            column_exists = result.fetchone() is not None
            
            if not column_exists:
                logger.info("Adding webhook_id column to feed table")
                db.session.execute(text("ALTER TABLE feed ADD COLUMN webhook_id VARCHAR(100) UNIQUE"))
                db.session.commit()
                logger.info("Migration complete: Added webhook_id column to feed table")
            else:
                logger.info("webhook_id column already exists in feed table")
                
            logger.info("Database migration completed successfully")
            return True
        except Exception as e:
            logger.error(f"Error during database migration: {str(e)}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    run_migration()