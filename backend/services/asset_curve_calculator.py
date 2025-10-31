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

logger = logging.getLogger(__name__)

# Bucket sizes in minutes for each timeframe option
TIMEFRAME_BUCKET_MINUTES: Dict[str, int] = {
    "5m": 5,
    "1h": 60,
    "1d": 60 * 24,
    "all": 0,  # 0 means no bucketing, return all snapshots
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


def _get_bucketed_snapshots(
    db: Session, bucket_minutes: int
) -> List[Tuple[int, float, float, float, datetime]]:
    """
    Query snapshots grouped by bucket using SQL aggregation.

    Returns tuples: (account_id, total_assets, cash, positions_value, event_time)
    
    If bucket_minutes is 0, returns all snapshots without bucketing.
    """
    # If bucket_minutes is 0, return all snapshots without bucketing
    if bucket_minutes == 0:
        rows = (
            db.query(
                AccountAssetSnapshot.account_id,
                AccountAssetSnapshot.total_assets,
                AccountAssetSnapshot.cash,
                AccountAssetSnapshot.positions_value,
                AccountAssetSnapshot.event_time,
            )
            .order_by(AccountAssetSnapshot.event_time.asc(), AccountAssetSnapshot.account_id.asc())
            .all()
        )
        return rows

    bucket_seconds = bucket_minutes * 60

    time_seconds = cast(func.strftime("%s", AccountAssetSnapshot.event_time), Integer)
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


def get_all_asset_curves_data_new(db: Session, timeframe: str = "1h") -> List[Dict]:
    """
    Build asset curve data for all active accounts using cached SQL aggregation.
    
    Args:
        timeframe: Time period for the curve, options: "5m", "1h", "1d", "all"
    """
    bucket_minutes = TIMEFRAME_BUCKET_MINUTES.get(timeframe, TIMEFRAME_BUCKET_MINUTES.get("5m", 5))

    current_max_snapshot_id: Optional[int] = db.query(func.max(AccountAssetSnapshot.id)).scalar()
    cache_key = timeframe

    with _CACHE_LOCK:
        cache_entry = _ASSET_CURVE_CACHE.get(cache_key)
        if (
            cache_entry
            and cache_entry.get("last_snapshot_id") == current_max_snapshot_id
            and cache_entry.get("data") is not None
        ):
            return cache_entry["data"]  # type: ignore[return-value]

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
