"""
Account and Asset Curve API Routes (Cleaned)
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging
import time

from database.connection import SessionLocal
from database.models import Account, Position, Trade, CryptoPrice, AccountAssetSnapshot, HyperliquidWallet, AccountPromptBinding
from services.asset_curve_calculator import invalidate_asset_curve_cache
from services.ai_decision_service import (
    build_chat_completion_endpoints,
    build_llm_headers,
    detect_api_format,
    is_new_openai_model,
    is_reasoning_model,
    _extract_text_from_message,
)
from schemas.account import StrategyConfig, StrategyConfigUpdate
from repositories.strategy_repo import get_strategy_by_account, upsert_strategy
from services.trading_strategy import hyper_strategy_manager
from services.hyperliquid_cache import get_cached_account_state
from services.entity_deletion_service import delete_trader
from utils.runtime_diagnostics import get_current_thread_count, log_hot_path_delta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["account"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _normalize_bool(value, default=True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "on"}
    return bool(value)


def _serialize_strategy(account: Account, strategy, db: Session = None) -> StrategyConfig:
    """Convert database strategy config to API schema."""
    from repositories.strategy_repo import parse_signal_pool_ids

    last_trigger = strategy.last_trigger_at
    if last_trigger:
        if last_trigger.tzinfo is None:
            last_iso = last_trigger.replace(tzinfo=timezone.utc).isoformat()
        else:
            last_iso = last_trigger.astimezone(timezone.utc).isoformat()
    else:
        last_iso = None

    # Get signal pool IDs (new format with fallback)
    pool_ids = parse_signal_pool_ids(strategy)

    # Get signal pool names if bound
    signal_pool_name = None  # Deprecated: for backward compatibility
    signal_pool_names = []
    if pool_ids and db:
        from sqlalchemy import text
        result = db.execute(
            text("SELECT id, pool_name FROM signal_pools WHERE id = ANY(:ids) AND (is_deleted IS NULL OR is_deleted = false)"),
            {"ids": pool_ids}
        ).fetchall()
        pool_name_map = {row[0]: row[1] for row in result}
        signal_pool_names = [pool_name_map.get(pid) for pid in pool_ids if pool_name_map.get(pid)]
        # Backward compatibility: use first pool name
        signal_pool_name = signal_pool_names[0] if signal_pool_names else None

    # Check if prompt binding exists when triggers are enabled
    warning = None
    has_trigger_enabled = strategy.scheduled_trigger_enabled or pool_ids
    if has_trigger_enabled and db:
        prompt_binding = db.query(AccountPromptBinding).filter(
            AccountPromptBinding.account_id == account.id,
            AccountPromptBinding.is_deleted != True
        ).first()
        if not prompt_binding:
            warning = "No prompt template bound. Scheduled and signal triggers will not execute until a prompt is configured."

    return StrategyConfig(
        trigger_mode="unified",
        interval_seconds=strategy.trigger_interval or 150,
        tick_batch_size=1,
        enabled=(strategy.enabled == "true" and account.auto_trading_enabled == "true"),
        scheduled_trigger_enabled=strategy.scheduled_trigger_enabled if strategy.scheduled_trigger_enabled is not None else True,
        exchange=getattr(strategy, 'exchange', None) or "hyperliquid",
        execution_mode=getattr(strategy, "execution_mode", None) or "real",
        last_trigger_at=last_iso,
        price_threshold=strategy.price_threshold or 1.0,
        signal_pool_id=pool_ids[0] if pool_ids else None,  # Deprecated
        signal_pool_ids=pool_ids if pool_ids else None,
        signal_pool_name=signal_pool_name,  # Deprecated
        signal_pool_names=signal_pool_names if signal_pool_names else None,
        warning=warning,
    )


@router.get("/list")
def list_all_accounts(include_hidden: bool = False, db: Session = Depends(get_db)):
    """Get all active accounts (for paper trading demo)

    Args:
        include_hidden: If True, include accounts with show_on_dashboard=False.
                       Default False (only show visible accounts for Dashboard).
    """
    start_threads = get_current_thread_count()
    start_time = time.monotonic()
    try:
        from database.models import User
        from eth_account import Account as EthAccount
        from services.hyperliquid_environment import decrypt_private_key

        query = db.query(Account).filter(Account.is_active == "true", Account.is_deleted != True)
        if not include_hidden:
            query = query.filter(Account.show_on_dashboard == True)
        accounts = query.all()

        result = []
        for account in accounts:
            user = db.query(User).filter(User.id == account.user_id).first()

            # Check if this is a Hyperliquid account
            hyperliquid_environment = getattr(account, "hyperliquid_environment", None)

            current_cash = float(account.current_cash)
            frozen_cash = float(account.frozen_cash)

            # For Hyperliquid accounts, fetch real-time balance
            if hyperliquid_environment in ["testnet", "mainnet"]:
                try:
                    cached_entry = get_cached_account_state(account.id, hyperliquid_environment)
                    if cached_entry:
                        account_state = cached_entry["data"]
                    else:
                        from services.hyperliquid_environment import get_hyperliquid_client

                        client = get_hyperliquid_client(db, account.id)
                        account_state = client.get_account_state(db)

                    current_cash = float(account_state.get('available_balance', current_cash))
                    frozen_cash = float(account_state.get('used_margin', frozen_cash))
                    logger.debug(
                        f"Account {account.name}: Using cached Hyperliquid balance data "
                        f"(available=${current_cash:.2f}, used_margin=${frozen_cash:.2f})"
                    )
                except Exception:
                    pass  # No wallet configured or fetch failed — use database values

            # Derive wallet_address for mainnet accounts
            # Check both old architecture (accounts table) and new architecture (hyperliquid_wallets table)
            wallet_address = None
            has_mainnet_wallet = False

            # First check new multi-wallet architecture (hyperliquid_wallets table)
            mainnet_wallet = db.query(HyperliquidWallet).filter(
                HyperliquidWallet.account_id == account.id,
                HyperliquidWallet.environment == "mainnet"
            ).first()

            if mainnet_wallet and mainnet_wallet.private_key_encrypted:
                has_mainnet_wallet = True
                try:
                    decrypted_key = decrypt_private_key(mainnet_wallet.private_key_encrypted)
                    if decrypted_key:
                        if not decrypted_key.startswith('0x'):
                            decrypted_key = '0x' + decrypted_key
                        eth_account = EthAccount.from_key(decrypted_key)
                        wallet_address = eth_account.address.lower()
                except Exception as wallet_err:
                    logger.warning(
                        f"Failed to derive wallet address from wallets table for account {account.id}: {wallet_err}"
                    )

            # Fallback to old architecture (accounts table field)
            if not has_mainnet_wallet:
                mainnet_private_key = getattr(account, "hyperliquid_mainnet_private_key", None)
                if mainnet_private_key:
                    has_mainnet_wallet = True
                    try:
                        decrypted_key = decrypt_private_key(mainnet_private_key)
                        if decrypted_key:
                            if not decrypted_key.startswith('0x'):
                                decrypted_key = '0x' + decrypted_key
                            eth_account = EthAccount.from_key(decrypted_key)
                            wallet_address = eth_account.address.lower()
                    except Exception as wallet_err:
                        logger.warning(
                            f"Failed to derive wallet address for account {account.id}: {wallet_err}"
                        )

            result.append({
                "id": account.id,
                "user_id": account.user_id,
                "username": user.username if user else "unknown",
                "name": account.name,
                "account_type": account.account_type,
                "initial_capital": float(account.initial_capital),
                "current_cash": current_cash,
                "frozen_cash": frozen_cash,
                "model": account.model,
                "base_url": account.base_url,
                "api_key": account.api_key,
                "is_active": account.is_active == "true",
                "auto_trading_enabled": account.auto_trading_enabled == "true",
                "wallet_address": wallet_address,
                "has_mainnet_wallet": has_mainnet_wallet,
                "show_on_dashboard": account.show_on_dashboard,
                "avatar_preset_id": account.avatar_preset_id
            })

        return result
    except Exception as e:
        logger.error(f"Failed to list accounts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list accounts: {str(e)}")
    finally:
        log_hot_path_delta(
            logger,
            "account:list",
            "/api/account/list",
            start_threads,
            start_time,
            include_hidden=include_hidden,
        )


@router.get("/{account_id}/overview")
def get_specific_account_overview(account_id: int, db: Session = Depends(get_db)):
    """Get overview for a specific account"""
    try:
        # Get the specific account
        account = db.query(Account).filter(
            Account.id == account_id,
            Account.is_active == "true",
            Account.is_deleted != True
        ).first()
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # Calculate positions value for this specific account
        from services.asset_calculator import calc_positions_value
        positions_value = float(calc_positions_value(db, account.id) or 0.0)
        
        # Count positions and pending orders for this account
        positions_count = db.query(Position).filter(
            Position.account_id == account.id,
            Position.quantity > 0
        ).count()
        
        from database.models import Order
        pending_orders = db.query(Order).filter(
            Order.account_id == account.id,
            Order.status == "PENDING"
        ).count()
        
        return {
            "account": {
                "id": account.id,
                "name": account.name,
                "account_type": account.account_type,
                "current_cash": float(account.current_cash),
                "frozen_cash": float(account.frozen_cash),
            },
            "total_assets": positions_value + float(account.current_cash),
            "positions_value": positions_value,
            "positions_count": positions_count,
            "pending_orders": pending_orders,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get account {account_id} overview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get account overview: {str(e)}")


@router.get("/{account_id}/strategy", response_model=StrategyConfig)
def get_account_strategy(account_id: int, db: Session = Depends(get_db)):
    """Fetch AI trading strategy configuration for an account."""
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.is_active == "true", Account.is_deleted != True)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    strategy = get_strategy_by_account(db, account_id)
    if not strategy:
        # Check if account has a Binance wallet to determine default exchange
        from database.models import BinanceWallet
        has_binance = db.query(BinanceWallet).filter(
            BinanceWallet.account_id == account_id,
            BinanceWallet.is_active == "true"
        ).first()
        default_exchange = "binance" if has_binance else "hyperliquid"
        strategy = upsert_strategy(
            db,
            account_id=account_id,
            price_threshold=1.0,
            trigger_interval=150,
            enabled=(account.auto_trading_enabled == "true"),
            exchange=default_exchange,
        )
        # Reload strategies after creation
        hyper_strategy_manager._load_strategies()

    return _serialize_strategy(account, strategy, db)


@router.put("/{account_id}/strategy", response_model=StrategyConfig)
def update_account_strategy(
    account_id: int,
    payload: StrategyConfigUpdate,
    db: Session = Depends(get_db),
):
    """Update AI trading strategy configuration for an account."""
    print(f"Backend received payload for account {account_id}: {payload}")
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.is_active == "true", Account.is_deleted != True)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Validate price threshold
    if hasattr(payload, 'price_threshold') and payload.price_threshold is not None:
        if payload.price_threshold <= 0 or payload.price_threshold > 10:
            raise HTTPException(
                status_code=400,
                detail="price_threshold must be between 0.1 and 10.0",
            )
        price_threshold = payload.price_threshold
    else:
        price_threshold = 1.0

    # Validate trigger interval
    if hasattr(payload, 'interval_seconds') and payload.interval_seconds is not None:
        if payload.interval_seconds < 30:
            raise HTTPException(
                status_code=400,
                detail="trigger_interval must be >= 30 seconds",
            )
        trigger_interval = payload.interval_seconds
    else:
        trigger_interval = 150

    strategy = upsert_strategy(
        db,
        account_id=account_id,
        trigger_mode=payload.trigger_mode,
        price_threshold=price_threshold,
        trigger_interval=trigger_interval,
        enabled=payload.enabled,
        scheduled_trigger_enabled=payload.scheduled_trigger_enabled,
        signal_pool_id=payload.signal_pool_id,  # Deprecated: for backward compatibility
        signal_pool_ids=payload.signal_pool_ids,  # New: list of pool IDs
        exchange=payload.exchange,
        execution_mode=payload.execution_mode,
    )

    # Reload strategies after update
    hyper_strategy_manager._load_strategies()
    return _serialize_strategy(account, strategy, db)


@router.get("/overview")
def get_account_overview(db: Session = Depends(get_db)):
    """Get overview for the default account (for paper trading demo)"""
    try:
        # Get the first active account (default account)
        account = db.query(Account).filter(Account.is_active == "true", Account.is_deleted != True).first()
        
        if not account:
            raise HTTPException(status_code=404, detail="No active account found")
        
        # Calculate positions value
        from services.asset_calculator import calc_positions_value
        positions_value = float(calc_positions_value(db, account.id) or 0.0)
        
        # Count positions and pending orders
        positions_count = db.query(Position).filter(
            Position.account_id == account.id,
            Position.quantity > 0
        ).count()
        
        from database.models import Order
        pending_orders = db.query(Order).filter(
            Order.account_id == account.id,
            Order.status == "PENDING"
        ).count()
        
        return {
            "account": {
                "id": account.id,
                "name": account.name,
                "account_type": account.account_type,
                "current_cash": float(account.current_cash),
                "frozen_cash": float(account.frozen_cash),
            },
            "portfolio": {
                "total_assets": positions_value + float(account.current_cash),
                "positions_value": positions_value,
                "positions_count": positions_count,
                "pending_orders": pending_orders,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get overview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get overview: {str(e)}")


@router.post("/")
def create_new_account(payload: dict, db: Session = Depends(get_db)):
    """Create a new account for the default user (for paper trading demo)"""
    try:
        from database.models import User
        
        # Get the default user (or first user)
        user = db.query(User).filter(User.username == "default").first()
        if not user:
            user = db.query(User).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="No user found")
        
        # Validate required fields
        if "name" not in payload or not payload["name"]:
            raise HTTPException(status_code=400, detail="Account name is required")
        
        # Create new account
        auto_trading_enabled = _normalize_bool(payload.get("auto_trading_enabled", True))
        auto_trading_value = "true" if auto_trading_enabled else "false"

        import random
        avatar_preset_id = random.randint(1, 12)

        new_account = Account(
            user_id=user.id,
            version="v1",
            name=payload["name"],
            account_type=payload.get("account_type", "AI"),
            model=payload.get("model", "gpt-4-turbo"),
            base_url=payload.get("base_url", "https://api.openai.com/v1"),
            api_key=payload.get("api_key", ""),
            initial_capital=float(payload.get("initial_capital", 10000.0)),
            current_cash=float(payload.get("initial_capital", 10000.0)),
            frozen_cash=0.0,
            is_active="true",
            auto_trading_enabled=auto_trading_value,
            avatar_preset_id=avatar_preset_id
        )
        
        db.add(new_account)
        db.commit()
        db.refresh(new_account)

        # Record initial snapshot so asset curves start at the configured capital
        try:
            now_utc = datetime.now(timezone.utc)
            initial_total = Decimal(str(new_account.initial_capital))
            snapshot = AccountAssetSnapshot(
                account_id=new_account.id,
                total_assets=initial_total,
                cash=Decimal(str(new_account.current_cash)),
                positions_value=Decimal("0"),
                event_time=now_utc,
                trigger_symbol=None,
                trigger_market="CRYPTO",
            )
            db.add(snapshot)
            db.commit()
            invalidate_asset_curve_cache()
        except Exception as snapshot_err:
            db.rollback()
            logger.warning(
                "Failed to create initial account snapshot for account %s: %s",
                new_account.id,
                snapshot_err,
            )

        # Reset auto trading job after creating new account (async in background to avoid blocking response)
        import threading
        def reset_job_async():
            try:
                from services.scheduler import reset_auto_trading_job
                reset_auto_trading_job()
                logger.info("Auto trading job reset successfully after account creation")
            except Exception as e:
                logger.warning(f"Failed to reset auto trading job: {e}")

        # Run reset in background thread to not block API response
        reset_thread = threading.Thread(target=reset_job_async, daemon=True)
        reset_thread.start()
        logger.info("Auto trading job reset initiated in background")

        return {
            "id": new_account.id,
            "user_id": new_account.user_id,
            "username": user.username,
            "name": new_account.name,
            "account_type": new_account.account_type,
            "initial_capital": float(new_account.initial_capital),
            "current_cash": float(new_account.current_cash),
            "frozen_cash": float(new_account.frozen_cash),
            "model": new_account.model,
            "base_url": new_account.base_url,
            "api_key": new_account.api_key,
            "is_active": new_account.is_active == "true",
            "auto_trading_enabled": new_account.auto_trading_enabled == "true",
            "avatar_preset_id": new_account.avatar_preset_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create account: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create account: {str(e)}")


@router.put("/{account_id}")
def update_account_settings(account_id: int, payload: dict, db: Session = Depends(get_db)):
    """Update account settings (for paper trading demo)"""
    try:
        logger.info(f"Updating account {account_id} with payload: {payload}")

        account = db.query(Account).filter(
            Account.id == account_id,
            Account.is_active == "true",
            Account.is_deleted != True
        ).first()

        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # Update fields if provided (allow empty strings for api_key and base_url)
        if "name" in payload:
            if payload["name"]:
                account.name = payload["name"]
                logger.info(f"Updated name to: {payload['name']}")
            else:
                raise HTTPException(status_code=400, detail="Account name cannot be empty")
        
        if "model" in payload:
            account.model = payload["model"] if payload["model"] else None
            logger.info(f"Updated model to: {account.model}")
        
        if "base_url" in payload:
            account.base_url = payload["base_url"]
            logger.info(f"Updated base_url to: {account.base_url}")
        
        if "api_key" in payload:
            account.api_key = payload["api_key"]
            logger.info(f"Updated api_key (length: {len(payload['api_key']) if payload['api_key'] else 0})")

        if "auto_trading_enabled" in payload:
            auto_trading_enabled = _normalize_bool(payload.get("auto_trading_enabled"))
            account.auto_trading_enabled = "true" if auto_trading_enabled else "false"
            logger.info(f"Updated auto_trading_enabled to: {account.auto_trading_enabled}")
        
        db.commit()
        db.refresh(account)
        logger.info(f"Account {account_id} updated successfully")

        # Reset auto trading job after account update (async in background to avoid blocking response)
        import threading
        def reset_job_async():
            try:
                from services.scheduler import reset_auto_trading_job
                reset_auto_trading_job()
                logger.info("Auto trading job reset successfully after account update")
            except Exception as e:
                logger.warning(f"Failed to reset auto trading job: {e}")

        # Run reset in background thread to not block API response
        reset_thread = threading.Thread(target=reset_job_async, daemon=True)
        reset_thread.start()
        logger.info("Auto trading job reset initiated in background")

        from database.models import User
        user = db.query(User).filter(User.id == account.user_id).first()
        
        return {
            "id": account.id,
            "user_id": account.user_id,
            "username": user.username if user else "unknown",
            "name": account.name,
            "account_type": account.account_type,
            "initial_capital": float(account.initial_capital),
            "current_cash": float(account.current_cash),
            "frozen_cash": float(account.frozen_cash),
            "model": account.model,
            "base_url": account.base_url,
            "api_key": account.api_key,
            "is_active": account.is_active == "true",
            "auto_trading_enabled": account.auto_trading_enabled == "true"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update account: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update account: {str(e)}")


@router.delete("/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """Soft-delete an AI Trader with dependency checking."""
    result = delete_trader(db, account_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Trader not found"))
    return result


@router.get("/asset-curve")
def get_asset_curve(
    timeframe: str = "5m",
    trading_mode: str = "testnet",
    environment: Optional[str] = None,
    wallet_address: Optional[str] = None,
    account_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get asset curve data for all accounts (or specific account) with specified timeframe and trading mode"""
    start_threads = get_current_thread_count()
    start_time = time.monotonic()
    try:
        from services.asset_curve_calculator import get_all_asset_curves_data_new
        data = get_all_asset_curves_data_new(
            db,
            timeframe=timeframe,
            trading_mode=trading_mode,
            environment=environment,
            wallet_address=wallet_address,
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
        )
        return data
    except Exception as e:
        logger.error(f"Error fetching asset curve data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch asset curve data: {str(e)}")
    finally:
        log_hot_path_delta(
            logger,
            "account:asset-curve",
            "/api/account/asset-curve",
            start_threads,
            start_time,
            timeframe=timeframe,
            trading_mode=trading_mode,
            environment=environment,
            account_id=account_id,
        )


