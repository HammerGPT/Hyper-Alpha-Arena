#!/usr/bin/env python3
"""
Migration: Create price_samples table for persistent sampling data

This migration creates a new table to store price sampling data that was
previously only kept in memory. This ensures sampling data survives service
restarts and provides historical context for AI decisions.

Table: price_samples
- Stores individual price samples with timestamps
- Supports multi-exchange data
- Enables service restart recovery
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from connection import SessionLocal, engine


def upgrade():
    """Apply the migration"""
    print("Starting migration: create_price_samples_table")

    db = SessionLocal()
    try:
        # Create price_samples table
        print("Creating price_samples table...")
        db.execute(text("""
            CREATE TABLE price_samples (
                id SERIAL PRIMARY KEY,
                exchange VARCHAR(20) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                price DECIMAL(18, 8) NOT NULL,
                sample_time TIMESTAMP NOT NULL,
                account_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create indexes for performance
        print("Creating indexes...")
        db.execute(text("""
            CREATE INDEX idx_price_samples_exchange ON price_samples(exchange)
        """))

        db.execute(text("""
            CREATE INDEX idx_price_samples_symbol ON price_samples(symbol)
        """))

        db.execute(text("""
            CREATE INDEX idx_price_samples_sample_time ON price_samples(sample_time)
        """))

        db.execute(text("""
            CREATE INDEX idx_price_samples_exchange_symbol ON price_samples(exchange, symbol)
        """))

        db.execute(text("""
            CREATE INDEX idx_price_samples_exchange_symbol_time ON price_samples(exchange, symbol, sample_time)
        """))

        # Add foreign key constraint for account_id (optional)
        print("Adding foreign key constraint...")
        db.execute(text("""
            ALTER TABLE price_samples
            ADD CONSTRAINT fk_price_samples_account_id
            FOREIGN KEY (account_id) REFERENCES accounts(id)
            ON DELETE SET NULL
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
    print("Starting rollback: create_price_samples_table")

    db = SessionLocal()
    try:
        # Drop the table (this will also drop all indexes and constraints)
        print("Dropping price_samples table...")
        db.execute(text("""
            DROP TABLE IF EXISTS price_samples CASCADE
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
    parser = argparse.ArgumentParser(description='Price Samples Table Migration')
    parser.add_argument('--rollback', action='store_true', help='Rollback the migration')
    args = parser.parse_args()

    if args.rollback:
        downgrade()
    else:
        upgrade()