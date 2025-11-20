"""
Migration: Add sampling_depth to global_sampling_configs table

This migration moves sampling_depth from per-account configuration to global configuration.
Sampling pool is shared across all AI traders, so depth should be a global setting.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.connection import SessionLocal
from sqlalchemy import text
from datetime import datetime, timezone

def upgrade():
    """Apply migration"""
    db = SessionLocal()
    try:
        print("Adding sampling_depth column to global_sampling_configs table...")

        # Add sampling_depth column
        db.execute(text("""
            ALTER TABLE global_sampling_configs
            ADD COLUMN sampling_depth INTEGER NOT NULL DEFAULT 10
        """))

        db.commit()
        print("✓ sampling_depth column added to global_sampling_configs table")

        # Check if config exists, if not create default
        result = db.execute(text("SELECT COUNT(*) FROM global_sampling_configs"))
        count = result.scalar()

        if count == 0:
            print("Creating default global sampling configuration...")
            db.execute(text("""
                INSERT INTO global_sampling_configs (sampling_interval, sampling_depth)
                VALUES (18, 10)
            """))
            db.commit()
            print("✓ Default configuration created (interval=18s, depth=10)")
        else:
            print(f"✓ Existing configuration found ({count} records)")

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
        print("Removing sampling_depth column from global_sampling_configs table...")

        db.execute(text("""
            ALTER TABLE global_sampling_configs
            DROP COLUMN sampling_depth
        """))

        db.commit()
        print("✓ sampling_depth column removed")
        print("\n✅ Rollback completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Rollback failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    upgrade()
