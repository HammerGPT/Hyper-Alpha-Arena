import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from database.models import Order, Position, Trade, User, US_MIN_COMMISSION, US_COMMISSION_RATE, US_MIN_ORDER_QUANTITY, US_LOT_SIZE
from .market_data import get_last_price


def _calc_commission(notional: Decimal) -> Decimal:
    pct_fee = notional * Decimal(str(US_COMMISSION_RATE))
    min_fee = Decimal(str(US_MIN_COMMISSION))
    return max(pct_fee, min_fee)

def place_and_execute(db: Session, user: User, symbol: str, name: str, market: str, side: str, order_type: str, price: float | None, quantity: int) -> Order:
    # Only support US market
    if market != "US":
        raise ValueError("Only US market is supported")

    # Adjust quantity to lot size
    if quantity % US_LOT_SIZE != 0:
        raise ValueError(f"quantity must be a multiple of lot_size={US_LOT_SIZE}")
    if quantity < US_MIN_ORDER_QUANTITY:
        raise ValueError(f"quantity must be >= min_order_quantity={US_MIN_ORDER_QUANTITY}")

    exec_price = Decimal(str(price if (order_type == "LIMIT" and price) else get_last_price(symbol, market)))

    order = Order(
        version="v1",
        user_id=user.id,
        order_no=uuid.uuid4().hex[:16],
        symbol=symbol,
        name=name,
        market=market,
        side=side,
        order_type=order_type,
        price=float(exec_price),
        quantity=quantity,
        filled_quantity=0,
        status="PENDING",
    )
    db.add(order)
    db.flush()

    notional = exec_price * Decimal(quantity)
    commission = _calc_commission(notional)

    if side == "BUY":
        cash_needed = notional + commission
        if Decimal(str(user.current_cash)) < cash_needed:
            raise ValueError("Insufficient USD cash")
        user.current_cash = float(Decimal(str(user.current_cash)) - cash_needed)
        
        # position update (avg cost)
        pos = (
            db.query(Position)
            .filter(Position.user_id == user.id, Position.symbol == symbol, Position.market == market)
            .first()
        )
        if not pos:
            pos = Position(
                version="v1",
                user_id=user.id,
                symbol=symbol,
                name=name,
                market=market,
                quantity=0,
                available_quantity=0,
                avg_cost=0,
            )
            db.add(pos)
            db.flush()
        new_qty = int(pos.quantity) + quantity
        new_cost = (Decimal(str(pos.avg_cost)) * Decimal(int(pos.quantity)) + notional) / Decimal(new_qty)
        pos.quantity = new_qty
        pos.available_quantity = int(pos.available_quantity) + quantity
        pos.avg_cost = float(new_cost)
    else:  # SELL
        pos = (
            db.query(Position)
            .filter(Position.user_id == user.id, Position.symbol == symbol, Position.market == market)
            .first()
        )
        if not pos or int(pos.available_quantity) < quantity:
            raise ValueError("Insufficient position to sell")
        pos.quantity = int(pos.quantity) - quantity
        pos.available_quantity = int(pos.available_quantity) - quantity
        
        cash_gain = notional - commission
        user.current_cash = float(Decimal(str(user.current_cash)) + cash_gain)

    trade = Trade(
        order_id=order.id,
        user_id=user.id,
        symbol=symbol,
        name=name,
        market=market,
        side=side,
        price=float(exec_price),
        quantity=quantity,
        commission=float(commission),
    )
    db.add(trade)

    order.filled_quantity = quantity
    order.status = "FILLED"

    db.commit()
    db.refresh(order)
    return order
