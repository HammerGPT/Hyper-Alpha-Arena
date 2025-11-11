"""
Hyperliquid symbol management utilities.

Handles:
- Fetching tradable symbol metadata from Hyperliquid meta API
- Persisting available symbols + user-selected watchlist in SystemConfig
- Exposing helpers for other services (prompt generation, execution, etc.)
- Keeping market data stream in sync with selected symbols
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import SystemConfig, Account

logger = logging.getLogger(__name__)

AVAILABLE_SYMBOLS_KEY = "hyperliquid_available_symbols"
SELECTED_SYMBOLS_KEY = "hyperliquid_selected_symbols"
MAX_WATCHLIST_SYMBOLS = 10
SYMBOL_REFRESH_TASK_ID = "hyperliquid_symbol_refresh"

DEFAULT_SYMBOLS: List[Dict[str, str]] = [
    {"symbol": "BTC", "name": "Bitcoin"},
    {"symbol": "ETH", "name": "Ethereum"},
    {"symbol": "SOL", "name": "Solana"},
    {"symbol": "DOGE", "name": "Dogecoin"},
]

META_ENDPOINTS = {
    "testnet": "https://api.hyperliquid-testnet.xyz/info",
    "mainnet": "https://api.hyperliquid.xyz/info",
}


def _load_config_value(db: Session, key: str) -> Optional[str]:
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    return config.value if config else None


def _save_config_value(db: Session, key: str, value: str) -> None:
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if not config:
        config = SystemConfig(key=key, value=value)
        db.add(config)
    else:
        config.value = value
    db.commit()


def _parse_symbol_json(value: Optional[str]) -> List[Dict[str, str]]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            result = []
            for entry in parsed:
                if not isinstance(entry, dict):
                    continue
                symbol = str(entry.get("symbol") or "").upper()
                if not symbol:
                    continue
                result.append(
                    {
                        "symbol": symbol,
                        "name": entry.get("name") or symbol,
                        "type": entry.get("type") or entry.get("category"),
                    }
                )
            return result
    except json.JSONDecodeError:
        logger.warning("Failed to decode stored Hyperliquid symbols; falling back to defaults")
    return []


def _serialize_symbols(symbols: List[Dict[str, str]]) -> str:
    sanitized = []
    seen = set()
    for entry in symbols:
        symbol = str(entry.get("symbol") or "").upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        sanitized.append(
            {
                "symbol": symbol,
                "name": entry.get("name") or symbol,
                "type": entry.get("type") or entry.get("category"),
            }
        )
    return json.dumps(sanitized)


def _validate_symbol_tradability(symbol: str) -> bool:
    """
    Test if a symbol can actually fetch price data (i.e., is tradable).

    Uses silent validation method that doesn't log errors for invalid symbols.
    """
    try:
        from services.hyperliquid_market_data import hyperliquid_client
        return hyperliquid_client.check_symbol_tradability(symbol)
    except Exception:
        return False


def fetch_remote_symbols(environment: str = "testnet") -> List[Dict[str, str]]:
    """Call Hyperliquid meta endpoint to retrieve tradable universe."""
    url = META_ENDPOINTS.get(environment, META_ENDPOINTS["testnet"])
    try:
        resp = requests.post(url, json={"type": "meta"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        universe = data.get("universe") or data.get("universeSpot") or []
    except Exception as err:
        logger.warning("Failed to fetch Hyperliquid meta info: %s", err)
        return []

    results: List[Dict[str, str]] = []
    seen = set()
    invalid_count = 0

    for entry in universe:
        if not isinstance(entry, dict):
            continue
        raw_symbol = entry.get("name") or entry.get("symbol")
        if not raw_symbol:
            continue
        symbol = str(raw_symbol).upper()
        if symbol in seen:
            continue
        seen.add(symbol)

        # Validate symbol is actually tradable
        if not _validate_symbol_tradability(symbol):
            logger.debug(f"Skipping symbol {symbol} (not tradable on Hyperliquid)")
            invalid_count += 1
            continue

        results.append(
            {
                "symbol": symbol,
                "name": entry.get("displayName") or entry.get("name") or symbol,
                "type": entry.get("type") or entry.get("szType") or entry.get("assetType"),
            }
        )

    if invalid_count > 0:
        logger.info(f"Filtered out {invalid_count} delisted/non-tradable symbols during Hyperliquid symbol refresh")

    return results


def refresh_hyperliquid_symbols(environment: str = "testnet") -> List[Dict[str, str]]:
    """Refresh available symbol list from Hyperliquid."""
    remote_symbols = fetch_remote_symbols(environment)
    if not remote_symbols:
        logger.warning("No symbols fetched from Hyperliquid meta; keeping existing list")

    with SessionLocal() as db:
        if remote_symbols:
            _save_config_value(db, AVAILABLE_SYMBOLS_KEY, _serialize_symbols(remote_symbols))
            _ensure_watchlist_valid(db, remote_symbols)
            logger.info("Hyperliquid symbol catalog refreshed (%d symbols)", len(remote_symbols))
        else:
            stored = _parse_symbol_json(_load_config_value(db, AVAILABLE_SYMBOLS_KEY))
            if not stored:
                _save_config_value(db, AVAILABLE_SYMBOLS_KEY, _serialize_symbols(DEFAULT_SYMBOLS))
                _ensure_watchlist_valid(db, DEFAULT_SYMBOLS)
    return get_available_symbols()


def _ensure_watchlist_valid(db: Session, available: List[Dict[str, str]]) -> None:
    available_set = {item["symbol"] for item in available}
    raw_value = _load_config_value(db, SELECTED_SYMBOLS_KEY)
    if not raw_value:
        # Populate defaults
        default = [entry["symbol"] for entry in available[:MAX_WATCHLIST_SYMBOLS]] or [
            item["symbol"] for item in DEFAULT_SYMBOLS
        ]
        _save_config_value(db, SELECTED_SYMBOLS_KEY, json.dumps(default))
        return

    try:
        symbols = json.loads(raw_value)
        if not isinstance(symbols, list):
            raise ValueError("Selection is not a list")
    except Exception:
        logger.warning("Invalid Hyperliquid watchlist stored; resetting to defaults")
        default = [entry["symbol"] for entry in available[:MAX_WATCHLIST_SYMBOLS]] or [
            item["symbol"] for item in DEFAULT_SYMBOLS
        ]
        _save_config_value(db, SELECTED_SYMBOLS_KEY, json.dumps(default))
        return

    filtered = [str(sym).upper() for sym in symbols if str(sym).upper() in available_set]

    if filtered:
        _save_config_value(db, SELECTED_SYMBOLS_KEY, json.dumps(filtered[:MAX_WATCHLIST_SYMBOLS]))
        return

    if symbols:
        # Previously selected symbols are no longer available -> fall back to defaults
        default = [entry["symbol"] for entry in available[:MAX_WATCHLIST_SYMBOLS]] or [
            item["symbol"] for item in DEFAULT_SYMBOLS
        ]
        _save_config_value(db, SELECTED_SYMBOLS_KEY, json.dumps(default))
    else:
        # User intentionally cleared watchlist, keep empty
        _save_config_value(db, SELECTED_SYMBOLS_KEY, json.dumps([]))


def get_available_symbols() -> List[Dict[str, str]]:
    """Return cached available Hyperliquid symbols."""
    with SessionLocal() as db:
        stored = _parse_symbol_json(_load_config_value(db, AVAILABLE_SYMBOLS_KEY))
        if stored:
            return stored
        # Seed defaults if missing
        _save_config_value(db, AVAILABLE_SYMBOLS_KEY, _serialize_symbols(DEFAULT_SYMBOLS))
        _ensure_watchlist_valid(db, DEFAULT_SYMBOLS)
        return DEFAULT_SYMBOLS.copy()


def get_available_symbols_info() -> Dict[str, Optional[str]]:
    """Return available symbols plus last update timestamp."""
    with SessionLocal() as db:
        config = db.query(SystemConfig).filter(SystemConfig.key == AVAILABLE_SYMBOLS_KEY).first()
        symbols = _parse_symbol_json(config.value if config else None)
        updated_at = config.updated_at.isoformat() if config and config.updated_at else None
        if not symbols:
            symbols = DEFAULT_SYMBOLS.copy()
        return {"symbols": symbols, "updated_at": updated_at}


def get_available_symbol_map() -> Dict[str, Dict[str, str]]:
    """Return mapping of symbol -> metadata."""
    return {entry["symbol"]: entry for entry in get_available_symbols()}


def get_selected_symbols() -> List[str]:
    """Return user-selected Hyperliquid symbols."""
    with SessionLocal() as db:
        raw_value = _load_config_value(db, SELECTED_SYMBOLS_KEY)
        try:
            selected = json.loads(raw_value) if raw_value else []
        except json.JSONDecodeError:
            selected = []

        available_set = {entry["symbol"] for entry in get_available_symbols()}
        filtered = [
            str(symbol).upper()
            for symbol in selected
            if str(symbol).upper() in available_set
        ]

        if filtered:
            return filtered[:MAX_WATCHLIST_SYMBOLS]

        if raw_value:
            # User explicitly saved empty list or all selections invalid -> return empty
            return []

        # If nothing stored yet, default to first few
        default = [entry["symbol"] for entry in get_available_symbols()[:MAX_WATCHLIST_SYMBOLS]]
        _save_config_value(db, SELECTED_SYMBOLS_KEY, json.dumps(default))
        return default


def update_selected_symbols(symbols: List[str]) -> List[str]:
    """Persist new watchlist (validated)."""
    unique_symbols: List[str] = []
    seen = set()
    for symbol in symbols:
        symbol_upper = str(symbol).upper()
        if symbol_upper in seen:
            continue
        seen.add(symbol_upper)
        unique_symbols.append(symbol_upper)

    if len(unique_symbols) > MAX_WATCHLIST_SYMBOLS:
        raise ValueError(f"Cannot monitor more than {MAX_WATCHLIST_SYMBOLS} symbols")

    available_set = {entry["symbol"] for entry in get_available_symbols()}
    invalid = [symbol for symbol in unique_symbols if symbol not in available_set]
    if invalid:
        raise ValueError(f"Unsupported Hyperliquid symbols: {', '.join(invalid)}")

    with SessionLocal() as db:
        _save_config_value(db, SELECTED_SYMBOLS_KEY, json.dumps(unique_symbols))

    logger.info("Hyperliquid watchlist updated: %s", ", ".join(unique_symbols) or "none")
    refresh_market_stream_symbols()
    return unique_symbols


def get_symbol_display(symbol: str) -> str:
    """Friendly display name for symbol."""
    symbol_upper = symbol.upper()
    metadata = get_available_symbol_map()
    entry = metadata.get(symbol_upper)
    if entry:
        return entry.get("name") or symbol_upper
    return symbol_upper


def schedule_symbol_refresh_task(interval_seconds: int = 7200) -> None:
    """Register periodic symbol refresh job."""
    from services.scheduler import task_scheduler

    def _task():
        try:
            refreshed = refresh_hyperliquid_symbols()
            logger.debug("Symbol refresh task ran; %d symbols available", len(refreshed))
        except Exception as err:
            logger.warning("Hyperliquid symbol refresh failed: %s", err)

    # Remove existing task if present to avoid duplicates
    task_scheduler.remove_task(SYMBOL_REFRESH_TASK_ID)
    task_scheduler.add_interval_task(
        task_func=_task,
        interval_seconds=interval_seconds,
        task_id=SYMBOL_REFRESH_TASK_ID,
    )


def _has_active_paper_accounts() -> bool:
    """Return True if any active AI account is still running in paper mode."""
    with SessionLocal() as db:
        paper_account = (
            db.query(Account.id)
            .filter(
                Account.is_active == "true",
                Account.auto_trading_enabled == "true",
                Account.account_type == "AI",
                Account.hyperliquid_enabled != "true",
            )
            .first()
        )
        return paper_account is not None


def build_market_stream_symbols() -> List[str]:
    """Compute the combined set of symbols for the shared market data stream."""
    paper_symbols: List[str] = []
    if _has_active_paper_accounts():
        try:
            from services.trading_commands import AI_TRADING_SYMBOLS
        except Exception:
            paper_symbols = [entry["symbol"] for entry in DEFAULT_SYMBOLS]
        else:
            paper_symbols = list(AI_TRADING_SYMBOLS)

    combined = sorted(set(paper_symbols + get_selected_symbols()))
    return combined


def refresh_market_stream_symbols() -> List[str]:
    """
    Update market data stream with combined paper + selected Hyperliquid symbols.

    Returns the combined list used.
    """
    combined = build_market_stream_symbols()

    try:
        from services.market_stream import market_data_stream, start_market_stream
    except Exception as err:
        logger.warning("Unable to update market stream symbols: %s", err)
        return combined

    if market_data_stream:
        market_data_stream.update_symbols(combined)
    else:
        start_market_stream(combined, interval_seconds=1.5)

    return combined
