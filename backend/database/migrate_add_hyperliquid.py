"""
Database Migration Script - Add Hyperliquid Support

This script adds Hyperliquid trading support to the existing database.
Run this ONCE after updating the models.py file.

Usage:
    cd /home/wwwroot/open-alpha-arena/backend
    source .venv/bin/activate  # Activate virtual environment
    python database/migrate_add_hyperliquid.py
"""
import sys
import os

# Add parent directory to path so we can import from backend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from database.connection import DATABASE_URL, engine
from database.models import Base, HyperliquidAccountSnapshot, HyperliquidPosition
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_column_exists(engine, table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def check_table_exists(engine, table_name):
    """Check if a table exists"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def migrate_accounts_table():
    """Add Hyperliquid fields to accounts table"""
    logger.info("Migrating accounts table...")

    with engine.connect() as conn:
        # Check if columns already exist
        if check_column_exists(engine, 'accounts', 'hyperliquid_enabled'):
            logger.info("  ✓ Hyperliquid fields already exist in accounts table, skipping")
            return

        # Add Hyperliquid configuration fields
        logger.info("  Adding hyperliquid_enabled column...")
        conn.execute(text(
            "ALTER TABLE accounts ADD COLUMN hyperliquid_enabled VARCHAR(10) DEFAULT 'false'"
        ))

        logger.info("  Adding hyperliquid_environment column...")
        conn.execute(text(
            "ALTER TABLE accounts ADD COLUMN hyperliquid_environment VARCHAR(20)"
        ))

        logger.info("  Adding hyperliquid_testnet_private_key column...")
        conn.execute(text(
            "ALTER TABLE accounts ADD COLUMN hyperliquid_testnet_private_key VARCHAR(500)"
        ))

        logger.info("  Adding hyperliquid_mainnet_private_key column...")
        conn.execute(text(
            "ALTER TABLE accounts ADD COLUMN hyperliquid_mainnet_private_key VARCHAR(500)"
        ))

        logger.info("  Adding max_leverage column...")
        conn.execute(text(
            "ALTER TABLE accounts ADD COLUMN max_leverage INTEGER DEFAULT 3"
        ))

        logger.info("  Adding default_leverage column...")
        conn.execute(text(
            "ALTER TABLE accounts ADD COLUMN default_leverage INTEGER DEFAULT 1"
        ))

        conn.commit()
        logger.info("✓ Accounts table migration completed")


def migrate_orders_table():
    """Add Hyperliquid fields to orders table"""
    logger.info("Migrating orders table...")

    with engine.connect() as conn:
        # Check if columns already exist
        if check_column_exists(engine, 'orders', 'hyperliquid_environment'):
            logger.info("  ✓ Hyperliquid fields already exist in orders table, skipping")
            return

        logger.info("  Adding hyperliquid_environment column...")
        conn.execute(text(
            "ALTER TABLE orders ADD COLUMN hyperliquid_environment VARCHAR(20)"
        ))

        logger.info("  Adding leverage column...")
        conn.execute(text(
            "ALTER TABLE orders ADD COLUMN leverage INTEGER DEFAULT 1"
        ))

        logger.info("  Adding margin_mode column...")
        conn.execute(text(
            "ALTER TABLE orders ADD COLUMN margin_mode VARCHAR(20) DEFAULT 'cross'"
        ))

        logger.info("  Adding reduce_only column...")
        conn.execute(text(
            "ALTER TABLE orders ADD COLUMN reduce_only VARCHAR(10) DEFAULT 'false'"
        ))

        logger.info("  Adding hyperliquid_order_id column...")
        conn.execute(text(
            "ALTER TABLE orders ADD COLUMN hyperliquid_order_id VARCHAR(50)"
        ))

        logger.info("  Adding liquidation_price column...")
        conn.execute(text(
            "ALTER TABLE orders ADD COLUMN liquidation_price DECIMAL(18, 6)"
        ))

        conn.commit()
        logger.info("✓ Orders table migration completed")


def create_hyperliquid_tables():
    """Create new Hyperliquid tables"""
    logger.info("Creating Hyperliquid tables...")

    # Check if tables already exist
    if check_table_exists(engine, 'hyperliquid_account_snapshots'):
        logger.info("  ✓ hyperliquid_account_snapshots already exists, skipping")
    else:
        logger.info("  Creating hyperliquid_account_snapshots table...")
        HyperliquidAccountSnapshot.__table__.create(engine)
        logger.info("  ✓ hyperliquid_account_snapshots created")

    if check_table_exists(engine, 'hyperliquid_positions'):
        logger.info("  ✓ hyperliquid_positions already exists, skipping")
    else:
        logger.info("  Creating hyperliquid_positions table...")
        HyperliquidPosition.__table__.create(engine)
        logger.info("  ✓ hyperliquid_positions created")

    logger.info("✓ Hyperliquid tables creation completed")


def verify_migration():
    """Verify migration was successful"""
    logger.info("\nVerifying migration...")

    inspector = inspect(engine)

    # Check accounts table
    accounts_columns = [col['name'] for col in inspector.get_columns('accounts')]
    required_account_columns = [
        'hyperliquid_enabled',
        'hyperliquid_environment',
        'hyperliquid_testnet_private_key',
        'hyperliquid_mainnet_private_key',
        'max_leverage',
        'default_leverage'
    ]

    for col in required_account_columns:
        if col in accounts_columns:
            logger.info(f"  ✓ accounts.{col} exists")
        else:
            logger.error(f"  ✗ accounts.{col} MISSING")
            return False

    # Check orders table
    orders_columns = [col['name'] for col in inspector.get_columns('orders')]
    required_order_columns = [
        'hyperliquid_environment',
        'leverage',
        'margin_mode',
        'reduce_only',
        'hyperliquid_order_id',
        'liquidation_price'
    ]

    for col in required_order_columns:
        if col in orders_columns:
            logger.info(f"  ✓ orders.{col} exists")
        else:
            logger.error(f"  ✗ orders.{col} MISSING")
            return False

    # Check new tables
    tables = inspector.get_table_names()
    if 'hyperliquid_account_snapshots' in tables:
        logger.info("  ✓ hyperliquid_account_snapshots table exists")
    else:
        logger.error("  ✗ hyperliquid_account_snapshots table MISSING")
        return False

    if 'hyperliquid_positions' in tables:
        logger.info("  ✓ hyperliquid_positions table exists")
    else:
        logger.error("  ✗ hyperliquid_positions table MISSING")
        return False

    logger.info("\n✓ Migration verification passed!")
    return True


def main():
    """Run database migration"""
    logger.info("=" * 60)
    logger.info("Hyper Alpha Arena - Hyperliquid Database Migration")
    logger.info("=" * 60)
    logger.info(f"Database: {DATABASE_URL}\n")

    try:
        # Step 1: Migrate existing tables
        migrate_accounts_table()
        migrate_orders_table()

        # Step 2: Create new tables
        create_hyperliquid_tables()

        # Step 3: Verify migration
        if verify_migration():
            logger.info("\n" + "=" * 60)
            logger.info("✓ Migration completed successfully!")
            logger.info("=" * 60)
            logger.info("\nNext steps:")
            logger.info("1. Set HYPERLIQUID_ENCRYPTION_KEY environment variable")
            logger.info("2. Generate key with: python utils/encryption.py")
            logger.info("3. Configure Hyperliquid accounts via API or admin panel")
            return 0
        else:
            logger.error("\n✗ Migration verification failed!")
            return 1

    except Exception as e:
        logger.error(f"\n✗ Migration failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
