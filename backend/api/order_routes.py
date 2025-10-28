"""
Order Management API Routes
Provides functionality for creating, querying, and canceling orders
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import logging

from database.connection import SessionLocal
from database.models import User, Order, Account
from schemas.order import OrderCreate, OrderOut
from services.order_matching import create_order, check_and_execute_order, get_pending_orders, cancel_order, process_all_pending_orders
from repositories.user_repo import verify_user_password, user_has_password, set_user_password, verify_auth_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["orders"])


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class OrderCreateRequest(BaseModel):
    """Order creation request model"""
    user_id: int
    symbol: str
    name: str
    side: str  # BUY/SELL
    order_type: str  # MARKET/LIMIT
    price: Optional[float] = None
    quantity: float
    username: Optional[str] = None  # Username for verification (required if no session_token)
    password: Optional[str] = None  # Trading password (required if no session_token)
    session_token: Optional[str] = None  # Auth session token (alternative to username+password)


class OrderExecutionResult(BaseModel):
    order_id: int
    executed: bool
    message: str


class OrderProcessingResult(BaseModel):
    """Order processing result model"""
    executed_count: int
    total_checked: int
    message: str


@router.post("/create", response_model=OrderOut)
async def create_new_order(request: OrderCreateRequest, db: Session = Depends(get_db)):
    """
    Create a new order
    
    Args:
        request: Order creation request
        db: Database session
        
    Returns:
        Created order information
    """
    try:
        # Get user
        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Authentication: supports either session_token or username+password
        if request.session_token:
            # Authenticate using session token (hardcoded 180-day password-free feature)
            session_user_id = verify_auth_session(db, request.session_token)
            if session_user_id != request.user_id:
                raise HTTPException(status_code=401, detail="Invalid or expired session")
        elif request.username and request.password:
            # Authenticate using username and password
            if user.username != request.username:
                raise HTTPException(status_code=401, detail="Username does not match")
            
            # Password verification
            if not user_has_password(db, request.user_id):
                # First transaction, set password
                if len(request.password.strip()) < 4:
                    raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
                
                updated_user = set_user_password(db, request.user_id, request.password)
                if not updated_user:
                    raise HTTPException(status_code=500, detail="Failed to set trading password")
                
                logger.info(f"User {request.user_id} first transaction, trading password set")
            else:
                # Verify existing password
                if not verify_user_password(db, request.user_id, request.password):
                    raise HTTPException(status_code=401, detail="Incorrect trading password")
        else:
            raise HTTPException(status_code=400, detail="Please provide either session token or username+password")
        
        # Resolve trading account for the user (default user initialized in backend/main.py has at least one account)
        account = (
            db.query(Account)
            .filter(Account.user_id == user.id, Account.is_active == "true")
            .first()
        )
        if not account:
            raise HTTPException(status_code=404, detail="Active trading account not found for user")

        # Create order (crypto-only)
        order = create_order(
            db=db,
            account=account,
            symbol=request.symbol,
            name=request.name,
            side=request.side,
            order_type=request.order_type,
            price=request.price,
            quantity=request.quantity
        )
        
        db.commit()
        db.refresh(order)
        
        logger.info(f"User {user.username} created order: {order.order_no}")
        return order
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create order: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create order: {str(e)}")


@router.get("/pending", response_model=List[OrderOut])
async def get_user_pending_orders(user_id: Optional[int] = None, db: Session = Depends(get_db)):
    """
    Get pending orders
    
    Args:
        user_id: User ID, if None returns pending orders for all users
        db: Database session
        
    Returns:
        List of pending orders
    """
    try:
        orders = get_pending_orders(db, user_id)
        return orders
    except Exception as e:
        logger.error(f"Failed to get pending orders: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get pending orders: {str(e)}")


@router.get("/user/{user_id}", response_model=List[OrderOut])
async def get_user_orders(user_id: int, status: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Get all orders for a user
    
    Args:
        user_id: User ID
        status: Filter by order status (PENDING/FILLED/CANCELLED)
        db: Database session
        
    Returns:
        List of user's orders
    """
    try:
        query = db.query(Order).filter(Order.user_id == user_id)
        
        if status:
            query = query.filter(Order.status == status)
        
        orders = query.order_by(Order.created_at.desc()).all()
        return orders
        
    except Exception as e:
        logger.error(f"Failed to get user orders: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get user orders: {str(e)}")


