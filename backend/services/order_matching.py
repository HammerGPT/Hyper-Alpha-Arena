"""
Order matching service
Implements conditional execution logic for limit orders with enhanced paper trading simulations
"""

import uuid
from decimal import Decimal
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
import logging

from database.models import Order, Position, Trade, Account, User, CRYPTO_MIN_COMMISSION, CRYPTO_COMMISSION_RATE, CRYPTO_MIN_ORDER_QUANTITY, CRYPTO_LOT_SIZE
from .market_data import get_last_price
from .paper_trading_engine import paper_trading_engine

logger = logging.getLogger(__name__)


def _calc_commission(notional: Decimal) -> Decimal:
    """Calculate commission"""
    pct_fee = notional * Decimal(str(CRYPTO_COMMISSION_RATE))
    min_fee = Decimal(str(CRYPTO_MIN_COMMISSION))
    return max(pct_fee, min_fee)


def create_order(db: Session, account: Account, symbol: str, name: str,
                side: str, order_type: str, price: Optional[float], quantity: float) -> Order:
    """
    Create limit order

    Args:
        db: Database session
        account: Account object
        symbol: crypto Symbol
        name: crypto name
        side: Buy/side direction (BUY/SELL)
        order_type: Order type (MARKET/LIMIT)
        price: Order price (required for limit orders)
        quantity: Order quantity

    Returns:
        Created order object

    Raises:
        ValueError: Parameter validation failed or insufficient funds/positions
    """
    # Basic parameter validation (crypto-only)
    
    # For crypto, we support fractional quantities, so no lot size validation needed
    # if quantity % CRYPTO_LOT_SIZE != 0:
    #     raise ValueError(f"Order quantity must be integer multiple of {CRYPTO_LOT_SIZE}")

    # For crypto, allow very small quantities (minimum $1 worth)
    if quantity <= 0:
        raise ValueError(f"Order quantity must be > 0")

    if order_type == "LIMIT" and (price is None or price <= 0):
        raise ValueError("Limit order must specify valid order price")
    
    # Get current market price for fund validation (only when cookie is configured)
    current_market_price = None
    if order_type == "MARKET":
        # Market order: get current price for fund validation
        try:
            current_market_price = get_last_price(symbol)
        except Exception as err:
            raise ValueError(f"Unable to get market price for market order: {err}")
        check_price = Decimal(str(current_market_price))
    else:
        # Limit order: use order price for fund validation
        check_price = Decimal(str(price))

    # Pre-check funds and positions
    if side == "BUY":
        # Buy: check if sufficient cash available
        notional = check_price * Decimal(quantity)
        commission = _calc_commission(notional)
        cash_needed = notional + commission

        if Decimal(str(account.current_cash)) < cash_needed:
            raise ValueError(f"Insufficient cash. Need ${cash_needed:.2f}, current cash ${account.current_cash:.2f}")

    else:  # SELL
        # Sell: check if sufficient positions available
        position = (
            db.query(Position)
            .filter(Position.account_id == account.id, Position.symbol == symbol, Position.market == "CRYPTO")
            .first()
        )

        if not position or Decimal(str(position.available_quantity)) < Decimal(str(quantity)):
            available_qty = float(position.available_quantity) if position else 0
            raise ValueError(f"Insufficient positions. Need {quantity} {symbol}, available {available_qty} {symbol}")
    
    # Create order
    order = Order(
        version="v1",
        account_id=account.id,
        order_no=uuid.uuid4().hex[:16],
        symbol=symbol,
        name=name,
        market="CRYPTO",
        side=side,
        order_type=order_type,
        price=price,
        quantity=quantity,
        filled_quantity=0,
        status="PENDING",
    )

    db.add(order)
    db.flush()

    logger.info(f"Created limit order: {order.order_no}, {side} {quantity} {symbol} @ {price if price else 'MARKET'}")

    return order


