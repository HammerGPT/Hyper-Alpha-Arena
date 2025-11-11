"""
Asset Curve Calculator with SQL-level aggregation and caching.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import cast, func
from sqlalchemy.orm import Session, aliased
from sqlalchemy.types import Integer

from database.models import Account, AccountAssetSnapshot
from database.snapshot_connection import SnapshotSessionLocal
from database.snapshot_models import HyperliquidAccountSnapshot

logger = logging.getLogger(__name__)

# Bucket sizes in minutes for each timeframe option
TIMEFRAME_BUCKET_MINUTES: Dict[str, int] = {
    "5m": 5,
    "1h": 60,
    "1d": 60 * 24,
}

# Simple in-process cache keyed by timeframe
_ASSET_CURVE_CACHE: Dict[str, Dict[str, object]] = {}
_CACHE_LOCK = threading.Lock()


def invalidate_asset_curve_cache() -> None:
    """Clear cached asset curve data (call when snapshots change)."""
    with _CACHE_LOCK:
        _ASSET_CURVE_CACHE.clear()
        logger.debug("Asset curve cache invalidated")


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_utc_timestamp(dt: datetime) -> int:
    """Convert datetime to UTC timestamp"""
    utc_dt = _ensure_utc(dt)
    return int(utc_dt.timestamp())


def _get_bucketed_snapshots(
    db: Session, bucket_minutes: int
) -> List[Tuple[int, float, float, float, datetime]]:
    """
    Query snapshots grouped by bucket using SQL aggregation.

    Returns tuples: (account_id, total_assets, cash, positions_value, event_time)
    """
    bucket_seconds = bucket_minutes * 60
    if bucket_seconds <= 0:
        bucket_seconds = TIMEFRAME_BUCKET_MINUTES["5m"] * 60

    time_seconds = cast(func.extract('epoch', AccountAssetSnapshot.event_time), Integer)
    bucket_index_expr = cast(func.floor(time_seconds / bucket_seconds), Integer)

    bucket_subquery = (
        db.query(
            AccountAssetSnapshot.account_id.label("account_id"),
            bucket_index_expr.label("bucket_index"),
            func.max(AccountAssetSnapshot.event_time).label("latest_event_time"),
        )
        .group_by(AccountAssetSnapshot.account_id, bucket_index_expr)
        .subquery()
    )

    snapshot_alias = aliased(AccountAssetSnapshot)

    rows = (
        db.query(
            snapshot_alias.account_id,
            snapshot_alias.total_assets,
            snapshot_alias.cash,
            snapshot_alias.positions_value,
            snapshot_alias.event_time,
        )
        .join(
            bucket_subquery,
            (snapshot_alias.account_id == bucket_subquery.c.account_id)
            & (snapshot_alias.event_time == bucket_subquery.c.latest_event_time),
        )
        .order_by(snapshot_alias.event_time.asc(), snapshot_alias.account_id.asc())
        .all()
    )

    return rows


def get_all_asset_curves_data_new(
    db: Session,
    timeframe: str = "1h",
    trading_mode: str = "testnet",
    environment: Optional[str] = None,
    wallet_address: Optional[str] = None,
) -> List[Dict]:
    """
    Build asset curve data for all active accounts using cached SQL aggregation.
    """
    bucket_minutes = TIMEFRAME_BUCKET_MINUTES.get(timeframe, TIMEFRAME_BUCKET_MINUTES["5m"])

    # Handle Hyperliquid mode with 5-minute bucketing
    hyperliquid_modes = {"hyperliquid", "testnet", "mainnet"}
    if trading_mode in hyperliquid_modes:
        effective_environment = environment
        if effective_environment not in {"testnet", "mainnet"} and trading_mode in {"testnet", "mainnet"}:
            effective_environment = trading_mode
        return _build_hyperliquid_asset_curve(
            db,
            bucket_minutes,
            environment=effective_environment,
            wallet_address=wallet_address,
        )

    # For other non-paper modes, return empty data for now
    if trading_mode != "paper":
        return []

    current_max_snapshot_id: Optional[int] = db.query(func.max(AccountAssetSnapshot.id)).scalar()
    cache_key = f"{timeframe}_{trading_mode}"

    with _CACHE_LOCK:
        cache_entry = _ASSET_CURVE_CACHE.get(cache_key)
        if (
            cache_entry
            and cache_entry.get("last_snapshot_id") == current_max_snapshot_id
            and cache_entry.get("data") is not None
        ):
            return cache_entry["data"]  # type: ignore[return-value]

    # Get all active accounts for paper mode
    accounts = db.query(Account).filter(Account.is_active == "true").all()
    account_map = {account.id: account for account in accounts}
    rows = _get_bucketed_snapshots(db, bucket_minutes)

    result: List[Dict] = []
    seen_accounts = set()

    for account_id, total_assets, cash, positions_value, event_time in rows:
        account = account_map.get(account_id)
        if not account:
            continue

        event_time_utc = _ensure_utc(event_time)
        seen_accounts.add(account_id)
        result.append(
            {
                "timestamp": int(event_time_utc.timestamp()),
                "datetime_str": event_time_utc.isoformat(),
                "account_id": account_id,
                "user_id": account.user_id,
                "username": account.name,
                "total_assets": float(total_assets),
                "cash": float(cash),
                "positions_value": float(positions_value),
            }
        )

    # Ensure accounts without snapshots still appear with their initial capital
    now_utc = datetime.now(timezone.utc)
    for account in accounts:
        if account.id not in seen_accounts:
            result.append(
                {
                    "timestamp": int(now_utc.timestamp()),
                    "datetime_str": now_utc.isoformat(),
                    "account_id": account.id,
                    "user_id": account.user_id,
                    "username": account.name,
                    "total_assets": float(account.initial_capital),
                    "cash": float(account.current_cash),
                    "positions_value": 0.0,
                }
            )

    result.sort(key=lambda item: (item["timestamp"], item["account_id"]))

    with _CACHE_LOCK:
        _ASSET_CURVE_CACHE[cache_key] = {
            "last_snapshot_id": current_max_snapshot_id,
            "data": result,
        }

    return result


def _build_hyperliquid_asset_curve(
    db: Session,
    bucket_minutes: int,
    environment: Optional[str] = None,
    wallet_address: Optional[str] = None,
) -> List[Dict]:
    """Build asset curve for Hyperliquid accounts with 5-minute bucketing"""
    bucket_seconds = bucket_minutes * 60
    if bucket_seconds <= 0:
        bucket_seconds = TIMEFRAME_BUCKET_MINUTES["5m"] * 60

    # Use snapshot database for Hyperliquid data
    snapshot_db = SnapshotSessionLocal()

    try:
        # Get active accounts with Hyperliquid environment configured
        account_query = db.query(Account).filter(
            Account.is_active == "true",
        )

        env_filter_value = environment if environment in {"testnet", "mainnet"} else None
        if env_filter_value:
            account_query = account_query.filter(Account.hyperliquid_environment == env_filter_value)

        accounts = account_query.all()

        if not accounts:
            return []

        account_map = {account.id: account for account in accounts}

        # Build bucket query for Hyperliquid snapshots
        time_seconds = cast(func.extract('epoch', HyperliquidAccountSnapshot.created_at), Integer)
        bucket_index_expr = cast(func.floor(time_seconds / bucket_seconds), Integer)

        bucket_query = snapshot_db.query(
            HyperliquidAccountSnapshot.account_id.label("account_id"),
            bucket_index_expr.label("bucket_index"),
            func.max(HyperliquidAccountSnapshot.created_at).label("latest_created_at"),
        )
        if env_filter_value:
            bucket_query = bucket_query.filter(HyperliquidAccountSnapshot.environment == env_filter_value)
        if wallet_address:
            bucket_query = bucket_query.filter(HyperliquidAccountSnapshot.wallet_address == wallet_address)

        bucket_subquery = bucket_query.group_by(
            HyperliquidAccountSnapshot.account_id,
            bucket_index_expr,
        ).subquery()

        snapshot_alias = aliased(HyperliquidAccountSnapshot)
        rows_query = snapshot_db.query(
            snapshot_alias.account_id,
            snapshot_alias.total_equity,
            snapshot_alias.created_at,
            snapshot_alias.wallet_address,
        ).join(
            bucket_subquery,
            (snapshot_alias.account_id == bucket_subquery.c.account_id)
            & (snapshot_alias.created_at == bucket_subquery.c.latest_created_at),
        )

        if env_filter_value:
            rows_query = rows_query.filter(snapshot_alias.environment == env_filter_value)
        if wallet_address:
            rows_query = rows_query.filter(snapshot_alias.wallet_address == wallet_address)

        rows = rows_query.order_by(
            snapshot_alias.created_at.asc(),
            snapshot_alias.account_id.asc(),
        ).all()

        result: List[Dict] = []
        seen_accounts = set()

        for account_id, total_equity, created_at, snap_wallet in rows:
            account = account_map.get(account_id)
            if not account:
                continue

            seen_accounts.add(account_id)
            timestamp = _to_utc_timestamp(created_at)

            result.append({
                "timestamp": timestamp,
                "datetime_str": _ensure_utc(created_at).strftime("%Y-%m-%d %H:%M:%S"),
                "account_id": account_id,
                "username": account.name,
                "total_equity": float(total_equity),
                "wallet_address": snap_wallet,
            })

        # Add accounts without snapshots with initial capital
        now_utc = datetime.now(timezone.utc)
        for account in accounts:
            if account.id not in seen_accounts:
                initial_capital = float(account.initial_capital or 1000)
                result.append({
                    "timestamp": _to_utc_timestamp(now_utc),
                    "datetime_str": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
                    "account_id": account.id,
                    "username": account.name,
                    "total_equity": initial_capital,
                    "wallet_address": wallet_address,
                })

        result.sort(key=lambda item: (item["timestamp"], item["account_id"]))
        return result

    finally:
        snapshot_db.close()
