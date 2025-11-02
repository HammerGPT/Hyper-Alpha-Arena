"""
Initialize the database with all tables

This script creates all database tables based on the SQLAlchemy models.
Run this once before starting the application.

Usage:
    cd backend
    uv run python init_database.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from database.connection import engine, Base
from database.models import (
    User, Account, Position, Order, Trade, TradingConfig,
    SystemConfig, CryptoPrice, CryptoKline, CryptoPriceTick,
    AccountAssetSnapshot, AccountStrategyConfig, PromptTemplate,
    AccountPromptBinding, AIDecisionLog
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_database():
    """Initialize database with all tables"""
    logger.info("Initializing database...")

    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)

        logger.info("✓ All tables created successfully")
        logger.info("")
        logger.info("Created tables:")
        for table_name in Base.metadata.tables.keys():
            logger.info(f"  - {table_name}")

        logger.info("")
        logger.info("Database initialization complete!")
        logger.info("You can now:")
        logger.info("1. Run migrations if needed")
        logger.info("2. Start the backend server")

        return True

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("Database Initialization")
    print("=" * 70)
    print("")

    success = init_database()

    if not success:
        sys.exit(1)
