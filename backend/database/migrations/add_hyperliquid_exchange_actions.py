"""
Migration script to add the hyperliquid_exchange_actions table.

Usage:
    cd /home/wwwroot/hyper-alpha-arena-prod/backend
    source .venv/bin/activate
    python database/migrations/add_hyperliquid_exchange_actions.py
"""
import os
import sys

from sqlalchemy import inspect

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, PROJECT_ROOT)

from database.connection import engine  # noqa: E402
from database.models import HyperliquidExchangeAction  # noqa: E402


def main():
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "hyperliquid_exchange_actions" in tables:
        print("✅ hyperliquid_exchange_actions table already exists, skipping")
        return

    HyperliquidExchangeAction.__table__.create(bind=engine)
    print("✅ hyperliquid_exchange_actions table created successfully")


if __name__ == "__main__":
    main()