def check_and_execute_order(db: Session, order: Order) -> bool:
    """
    Check and execute limit order with enhanced paper trading simulations

    Execution conditions:
    - Buy: order price >= current market price and sufficient funds
    - Sell: order price <= current market price and sufficient positions

    Paper trading enhancements:
    - Realistic slippage (0.01-0.1% based on order size)
    - Execution latency (50-200ms)
    - Partial fills for large orders (>$10k)
    - Random order rejections (2% base rate)
    - Liquidity constraints (max $100k per order)

    Args:
        db: Database session
        order: Order to check

    Returns:
        Whether order was executed (fully or partially)
    """
    if order.status != "PENDING":
        return False

    # Check if cookie is configured, skip order checking if not
    try:
        # Get current market price
        current_price = get_last_price(order.symbol, order.market)
        current_price_decimal = Decimal(str(current_price))

        # Get user information
        account = db.query(Account).filter(Account.id == order.account_id).first()
        if not account:
            logger.error(f"Account corresponding to order {order.order_no} does not exist")
            return False

        # Check execution conditions
        should_execute = False
        execution_price = current_price_decimal

        if order.order_type == "MARKET":
            # Market order executes immediately
            should_execute = True
            execution_price = current_price_decimal

        elif order.order_type == "LIMIT":
            # Limit order conditional execution
            limit_price = Decimal(str(order.price))

            if order.side == "BUY":
                # Buy: order price >= current market price
                if limit_price >= current_price_decimal:
                    should_execute = True
                    execution_price = current_price_decimal  # Execute at market price

            else:  # SELL
                # Sell: order price <= current market price
                if limit_price <= current_price_decimal:
                    should_execute = True
                    execution_price = current_price_decimal  # Execute at market price

        if not should_execute:
            logger.debug(f"Order {order.order_no} does not meet execution condition: {order.side} {order.price} vs market {current_price}")
            return False

        # Enhanced paper trading simulation
        simulation_result = paper_trading_engine.simulate_order_execution(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=Decimal(str(order.quantity)),
            current_price=current_price_decimal,
            limit_price=Decimal(str(order.price)) if order.price else None
        )

        # Handle rejection
        if simulation_result.status == "REJECTED":
            order.status = "REJECTED"
            order.rejection_reason = simulation_result.rejection_reason
            db.commit()
            logger.info(f"Order {order.order_no} rejected: {simulation_result.rejection_reason}")
            return False

        # Use simulated execution price and quantity
        execution_price = simulation_result.execution_price
        filled_quantity = simulation_result.filled_quantity

        # Handle partial fills
        if simulation_result.status == "PARTIALLY_FILLED":
            logger.info(f"Order {order.order_no} partially filled: {float(filled_quantity)}/{order.quantity}")

        # Execute order with simulated parameters
        return _execute_order(
            db=db,
            order=order,
            account=account,
            execution_price=execution_price,
            filled_quantity=filled_quantity,
            slippage=simulation_result.slippage
        )

    except Exception as e:
        logger.error(f"Error checking order {order.order_no}: {e}")
        return False


def _release_frozen_on_fill(account: Account, order: Order, execution_price: Decimal, commission: Decimal):
    """Release frozen cash on fill (for BUY only)"""
    if order.side == "BUY":
        # Estimated frozen amount may differ from actual execution, release based on actual execution amount
        notional = execution_price * Decimal(order.quantity)
        frozen_to_release = notional + commission
        account.frozen_cash = float(max(Decimal(str(account.frozen_cash)) - frozen_to_release, Decimal('0')))


def _execute_order(
    db: Session,
    order: Order,
    account: Account,
    execution_price: Decimal,
    filled_quantity: Optional[Decimal] = None,
    slippage: Optional[Decimal] = None
) -> bool:
    """
    Execute order fill with optional paper trading parameters

    Args:
        db: Database session
        order: Order object
        account: Account object
        execution_price: Execution price (may include simulated slippage)
        filled_quantity: Quantity filled (may be partial). If None, uses full order quantity
        slippage: Slippage percentage (for paper trading tracking)

    Returns:
        Whether execution was successful
    """
    try:
        # Use filled_quantity if provided, otherwise full order quantity
        quantity = filled_quantity if filled_quantity is not None else Decimal(str(order.quantity))
        notional = execution_price * quantity
        commission = _calc_commission(notional)
        
        # Re-check funds and positions (prevent concurrency issues)
        if order.side == "BUY":
            cash_needed = notional + commission
            if Decimal(str(account.current_cash)) < cash_needed:
                logger.warning(f"Insufficient cash when executing order {order.order_no}")
                return False
                
            # Deduct cash
            account.current_cash = float(Decimal(str(account.current_cash)) - cash_needed)
            
            # Update position
            position = (
                db.query(Position)
                .filter(Position.account_id == account.id, Position.symbol == order.symbol, Position.market == order.market)
                .first()
            )
            
            if not position:
                position = Position(
                    version="v1",
                    account_id=account.id,
                    symbol=order.symbol,
                    name=order.name,
                    market=order.market,
                    quantity=0,
                    available_quantity=0,
                    avg_cost=0,
                )
                db.add(position)
                db.flush()
            
            # Calculate new average cost (use Decimal for precision)
            old_qty = Decimal(str(position.quantity))
            old_cost = Decimal(str(position.avg_cost))
            new_qty = old_qty + quantity
            
            if old_qty == 0:
                new_avg_cost = execution_price
            else:
                new_avg_cost = (old_cost * old_qty + notional) / new_qty
            
            position.quantity = float(new_qty)  # Store as float for database
            position.available_quantity = float(Decimal(str(position.available_quantity)) + quantity)
            position.avg_cost = float(new_avg_cost)
            
        else:  # SELL
            # Check position
            position = (
                db.query(Position)
                .filter(Position.account_id == account.id, Position.symbol == order.symbol, Position.market == order.market)
                .first()
            )

            if not position or Decimal(str(position.available_quantity)) < quantity:
                logger.warning(f"Insufficient position when executing order {order.order_no}")
                return False

            # Reduce position (use Decimal for precision)
            position.quantity = float(Decimal(str(position.quantity)) - quantity)
            position.available_quantity = float(Decimal(str(position.available_quantity)) - quantity)
            
            # Add cash
            cash_gain = notional - commission
            account.current_cash = float(Decimal(str(account.current_cash)) + cash_gain)
        
        # Create trade record
        trade = Trade(
            order_id=order.id,
            account_id=account.id,
            symbol=order.symbol,
            name=order.name,
            market=order.market,
            side=order.side,
            price=float(execution_price),
            quantity=float(quantity),
            commission=float(commission),
        )
        db.add(trade)

        # Release frozen (BUY)
        _release_frozen_on_fill(account, order, execution_price, commission)

        # Update order status and paper trading metadata
        order.filled_quantity = float(quantity)

        # Set status based on fill completeness
        if quantity >= Decimal(str(order.quantity)):
            order.status = "FILLED"
        else:
            order.status = "PARTIALLY_FILLED"

        # Store slippage for paper trading analysis
        if slippage is not None:
            order.slippage = float(slippage)

        db.commit()

        logger.info(f"Order {order.order_no} executed: {order.side} {quantity} {order.symbol} @ ${execution_price}")

        # Broadcast real-time updates via WebSocket
        import asyncio
        from api.ws import broadcast_trade_update, broadcast_position_update
        from repositories.position_repo import list_positions

        try:
            # Check if there's a running event loop (required for async tasks)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No event loop running, skip WebSocket broadcast
                logger.debug(f"No event loop available for WebSocket broadcast of order {order.order_no}")
                loop = None

            if loop:
                # Broadcast trade update
                asyncio.create_task(broadcast_trade_update({
                    "trade_id": trade.id,
                    "account_id": account.id,
                    "account_name": account.name,
                    "symbol": trade.symbol,
                    "name": trade.name,
                    "market": trade.market,
                    "side": trade.side,
                    "price": float(execution_price),
                    "quantity": float(quantity),
                    "commission": float(commission),
                    "notional": float(notional),
                    "trade_time": trade.trade_time.isoformat() if hasattr(trade.trade_time, 'isoformat') else str(trade.trade_time),
                    "direction": trade.side  # For frontend compatibility
                }))

                # Broadcast position update
                positions = list_positions(db, account.id)
                positions_data = [
                    {
                        "id": p.id,
                        "account_id": p.account_id,
                        "symbol": p.symbol,
                        "name": p.name,
                        "market": p.market,
                        "quantity": float(p.quantity),
                        "available_quantity": float(p.available_quantity),
                        "avg_cost": float(p.avg_cost),
                        "last_price": None,  # Will be updated by frontend
                        "market_value": None  # Will be updated by frontend
                    }
                    for p in positions
                ]
                asyncio.create_task(broadcast_position_update(account.id, positions_data))

        except Exception as broadcast_err:
            # Don't fail the order execution if broadcast fails
            logger.debug(f"WebSocket broadcast skipped for order {order.order_no}: {broadcast_err}")

        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Error executing order {order.order_no}: {e}")
        return False


