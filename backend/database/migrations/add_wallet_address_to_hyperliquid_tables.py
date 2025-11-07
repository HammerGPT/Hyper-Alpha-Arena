"""
Migration script to add wallet_address columns to Hyperliquid tables in the main DB.

Usage:
    cd /home/wwwroot/hyper-alpha-arena-prod/backend
    source .venv/bin/activate
    python database/migrations/add_wallet_address_to_hyperliquid_tables.py
"""
import os
import sys

from sqlalchemy import inspect, text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, PROJECT_ROOT)

from database.connection import engine  # noqa: E402


def column_exists(inspector, table: str, column: str) -> bool:
    columns = [col["name"] for col in inspector.get_columns(table)]
    return column in columns


def main():
    inspector = inspect(engine)

    with engine.connect() as conn:
        if not column_exists(inspector, "hyperliquid_account_snapshots", "wallet_address"):
            conn.execute(
                text("ALTER TABLE hyperliquid_account_snapshots ADD COLUMN wallet_address VARCHAR(100)")
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_hlas_wallet_address ON hyperliquid_account_snapshots (wallet_address)")
            )
            print("✅ Added wallet_address to hyperliquid_account_snapshots")
        else:
            print("ℹ️  wallet_address already exists on hyperliquid_account_snapshots")

        if not column_exists(inspector, "hyperliquid_positions", "wallet_address"):
            conn.execute(
                text("ALTER TABLE hyperliquid_positions ADD COLUMN wallet_address VARCHAR(100)")
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_hlp_wallet_address ON hyperliquid_positions (wallet_address)")
            )
            print("✅ Added wallet_address to hyperliquid_positions")
        else:
            print("ℹ️  wallet_address already exists on hyperliquid_positions")

        conn.commit()


if __name__ == "__main__":
    main()
