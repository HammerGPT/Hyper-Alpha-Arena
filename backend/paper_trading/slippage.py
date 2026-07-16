"""Orderbook-walk fill pricing with fixed-percent fallback (mainnet public APIs)."""
import logging
from typing import Dict, List, Optional, Tuple

import requests

from paper_trading.fees import DEFAULT_SLIPPAGE_FALLBACK_PCT  # noqa: F401 (re-export)

logger = logging.getLogger(__name__)

HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"
BINANCE_DEPTH_URL = "https://fapi.binance.com/fapi/v1/depth"


def fetch_orderbook(data_exchange: str, symbol: str, depth: int = 50) -> Optional[Dict[str, list]]:
    """Fetch mainnet L2 orderbook. Returns {"bids": [(px, sz)...], "asks": [(px, sz)...]} or None."""
    try:
        if data_exchange == "binance":
            from services.exchanges.symbol_mapper import SymbolMapper
            exchange_symbol = SymbolMapper.to_exchange(symbol, "binance")
            resp = requests.get(
                BINANCE_DEPTH_URL,
                params={"symbol": exchange_symbol, "limit": min(depth, 100)},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            bids = [(float(px), float(sz)) for px, sz in data.get("bids", [])]
            asks = [(float(px), float(sz)) for px, sz in data.get("asks", [])]
        else:
            from services.exchanges.symbol_mapper import SymbolMapper
            coin = SymbolMapper.to_exchange(symbol, "hyperliquid")
            resp = requests.post(
                HYPERLIQUID_INFO_URL,
                json={"type": "l2Book", "coin": coin},
                timeout=10,
            )
            resp.raise_for_status()
            levels = resp.json().get("levels", [[], []])
            bids = [(float(l["px"]), float(l["sz"])) for l in levels[0]]
            asks = [(float(l["px"]), float(l["sz"])) for l in levels[1]]
        if not bids and not asks:
            return None
        return {"bids": bids, "asks": asks}
    except Exception as e:
        logger.warning(f"[PAPER] Orderbook fetch failed for {symbol} ({data_exchange}): {e}")
        return None


def walk_the_book(
    levels: List[Tuple[float, float]], size: float, fallback_pct: float, side: str
) -> Optional[float]:
    """Weighted-average fill price walking price levels; leftover priced at worst level +/- fallback.

    `side` is "buy" (leftover priced at worst_px * (1 + fallback_pct/100)) or
    "sell" (worst_px * (1 - fallback_pct/100)).
    """
    if not levels or size <= 0:
        return None
    remaining = size
    cost = 0.0
    worst_px = levels[0][0]
    for px, sz in levels:
        take = min(remaining, sz)
        cost += take * px
        remaining -= take
        worst_px = px
        if remaining <= 1e-12:
            break
    if remaining > 1e-12:
        adj = 1 + fallback_pct / 100 if side == "buy" else 1 - fallback_pct / 100
        cost += remaining * worst_px * adj
    return cost / size


def compute_fill_price(
    data_exchange: str, symbol: str, side: str, size: float,
    reference_price: float, fallback_pct: float,
) -> Tuple[float, str]:
    """Fill price via book walk; falls back to reference_price +/- fallback_pct."""
    book = fetch_orderbook(data_exchange, symbol)
    if book:
        levels = book["asks"] if side == "buy" else book["bids"]
        avg = walk_the_book(levels, size, fallback_pct, side)
        if avg is not None:
            return avg, "orderbook"
    if side == "buy":
        return reference_price * (1 + fallback_pct / 100), "fallback"
    return reference_price * (1 - fallback_pct / 100), "fallback"
