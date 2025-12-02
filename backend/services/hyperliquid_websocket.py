"""
Hyperliquid WebSocket Manager - Real-time data streaming

This module provides WebSocket connections to Hyperliquid for real-time data:
- All mid prices (allMids)
- Account state (clearinghouseState)
- User events (fills, funding, liquidations)
- Order updates
- Trades

Using WebSocket instead of HTTP polling dramatically reduces API quota consumption.
WebSocket connections do NOT count toward the address-based rate limit.
"""

import asyncio
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = logging.getLogger(__name__)


class SubscriptionType(Enum):
    """Hyperliquid WebSocket subscription types"""
    ALL_MIDS = "allMids"
    TRADES = "trades"
    L2_BOOK = "l2Book"
    CANDLE = "candle"
    NOTIFICATION = "notification"
    WEB_DATA = "webData3"
    CLEARINGHOUSE_STATE = "clearinghouseState"
    OPEN_ORDERS = "openOrders"
    ORDER_UPDATES = "orderUpdates"
    USER_EVENTS = "userEvents"
    USER_FILLS = "userFills"
    USER_FUNDINGS = "userFundings"
    ACTIVE_ASSET_CTX = "activeAssetCtx"
    BBO = "bbo"


@dataclass
class Subscription:
    """Represents a WebSocket subscription"""
    type: SubscriptionType
    params: Dict[str, Any] = field(default_factory=dict)
    callback: Optional[Callable[[Dict[str, Any]], None]] = None
    
    def to_message(self) -> Dict[str, Any]:
        """Convert to Hyperliquid subscription message format"""
        subscription = {"type": self.type.value}
        subscription.update(self.params)
        return {
            "method": "subscribe",
            "subscription": subscription
        }
    
    def to_unsubscribe_message(self) -> Dict[str, Any]:
        """Convert to Hyperliquid unsubscribe message format"""
        subscription = {"type": self.type.value}
        subscription.update(self.params)
        return {
            "method": "unsubscribe",
            "subscription": subscription
        }
    
    @property
    def key(self) -> str:
        """Unique key for this subscription"""
        params_str = json.dumps(self.params, sort_keys=True)
        return f"{self.type.value}:{params_str}"


