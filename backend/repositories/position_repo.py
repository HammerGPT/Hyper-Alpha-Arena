from sqlalchemy.orm import Session
from database.models import Position
from typing import List, Optional


def list_positions(db: Session, account_id: int) -> List[Position]:
    return db.query(Position).filter(Position.account_id == account_id).all()


def get_position(db: Session, account_id: int, symbol: str, market: str) -> Optional[Position]:
    return (
        db.query(Position)
        .filter(
            Position.account_id == account_id,
            Position.symbol == symbol,
            Position.market == market,
        )
        .first()
    )


def upsert_position(db: Session, position: Position) -> Position:
    db.add(position)
    db.commit()
    db.refresh(position)
    return position
