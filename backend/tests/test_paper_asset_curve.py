"""Paper trading curves on the dashboard asset-curve endpoint.

Covers Task 14: get_all_asset_curves_data_new's hyperliquid-mode branch merges
in a third curve for environment="paper" snapshots (HyperliquidAccountSnapshot),
tagging each item `is_paper: True` and suffixing `username` with " [PAPER]".

Also guards the whitelist bug the brief called out: _build_hyperliquid_asset_curve
computed `env_filter_value = environment if environment in {"testnet", "mainnet"}
else None` -- passing environment="paper" fell through to `None`, which means
*no* environment filter at all (silently returning testnet+mainnet+paper rows
mixed together) instead of paper-only rows. That whitelist now includes "paper".
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from database.connection import Base
from database.models import Account, BinanceAccountSnapshot, User
from database.snapshot_models import HyperliquidAccountSnapshot

import services.asset_curve_calculator as asset_curve_calculator
from services.asset_curve_calculator import (
    _build_hyperliquid_asset_curve,
    get_all_asset_curves_data_new,
)


def _make_account(db_session, username="t_paper_curve"):
    user = User(username=username)
    db_session.add(user)
    db_session.flush()
    account = Account(user_id=user.id, name="Claude", model="m", api_key="k")
    db_session.add(account)
    db_session.flush()
    return account


def _add_snapshot(snap, account_id, environment, total_equity, created_at):
    snap.add(HyperliquidAccountSnapshot(
        account_id=account_id, environment=environment, wallet_address=None,
        total_equity=Decimal(str(total_equity)), available_balance=Decimal(str(total_equity)),
        used_margin=Decimal("0"), created_at=created_at,
    ))
    snap.commit()


# ---------------------------------------------------------------------------
# _build_hyperliquid_asset_curve: environment="paper" must filter to paper-only
# rows, not fall through to "no filter" (the whitelist bug the brief flagged).
# ---------------------------------------------------------------------------

def test_paper_environment_filter_returns_only_paper_rows(
    db_session, snapshot_session_factory, monkeypatch
):
    monkeypatch.setattr(asset_curve_calculator, "SnapshotSessionLocal", snapshot_session_factory)

    account = _make_account(db_session)
    now = datetime.now(timezone.utc)

    snap = snapshot_session_factory()
    _add_snapshot(snap, account.id, "mainnet", 10000, now - timedelta(minutes=5))
    _add_snapshot(snap, account.id, "paper", 12345, now)
    snap.close()

    paper_rows = _build_hyperliquid_asset_curve(
        db_session, bucket_minutes=60, environment="paper",
        wallet_address=None, account_id=None, start_date=None, end_date=None,
    )

    assert len(paper_rows) == 1
    assert paper_rows[0]["total_assets"] == 12345.0
    assert paper_rows[0]["account_id"] == account.id

    # Regression: mainnet filtering is untouched by the whitelist relaxation.
    mainnet_rows = _build_hyperliquid_asset_curve(
        db_session, bucket_minutes=60, environment="mainnet",
        wallet_address=None, account_id=None, start_date=None, end_date=None,
    )
    assert len(mainnet_rows) == 1
    assert mainnet_rows[0]["total_assets"] == 10000.0


# ---------------------------------------------------------------------------
# get_all_asset_curves_data_new: hyperliquid-mode branch merges in the paper
# curve alongside hl_data/binance_data, tagging is_paper + " [PAPER]" username.
# ---------------------------------------------------------------------------

def test_get_all_asset_curves_data_new_merges_and_tags_paper_curve(
    db_session, snapshot_session_factory, monkeypatch
):
    monkeypatch.setattr(asset_curve_calculator, "SnapshotSessionLocal", snapshot_session_factory)

    # get_all_asset_curves_data_new's hyperliquid branch also calls
    # _build_binance_asset_curve, which queries BinanceAccountSnapshot on the
    # main db -- add that table to db_session's in-memory engine so the query
    # doesn't fail on "no such table" (conftest's db_session fixture doesn't
    # create it). It stays empty; no Binance rows are involved in this test.
    engine = db_session.get_bind()
    Base.metadata.create_all(engine, tables=[BinanceAccountSnapshot.__table__])

    account = _make_account(db_session)
    now = datetime.now(timezone.utc)

    snap = snapshot_session_factory()
    _add_snapshot(snap, account.id, "mainnet", 10000, now - timedelta(minutes=5))
    _add_snapshot(snap, account.id, "paper", 12345, now)
    snap.close()

    combined = get_all_asset_curves_data_new(
        db_session, timeframe="1h", trading_mode="mainnet", environment="mainnet",
    )

    paper_items = [item for item in combined if item.get("is_paper")]
    real_items = [item for item in combined if not item.get("is_paper")]

    assert len(paper_items) == 1
    assert paper_items[0]["total_assets"] == 12345.0
    assert paper_items[0]["username"] == "Claude [PAPER]"

    assert len(real_items) == 1
    assert real_items[0]["total_assets"] == 10000.0
    assert real_items[0]["username"] == "Claude"
    assert "is_paper" not in real_items[0]
