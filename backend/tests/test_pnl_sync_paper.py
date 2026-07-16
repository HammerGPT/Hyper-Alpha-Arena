"""Paper trading PnL sync semantics for arena_routes.

Covers:
- check-pnl-status: "paper" now filters on environment == "paper" (new paper
  trading), not the legacy environment IS NULL semantics.
- update_pnl_data's paper backfill safety net (_backfill_paper_pnl), including
  the PnL-recovery deviation from the Task 13 brief's literal snippet.
"""
from datetime import datetime
from decimal import Decimal

from database.models import (
    AIDecisionLog, PaperOrder, User, Account, HyperliquidWallet, BinanceWallet,
)
from database.snapshot_models import HyperliquidTrade
from database.connection import Base
import api.arena_routes as arena_routes
from api.arena_routes import _backfill_paper_pnl, check_pnl_sync_status


def _make_account(db_session, username):
    u = User(username=username)
    db_session.add(u)
    db_session.flush()
    account = Account(user_id=u.id, name="T", model="m", api_key="k")
    db_session.add(account)
    db_session.flush()
    return account


def _make_decision(db_session, account, tp_order_id=None, sl_order_id=None):
    log = AIDecisionLog(
        account_id=account.id, reason="r", operation="buy", symbol="BTC",
        prev_portion=0, target_portion=0.1, total_balance=10000,
        executed="true", hyperliquid_environment="paper",
        tp_order_id=tp_order_id, sl_order_id=sl_order_id, exchange="hyperliquid",
    )
    db_session.add(log)
    db_session.flush()
    return log


def _make_filled_tpsl_order(db_session, paper_account, order_no, side, entry_price, size=0.1):
    order = PaperOrder(
        paper_account_id=paper_account.id, order_no=order_no, symbol="BTC",
        side=side, order_type="take_profit", trigger_price=110000,
        size=size, entry_price=entry_price, status="filled",
        filled_at=datetime.utcnow(), cycle=1,
    )
    db_session.add(order)
    db_session.flush()
    return order


def _make_fill_row(snap, order_no, side, qty, price, account_id=1):
    snap.add(HyperliquidTrade(
        account_id=account_id, environment="paper", wallet_address=f"paper-{account_id}",
        symbol="BTC", side=side, quantity=Decimal(str(qty)), price=Decimal(str(price)),
        leverage=2, order_id=order_no, order_status="filled",
        trade_value=Decimal(str(qty)) * Decimal(str(price)), fee=Decimal("1.65"),
    ))
    snap.commit()


# ---------------------------------------------------------------------------
# _backfill_paper_pnl: the deviation from the brief -- recovering realized_pnl
# ---------------------------------------------------------------------------

def test_backfill_recovers_pnl_for_long_close(db_session, snapshot_session_factory, paper_account):
    """TP order closes a long: pnl = (fill_price - entry_price) * qty."""
    account = _make_account(db_session, "t_pnl_long")
    _make_filled_tpsl_order(db_session, paper_account, "P-tp1", side="sell", entry_price=100000)
    decision = _make_decision(db_session, account, tp_order_id="P-tp1")

    snap = snapshot_session_factory()
    _make_fill_row(snap, "P-tp1", side="sell", qty=0.1, price=110000)

    result = _backfill_paper_pnl(db_session, snap)

    assert result == {"backfilled": 1}
    db_session.refresh(decision)
    assert float(decision.realized_pnl) == 1000.0  # (110000 - 100000) * 0.1
    assert decision.pnl_updated_at is not None
    snap.close()


def test_backfill_recovers_pnl_for_short_close(db_session, snapshot_session_factory, paper_account):
    """SL order closes a short: pnl = (entry_price - fill_price) * qty."""
    account = _make_account(db_session, "t_pnl_short")
    # Short position's close side is "buy" (see PaperEngine._register_tpsl).
    _make_filled_tpsl_order(db_session, paper_account, "P-sl1", side="buy", entry_price=100000)
    decision = _make_decision(db_session, account, sl_order_id="P-sl1")

    snap = snapshot_session_factory()
    _make_fill_row(snap, "P-sl1", side="buy", qty=0.1, price=95000)

    result = _backfill_paper_pnl(db_session, snap)

    assert result == {"backfilled": 1}
    db_session.refresh(decision)
    assert float(decision.realized_pnl) == 500.0  # (100000 - 95000) * 0.1
    assert decision.pnl_updated_at is not None
    snap.close()


