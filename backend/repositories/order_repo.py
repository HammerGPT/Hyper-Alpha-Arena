from sqlalchemy.orm import Session
from database.models import Order
from typing import List, Optional


def create_order(db: Session, order: Order) -> Order:
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def list_orders(db: Session, account_id: int) -> List[Order]:
    return (
        db.query(Order)
        .filter(Order.account_id == account_id)
        .order_by(Order.created_at.desc())
        .all()
    )


def get_order_by_no(db: Session, order_no: str) -> Optional[Order]:
    return db.query(Order).filter(Order.order_no == order_no).first()