@router.get("/asset-curve/timeframe")
def get_asset_curve_by_timeframe(
    timeframe: str = "1d",
    db: Session = Depends(get_db)
):
    """Get asset curve data for all accounts within a specified timeframe (20 data points)
    
    Args:
        timeframe: Time period, options: 5m, 1h, 1d
    """
    try:
        # Validate timeframe
        valid_timeframes = ["5m", "1h", "1d"]
        if timeframe not in valid_timeframes:
            raise HTTPException(status_code=400, detail=f"Invalid timeframe. Must be one of: {', '.join(valid_timeframes)}")
        
        # Map timeframe to period for kline data
        timeframe_map = {
            "5m": "5m",
            "1h": "1h",
            "1d": "1d"
        }
        period = timeframe_map[timeframe]
        
        # Get all active accounts
        accounts = db.query(Account).filter(Account.is_active == "true", Account.is_deleted != True).all()
        if not accounts:
            return []
        
        # Get all unique symbols from all account positions and trades
        symbols_query = db.query(Trade.symbol, Trade.market).distinct().all()
        unique_symbols = set()
        for symbol, market in symbols_query:
            unique_symbols.add((symbol, market))
        
        if not unique_symbols:
            # No trades yet, return initial capital for all accounts
            now = datetime.now()
            return [{
                "timestamp": int(now.timestamp()),
                "datetime_str": now.isoformat(),
                "user_id": account.user_id,
                "username": account.name,
                "total_assets": float(account.initial_capital),
                "cash": float(account.current_cash),
                "positions_value": 0.0,
            } for account in accounts]
        
        # Fetch kline data for all symbols (20 points)
        from services.market_data import get_kline_data
        
        symbol_klines = {}
        for symbol, market in unique_symbols:
            try:
                klines = get_kline_data(symbol, market, period, 20)
                if klines:
                    symbol_klines[(symbol, market)] = klines
                    logger.info(f"Fetched {len(klines)} klines for {symbol}.{market}")
            except Exception as e:
                logger.warning(f"Failed to fetch klines for {symbol}.{market}: {e}")
        
        if not symbol_klines:
            raise HTTPException(status_code=500, detail="Failed to fetch market data")
        
        # Get timestamps from the first symbol's klines
        first_klines = next(iter(symbol_klines.values()))
        timestamps = [k['timestamp'] for k in first_klines]
        
        # Calculate asset value for each account at each timestamp
        result = []
        for account in accounts:
            account_id = account.id
            
            # Get all trades for this account
            trades = db.query(Trade).filter(
                Trade.account_id == account_id
            ).order_by(Trade.trade_time.asc()).all()
            
            if not trades:
                # No trades, return initial capital at all timestamps
                for i, ts in enumerate(timestamps):
                    result.append({
                        "timestamp": ts,
                        "datetime_str": first_klines[i]['datetime_str'],
                        "user_id": account.user_id,
                        "username": account.name,
                        "total_assets": float(account.initial_capital),
                        "cash": float(account.initial_capital),
                        "positions_value": 0.0,
                    })
                continue
            
            # Calculate holdings and cash at each timestamp
            for i, ts in enumerate(timestamps):
                ts_datetime = datetime.fromtimestamp(ts, tz=timezone.utc)
                
                # Calculate cash changes up to this timestamp
                cash_change = 0.0
                position_quantities = {}
                
                for trade in trades:
                    trade_time = trade.trade_time
                    if not trade_time.tzinfo:
                        trade_time = trade_time.replace(tzinfo=timezone.utc)
                    
                    if trade_time <= ts_datetime:
                        # Update cash
                        trade_amount = float(trade.price) * float(trade.quantity) + float(trade.commission)
                        if trade.side == "BUY":
                            cash_change -= trade_amount
                        else:  # SELL
                            cash_change += trade_amount
                        
                        # Update position
                        key = (trade.symbol, trade.market)
                        if key not in position_quantities:
                            position_quantities[key] = 0.0
                        
                        if trade.side == "BUY":
                            position_quantities[key] += float(trade.quantity)
                        else:  # SELL
                            position_quantities[key] -= float(trade.quantity)
                
                current_cash = float(account.initial_capital) + cash_change
                
                # Calculate positions value using prices at this timestamp
                positions_value = 0.0
                for (symbol, market), quantity in position_quantities.items():
                    if quantity > 0 and (symbol, market) in symbol_klines:
                        klines = symbol_klines[(symbol, market)]
                        if i < len(klines):
                            price = klines[i]['close']
                            if price:
                                positions_value += float(price) * quantity
                
                total_assets = current_cash + positions_value
                
                result.append({
                    "timestamp": ts,
                    "datetime_str": first_klines[i]['datetime_str'],
                    "user_id": account.user_id,
                    "username": account.name,
                    "total_assets": total_assets,
                    "cash": current_cash,
                    "positions_value": positions_value,
                })
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get asset curve for timeframe: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get asset curve for timeframe: {str(e)}")


