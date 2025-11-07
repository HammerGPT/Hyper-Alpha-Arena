"""
Add wallet_address column to hyperliquid_trades table in the snapshot DB.

Usage:
    cd /home/wwwroot/hyper-alpha-arena-prod/backend
    source .venv/bin/activate
    python database/migrations/add_wallet_address_to_hyperliquid_trades.py
"""
import os
import sys

from sqlalchemy import inspect, text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, PROJECT_ROOT)

from database.snapshot_connection import snapshot_engine  # noqa: E402


def column_exists(inspector, table: str, column: str) -> bool:
    return column in {col["name"] for col in inspector.get_columns(table)}


def main() -> None:
    inspector = inspect(snapshot_engine)

    with snapshot_engine.connect() as conn:
        if not column_exists(inspector, "hyperliquid_trades", "wallet_address"):
            conn.execute(text("ALTER TABLE hyperliquid_trades ADD COLUMN wallet_address VARCHAR(100)"))
            print("✅ Added wallet_address to hyperliquid_trades")
        else:
            print("ℹ️  wallet_address already exists on hyperliquid_trades")

        conn.commit()


if __name__ == "__main__":
    main()