class HyperliquidWebSocketManager:
    """
    Manages WebSocket connections to Hyperliquid for real-time data streaming.
    
    Features:
    - Automatic reconnection on disconnect
    - Heartbeat/ping to keep connection alive
    - Multiple subscription management
    - Thread-safe callback execution
    - Environment support (mainnet/testnet)
    
    Usage:
        manager = HyperliquidWebSocketManager(environment="mainnet")
        await manager.connect()
        
        # Subscribe to all mid prices
        await manager.subscribe_all_mids(callback=handle_prices)
        
        # Subscribe to user events
        await manager.subscribe_user_events(wallet_address="0x...", callback=handle_events)
    """
    
    # WebSocket endpoints
    MAINNET_WS_URL = "wss://api.hyperliquid.xyz/ws"
    TESTNET_WS_URL = "wss://api.hyperliquid-testnet.xyz/ws"
    
    # Connection settings
    HEARTBEAT_INTERVAL = 30  # seconds
    RECONNECT_DELAY = 5  # seconds
    MAX_RECONNECT_ATTEMPTS = 10
    
    def __init__(self, environment: str = "mainnet"):
        """
        Initialize WebSocket manager.
        
        Args:
            environment: "mainnet" or "testnet"
        """
        if environment not in ["mainnet", "testnet"]:
            raise ValueError(f"Invalid environment: {environment}")
        
        self.environment = environment
        self.ws_url = self.MAINNET_WS_URL if environment == "mainnet" else self.TESTNET_WS_URL
        
        # Connection state
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._running = False
        self._reconnect_attempts = 0
        
        # Subscriptions
        self._subscriptions: Dict[str, Subscription] = {}
        self._lock = threading.Lock()
        
        # Background tasks
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        
        # Global callbacks
        self._on_connect_callbacks: List[Callable[[], None]] = []
        self._on_disconnect_callbacks: List[Callable[[], None]] = []
        self._on_error_callbacks: List[Callable[[Exception], None]] = []
        
        # Data caches (updated by WebSocket)
        self._all_mids_cache: Dict[str, float] = {}
        self._all_mids_lock = threading.Lock()
        self._last_all_mids_update: float = 0
        
        logger.info(f"HyperliquidWebSocketManager initialized for {environment}")
    
    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self._connected and self._ws is not None
    
    @property
    def all_mids(self) -> Dict[str, float]:
        """Get cached mid prices (thread-safe)"""
        with self._all_mids_lock:
            return self._all_mids_cache.copy()
    
    def get_mid_price(self, symbol: str) -> Optional[float]:
        """Get mid price for a specific symbol"""
        symbol_upper = symbol.upper().replace("/USDC", "").replace(":USDC", "")
        with self._all_mids_lock:
            return self._all_mids_cache.get(symbol_upper)
    
    async def connect(self) -> bool:
        """
        Establish WebSocket connection to Hyperliquid.
        
        Returns:
            True if connection successful, False otherwise
        """
        if self._connected:
            logger.warning("Already connected to Hyperliquid WebSocket")
            return True
        
        try:
            logger.info(f"Connecting to Hyperliquid WebSocket: {self.ws_url}")
            
            self._ws = await websockets.connect(
                self.ws_url,
                ping_interval=None,  # We handle our own heartbeat
                ping_timeout=None,
                close_timeout=10,
                max_size=10 * 1024 * 1024,  # 10MB max message size
            )
            
            self._connected = True
            self._running = True
            self._reconnect_attempts = 0
            
            # Start background tasks
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            # Notify callbacks
            for callback in self._on_connect_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in on_connect callback: {e}")
            
            # Resubscribe to all existing subscriptions
            await self._resubscribe_all()
            
            logger.info(f"Connected to Hyperliquid WebSocket ({self.environment})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Hyperliquid WebSocket: {e}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from WebSocket"""
        logger.info("Disconnecting from Hyperliquid WebSocket")
        
        self._running = False
        self._connected = False
        
        # Cancel background tasks
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Close WebSocket
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            self._ws = None
        
        # Notify callbacks
        for callback in self._on_disconnect_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in on_disconnect callback: {e}")
        
        logger.info("Disconnected from Hyperliquid WebSocket")
    
    async def _receive_loop(self):
        """Background task to receive and process WebSocket messages"""
        while self._running and self._ws:
            try:
                message = await self._ws.recv()
                await self._handle_message(message)
                
            except ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}")
                self._connected = False
                if self._running:
                    await self._reconnect()
                break
                
            except asyncio.CancelledError:
                break
                
            except Exception as e:
                logger.error(f"Error in receive loop: {e}")
                for callback in self._on_error_callbacks:
                    try:
                        callback(e)
                    except Exception:
                        pass
    
    async def _heartbeat_loop(self):
        """Background task to send periodic heartbeat"""
        while self._running and self._ws:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                
                if self._ws and self._connected:
                    # Send ping message
                    await self._ws.send(json.dumps({"method": "ping"}))
                    logger.debug("Sent heartbeat ping")
                    
            except asyncio.CancelledError:
                break
                
            except Exception as e:
                logger.warning(f"Error sending heartbeat: {e}")
    
    async def _reconnect(self):
        """Attempt to reconnect to WebSocket"""
        while self._running and self._reconnect_attempts < self.MAX_RECONNECT_ATTEMPTS:
            self._reconnect_attempts += 1
            logger.info(f"Reconnection attempt {self._reconnect_attempts}/{self.MAX_RECONNECT_ATTEMPTS}")
            
            await asyncio.sleep(self.RECONNECT_DELAY * self._reconnect_attempts)
            
            if await self.connect():
                return
        
        logger.error("Max reconnection attempts reached")
        for callback in self._on_error_callbacks:
            try:
                callback(Exception("Max reconnection attempts reached"))
            except Exception:
                pass
    
    async def _resubscribe_all(self):
        """Resubscribe to all existing subscriptions after reconnect"""
        with self._lock:
            subscriptions = list(self._subscriptions.values())
        
        for sub in subscriptions:
            try:
                await self._send_subscription(sub)
                logger.debug(f"Resubscribed to {sub.type.value}")
            except Exception as e:
                logger.error(f"Failed to resubscribe to {sub.type.value}: {e}")
    
    async def _send_subscription(self, subscription: Subscription):
        """Send subscription message to WebSocket"""
        if not self._ws or not self._connected:
            raise RuntimeError("WebSocket not connected")
        
        message = subscription.to_message()
        await self._ws.send(json.dumps(message))
        logger.debug(f"Sent subscription: {message}")
    
    async def _handle_message(self, raw_message: str):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(raw_message)
            
            # Handle subscription response
            if data.get("channel") == "subscriptionResponse":
                logger.debug(f"Subscription confirmed: {data.get('data')}")
                return
            
            # Handle pong response
            if data.get("channel") == "pong":
                logger.debug("Received pong")
                return
            
            # Handle data channels
            channel = data.get("channel")
            payload = data.get("data")
            
            if channel == "allMids":
                self._handle_all_mids(payload)
            elif channel == "trades":
                self._handle_trades(payload)
            elif channel == "l2Book":
                self._handle_l2_book(payload)
            elif channel == "clearinghouseState":
                self._handle_clearinghouse_state(payload)
            elif channel == "openOrders":
                self._handle_open_orders(payload)
            elif channel == "orderUpdates":
                self._handle_order_updates(payload)
            elif channel == "userEvents":
                self._handle_user_events(payload)
            elif channel == "userFills":
                self._handle_user_fills(payload)
            elif channel == "userFundings":
                self._handle_user_fundings(payload)
            elif channel == "notification":
                self._handle_notification(payload)
            elif channel == "candle":
                self._handle_candle(payload)
            elif channel == "activeAssetCtx":
                self._handle_active_asset_ctx(payload)
            elif channel == "bbo":
                self._handle_bbo(payload)
            else:
                logger.debug(f"Unknown channel: {channel}")
            
            # Call subscription-specific callbacks
            self._dispatch_to_callbacks(channel, payload)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse WebSocket message: {e}")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
    
    def _dispatch_to_callbacks(self, channel: str, data: Any):
        """Dispatch data to registered callbacks"""
        with self._lock:
            for sub in self._subscriptions.values():
                if sub.type.value == channel and sub.callback:
                    try:
                        sub.callback(data)
                    except Exception as e:
                        logger.error(f"Error in subscription callback: {e}")
    
    def _handle_all_mids(self, data: Dict[str, Any]):
        """Handle allMids update"""
        if not isinstance(data, dict) or "mids" not in data:
            return
        
        mids = data["mids"]
        with self._all_mids_lock:
            for symbol, price_str in mids.items():
                try:
                    self._all_mids_cache[symbol.upper()] = float(price_str)
                except (ValueError, TypeError):
                    continue
            self._last_all_mids_update = time.time()
        
        logger.debug(f"Updated {len(mids)} mid prices")
    
    def _handle_trades(self, data: List[Dict[str, Any]]):
        """Handle trades update"""
        logger.debug(f"Received {len(data) if isinstance(data, list) else 1} trades")
    
    def _handle_l2_book(self, data: Dict[str, Any]):
        """Handle L2 order book update"""
        logger.debug(f"Received L2 book update for {data.get('coin', 'unknown')}")
    
    def _handle_clearinghouse_state(self, data: Dict[str, Any]):
        """Handle clearinghouse state update (account state)"""
        logger.debug("Received clearinghouse state update")
    
    def _handle_open_orders(self, data: Dict[str, Any]):
        """Handle open orders update"""
        logger.debug("Received open orders update")
    
    def _handle_order_updates(self, data: List[Dict[str, Any]]):
        """Handle order updates"""
        logger.debug(f"Received {len(data) if isinstance(data, list) else 1} order updates")
    
    def _handle_user_events(self, data: Dict[str, Any]):
        """Handle user events (fills, funding, liquidations)"""
        logger.debug(f"Received user event: {list(data.keys()) if isinstance(data, dict) else 'unknown'}")
    
    def _handle_user_fills(self, data: Dict[str, Any]):
        """Handle user fills update"""
        is_snapshot = data.get("isSnapshot", False)
        fills = data.get("fills", [])
        logger.debug(f"Received {len(fills)} user fills (snapshot={is_snapshot})")
    
    def _handle_user_fundings(self, data: Dict[str, Any]):
        """Handle user funding payments update"""
        logger.debug("Received user fundings update")
    
    def _handle_notification(self, data: Dict[str, Any]):
        """Handle notification"""
        logger.info(f"Notification: {data.get('notification', 'unknown')}")
    
    def _handle_candle(self, data: List[Dict[str, Any]]):
        """Handle candle update"""
        logger.debug(f"Received {len(data) if isinstance(data, list) else 1} candles")
    
    def _handle_active_asset_ctx(self, data: Dict[str, Any]):
        """Handle active asset context update"""
        logger.debug(f"Received asset context for {data.get('coin', 'unknown')}")
    
    def _handle_bbo(self, data: Dict[str, Any]):
        """Handle best bid/offer update"""
        logger.debug(f"Received BBO for {data.get('coin', 'unknown')}")
    
    # ========== Subscription Methods ==========
    
    async def subscribe_all_mids(
        self,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        dex: Optional[str] = None
    ) -> str:
        """
        Subscribe to all mid prices.
        
        This is the most efficient way to get real-time prices for all assets.
        Updates are pushed whenever any price changes.
        
        Args:
            callback: Optional callback function for price updates
            dex: Optional DEX filter
            
        Returns:
            Subscription key
        """
        params = {}
        if dex:
            params["dex"] = dex
        
        sub = Subscription(
            type=SubscriptionType.ALL_MIDS,
            params=params,
            callback=callback
        )
        
        return await self._add_subscription(sub)
    
    async def subscribe_trades(
        self,
        coin: str,
        callback: Optional[Callable[[List[Dict[str, Any]]], None]] = None
    ) -> str:
        """
        Subscribe to trades for a specific coin.
        
        Args:
            coin: Asset symbol (e.g., "BTC", "ETH")
            callback: Optional callback for trade updates
            
        Returns:
            Subscription key
        """
        sub = Subscription(
            type=SubscriptionType.TRADES,
            params={"coin": coin.upper()},
            callback=callback
        )
        
        return await self._add_subscription(sub)
    
    async def subscribe_l2_book(
        self,
        coin: str,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        n_sig_figs: Optional[int] = None,
        mantissa: Optional[int] = None
    ) -> str:
        """
        Subscribe to L2 order book for a specific coin.
        
        Args:
            coin: Asset symbol
            callback: Optional callback for book updates
            n_sig_figs: Optional significant figures for price aggregation
            mantissa: Optional mantissa for price aggregation
            
        Returns:
            Subscription key
        """
        params = {"coin": coin.upper()}
        if n_sig_figs is not None:
            params["nSigFigs"] = n_sig_figs
        if mantissa is not None:
            params["mantissa"] = mantissa
        
        sub = Subscription(
            type=SubscriptionType.L2_BOOK,
            params=params,
            callback=callback
        )
        
        return await self._add_subscription(sub)
    
    async def subscribe_candle(
        self,
        coin: str,
        interval: str,
        callback: Optional[Callable[[List[Dict[str, Any]]], None]] = None
    ) -> str:
        """
        Subscribe to candle updates for a specific coin and interval.
        
        Args:
            coin: Asset symbol
            interval: Candle interval (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 12h, 1d, 3d, 1w, 1M)
            callback: Optional callback for candle updates
            
        Returns:
            Subscription key
        """
        valid_intervals = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d", "3d", "1w", "1M"]
        if interval not in valid_intervals:
            raise ValueError(f"Invalid interval: {interval}. Must be one of {valid_intervals}")
        
        sub = Subscription(
            type=SubscriptionType.CANDLE,
            params={"coin": coin.upper(), "interval": interval},
            callback=callback
        )
        
        return await self._add_subscription(sub)
    
    async def subscribe_clearinghouse_state(
        self,
        user_address: str,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> str:
        """
        Subscribe to clearinghouse state (account state) for a user.
        
        This provides real-time updates on:
        - Account equity
        - Margin usage
        - Position values
        
        Args:
            user_address: Wallet address (0x...)
            callback: Optional callback for state updates
            
        Returns:
            Subscription key
        """
        sub = Subscription(
            type=SubscriptionType.CLEARINGHOUSE_STATE,
            params={"user": user_address.lower()},
            callback=callback
        )
        
        return await self._add_subscription(sub)
    
    async def subscribe_open_orders(
        self,
        user_address: str,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> str:
        """
        Subscribe to open orders for a user.
        
        Args:
            user_address: Wallet address
            callback: Optional callback for order updates
            
        Returns:
            Subscription key
        """
        sub = Subscription(
            type=SubscriptionType.OPEN_ORDERS,
            params={"user": user_address.lower()},
            callback=callback
        )
        
        return await self._add_subscription(sub)
    
    async def subscribe_order_updates(
        self,
        user_address: str,
        callback: Optional[Callable[[List[Dict[str, Any]]], None]] = None
    ) -> str:
        """
        Subscribe to order status updates for a user.
        
        Args:
            user_address: Wallet address
            callback: Optional callback for order updates
            
        Returns:
            Subscription key
        """
        sub = Subscription(
            type=SubscriptionType.ORDER_UPDATES,
            params={"user": user_address.lower()},
            callback=callback
        )
        
        return await self._add_subscription(sub)
    
    async def subscribe_user_events(
        self,
        user_address: str,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> str:
        """
        Subscribe to user events (fills, funding, liquidations).
        
        This is a comprehensive subscription that includes:
        - Trade fills
        - Funding payments
        - Liquidation events
        - Non-user cancels
        
        Args:
            user_address: Wallet address
            callback: Optional callback for events
            
        Returns:
            Subscription key
        """
        sub = Subscription(
            type=SubscriptionType.USER_EVENTS,
            params={"user": user_address.lower()},
            callback=callback
        )
        
        return await self._add_subscription(sub)
    
    async def subscribe_user_fills(
        self,
        user_address: str,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        aggregate_by_time: bool = False
    ) -> str:
        """
        Subscribe to user fills (trade executions).
        
        Args:
            user_address: Wallet address
            callback: Optional callback for fills
            aggregate_by_time: Whether to aggregate fills by time
            
        Returns:
            Subscription key
        """
        params = {"user": user_address.lower()}
        if aggregate_by_time:
            params["aggregateByTime"] = True
        
        sub = Subscription(
            type=SubscriptionType.USER_FILLS,
            params=params,
            callback=callback
        )
        
        return await self._add_subscription(sub)
    
    async def subscribe_user_fundings(
        self,
        user_address: str,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> str:
        """
        Subscribe to user funding payments.
        
        Args:
            user_address: Wallet address
            callback: Optional callback for funding updates
            
        Returns:
            Subscription key
        """
        sub = Subscription(
            type=SubscriptionType.USER_FUNDINGS,
            params={"user": user_address.lower()},
            callback=callback
        )
        
        return await self._add_subscription(sub)
    
    async def subscribe_bbo(
        self,
        coin: str,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> str:
        """
        Subscribe to best bid/offer updates for a coin.
        
        Args:
            coin: Asset symbol
            callback: Optional callback for BBO updates
            
        Returns:
            Subscription key
        """
        sub = Subscription(
            type=SubscriptionType.BBO,
            params={"coin": coin.upper()},
            callback=callback
        )
        
        return await self._add_subscription(sub)
    
    async def _add_subscription(self, subscription: Subscription) -> str:
        """Add a subscription and send to WebSocket"""
        key = subscription.key
        
        with self._lock:
            self._subscriptions[key] = subscription
        
        if self._connected:
            await self._send_subscription(subscription)
        
        logger.info(f"Added subscription: {subscription.type.value}")
        return key
    
    async def unsubscribe(self, subscription_key: str) -> bool:
        """
        Unsubscribe from a subscription.
        
        Args:
            subscription_key: Key returned from subscribe method
            
        Returns:
            True if unsubscribed successfully
        """
        with self._lock:
            subscription = self._subscriptions.pop(subscription_key, None)
        
        if not subscription:
            logger.warning(f"Subscription not found: {subscription_key}")
            return False
        
        if self._connected and self._ws:
            try:
                message = subscription.to_unsubscribe_message()
                await self._ws.send(json.dumps(message))
                logger.info(f"Unsubscribed from {subscription.type.value}")
            except Exception as e:
                logger.error(f"Error sending unsubscribe: {e}")
                return False
        
        return True
    
    async def unsubscribe_all(self):
        """Unsubscribe from all subscriptions"""
        with self._lock:
            keys = list(self._subscriptions.keys())
        
        for key in keys:
            await self.unsubscribe(key)
    
    # ========== Event Handlers ==========
    
    def on_connect(self, callback: Callable[[], None]):
        """Register callback for connection events"""
        self._on_connect_callbacks.append(callback)
    
    def on_disconnect(self, callback: Callable[[], None]):
        """Register callback for disconnection events"""
        self._on_disconnect_callbacks.append(callback)
    
    def on_error(self, callback: Callable[[Exception], None]):
        """Register callback for error events"""
        self._on_error_callbacks.append(callback)


# ========== Global Manager Instances ==========

_ws_managers: Dict[str, HyperliquidWebSocketManager] = {}
_ws_managers_lock = threading.Lock()


def get_websocket_manager(environment: str = "mainnet") -> HyperliquidWebSocketManager:
    """
    Get or create WebSocket manager for environment.
    
    Args:
        environment: "mainnet" or "testnet"
        
    Returns:
        HyperliquidWebSocketManager instance
    """
    with _ws_managers_lock:
        if environment not in _ws_managers:
            _ws_managers[environment] = HyperliquidWebSocketManager(environment)
        return _ws_managers[environment]


async def start_websocket_manager(environment: str = "mainnet") -> HyperliquidWebSocketManager:
    """
    Start WebSocket manager and connect.
    
    Args:
        environment: "mainnet" or "testnet"
        
    Returns:
        Connected HyperliquidWebSocketManager instance
    """
    manager = get_websocket_manager(environment)
    
    if not manager.is_connected:
        await manager.connect()
    
    return manager


async def stop_websocket_manager(environment: str = "mainnet"):
    """
    Stop WebSocket manager and disconnect.
    
    Args:
        environment: "mainnet" or "testnet"
    """
    with _ws_managers_lock:
        manager = _ws_managers.get(environment)
    
    if manager:
        await manager.disconnect()


async def stop_all_websocket_managers():
    """Stop all WebSocket managers"""
    with _ws_managers_lock:
        managers = list(_ws_managers.values())
    
    for manager in managers:
        await manager.disconnect()


# ========== Convenience Functions ==========

async def get_realtime_price(symbol: str, environment: str = "mainnet") -> Optional[float]:
    """
    Get real-time price from WebSocket cache.
    
    Falls back to None if WebSocket not connected or price not available.
    
    Args:
        symbol: Asset symbol
        environment: "mainnet" or "testnet"
        
    Returns:
        Price or None
    """
    manager = get_websocket_manager(environment)
    return manager.get_mid_price(symbol)


def get_all_realtime_prices(environment: str = "mainnet") -> Dict[str, float]:
    """
    Get all real-time prices from WebSocket cache.
    
    Args:
        environment: "mainnet" or "testnet"
        
    Returns:
        Dict of symbol -> price
    """
    manager = get_websocket_manager(environment)
    return manager.all_mids
