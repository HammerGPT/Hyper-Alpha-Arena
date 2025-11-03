"""
Migration 003: Add API Wallet Fields

Adds fields to support MetaMask integration with API wallet pattern:
- api_wallet_address: Public address of delegated trading wallet
- api_wallet_registered_at: Timestamp when API wallet was registered

This migration is idempotent and backward compatible.
All new fields are optional (nullable).

Usage:
    cd backend
    uv run python database/migrations/003_add_api_wallet_fields.py
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

DB_PATH = Path(__file__).parent.parent.parent / "data.db"


def column_exists(cursor, table_name: str, column_name: str) -> bool:
    """Check if column exists in table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def add_api_wallet_fields(cursor):
    """Add API wallet fields to accounts table."""
    print("\n=== Adding API Wallet Fields ===")

    # Check and add api_wallet_address
    if not column_exists(cursor, "accounts", "api_wallet_address"):
        print("  Adding api_wallet_address column...")
        cursor.execute("""
            ALTER TABLE accounts
            ADD COLUMN api_wallet_address VARCHAR(100) NULL
        """)
        print("  ✓ api_wallet_address added")
    else:
        print("  ℹ api_wallet_address already exists")

    # Check and add api_wallet_registered_at
    if not column_exists(cursor, "accounts", "api_wallet_registered_at"):
        print("  Adding api_wallet_registered_at column...")
        cursor.execute("""
            ALTER TABLE accounts
            ADD COLUMN api_wallet_registered_at TIMESTAMP NULL
        """)
        print("  ✓ api_wallet_registered_at added")
    else:
        print("  ℹ api_wallet_registered_at already exists")


def verify_migration(cursor):
    """Verify migration was successful."""
    print("\n=== Verifying Migration ===")

    # Check api_wallet_address
    if column_exists(cursor, "accounts", "api_wallet_address"):
        print("  ✓ api_wallet_address column exists")
    else:
        print("  ✗ api_wallet_address column missing!")
        return False

    # Check api_wallet_registered_at
    if column_exists(cursor, "accounts", "api_wallet_registered_at"):
        print("  ✓ api_wallet_registered_at column exists")
    else:
        print("  ✗ api_wallet_registered_at column missing!")
        return False

    # Check account count
    cursor.execute("SELECT COUNT(*) FROM accounts")
    account_count = cursor.fetchone()[0]
    print(f"  ✓ {account_count} accounts found")

    # Verify all accounts have NULL values for new fields (expected)
    cursor.execute("""
        SELECT COUNT(*) FROM accounts
        WHERE api_wallet_address IS NOT NULL
    """)
    non_null_count = cursor.fetchone()[0]
    print(f"  ℹ {non_null_count} accounts with API wallet configured")

    return True


def main():
    """Run migration."""
    print("\n" + "=" * 60)
    print("Migration 003: Add API Wallet Fields")
    print("=" * 60)

    if not DB_PATH.exists():
        print(f"\n✗ Database not found at {DB_PATH}")
        print("  Create database first by running the application")
        sys.exit(1)

    print(f"\nDatabase: {DB_PATH}")

    # Backup recommendation
    print("\n⚠️  RECOMMENDED: Backup database before migration")
    print(f"  cp {DB_PATH} {DB_PATH}.backup")
    response = input("\nContinue with migration? (yes/no): ")

    if response.lower() not in ["yes", "y"]:
        print("Migration cancelled")
        sys.exit(0)

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Add API wallet fields
        add_api_wallet_fields(cursor)

        # Commit changes
        conn.commit()
        print("\n✓ Migration committed successfully")

        # Verify
        if verify_migration(cursor):
            print("\n✓ Migration verification passed")
            print("\n" + "=" * 60)
            print("✅ Migration 003 Complete!")
            print("=" * 60)
            print("\nNext Steps:")
            print("  1. Update Pydantic schemas to include new fields")
            print("  2. Create wallet API routes")
            print("  3. Implement frontend MetaMask integration")
        else:
            print("\n✗ Migration verification failed")
            sys.exit(1)

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Migration failed: {e}")
        print(f"  Restore from backup if needed:")
        print(f"  cp {DB_PATH}.backup {DB_PATH}")
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