def test_backfill_falls_back_to_stamp_only_when_entry_price_missing(
    db_session, snapshot_session_factory, paper_account
):
    """No entry_price on the PaperOrder -> can't reconstruct PnL; brief's literal
    fallback applies: stamp pnl_updated_at, leave realized_pnl NULL."""
    account = _make_account(db_session, "t_pnl_no_entry")
    _make_filled_tpsl_order(db_session, paper_account, "P-tp2", side="sell", entry_price=None)
    decision = _make_decision(db_session, account, tp_order_id="P-tp2")

    snap = snapshot_session_factory()
    _make_fill_row(snap, "P-tp2", side="sell", qty=0.1, price=110000)

    result = _backfill_paper_pnl(db_session, snap)

    assert result == {"backfilled": 1}
    db_session.refresh(decision)
    assert decision.realized_pnl is None
    assert decision.pnl_updated_at is not None
    snap.close()


def test_backfill_falls_back_to_stamp_only_when_no_fill_row(
    db_session, snapshot_session_factory, paper_account
):
    """PaperOrder filled but the snapshot fill row is missing -> same fallback."""
    account = _make_account(db_session, "t_pnl_no_fill")
    _make_filled_tpsl_order(db_session, paper_account, "P-tp3", side="sell", entry_price=100000)
    decision = _make_decision(db_session, account, tp_order_id="P-tp3")

    snap = snapshot_session_factory()  # no HyperliquidTrade row created

    result = _backfill_paper_pnl(db_session, snap)

    assert result == {"backfilled": 1}
    db_session.refresh(decision)
    assert decision.realized_pnl is None
    assert decision.pnl_updated_at is not None
    snap.close()


def test_backfill_skips_pending_tpsl_order(db_session, snapshot_session_factory, paper_account):
    """Entry order with TP/SL still pending (position not closed yet) stays unsynced."""
    account = _make_account(db_session, "t_pnl_pending")
    order = PaperOrder(
        paper_account_id=paper_account.id, order_no="P-tp4", symbol="BTC",
        side="sell", order_type="take_profit", trigger_price=110000,
        size=0.1, entry_price=100000, status="pending", cycle=1,
    )
    db_session.add(order)
    db_session.flush()
    decision = _make_decision(db_session, account, tp_order_id="P-tp4")

    snap = snapshot_session_factory()

    result = _backfill_paper_pnl(db_session, snap)

    assert result == {"backfilled": 0}
    db_session.refresh(decision)
    assert decision.realized_pnl is None
    assert decision.pnl_updated_at is None
    snap.close()


def test_backfill_stamps_pnl_updated_at_when_realized_pnl_already_set(
    db_session, snapshot_session_factory, paper_account
):
    """A row that already has realized_pnl (e.g. written by
    program_execution_service, which sets realized_pnl without stamping
    pnl_updated_at) gets pnl_updated_at stamped here so it drops out of the
    "needs sync" count -- but realized_pnl must NOT be recomputed/overwritten."""
    account = _make_account(db_session, "t_pnl_existing")
    _make_filled_tpsl_order(db_session, paper_account, "P-tp5", side="sell", entry_price=100000)
    decision = _make_decision(db_session, account, tp_order_id="P-tp5")
    decision.realized_pnl = Decimal("42")
    db_session.flush()

    snap = snapshot_session_factory()
    _make_fill_row(snap, "P-tp5", side="sell", qty=0.1, price=110000)

    result = _backfill_paper_pnl(db_session, snap)

    assert result == {"backfilled": 1}
    db_session.refresh(decision)
    assert float(decision.realized_pnl) == 42.0  # unchanged, not recomputed to 1000
    assert decision.pnl_updated_at is not None
    snap.close()


# ---------------------------------------------------------------------------
# check-pnl-status: trading_mode == "paper" now filters environment == "paper"
# ---------------------------------------------------------------------------

