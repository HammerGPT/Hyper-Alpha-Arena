from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DATABASE_URL = os.environ.get('DATABASE_URL', "postgresql://alpha_user:alpha_pass@localhost/alpha_arena")

# Allow tuning via environment variables but provide sensible defaults for our workload
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "20"))
POOL_MAX_OVERFLOW = int(os.environ.get("DB_POOL_MAX_OVERFLOW", "20"))
POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE", "1800"))  # seconds
POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", "30"))

engine = create_engine(
    DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=POOL_MAX_OVERFLOW,
    pool_recycle=POOL_RECYCLE,
    pool_timeout=POOL_TIMEOUT,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
