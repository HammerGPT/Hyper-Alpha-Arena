"""
Account and Asset Curve API Routes (Cleaned)
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging

from database.connection import SessionLocal
from database.models import Account, Position, Trade, CryptoPrice
from services.ai_decision_service import build_chat_completion_endpoints, _extract_text_from_message
from schemas.account import StrategyConfig, StrategyConfigUpdate
from repositories.strategy_repo import get_strategy_by_account, upsert_strategy
from services.trading_strategy import strategy_manager

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


def _serialize_strategy(account: Account, strategy) -> StrategyConfig:
    """Convert database strategy config to API schema."""
    last_trigger = strategy.last_trigger_at
    if last_trigger:
        if last_trigger.tzinfo is None:
            last_iso = last_trigger.replace(tzinfo=timezone.utc).isoformat()
        else:
            last_iso = last_trigger.astimezone(timezone.utc).isoformat()
    else:
        last_iso = None

    return StrategyConfig(
        trigger_mode=strategy.trigger_mode or "realtime",
        interval_seconds=strategy.interval_seconds,
        tick_batch_size=strategy.tick_batch_size,
        enabled=(strategy.enabled == "true" and account.auto_trading_enabled == "true"),
        last_trigger_at=last_iso,
    )


@router.get("/list")
async def list_all_accounts(db: Session = Depends(get_db)):
    """Get all active accounts (for paper trading demo)"""
    try:
        from database.models import User
        accounts = db.query(Account).filter(Account.is_active == "true").all()
        
        result = []
        for account in accounts:
            user = db.query(User).filter(User.id == account.user_id).first()
            result.append({
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
            })
        
        return result
    except Exception as e:
        logger.error(f"Failed to list accounts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list accounts: {str(e)}")


@router.get("/{account_id}/overview")
async def get_specific_account_overview(account_id: int, db: Session = Depends(get_db)):
    """Get overview for a specific account"""
    try:
        # Get the specific account
        account = db.query(Account).filter(
            Account.id == account_id,
            Account.is_active == "true"
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
async def get_account_strategy(account_id: int, db: Session = Depends(get_db)):
    """Fetch AI trading strategy configuration for an account."""
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.is_active == "true")
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    strategy = get_strategy_by_account(db, account_id)
    if not strategy:
        strategy = upsert_strategy(
            db,
            account_id=account_id,
            trigger_mode="realtime",
            interval_seconds=1,
            tick_batch_size=1,
            enabled=(account.auto_trading_enabled == "true"),
        )
        strategy_manager.refresh_strategies(force=True)

    return _serialize_strategy(account, strategy)


@router.put("/{account_id}/strategy", response_model=StrategyConfig)
async def update_account_strategy(
    account_id: int,
    payload: StrategyConfigUpdate,
    db: Session = Depends(get_db),
):
    """Update AI trading strategy configuration for an account."""
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.is_active == "true")
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    valid_modes = {"realtime", "interval", "tick_batch"}
    if payload.trigger_mode not in valid_modes:
        raise HTTPException(status_code=400, detail="Invalid trigger_mode")

    if payload.trigger_mode == "interval":
        if payload.interval_seconds is None or payload.interval_seconds <= 0:
            raise HTTPException(
                status_code=400,
                detail="interval_seconds must be > 0 for interval mode",
            )
    else:
        interval_seconds = None

    if payload.trigger_mode == "tick_batch":
        if payload.tick_batch_size is None or payload.tick_batch_size <= 0:
            raise HTTPException(
                status_code=400,
                detail="tick_batch_size must be > 0 for tick_batch mode",
            )
    else:
        tick_batch_size = None

    interval_seconds = payload.interval_seconds if payload.trigger_mode == "interval" else None
    tick_batch_size = payload.tick_batch_size if payload.trigger_mode == "tick_batch" else None

    strategy = upsert_strategy(
        db,
        account_id=account_id,
        trigger_mode=payload.trigger_mode,
        interval_seconds=interval_seconds,
        tick_batch_size=tick_batch_size,
        enabled=payload.enabled,
    )

    strategy_manager.refresh_strategies(force=True)
    return _serialize_strategy(account, strategy)


@router.get("/overview")
async def get_account_overview(db: Session = Depends(get_db)):
    """Get overview for the default account (for paper trading demo)"""
    try:
        # Get the first active account (default account)
        account = db.query(Account).filter(Account.is_active == "true").first()
        
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
async def create_new_account(payload: dict, db: Session = Depends(get_db)):
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
            auto_trading_enabled=auto_trading_value
        )
        
        db.add(new_account)
        db.commit()
        db.refresh(new_account)

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
            "auto_trading_enabled": new_account.auto_trading_enabled == "true"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create account: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create account: {str(e)}")


@router.put("/{account_id}")
async def update_account_settings(account_id: int, payload: dict, db: Session = Depends(get_db)):
    """Update account settings (for paper trading demo)"""
    try:
        logger.info(f"Updating account {account_id} with payload: {payload}")
        
        account = db.query(Account).filter(
            Account.id == account_id,
            Account.is_active == "true"
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


@router.get("/asset-curve/timeframe")
async def get_asset_curve_by_timeframe(
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
        accounts = db.query(Account).filter(Account.is_active == "true").all()
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
async def test_llm_connection(payload: dict):
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
        
        # Test the connection with a simple completion request
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            # Use OpenAI-compatible chat completions format
            # Build payload with appropriate parameters based on model type
            model_lower = model.lower()

            # Reasoning models that don't support temperature parameter
            is_reasoning_model = any(x in model_lower for x in [
                'gpt-5', 'o1-preview', 'o1-mini', 'o1-', 'o3-', 'o4-'
            ])

            # o1 series specifically doesn't support system messages
            is_o1_series = any(x in model_lower for x in ['o1-preview', 'o1-mini', 'o1-'])

            # New models that use max_completion_tokens instead of max_tokens
            is_new_model = is_reasoning_model or any(x in model_lower for x in ['gpt-4o'])

            # o1 series models don't support system messages
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

            # Reasoning models (GPT-5, o1, o3, o4) don't support custom temperature
            # Only add temperature parameter for non-reasoning models
            if not is_reasoning_model:
                payload_data["temperature"] = 0

            # Use max_completion_tokens for newer models
            # Use max_tokens for older models (GPT-3.5, GPT-4, GPT-4-turbo, Deepseek)
            # Modern models have large context windows, so we can be generous with token limits
            if is_new_model:
                # Reasoning models (GPT-5/o1) need more tokens for internal reasoning
                payload_data["max_completion_tokens"] = 2000
            else:
                # Regular models (GPT-4, Deepseek, Claude, etc.)
                payload_data["max_tokens"] = 2000

            # For GPT-5 series, set reasoning_effort to minimal for faster test
            if 'gpt-5' in model_lower:
                payload_data["reasoning_effort"] = "minimal"

            endpoints = build_chat_completion_endpoints(base_url, model)
            if not endpoints:
                return {"success": False, "message": "Invalid base URL"}

            last_failure_message = "Connection test failed"

            for idx, endpoint in enumerate(endpoints):
                try:
                    response = requests.post(
                        endpoint,
                        headers=headers,
                        json=payload_data,
                        timeout=10.0,
                        verify=False  # Disable SSL verification for custom AI endpoints
                    )
                except requests.ConnectionError:
                    last_failure_message = f"Failed to connect to {endpoint}. Please check the base URL."
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

                    # Extract text from OpenAI-compatible response format
                    if "choices" in result and len(result["choices"]) > 0:
                        choice = result["choices"][0]
                        message = choice.get("message", {})
                        finish_reason = choice.get("finish_reason", "")

                        # Get content from message
                        raw_content = message.get("content")
                        content = _extract_text_from_message(raw_content)

                        # For reasoning models (GPT-5, o1), check reasoning field if content is empty
                        if not content and is_reasoning_model:
                            reasoning = _extract_text_from_message(message.get("reasoning"))
                            if reasoning:
                                logger.info(f"LLM test successful for model {model} at {endpoint} (reasoning model)")
                                snippet = reasoning[:100] + "..." if len(reasoning) > 100 else reasoning
                                return {
                                    "success": True,
                                    "message": f"Connection successful! Model {model} (reasoning model) responded correctly.",
                                    "response": f"[Reasoning: {snippet}]"
                                }

                        # Standard content check
                        if content:
                            logger.info(f"LLM test successful for model {model} at {endpoint}")
                            return {
                                "success": True,
                                "message": f"Connection successful! Model {model} responded correctly.",
                                "response": content
                            }

                        # If still no content, show more debug info
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
                    if idx < len(endpoints) - 1:
                        logger.info(f"Endpoint {endpoint} returned 404, trying alternative path")
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
