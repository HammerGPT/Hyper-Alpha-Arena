from decimal import Decimal
from sqlalchemy.orm import Session
from database.models import Position
from .market_data import get_last_price


def calc_positions_value(db: Session, account_id: int) -> float:
    """
    Calculate total market value of positions

    Args:
        db: Database session
        account_id: Account ID

    Returns:
        Total market value of positions, returns 0 if price cannot be obtained
    """
    positions = db.query(Position).filter(Position.account_id == account_id).all()
    total = Decimal("0")
    
    for p in positions:
        try:
            price = Decimal(str(get_last_price(p.symbol, p.market)))
            total += price * Decimal(p.quantity)
        except Exception as e:
            # Log error but don't interrupt calculation, skip position if price cannot be obtained
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Cannot get price for {p.symbol}.{p.market}, skipping position value calculation: {e}")
            continue
    
    return float(total)
