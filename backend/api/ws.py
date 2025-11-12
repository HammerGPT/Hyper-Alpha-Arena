import asyncio
import json
import logging
import threading
from datetime import date, datetime, timedelta
from typing import Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import AIDecisionLog, Account, CryptoPrice, Trade, User
from repositories.account_repo import get_account, get_or_create_default_account
from repositories.order_repo import list_orders
from repositories.position_repo import list_positions
from repositories.user_repo import get_or_create_user, get_user
from services.asset_calculator import calc_positions_value
from services.asset_curve_calculator import get_all_asset_curves_data_new
from services.market_data import get_last_price
from services.scheduler import add_account_snapshot_job, remove_account_snapshot_job
from services.hyperliquid_cache import get_cached_account_state, get_cached_positions
from services.hyperliquid_environment import get_hyperliquid_client


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, websocket: WebSocket):
        pass  # WebSocket is already accepted in the endpoint

    def register(self, account_id: Optional[int], websocket: WebSocket):
        if account_id is not None:
            self.active_connections.setdefault(account_id, set()).add(websocket)
            # Add scheduled snapshot task for new account
            add_account_snapshot_job(account_id, interval_seconds=10)

    def unregister(self, account_id: Optional[int], websocket: WebSocket):
        if account_id is not None and account_id in self.active_connections:
            self.active_connections[account_id].discard(websocket)
            if not self.active_connections[account_id]:
                del self.active_connections[account_id]
                # Remove the scheduled task for this account
                remove_account_snapshot_job(account_id)

    async def send_to_account(self, account_id: int, message: dict):
        if account_id not in self.active_connections:
            return
        payload = json.dumps(message, ensure_ascii=False)
        for ws in list(self.active_connections[account_id]):
            try:
                # Check if WebSocket is still open before sending
                if ws.client_state.name != "CONNECTED":
                    self.active_connections[account_id].discard(ws)
                    continue
                await ws.send_text(payload)
            except Exception as e:
                # Log the error and remove broken connection
                logging.warning(f"Failed to send message to WebSocket: {e}")
                self.active_connections[account_id].discard(ws)

    async def broadcast_to_all(self, message: dict):
        """Broadcast message to all connected clients"""
        payload = json.dumps(message, ensure_ascii=False)
        for account_id, websockets in list(self.active_connections.items()):
            for ws in list(websockets):
                try:
                    # Check if WebSocket is still open before sending
                    if ws.client_state.name != "CONNECTED":
                        websockets.discard(ws)
                        continue
                    await ws.send_text(payload)
                except Exception as e:
                    # Log the error and remove broken connection
                    logging.warning(f"Failed to broadcast message to WebSocket: {e}")
                    websockets.discard(ws)

    def has_connections(self) -> bool:
        return any(self.active_connections.values())

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        if loop and loop.is_running():
            self._loop = loop

    def schedule_task(self, coro):
        loop = None
        if self._loop and self._loop.is_running():
            loop = self._loop
        else:
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    self._loop = loop
            except RuntimeError:
                loop = None

        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, loop)
            return

        # Fallback: run in a dedicated daemon thread to avoid blocking the caller
        def _run():
            asyncio.run(coro)

        threading.Thread(target=_run, daemon=True).start()


manager = ConnectionManager()
HYPERLIQUID_SNAPSHOT_CACHE_TTL = 360  # seconds


async def broadcast_asset_curve_update(timeframe: str = "1h"):
    """Broadcast asset curve updates to all connected clients"""
    db = SessionLocal()
    try:
        asset_curves = get_all_asset_curves_data(db, timeframe)
        await manager.broadcast_to_all({
            "type": "asset_curve_update",
            "timeframe": timeframe,
            "data": asset_curves
        })
    except Exception as e:
        logging.error(f"Failed to broadcast asset curve update: {e}")
    finally:
        db.close()


