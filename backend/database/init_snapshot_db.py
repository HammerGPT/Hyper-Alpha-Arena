"""
Initialize snapshot database tables
"""
from database.snapshot_connection import snapshot_engine
from database.snapshot_models import SnapshotBase

def init_snapshot_database():
    """Create all snapshot database tables"""
    SnapshotBase.metadata.create_all(bind=snapshot_engine)
    print("Snapshot database tables created successfully")

if __name__ == "__main__":
    init_snapshot_database()