"""PaperEngine: close, reverse-netting, pending order triggers, cancel."""
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


def _open_long(engine, paper, size=0.1, price=100000.0, leverage=2, **kw):
    return engine.place_order(paper, "BTC", True, size, price, price, leverage=leverage, **kw)


def test_reduce_only_close_realizes_pnl(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper)
    # close at 110000: pnl = (110000-100000)*0.1 = 1000
    result = engine.place_order(paper, "BTC", False, 0.1, 110000.0, 110000.0, reduce_only=True)
    assert result["status"] == "filled"
    assert result["realized_pnl"] == pytest.approx(1000.0)
    assert engine.positions(paper) == []
    state = engine.compute_state(paper, {})
    # fees: open 4.5 + close 0.1*110000*0.045% = 4.95
    assert state["total_equity"] == pytest.approx(10000 + 1000 - 4.5 - 4.95)


def test_partial_close(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper, size=0.2)
    result = engine.place_order(paper, "BTC", False, 0.1, 110000.0, 110000.0, reduce_only=True)
    assert result["realized_pnl"] == pytest.approx(1000.0)
    pos = engine.positions(paper)[0]
    assert float(pos.size) == pytest.approx(0.1)


def test_reverse_position_nets_then_opens(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper, size=0.1)
    # sell 0.3 at 110000: closes 0.1 long (pnl 1000), opens 0.2 short.
    # leverage=3 here: after netting, available ~= 10990.55 (10000 + 1000
    # realized - 9.45 accumulated fees); the 0.2 open leg needs
    # 0.2*110000/3 ~= 7333.33 margin, which fits (at leverage=2 it would need
    # 11000, ~9.45 short of available -- infeasible under strict margin).
    result = engine.place_order(paper, "BTC", False, 0.3, 110000.0, 110000.0, leverage=3)
    assert result["status"] == "filled"
    assert result["realized_pnl"] == pytest.approx(1000.0)
    pos = engine.positions(paper)[0]
    assert pos.side == "short"
    assert float(pos.size) == pytest.approx(0.2)
    assert float(pos.entry_price) == pytest.approx(110000.0)


def test_oversized_reversal_open_leg_skipped(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    # tiny long, then a reversal far beyond any margin: close fills, open leg must be skipped
    engine.place_order(paper, "BTC", True, 0.001, 50000.0, 50000.0, leverage=1)
    result = engine.place_order(paper, "BTC", False, 100.001, 50000.0, 50000.0, leverage=50)
    assert result["status"] == "filled"
    assert result["filled_amount"] == pytest.approx(0.001)  # only the netting close
    assert engine.positions(paper) == []  # no short was opened
    state = engine.compute_state(paper, {})
    assert state["used_margin"] == 0


def test_gtc_resting_then_trigger(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    # buy limit 90000 while market at 100000 -> resting
    result = engine.place_order(
        paper, "BTC", True, 0.1, 90000.0, 100000.0, leverage=2, time_in_force="Gtc",
    )
    assert result["status"] == "resting"
    order = engine.pending_orders(paper)[0]
    # price hasn't crossed: no trigger
    assert engine.trigger_order(paper, order, 95000.0) is None
    # price crossed: fills at limit price with maker fee (0.1*90000*0.015% = 1.35)
    fill = engine.trigger_order(paper, order, 89999.0)
    assert fill is not None
    assert fill["price"] == pytest.approx(90000.0)
    assert fill["fee"] == pytest.approx(1.35)
    assert order.status == "filled"
    assert engine.positions(paper)[0].side == "long"


def test_tp_trigger_limit_exec(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper, take_profit_price=110000.0)
    tp = next(o for o in engine.pending_orders(paper) if o.order_type == "take_profit")
    assert engine.trigger_order(paper, tp, 109000.0) is None
    fill = engine.trigger_order(paper, tp, 110500.0)
    assert fill["exit_reason"] == "tp"
    assert fill["price"] == pytest.approx(110000.0)  # limit exec at trigger
    assert fill["realized_pnl"] == pytest.approx(1000.0)
    assert engine.positions(paper) == []


def test_sl_trigger_market_exec_with_slippage(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper, stop_loss_price=95000.0, sl_execution="market")
    sl = next(o for o in engine.pending_orders(paper) if o.order_type == "stop_loss")
    fill = engine.trigger_order(paper, sl, 94900.0)
    assert fill["exit_reason"] == "sl"
    # market exec: trigger price minus fallback slippage (sell side)
    assert fill["price"] == pytest.approx(95000.0 * (1 - 0.05 / 100))
    assert engine.positions(paper) == []


def test_orphan_tpsl_cancelled_when_no_position(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper, take_profit_price=110000.0)
    engine.place_order(paper, "BTC", False, 0.1, 100000.0, 100000.0, reduce_only=True)
    tp = next(o for o in engine.pending_orders(paper) if o.order_type == "take_profit")
    assert engine.trigger_order(paper, tp, 111000.0) is None
    assert tp.status == "cancelled"


def test_cancel_order(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper, take_profit_price=110000.0)
    tp = engine.pending_orders(paper)[0]
    assert engine.cancel_order(paper, tp.order_no) is True
    assert engine.pending_orders(paper) == []
    assert engine.cancel_order(paper, "P-nonexistent") is False


def test_positions_client_format(engine):
    paper = engine.get_or_create(1, "hyperliquid")
    _open_long(engine, paper)
    out = engine.positions_as_client_format(paper, {"BTC": 105000.0})
    assert out[0]["coin"] == "BTC"
    assert out[0]["szi"] == pytest.approx(0.1)
    assert out[0]["entry_px"] == pytest.approx(100000.0)
    assert out[0]["unrealized_pnl"] == pytest.approx(500.0)
    assert out[0]["leverage"] == 2
    assert out[0]["side"] == "Long"
