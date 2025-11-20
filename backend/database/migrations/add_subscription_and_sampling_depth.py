"""
Database migration: Add user subscriptions and sampling depth configuration

This migration adds:
1. user_subscriptions table for tracking premium subscriptions
2. sampling_depth column to accounts table
"""

import sys
import os
from datetime import datetime, timedelta, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlalchemy import text
from database.connection import SessionLocal, engine


def upgrade():
    """Apply migration"""
    db = SessionLocal()

    try:
        print("Starting migration: add_subscription_and_sampling_depth")

        # Step 1: Create user_subscriptions table
        print("Creating user_subscriptions table...")
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                subscription_type VARCHAR(20) NOT NULL DEFAULT 'free',
                expires_at TIMESTAMP,
                max_sampling_depth INTEGER NOT NULL DEFAULT 20,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT user_subscriptions_user_id_unique UNIQUE (user_id),
                CONSTRAINT user_subscriptions_subscription_type_check
                    CHECK (subscription_type IN ('free', 'premium'))
            )
        """))
        db.commit()
        print("✓ user_subscriptions table created")

        # Step 2: Add sampling_depth column to accounts table
        print("Adding sampling_depth column to accounts table...")

        # Check if column already exists
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='accounts' AND column_name='sampling_depth'
        """))

        if result.fetchone() is None:
            db.execute(text("""
                ALTER TABLE accounts
                ADD COLUMN sampling_depth INTEGER NOT NULL DEFAULT 20
            """))
            db.commit()
            print("✓ sampling_depth column added to accounts table")
        else:
            print("✓ sampling_depth column already exists")

        # Step 3: Create default free subscriptions for existing users
        print("Creating default free subscriptions for existing users...")
        db.execute(text("""
            INSERT INTO user_subscriptions (user_id, subscription_type, max_sampling_depth)
            SELECT id, 'free', 20
            FROM users
            WHERE id NOT IN (SELECT user_id FROM user_subscriptions)
        """))
        db.commit()
        print("✓ Default subscriptions created")

        # Step 4: Create test premium subscription for default user (for development)
        print("Creating test premium subscription for user_id=1 (development only)...")
        future_expiry = datetime.now(timezone.utc) + timedelta(days=365)
        db.execute(text("""
            INSERT INTO user_subscriptions (user_id, subscription_type, expires_at, max_sampling_depth)
            VALUES (1, 'premium', :expires_at, 60)
            ON CONFLICT (user_id)
            DO UPDATE SET
                subscription_type = 'premium',
                expires_at = :expires_at,
                max_sampling_depth = 60
        """), {"expires_at": future_expiry})
        db.commit()
        print(f"✓ Test premium subscription created (expires: {future_expiry.isoformat()})")

        print("\n✅ Migration completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        db.close()


def downgrade():
    """Rollback migration"""
    db = SessionLocal()

    try:
        print("Rolling back migration: add_subscription_and_sampling_depth")

        # Remove sampling_depth column
        print("Removing sampling_depth column from accounts table...")
        db.execute(text("ALTER TABLE accounts DROP COLUMN IF EXISTS sampling_depth"))
        db.commit()
        print("✓ sampling_depth column removed")

        # Drop user_subscriptions table
        print("Dropping user_subscriptions table...")
        db.execute(text("DROP TABLE IF EXISTS user_subscriptions"))
        db.commit()
        print("✓ user_subscriptions table dropped")

        print("\n✅ Rollback completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Rollback failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Database migration for subscriptions and sampling depth")
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()

    if args.rollback:
        downgrade()
    else:
        upgrade()
