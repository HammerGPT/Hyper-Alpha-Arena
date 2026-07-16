"""Shared fixtures: in-memory SQLite for main and snapshot databases."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _memory_engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture()
def db_session():
    from database.connection import Base
    from database.models import (  # noqa: F401 - register tables
        User, Account, AccountStrategyConfig, AIDecisionLog,
        PaperAccount, PaperPosition, PaperOrder, PaperFundingRecord,
    )
    engine = _memory_engine()
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__, Account.__table__, AccountStrategyConfig.__table__,
            AIDecisionLog.__table__,
            PaperAccount.__table__, PaperPosition.__table__,
            PaperOrder.__table__, PaperFundingRecord.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def snapshot_session_factory():
    from database.snapshot_connection import SnapshotBase
    from database.snapshot_models import HyperliquidTrade, HyperliquidAccountSnapshot  # noqa: F401
    engine = _memory_engine()
    SnapshotBase.metadata.create_all(
        engine,
        tables=[HyperliquidTrade.__table__, HyperliquidAccountSnapshot.__table__],
    )
    return sessionmaker(bind=engine)


@pytest.fixture()
def paper_account(db_session):
    """A PaperAccount with $10,000 initial capital (account_id=1, hyperliquid data)."""
    from database.models import PaperAccount
    paper = PaperAccount(account_id=1, data_exchange="hyperliquid")
    db_session.add(paper)
    db_session.flush()
    return paper
