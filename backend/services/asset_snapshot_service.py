"""
Record account asset snapshots on price updates.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Account, AccountAssetSnapshot, Position
from services.market_data import get_last_price
from api.ws import broadcast_arena_asset_update, manager

logger = logging.getLogger(__name__)

SNAPSHOT_RETENTION_HOURS = 24


def _get_active_accounts(db: Session) -> List[Account]:
    return (
        db.query(Account)
        .filter(Account.is_active == "true", Account.account_type == "AI")
        .all()
    )


def handle_price_update(event: Dict[str, Any]) -> None:
    """Persist account asset snapshots based on the latest price event."""
    session = SessionLocal()
    try:
        accounts = _get_active_accounts(session)
        if not accounts:
            return

        trigger_symbol = event.get("symbol")
        trigger_market = event.get("market", "CRYPTO")
        event_time: datetime = event.get("event_time") or datetime.now(tz=timezone.utc)

        snapshots: List[AccountAssetSnapshot] = []
        symbol_totals = defaultdict(float)
        accounts_payload: List[Dict[str, Any]] = []
        total_available_cash = 0.0
        total_frozen_cash = 0.0
        total_positions_value = 0.0
        price_cache: Dict[str, float] = {}

        for account in accounts:
            try:
                positions = (
                    session.query(Position)
                    .filter(Position.account_id == account.id)
                    .all()
                )

                positions_value = 0.0
                for position in positions:
                    symbol_key = (position.symbol or "").upper()
                    market_key = position.market or "CRYPTO"
                    cache_key = f"{symbol_key}.{market_key}"

                    try:
                        if cache_key in price_cache:
                            price = price_cache[cache_key]
                        else:
                            price = float(get_last_price(symbol_key, market_key))
                            price_cache[cache_key] = price
                    except Exception as price_err:
                        logger.debug(
                            "Skipping valuation for %s.%s: %s",
                            symbol_key,
                            market_key,
                            price_err,
                        )
                        continue

                    current_value = price * float(position.quantity or 0.0)
                    positions_value += current_value
                    symbol_totals[symbol_key] += current_value

                available_cash = float(account.current_cash or 0.0)
                frozen_cash = float(account.frozen_cash or 0.0)
                total_assets = positions_value + available_cash

                total_available_cash += available_cash
                total_frozen_cash += frozen_cash
                total_positions_value += positions_value

                accounts_payload.append(
                    {
                        "account_id": account.id,
                        "account_name": account.name,
                        "model": account.model,
                        "available_cash": round(available_cash, 2),
                        "frozen_cash": round(frozen_cash, 2),
                        "positions_value": round(positions_value, 2),
                        "total_assets": round(total_assets, 2),
                    }
                )

                snapshot = AccountAssetSnapshot(
                    account_id=account.id,
                    total_assets=total_assets,
                    cash=available_cash,
                    positions_value=positions_value,
                    trigger_symbol=trigger_symbol,
                    trigger_market=trigger_market,
                    event_time=event_time,
                )
                snapshots.append(snapshot)
            except Exception as account_err:
                logger.warning(
                    "Failed to compute snapshot for account %s: %s",
                    account.name,
                    account_err,
                )

        if snapshots:
            session.bulk_save_objects(snapshots)
            session.commit()

        if manager.has_connections():
            update_payload = {
                "generated_at": event_time.isoformat(),
                "totals": {
                    "available_cash": round(total_available_cash, 2),
                    "frozen_cash": round(total_frozen_cash, 2),
                    "positions_value": round(total_positions_value, 2),
                    "total_assets": round(
                        total_available_cash + total_frozen_cash + total_positions_value, 2
                    ),
                },
                "symbols": {symbol: round(value, 2) for symbol, value in symbol_totals.items()},
                "accounts": accounts_payload,
            }
            try:
                manager.schedule_task(broadcast_arena_asset_update(update_payload))
            except Exception as broadcast_err:
                logger.debug("Failed to schedule arena asset broadcast: %s", broadcast_err)

        _purge_old_snapshots(session, cutoff_hours=SNAPSHOT_RETENTION_HOURS)
    except Exception as err:
        session.rollback()
        logger.error("Failed to record asset snapshots: %s", err)
    finally:
        session.close()


def _purge_old_snapshots(session: Session, cutoff_hours: int) -> None:
    """Remove snapshots older than retention window to control storage."""
    cutoff_time = datetime.now(tz=timezone.utc) - timedelta(hours=cutoff_hours)
    deleted = (
        session.query(AccountAssetSnapshot)
        .filter(AccountAssetSnapshot.event_time < cutoff_time)
        .delete(synchronize_session=False)
    )
    if deleted:
        session.commit()
        logger.debug("Purged %d old asset snapshots", deleted)
