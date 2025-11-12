"""
In-memory cache for Hyperliquid account state and positions.

This cache is used to serve UI/analytics requests without repeatedly
calling Hyperliquid APIs. AI decision logic MUST continue to fetch
real-time data; after each successful fetch we update the cache.

Cache keys are tuples of (account_id, environment) to support multi-wallet
architecture where one account can have both testnet and mainnet wallets.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple, TypedDict


class _CacheEntry(TypedDict):
    data: Any
    timestamp: float


_ACCOUNT_STATE_CACHE: Dict[Tuple[int, str], _CacheEntry] = {}
_POSITIONS_CACHE: Dict[Tuple[int, str], _CacheEntry] = {}
_cache_lock = threading.Lock()


def _now() -> float:
    return time.time()


def _make_cache_key(account_id: int, environment: str) -> Tuple[int, str]:
    """Create cache key from account_id and environment."""
    return (account_id, environment)


def update_account_state_cache(account_id: int, state: Dict[str, Any], environment: str = "testnet") -> None:
    """Store latest Hyperliquid account state for (account_id, environment)."""
    cache_key = _make_cache_key(account_id, environment)
    with _cache_lock:
        _ACCOUNT_STATE_CACHE[cache_key] = {"data": state, "timestamp": _now()}


def update_positions_cache(account_id: int, positions: List[Dict[str, Any]], environment: str = "testnet") -> None:
    """Store latest Hyperliquid positions for (account_id, environment)."""
    cache_key = _make_cache_key(account_id, environment)
    with _cache_lock:
        _POSITIONS_CACHE[cache_key] = {"data": positions, "timestamp": _now()}


def get_cached_account_state(
    account_id: int,
    environment: str = "testnet",
    max_age_seconds: Optional[int] = None,
) -> Optional[_CacheEntry]:
    """Return cached account state if present and within optional TTL."""
    cache_key = _make_cache_key(account_id, environment)
    with _cache_lock:
        entry = _ACCOUNT_STATE_CACHE.get(cache_key)
        if not entry:
            return None
        if max_age_seconds is not None and _now() - entry["timestamp"] > max_age_seconds:
            return None
        return entry


def get_cached_positions(
    account_id: int,
    environment: str = "testnet",
    max_age_seconds: Optional[int] = None,
) -> Optional[_CacheEntry]:
    """Return cached positions if present and within optional TTL."""
    cache_key = _make_cache_key(account_id, environment)
    with _cache_lock:
        entry = _POSITIONS_CACHE.get(cache_key)
        if not entry:
            return None
        if max_age_seconds is not None and _now() - entry["timestamp"] > max_age_seconds:
            return None
        return entry


def clear_account_cache(account_id: Optional[int] = None, environment: Optional[str] = None) -> None:
    """
    Clear cached entries.

    Args:
        account_id: If None, clear all accounts. If provided with environment, clear specific entry.
        environment: If None with account_id, clear both environments for that account.
    """
    with _cache_lock:
        if account_id is None:
            # Clear all caches
            _ACCOUNT_STATE_CACHE.clear()
            _POSITIONS_CACHE.clear()
        elif environment is None:
            # Clear both testnet and mainnet for this account
            for env in ["testnet", "mainnet"]:
                cache_key = _make_cache_key(account_id, env)
                _ACCOUNT_STATE_CACHE.pop(cache_key, None)
                _POSITIONS_CACHE.pop(cache_key, None)
        else:
            # Clear specific (account_id, environment) entry
            cache_key = _make_cache_key(account_id, environment)
            _ACCOUNT_STATE_CACHE.pop(cache_key, None)
            _POSITIONS_CACHE.pop(cache_key, None)


def clear_all_caches() -> None:
    """Clear all cached entries across all accounts."""
    clear_account_cache(account_id=None)


def get_cache_stats() -> Dict[str, Any]:
    """Return basic cache diagnostics."""
    with _cache_lock:
        return {
            "accounts_cached": len(_ACCOUNT_STATE_CACHE),
            "positions_cached": len(_POSITIONS_CACHE),
        }