def test_check_pnl_status_paper_filters_new_environment(db_session):
    """Regression guard for the repointed semantics: with trading_mode="paper",
    only decisions with hyperliquid_environment == "paper" (new paper trading)
    are counted -- a legacy hyperliquid_environment IS NULL row (old deprecated
    paper mode) and a mainnet row must both be excluded.

    Calls the real check_pnl_sync_status endpoint function directly (with
    explicit kwargs, bypassing FastAPI's Query/Depends defaults) so this
    actually exercises the production filter instead of a hand-rolled copy
    of it that could drift out of sync."""
    account = _make_account(db_session, "t_status")

    legacy_null_env = AIDecisionLog(
        account_id=account.id, reason="r", operation="buy", symbol="BTC",
        prev_portion=0, target_portion=0.1, total_balance=10000,
        executed="true", hyperliquid_environment=None,
        hyperliquid_order_id="OLD-1", exchange="hyperliquid",
    )
    new_paper_env = AIDecisionLog(
        account_id=account.id, reason="r", operation="buy", symbol="BTC",
        prev_portion=0, target_portion=0.1, total_balance=10000,
        executed="true", hyperliquid_environment="paper",
        hyperliquid_order_id="NEW-1", exchange="hyperliquid",
    )
    mainnet_env = AIDecisionLog(
        account_id=account.id, reason="r", operation="buy", symbol="BTC",
        prev_portion=0, target_portion=0.1, total_balance=10000,
        executed="true", hyperliquid_environment="mainnet",
        hyperliquid_order_id="MAIN-1", exchange="hyperliquid",
    )
    db_session.add_all([legacy_null_env, new_paper_env, mainnet_env])
    db_session.flush()

    result = check_pnl_sync_status(trading_mode="paper", db=db_session)

    assert result["ai_unsync_count"] == 1
    assert result["program_unsync_count"] == 0
    assert result["unsync_count"] == 1
    assert result["needs_sync"] is True


# ---------------------------------------------------------------------------
# update_pnl_data: a paper-backfill failure must not poison db/snapshot_db
# for the rest of the request (real Hyperliquid/Binance sync runs right after).
# ---------------------------------------------------------------------------

def test_paper_backfill_failure_rolls_back_and_does_not_abort_rest_of_sync(
    db_session, snapshot_session_factory, monkeypatch
):
    """Forces _backfill_paper_pnl to raise mid-work via a *genuine* DB error
    (an IntegrityError from a real ORM flush -- not a bare `raise`), so that on
    SQLite (same as Postgres, since SQLAlchemy 1.4+/2.0 tracks this at the
    Session level, not just the wire protocol) a missing rollback leaves the
    session's transaction in a "must rollback" state: the very next query
    raises PendingRollbackError instead of running.

    Calls the real update_pnl_data function directly (bypassing FastAPI's
    Depends wiring via an explicit db= kwarg). HyperliquidWallet/BinanceWallet
    tables are added to db_session's in-memory engine (conftest's db_session
    fixture doesn't create them) purely so the endpoint's wallet queries --
    which run immediately after the paper backfill -- have a table to query
    against; both stay empty so no wallet/fill processing actually happens.

    Honesty check: without the fix (removing the two rollback() calls from
    update_pnl_data's except block), db.query(HyperliquidWallet) below would
    raise PendingRollbackError, which the endpoint's outer except would catch,
    flipping result["success"] to False and adding a *second* unrelated error
    -- so this test would fail on the pre-fix code.
    """
    engine = db_session.get_bind()
    Base.metadata.create_all(
        engine, tables=[HyperliquidWallet.__table__, BinanceWallet.__table__]
    )

    _make_account(db_session, "dup_me")  # existing username to collide with
    db_session.commit()  # durable baseline row -- must survive the rollback below

    def _boom(db, snapshot_db):
        db.add(User(username="dup_me"))  # real UNIQUE-constraint violation
        db.flush()  # -> IntegrityError, poisoning db's transaction on flush
        return {"backfilled": 0}

    monkeypatch.setattr(arena_routes, "_backfill_paper_pnl", _boom)
    monkeypatch.setattr(arena_routes, "SnapshotSessionLocal", snapshot_session_factory)

    result = arena_routes.update_pnl_data(db=db_session)

    assert len(result["errors"]) == 1
    assert "paper backfill" in result["errors"][0]
    # If db.rollback() were missing, the query below (inside update_pnl_data,
    # right after the paper backfill) would raise PendingRollbackError,
    # which the outer except would catch and flip this to False.
    assert result["success"] is True

    # The session must remain directly usable by the caller afterward too.
    assert db_session.query(User).filter(User.username == "dup_me").count() == 1
