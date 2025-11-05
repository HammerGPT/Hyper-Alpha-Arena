"""
Add hyperliquid_environment column to trades and ai_decision_logs tables
"""
import sqlite3
import sys
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "data.db"

def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        # Check if column already exists in trades
        cursor.execute("PRAGMA table_info(trades)")
        trades_columns = [col[1] for col in cursor.fetchall()]

        if 'hyperliquid_environment' not in trades_columns:
            print("Adding hyperliquid_environment column to trades table...")
            cursor.execute("""
                ALTER TABLE trades
                ADD COLUMN hyperliquid_environment VARCHAR(20) DEFAULT NULL
            """)
            print("✓ Added hyperliquid_environment to trades")
        else:
            print("✓ trades.hyperliquid_environment already exists")

        # Check if column already exists in ai_decision_logs
        cursor.execute("PRAGMA table_info(ai_decision_logs)")
        ai_columns = [col[1] for col in cursor.fetchall()]

        if 'hyperliquid_environment' not in ai_columns:
            print("Adding hyperliquid_environment column to ai_decision_logs table...")
            cursor.execute("""
                ALTER TABLE ai_decision_logs
                ADD COLUMN hyperliquid_environment VARCHAR(20) DEFAULT NULL
            """)
            print("✓ Added hyperliquid_environment to ai_decision_logs")
        else:
            print("✓ ai_decision_logs.hyperliquid_environment already exists")

        # Create indexes
        print("Creating indexes...")
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_hyperliquid_environment
                ON trades(hyperliquid_environment)
            """)
            print("✓ Created index on trades.hyperliquid_environment")
        except sqlite3.OperationalError as e:
            print(f"Index already exists: {e}")

        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_decision_logs_hyperliquid_environment
                ON ai_decision_logs(hyperliquid_environment)
            """)
            print("✓ Created index on ai_decision_logs.hyperliquid_environment")
        except sqlite3.OperationalError as e:
            print(f"Index already exists: {e}")

        conn.commit()
        print("\n✅ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
