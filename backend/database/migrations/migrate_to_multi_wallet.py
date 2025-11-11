"""
Migration script: Migrate to multi-wallet architecture

This script:
1. Creates hyperliquid_wallets table
2. Migrates existing Account private keys to hyperliquid_wallets table
3. Adds global trading_mode configuration to system_configs
4. Preserves existing Account table fields for backward compatibility
"""

import sys
import os
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from database.connection import SessionLocal, engine
from database.models import Base, Account, SystemConfig
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_hyperliquid_wallets_table():
    """Create hyperliquid_wallets table if not exists"""
    logger.info("Creating hyperliquid_wallets table...")

    # Import HyperliquidWallet to ensure it's registered with Base
    from database.models import HyperliquidWallet

    # Create only the hyperliquid_wallets table
    HyperliquidWallet.__table__.create(bind=engine, checkfirst=True)
    logger.info("✓ hyperliquid_wallets table created")


def parse_wallet_address_from_private_key(private_key: str) -> str:
    """Parse wallet address from private key using eth_account"""
    try:
        from eth_account import Account as EthAccount

        # Remove 0x prefix if present
        if private_key.startswith('0x'):
            private_key = private_key[2:]

        # Create account from private key
        account = EthAccount.from_key(private_key)
        return account.address
    except Exception as e:
        logger.error(f"Failed to parse wallet address from private key: {e}")
        return None


def migrate_account_wallets():
    """Migrate existing Account private keys to hyperliquid_wallets table"""
    logger.info("Migrating Account private keys to hyperliquid_wallets...")

    db = SessionLocal()
    try:
        # Query all accounts that have Hyperliquid configuration
        accounts = db.query(Account).filter(
            (Account.hyperliquid_testnet_private_key.isnot(None)) |
            (Account.hyperliquid_mainnet_private_key.isnot(None))
        ).all()

        logger.info(f"Found {len(accounts)} accounts with Hyperliquid configuration")

        migrated_count = 0
        skipped_count = 0

        for account in accounts:
            # Check if wallet record already exists for this account
            existing = db.execute(
                text("SELECT id FROM hyperliquid_wallets WHERE account_id = :account_id"),
                {"account_id": account.id}
            ).fetchone()

            if existing:
                logger.info(f"  Account {account.id} ({account.name}): wallet already exists, skipping")
                skipped_count += 1
                continue

            # Determine which private key to use (prefer testnet if both exist)
            private_key = None
            if account.hyperliquid_testnet_private_key:
                private_key = account.hyperliquid_testnet_private_key
                logger.info(f"  Account {account.id} ({account.name}): using testnet private key")
            elif account.hyperliquid_mainnet_private_key:
                private_key = account.hyperliquid_mainnet_private_key
                logger.info(f"  Account {account.id} ({account.name}): using mainnet private key")
            else:
                logger.warning(f"  Account {account.id} ({account.name}): no private key found, skipping")
                skipped_count += 1
                continue

            # Parse wallet address from private key
            wallet_address = parse_wallet_address_from_private_key(private_key)
            if not wallet_address:
                logger.error(f"  Account {account.id} ({account.name}): failed to parse wallet address, skipping")
                skipped_count += 1
                continue

            # Get leverage settings from account or use defaults
            max_leverage = account.max_leverage if account.max_leverage else 3
            default_leverage = account.default_leverage if account.default_leverage else 1

            # Insert into hyperliquid_wallets table
            db.execute(
                text("""
                    INSERT INTO hyperliquid_wallets
                    (account_id, private_key_encrypted, wallet_address, max_leverage, default_leverage, is_active, created_at, updated_at)
                    VALUES (:account_id, :private_key, :wallet_address, :max_leverage, :default_leverage, 'true', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """),
                {
                    "account_id": account.id,
                    "private_key": private_key,
                    "wallet_address": wallet_address,
                    "max_leverage": max_leverage,
                    "default_leverage": default_leverage
                }
            )

            logger.info(f"  ✓ Account {account.id} ({account.name}): migrated wallet {wallet_address}")
            migrated_count += 1

        db.commit()
        logger.info(f"Migration complete: {migrated_count} wallets migrated, {skipped_count} skipped")

    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        db.close()


def initialize_global_trading_mode():
    """Initialize global trading_mode in system_configs if not exists"""
    logger.info("Initializing global trading_mode configuration...")

    db = SessionLocal()
    try:
        # Check if trading_mode config already exists
        existing_config = db.query(SystemConfig).filter(
            SystemConfig.key == "hyperliquid_trading_mode"
        ).first()

        if existing_config:
            logger.info(f"  Global trading_mode already exists: {existing_config.value}")
        else:
            # Create new config with default value "testnet"
            new_config = SystemConfig(
                key="hyperliquid_trading_mode",
                value="testnet",
                description="Global Hyperliquid trading environment: 'testnet' or 'mainnet'. Controls which network all AI Traders connect to."
            )
            db.add(new_config)
            db.commit()
            logger.info("  ✓ Global trading_mode initialized to 'testnet'")

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to initialize trading_mode: {e}")
        raise
    finally:
        db.close()


def verify_migration():
    """Verify migration was successful"""
    logger.info("Verifying migration...")

    db = SessionLocal()
    try:
        # Count wallets
        wallet_count = db.execute(
            text("SELECT COUNT(*) FROM hyperliquid_wallets")
        ).scalar()

        # Check trading_mode config
        trading_mode = db.query(SystemConfig).filter(
            SystemConfig.key == "hyperliquid_trading_mode"
        ).first()

        logger.info(f"  Wallet records: {wallet_count}")
        logger.info(f"  Trading mode: {trading_mode.value if trading_mode else 'NOT SET'}")

        # List all wallets
        wallets = db.execute(
            text("""
                SELECT hw.id, hw.account_id, a.name, hw.wallet_address, hw.max_leverage
                FROM hyperliquid_wallets hw
                JOIN accounts a ON hw.account_id = a.id
            """)
        ).fetchall()

        logger.info(f"  Wallet details:")
        for wallet in wallets:
            logger.info(f"    ID: {wallet[0]}, Account: {wallet[2]} (ID: {wallet[1]}), Address: {wallet[3]}, Max Leverage: {wallet[4]}")

        logger.info("✓ Migration verification complete")

    except Exception as e:
        logger.error(f"Verification failed: {e}")
    finally:
        db.close()


def main():
    """Run migration"""
    logger.info("=" * 60)
    logger.info("Starting migration to multi-wallet architecture")
    logger.info("=" * 60)

    try:
        # Step 1: Create table
        create_hyperliquid_wallets_table()

        # Step 2: Migrate data
        migrate_account_wallets()

        # Step 3: Initialize global config
        initialize_global_trading_mode()

        # Step 4: Verify
        verify_migration()

        logger.info("=" * 60)
        logger.info("Migration completed successfully!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"Migration failed: {e}")
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
