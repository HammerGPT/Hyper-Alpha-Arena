"""Paper trading API routes (logic-level, using route handler functions directly)."""
import pytest


def test_get_state_unconfigured(db_session):
    from api.paper_trading_routes import build_state
    state = build_state(db_session, account_id=42, create=False)
    assert state == {"configured": False, "account_id": 42}


def test_get_state_and_reset(db_session, snapshot_session_factory, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(
        engine_mod.slip_mod, "compute_fill_price",
        lambda ex, sym, side, size, ref, fb: (ref, "orderbook"),
    )
    from api import paper_trading_routes as routes
    monkeypatch.setattr(routes, "_prices_for", lambda db, paper, engine: {"BTC": 100000.0})

    from paper_trading.engine import PaperEngine
    engine = PaperEngine(db_session, snapshot_session_factory=snapshot_session_factory)
    paper = engine.get_or_create(7, "hyperliquid")
    engine.place_order(paper, "BTC", True, 0.1, 100000.0, 100000.0, leverage=2)

    state = routes.build_state(db_session, account_id=7, create=False)
    assert state["configured"] is True
    assert state["cycle"] == 1
    assert len(state["positions"]) == 1
    assert state["total_equity"] == pytest.approx(10000 - 4.5)

    result = routes.do_reset(db_session, account_id=7, initial_capital=15000.0)
    assert result["cycle"] == 2
    assert result["total_equity"] == 15000.0
    assert result["positions"] == []
