"""
In-memory cache for Hyperliquid account state and positions.

This cache is used to serve UI/analytics requests without repeatedly
calling Hyperliquid APIs. AI decision logic MUST continue to fetch
real-time data; after each successful fetch we update the cache.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, TypedDict


class _CacheEntry(TypedDict):
    data: Any
    timestamp: float


_ACCOUNT_STATE_CACHE: Dict[int, _CacheEntry] = {}
_POSITIONS_CACHE: Dict[int, _CacheEntry] = {}
_cache_lock = threading.Lock()


def _now() -> float:
    return time.time()


def update_account_state_cache(account_id: int, state: Dict[str, Any]) -> None:
    """Store latest Hyperliquid account state for account_id."""
    with _cache_lock:
        _ACCOUNT_STATE_CACHE[account_id] = {"data": state, "timestamp": _now()}


def update_positions_cache(account_id: int, positions: List[Dict[str, Any]]) -> None:
    """Store latest Hyperliquid positions for account_id."""
    with _cache_lock:
        _POSITIONS_CACHE[account_id] = {"data": positions, "timestamp": _now()}


def get_cached_account_state(
    account_id: int,
    max_age_seconds: Optional[int] = None,
) -> Optional[_CacheEntry]:
    """Return cached account state if present and within optional TTL."""
    with _cache_lock:
        entry = _ACCOUNT_STATE_CACHE.get(account_id)
        if not entry:
            return None
        if max_age_seconds is not None and _now() - entry["timestamp"] > max_age_seconds:
            return None
        return entry


def get_cached_positions(
    account_id: int,
    max_age_seconds: Optional[int] = None,
) -> Optional[_CacheEntry]:
    """Return cached positions if present and within optional TTL."""
    with _cache_lock:
        entry = _POSITIONS_CACHE.get(account_id)
        if not entry:
            return None
        if max_age_seconds is not None and _now() - entry["timestamp"] > max_age_seconds:
            return None
        return entry


def clear_account_cache(account_id: Optional[int] = None) -> None:
    """Clear cached entries (single account or all)."""
    with _cache_lock:
        if account_id is None:
            _ACCOUNT_STATE_CACHE.clear()
            _POSITIONS_CACHE.clear()
        else:
            _ACCOUNT_STATE_CACHE.pop(account_id, None)
            _POSITIONS_CACHE.pop(account_id, None)


def get_cache_stats() -> Dict[str, Any]:
    """Return basic cache diagnostics."""
    with _cache_lock:
        return {
            "accounts_cached": len(_ACCOUNT_STATE_CACHE),
            "positions_cached": len(_POSITIONS_CACHE),
        }
