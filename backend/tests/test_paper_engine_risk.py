"""PaperEngine: liquidation, funding settlement, cycle reset."""
from datetime import datetime, timedelta

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


def test_no_liquidation_when_healthy(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2)
    assert engine.check_liquidation(paper, {"BTC": 99000.0}) is None


def test_liquidation_closes_all_and_cancels_orders(engine, snapshot_session_factory):
    paper = engine.get_or_create(1, "hyperliquid")
    # 10x leverage: margin 5000, position 0.5 BTC @ 100000
    engine.place_order(
        paper, "BTC", True, 0.5, 100000.0, 100000.0, leverage=10,
        stop_loss_price=80000.0,
    )
    # equity at 85000: 10000 - 0.5*15000 - fees < maintenance (5000*0.5=2500)
    result = engine.check_liquidation(paper, {"BTC": 85000.0})
    assert result is not None
    assert len(result["closed"]) == 1
    assert result["closed"][0]["symbol"] == "BTC"
    assert engine.positions(paper) == []
    assert engine.pending_orders(paper) == []
    # realized loss applied
    state = engine.compute_state(paper, {})
    assert state["total_equity"] < 3000

    # spec §5: liquidation fills must be annotated order_status="liquidation"
    # (distinguishable from ordinary "filled" open/close rows in the snapshot DB)
    from database.snapshot_models import HyperliquidTrade
    sdb = snapshot_session_factory()
    trades = sdb.query(HyperliquidTrade).all()
    sdb.close()
    open_fill = [t for t in trades if t.side == "buy"]
    liquidation_fill = [t for t in trades if t.side == "sell"]
    assert len(open_fill) == 1 and open_fill[0].order_status == "filled"
    assert len(liquidation_fill) == 1 and liquidation_fill[0].order_status == "liquidation"


def test_funding_not_due(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2)
    paper.last_funding_at = datetime.utcnow() - timedelta(minutes=30)
    assert engine.apply_funding(paper, {"BTC": 100000.0}) == 0.0


def test_funding_settlement_long_pays(engine, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(engine_mod.fee_mod, "fetch_funding_rate", lambda ex, sym: 0.0001)
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2)
    paper.last_funding_at = datetime.utcnow() - timedelta(hours=2)
    amount = engine.apply_funding(paper, {"BTC": 100000.0})
    # long pays positive rate: -0.0001 * 10000 = -1.0
    assert amount == pytest.approx(-1.0)
    assert float(paper.total_funding) == pytest.approx(-1.0)

    from database.models import PaperFundingRecord
    records = engine.db.query(PaperFundingRecord).all()
    assert len(records) == 1
    assert float(records[0].amount) == pytest.approx(-1.0)


def test_funding_settlement_short_receives(engine, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(engine_mod.fee_mod, "fetch_funding_rate", lambda ex, sym: 0.0001)
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(paper, "BTC", False, 0.1, 100000.0, 100000.0, leverage=2)
    paper.last_funding_at = datetime.utcnow() - timedelta(hours=2)
    amount = engine.apply_funding(paper, {"BTC": 100000.0})
    assert amount == pytest.approx(1.0)


def test_reset_cycle(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(
        paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2,
        take_profit_price=110000.0,
    )
    engine.reset_cycle(paper, initial_capital=20000.0)
    assert engine.positions(paper) == []
    assert engine.pending_orders(paper) == []
    assert paper.cycle == 2
    assert float(paper.initial_capital) == 20000.0
    assert float(paper.realized_pnl_total) == 0
    assert float(paper.total_fees) == 0
    assert float(paper.total_funding) == 0
    state = engine.compute_state(paper, {})
    assert state["total_equity"] == 20000.0
