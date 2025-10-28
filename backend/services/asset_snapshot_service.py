"""
Record account asset snapshots on price updates.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Account, AccountAssetSnapshot
from services.asset_calculator import calc_positions_value

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
        for account in accounts:
            try:
                positions_value = calc_positions_value(session, account.id)
                total_assets = float(positions_value) + float(account.current_cash or 0)

                snapshot = AccountAssetSnapshot(
                    account_id=account.id,
                    total_assets=total_assets,
                    cash=float(account.current_cash or 0),
                    positions_value=float(positions_value),
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
