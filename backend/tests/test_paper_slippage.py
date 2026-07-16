"""Orderbook walk and slippage fallback tests."""
import pytest


def test_walk_the_book_single_level():
    from paper_trading.slippage import walk_the_book
    # 10 BTC available at 100, buying 5 -> avg 100
    assert walk_the_book([(100.0, 10.0)], 5.0, 0.05, "buy") == 100.0


def test_walk_the_book_multi_level_weighted_avg():
    from paper_trading.slippage import walk_the_book
    # buy 15: 10 @ 100 + 5 @ 101 -> (1000 + 505) / 15
    avg = walk_the_book([(100.0, 10.0), (101.0, 5.0)], 15.0, 0.05, "buy")
    assert avg == pytest.approx((100.0 * 10 + 101.0 * 5) / 15)


def test_walk_the_book_insufficient_depth():
    from paper_trading.slippage import walk_the_book
    # buy 20, only 10 available at 100: remainder at 100 * (1 + 0.05%)
    avg = walk_the_book([(100.0, 10.0)], 20.0, 0.05, "buy")
    expected = (100.0 * 10 + 100.0 * 1.0005 * 10) / 20
    assert avg == pytest.approx(expected)


def test_walk_the_book_sell_insufficient_depth_prices_down():
    from paper_trading.slippage import walk_the_book
    # sell 20 into a single bid level of 10 @ 100: remainder at 100 * (1 - 0.05%)
    avg = walk_the_book([(100.0, 10.0)], 20.0, 0.05, "sell")
    expected = (100.0 * 10 + 100.0 * 0.9995 * 10) / 20
    assert avg == pytest.approx(expected)


def test_walk_the_book_empty():
    from paper_trading.slippage import walk_the_book
    assert walk_the_book([], 5.0, 0.05, "buy") is None


def test_compute_fill_price_uses_orderbook(monkeypatch):
    from paper_trading import slippage
    monkeypatch.setattr(
        slippage, "fetch_orderbook",
        lambda ex, sym, depth=50: {
            "bids": [(99.0, 100.0)],
            "asks": [(101.0, 100.0)],
        },
    )
    price, source = slippage.compute_fill_price("hyperliquid", "BTC", "buy", 1.0, 100.0, 0.05)
    assert source == "orderbook"
    assert price == 101.0  # buy fills against asks
    price, source = slippage.compute_fill_price("hyperliquid", "BTC", "sell", 1.0, 100.0, 0.05)
    assert price == 99.0  # sell fills against bids


def test_compute_fill_price_fallback(monkeypatch):
    from paper_trading import slippage
    monkeypatch.setattr(slippage, "fetch_orderbook", lambda ex, sym, depth=50: None)
    price, source = slippage.compute_fill_price("hyperliquid", "BTC", "buy", 1.0, 100.0, 0.05)
    assert source == "fallback"
    assert price == pytest.approx(100.0 * 1.0005)
    price, _ = slippage.compute_fill_price("hyperliquid", "BTC", "sell", 1.0, 100.0, 0.05)
    assert price == pytest.approx(100.0 * 0.9995)
