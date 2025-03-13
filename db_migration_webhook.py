"""Special migration to remove webhook_id unique constraint"""
import logging
from app import db
from sqlalchemy import text
import time

logger = logging.getLogger(__name__)

def run_webhook_id_migration():
    """Remove the unique constraint on webhook_id to allow multiple feeds with the same webhook ID"""
    try:
        logger.info("Starting webhook_id unique constraint removal migration")
        
        # Skip the step to update NULL webhook_ids, as we'll handle them when
        # we recreate the column without the constraint
        
        # Step 1: Create a temporary column
        db.session.execute(text(
            "ALTER TABLE feed ADD COLUMN webhook_id_temp VARCHAR(100)"
        ))
        db.session.commit()
        logger.info("Added temporary webhook_id_temp column")
        
        # Step 2: Copy data from webhook_id to webhook_id_temp
        db.session.execute(text(
            "UPDATE feed SET webhook_id_temp = webhook_id"
        ))
        db.session.commit()
        logger.info("Copied webhook_id data to temporary column")
        
        # Step 3: Drop the old column with its constraint
        db.session.execute(text(
            "ALTER TABLE feed DROP COLUMN webhook_id"
        ))
        db.session.commit()
        logger.info("Dropped webhook_id column with unique constraint")
        
        # Step 4: Rename the temporary column to webhook_id (no unique constraint)
        db.session.execute(text(
            "ALTER TABLE feed RENAME COLUMN webhook_id_temp TO webhook_id"
        ))
        db.session.commit()
        logger.info("Renamed temp column to webhook_id (without unique constraint)")
        
        # Step 5: Update empty string webhook_ids back to NULL
        db.session.execute(text(
            "UPDATE feed SET webhook_id = NULL WHERE webhook_id = ''"
        ))
        db.session.commit()
        
        logger.info("Successfully completed webhook_id constraint removal migration")
        return True
    except Exception as e:
        logger.error(f"Error during webhook_id constraint migration: {str(e)}")
        db.session.rollback()
        return False

if __name__ == "__main__":
    # Can be run directly for testing
    run_webhook_id_migration()