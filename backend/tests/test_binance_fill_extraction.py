"""Unit tests for _extract_binance_fill (trading_commands.py).

Regression coverage for the bug where _execute_binance_decision's "close"
branch read result.get('filled_qty', 0) against BinanceTradingClient
.close_position's return, which never has a 'filled_qty' key -- so every
real Binance close trade was recorded with quantity=0 in the HyperliquidTrade
snapshot table (corrupting attribution/fees).

Shapes verified directly against binance_trading_client.py:
- BinanceTradingClient.place_order (~line 677-692) returns normalized
  snake_case float fields: 'executed_qty', 'avg_price'. close_position
  (line 1020) returns this same dict (with 'cancelled_algo_orders' added),
  so this -- not a raw camelCase Binance payload -- is what the close
  branch actually receives.
- place_order_with_tpsl (~line 1125-1134, 1154-1155) returns the legacy
  normalized fields 'filled_qty' / 'avg_price' directly.
- PaperTradingClient.close_position (paper_trading/client.py ~207-219)
  returns 'filled_qty' / 'avg_price' / 'fee'.
- Binance never returns a commission/fee field from order placement
  (fees only come from the separate user-trades/income-history endpoints,
  see binance_trading_client.py get_user_fills ~line 1509), so fee is
  expected to be 0.0 for all real-Binance shapes tested here.
"""
from services.trading_commands import _extract_binance_fill


def test_extract_from_real_binance_close_position_shape():
    """Actual BinanceTradingClient.close_position/place_order return shape:
    normalized snake_case keys, float values, no fee key at all."""
    result = {
        "order_id": 123456,
        "client_order_id": "x-broker-1",
        "symbol": "BTC",
        "side": "SELL",
        "type": "MARKET",
        "quantity": 0.01,
        "price": 0.0,
        "avg_price": 50123.4,
        "executed_qty": 0.01,
        "status": "FILLED",
        "time_in_force": "GTC",
        "reduce_only": True,
        "environment": "mainnet",
        "raw_response": {"orderId": 123456, "avgPrice": "50123.40000000", "executedQty": "0.010"},
        "cancelled_algo_orders": {"cancelled_count": 2},
    }
    qty, price, fee = _extract_binance_fill(result)
    assert qty == 0.01
    assert price == 50123.4
    assert fee == 0.0


def test_extract_from_raw_camelcase_binance_payload_with_string_values():
    """Defensive coverage: if a raw (unnormalized) Binance REST payload is
    ever passed through -- camelCase keys, numeric values as strings."""
    result = {
        "orderId": 987654,
        "symbol": "BTCUSDT",
        "status": "FILLED",
        "avgPrice": "50123.40000000",
        "executedQty": "0.01000000",
        "cumQuote": "501.234",
        "origQty": "0.01000000",
    }
    qty, price, fee = _extract_binance_fill(result)
    assert qty == 0.01
    assert price == 50123.4
    assert fee == 0.0


def test_extract_from_legacy_paper_shape_with_filled_qty_and_fee():
    """PaperTradingClient.close_position / place_order_with_tpsl legacy shape."""
    result = {
        "status": "filled",
        "order_id": "P-1",
        "filled_qty": 0.02,
        "avg_price": 3000.5,
        "quantity": 0.02,
        "environment": "paper",
        "realized_pnl": 12.34,
        "fee": 1.25,
        "error": None,
    }
    qty, price, fee = _extract_binance_fill(result)
    assert qty == 0.02
    assert price == 3000.5
    assert fee == 1.25


def test_extract_prefers_commission_key_over_fee_for_fee():
    result = {"executed_qty": 1.0, "avg_price": 100.0, "commission": "0.05", "fee": 999}
    qty, price, fee = _extract_binance_fill(result)
    assert fee == 0.05


def test_extract_defaults_to_zero_when_keys_missing_or_none():
    assert _extract_binance_fill({}) == (0.0, 0.0, 0.0)
    result = {"executed_qty": None, "avg_price": None, "filled_qty": None}
    assert _extract_binance_fill(result) == (0.0, 0.0, 0.0)


def test_extract_ignores_unparseable_values_and_falls_through():
    # If a higher-priority key holds junk, fall through to the next key
    # rather than raising or returning garbage.
    result = {"executedQty": "not-a-number", "executed_qty": "0.03", "avg_price": 200.0}
    qty, price, fee = _extract_binance_fill(result)
    assert qty == 0.03
    assert price == 200.0
