"""
Snapshot database connection - separate from main database to avoid locks
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
import os
import logging

logger = logging.getLogger(__name__)

# Snapshot database URL from environment or default
SNAPSHOT_DATABASE_URL = os.environ.get('SNAPSHOT_DATABASE_URL', "postgresql://alpha_user:alpha_pass@localhost/alpha_snapshots")

def _ensure_snapshot_engine():
    """Create snapshot database if it does not already exist."""
    url = make_url(SNAPSHOT_DATABASE_URL)
    db_name = url.database

    try:
        engine = create_engine(SNAPSHOT_DATABASE_URL)
        with engine.connect():
            logger.debug("Snapshot database %s reachable", db_name)
        return engine
    except OperationalError as exc:
        message = str(exc).lower()
        if "does not exist" not in message:
            raise

        logger.warning("Snapshot database %s missing – creating it", db_name)
        admin_url = url.set(database='postgres')
        admin_engine = create_engine(admin_url)
        try:
            with admin_engine.connect() as conn:
                conn = conn.execution_options(isolation_level='AUTOCOMMIT')
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                logger.info("Snapshot database %s created", db_name)
        finally:
            admin_engine.dispose()

        engine = create_engine(SNAPSHOT_DATABASE_URL)
        with engine.connect():
            logger.debug("Snapshot database %s ready after creation", db_name)
        return engine


# Create engine for snapshot database
snapshot_engine = _ensure_snapshot_engine()

# Session factory for snapshot database
SnapshotSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=snapshot_engine)

# Base class for snapshot models
SnapshotBase = declarative_base()

def get_snapshot_db():
    """Get snapshot database session"""
    db = SnapshotSessionLocal()
    try:
        yield db
    finally:
        db.close()