@router.post("/test-llm")
def test_llm_connection(payload: dict):
    """Test LLM connection with provided credentials"""
    try:
        import requests
        import json

        model = payload.get("model", "gpt-3.5-turbo")
        base_url = payload.get("base_url", "https://api.openai.com/v1")
        api_key = payload.get("api_key", "")

        if not api_key:
            return {"success": False, "message": "API key is required"}

        if not base_url:
            return {"success": False, "message": "Base URL is required"}

        # Clean up base_url - ensure it doesn't end with slash
        if base_url.endswith('/'):
            base_url = base_url.rstrip('/')

        # Detect API format from URL
        endpoint, api_format = detect_api_format(base_url)
        if not endpoint:
            return {"success": False, "message": "Invalid base URL"}

        # Test the connection with a simple completion request
        try:
            model_lower = model.lower()
            is_reasoning = is_reasoning_model(model)
            is_o1_series = any(x in model_lower for x in ['o1-preview', 'o1-mini', 'o1-', 'o1'])
            is_new_model = is_new_openai_model(model)

            if api_format == 'anthropic':
                # Anthropic native format
                headers = build_llm_headers(api_format, api_key, endpoint)
                payload_data = {
                    "model": model,
                    "max_tokens": 1024,
                    "messages": [
                        {"role": "user", "content": "Say 'Connection test successful' if you can read this."}
                    ]
                }
            else:
                # OpenAI compatible format
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
                if is_o1_series:
                    payload_data = {
                        "model": model,
                        "messages": [
                            {"role": "user", "content": "Say 'Connection test successful' if you can read this."}
                        ]
                    }
                else:
                    payload_data = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "You are a helpful assistant."},
                            {"role": "user", "content": "Say 'Connection test successful' if you can read this."}
                        ]
                    }

                if not is_reasoning:
                    payload_data["temperature"] = 0

                if is_new_model:
                    payload_data["max_completion_tokens"] = 2000
                else:
                    payload_data["max_tokens"] = 2000

                if 'gpt-5' in model_lower:
                    payload_data["reasoning_effort"] = "low"

            # For Anthropic format, use the detected endpoint directly
            # For OpenAI format, use build_chat_completion_endpoints for fallback support
            if api_format == 'anthropic':
                endpoints_to_try = [endpoint]
            else:
                endpoints_to_try = build_chat_completion_endpoints(base_url, model)
                if not endpoints_to_try:
                    return {"success": False, "message": "Invalid base URL"}

            last_failure_message = "Connection test failed"

            for idx, ep in enumerate(endpoints_to_try):
                try:
                    response = requests.post(
                        ep,
                        headers=headers,
                        json=payload_data,
                        timeout=10.0,
                        verify=False
                    )
                except requests.ConnectionError:
                    last_failure_message = f"Failed to connect to {ep}. Please check the base URL."
                    continue
                except requests.Timeout:
                    last_failure_message = "Request timed out. The LLM service may be unavailable."
                    continue
                except requests.RequestException as req_err:
                    last_failure_message = f"Connection test failed: {str(req_err)}"
                    continue

                # Check response status
                if response.status_code == 200:
                    result = response.json()

                    if api_format == 'anthropic':
                        # Anthropic response format: {"content": [{"type": "text", "text": "..."}], ...}
                        content_list = result.get("content", [])
                        content = ""
                        for item in content_list:
                            if isinstance(item, dict) and item.get("type") == "text":
                                content = item.get("text", "")
                                break
                        if content:
                            logger.info(f"LLM test successful for model {model} at {ep} (Anthropic format)")
                            return {
                                "success": True,
                                "message": f"Connection successful! Model {model} responded correctly (Anthropic API).",
                                "response": content
                            }
                        else:
                            return {"success": False, "message": "Anthropic API responded but with empty content."}
                    else:
                        # OpenAI-compatible response format
                        if "choices" in result and len(result["choices"]) > 0:
                            choice = result["choices"][0]
                            message = choice.get("message", {})
                            finish_reason = choice.get("finish_reason", "")

                            raw_content = message.get("content")
                            content = _extract_text_from_message(raw_content)

                            if not content and is_reasoning:
                                reasoning = _extract_text_from_message(message.get("reasoning"))
                                if reasoning:
                                    logger.info(f"LLM test successful for model {model} at {ep} (reasoning model)")
                                    snippet = reasoning[:100] + "..." if len(reasoning) > 100 else reasoning
                                    return {
                                        "success": True,
                                        "message": f"Connection successful! Model {model} (reasoning model) responded correctly.",
                                        "response": f"[Reasoning: {snippet}]"
                                    }

                            if content:
                                logger.info(f"LLM test successful for model {model} at {ep}")
                                return {
                                    "success": True,
                                    "message": f"Connection successful! Model {model} responded correctly.",
                                    "response": content
                                }

                            logger.warning(f"LLM response has empty content. finish_reason={finish_reason}, full_message={message}")
                            return {
                                "success": False,
                                "message": f"LLM responded but with empty content (finish_reason: {finish_reason}). Try increasing token limit or using a different model."
                            }
                        else:
                            return {"success": False, "message": "Unexpected response format from LLM"}
                elif response.status_code == 401:
                    return {"success": False, "message": "Authentication failed. Please check your API key."}
                elif response.status_code == 403:
                    return {"success": False, "message": "Permission denied. Your API key may not have access to this model."}
                elif response.status_code == 429:
                    return {"success": False, "message": "Rate limit exceeded. Please try again later."}
                elif response.status_code == 404:
                    last_failure_message = f"Model '{model}' not found or endpoint not available."
                    if idx < len(endpoints_to_try) - 1:
                        logger.info(f"Endpoint {ep} returned 404, trying alternative path")
                        continue
                    return {"success": False, "message": last_failure_message}
                else:
                    return {"success": False, "message": f"API returned status {response.status_code}: {response.text}"}

            return {"success": False, "message": last_failure_message}
                
        except requests.ConnectionError:
            return {"success": False, "message": f"Failed to connect to {base_url}. Please check the base URL."}
        except requests.Timeout:
            return {"success": False, "message": "Request timed out. The LLM service may be unavailable."}
        except json.JSONDecodeError:
            return {"success": False, "message": "Invalid JSON response from LLM service."}
        except requests.RequestException as e:
            logger.error(f"LLM test request failed: {e}", exc_info=True)
            return {"success": False, "message": f"Connection test failed: {str(e)}"}
        except Exception as e:
            logger.error(f"LLM test failed: {e}", exc_info=True)
            return {"success": False, "message": f"Connection test failed: {str(e)}"}
            
    except Exception as e:
        logger.error(f"Failed to test LLM connection: {e}", exc_info=True)
        return {"success": False, "message": f"Failed to test LLM connection: {str(e)}"}


