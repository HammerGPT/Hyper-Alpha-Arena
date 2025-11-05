"""
Initialize Hyperliquid Tables - Simple Approach

This script uses SQLAlchemy's create_all() to automatically create missing tables
and columns. Much simpler than manual migration for SQLite.

Usage:
    cd /home/wwwroot/open-alpha-arena/backend
    python database/init_hyperliquid_tables.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect
from database.connection import engine, DATABASE_URL
from database.models import Base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_hyperliquid_tables():
    """Initialize all tables - SQLAlchemy will handle missing columns/tables"""
    logger.info("=" * 60)
    logger.info("Initializing Hyperliquid Tables")
    logger.info("=" * 60)
    logger.info(f"Database: {DATABASE_URL}\n")

    try:
        # SQLAlchemy's create_all() is smart:
        # - Creates tables that don't exist
        # - For SQLite, can add new columns to existing tables
        # - Idempotent - safe to run multiple times
        Base.metadata.create_all(bind=engine)

        logger.info("✓ Tables initialized successfully!")

        # Verify tables exist
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        logger.info("\nVerifying tables:")
        required_tables = [
            'accounts',
            'orders',
            'hyperliquid_account_snapshots',
            'hyperliquid_positions'
        ]

        for table in required_tables:
            if table in tables:
                columns = [col['name'] for col in inspector.get_columns(table)]
                logger.info(f"  ✓ {table} ({len(columns)} columns)")
            else:
                logger.warning(f"  ✗ {table} NOT FOUND")

        # Check key Hyperliquid columns in accounts
        accounts_cols = [col['name'] for col in inspector.get_columns('accounts')]
        if 'hyperliquid_enabled' in accounts_cols:
            logger.info("\n✓ Hyperliquid fields exist in accounts table")
        else:
            logger.warning("\n⚠️  Hyperliquid fields NOT in accounts table")
            logger.warning("   This may be due to SQLite's ALTER TABLE limitations")
            logger.warning("   You may need to use the full migration script")

        logger.info("\n" + "=" * 60)
        logger.info("✓ Initialization complete!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"\n✗ Initialization failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(init_hyperliquid_tables())
