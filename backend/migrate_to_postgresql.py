#!/usr/bin/env python3
"""
Migrate data from SQLite to PostgreSQL
"""
import sqlite3
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# SQLite connection
sqlite_conn = sqlite3.connect('data.db')
sqlite_conn.row_factory = sqlite3.Row

# PostgreSQL connection
pg_engine = create_engine("postgresql://alpha_user:alpha_pass@localhost/alpha_arena")
PgSession = sessionmaker(bind=pg_engine)

def migrate_table(table_name, columns):
    """Migrate a table from SQLite to PostgreSQL"""
    print(f"Migrating {table_name}...")

    # Get data from SQLite
    cursor = sqlite_conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()

    if not rows:
        print(f"  No data in {table_name}")
        return

    # Insert into PostgreSQL
    pg_session = PgSession()
    try:
        for row in rows:
            values = []
            for col in columns:
                if row[col] is not None:
                    escaped_value = str(row[col]).replace("'", "''")
                    values.append(f"'{escaped_value}'")
                else:
                    values.append('NULL')
            query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(values)})"
            pg_session.execute(text(query))

        pg_session.commit()
        print(f"  Migrated {len(rows)} rows")
    except Exception as e:
        print(f"  Error migrating {table_name}: {e}")
        pg_session.rollback()
    finally:
        pg_session.close()

def main():
    print("Starting migration from SQLite to PostgreSQL...")

    # Check if SQLite tables exist
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    print(f"Found tables: {tables}")

    # Migrate essential tables
    if 'accounts' in tables:
        migrate_table('accounts', [
            'id', 'name', 'model', 'current_cash', 'frozen_cash', 'is_active',
            'account_type', 'hyperliquid_enabled', 'hyperliquid_environment',
            'hyperliquid_private_key', 'hyperliquid_wallet_address', 'created_at'
        ])

    if 'positions' in tables:
        migrate_table('positions', [
            'id', 'account_id', 'symbol', 'market', 'quantity', 'average_price',
            'current_price', 'unrealized_pnl', 'created_at', 'updated_at'
        ])

    if 'trades' in tables:
        migrate_table('trades', [
            'id', 'account_id', 'symbol', 'market', 'side', 'quantity', 'price',
            'trade_value', 'fee', 'trade_time', 'created_at'
        ])

    if 'strategies' in tables:
        migrate_table('strategies', [
            'id', 'account_id', 'name', 'description', 'prompt_template',
            'is_active', 'created_at', 'updated_at'
        ])

    print("Migration completed!")

if __name__ == "__main__":
    main()