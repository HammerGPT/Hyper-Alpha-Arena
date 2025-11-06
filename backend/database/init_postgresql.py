#!/usr/bin/env python3
"""
PostgreSQL database initialization script
Automatically creates databases and tables for Hyper Alpha Arena
"""

import sys
import logging
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import OperationalError, ProgrammingError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
DB_USER = "alpha_user"
DB_PASSWORD = "alpha_pass"
DB_HOST = "localhost"
MAIN_DB_NAME = "alpha_arena"
SNAPSHOT_DB_NAME = "alpha_snapshots"


def create_postgres_user_and_databases():
    """Create PostgreSQL user and databases if they don't exist"""
    try:
        # Connect to PostgreSQL default database
        admin_engine = create_engine(f"postgresql://postgres@{DB_HOST}/postgres", isolation_level="AUTOCOMMIT")

        with admin_engine.connect() as conn:
            # Check if user exists
            result = conn.execute(text(
                f"SELECT 1 FROM pg_roles WHERE rolname='{DB_USER}'"
            ))
            user_exists = result.fetchone() is not None

            if not user_exists:
                logger.info(f"Creating PostgreSQL user: {DB_USER}")
                conn.execute(text(
                    f"CREATE USER {DB_USER} WITH PASSWORD '{DB_PASSWORD}'"
                ))
                logger.info(f"✓ User {DB_USER} created successfully")
            else:
                logger.info(f"✓ User {DB_USER} already exists")

            # Create main database
            result = conn.execute(text(
                f"SELECT 1 FROM pg_database WHERE datname='{MAIN_DB_NAME}'"
            ))
            main_db_exists = result.fetchone() is not None

            if not main_db_exists:
                logger.info(f"Creating database: {MAIN_DB_NAME}")
                conn.execute(text(f"CREATE DATABASE {MAIN_DB_NAME} OWNER {DB_USER}"))
                logger.info(f"✓ Database {MAIN_DB_NAME} created successfully")
            else:
                logger.info(f"✓ Database {MAIN_DB_NAME} already exists")

            # Create snapshot database
            result = conn.execute(text(
                f"SELECT 1 FROM pg_database WHERE datname='{SNAPSHOT_DB_NAME}'"
            ))
            snapshot_db_exists = result.fetchone() is not None

            if not snapshot_db_exists:
                logger.info(f"Creating database: {SNAPSHOT_DB_NAME}")
                conn.execute(text(f"CREATE DATABASE {SNAPSHOT_DB_NAME} OWNER {DB_USER}"))
                logger.info(f"✓ Database {SNAPSHOT_DB_NAME} created successfully")
            else:
                logger.info(f"✓ Database {SNAPSHOT_DB_NAME} already exists")

        return True

    except OperationalError as e:
        if "could not connect to server" in str(e):
            logger.error("❌ PostgreSQL is not running. Please start PostgreSQL service.")
            logger.error("   Ubuntu/Debian: sudo systemctl start postgresql")
            logger.error("   macOS: brew services start postgresql")
            return False
        elif "peer authentication failed" in str(e):
            logger.error("❌ PostgreSQL authentication failed.")
            logger.error("   You may need to configure PostgreSQL to allow local connections.")
            logger.error("   Edit /etc/postgresql/*/main/pg_hba.conf and change 'peer' to 'trust' for local connections.")
            return False
        else:
            logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
            return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False


def create_tables():
    """Create all tables in the databases"""
    try:
        # Import models to register them with SQLAlchemy
        from database.connection import engine, Base
        from database.snapshot_connection import snapshot_engine, SnapshotBase
        from database import models  # This imports all model definitions
        from database import snapshot_models  # This imports snapshot model definitions

        # Create main database tables
        logger.info("Creating main database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Main database tables created successfully")

        # Create snapshot database tables
        logger.info("Creating snapshot database tables...")
        SnapshotBase.metadata.create_all(bind=snapshot_engine)
        logger.info("✓ Snapshot database tables created successfully")

        return True

    except Exception as e:
        logger.error(f"❌ Failed to create tables: {e}")
        return False


def verify_setup():
    """Verify that the setup is complete"""
    try:
        from database.connection import engine
        from database.snapshot_connection import snapshot_engine

        # Check main database
        inspector = inspect(engine)
        main_tables = inspector.get_table_names()
        logger.info(f"✓ Main database has {len(main_tables)} tables")

        # Check snapshot database
        inspector = inspect(snapshot_engine)
        snapshot_tables = inspector.get_table_names()
        logger.info(f"✓ Snapshot database has {len(snapshot_tables)} tables")

        if len(main_tables) > 0 and len(snapshot_tables) > 0:
            logger.info("✅ PostgreSQL setup completed successfully!")
            return True
        else:
            logger.error("❌ Setup incomplete: some tables are missing")
            return False

    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return False


def main():
    """Main initialization function"""
    logger.info("=" * 60)
    logger.info("Hyper Alpha Arena - PostgreSQL Initialization")
    logger.info("=" * 60)

    # Step 1: Create user and databases
    if not create_postgres_user_and_databases():
        logger.error("\n❌ Database initialization failed!")
        logger.error("Please ensure PostgreSQL is installed and running.")
        return 1

    # Step 2: Create tables
    if not create_tables():
        logger.error("\n❌ Table creation failed!")
        return 1

    # Step 3: Verify setup
    if not verify_setup():
        logger.error("\n❌ Setup verification failed!")
        return 1

    logger.info("\n" + "=" * 60)
    logger.info("✅ All database initialization tasks completed!")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
