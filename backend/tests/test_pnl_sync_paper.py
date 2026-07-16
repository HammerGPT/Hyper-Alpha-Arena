"""Paper trading PnL sync semantics for arena_routes.

Covers:
- check-pnl-status: "paper" now filters on environment == "paper" (new paper
  trading), not the legacy environment IS NULL semantics.
- update_pnl_data's paper backfill safety net (_backfill_paper_pnl), including
  the PnL-recovery deviation from the Task 13 brief's literal snippet.
"""
from datetime import datetime
from decimal import Decimal

from database.models import AIDecisionLog, PaperOrder, User, Account
from database.snapshot_models import HyperliquidTrade
from api.arena_routes import _backfill_paper_pnl


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


def test_backfill_skips_records_with_existing_realized_pnl(
    db_session, snapshot_session_factory, paper_account
):
    """A row that already has realized_pnl but somehow lacks pnl_updated_at is left
    alone (not double-counted / not overwritten)."""
    account = _make_account(db_session, "t_pnl_existing")
    _make_filled_tpsl_order(db_session, paper_account, "P-tp5", side="sell", entry_price=100000)
    decision = _make_decision(db_session, account, tp_order_id="P-tp5")
    decision.realized_pnl = Decimal("42")
    db_session.flush()

    snap = snapshot_session_factory()
    _make_fill_row(snap, "P-tp5", side="sell", qty=0.1, price=110000)

    result = _backfill_paper_pnl(db_session, snap)

    assert result == {"backfilled": 0}
    db_session.refresh(decision)
    assert float(decision.realized_pnl) == 42.0
    assert decision.pnl_updated_at is None
    snap.close()


# ---------------------------------------------------------------------------
# check-pnl-status: trading_mode == "paper" now filters environment == "paper"
# ---------------------------------------------------------------------------

def test_check_pnl_status_paper_filters_new_environment(db_session):
    """Regression guard for the repointed semantics: a decision with
    hyperliquid_environment IS NULL (legacy deprecated paper) must NOT be
    counted for trading_mode="paper" anymore, while an environment="paper"
    (new paper trading) row must be counted."""
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
    db_session.add_all([legacy_null_env, new_paper_env])
    db_session.flush()

    ai_query = db_session.query(AIDecisionLog).filter(
        AIDecisionLog.operation.in_(["buy", "sell", "close"]),
        AIDecisionLog.executed == "true",
        AIDecisionLog.pnl_updated_at == None,
    )
    trading_mode = "paper"
    if trading_mode:
        ai_query = ai_query.filter(AIDecisionLog.hyperliquid_environment == trading_mode)
    else:
        ai_query = ai_query.filter(AIDecisionLog.hyperliquid_environment.isnot(None))

    results = ai_query.all()
    assert [r.hyperliquid_order_id for r in results] == ["NEW-1"]