async def broadcast_arena_asset_update(update_payload: dict):
    """Broadcast aggregated arena asset update to all connected clients"""
    message = {
        "type": "arena_asset_update",
        **update_payload,
    }
    await manager.broadcast_to_all(message)


async def broadcast_trade_update(trade_data: dict):
    """Broadcast trade update to specific account when trade is executed

    Args:
        trade_data: Dictionary containing trade information including account_id
    """
    account_id = trade_data.get("account_id")
    if not account_id:
        logging.warning("broadcast_trade_update called without account_id")
        return

    try:
        await manager.send_to_account(account_id, {
            "type": "trade_update",
            "trade": trade_data
        })
    except Exception as e:
        logging.error(f"Failed to broadcast trade update: {e}")


async def broadcast_position_update(account_id: int, positions_data: list):
    """Broadcast position update to specific account when positions change

    Args:
        account_id: Account ID to send update to
        positions_data: List of position dictionaries
    """
    try:
        await manager.send_to_account(account_id, {
            "type": "position_update",
            "positions": positions_data
        })
    except Exception as e:
        logging.error(f"Failed to broadcast position update: {e}")


async def broadcast_model_chat_update(decision_data: dict):
    """Broadcast AI decision update to specific account

    Args:
        decision_data: Dictionary containing AI decision information including account_id
    """
    account_id = decision_data.get("account_id")
    if not account_id:
        logging.warning("broadcast_model_chat_update called without account_id")
        return

    try:
        await manager.send_to_account(account_id, {
            "type": "model_chat_update",
            "decision": decision_data
        })
    except Exception as e:
        logging.error(f"Failed to broadcast model chat update: {e}")


def get_all_asset_curves_data(
    db: Session,
    timeframe: str = "1h",
    trading_mode: str = "testnet",
    environment: Optional[str] = None,
    wallet_address: Optional[str] = None,
):
    """Get timeframe-based asset curve data for all accounts - WebSocket version

    Uses the new algorithm that draws curves by accounts and creates all-time lists.

    Args:
        timeframe: Time period for the curve, options: "5m", "1h", "1d"
        trading_mode: Trading mode filter, options: "paper", "testnet", "mainnet"
    """
    return get_all_asset_curves_data_new(
        db,
        timeframe,
        trading_mode,
        environment,
        wallet_address=wallet_address,
    )


