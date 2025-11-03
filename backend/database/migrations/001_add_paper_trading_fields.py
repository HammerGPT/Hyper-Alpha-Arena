"""
Migration: Add paper trading enhancement fields to Order table

This migration adds:
- slippage: DECIMAL(10,6) - Tracks slippage percentage for paper trading analysis
- rejection_reason: VARCHAR(200) - Stores reason if order is rejected

Run this migration ONCE before using enhanced paper trading features.

Usage:
    cd backend
    uv run python database/migrations/001_add_paper_trading_fields.py
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import database connection
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.connection import SessionLocal, engine
from sqlalchemy import text, inspect
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def column_exists(db, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    try:
        # Try to select the column - if it exists, no error
        result = db.execute(text(f"SELECT {column_name} FROM {table_name} LIMIT 1"))
        return True
    except Exception:
        # Column doesn't exist
        return False


def run_migration():
    """Run the migration to add paper trading fields"""
    logger.info("Starting migration: Add paper trading enhancement fields to Order table")

    db = SessionLocal()

    try:
        # Check if slippage column already exists
        if column_exists(db, 'orders', 'slippage'):
            logger.info("Column 'slippage' already exists in orders table - skipping")
        else:
            logger.info("Adding 'slippage' column to orders table...")
            db.execute(text(
                "ALTER TABLE orders ADD COLUMN slippage DECIMAL(10, 6) NULL"
            ))
            db.commit()
            logger.info("✓ Added 'slippage' column")

        # Check if rejection_reason column already exists
        if column_exists(db, 'orders', 'rejection_reason'):
            logger.info("Column 'rejection_reason' already exists in orders table - skipping")
        else:
            logger.info("Adding 'rejection_reason' column to orders table...")
            db.execute(text(
                "ALTER TABLE orders ADD COLUMN rejection_reason VARCHAR(200) NULL"
            ))
            db.commit()
            logger.info("✓ Added 'rejection_reason' column")

        logger.info("Migration completed successfully!")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Restart the backend server")
        logger.info("2. Place test orders to verify slippage simulation")
        logger.info("3. Check logs for paper trading simulation details")

        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed: {e}")
        logger.error("Please check database permissions and try again")
        return False

    finally:
        db.close()


def verify_migration():
    """Verify that the migration was successful"""
    logger.info("\nVerifying migration...")

    db = SessionLocal()
    try:
        if column_exists(db, 'orders', 'slippage'):
            logger.info("✓ Column 'slippage' exists")
        else:
            logger.error("✗ Column 'slippage' NOT found")
            return False

        if column_exists(db, 'orders', 'rejection_reason'):
            logger.info("✓ Column 'rejection_reason' exists")
        else:
            logger.error("✗ Column 'rejection_reason' NOT found")
            return False

        logger.info("✓ Migration verification passed")
        return True
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 70)
    print("Paper Trading Enhancement Migration")
    print("=" * 70)
    print("")

    # Run migration
    success = run_migration()

    if success:
        # Verify migration
        verify_migration()
    else:
        sys.exit(1)
