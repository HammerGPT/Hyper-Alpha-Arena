"""
Upgrade Database for Hyperliquid - Smart Approach

This script:
1. Exports important trader configurations (API keys)
2. Backs up old database
3. Creates new database with all Hyperliquid fields
4. Restores trader configurations
5. Initializes with default data

Usage:
    cd /home/wwwroot/open-alpha-arena/backend
    python database/upgrade_for_hyperliquid.py
"""
import sys
import os
import json
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from database.connection import engine, SessionLocal, DATABASE_URL
from database.models import Base, Account, User, TradingConfig
from config.settings import DEFAULT_TRADING_CONFIGS
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def export_trader_configs(db: Session) -> list:
    """Export trader API configurations"""
    accounts = db.query(Account).all()
    configs = []

    for acc in accounts:
        configs.append({
            'name': acc.name,
            'account_type': acc.account_type,
            'model': acc.model,
            'base_url': acc.base_url,
            'api_key': acc.api_key,
            'is_active': acc.is_active,
            'auto_trading_enabled': acc.auto_trading_enabled,
        })

    logger.info(f"Exported {len(configs)} trader configurations")
    return configs


def backup_database():
    """Backup existing database"""
    db_path = DATABASE_URL.replace('sqlite:///./', '')
    if not os.path.exists(db_path):
        logger.info("No existing database to backup")
        return None

    backup_path = f"{db_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    logger.info(f"✓ Database backed up to: {backup_path}")
    return backup_path


def create_fresh_database():
    """Create fresh database with all Hyperliquid fields"""
    db_path = DATABASE_URL.replace('sqlite:///./', '')

    # Remove old database
    if os.path.exists(db_path):
        os.remove(db_path)
        logger.info(f"Removed old database: {db_path}")

    # Create new database with all tables
    Base.metadata.create_all(bind=engine)
    logger.info("✓ Created fresh database with Hyperliquid support")


def restore_trader_configs(db: Session, configs: list):
    """Restore trader configurations"""
    # Ensure default user exists
    user = db.query(User).filter(User.username == "default").first()
    if not user:
        user = User(username="default", is_active="true")
        db.add(user)
        db.commit()
        db.refresh(user)

    # Restore accounts
    for config in configs:
        account = Account(
            user_id=user.id,
            name=config['name'],
            account_type=config['account_type'],
            model=config.get('model', 'gpt-4'),
            base_url=config.get('base_url', 'https://api.openai.com/v1'),
            api_key=config.get('api_key'),
            is_active=config['is_active'],
            auto_trading_enabled=config['auto_trading_enabled'],
            initial_capital=10000.00,
            current_cash=10000.00,
            frozen_cash=0.00,
            # Hyperliquid fields initialized to defaults
            hyperliquid_enabled="false",
            hyperliquid_environment=None,
            max_leverage=3,
            default_leverage=1
        )
        db.add(account)

    db.commit()
    logger.info(f"✓ Restored {len(configs)} trader configurations")


def initialize_trading_configs(db: Session):
    """Initialize trading configurations"""
    for market, config_data in DEFAULT_TRADING_CONFIGS.items():
        existing = db.query(TradingConfig).filter(
            TradingConfig.market == market,
            TradingConfig.version == "v1"
        ).first()

        if not existing:
            config = TradingConfig(
                market=market,
                version="v1",
                min_commission=config_data.min_commission,
                commission_rate=config_data.commission_rate,
                exchange_rate=config_data.exchange_rate,
                min_order_quantity=config_data.min_order_quantity,
                lot_size=config_data.lot_size
            )
            db.add(config)

    db.commit()
    logger.info("✓ Initialized trading configurations")


def main():
    """Run database upgrade"""
    logger.info("=" * 70)
    logger.info("Hyper Alpha Arena - Database Upgrade for Hyperliquid")
    logger.info("=" * 70)
    logger.info("")

    try:
        # Step 1: Export existing trader configs
        logger.info("Step 1: Exporting trader configurations...")
        db = SessionLocal()
        try:
            configs = export_trader_configs(db)
        except Exception as e:
            logger.warning(f"No existing database or failed to export: {e}")
            configs = []
        finally:
            db.close()

        # Step 2: Backup database
        logger.info("\nStep 2: Backing up database...")
        backup_path = backup_database()

        # Step 3: Create fresh database
        logger.info("\nStep 3: Creating fresh database with Hyperliquid support...")
        create_fresh_database()

        # Step 4: Restore trader configs
        logger.info("\nStep 4: Restoring trader configurations...")
        db = SessionLocal()
        try:
            restore_trader_configs(db, configs)
            initialize_trading_configs(db)
        finally:
            db.close()

        # Step 5: Verify
        logger.info("\nStep 5: Verifying new database...")
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        required_tables = [
            'users', 'accounts', 'orders', 'positions',
            'hyperliquid_account_snapshots',
            'hyperliquid_positions'
        ]

        all_ok = True
        for table in required_tables:
            if table in tables:
                logger.info(f"  ✓ {table}")
            else:
                logger.error(f"  ✗ {table} MISSING")
                all_ok = False

        # Check Hyperliquid fields in accounts
        accounts_cols = [col['name'] for col in inspector.get_columns('accounts')]
        hyperliquid_fields = [
            'hyperliquid_enabled',
            'hyperliquid_environment',
            'hyperliquid_testnet_private_key',
            'hyperliquid_mainnet_private_key',
            'max_leverage',
            'default_leverage'
        ]

        logger.info("\n  Hyperliquid fields in accounts table:")
        for field in hyperliquid_fields:
            if field in accounts_cols:
                logger.info(f"    ✓ {field}")
            else:
                logger.error(f"    ✗ {field} MISSING")
                all_ok = False

        if all_ok:
            logger.info("\n" + "=" * 70)
            logger.info("✓ Database upgrade completed successfully!")
            logger.info("=" * 70)
            logger.info(f"\nBackup location: {backup_path}")
            logger.info(f"Restored {len(configs)} trader configurations")
            logger.info("\nNext steps:")
            logger.info("1. Generate encryption key: python utils/encryption.py")
            logger.info("2. Add to .env: HYPERLIQUID_ENCRYPTION_KEY=<key>")
            logger.info("3. Configure Hyperliquid accounts via API")
            return 0
        else:
            logger.error("\n✗ Database upgrade verification failed!")
            return 1

    except Exception as e:
        logger.error(f"\n✗ Upgrade failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
