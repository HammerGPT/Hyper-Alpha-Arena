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
    trigger_mode: Optional[str] = None,  # None = preserve current value; creation default "unified"
    interval_seconds: Optional[int] = None,
    tick_batch_size: Optional[int] = None,
    enabled: Optional[bool] = None,  # None = preserve current value; creation default True
    scheduled_trigger_enabled: Optional[bool] = None,  # None = preserve current value; creation default True
    price_threshold: Optional[float] = None,
    trigger_interval: Optional[int] = None,
    signal_pool_id: Optional[int] = None,  # Deprecated: kept for backward compatibility
    signal_pool_ids: Optional[List[int]] = None,  # New: list of pool IDs
    exchange: Optional[str] = None,  # "hyperliquid" or "binance"; None = preserve current value
    execution_mode: Optional[str] = None,  # "real" or "paper"; None = preserve current value
) -> AccountStrategyConfig:
    print(f"upsert_strategy called with: account_id={account_id}, signal_pool_ids={signal_pool_ids}, signal_pool_id={signal_pool_id}")
    strategy = get_strategy_by_account(db, account_id)
    if strategy is None:
        strategy = AccountStrategyConfig(account_id=account_id)
        db.add(strategy)

    # trigger_mode has no backing DB column today (legacy/vestigial field kept only
    # as a transient attribute on the ORM instance); still honor None-preserve /
    # creation-default semantics for parity with the other fields and the API contract.
    if trigger_mode is not None:
        strategy.trigger_mode = trigger_mode
    elif getattr(strategy, "trigger_mode", None) is None:
        strategy.trigger_mode = "unified"

    strategy.trigger_interval = trigger_interval or interval_seconds
    strategy.tick_batch_size = tick_batch_size

    if enabled is not None:
        strategy.enabled = "true" if enabled else "false"
    elif strategy.enabled is None:
        # creation path: new row before flush has no value yet
        strategy.enabled = "true"

    if scheduled_trigger_enabled is not None:
        strategy.scheduled_trigger_enabled = scheduled_trigger_enabled
    elif strategy.scheduled_trigger_enabled is None:
        # creation path: new row before flush has no value yet
        strategy.scheduled_trigger_enabled = True

    if exchange is not None:
        normalized_exchange = str(exchange).lower()
        if normalized_exchange in ("hyperliquid", "binance"):
            strategy.exchange = normalized_exchange
        elif strategy.exchange is None:
            # creation path with an invalid value supplied: fall back to the old default
            strategy.exchange = "hyperliquid"
        # else: invalid value on an existing row -> preserve current value (no-op)
    elif strategy.exchange is None:
        # creation path: new row before flush has no value yet
        strategy.exchange = "hyperliquid"

    if execution_mode is not None:
        normalized_mode = str(execution_mode).lower()
        strategy.execution_mode = normalized_mode if normalized_mode in ("real", "paper") else "real"
    elif strategy.execution_mode is None:
        # creation path: new row before flush has no value yet
        strategy.execution_mode = "real"
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
