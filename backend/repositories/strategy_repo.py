from datetime import datetime, timezone
from typing import Optional, List
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


def upsert_strategy(
    db: Session,
    account_id: int,
    trigger_mode: str = "unified",
    interval_seconds: Optional[int] = None,
    tick_batch_size: Optional[int] = None,
    enabled: bool = True,
    price_threshold: Optional[float] = None,
    trigger_interval: Optional[int] = None,
) -> AccountStrategyConfig:
    print(f"upsert_strategy called with: account_id={account_id}, interval_seconds={interval_seconds}, trigger_interval={trigger_interval}")
    strategy = get_strategy_by_account(db, account_id)
    if strategy is None:
        strategy = AccountStrategyConfig(account_id=account_id)
        db.add(strategy)

    strategy.trigger_mode = trigger_mode
    strategy.trigger_interval = trigger_interval or interval_seconds
    strategy.tick_batch_size = tick_batch_size
    strategy.enabled = "true" if enabled else "false"
    if price_threshold is not None:
        strategy.price_threshold = price_threshold

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
