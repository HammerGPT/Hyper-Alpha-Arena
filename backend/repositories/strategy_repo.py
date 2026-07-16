from datetime import datetime, timezone
from typing import Optional, List
import json
from sqlalchemy.orm import Session

from database.models import AccountStrategyConfig


def get_strategy_by_account(db: Session, account_id: int) -> Optional[AccountStrategyConfig]:
    return (
        db.query(AccountStrategyConfig)
        .filter(AccountStrategyConfig.account_id == account_id)
        .first()
    )


def list_strategies(db: Session) -> List[AccountStrategyConfig]:
    return db.query(AccountStrategyConfig).all()


def parse_signal_pool_ids(strategy: AccountStrategyConfig) -> List[int]:
    """Parse signal_pool_ids from strategy, with fallback to signal_pool_id for compatibility."""
    # Try new field first
    if strategy.signal_pool_ids:
        try:
            ids = strategy.signal_pool_ids
            if isinstance(ids, str):
                ids = json.loads(ids)
            if isinstance(ids, list):
                return [int(i) for i in ids if i is not None]
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    # Fallback to old field
    if strategy.signal_pool_id is not None:
        return [strategy.signal_pool_id]
    return []


def upsert_strategy(
    db: Session,
    account_id: int,
    trigger_mode: str = "unified",
    interval_seconds: Optional[int] = None,
    tick_batch_size: Optional[int] = None,
    enabled: bool = True,
    scheduled_trigger_enabled: bool = True,
    price_threshold: Optional[float] = None,
    trigger_interval: Optional[int] = None,
    signal_pool_id: Optional[int] = None,  # Deprecated: kept for backward compatibility
    signal_pool_ids: Optional[List[int]] = None,  # New: list of pool IDs
    exchange: str = "hyperliquid",  # "hyperliquid" or "binance"
    execution_mode: str = "real",  # "real" or "paper"
) -> AccountStrategyConfig:
    print(f"upsert_strategy called with: account_id={account_id}, signal_pool_ids={signal_pool_ids}, signal_pool_id={signal_pool_id}")
    strategy = get_strategy_by_account(db, account_id)
    if strategy is None:
        strategy = AccountStrategyConfig(account_id=account_id)
        db.add(strategy)

    strategy.trigger_mode = trigger_mode
    strategy.trigger_interval = trigger_interval or interval_seconds
    strategy.tick_batch_size = tick_batch_size
    strategy.enabled = "true" if enabled else "false"
    strategy.scheduled_trigger_enabled = scheduled_trigger_enabled
    strategy.exchange = exchange
    strategy.execution_mode = execution_mode if execution_mode in ("real", "paper") else "real"
    if price_threshold is not None:
        strategy.price_threshold = price_threshold

    # Handle signal pool binding - prefer signal_pool_ids over signal_pool_id
    if signal_pool_ids is not None:
        # New format: store as JSON array
        strategy.signal_pool_ids = json.dumps(signal_pool_ids) if signal_pool_ids else None
        # Also update old field for backward compatibility (use first ID or None)
        strategy.signal_pool_id = signal_pool_ids[0] if signal_pool_ids else None
    elif signal_pool_id is not None:
        # Old format: convert to new format
        strategy.signal_pool_ids = json.dumps([signal_pool_id])
        strategy.signal_pool_id = signal_pool_id
    else:
        # Unbind all
        strategy.signal_pool_ids = None
        strategy.signal_pool_id = None

    db.commit()
    db.refresh(strategy)
    return strategy


def set_last_trigger(db: Session, account_id: int, when) -> None:
    strategy = get_strategy_by_account(db, account_id)
    if not strategy:
        return
    when_to_store = when
    if isinstance(when, datetime) and when.tzinfo is not None:
        when_to_store = when.astimezone(timezone.utc).replace(tzinfo=None)
    strategy.last_trigger_at = when_to_store
    db.commit()
