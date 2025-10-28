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
    trigger_mode: str,
    interval_seconds: Optional[int] = None,
    tick_batch_size: Optional[int] = None,
    enabled: bool = True,
) -> AccountStrategyConfig:
    strategy = get_strategy_by_account(db, account_id)
    if strategy is None:
        strategy = AccountStrategyConfig(account_id=account_id)
        db.add(strategy)

    strategy.trigger_mode = trigger_mode
    strategy.interval_seconds = interval_seconds
    strategy.tick_batch_size = tick_batch_size
    strategy.enabled = "true" if enabled else "false"

    db.commit()
    db.refresh(strategy)
    return strategy


def set_last_trigger(db: Session, account_id: int, when) -> None:
    strategy = get_strategy_by_account(db, account_id)
    if not strategy:
        return
    strategy.last_trigger_at = when
    db.commit()