async def _send_snapshot_optimized(db: Session, account_id: int):
    """Optimized version of snapshot that reduces expensive operations"""
    account = get_account(db, account_id)
    if not account:
        return
    
    positions = list_positions(db, account_id)
    orders = list_orders(db, account_id)
    trades = (
        db.query(Trade).filter(Trade.account_id == account_id).order_by(Trade.trade_time.desc()).limit(10).all()  # Reduced from 20 to 10
    )
    ai_decisions = (
        db.query(AIDecisionLog).filter(AIDecisionLog.account_id == account_id).order_by(AIDecisionLog.decision_time.desc()).limit(10).all()  # Reduced from 20 to 10
    )
    
    # Use cached positions value calculation
    positions_value = calc_positions_value(db, account_id)

    overview = {
        "account": {
            "id": account.id,
            "user_id": account.user_id,
            "name": account.name,
            "account_type": account.account_type,
            "initial_capital": float(account.initial_capital),
            "current_cash": float(account.current_cash),
            "frozen_cash": float(account.frozen_cash),
        },
        "total_assets": positions_value + float(account.current_cash),
        "positions_value": positions_value,
    }
    
    # Optimize position enrichment - batch price fetching
    enriched_positions = []
    price_error_message = None
    
    # Group positions by symbol to reduce API calls
    unique_symbols = set((p.symbol, p.market) for p in positions)
    price_cache = {}
    
    # Fetch all unique prices in one go
    for symbol, market in unique_symbols:
        try:
            price = get_last_price(symbol, market)
            price_cache[(symbol, market)] = price
        except Exception as e:
            price_cache[(symbol, market)] = None
            error_msg = str(e)
            if "cookie" in error_msg.lower() and price_error_message is None:
                price_error_message = error_msg

    for p in positions:
        price = price_cache.get((p.symbol, p.market))
        enriched_positions.append({
            "id": p.id,
            "account_id": p.account_id,
            "symbol": p.symbol,
            "name": p.name,
            "market": p.market,
            "quantity": float(p.quantity),
            "available_quantity": float(p.available_quantity),
            "avg_cost": float(p.avg_cost),
            "last_price": float(price) if price is not None else None,
            "market_value": (float(price) * float(p.quantity)) if price is not None else None,
        })

    # Prepare response data - exclude expensive asset curve calculation for frequent updates
    response_data = {
        "type": "snapshot_fast",  # Different type to indicate this is optimized
        "overview": overview,
        "positions": enriched_positions,
        "orders": [
            {
                "id": o.id,
                "order_no": o.order_no,
                "user_id": o.account_id,
                "symbol": o.symbol,
                "name": o.name,
                "market": o.market,
                "side": o.side,
                "order_type": o.order_type,
                "price": float(o.price) if o.price is not None else None,
                "quantity": float(o.quantity),
                "filled_quantity": float(o.filled_quantity),
                "status": o.status,
            }
            for o in orders[:10]  # Reduced from 20 to 10
        ],
        "trades": [
            {
                "id": t.id,
                "order_id": t.order_id,
                "user_id": t.account_id,
                "symbol": t.symbol,
                "name": t.name,
                "market": t.market,
                "side": t.side,
                "price": float(t.price),
                "quantity": float(t.quantity),
                "commission": float(t.commission),
                "trade_time": str(t.trade_time),
            }
            for t in trades
        ],
        "ai_decisions": [
            {
                "id": d.id,
                "decision_time": str(d.decision_time),
                "reason": d.reason,
                "operation": d.operation,
                "symbol": d.symbol,
                "prev_portion": float(d.prev_portion),
                "target_portion": float(d.target_portion),
                "total_balance": float(d.total_balance),
                "executed": str(d.executed).lower() if d.executed else "false",
                "order_id": d.order_id,
            }
            for d in ai_decisions
        ],
        # Asset curves only included occasionally (every minute)
        "timestamp": datetime.now().timestamp()
    }
    
    # Only include expensive asset curve data every 60 seconds
    current_second = int(datetime.now().timestamp()) % 60
    if current_second < 10:  # First 10 seconds of each minute
        try:
            response_data["all_asset_curves"] = get_all_asset_curves_data(db, "1h")
            response_data["type"] = "snapshot_full"  # Indicate this includes full data
        except Exception as e:
            logger.error(f"Failed to get asset curves: {e}")

    if price_error_message:
        response_data["warning"] = {
            "type": "market_data_error",
            "message": price_error_message
        }

    await manager.send_to_account(account_id, response_data)


async def _send_snapshot_by_mode(db: Session, account_id: int, trading_mode: str):
    """
    Send snapshot based on trading mode

    Args:
        db: Database session
        account_id: Account ID
        trading_mode: "paper", "testnet", or "mainnet"
    """
    logging.info(f"_send_snapshot_by_mode called: trading_mode={trading_mode}, account_id={account_id}")
    if trading_mode == "paper":
        # Use traditional paper trading snapshot
        logging.info(f"Sending paper trading snapshot for account {account_id}")
        await _send_snapshot(db, account_id)
    elif trading_mode in ["testnet", "mainnet"]:
        # Use Hyperliquid real-time snapshot
        logging.info(f"Sending Hyperliquid {trading_mode} snapshot for account {account_id}")
        await _send_hyperliquid_snapshot(db, account_id, trading_mode)
    else:
        logging.error(f"Invalid trading_mode: {trading_mode}")
        await _send_snapshot(db, account_id)  # Fallback to paper


