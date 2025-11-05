"""
Hyperliquid Management API Routes

Provides endpoints for:
- Account setup and configuration
- Environment switching (testnet/mainnet)
- Balance and position queries
- Manual order placement (for testing)
- Connection testing
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
import logging

from database.connection import get_db
from services.hyperliquid_environment import (
    setup_hyperliquid_account,
    get_hyperliquid_client,
    switch_hyperliquid_environment,
    get_account_hyperliquid_config,
    disable_hyperliquid_trading,
    enable_hyperliquid_trading
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hyperliquid", tags=["hyperliquid"])


# Request/Response Models
class HyperliquidSetupRequest(BaseModel):
    """Request model for Hyperliquid account setup"""
    environment: str = Field(..., pattern="^(testnet|mainnet)$", description="Trading environment")
    private_key: str = Field(..., min_length=10, description="Hyperliquid private key (will be encrypted)", alias="privateKey")
    max_leverage: int = Field(3, ge=1, le=50, description="Maximum allowed leverage", alias="maxLeverage")
    default_leverage: int = Field(1, ge=1, le=50, description="Default leverage for orders", alias="defaultLeverage")

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "environment": "testnet",
                "privateKey": "0x1234567890abcdef...",
                "maxLeverage": 3,
                "defaultLeverage": 1
            }
        }


class EnvironmentSwitchRequest(BaseModel):
    """Request model for environment switching"""
    target_environment: str = Field(..., pattern="^(testnet|mainnet)$")
    confirm_switch: bool = Field(False, description="Must be True to proceed (safety check)")

    class Config:
        json_schema_extra = {
            "example": {
                "target_environment": "mainnet",
                "confirm_switch": True
            }
        }


class ManualOrderRequest(BaseModel):
    """Request model for manual order placement"""
    symbol: str = Field(..., description="Asset symbol (e.g., 'BTC')")
    is_buy: bool = Field(..., description="True for long, False for short")
    size: float = Field(..., gt=0, description="Order size")
    order_type: str = Field("market", pattern="^(market|limit)$")
    price: Optional[float] = Field(None, gt=0, description="Price for limit orders")
    leverage: int = Field(1, ge=1, le=50, description="Position leverage")
    reduce_only: bool = Field(False, description="Only close existing positions")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "BTC",
                "is_buy": True,
                "size": 0.01,
                "order_type": "market",
                "leverage": 2,
                "reduce_only": False
            }
        }


# API Endpoints

@router.post("/accounts/{account_id}/setup")
async def setup_account(
    account_id: int,
    request: HyperliquidSetupRequest,
    db: Session = Depends(get_db)
):
    """
    Setup Hyperliquid trading for an account

    This endpoint:
    - Encrypts and stores the private key
    - Sets the trading environment (testnet or mainnet)
    - Configures leverage limits
    - Enables Hyperliquid trading

    **Note**: Private keys are encrypted using Fernet before storage.
    Ensure HYPERLIQUID_ENCRYPTION_KEY is set in environment.
    """
    try:
        result = setup_hyperliquid_account(
            db=db,
            account_id=account_id,
            environment=request.environment,
            private_key=request.private_key,
            max_leverage=request.max_leverage,
            default_leverage=request.default_leverage
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Setup failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Setup failed: {str(e)}")


@router.post("/accounts/{account_id}/switch-environment")
async def switch_environment(
    account_id: int,
    request: EnvironmentSwitchRequest,
    db: Session = Depends(get_db)
):
    """
    Switch account between testnet and mainnet

    **Safety measures**:
    - Requires explicit confirmation (confirm_switch=True)
    - Blocks switch if open positions exist
    - Verifies target environment has credentials configured

    **Warning**: This is a critical operation. Ensure you understand
    the implications before switching environments.
    """
    try:
        result = switch_hyperliquid_environment(
            db=db,
            account_id=account_id,
            target_environment=request.target_environment,
            confirm_switch=request.confirm_switch
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Environment switch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Switch failed: {str(e)}")


@router.get("/accounts/{account_id}/config")
async def get_config(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Get Hyperliquid configuration for an account

    Returns:
    - Enabled status
    - Current environment
    - Leverage settings
    - Whether testnet/mainnet credentials are configured
    """
    try:
        config = get_account_hyperliquid_config(db, account_id)
        return config
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounts/{account_id}/balance")
async def get_balance(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Get real-time Hyperliquid account balance

    Returns:
    - Total equity
    - Available balance
    - Used margin
    - Margin usage percentage
    - Current environment
    """
    try:
        client = get_hyperliquid_client(db, account_id)
        balance = client.get_account_state(db)
        return balance
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get balance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Balance query failed: {str(e)}")


@router.get("/accounts/{account_id}/positions")
async def get_positions(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all open positions from Hyperliquid

    Returns list of positions with:
    - Symbol
    - Position size (signed: positive=long, negative=short)
    - Entry price
    - Current P&L
    - Liquidation price
    - Leverage
    """
    try:
        client = get_hyperliquid_client(db, account_id)
        positions = client.get_positions(db)
        return {
            'account_id': account_id,
            'environment': client.environment,
            'positions': positions,
            'count': len(positions)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get positions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Positions query failed: {str(e)}")


@router.post("/accounts/{account_id}/orders/manual")
async def place_manual_order(
    account_id: int,
    request: ManualOrderRequest,
    db: Session = Depends(get_db)
):
    """
    Manually place a Hyperliquid order

    **Use cases**:
    - Testing order placement
    - Manual intervention during trading
    - Emergency position closing

    **Warning**: This bypasses AI decision-making. Use with caution.
    """
    try:
        client = get_hyperliquid_client(db, account_id)

        # Validate leverage against account limits
        from database.models import Account
        account = db.query(Account).filter(Account.id == account_id).first()
        if request.leverage > account.max_leverage:
            raise HTTPException(
                status_code=400,
                detail=f"Leverage {request.leverage}x exceeds account maximum {account.max_leverage}x"
            )

        # Place order
        result = client.place_order(
            db=db,
            symbol=request.symbol,
            is_buy=request.is_buy,
            size=request.size,
            order_type=request.order_type,
            price=request.price,
            reduce_only=request.reduce_only,
            leverage=request.leverage
        )

        return {
            'account_id': account_id,
            'environment': client.environment,
            'order_result': result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Manual order failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Order placement failed: {str(e)}")


@router.post("/accounts/{account_id}/disable")
async def disable_trading(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Disable Hyperliquid trading for an account

    **Note**: This does NOT delete stored credentials, only disables trading.
    Credentials remain encrypted in database for potential re-enable.
    """
    try:
        result = disable_hyperliquid_trading(db, account_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to disable trading: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accounts/{account_id}/enable")
async def enable_trading(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Re-enable Hyperliquid trading for an account

    Requires account to have environment and credentials already configured.
    """
    try:
        result = enable_hyperliquid_trading(db, account_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to enable trading: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounts/{account_id}/test-connection")
async def test_connection(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Test Hyperliquid API connection

    This endpoint:
    - Validates account configuration
    - Tests API authentication
    - Fetches basic account info
    - Returns connection status

    Use this to verify setup before enabling automated trading.
    """
    try:
        client = get_hyperliquid_client(db, account_id)
        result = client.test_connection(db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Connection test failed: {e}", exc_info=True)
        return {
            'connected': False,
            'error': str(e),
            'account_id': account_id
        }


@router.get("/accounts/{account_id}/snapshots")
async def get_account_snapshots(
    account_id: int,
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of snapshots to return"),
    db: Session = Depends(get_db)
):
    """
    Get historical account snapshots for Hyperliquid account

    Returns time-series data of account equity, available balance, and used margin.
    Used for asset curve visualization in the frontend.

    Query Parameters:
    - limit: Maximum number of snapshots (default: 100, max: 1000)

    Returns:
    - Array of snapshot objects with timestamp, equity, balance, and margin data
    """
    from database.models import Account
    from database.snapshot_connection import SnapshotSessionLocal
    from database.snapshot_models import HyperliquidAccountSnapshot

    # Verify account exists and has Hyperliquid enabled
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.hyperliquid_enabled != "true":
        raise HTTPException(
            status_code=400,
            detail="Hyperliquid trading is not enabled for this account"
        )

    # Query snapshots from snapshot database
    snapshot_db = SnapshotSessionLocal()
    try:
        snapshots = snapshot_db.query(HyperliquidAccountSnapshot).filter(
            HyperliquidAccountSnapshot.account_id == account_id
        ).order_by(
            HyperliquidAccountSnapshot.created_at.desc()
        ).limit(limit).all()
    finally:
        snapshot_db.close()

    # Convert to response format (reverse to oldest first for charting)
    result = []
    for snapshot in reversed(snapshots):
        result.append({
            'account_id': snapshot.account_id,
            'environment': snapshot.environment,
            'snapshot_time': snapshot.created_at.isoformat(),
            'total_equity': float(snapshot.total_equity),
            'available_balance': float(snapshot.available_balance),
            'used_margin': float(snapshot.used_margin),
            'maintenance_margin': float(snapshot.maintenance_margin),
            'trigger_event': snapshot.trigger_event
        })

    return {
        'account_id': account_id,
        'account_name': account.name,
        'environment': account.hyperliquid_environment,
        'snapshot_count': len(result),
        'snapshots': result
    }


@router.get("/health")
async def health_check():
    """
    Hyperliquid service health check

    Returns service status and configuration info.
    """
    import os
    return {
        'status': 'healthy',
        'service': 'hyperliquid',
        'encryption_configured': bool(os.getenv('HYPERLIQUID_ENCRYPTION_KEY')),
        'endpoints': {
            'setup': '/api/hyperliquid/accounts/{id}/setup',
            'balance': '/api/hyperliquid/accounts/{id}/balance',
            'positions': '/api/hyperliquid/accounts/{id}/positions',
            'snapshots': '/api/hyperliquid/accounts/{id}/snapshots',
            'test': '/api/hyperliquid/accounts/{id}/test-connection'
        }
    }
