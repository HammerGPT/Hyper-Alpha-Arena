"""
Hyperliquid Management API Routes

Provides endpoints for:
- Account setup and configuration
- Environment switching (testnet/mainnet)
- Balance and position queries
- Manual order placement (for testing)
- Connection testing
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
import logging

from database.connection import get_db
from database.models import HyperliquidExchangeAction
from services.hyperliquid_environment import (
    setup_hyperliquid_account,
    get_hyperliquid_client,
    switch_hyperliquid_environment,
    get_account_hyperliquid_config,
    disable_hyperliquid_trading,
    enable_hyperliquid_trading,
)
from services.hyperliquid_symbol_service import (
    get_available_symbols_info,
    get_selected_symbols,
    update_selected_symbols,
    MAX_WATCHLIST_SYMBOLS,
)
from services.hyperliquid_cache import (
    get_cached_account_state,
    get_cached_positions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hyperliquid", tags=["hyperliquid"])


def _ts_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


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


class HyperliquidSymbolSelectionRequest(BaseModel):
    symbols: List[str] = Field(default_factory=list, description="Symbols to monitor")

    class Config:
        json_schema_extra = {
            "example": {
                "symbols": ["BTC", "ETH", "SOL"]
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
    force_refresh: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get Hyperliquid account balance.

    Unless force_refresh is True, this endpoint returns the most recent cached
    snapshot captured by the backend. This avoids excessive direct calls to
    Hyperliquid when rendering dashboards.
    """
    try:
        if not force_refresh:
            cached_entry = get_cached_account_state(account_id)
            if cached_entry:
                payload = dict(cached_entry["data"])
                payload["source"] = "cache"
                payload["cached_at"] = _ts_to_iso(cached_entry["timestamp"])
                return payload

        client = get_hyperliquid_client(db, account_id)
        balance = client.get_account_state(db)
        balance["source"] = "live"
        ts_ms = balance.get("timestamp")
        if isinstance(ts_ms, (int, float)):
            balance["cached_at"] = _ts_to_iso(ts_ms / 1000.0)
        else:
            balance["cached_at"] = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
        return balance
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get balance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Balance query failed: {str(e)}")