async def _send_hyperliquid_snapshot(db: Session, account_id: int, environment: str):
    """
    Send Hyperliquid snapshot, preferring cached data to avoid unnecessary API calls.

    Args:
        db: Database session
        account_id: Account ID
        environment: "testnet" or "mainnet"
    """

    account = get_account(db, account_id)
    if not account:
        logging.error(f"Account {account_id} not found for Hyperliquid snapshot")
        return

    # Check if wallet exists for this environment (multi-wallet architecture)
    from database.models import HyperliquidWallet
    wallet = db.query(HyperliquidWallet).filter(
        HyperliquidWallet.account_id == account_id,
        HyperliquidWallet.environment == environment
    ).first()

    if not wallet:
        # Silently skip sending error to avoid spamming frontend
        # Just log the warning
        logging.debug(f"No {environment} wallet configured for account {account.name} (ID: {account_id})")
        return

    cached_state = get_cached_account_state(account_id, max_age_seconds=HYPERLIQUID_SNAPSHOT_CACHE_TTL)
    cached_positions = get_cached_positions(account_id, max_age_seconds=HYPERLIQUID_SNAPSHOT_CACHE_TTL)
    account_state = cached_state["data"] if cached_state else None
    positions_data = cached_positions["data"] if cached_positions else None
    wallet_address = None
    if isinstance(account_state, dict):
        wallet_address = account_state.get("wallet_address")

    data_source = "cache"
    client = None

    if account_state is None or positions_data is None:
        try:
            client = get_hyperliquid_client(db, account_id, override_environment=environment)
        except Exception as e:
            logging.warning(f"Failed to initialize Hyperliquid client for account {account.name} ({environment}): {e}")
            # Don't send error to frontend, just log and skip
            return

        try:
            account_state = client.get_account_state(db)
            positions_data = client.get_positions(db)
            wallet_address = client.wallet_address
            data_source = "live"
        except Exception as e:
            logging.error(f"Failed to fetch Hyperliquid data for account {account_id}: {e}", exc_info=True)
            await manager.send_to_account(account_id, {
                "type": "error",
                "message": f"Failed to fetch Hyperliquid data: {str(e)}"
            })
            return
    else:
        # Cache hit but wallet missing? fall back to client for metadata only.
        if wallet_address is None:
            try:
                client = get_hyperliquid_client(db, account_id)
                if client.environment == environment:
                    wallet_address = client.wallet_address
            except Exception:
                wallet_address = None

    if account_state is None or positions_data is None:
        logging.error(f"Hyperliquid snapshot missing state or positions for account {account_id}")
        return

    wallet_address = wallet_address or account_state.get("wallet_address")

    try:
        # Transform Hyperliquid data to frontend format
        overview = {
            "account": {
                "id": account.id,
                "user_id": account.user_id,
                "name": account.name,
                "account_type": f"hyperliquid_{environment}",
                "initial_capital": float(account.initial_capital),
                # Use Hyperliquid balance instead of local database
                "current_cash": account_state.get("available_balance", 0),
                "frozen_cash": account_state.get("used_margin", 0),
            },
            "total_assets": account_state.get("total_equity", 0),
            "positions_value": sum(
                abs(p.get("position_value", 0)) for p in positions_data
            ),
        }

        # Transform Hyperliquid positions to frontend format
        enriched_positions = []
        for p in positions_data:
            enriched_positions.append({
                "id": 0,  # Hyperliquid positions don't have local DB ID
                "account_id": account_id,
                "symbol": p.get("coin", ""),
                "name": p.get("coin", ""),
                "market": "HYPERLIQUID_PERP",
                "quantity": abs(p.get("szi", 0)),  # Absolute size
                "available_quantity": abs(p.get("szi", 0)),
                "avg_cost": p.get("entry_px", 0),
                "last_price": None,  # Can fetch from market data if needed
                "market_value": p.get("position_value", 0),
                "current_value": p.get("position_value", 0),
                "unrealized_pnl": p.get("unrealized_pnl", 0),
                "leverage": p.get("leverage", 1),
                "side": "LONG" if p.get("szi", 0) > 0 else "SHORT",
            })

        # Get orders and trades from local database (filtered by environment)
        orders = list_orders(db, account_id)
        # Filter orders by hyperliquid_environment
        hyperliquid_orders = [
            o for o in orders
            if o.hyperliquid_environment == environment
        ]

        trades = (
            db.query(Trade)
            .filter(Trade.account_id == account_id)
            .filter(Trade.hyperliquid_environment == environment)
            .order_by(Trade.trade_time.desc())
            .limit(20)
            .all()
        )

        ai_decisions = (
            db.query(AIDecisionLog)
            .filter(AIDecisionLog.account_id == account_id)
            .filter(AIDecisionLog.hyperliquid_environment == environment)
            .order_by(AIDecisionLog.decision_time.desc())
            .limit(20)
            .all()
        )

        # Prepare response data
        response_data = {
            "type": "snapshot",
            "trading_mode": environment,
            "overview": overview,
            "positions": enriched_positions,
            "orders": [
                {
                    "id": o.id,
                    "order_no": o.order_no,
                    "user_id": o.account_id,
                    "symbol": o.symbol,
                    "name": o.name,
                    "market": o.market,
                    "side": o.side,
                    "order_type": o.order_type,
                    "price": float(o.price) if o.price is not None else None,
                    "quantity": float(o.quantity),
                    "filled_quantity": float(o.filled_quantity),
                    "status": o.status,
                }
                for o in hyperliquid_orders[:20]
            ],
            "trades": [
                {
                    "id": t.id,
                    "order_id": t.order_id,
                    "user_id": t.account_id,
                    "symbol": t.symbol,
                    "name": t.name,
                    "market": t.market,
                    "side": t.side,
                    "price": float(t.price),
                    "quantity": float(t.quantity),
                    "commission": float(t.commission),
                    "trade_time": str(t.trade_time),
                }
                for t in trades
            ],
            "ai_decisions": [
                {
                    "id": d.id,
                    "decision_time": str(d.decision_time),
                    "reason": d.reason,
                    "operation": d.operation,
                    "symbol": d.symbol,
                    "prev_portion": float(d.prev_portion),
                    "target_portion": float(d.target_portion),
                    "total_balance": float(d.total_balance),
                    "executed": str(d.executed).lower() if d.executed else "false",
                    "order_id": d.order_id,
                }
                for d in ai_decisions
            ],
            "all_asset_curves": get_all_asset_curves_data(
                db,
                "1h",
                trading_mode=environment,
                environment=environment,
            ),
            "hyperliquid_state": {
                "environment": environment,
                "total_equity": account_state.get("total_equity", 0),
                "available_balance": account_state.get("available_balance", 0),
                "used_margin": account_state.get("used_margin", 0),
                "margin_usage_percent": account_state.get("margin_usage_percent", 0),
                "source": data_source,
                "wallet_address": wallet_address,
            }
        }

        await manager.send_to_account(account_id, response_data)

    except Exception as e:
        logging.error(f"Failed to get Hyperliquid snapshot: {e}", exc_info=True)
        await manager.send_to_account(account_id, {
            "type": "error",
            "message": f"Failed to fetch Hyperliquid data: {str(e)}"
        })


