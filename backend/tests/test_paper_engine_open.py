"""PaperEngine: state computation, open, add-to-position, margin rejection."""
import pytest


@pytest.fixture()
def engine(db_session, snapshot_session_factory, monkeypatch):
    from paper_trading import engine as engine_mod
    # deterministic fill: exact reference price, source orderbook
    monkeypatch.setattr(
        engine_mod.slip_mod, "compute_fill_price",
        lambda ex, sym, side, size, ref, fb: (ref, "orderbook"),
    )
    from paper_trading.engine import PaperEngine
    return PaperEngine(db_session, snapshot_session_factory=snapshot_session_factory)


def test_initial_state(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    state = engine.compute_state(paper, {})
    assert state["total_equity"] == 10000.00
    assert state["available_balance"] == 10000.00
    assert state["used_margin"] == 0
    assert state["environment"] == "paper"
    assert state["wallet_address"] == "paper-1"


def test_open_long_position(engine, db_session):
    paper = engine.get_or_create(1, "hyperliquid")
    result = engine.place_order(
        paper, "BTC", is_buy=True, size=0.1, limit_price=100000.0,
        market_price=100000.0, leverage=2,
    )
    assert result["status"] == "filled"
    assert result["average_price"] == 100000.0
    assert result["filled_amount"] == 0.1
    assert result["order_id"].startswith("P-")
    # taker fee: 0.1 * 100000 * 0.045% = 4.5
    assert result["fee"] == pytest.approx(4.5)

    positions = engine.positions(paper)
    assert len(positions) == 1
    assert positions[0].side == "long"
    assert float(positions[0].size) == 0.1
    # margin = 10000 / 2 = 5000
    state = engine.compute_state(paper, {"BTC": 100000.0})
    assert state["used_margin"] == pytest.approx(5000.0)
    assert state["total_equity"] == pytest.approx(10000.0 - 4.5)


def test_add_to_position_weighted_average(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    engine.place_order(paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2)
    engine.place_order(paper, "BTC", True, 0.1, 110000.0, 110000.0, leverage=2)
    pos = engine.positions(paper)[0]
    assert float(pos.size) == pytest.approx(0.2)
    assert float(pos.entry_price) == pytest.approx(105000.0)


def test_margin_rejection(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    # margin needed: 1 BTC * 100000 / 1x = 100000 > 10000 equity
    result = engine.place_order(paper, "BTC", True, 1.0, 100000.0, 100000.0, leverage=1)
    assert result["status"] == "error"
    assert "Insufficient" in result["error"]
    assert engine.positions(paper) == []


def test_tpsl_orders_registered(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    result = engine.place_order(
        paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2,
        take_profit_price=110000.0, stop_loss_price=95000.0, sl_execution="market",
    )
    assert result["tp_order_id"].startswith("P-")
    assert result["sl_order_id"].startswith("P-")
    orders = engine.pending_orders(paper)
    assert len(orders) == 2
    tp = next(o for o in orders if o.order_type == "take_profit")
    sl = next(o for o in orders if o.order_type == "stop_loss")
    assert float(tp.trigger_price) == 110000.0
    assert tp.exec_mode == "limit"
    assert sl.exec_mode == "market"
    assert tp.side == "sell" and sl.side == "sell"
    assert float(tp.entry_price) == 100000.0


def test_fill_recorded_to_snapshot_db(engine, snapshot_session_factory):
    from database.snapshot_models import HyperliquidTrade
    paper = engine.get_or_create(1, "hyperliquid")
    result = engine.place_order(paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2)
    sdb = snapshot_session_factory()
    trades = sdb.query(HyperliquidTrade).all()
    assert len(trades) == 1
    assert trades[0].environment == "paper"
    assert trades[0].order_id == result["order_id"]
    assert float(trades[0].fee) == pytest.approx(4.5)
    sdb.close()