@router.get("/accounts/{account_id}/positions")
async def get_positions(
    account_id: int,
    force_refresh: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get all open positions for an account.

    By default, this uses the latest cached snapshot taken by the backend.
    Set force_refresh=true to fetch directly from Hyperliquid.
    """
    try:
        if not force_refresh:
            cached_entry = get_cached_positions(account_id)
            if cached_entry:
                account_cache = get_cached_account_state(account_id)
                environment = (
                    account_cache["data"].get("environment")
                    if account_cache and isinstance(account_cache.get("data"), dict)
                    else "unknown"
                )
                return {
                    'account_id': account_id,
                    'environment': environment,
                    'positions': cached_entry["data"],
                    'count': len(cached_entry["data"]),
                    'source': 'cache',
                    'cached_at': _ts_to_iso(cached_entry["timestamp"]),
                }

        client = get_hyperliquid_client(db, account_id)
        positions = client.get_positions(db)
        return {
            'account_id': account_id,
            'environment': client.environment,
            'positions': positions,
            'count': len(positions),
            'source': 'live',
            'cached_at': datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
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

    # Verify account exists and has Hyperliquid environment configured
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if not account.hyperliquid_environment:
        raise HTTPException(
            status_code=400,
            detail="Hyperliquid environment is not configured for this account"
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


@router.get("/symbols/available")
async def list_available_symbols():
    """Return cached Hyperliquid tradable symbols (refreshed periodically)."""
    info = get_available_symbols_info()
    return {
        "symbols": info.get("symbols", []),
        "updated_at": info.get("updated_at"),
        "max_symbols": MAX_WATCHLIST_SYMBOLS,
    }


@router.get("/symbols/watchlist")
async def get_symbol_watchlist():
    """Return the currently configured global Hyperliquid watchlist."""
    symbols = get_selected_symbols()
    return {
        "symbols": symbols,
        "max_symbols": MAX_WATCHLIST_SYMBOLS,
    }


@router.put("/symbols/watchlist")
async def update_symbol_watchlist(payload: HyperliquidSymbolSelectionRequest):
    """Update global Hyperliquid watchlist (max 10 symbols)."""
    try:
        symbols = update_selected_symbols(payload.symbols)
        return {
            "symbols": symbols,
            "max_symbols": MAX_WATCHLIST_SYMBOLS,
        }
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:
        logger.error(f"Failed to update Hyperliquid watchlist: {err}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update Hyperliquid watchlist")


@router.get("/actions/summary")
async def get_action_summary(
    window_minutes: int = 1440,
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Summarize Hyperliquid exchange actions recorded by the backend.

    Parameters:
    - window_minutes: Lookback window (default 24h)
    - account_id: Optional filter for a single account
    """
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        query = db.query(
            HyperliquidExchangeAction.action_type.label("action_type"),
            func.count(HyperliquidExchangeAction.id).label("count"),
            func.sum(
                case((HyperliquidExchangeAction.status == "error", 1), else_=0)
            ).label("errors"),
            func.max(HyperliquidExchangeAction.created_at).label("last_ts"),
        ).filter(HyperliquidExchangeAction.created_at >= cutoff)

        if account_id is not None:
            query = query.filter(HyperliquidExchangeAction.account_id == account_id)

        rows = query.group_by(HyperliquidExchangeAction.action_type).all()
        total_actions = sum(row.count for row in rows)
        latest_event = max((row.last_ts for row in rows if row.last_ts), default=None)

        summary = {
            "window_minutes": window_minutes,
            "account_id": account_id,
            "total_actions": total_actions,
            "generated_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "latest_action_at": latest_event.isoformat().replace("+00:00", "Z") if latest_event else None,
            "by_action": [
                {
                    "action_type": row.action_type,
                    "count": row.count,
                    "errors": int(row.errors or 0),
                    "last_occurrence": row.last_ts.isoformat().replace("+00:00", "Z") if row.last_ts else None,
                }
                for row in rows
            ],
        }
        return summary
    except Exception as err:
        logger.error(f"Failed to summarize Hyperliquid actions: {err}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to summarize Hyperliquid actions")


@router.get("/accounts/{account_id}/rate-limit")
async def get_account_rate_limit(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Get API request rate limit status for Hyperliquid account

    Returns the address-based request quota information including:
    - Cumulative trading volume
    - Requests used vs cap
    - Remaining quota
    - Over-limit status

    This helps users understand if they need to increase trading volume
    to avoid "Too many requests" errors when placing orders.

    Args:
        account_id: Account ID
        db: Database session

    Returns:
        Rate limit status with usage metrics

    Raises:
        HTTPException: If account not found or Hyperliquid not enabled
    """
    try:
        # Get Hyperliquid client for this account
        client = get_hyperliquid_client(db, account_id)

        if not client:
            raise HTTPException(
                status_code=400,
                detail="Hyperliquid trading is not enabled for this account"
            )

        # Query rate limit status
        rate_limit = client.get_user_rate_limit(db)

        return {
            'success': True,
            'accountId': account_id,
            'rateLimit': rate_limit
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get rate limit for account {account_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query rate limit: {str(e)}"
        )


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
            'test': '/api/hyperliquid/accounts/{id}/test-connection',
            'wallet': '/api/hyperliquid/accounts/{id}/wallet'
        }
    }


# ========== Wallet Management API (New Multi-Wallet Architecture) ==========

class WalletConfigRequest(BaseModel):
    """Request model for wallet configuration"""
    private_key: str = Field(..., min_length=64, max_length=66, description="Hyperliquid private key (0x...)", alias="privateKey")
    max_leverage: int = Field(3, ge=1, le=50, description="Maximum allowed leverage", alias="maxLeverage")
    default_leverage: int = Field(1, ge=1, le=50, description="Default leverage", alias="defaultLeverage")
    environment: str = Field("testnet", description="Trading environment: testnet or mainnet")

    class Config:
        populate_by_name = True


class WalletConfigResponse(BaseModel):
    """Response model for wallet configuration"""
    success: bool
    wallet_id: Optional[int] = Field(None, alias="walletId")
    wallet_address: Optional[str] = Field(None, alias="walletAddress")
    message: str

    class Config:
        populate_by_name = True


@router.get("/accounts/{account_id}/wallet")
async def get_account_wallet(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Get wallet configurations for an AI Trader account (both testnet and mainnet)

    Returns both testnet and mainnet wallet configurations with balance information.
    """
    from database.models import HyperliquidWallet, Account
    from services.hyperliquid_environment import get_global_trading_mode

    try:
        # Check if account exists
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Get all wallets for this account (testnet and mainnet)
        wallets = db.query(HyperliquidWallet).filter(
            HyperliquidWallet.account_id == account_id
        ).all()

        # Organize wallets by environment
        testnet_wallet = None
        mainnet_wallet = None

        for wallet in wallets:
            wallet_data = {
                'id': wallet.id,
                'walletAddress': wallet.wallet_address,
                'maxLeverage': wallet.max_leverage,
                'defaultLeverage': wallet.default_leverage,
                'isActive': wallet.is_active == "true",
                'createdAt': wallet.created_at.isoformat() if wallet.created_at else None,
                'updatedAt': wallet.updated_at.isoformat() if wallet.updated_at else None,
                'environment': wallet.environment
            }

            # Try to get balance for this specific wallet
            try:
                # Use override_environment to get client for this wallet's environment
                client = get_hyperliquid_client(db, account_id, override_environment=wallet.environment)
                account_state = client.get_account_state(db)
                wallet_data['balance'] = {
                    'totalEquity': float(account_state.get('total_equity', 0)),
                    'availableBalance': float(account_state.get('available_balance', 0)),
                    'marginUsagePercent': float(account_state.get('margin_usage_percent', 0))
                }
            except Exception as e:
                logger.warning(f"Failed to fetch balance for {wallet.environment} wallet: {e}")
                wallet_data['balance'] = None

            if wallet.environment == 'testnet':
                testnet_wallet = wallet_data
            elif wallet.environment == 'mainnet':
                mainnet_wallet = wallet_data

        # Get global trading mode
        trading_mode = get_global_trading_mode(db)

        return {
            'success': True,
            'configured': testnet_wallet is not None or mainnet_wallet is not None,
            'accountId': account_id,
            'accountName': account.name,
            'testnetWallet': testnet_wallet,
            'mainnetWallet': mainnet_wallet,
            'globalTradingMode': trading_mode
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get wallets for account {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get wallet configuration: {str(e)}")


@router.post("/accounts/{account_id}/wallet")
async def configure_account_wallet(
    account_id: int,
    request: WalletConfigRequest,
    db: Session = Depends(get_db)
):
    """
    Configure or update wallet for an AI Trader account

    Creates a new wallet record or updates existing one for the specified environment.
    The private key will be encrypted before storage.
    """
    from database.models import HyperliquidWallet, Account
    from utils.encryption import encrypt_private_key
    from eth_account import Account as EthAccount

    try:
        # Validate environment
        if request.environment not in ['testnet', 'mainnet']:
            raise HTTPException(status_code=400, detail="Environment must be 'testnet' or 'mainnet'")

        # Check if account exists
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Validate and parse private key
        private_key = request.private_key.strip()
        if private_key.startswith('0x'):
            private_key = private_key[2:]

        if len(private_key) != 64:
            raise HTTPException(
                status_code=400,
                detail="Invalid private key format. Must be 64 hex characters (with or without 0x prefix)"
            )

        # Parse wallet address from private key
        try:
            eth_account = EthAccount.from_key('0x' + private_key)
            wallet_address = eth_account.address
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid private key: {str(e)}")

        # Encrypt private key
        try:
            encrypted_key = encrypt_private_key('0x' + private_key)
        except Exception as e:
            logger.error(f"Failed to encrypt private key: {e}")
            raise HTTPException(status_code=500, detail="Failed to encrypt private key")

        # Check if wallet already exists for this account and environment
        existing_wallet = db.query(HyperliquidWallet).filter(
            HyperliquidWallet.account_id == account_id,
            HyperliquidWallet.environment == request.environment
        ).first()

        if existing_wallet:
            # Update existing wallet
            existing_wallet.private_key_encrypted = encrypted_key
            existing_wallet.wallet_address = wallet_address
            existing_wallet.max_leverage = request.max_leverage
            existing_wallet.default_leverage = request.default_leverage
            existing_wallet.is_active = "true"

            db.commit()
            db.refresh(existing_wallet)

            logger.info(f"Updated {request.environment} wallet for account {account.name} (ID: {account_id}), address: {wallet_address}")

            return WalletConfigResponse(
                success=True,
                wallet_id=existing_wallet.id,
                wallet_address=wallet_address,
                message=f"{request.environment.capitalize()} wallet updated for {account.name}"
            )
        else:
            # Create new wallet
            new_wallet = HyperliquidWallet(
                account_id=account_id,
                environment=request.environment,
                private_key_encrypted=encrypted_key,
                wallet_address=wallet_address,
                max_leverage=request.max_leverage,
                default_leverage=request.default_leverage,
                is_active="true"
            )

            db.add(new_wallet)
            db.commit()
            db.refresh(new_wallet)

            logger.info(f"Created {request.environment} wallet for account {account.name} (ID: {account_id}), address: {wallet_address}")

            return WalletConfigResponse(
                success=True,
                wallet_id=new_wallet.id,
                wallet_address=wallet_address,
                message=f"{request.environment.capitalize()} wallet configured for {account.name}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to configure wallet for account {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to configure wallet: {str(e)}")


@router.delete("/accounts/{account_id}/wallet")
async def delete_account_wallet(
    account_id: int,
    environment: str = Query(..., pattern="^(testnet|mainnet)$", description="Environment to delete (testnet or mainnet)"),
    db: Session = Depends(get_db)
):
    """
    Delete wallet configuration for a specific environment

    Deletes the testnet or mainnet wallet for an AI Trader account.
    The other wallet (if exists) will remain configured.

    Query Parameters:
    - environment: Which wallet to delete ('testnet' or 'mainnet')
    """
    from database.models import HyperliquidWallet, Account

    try:
        # Check if account exists
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Find wallet for specified environment
        wallet = db.query(HyperliquidWallet).filter(
            HyperliquidWallet.account_id == account_id,
            HyperliquidWallet.environment == environment
        ).first()

        if not wallet:
            raise HTTPException(
                status_code=404,
                detail=f"No {environment} wallet configured for account {account_id}"
            )

        # Delete wallet
        wallet_address = wallet.wallet_address
        db.delete(wallet)
        db.commit()

        logger.warning(
            f"Deleted {environment} wallet ({wallet_address}) for account {account.name} (ID: {account_id})"
        )

        return {
            'success': True,
            'accountId': account_id,
            'accountName': account.name,
            'environment': environment,
            'message': f'{environment.capitalize()} wallet deleted'
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete {environment} wallet for account {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete wallet: {str(e)}")


@router.post("/accounts/{account_id}/wallet/test")
async def test_wallet_connection(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Test wallet connection to Hyperliquid

    Validates that the wallet can connect to the exchange and fetch account state.
    Uses global trading_mode to determine which network to test.
    """
    from database.models import Account
    from services.hyperliquid_environment import get_global_trading_mode

    try:
        # Check if account exists
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Get global trading mode
        trading_mode = get_global_trading_mode(db)

        # Try to get client and fetch account state
        try:
            client = get_hyperliquid_client(db, account_id)
            account_state = client.get_account_state(db)

            return {
                'success': True,
                'accountId': account_id,
                'accountName': account.name,
                'environment': trading_mode,
                'walletAddress': client.wallet_address,
                'connection': 'successful',
                'accountState': {
                    'totalEquity': float(account_state.get('total_equity', 0)),
                    'availableBalance': float(account_state.get('available_balance', 0)),
                    'marginUsage': float(account_state.get('margin_usage_percent', 0))
                }
            }

        except ValueError as e:
            # Wallet not configured
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            # Connection or API error
            return {
                'success': False,
                'accountId': account_id,
                'accountName': account.name,
                'environment': trading_mode,
                'connection': 'failed',
                'error': str(e)
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test wallet connection for account {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to test connection: {str(e)}")


# ========== Global Trading Mode Management ==========

class TradingModeRequest(BaseModel):
    """Request model for trading mode update"""
    mode: str = Field(..., pattern="^(testnet|mainnet)$", description="Trading environment mode")


@router.get("/trading-mode")
async def get_trading_mode(db: Session = Depends(get_db)):
    """
    Get global Hyperliquid trading mode

    Returns the current trading environment (testnet or mainnet) that all AI Traders use.
    """
    from services.hyperliquid_environment import get_global_trading_mode

    try:
        mode = get_global_trading_mode(db)

        return {
            'success': True,
            'mode': mode,
            'description': 'Testnet (paper trading)' if mode == 'testnet' else 'Mainnet (real funds)'
        }

    except Exception as e:
        logger.error(f"Failed to get trading mode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get trading mode: {str(e)}")


@router.post("/trading-mode")
async def set_trading_mode(
    request: TradingModeRequest,
    db: Session = Depends(get_db)
):
    """
    Set global Hyperliquid trading mode

    WARNING: Switching to mainnet will use real funds for all AI Traders.
    This change affects all active AI Traders immediately.
    """
    from database.models import SystemConfig

    try:
        # Check if config exists
        config = db.query(SystemConfig).filter(
            SystemConfig.key == "hyperliquid_trading_mode"
        ).first()

        old_mode = config.value if config else "testnet"
        new_mode = request.mode

        if old_mode == new_mode:
            return {
                'success': True,
                'mode': new_mode,
                'changed': False,
                'message': f'Trading mode already set to {new_mode}'
            }

        # Update or create config
        if config:
            config.value = new_mode
        else:
            config = SystemConfig(
                key="hyperliquid_trading_mode",
                value=new_mode,
                description="Global Hyperliquid trading environment: 'testnet' or 'mainnet'"
            )
            db.add(config)

        db.commit()

        logger.warning(f"GLOBAL TRADING MODE CHANGED: {old_mode} -> {new_mode}")

        # Clear all Hyperliquid caches when environment changes
        # This ensures fresh data is fetched from the new environment
        from services.hyperliquid_cache import clear_all_caches
        clear_all_caches()
        logger.info("Cleared all Hyperliquid caches after trading mode switch")

        return {
            'success': True,
            'mode': new_mode,
            'changed': True,
            'oldMode': old_mode,
            'message': f'Trading mode switched from {old_mode} to {new_mode}'
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to set trading mode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set trading mode: {str(e)}")


@router.get("/wallets/all")
async def get_all_wallets(db: Session = Depends(get_db)):
    """
    Get all Hyperliquid wallets (both testnet and mainnet) across all AI Trader accounts

    Used by the Trade page wallet selector to display all available wallets
    regardless of the current global trading mode.

    Returns:
        List of wallet objects with account information, sorted by account name and environment
    """
    from database.models import HyperliquidWallet, Account

    try:
        wallets = db.query(
            HyperliquidWallet.id.label("wallet_id"),
            HyperliquidWallet.account_id,
            HyperliquidWallet.wallet_address,
            HyperliquidWallet.environment,
            HyperliquidWallet.is_active,
            HyperliquidWallet.max_leverage,
            HyperliquidWallet.default_leverage,
            Account.name.label("account_name"),
            Account.model
        ).join(
            Account, HyperliquidWallet.account_id == Account.id
        ).filter(
            Account.is_active == "true"
        ).order_by(
            Account.name.asc(),
            HyperliquidWallet.environment.asc()
        ).all()

        return [
            {
                "wallet_id": w.wallet_id,
                "account_id": w.account_id,
                "account_name": w.account_name,
                "model": w.model,
                "wallet_address": w.wallet_address,
                "environment": w.environment,
                "is_active": w.is_active == "true",
                "max_leverage": w.max_leverage,
                "default_leverage": w.default_leverage
            }
            for w in wallets
        ]

    except Exception as e:
        logger.error(f"Failed to get all wallets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get wallets: {str(e)}")