async def _send_snapshot(db: Session, account_id: int):
    account = get_account(db, account_id)
    if not account:
        return
    positions = list_positions(db, account_id)
    orders = list_orders(db, account_id)
    trades = (
        db.query(Trade).filter(Trade.account_id == account_id).order_by(Trade.trade_time.desc()).limit(20).all()
    )
    ai_decisions = (
        db.query(AIDecisionLog).filter(AIDecisionLog.account_id == account_id).order_by(AIDecisionLog.decision_time.desc()).limit(20).all()
    )
    positions_value = calc_positions_value(db, account_id)

    overview = {
        "account": {
            "id": account.id,
            "user_id": account.user_id,
            "name": account.name,
            "account_type": account.account_type,
            "initial_capital": float(account.initial_capital),
            "current_cash": float(account.current_cash),
            "frozen_cash": float(account.frozen_cash),
        },
        "total_assets": positions_value + float(account.current_cash),
        "positions_value": positions_value,
    }
    # enrich positions with latest price and market value
    enriched_positions = []
    price_error_message = None

    for p in positions:
        try:
            price = get_last_price(p.symbol, p.market)
        except Exception as e:
            price = None
            # Collect price retrieval error messages, especially cookie-related errors
            error_msg = str(e)
            if "cookie" in error_msg.lower() and price_error_message is None:
                price_error_message = error_msg

        enriched_positions.append({
            "id": p.id,
            "account_id": p.account_id,
            "symbol": p.symbol,
            "name": p.name,
            "market": p.market,
            "quantity": float(p.quantity),
            "available_quantity": float(p.available_quantity),
            "avg_cost": float(p.avg_cost),
            "last_price": float(price) if price is not None else None,
            "market_value": (float(price) * float(p.quantity)) if price is not None else None,
        })

    # Prepare response data
    response_data = {
        "type": "snapshot",
        "overview": overview,
        "positions": enriched_positions,
        "orders": [
            {
                "id": o.id,
                "order_no": o.order_no,
                "user_id": o.account_id,
                "symbol": o.symbol,
                "name": o.name,
                "market": o.market,
                "side": o.side,
                "order_type": o.order_type,
                "price": float(o.price) if o.price is not None else None,
                "quantity": float(o.quantity),
                "filled_quantity": float(o.filled_quantity),
                "status": o.status,
            }
            for o in orders[:20]
        ],
        "trades": [
            {
                "id": t.id,
                "order_id": t.order_id,
                "user_id": t.account_id,
                "symbol": t.symbol,
                "name": t.name,
                "market": t.market,
                "side": t.side,
                "price": float(t.price),
                "quantity": float(t.quantity),
                "commission": float(t.commission),
                "trade_time": str(t.trade_time),
            }
            for t in trades
        ],
        "ai_decisions": [
            {
                "id": d.id,
                "decision_time": str(d.decision_time),
                "reason": d.reason,
                "operation": d.operation,
                "symbol": d.symbol,
                "prev_portion": float(d.prev_portion),
                "target_portion": float(d.target_portion),
                "total_balance": float(d.total_balance),
                "executed": str(d.executed).lower() if d.executed else "false",
                "order_id": d.order_id,
            }
            for d in ai_decisions
        ],
        "all_asset_curves": get_all_asset_curves_data(db, "1h"),
    }

    if price_error_message:
        response_data["warning"] = {
            "type": "market_data_error",
            "message": price_error_message
        }

    await manager.send_to_account(account_id, response_data)


