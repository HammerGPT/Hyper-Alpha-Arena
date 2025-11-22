#!/usr/bin/env python3
"""
Migration: Add user_exchange_config table for storing user exchange preferences
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from database.connection import DATABASE_URL

def migrate():
    """Add user_exchange_config table"""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Create user_exchange_config table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_exchange_config (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                selected_exchange VARCHAR(20) NOT NULL DEFAULT 'hyperliquid',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id)
            )
        """))

        # Create index for faster lookups
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_user_exchange_config_user_id
            ON user_exchange_config(user_id)
        """))

        # Insert default config for existing users (user_id=1 as default)
        conn.execute(text("""
            INSERT INTO user_exchange_config (user_id, selected_exchange)
            VALUES (1, 'hyperliquid')
            ON CONFLICT (user_id) DO NOTHING
        """))

        conn.commit()
        print("✅ user_exchange_config table created successfully")

if __name__ == "__main__":
    migrate()