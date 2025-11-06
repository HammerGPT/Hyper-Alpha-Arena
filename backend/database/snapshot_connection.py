"""
Snapshot database connection - separate from main database to avoid locks
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Snapshot database URL from environment or default
SNAPSHOT_DATABASE_URL = os.environ.get('SNAPSHOT_DATABASE_URL', "postgresql://alpha_user:alpha_pass@localhost/alpha_snapshots")

# Create engine for snapshot database
snapshot_engine = create_engine(SNAPSHOT_DATABASE_URL)

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