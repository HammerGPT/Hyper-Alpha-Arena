"""
Migration script to add AWS Bedrock support fields to the accounts table
Run this script to add the new Bedrock fields to existing databases:
    python backend/migrations/add_bedrock_fields.py
"""
import sqlite3
import os
import sys

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def run_migration():
    # Get database path
    db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data.db')

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        print("This might be a fresh install. The new schema will be created automatically.")
        return

    print(f"Running migration on database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if the columns already exist
    cursor.execute("PRAGMA table_info(accounts)")
    columns = [row[1] for row in cursor.fetchall()]

    migrations_to_run = []

    if 'provider_type' not in columns:
        migrations_to_run.append(
            "ALTER TABLE accounts ADD COLUMN provider_type VARCHAR(20) DEFAULT 'openai' NOT NULL"
        )

    if 'aws_region' not in columns:
        migrations_to_run.append(
            "ALTER TABLE accounts ADD COLUMN aws_region VARCHAR(50) DEFAULT 'us-east-1'"
        )

    if 'aws_access_key_id' not in columns:
        migrations_to_run.append(
            "ALTER TABLE accounts ADD COLUMN aws_access_key_id VARCHAR(500)"
        )

    if 'aws_secret_access_key' not in columns:
        migrations_to_run.append(
            "ALTER TABLE accounts ADD COLUMN aws_secret_access_key VARCHAR(500)"
        )

    if not migrations_to_run:
        print("All Bedrock fields already exist. No migration needed.")
        conn.close()
        return

    print(f"Adding {len(migrations_to_run)} new column(s) to accounts table...")

    try:
        for sql in migrations_to_run:
            print(f"Executing: {sql}")
            cursor.execute(sql)

        conn.commit()
        print("Migration completed successfully!")
        print("AWS Bedrock support has been added to your database.")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
