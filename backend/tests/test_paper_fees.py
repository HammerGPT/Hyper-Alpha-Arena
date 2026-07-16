"""Fee schedule and funding rate tests."""


def test_default_fee_rates():
    from paper_trading.fees import get_fee_rates
    hl = get_fee_rates("hyperliquid")
    assert hl == {"taker": 0.045, "maker": 0.015}
    bn = get_fee_rates("binance")
    assert bn == {"taker": 0.05, "maker": 0.02}


def test_fee_rates_account_override(db_session, paper_account):
    from paper_trading.fees import get_fee_rates
    paper_account.taker_fee_pct = 0.03
    rates = get_fee_rates("hyperliquid", paper_account)
    assert rates["taker"] == 0.03
    assert rates["maker"] == 0.015  # not overridden


def test_calc_fee():
    from paper_trading.fees import calc_fee
    assert calc_fee(10000.0, 0.045) == 4.5
    assert calc_fee(-10000.0, 0.045) == 4.5  # absolute notional


def test_fetch_funding_rate_hyperliquid(monkeypatch):
    from paper_trading import fees
    monkeypatch.setattr(
        fees, "_hyperliquid_ticker",
        lambda symbol: {"price": 100.0, "funding_rate": 0.0000125},
    )
    assert fees.fetch_funding_rate("hyperliquid", "BTC") == 0.0000125


def test_fetch_funding_rate_failure_returns_none(monkeypatch):
    from paper_trading import fees
    def boom(symbol):
        raise RuntimeError("network down")
    monkeypatch.setattr(fees, "_hyperliquid_ticker", boom)
    assert fees.fetch_funding_rate("hyperliquid", "BTC") is None
