"""PaperMonitor: trigger sweep and decision PnL backfill."""
import pytest


@pytest.fixture()
def engine(db_session, snapshot_session_factory, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(
        engine_mod.slip_mod, "compute_fill_price",
        lambda ex, sym, side, size, ref, fb: (ref, "orderbook"),
    )
    from paper_trading.engine import PaperEngine
    return PaperEngine(db_session, snapshot_session_factory=snapshot_session_factory)


def test_backfill_decision_pnl_matches_tp_order(db_session, engine):
    from database.models import User, Account, AIDecisionLog
    from paper_trading.monitor import PaperMonitor

    u = User(username="t2")
    db_session.add(u)
    db_session.flush()
    account = Account(user_id=u.id, name="T", model="m", api_key="k")
    db_session.add(account)
    db_session.flush()
    log = AIDecisionLog(
        account_id=account.id, reason="r", operation="buy", symbol="BTC",
        prev_portion=0, target_portion=0.1, total_balance=10000,
        executed="true", hyperliquid_environment="paper",
        tp_order_id="P-tp1", exchange="hyperliquid",
    )
    db_session.add(log)
    db_session.flush()

    monitor = PaperMonitor()
    monitor._backfill_decision_pnl(db_session, {
        "order_no": "P-tp1", "symbol": "BTC", "qty": 0.1, "price": 110000.0,
        "fee": 1.65, "realized_pnl": 1000.0, "exit_reason": "tp",
    })
    db_session.flush()
    assert float(log.realized_pnl) == pytest.approx(1000.0)
    assert log.pnl_updated_at is not None


def test_sweep_account_triggers_tp(db_session, engine, monkeypatch):
    from paper_trading.monitor import PaperMonitor
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(
        paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2,
        take_profit_price=110000.0,
    )
    monitor = PaperMonitor()
    fills = monitor._sweep_account(db_session, engine, paper, {"BTC": 111000.0})
    assert len(fills) == 1
    assert fills[0]["exit_reason"] == "tp"
    assert engine.positions(paper) == []


def test_run_once_commits_last_monitor_at_for_idle_account(db_session, engine, monkeypatch):
    from paper_trading.monitor import PaperMonitor
    paper = engine.get_or_create(1, "hyperliquid")
    db_session.commit()
    monitor = PaperMonitor()
    monitor.run_once(db_session)
    # idle account (no positions/orders): watermark persisted through commit
    db_session.expire_all()
    from database.models import PaperAccount
    fresh = db_session.query(PaperAccount).filter(PaperAccount.account_id == 1).one()
    assert fresh.last_monitor_at is not None


def test_pending_orders_deterministic_order(db_session, engine):
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(
        paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2,
        take_profit_price=110000.0, stop_loss_price=95000.0,
    )
    orders = engine.pending_orders(paper)
    ids = [o.id for o in orders]
    assert ids == sorted(ids)