def get_pending_orders(db: Session, account_id: Optional[int] = None) -> List[Order]:
    """
    Get pending orders

    Args:
        db: Database session
        account_id: Account ID, when None get all accounts' pending orders

    Returns:
        List of pending orders
    """
    query = db.query(Order).filter(Order.status == "PENDING")
    
    if account_id is not None:
        query = query.filter(Order.account_id == account_id)
    
    return query.order_by(Order.created_at).all()


def _release_frozen_on_cancel(account: Account, order: Order):
    """Release frozen on order cancel (BUY only)"""
    if order.side == "BUY":
        # Conservative release: estimate frozen amount based on order price, avoid getting market price
        ref_price = float(order.price or 0.0)
        if ref_price <= 0:
            # If no order price (theoretically shouldn't happen), use conservative estimate
            logger.warning(f"Order {order.order_no} has no order price, unable to accurately release frozen funds")
            ref_price = 100.0  # Use default value

        notional = Decimal(str(ref_price)) * Decimal(order.quantity)
        commission = _calc_commission(notional)
        release_amt = notional + commission
        account.frozen_cash = float(max(Decimal(str(account.frozen_cash)) - release_amt, Decimal('0')))


def cancel_order(db: Session, order: Order, reason: str = "User cancelled") -> bool:
    """
    Cancel order

    Args:
        db: Database session
        order: Order object
        reason: Cancel reason

    Returns:
        Whether cancellation was successful
    """
    if order.status != "PENDING":
        return False
    
    try:
        order.status = "CANCELLED"
        # Release frozen
        account = db.query(Account).filter(Account.id == order.account_id).first()
        if account:
            _release_frozen_on_cancel(account, order)
        db.commit()
        
        logger.info(f"Order {order.order_no} cancelled: {reason}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error cancelling order {order.order_no}: {e}")
        return False


def process_all_pending_orders(db: Session) -> Tuple[int, int]:
    """
    Process all pending orders

    Args:
        db: Database session

    Returns:
        (Executed orders count, Total checked orders)
    """
    pending_orders = get_pending_orders(db)
    executed_count = 0
    
    for order in pending_orders:
        if check_and_execute_order(db, order):
            executed_count += 1
    
    logger.info(f"Processing pending orders: checked {len(pending_orders)} orders, executed {executed_count} orders")
    return executed_count, len(pending_orders)