#!/usr/bin/env python3
"""
Migration: Add exchange field to crypto_klines table for multi-exchange support

This migration adds an 'exchange' field to the crypto_klines table to support
data from multiple exchanges (hyperliquid, binance, okx, etc.).

Changes:
1. Add 'exchange' column with default value 'hyperliquid'
2. Update unique constraint to include exchange field
3. Create index on exchange field for performance
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from connection import SessionLocal, engine


def upgrade():
    """Apply the migration"""
    print("Starting migration: add_exchange_to_crypto_klines")

    db = SessionLocal()
    try:
        # Step 1: Add exchange column with default value
        print("Adding exchange column to crypto_klines table...")
        db.execute(text("""
            ALTER TABLE crypto_klines
            ADD COLUMN exchange VARCHAR(20) NOT NULL DEFAULT 'hyperliquid'
        """))

        # Step 2: Create index on exchange field
        print("Creating index on exchange field...")
        db.execute(text("""
            CREATE INDEX idx_crypto_klines_exchange ON crypto_klines(exchange)
        """))

        # Step 3: Drop old unique constraint
        print("Dropping old unique constraint...")
        db.execute(text("""
            ALTER TABLE crypto_klines
            DROP CONSTRAINT IF EXISTS crypto_klines_symbol_market_period_timestamp_key
        """))

        # Step 4: Create new unique constraint including exchange
        print("Creating new unique constraint with exchange field...")
        db.execute(text("""
            ALTER TABLE crypto_klines
            ADD CONSTRAINT crypto_klines_exchange_symbol_market_period_timestamp_key
            UNIQUE (exchange, symbol, market, period, timestamp)
        """))

        db.commit()
        print("Migration completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        db.close()


def downgrade():
    """Rollback the migration"""
    print("Starting rollback: add_exchange_to_crypto_klines")

    db = SessionLocal()
    try:
        # Step 1: Drop new unique constraint
        print("Dropping new unique constraint...")
        db.execute(text("""
            ALTER TABLE crypto_klines
            DROP CONSTRAINT IF EXISTS crypto_klines_exchange_symbol_market_period_timestamp_key
        """))

        # Step 2: Recreate old unique constraint
        print("Recreating old unique constraint...")
        db.execute(text("""
            ALTER TABLE crypto_klines
            ADD CONSTRAINT crypto_klines_symbol_market_period_timestamp_key
            UNIQUE (symbol, market, period, timestamp)
        """))

        # Step 3: Drop index
        print("Dropping exchange index...")
        db.execute(text("""
            DROP INDEX IF EXISTS idx_crypto_klines_exchange
        """))

        # Step 4: Drop exchange column
        print("Dropping exchange column...")
        db.execute(text("""
            ALTER TABLE crypto_klines DROP COLUMN IF EXISTS exchange
        """))

        db.commit()
        print("Rollback completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"Rollback failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Crypto Klines Exchange Migration')
    parser.add_argument('--rollback', action='store_true', help='Rollback the migration')
    args = parser.parse_args()

    if args.rollback:
        downgrade()
    else:
        upgrade()