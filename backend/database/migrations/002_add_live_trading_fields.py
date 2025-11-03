"""
Migration 002: Add Live Trading Fields (Phase 2)

This migration adds database schema support for live trading:
1. Adds trading mode and exchange fields to Account table
2. Adds exchange integration fields to Order table
3. Creates ExchangeConfig table
4. Populates ExchangeConfig with Hyperliquid testnet/mainnet configs

Usage:
    cd /mnt/c/Users/PC/Dev/Hyper-Alpha-Arena/backend
    uv run python database/migrations/002_add_live_trading_fields.py

Safety:
    - All new fields are nullable or have defaults
    - Existing accounts default to PAPER mode
    - Backward compatible with Phase 1 paper trading
    - Can be rolled back by dropping added columns/table
"""

import sys
import os
import sqlite3
import logging
from pathlib import Path

# Add parent directory to path to import database connection
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.connection import SessionLocal, engine
from sqlalchemy import text, inspect
from config.exchanges import EXCHANGE_CONFIGS

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def table_exists(table_name: str) -> bool:
    """Check if a table exists"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def add_account_trading_fields():
    """Add trading mode and exchange fields to accounts table"""
    logger.info("=" * 60)
    logger.info("STEP 1: Adding trading mode & exchange fields to accounts table")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        fields_to_add = [
            ("trading_mode", "VARCHAR(10) NOT NULL DEFAULT 'PAPER'"),
            ("exchange", "VARCHAR(20) NOT NULL DEFAULT 'HYPERLIQUID'"),
            ("exchange_api_key", "VARCHAR(500)"),
            ("exchange_api_secret", "VARCHAR(500)"),
            ("wallet_address", "VARCHAR(100)"),
            ("testnet_enabled", "VARCHAR(10) NOT NULL DEFAULT 'true'"),
        ]

        for field_name, field_type in fields_to_add:
            if column_exists("accounts", field_name):
                logger.info(f"✓ Column 'accounts.{field_name}' already exists, skipping")
            else:
                logger.info(f"Adding column 'accounts.{field_name}'...")
                db.execute(text(f"ALTER TABLE accounts ADD COLUMN {field_name} {field_type}"))
                db.commit()
                logger.info(f"✓ Successfully added 'accounts.{field_name}'")

        logger.info("✅ Account trading fields migration complete")

    except Exception as e:
        logger.error(f"❌ Error adding account trading fields: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def add_order_exchange_fields():
    """Add exchange integration fields to orders table"""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 2: Adding exchange fields to orders table")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        fields_to_add = [
            ("exchange_order_id", "VARCHAR(100)"),
            ("exchange", "VARCHAR(20)"),
            ("actual_fill_price", "DECIMAL(18, 6)"),
        ]

        for field_name, field_type in fields_to_add:
            if column_exists("orders", field_name):
                logger.info(f"✓ Column 'orders.{field_name}' already exists, skipping")
            else:
                logger.info(f"Adding column 'orders.{field_name}'...")
                db.execute(text(f"ALTER TABLE orders ADD COLUMN {field_name} {field_type}"))
                db.commit()
                logger.info(f"✓ Successfully added 'orders.{field_name}'")

        logger.info("✅ Order exchange fields migration complete")

    except Exception as e:
        logger.error(f"❌ Error adding order exchange fields: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def create_exchange_config_table():
    """Create exchange_configs table"""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 3: Creating exchange_configs table")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        if table_exists("exchange_configs"):
            logger.info("✓ Table 'exchange_configs' already exists, skipping creation")
            return

        logger.info("Creating 'exchange_configs' table...")
        create_table_sql = """
        CREATE TABLE exchange_configs (
            id INTEGER PRIMARY KEY,
            exchange VARCHAR(20) NOT NULL,
            environment VARCHAR(10) NOT NULL,
            api_endpoint VARCHAR(200) NOT NULL,
            ws_endpoint VARCHAR(200),
            commission_rate FLOAT NOT NULL,
            min_commission FLOAT NOT NULL,
            max_leverage INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(exchange, environment)
        )
        """
        db.execute(text(create_table_sql))
        db.commit()
        logger.info("✓ Successfully created 'exchange_configs' table")
        logger.info("✅ Exchange config table creation complete")

    except Exception as e:
        logger.error(f"❌ Error creating exchange_configs table: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def populate_exchange_configs():
    """Populate exchange_configs table with Hyperliquid configurations"""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 4: Populating exchange_configs table")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        # Check if configs already exist
        result = db.execute(text("SELECT COUNT(*) FROM exchange_configs"))
        count = result.scalar()

        if count > 0:
            logger.info(f"✓ Exchange configs already exist ({count} records), skipping")
            return

        logger.info("Inserting Hyperliquid exchange configurations...")

        for config in EXCHANGE_CONFIGS:
            insert_sql = """
            INSERT INTO exchange_configs (
                exchange, environment, api_endpoint, ws_endpoint,
                commission_rate, min_commission, max_leverage
            ) VALUES (
                :exchange, :environment, :api_endpoint, :ws_endpoint,
                :commission_rate, :min_commission, :max_leverage
            )
            """
            db.execute(text(insert_sql), config)
            logger.info(f"  ✓ Added {config['exchange']} {config['environment']}")

        db.commit()
        logger.info("✅ Exchange configs populated successfully")

    except Exception as e:
        logger.error(f"❌ Error populating exchange configs: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def verify_migration():
    """Verify that migration was successful"""
    logger.info("\n" + "=" * 60)
    logger.info("VERIFICATION: Checking migration results")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        # Verify Account table fields
        account_fields = ["trading_mode", "exchange", "wallet_address", "testnet_enabled"]
        logger.info("Checking accounts table...")
        for field in account_fields:
            exists = column_exists("accounts", field)
            status = "✓" if exists else "✗"
            logger.info(f"  {status} {field}: {'EXISTS' if exists else 'MISSING'}")

        # Verify Order table fields
        order_fields = ["exchange_order_id", "exchange", "actual_fill_price"]
        logger.info("\nChecking orders table...")
        for field in order_fields:
            exists = column_exists("orders", field)
            status = "✓" if exists else "✗"
            logger.info(f"  {status} {field}: {'EXISTS' if exists else 'MISSING'}")

        # Verify ExchangeConfig table
        logger.info("\nChecking exchange_configs table...")
        exists = table_exists("exchange_configs")
        status = "✓" if exists else "✗"
        logger.info(f"  {status} table exists: {exists}")

        if exists:
            result = db.execute(text("SELECT COUNT(*) FROM exchange_configs"))
            count = result.scalar()
            logger.info(f"  ✓ Contains {count} configurations")

        # Check existing accounts default to PAPER
        logger.info("\nChecking existing accounts...")
        result = db.execute(text("SELECT COUNT(*) FROM accounts WHERE trading_mode = 'PAPER'"))
        paper_count = result.scalar()
        result = db.execute(text("SELECT COUNT(*) FROM accounts"))
        total_count = result.scalar()
        logger.info(f"  ✓ {paper_count}/{total_count} accounts set to PAPER mode")

        logger.info("\n✅ Migration verification complete!")

    except Exception as e:
        logger.error(f"❌ Error during verification: {e}")
        raise
    finally:
        db.close()


def main():
    """Run the migration"""
    logger.info("=" * 60)
    logger.info("Migration 002: Add Live Trading Fields (Phase 2)")
    logger.info("=" * 60)
    logger.info("Database: data.db (SQLite)")
    logger.info("=" * 60)

    try:
        # Step 1: Add trading mode & exchange fields to accounts
        add_account_trading_fields()

        # Step 2: Add exchange fields to orders
        add_order_exchange_fields()

        # Step 3: Create exchange_configs table
        create_exchange_config_table()

        # Step 4: Populate exchange configs
        populate_exchange_configs()

        # Step 5: Verify migration
        verify_migration()

        logger.info("\n" + "=" * 60)
        logger.info("🎉 MIGRATION 002 COMPLETED SUCCESSFULLY!")
        logger.info("=" * 60)
        logger.info("Phase 2 database schema is now ready for live trading")
        logger.info("All existing accounts remain in PAPER mode")
        logger.info("=" * 60)

    except Exception as e:
        logger.error("\n" + "=" * 60)
        logger.error("❌ MIGRATION FAILED!")
        logger.error("=" * 60)
        logger.error(f"Error: {e}")
        logger.error("Please check database permissions and try again")
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
