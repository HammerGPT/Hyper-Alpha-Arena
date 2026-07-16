"""PaperTradingClient interface parity tests."""
import pytest


@pytest.fixture()
def client(db_session, snapshot_session_factory, monkeypatch):
    from paper_trading import engine as engine_mod
    monkeypatch.setattr(
        engine_mod.slip_mod, "compute_fill_price",
        lambda ex, sym, side, size, ref, fb: (ref, "orderbook"),
    )
    from paper_trading import client as client_mod
    monkeypatch.setattr(client_mod, "_get_last_price", lambda symbol, exchange: 100000.0)
    from paper_trading.client import PaperTradingClient
    c = PaperTradingClient(account_id=1, data_exchange="hyperliquid")
    monkeypatch.setattr(c, "_session_factory", lambda: db_session)
    c._snapshot_factory = snapshot_session_factory
    return c


def test_client_attributes(client):
    assert client.environment == "paper"
    assert client.wallet_address == "paper-1"


def test_account_state_shape(client, db_session):
    state = client.get_account_state(db_session)
    for key in ("total_equity", "available_balance", "used_margin",
                "maintenance_margin", "margin_usage_percent", "wallet_address"):
        assert key in state
    assert state["total_equity"] == 10000.0


def test_place_order_and_positions(client, db_session):
    result = client.place_order_with_tpsl(
        db=db_session, symbol="BTC", is_buy=True, size=0.1, price=100000.0,
        leverage=2, take_profit_price=110000.0, stop_loss_price=95000.0,
    )
    assert result["status"] == "filled"
    assert result["order_id"].startswith("P-")
    assert result["tp_order_id"].startswith("P-")

    positions = client.get_positions(db_session, include_timing=True)
    assert positions[0]["coin"] == "BTC"
    assert positions[0]["szi"] == pytest.approx(0.1)
    assert "opened_at_str" in positions[0]

    orders = client.get_open_orders(db_session, symbol="BTC")
    assert len(orders) == 2
    assert client.cancel_order(db_session, orders[0]["order_id"], "BTC") is True


def test_place_order_passes_position_marks(client, db_session, monkeypatch):
    # open an ETH position first (mark will be fetched at patched price)
    client.place_order_with_tpsl(db=db_session, symbol="ETH", is_buy=True, size=0.01, price=100000.0, leverage=2)
    captured = {}
    from paper_trading.engine import PaperEngine
    original = PaperEngine.place_order
    def spy(self, paper, symbol, is_buy, size, **kwargs):
        captured.update(kwargs)
        return original(self, paper, symbol, is_buy, size, **kwargs)
    monkeypatch.setattr(PaperEngine, "place_order", spy)
    client.place_order_with_tpsl(db=db_session, symbol="BTC", is_buy=True, size=0.01, price=100000.0, leverage=2)
    assert captured.get("mark_prices") == {"ETH": 100000.0}


def test_close_position(client, db_session):
    client.place_order_with_tpsl(
        db=db_session, symbol="BTC", is_buy=True, size=0.1, price=100000.0,
        leverage=2, take_profit_price=110000.0,
    )
    result = client.close_position("BTC", cancel_tpsl=True, db=db_session)
    assert result is not None
    assert result.get("status") == "filled"
    assert client.get_positions(db_session) == []
    assert client.get_open_orders(db_session) == []


def test_close_position_no_position(client, db_session):
    result = client.close_position("ETH", cancel_tpsl=True, db=db_session)
    assert result is None
