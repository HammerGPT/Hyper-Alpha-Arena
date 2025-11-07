"""
Add wallet_address column to ai_decision_logs table.

Usage:
    cd /home/wwwroot/hyper-alpha-arena-prod/backend
    source .venv/bin/activate
    python database/migrations/add_wallet_address_to_ai_decision_logs.py
"""
import os
import sys

from sqlalchemy import inspect, text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, PROJECT_ROOT)

from database.connection import engine  # noqa: E402


def column_exists(inspector, table: str, column: str) -> bool:
    return column in {col["name"] for col in inspector.get_columns(table)}


def main() -> None:
    inspector = inspect(engine)

    with engine.connect() as conn:
        if not column_exists(inspector, "ai_decision_logs", "wallet_address"):
            conn.execute(text("ALTER TABLE ai_decision_logs ADD COLUMN wallet_address VARCHAR(100)"))
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_ai_decision_logs_wallet_address "
                    "ON ai_decision_logs (wallet_address)"
                )
            )
            print("✅ Added wallet_address to ai_decision_logs")
        else:
            print("ℹ️  wallet_address already exists on ai_decision_logs")

        conn.commit()


if __name__ == "__main__":
    main()
