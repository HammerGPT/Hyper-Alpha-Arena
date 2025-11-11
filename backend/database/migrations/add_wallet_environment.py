"""
Migration: Add environment field to hyperliquid_wallets

This migration:
1. Adds 'environment' column (testnet/mainnet)
2. Drops UNIQUE constraint on account_id
3. Adds UNIQUE constraint on (account_id, environment)
4. Updates existing records to use 'testnet' as default
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from database.connection import SessionLocal, engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_environment_field():
    """Add environment field and adjust constraints"""
    logger.info("=" * 60)
    logger.info("Adding environment field to hyperliquid_wallets")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        # Step 1: Add environment column (nullable first)
        logger.info("Step 1: Adding environment column...")
        db.execute(text("""
            ALTER TABLE hyperliquid_wallets
            ADD COLUMN IF NOT EXISTS environment VARCHAR(20)
        """))
        db.commit()
        logger.info("✓ Environment column added")

        # Step 2: Update existing records to 'testnet'
        logger.info("Step 2: Setting existing records to testnet...")
        result = db.execute(text("""
            UPDATE hyperliquid_wallets
            SET environment = 'testnet'
            WHERE environment IS NULL
        """))
        db.commit()
        logger.info(f"✓ Updated {result.rowcount} existing records to testnet")

        # Step 3: Make environment column NOT NULL
        logger.info("Step 3: Making environment column NOT NULL...")
        db.execute(text("""
            ALTER TABLE hyperliquid_wallets
            ALTER COLUMN environment SET NOT NULL
        """))
        db.commit()
        logger.info("✓ Environment column set to NOT NULL")

        # Step 4: Drop old UNIQUE constraint on account_id
        logger.info("Step 4: Dropping old UNIQUE constraint on account_id...")
        db.execute(text("""
            ALTER TABLE hyperliquid_wallets
            DROP CONSTRAINT IF EXISTS ix_hyperliquid_wallets_account_id
        """))
        db.commit()
        logger.info("✓ Old UNIQUE constraint dropped")

        # Step 5: Create new index on account_id (non-unique)
        logger.info("Step 5: Creating non-unique index on account_id...")
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_hyperliquid_wallets_account_id
            ON hyperliquid_wallets(account_id)
        """))
        db.commit()
        logger.info("✓ Non-unique index created on account_id")

        # Step 6: Add UNIQUE constraint on (account_id, environment)
        logger.info("Step 6: Adding UNIQUE constraint on (account_id, environment)...")
        db.execute(text("""
            ALTER TABLE hyperliquid_wallets
            ADD CONSTRAINT uq_hyperliquid_wallets_account_environment
            UNIQUE (account_id, environment)
        """))
        db.commit()
        logger.info("✓ UNIQUE constraint added on (account_id, environment)")

        logger.info("=" * 60)
        logger.info("Migration completed successfully!")
        logger.info("=" * 60)

    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        db.close()


def verify_migration():
    """Verify the migration was successful"""
    logger.info("\nVerifying migration...")

    db = SessionLocal()
    try:
        # Check table structure
        result = db.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'hyperliquid_wallets'
            ORDER BY ordinal_position
        """))

        logger.info("\nTable structure:")
        for row in result:
            logger.info(f"  {row.column_name}: {row.data_type} (nullable: {row.is_nullable})")

        # Check constraints
        result = db.execute(text("""
            SELECT constraint_name, constraint_type
            FROM information_schema.table_constraints
            WHERE table_name = 'hyperliquid_wallets'
        """))

        logger.info("\nConstraints:")
        for row in result:
            logger.info(f"  {row.constraint_name}: {row.constraint_type}")

        # Check existing data
        result = db.execute(text("""
            SELECT id, account_id, wallet_address, environment
            FROM hyperliquid_wallets
            ORDER BY id
        """))

        logger.info("\nExisting wallet records:")
        for row in result:
            logger.info(f"  ID: {row.id}, Account: {row.account_id}, "
                       f"Address: {row.wallet_address}, Env: {row.environment}")

        logger.info("\n✓ Verification complete")

    except Exception as e:
        logger.error(f"Verification failed: {e}")
    finally:
        db.close()


def main():
    try:
        add_environment_field()
        verify_migration()
    except Exception as e:
        logger.error(f"Migration script failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
