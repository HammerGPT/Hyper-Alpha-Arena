"""End-to-end: paper order -> decision log -> TP trigger -> PnL backfill consistency."""
import pytest


def test_full_paper_trade_lifecycle(db_session, snapshot_session_factory, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(
        engine_mod.slip_mod, "compute_fill_price",
        lambda ex, sym, side, size, ref, fb: (ref, "orderbook"),
    )
    from database.models import User, Account, AIDecisionLog
    from database.snapshot_models import HyperliquidTrade
    from paper_trading.engine import PaperEngine
    from paper_trading.monitor import PaperMonitor

    u = User(username="e2e")
    db_session.add(u)
    db_session.flush()
    account = Account(user_id=u.id, name="E2E", model="m", api_key="k")
    db_session.add(account)
    db_session.flush()

    engine = PaperEngine(db_session, snapshot_session_factory=snapshot_session_factory)
    paper = engine.get_or_create(account.id, "hyperliquid")

    # 1. open with TP (as the AI pipeline would)
    result = engine.place_order(
        paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2,
        take_profit_price=110000.0,
    )
    assert result["status"] == "filled"

    # 2. decision log records paper environment + order ids (as pipeline does)
    log = AIDecisionLog(
        account_id=account.id, reason="e2e", operation="buy", symbol="BTC",
        prev_portion=0, target_portion=0.1, total_balance=10000,
        executed="true", hyperliquid_environment="paper", exchange="hyperliquid",
        hyperliquid_order_id=result["order_id"], tp_order_id=result["tp_order_id"],
    )
    db_session.add(log)
    db_session.flush()

    # 3. monitor sweep triggers TP and backfills PnL
    monitor = PaperMonitor()
    fills = monitor._sweep_account(db_session, engine, paper, {"BTC": 111000.0})
    for f in fills:
        monitor._backfill_decision_pnl(db_session, f)
    db_session.flush()

    assert float(log.realized_pnl) == pytest.approx(1000.0)
    assert log.pnl_updated_at is not None

    # 4. fills in snapshot DB carry environment=paper and fees (attribution source)
    sdb = snapshot_session_factory()
    trades = sdb.query(HyperliquidTrade).all()
    assert all(t.environment == "paper" for t in trades)
    assert len(trades) == 2  # open fill + tp close fill
    total_fee = sum(float(t.fee) for t in trades)
    sdb.close()

    # 5. equity accounting consistent: 10000 + 1000 - fees
    state = engine.compute_state(paper, {})
    assert state["total_equity"] == pytest.approx(10000 + 1000 - total_fee)