@router.post("/execute/{order_id}", response_model=OrderExecutionResult)
async def execute_order_manually(order_id: int, db: Session = Depends(get_db)):
    """
    Manually execute a specific order (check execution conditions)
    
    Args:
        order_id: Order ID
        db: Database session
        
    Returns:
        Order execution result
    """
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.status != "PENDING":
            return OrderExecutionResult(
                order_id=order_id,
                executed=False,
                message=f"Order status is {order.status}, cannot execute"
            )
        
        # Check and execute order
        executed = check_and_execute_order(db, order)
        
        if executed:
            return OrderExecutionResult(
                order_id=order_id,
                executed=True,
                message="Order executed successfully"
            )
        else:
            return OrderExecutionResult(
                order_id=order_id,
                executed=False,
                message="Order does not meet execution conditions"
            )
            
    except Exception as e:
        logger.error(f"Failed to execute order: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to execute order: {str(e)}")


@router.post("/cancel/{order_id}")
async def cancel_user_order(order_id: int, reason: str = "User cancelled", db: Session = Depends(get_db)):
    """
    Cancel an order
    
    Args:
        order_id: Order ID
        reason: Reason for cancellation
        db: Database session
        
    Returns:
        Cancellation result
    """
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.status != "PENDING":
            raise HTTPException(status_code=400, detail=f"Order status is {order.status}, cannot be cancelled")
        
        success = cancel_order(db, order, reason)
        
        if success:
            return {"message": "Order cancelled successfully", "order_id": order_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to cancel order")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel order: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel order: {str(e)}")


@router.post("/process-all", response_model=OrderProcessingResult)
async def process_all_orders(db: Session = Depends(get_db)):
    """
    Process all pending orders
    
    Args:
        db: Database session
        
    Returns:
        Processing statistics
    """
    try:
        executed_count, total_checked = process_all_pending_orders(db)
        
        return OrderProcessingResult(
            executed_count=executed_count,
            total_checked=total_checked,
            message=f"Processing complete: Checked {total_checked} orders, executed {executed_count}"
        )
        
    except Exception as e:
        logger.error(f"Failed to process orders: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process orders: {str(e)}")


@router.get("/order/{order_id}", response_model=OrderOut)
async def get_order_details(order_id: int, db: Session = Depends(get_db)):
    """
    Get order details
    
    Args:
        order_id: Order ID
        db: Database session
        
    Returns:
        Order details
    """
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        return order
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get order details: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get order details: {str(e)}")


@router.get("/health")
async def orders_health_check(db: Session = Depends(get_db)):
    """
    Order service health check
    
    Returns:
        Service status information
    """
    try:
        # Count orders by status
        total_orders = db.query(Order).count()
        pending_orders = db.query(Order).filter(Order.status == "PENDING").count()
        filled_orders = db.query(Order).filter(Order.status == "FILLED").count()
        cancelled_orders = db.query(Order).filter(Order.status == "CANCELLED").count()
        
        import time
        return {
            "status": "healthy",
            "timestamp": int(time.time() * 1000),
            "statistics": {
                "total_orders": total_orders,
                "pending_orders": pending_orders,
                "filled_orders": filled_orders,
                "cancelled_orders": cancelled_orders
            },
            "message": "Order service is running normally"
        }
        
    except Exception as e:
        logger.error(f"Order service health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": int(time.time() * 1000),
            "error": str(e),
            "message": "Order service exception"
        }