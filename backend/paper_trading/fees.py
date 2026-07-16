"""Fee schedule and funding rates for paper trading (mainnet public data)."""
import logging
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

# Percent rates (0.045 = 0.045%)
DEFAULT_FEES: Dict[str, Dict[str, float]] = {
    "hyperliquid": {"taker": 0.045, "maker": 0.015},
    "binance": {"taker": 0.05, "maker": 0.02},
}

FUNDING_INTERVAL_HOURS: Dict[str, int] = {"hyperliquid": 1, "binance": 8}

DEFAULT_SLIPPAGE_FALLBACK_PCT = 0.05


def get_fee_rates(data_exchange: str, paper_account=None) -> Dict[str, float]:
    rates = dict(DEFAULT_FEES.get(data_exchange, DEFAULT_FEES["hyperliquid"]))
    if paper_account is not None:
        if paper_account.taker_fee_pct is not None:
            rates["taker"] = float(paper_account.taker_fee_pct)
        if paper_account.maker_fee_pct is not None:
            rates["maker"] = float(paper_account.maker_fee_pct)
    return rates


def calc_fee(notional: float, rate_pct: float) -> float:
    return abs(notional) * rate_pct / 100.0


def _hyperliquid_ticker(symbol: str) -> Optional[dict]:
    from services.hyperliquid_market_data import get_ticker_data_from_hyperliquid
    return get_ticker_data_from_hyperliquid(symbol, environment="mainnet")


def _binance_funding(symbol: str) -> Optional[float]:
    from services.exchanges.symbol_mapper import SymbolMapper
    exchange_symbol = SymbolMapper.to_exchange(symbol, "binance")
    resp = requests.get(
        "https://fapi.binance.com/fapi/v1/premiumIndex",
        params={"symbol": exchange_symbol},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return float(data["lastFundingRate"])


def fetch_funding_rate(data_exchange: str, symbol: str) -> Optional[float]:
    """Current funding rate as a decimal (e.g. 0.0000125). None on failure."""
    try:
        if data_exchange == "binance":
            return _binance_funding(symbol)
        ticker = _hyperliquid_ticker(symbol)
        if ticker and ticker.get("funding_rate") is not None:
            return float(ticker["funding_rate"])
        return None
    except Exception as e:
        logger.warning(f"[PAPER] Failed to fetch funding rate for {symbol} ({data_exchange}): {e}")
        return None