async def websocket_endpoint(websocket: WebSocket):
    client_host = websocket.client.host if websocket.client else "unknown"
    logging.info(f"[WS] New WebSocket connection from {client_host}")
    await websocket.accept()
    logging.info(f"[WS] WebSocket connection accepted from {client_host}")
    try:
        manager.set_event_loop(asyncio.get_running_loop())
    except RuntimeError:
        pass
    account_id: int | None = None
    user_id: int | None = None  # Initialize user_id to avoid UnboundLocalError

    try:
        while True:
            # Check if WebSocket is still connected before trying to receive
            if websocket.client_state.name != "CONNECTED":
                break
                
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                # Client disconnected gracefully
                break
            except Exception as e:
                # Handle other connection errors
                logging.error(f"WebSocket receive error: {e}")
                break
                
            try:
                msg = json.loads(data)
            except json.JSONDecodeError as e:
                logging.error(f"Invalid JSON received: {e}")
                try:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON format"}))
                except:
                    break
                continue
            kind = msg.get("type")
            logging.info(f"[WS] Received message type: {kind}")
            db: Session = SessionLocal()
            try:
                if kind == "bootstrap":
                    #  mode: Create or get default default user
                    username = msg.get("username", "default")
                    trading_mode = msg.get("trading_mode", "paper")
                    logging.info(f"[WS] Bootstrap request: username={username}, trading_mode={trading_mode}")
                    user = get_or_create_user(db, username)
                    
                    # Get existing account for this user
                    account = get_or_create_default_account(
                        db,
                        user.id,
                        account_name=f"{username} AI Trader",
                        initial_capital=float(msg.get("initial_capital", 100000))
                    )

                    if not account:
                        # Allow connection but with no account (frontend will handle this)
                        account_id = None
                    else:
                        account_id = account.id

                    # Register the connection (handles None account_id gracefully)
                    manager.register(account_id, websocket)
                    logging.info(f"[WS] Registered connection for account_id={account_id}")

                    # Send bootstrap confirmation with account info
                    try:
                        if account:
                            logging.info(f"[WS] Sending bootstrap_ok for account {account.id}")
                            await manager.send_to_account(account_id, {
                                "type": "bootstrap_ok",
                                "user": {"id": user.id, "username": user.username},
                                "account": {"id": account.id, "name": account.name, "user_id": account.user_id}
                            })
                            logging.info(f"[WS] Sending snapshot for account {account.id}")
                            await _send_snapshot(db, account_id)
                            logging.info(f"[WS] Bootstrap complete for account {account.id}")
                        else:
                            # Send bootstrap with no account info
                            await websocket.send_text(json.dumps({
                                "type": "bootstrap_ok",
                                "user": {"id": user.id, "username": user.username},
                                "account": None
                            }))
                    except Exception as e:
                        logging.error(f"Failed to send bootstrap response: {e}")
                        break
                elif kind == "subscribe":
                    # subscribe existing user_id
                    uid = int(msg.get("user_id"))
                    u = get_user(db, uid)
                    if not u:
                        try:
                            await websocket.send_text(json.dumps({"type": "error", "message": "user not found"}))
                        except:
                            break
                        continue
                    user_id = uid
                    manager.register(user_id, websocket)
                    try:
                        await _send_snapshot(db, user_id)
                    except Exception as e:
                        logging.error(f"Failed to send snapshot: {e}")
                        break
                elif kind == "switch_user":
                    # Switch to different user account
                    target_username = msg.get("username")
                    if not target_username:
                        await websocket.send_text(json.dumps({"type": "error", "message": "username required"}))
                        continue

                    # Unregister from current user if any
                    if user_id is not None:
                        manager.unregister(user_id, websocket)

                    # Find target user
                    target_user = get_or_create_user(db, target_username, 100000.0)
                    user_id = target_user.id

                    # Register to new user
                    manager.register(user_id, websocket)

                    # Send confirmation and snapshot
                    await manager.send_to_account(user_id, {
                        "type": "user_switched",
                        "user": {
                            "id": target_user.id,
                            "username": target_user.username
                        }
                    })
                    await _send_snapshot(db, user_id)
                elif kind == "switch_account":
                    # Switch to different account by ID
                    target_account_id = msg.get("account_id")
                    if not target_account_id:
                        await websocket.send_text(json.dumps({"type": "error", "message": "account_id required"}))
                        continue

                    # Unregister from current account if any
                    if account_id is not None:
                        manager.unregister(account_id, websocket)

                    # Get target account
                    target_account = get_account(db, target_account_id)
                    if not target_account:
                        await websocket.send_text(json.dumps({"type": "error", "message": "account not found"}))
                        continue

                    account_id = target_account.id
                    
                    # Register to new account
                    manager.register(account_id, websocket)

                    # Send confirmation and snapshot
                    await manager.send_to_account(account_id, {
                        "type": "account_switched",
                        "account": {
                            "id": target_account.id,
                            "user_id": target_account.user_id,
                            "name": target_account.name
                        }
                    })
                    await _send_snapshot(db, account_id)
                elif kind == "get_snapshot":
                    if account_id is not None:
                        # Get trading mode from request (default to "testnet")
                        trading_mode = msg.get("trading_mode", "testnet")
                        logging.info(f"Received get_snapshot request: account_id={account_id}, trading_mode={trading_mode}")
                        await _send_snapshot_by_mode(db, account_id, trading_mode)
                elif kind == "get_asset_curve":
                    # Get asset curve data with specific timeframe and trading mode
                    timeframe = msg.get("timeframe", "1h")
                    trading_mode = msg.get("trading_mode", "testnet")
                    environment = msg.get("environment")
                    if timeframe not in ["5m", "1h", "1d"]:
                        await websocket.send_text(json.dumps({"type": "error", "message": "Invalid timeframe. Must be 5m, 1h, or 1d"}))
                        continue

                    asset_curves = get_all_asset_curves_data(
                        db,
                        timeframe,
                        trading_mode,
                        environment=environment,
                    )
                    await websocket.send_text(json.dumps({
                        "type": "asset_curve_data",
                        "timeframe": timeframe,
                        "trading_mode": trading_mode,
                        "environment": environment,
                        "data": asset_curves
                    }))
                elif kind == "place_order":
                    if account_id is None:
                        await websocket.send_text(json.dumps({"type": "error", "message": "not authenticated"}))
                        continue

                    try:
                        # Import the order creation service
                        from services.order_matching import create_order

                        # Get account and user object
                        account = get_account(db, account_id)
                        if not account:
                            await websocket.send_text(json.dumps({"type": "error", "message": "account not found"}))
                            continue

                        user = get_user(db, account.user_id)
                        if not user:
                            await websocket.send_text(json.dumps({"type": "error", "message": "user not found"}))
                            continue

                        # Extract order parameters
                        symbol = msg.get("symbol")
                        name = msg.get("name", symbol)  # Use symbol as name if not provided
                        market = msg.get("market", "CRYPTO")
                        side = msg.get("side")
                        order_type = msg.get("order_type")
                        price = msg.get("price")
                        quantity = msg.get("quantity")

                        # Validate required parameters
                        if not all([symbol, side, order_type, quantity]):
                            await websocket.send_text(json.dumps({"type": "error", "message": "missing required parameters"}))
                            continue

                        # Convert quantity to float (crypto supports fractional quantities)
                        try:
                            quantity = float(quantity)
                        except (ValueError, TypeError):
                            await websocket.send_text(json.dumps({"type": "error", "message": "invalid quantity"}))
                            continue

                        # Create the order
                        order = create_order(
                            db=db,
                            account=account,
                            symbol=symbol,
                            name=name,
                            side=side,
                            order_type=order_type,
                            price=price,
                            quantity=quantity
                        )

                        # Commit the order
                        db.commit()

                        # Send success response
                        await manager.send_to_account(account_id, {"type": "order_pending", "order_id": order.id})

                        # Send updated snapshot
                        await _send_snapshot(db, account_id)

                    except ValueError as e:
                        # Business logic errors (insufficient funds, etc.)
                        try:
                            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
                        except:
                            break
                    except Exception as e:
                        # Unexpected errors
                        import traceback
                        print(f"Order placement error: {e}")
                        print(traceback.format_exc())
                        try:
                            await websocket.send_text(json.dumps({"type": "error", "message": f"order placement failed: {str(e)}"}))
                        except:
                            break
                elif kind == "ping":
                    try:
                        await websocket.send_text(json.dumps({"type": "pong"}))
                    except:
                        break
                else:
                    try:
                        await websocket.send_text(json.dumps({"type": "error", "message": "unknown message"}))
                    except:
                        break
            finally:
                db.close()
    except WebSocketDisconnect:
        if account_id is not None:
            manager.unregister(account_id, websocket)
        if user_id is not None:
            manager.unregister(user_id, websocket)
        return
    finally:
        # Clean up resources when user disconnects
        if account_id is not None:
            manager.unregister(account_id, websocket)
        if user_id is not None:
            manager.unregister(user_id, websocket)
