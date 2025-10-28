"""
Price caching service to reduce API calls and provide short-term history.
"""

import time
from typing import Deque, Dict, List, Optional, Tuple
import logging
from threading import Lock
from collections import deque

logger = logging.getLogger(__name__)


class PriceCache:
    """In-memory price cache with TTL and rolling history retention."""

    def __init__(self, ttl_seconds: int = 30, history_seconds: int = 3600):
        # key: (symbol, market), value: (price, timestamp)
        self.cache: Dict[Tuple[str, str], Tuple[float, float]] = {}
        # key: (symbol, market), deque of (timestamp, price)
        self.history: Dict[Tuple[str, str], Deque[Tuple[float, float]]] = {}
        self.ttl_seconds = ttl_seconds
        self.history_seconds = history_seconds
        self.lock = Lock()

    def get(self, symbol: str, market: str) -> Optional[float]:
        """Get cached price if still within TTL."""
        key = (symbol, market)
        current_time = time.time()

        with self.lock:
            entry = self.cache.get(key)
            if not entry:
                return None

            price, timestamp = entry
            if current_time - timestamp < self.ttl_seconds:
                logger.debug("Cache hit for %s.%s: %s", symbol, market, price)
                return price

            # TTL expired – purge entry
            del self.cache[key]
            logger.debug("Cache expired for %s.%s", symbol, market)
            return None

    def record(self, symbol: str, market: str, price: float, timestamp: Optional[float] = None) -> None:
        """Record price into short cache and long-term history."""
        key = (symbol, market)
        event_time = timestamp or time.time()

        with self.lock:
            self.cache[key] = (price, event_time)

            history_queue = self.history.setdefault(key, deque())
            history_queue.append((event_time, price))

            cutoff = event_time - self.history_seconds
            while history_queue and history_queue[0][0] < cutoff:
                history_queue.popleft()

        logger.debug("Recorded price update for %s.%s: %s @ %s", symbol, market, price, event_time)

    def clear_expired(self) -> None:
        """Remove expired cache entries and prune history."""
        current_time = time.time()
        cutoff = current_time - self.history_seconds

        with self.lock:
            expired_keys = [
                key for key, (_, ts) in self.cache.items() if current_time - ts >= self.ttl_seconds
            ]
            for key in expired_keys:
                self.cache.pop(key, None)
                self.history.pop(key, None)

            for key, queue in list(self.history.items()):
                while queue and queue[0][0] < cutoff:
                    queue.popleft()
                if not queue:
                    self.history.pop(key, None)

        if expired_keys:
            logger.debug("Cleared %d expired cache entries", len(expired_keys))

    def get_cache_stats(self) -> Dict:
        """Get short-term cache and history stats."""
        current_time = time.time()

        with self.lock:
            valid_entries = sum(
                1 for _, ts in self.cache.values() if current_time - ts < self.ttl_seconds
            )
            history_entries = sum(len(q) for q in self.history.values())
            total_entries = len(self.cache)

        return {
            "total_entries": total_entries,
            "valid_entries": valid_entries,
            "ttl_seconds": self.ttl_seconds,
            "history_entries": history_entries,
            "history_seconds": self.history_seconds,
        }

    def get_history(self, symbol: str, market: str) -> List[Tuple[float, float]]:
        """Return rolling history for symbol within retention window."""
        key = (symbol, market)
        with self.lock:
            queue = self.history.get(key)
            if not queue:
                return []
            return list(queue)


# Global price cache instance
price_cache = PriceCache(ttl_seconds=30, history_seconds=3600)


def get_cached_price(symbol: str, market: str = "CRYPTO") -> Optional[float]:
    """Get price from cache if available."""
    return price_cache.get(symbol, market)


def cache_price(symbol: str, market: str, price: float) -> None:
    """Legacy API – record price with current timestamp."""
    price_cache.record(symbol, market, price)


def record_price_update(symbol: str, market: str, price: float, timestamp: Optional[float] = None) -> None:
    """Explicitly record price update with optional timestamp."""
    price_cache.record(symbol, market, price, timestamp)


def get_price_history(symbol: str, market: str = "CRYPTO") -> List[Tuple[float, float]]:
    """Return recent price history (timestamp, price)."""
    return price_cache.get_history(symbol, market)


def clear_expired_prices() -> None:
    """Clear expired price entries."""
    price_cache.clear_expired()


def get_price_cache_stats() -> Dict:
    """Get cache statistics for diagnostics."""
    return price_cache.get_cache_stats()