@router.post("/{account_id}/trigger-ai-trade")
def trigger_ai_trade(
    account_id: int,
    force_operation: str = None,  # Optional: "buy", "sell", "close", "hold"
    symbol: str = None,  # Optional: specific symbol to trade
    db: Session = Depends(get_db)
):
    """
    Manually trigger AI trading for a specific account.

    Args:
        account_id: The account ID to trigger trading for
        force_operation: Optional operation to force ("buy", "sell", "close", "hold")
        symbol: Optional specific symbol to trade (default: auto-detect from sampling pool)

    Returns:
        Trade execution result
    """
    try:
        from services.trading_commands import place_ai_driven_crypto_order

        # Validate account exists and is active
        account = db.query(Account).filter(Account.id == account_id, Account.is_deleted != True).first()
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        if account.is_active != "true":
            raise HTTPException(status_code=400, detail=f"Account {account.name} is inactive")

        if account.account_type != "AI":
            raise HTTPException(status_code=400, detail=f"Only AI accounts can trigger AI trading")

        logger.info(f"Manually triggering AI trade for account {account.name} (ID: {account_id})")
        if force_operation:
            logger.info(f"  Force operation: {force_operation}")
        if symbol:
            logger.info(f"  Target symbol: {symbol}")

        # If forcing a specific operation, we need to mock the AI decision
        samples = None
        if force_operation:
            # Prepare mock samples to force specific operation
            if force_operation.lower() == "close":
                # For CLOSE operation, we need to find a position to close
                positions = db.query(Position).filter(
                    Position.account_id == account_id,
                    Position.market == "CRYPTO",
                    Position.available_quantity > 0
                ).all()

                if not positions:
                    return {
                        "success": False,
                        "message": "No open positions to close",
                        "account_id": account_id,
                        "account_name": account.name
                    }

                # Use the first available position if symbol not specified
                if not symbol:
                    symbol = positions[0].symbol

                # Mock AI decision for CLOSE operation
                samples = [{
                    "operation": "close",
                    "symbol": symbol,
                    "target_portion_of_balance": 1.0,  # Close 100%
                    "reason": f"Manual CLOSE trigger via API for {account.name}"
                }]

            elif force_operation.lower() in ["buy", "sell"]:
                if not symbol:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Symbol is required when forcing {force_operation} operation"
                    )

                samples = [{
                    "operation": force_operation.lower(),
                    "symbol": symbol,
                    "target_portion_of_balance": 0.2,  # Default 20%
                    "reason": f"Manual {force_operation.upper()} trigger via API for {account.name}"
                }]

            elif force_operation.lower() == "hold":
                samples = [{
                    "operation": "hold",
                    "symbol": symbol or "BTC",
                    "target_portion_of_balance": 0,
                    "reason": f"Manual HOLD trigger via API for {account.name}"
                }]

        # Check if account has Hyperliquid environment configured
        hyperliquid_environment = getattr(account, "hyperliquid_environment", None)

        print(
            f"[DEBUG] Trigger API: account_id={account_id} "
            f"hyperliquid_environment={hyperliquid_environment}"
        )

        # Trigger AI trading based on account configuration
        if hyperliquid_environment in ["testnet", "mainnet"]:
            print(f"[DEBUG] ENTERING HYPERLIQUID BRANCH")
            try:
                from services.trading_commands import place_ai_driven_hyperliquid_order
                print(f"[DEBUG] Successfully imported place_ai_driven_hyperliquid_order")
                print(f"[DEBUG] Calling place_ai_driven_hyperliquid_order for account {account_id}")
                place_ai_driven_hyperliquid_order(
                    account_id=account_id,
                    bypass_auto_trading=True,
                )
                print(f"[DEBUG] place_ai_driven_hyperliquid_order completed for account {account_id}")
            except Exception as hyperliquid_err:
                print(f"[DEBUG] Error in Hyperliquid trading: {hyperliquid_err}")
                logger.error(f"Error in Hyperliquid trading for account {account_id}: {hyperliquid_err}", exc_info=True)
        else:
            place_ai_driven_crypto_order(
                max_ratio=0.2,
                account_id=account_id,
                symbol=symbol,
                samples=samples
            )

        # Check for new trades
        recent_trades = db.query(Trade).filter(
            Trade.account_id == account_id
        ).order_by(Trade.trade_time.desc()).limit(1).all()

        if recent_trades:
            latest_trade = recent_trades[0]
            return {
                "success": True,
                "message": f"AI trading triggered successfully for {account.name}",
                "account_id": account_id,
                "account_name": account.name,
                "trade": {
                    "id": latest_trade.id,
                    "symbol": latest_trade.symbol,
                    "side": latest_trade.side,
                    "quantity": float(latest_trade.quantity),
                    "price": float(latest_trade.price),
                    "trade_time": latest_trade.trade_time.isoformat() if latest_trade.trade_time else None
                }
            }
        else:
            return {
                "success": True,
                "message": f"AI trading triggered for {account.name}, but no trade was executed (AI may have decided to HOLD)",
                "account_id": account_id,
                "account_name": account.name
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger AI trade for account {account_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger AI trade: {str(e)}"
        )


@router.get("/hyperliquid/check-builder-authorization")
def check_builder_authorization(
    wallet_address: str,
    db: Session = Depends(get_db)
):
    """
    Check if a wallet address has authorized the platform's builder fee.

    Args:
        wallet_address: The Hyperliquid wallet address to check

    Returns:
        {
            "authorized": bool,  # True if authorized with sufficient fee
            "max_fee": int,      # Maximum fee approved (in tenths of basis point)
            "required_fee": int  # Required fee by platform (in tenths of basis point)
        }
    """
    try:
        import requests
        from config.settings import HYPERLIQUID_BUILDER_CONFIG

        # Query Hyperliquid API for max builder fee
        response = requests.post(
            "https://api.hyperliquid.xyz/info",
            json={
                "type": "maxBuilderFee",
                "user": wallet_address,
                "builder": HYPERLIQUID_BUILDER_CONFIG.builder_address
            },
            timeout=10
        )

        if response.status_code != 200:
            logger.error(f"Failed to check builder authorization: HTTP {response.status_code}")
            raise HTTPException(
                status_code=500,
                detail="Failed to query Hyperliquid authorization status"
            )

        max_fee = response.json()  # Returns integer (e.g., 30 for 0.03%)
        required_fee = HYPERLIQUID_BUILDER_CONFIG.builder_fee

        return {
            "authorized": max_fee >= required_fee,
            "max_fee": max_fee,
            "required_fee": required_fee,
            "builder_address": HYPERLIQUID_BUILDER_CONFIG.builder_address
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error checking builder authorization: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Network error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error checking builder authorization: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check authorization: {str(e)}"
        )


@router.post("/hyperliquid/approve-builder")
def approve_builder_fee(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Trigger builder fee approval for a Hyperliquid account.

    This endpoint initiates the approval process where the user's wallet
    will be prompted to sign a transaction approving the platform's builder fee.

    Args:
        account_id: The account ID to approve builder fee for

    Returns:
        {
            "success": bool,
            "message": str,
            "builder_address": str,
            "approved_fee": str  # e.g., "0.03%"
        }
    """
    try:
        print(f"[BUILDER_AUTH] ========== Starting authorization for account_id={account_id} ==========")
        from config.settings import HYPERLIQUID_BUILDER_CONFIG
        from services.hyperliquid_environment import get_hyperliquid_client

        # Get account
        account = db.query(Account).filter(Account.id == account_id, Account.is_deleted != True).first()
        if not account:
            print(f"[BUILDER_AUTH] ERROR: Account {account_id} not found")
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Check if account has mainnet wallet configured (new architecture first, then fallback)
        mainnet_wallet = db.query(HyperliquidWallet).filter(
            HyperliquidWallet.account_id == account_id,
            HyperliquidWallet.environment == "mainnet",
            HyperliquidWallet.private_key_encrypted.isnot(None)
        ).first()

        # Fallback to old architecture
        if not mainnet_wallet:
            mainnet_key = getattr(account, "hyperliquid_mainnet_private_key", None)
            if not mainnet_key:
                print(f"[BUILDER_AUTH] ERROR: Account {account_id} does not have a mainnet wallet configured")
                raise HTTPException(
                    status_code=400,
                    detail="Account does not have a mainnet wallet configured"
                )
            print(f"[BUILDER_AUTH] Using old architecture mainnet wallet for account {account_id}")
        else:
            print(f"[BUILDER_AUTH] Using new architecture mainnet wallet for account {account_id}, wallet_address={mainnet_wallet.wallet_address}")

        # Get Hyperliquid client with mainnet environment (regardless of current trading mode)
        client = get_hyperliquid_client(db, account_id, override_environment="mainnet")
        print(f"[BUILDER_AUTH] Got Hyperliquid client for account {account_id}")

        # Calculate fee percentage for display (e.g., 30 -> "0.03%")
        fee_bps = HYPERLIQUID_BUILDER_CONFIG.builder_fee / 10  # Convert to basis points
        fee_percentage = f"{fee_bps / 100}%"  # Convert to percentage string

        print(f"[BUILDER_AUTH] Calling approve_builder_fee: builder={HYPERLIQUID_BUILDER_CONFIG.builder_address}, fee={fee_percentage}")

        # Call approve_builder_fee on the exchange
        # This will trigger wallet signature request
        result = client.sdk_exchange.approve_builder_fee(
            HYPERLIQUID_BUILDER_CONFIG.builder_address,
            fee_percentage
        )

        # Check if authorization was successful based on Hyperliquid response
        is_success = not (isinstance(result, dict) and result.get('status') == 'err')

        if is_success:
            print(f"[BUILDER_AUTH] SUCCESS for account {account_id}: result={result}")
        else:
            print(f"[BUILDER_AUTH] FAILED for account {account_id}: result={result}")

        logger.info(
            f"Builder fee approval initiated for account {account_id}: "
            f"builder={HYPERLIQUID_BUILDER_CONFIG.builder_address}, "
            f"fee={fee_percentage}, result={result}"
        )

        return {
            "success": is_success,
            "message": result.get('response', 'Authorization failed') if not is_success else "Builder fee authorized successfully",
            "builder_address": HYPERLIQUID_BUILDER_CONFIG.builder_address,
            "approved_fee": fee_percentage,
            "result": result
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[BUILDER_AUTH] EXCEPTION for account {account_id}: {type(e).__name__}: {e}")
        logger.error(f"Failed to approve builder fee for account {account_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to approve builder fee: {str(e)}"
        )


@router.get("/hyperliquid/check-mainnet-accounts")
def check_mainnet_accounts(
    db: Session = Depends(get_db)
):
    """
    Check builder fee authorization for all active mainnet trading accounts.

    This endpoint is called on system startup to identify accounts that have:
    - auto_trading_enabled = true
    - hyperliquid_mainnet_private_key configured
    - but builder fee NOT authorized

    Returns:
        {
            "unauthorized_accounts": [
                {
                    "account_id": int,
                    "account_name": str,
                    "wallet_address": str,
                    "max_fee": int,  # Current authorized fee in tenths of basis point
                    "required_fee": int  # Required fee (30 for 0.03%)
                }
            ]
        }
    """
    try:
        import requests
        from config.settings import HYPERLIQUID_BUILDER_CONFIG
        from eth_account import Account as EthAccount
        from services.hyperliquid_environment import decrypt_private_key

        unauthorized_accounts = []
        checked_account_ids = set()

        # === Check new multi-wallet architecture (hyperliquid_wallets table) ===
        # Query accounts with mainnet wallet in hyperliquid_wallets table and trading enabled
        mainnet_wallets = db.query(HyperliquidWallet, Account).join(
            Account, HyperliquidWallet.account_id == Account.id
        ).filter(
            HyperliquidWallet.environment == "mainnet",
            HyperliquidWallet.private_key_encrypted.isnot(None),
            Account.auto_trading_enabled == "true"
        ).all()

        logger.info(f"Found {len(mainnet_wallets)} accounts with mainnet wallet in wallets table")

        for wallet, account in mainnet_wallets:
            checked_account_ids.add(account.id)
            try:
                # For agent_key wallets, check builder fee against master wallet address
                # (builder fee authorization is tied to the master wallet, not the agent)
                if wallet.key_type == "agent_key" and wallet.master_wallet_address:
                    wallet_address = wallet.master_wallet_address.lower()
                else:
                    decrypted_key = decrypt_private_key(wallet.private_key_encrypted)
                    if not decrypted_key:
                        logger.warning(f"Failed to decrypt mainnet key for account {account.id} from wallets table")
                        continue
                    if not decrypted_key.startswith('0x'):
                        decrypted_key = '0x' + decrypted_key
                    eth_account = EthAccount.from_key(decrypted_key)
                    wallet_address = eth_account.address.lower()

                response = requests.post(
                    "https://api.hyperliquid.xyz/info",
                    json={
                        "type": "maxBuilderFee",
                        "user": wallet_address,
                        "builder": HYPERLIQUID_BUILDER_CONFIG.builder_address
                    },
                    timeout=10
                )

                if response.status_code == 200:
                    max_fee = response.json()
                    required_fee = HYPERLIQUID_BUILDER_CONFIG.builder_fee

                    if max_fee < required_fee:
                        unauthorized_accounts.append({
                            "account_id": account.id,
                            "account_name": account.name,
                            "wallet_address": wallet_address,
                            "max_fee": max_fee,
                            "required_fee": required_fee
                        })
                        logger.info(
                            f"Account {account.id} ({account.name}) unauthorized: "
                            f"max_fee={max_fee}, required={required_fee}"
                        )
                else:
                    logger.error(
                        f"Failed to check authorization for account {account.id}: "
                        f"HTTP {response.status_code}"
                    )
            except Exception as account_err:
                logger.error(
                    f"Error checking account {account.id} from wallets table: {account_err}",
                    exc_info=True
                )
                continue

        # === Fallback: Check old architecture (accounts table field) ===
        # Query accounts with mainnet key in accounts table (not already checked)
        old_accounts = db.query(Account).filter(
            Account.auto_trading_enabled == "true",
            Account.hyperliquid_mainnet_private_key.isnot(None),
            Account.hyperliquid_mainnet_private_key != "",
            Account.is_deleted != True
        ).all()

        # Filter out accounts already checked via wallets table
        old_accounts = [a for a in old_accounts if a.id not in checked_account_ids]

        logger.info(f"Found {len(old_accounts)} additional accounts with mainnet key in accounts table")

        for account in old_accounts:
            try:
                decrypted_key = decrypt_private_key(account.hyperliquid_mainnet_private_key)
                if not decrypted_key:
                    logger.warning(f"Failed to decrypt mainnet key for account {account.id}")
                    continue

                if not decrypted_key.startswith('0x'):
                    decrypted_key = '0x' + decrypted_key

                eth_account = EthAccount.from_key(decrypted_key)
                wallet_address = eth_account.address.lower()

                response = requests.post(
                    "https://api.hyperliquid.xyz/info",
                    json={
                        "type": "maxBuilderFee",
                        "user": wallet_address,
                        "builder": HYPERLIQUID_BUILDER_CONFIG.builder_address
                    },
                    timeout=10
                )

                if response.status_code == 200:
                    max_fee = response.json()
                    required_fee = HYPERLIQUID_BUILDER_CONFIG.builder_fee

                    if max_fee < required_fee:
                        unauthorized_accounts.append({
                            "account_id": account.id,
                            "account_name": account.name,
                            "wallet_address": wallet_address,
                            "max_fee": max_fee,
                            "required_fee": required_fee
                        })
                        logger.info(
                            f"Account {account.id} ({account.name}) unauthorized: "
                            f"max_fee={max_fee}, required={required_fee}"
                        )
                else:
                    logger.error(
                        f"Failed to check authorization for account {account.id}: "
                        f"HTTP {response.status_code}"
                    )
            except Exception as account_err:
                logger.error(
                    f"Error checking account {account.id}: {account_err}",
                    exc_info=True
                )
                continue

        total_checked = len(mainnet_wallets) + len(old_accounts)
        logger.info(
            f"Builder fee check complete: {len(unauthorized_accounts)} "
            f"unauthorized out of {total_checked} total"
        )

        return {
            "unauthorized_accounts": unauthorized_accounts
        }

    except Exception as e:
        logger.error(f"Failed to check mainnet accounts: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check mainnet accounts: {str(e)}"
        )


@router.post("/{account_id}/disable-trading")
def disable_trading(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    Disable auto trading for an account.

    This endpoint is called when a user refuses to authorize builder fee,
    ensuring that the account cannot place orders without proper authorization.

    Args:
        account_id: The account ID to disable trading for

    Returns:
        {
            "success": bool,
            "message": str,
            "account_id": int,
            "account_name": str
        }
    """
    try:
        # Get account
        account = db.query(Account).filter(Account.id == account_id, Account.is_deleted != True).first()
        if not account:
            raise HTTPException(
                status_code=404,
                detail=f"Account {account_id} not found"
            )

        # Disable auto trading
        account.auto_trading_enabled = "false"
        db.commit()

        logger.info(
            f"Auto trading disabled for account {account_id} ({account.name}) "
            f"due to builder fee authorization refusal"
        )

        return {
            "success": True,
            "message": f"Auto trading disabled for {account.name}",
            "account_id": account_id,
            "account_name": account.name
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to disable trading for account {account_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to disable trading: {str(e)}"
        )


@router.patch("/dashboard-visibility")
def update_dashboard_visibility(
    visibility_updates: List[dict],
    db: Session = Depends(get_db)
):
    """
    Batch update show_on_dashboard for multiple accounts.

    Request body: [{"account_id": 1, "show_on_dashboard": true}, ...]

    Returns:
        {"success": bool, "updated_count": int, "updates": [...]}
    """
    try:
        updated = []
        for item in visibility_updates:
            account_id = item.get("account_id")
            show = item.get("show_on_dashboard", True)

            account = db.query(Account).filter(Account.id == account_id, Account.is_deleted != True).first()
            if account:
                account.show_on_dashboard = show
                updated.append({"account_id": account_id, "show_on_dashboard": show})

        db.commit()

        logger.info(f"Updated dashboard visibility for {len(updated)} accounts")
        return {
            "success": True,
            "updated_count": len(updated),
            "updates": updated
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update dashboard visibility: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update dashboard visibility: {str(e)}"
        )
