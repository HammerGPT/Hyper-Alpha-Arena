#!/usr/bin/env python3
"""
Migration: Create perp_funding table for perpetual contract funding rates

This migration creates a new table to store funding rate data for perpetual
contracts from multiple exchanges.

Table: perp_funding
- Stores funding rate snapshots for each exchange/symbol/timestamp
- Supports multi-exchange data collection
- Essential for accurate PnL calculation in backtesting
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from connection import SessionLocal, engine


def upgrade():
    """Apply the migration"""
    print("Starting migration: create_perp_funding_table")

    db = SessionLocal()
    try:
        # Create perp_funding table
        print("Creating perp_funding table...")
        db.execute(text("""
            CREATE TABLE perp_funding (
                id SERIAL PRIMARY KEY,
                exchange VARCHAR(20) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                timestamp INTEGER NOT NULL,
                funding_rate DECIMAL(18, 8) NOT NULL,
                mark_price DECIMAL(18, 6),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                CONSTRAINT perp_funding_exchange_symbol_timestamp_key
                UNIQUE (exchange, symbol, timestamp)
            )
        """))

        # Create indexes for performance
        print("Creating indexes...")
        db.execute(text("""
            CREATE INDEX idx_perp_funding_exchange ON perp_funding(exchange)
        """))

        db.execute(text("""
            CREATE INDEX idx_perp_funding_symbol ON perp_funding(symbol)
        """))

        db.execute(text("""
            CREATE INDEX idx_perp_funding_timestamp ON perp_funding(timestamp)
        """))

        db.execute(text("""
            CREATE INDEX idx_perp_funding_exchange_symbol ON perp_funding(exchange, symbol)
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
    print("Starting rollback: create_perp_funding_table")

    db = SessionLocal()
    try:
        # Drop the table (this will also drop all indexes)
        print("Dropping perp_funding table...")
        db.execute(text("""
            DROP TABLE IF EXISTS perp_funding CASCADE
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
    parser = argparse.ArgumentParser(description='Perp Funding Table Migration')
    parser.add_argument('--rollback', action='store_true', help='Rollback the migration')
    args = parser.parse_args()

    if args.rollback:
        downgrade()
    else:
        upgrade()