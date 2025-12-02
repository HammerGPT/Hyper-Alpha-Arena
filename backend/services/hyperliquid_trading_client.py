"""
Hyperliquid Trading Client - Real trading execution with environment isolation

This module provides authenticated trading client for Hyperliquid perpetual contracts.
Key features:
- Testnet/Mainnet environment isolation
- Strict environment validation on every API call
- Account state and position management
- Order placement with leverage support
"""
import logging
import time
import json
import math
import requests
from typing import Dict, List, Optional, Any
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR, ROUND_CEILING, InvalidOperation, getcontext
from eth_account import Account as EthAccount
from eth_account.messages import encode_defunct, _hash_eip191_message
from eth_utils import keccak

# Try different function names across eth_account versions
encode_typed_data_func = None
try:
    # eth_account >= 0.6.0
    from eth_account.messages import encode_typed_data
    encode_typed_data_func = encode_typed_data
except ImportError:
    try:
        # Some versions use encode_structured_data
        from eth_account.messages import encode_structured_data
        encode_typed_data_func = encode_structured_data
    except ImportError:
        encode_typed_data_func = None

import ccxt
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Account, HyperliquidExchangeAction
from services.hyperliquid_cache import (
    update_account_state_cache,
    update_positions_cache,
)

getcontext().prec = 28

logger = logging.getLogger(__name__)

# ============================================================================
# TPSL ORDER CACHE - In-memory cache to prevent duplicate TP/SL orders
# ============================================================================
# This cache tracks TP/SL orders that have been placed to avoid creating
# duplicates when the Hyperliquid API has latency in returning newly created orders.
# Structure: {(wallet_address, symbol): {"tp_price": float, "sl_price": float, "timestamp": int}}
# The cache is automatically cleared on server restart (desired behavior).
from typing import Tuple
_tpsl_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

def _get_cache_key(wallet_address: str, symbol: str) -> Tuple[str, str]:
    """Generate cache key for TPSL orders"""
    return (wallet_address.lower() if wallet_address else "", symbol.upper())

def _get_cached_tpsl(wallet_address: str, symbol: str) -> Optional[Dict[str, Any]]:
    """Get cached TPSL prices for a symbol"""
    key = _get_cache_key(wallet_address, symbol)
    return _tpsl_cache.get(key)

def _set_cached_tpsl(wallet_address: str, symbol: str, tp_price: Optional[float], sl_price: Optional[float]) -> None:
    """Update cached TPSL prices for a symbol"""
    key = _get_cache_key(wallet_address, symbol)
    _tpsl_cache[key] = {
        "tp_price": tp_price,
        "sl_price": sl_price,
        "timestamp": int(time.time() * 1000)
    }
    logger.info(f"[TPSL CACHE] Updated cache for {symbol}: TP={tp_price}, SL={sl_price}")

def _clear_cached_tpsl(wallet_address: str, symbol: str) -> None:
    """Clear cached TPSL prices for a symbol"""
    key = _get_cache_key(wallet_address, symbol)
    if key in _tpsl_cache:
        del _tpsl_cache[key]
        logger.info(f"[TPSL CACHE] Cleared cache for {symbol}")


class EnvironmentMismatchError(Exception):
    """Raised when account environment doesn't match client environment"""
    pass


class HyperliquidTradingClient:
    """
    Hyperliquid trading client with environment isolation

    Supports both testnet and mainnet with strict validation to prevent
    accidental cross-environment operations.
    """

    def __init__(self, account_id: int, private_key: str, environment: str = "testnet", wallet_address: Optional[str] = None):
        """
        Initialize trading client

        Args:
            account_id: Database account ID (for validation)
            private_key: Hyperliquid private key (0x... format)
            environment: "testnet" or "mainnet"
            wallet_address: Ethereum wallet address (derived from private key if not provided)

        Raises:
            ValueError: If environment is invalid
        """
        if environment not in ["testnet", "mainnet"]:
            raise ValueError(f"Invalid environment: {environment}. Must be 'testnet' or 'mainnet'")

        self.account_id = account_id
        self.environment = environment

        # Ensure private key has 0x prefix for consistency
        if not private_key.startswith('0x'):
            private_key = '0x' + private_key
        self.private_key = private_key

        import sys
        print(f"[DEBUG __init__] account_id={account_id}, environment={environment}, wallet_address={wallet_address}", file=sys.stderr, flush=True)

        # Derive wallet address from private key if not provided
        if not wallet_address:
            try:
                from eth_account import Account as EthAccount
                eth_account = EthAccount.from_key(private_key)
                # Lowercase address as recommended by Hyperliquid docs
                self.wallet_address = eth_account.address.lower()
                logger.info(f"Derived wallet address from private key: {self.wallet_address}")
            except Exception as e:
                logger.error(f"Failed to derive wallet address from private key: {e}", exc_info=True)
                self.wallet_address = None
        else:
            # Lowercase address as recommended by Hyperliquid docs
            self.wallet_address = wallet_address.lower()
            logger.info(f"Using provided wallet address: {self.wallet_address}")

        if not self.wallet_address:
            raise ValueError("Wallet address could not be derived from private key. Please check key format.")

        logger.info(f"[FINAL] Using wallet address: {self.wallet_address}")

        # Set API endpoint based on environment
        if environment == "testnet":
            self.api_url = "https://api.hyperliquid-testnet.xyz"
        else:
            self.api_url = "https://api.hyperliquid.xyz"

        # Initialize CCXT exchange with authentication (for balance/position queries)
        try:
            self.exchange = ccxt.hyperliquid({
                'sandbox': (environment == "testnet"),
                'enableRateLimit': True,
                'rateLimit': 100,  # 100ms between requests
                'privateKey': private_key,  # Hyperliquid requires privateKey field
                'walletAddress': self.wallet_address,
                'options': {
                    'fetchMarkets': {
                        'hip3': {
                            'dex': []  # Empty list to skip HIP3 DEX markets (we only need perp markets)
                        }
                    }
                }
            })
            self._disable_hip3_markets()

            logger.info(
                f"CCXT HyperliquidClient initialized: account_id={account_id} "
                f"environment={environment.upper()} wallet={self.wallet_address}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize CCXT Hyperliquid exchange: {e}")
            raise

        # Initialize official Hyperliquid SDK (for order placement)
        try:
            from hyperliquid.exchange import Exchange
            from hyperliquid.info import Info
            from eth_account import Account as EthAccount

            # Create eth_account wallet for SDK
            self.eth_wallet = EthAccount.from_key(private_key)

            # Initialize SDK Exchange
            self.sdk_exchange = Exchange(
                wallet=self.eth_wallet,
                base_url=self.api_url,
                account_address=self.wallet_address
            )

            # Initialize SDK Info (for querying user fills and historical orders)
            self.sdk_info = Info(
                base_url=self.api_url,
                skip_ws=True  # We don't need WebSocket for historical data queries
            )

            logger.info(
                f"Official SDK Exchange + Info initialized: account_id={account_id} "
                f"environment={environment.upper()} wallet={self.wallet_address}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Hyperliquid SDK: {e}")
            raise

    def _disable_hip3_markets(self) -> None:
        """Ensure HIP3 market fetching is disabled in ccxt."""
        try:
            fetch_markets_options = self.exchange.options.setdefault('fetchMarkets', {})
            hip3_options = fetch_markets_options.setdefault('hip3', {})
            hip3_options['enabled'] = False
            hip3_options['dex'] = []
        except Exception as options_error:
            logger.debug(f"Unable to update HIP3 fetch options: {options_error}")

        if hasattr(self.exchange, 'fetch_hip3_markets'):
            def _skip_hip3_markets(exchange_self, params=None):
                logger.debug("Skipping HIP3 market fetch per deployment requirements")
                return []
            self.exchange.fetch_hip3_markets = _skip_hip3_markets.__get__(self.exchange, type(self.exchange))
            logger.info("HIP3 market fetch disabled for Hyperliquid exchange instance")

    def _serialize_payload(self, payload: Optional[Any]) -> Optional[str]:
        if payload is None:
            return None
        try:
            return json.dumps(payload, default=str)
        except Exception:
            return str(payload)

    def _record_exchange_action(
        self,
        action_type: str,
        status: str,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        leverage: Optional[int] = None,
        size: Optional[float] = None,
        price: Optional[float] = None,
        request_payload: Optional[Any] = None,
        response_payload: Optional[Any] = None,
        error_message: Optional[str] = None,
        request_weight: int = 1,
    ) -> None:
        session = SessionLocal()
        try:
            size_decimal = Decimal(str(size)) if size is not None else None
            price_decimal = Decimal(str(price)) if price is not None else None
            notional_decimal = (
                size_decimal * price_decimal if size_decimal is not None and price_decimal is not None else None
            )

            entry = HyperliquidExchangeAction(
                account_id=self.account_id,
                environment=self.environment,
                wallet_address=self.wallet_address,
                action_type=action_type,
                status=status,
                symbol=symbol,
                side=side,
                leverage=leverage,
                size=size_decimal,
                price=price_decimal,
                notional=notional_decimal,
                request_weight=request_weight,
                request_payload=self._serialize_payload(request_payload),
                response_payload=self._serialize_payload(response_payload),
                error_message=error_message[:2000] if error_message else None,
            )
            session.add(entry)
            session.commit()
        except Exception as log_err:
            session.rollback()
            logger.warning(f"Failed to record Hyperliquid exchange action ({action_type}): {log_err}")
        finally:
            session.close()

    def _validate_environment(self, db: Session) -> bool:
        """
        Validate that account has a wallet configured for this environment

        Multi-wallet architecture: Each account can have separate testnet and mainnet wallets.
        This validates that the wallet for the current environment exists and is active.

        Args:
            db: Database session

        Returns:
            True if validation passes

        Raises:
            ValueError: If account not found or wallet not configured for this environment
        """
        from database.models import HyperliquidWallet

        account = db.query(Account).filter(Account.id == self.account_id).first()
        if not account:
            raise ValueError(f"Account {self.account_id} not found")

        # Check if wallet exists for this account and environment
        wallet = db.query(HyperliquidWallet).filter(
            HyperliquidWallet.account_id == self.account_id,
            HyperliquidWallet.environment == self.environment
        ).first()

        if not wallet:
            raise ValueError(
                f"No {self.environment} wallet configured for account {account.name}. "
                f"Please configure a wallet before trading."
            )

        return True

    def get_account_state(self, db: Session) -> Dict[str, Any]:
        """
        Get current account state from Hyperliquid

        Returns account equity, available balance, margin usage, etc.

        Args:
            db: Database session

        Returns:
            Dict with:
                - environment: "testnet" or "mainnet"
                - account_id: Database account ID
                - total_equity: Total account value
                - available_balance: Available for new positions
                - used_margin: Margin currently used
                - maintenance_margin: Required maintenance margin
                - margin_usage_percent: Used margin / Total equity * 100
                - withdrawal_available: Amount available for withdrawal

        Raises:
            EnvironmentMismatchError: If environment validation fails
        """
        self._validate_environment(db)

        try:
            logger.info(f"Fetching account state for account {self.account_id} on {self.environment}")

            # Use CCXT's fetchBalance to get account info
            balance = self.exchange.fetch_balance()

            # CCXT balance structure: {'free': {...}, 'used': {...}, 'total': {...}, 'info': {...}}
            # Extract USDC balance (Hyperliquid uses USDC)
            total_equity = float(balance.get('total', {}).get('USDC', 0) or 0)
            used_margin = float(balance.get('used', {}).get('USDC', 0) or 0)
            available_balance = float(balance.get('free', {}).get('USDC', 0) or 0)

            # Calculate margin usage percentage
            margin_usage_percent = (used_margin / total_equity * 100) if total_equity > 0 else 0

            result = {
                'environment': self.environment,
                'account_id': self.account_id,
                'total_equity': total_equity,
                'available_balance': available_balance,
                'used_margin': used_margin,
                'maintenance_margin': used_margin * 0.5,  # Estimate: maintenance = 50% of initial
                'margin_usage_percent': margin_usage_percent,
                'withdrawal_available': available_balance,
                'wallet_address': self.wallet_address,
                'timestamp': int(time.time() * 1000)
            }

            logger.debug(f"Account state: equity=${result['total_equity']:.2f}, available=${result['available_balance']:.2f}")
            update_account_state_cache(self.account_id, result, self.environment)
            self._record_exchange_action(
                action_type="fetch_account_state",
                status="success",
                symbol=None,
                request_payload={
                    "account_id": self.account_id,
                    "environment": self.environment,
                },
                response_payload=None,
            )

            return result

        except Exception as e:
            self._record_exchange_action(
                action_type="fetch_account_state",
                status="error",
                symbol=None,
                request_payload={
                    "account_id": self.account_id,
                    "environment": self.environment,
                },
                response_payload=None,
                error_message=str(e),
            )
            logger.error(f"Failed to get account state: {e}", exc_info=True)
            raise

    def get_positions(self, db: Session) -> List[Dict[str, Any]]:
        """
        Get all open positions from Hyperliquid with timing information

        Args:
            db: Database session

        Returns:
            List of position dicts, each with:
                - coin: Symbol name (e.g., "BTC")
                - szi: Position size (signed: positive=long, negative=short)
                - entry_px: Average entry price
                - position_value: Current position value
                - unrealized_pnl: Unrealized profit/loss
                - margin_used: Margin used for this position
                - liquidation_px: Liquidation price
                - leverage: Current leverage
                - opened_at: Timestamp when position was opened (milliseconds)
                - opened_at_str: Human-readable opened time
                - holding_duration_seconds: How long position has been held
                - holding_duration_str: Human-readable holding duration

        Raises:
            EnvironmentMismatchError: If environment validation fails
        """
        self._validate_environment(db)

        try:
            logger.info(f"Fetching positions for account {self.account_id} on {self.environment}")

            # Use CCXT's fetchPositions to get all positions
            positions_raw = self.exchange.fetch_positions()

            # Debug: Print all raw positions data to console
            print(f"=== CCXT RAW POSITIONS DATA ===")
            print(positions_raw)
            print(f"=== END CCXT RAW DATA ===")
            logger.info(f"CCXT RAW POSITIONS DATA: {positions_raw}")

            # Get user fills to calculate position opened times
            user_fills = []
            try:
                user_fills = self._get_user_fills(db)
                logger.info(f"Retrieved {len(user_fills)} user fills for position timing calculation")
            except Exception as fills_error:
                logger.warning(f"Failed to get user fills for position timing: {fills_error}")
                # Continue without timing information

            # Transform CCXT positions to our format
            positions = []
            for pos in positions_raw:
                info_position = (pos.get('info') or {}).get('position') or {}
                raw_size = info_position.get('szi')
                try:
                    position_size = float(raw_size)
                except (TypeError, ValueError):
                    position_size = 0.0
                side = pos.get('side', '').capitalize()

                coin = info_position.get('coin')

                # Calculate position timing
                opened_at = None
                opened_at_str = None
                holding_duration_seconds = None
                holding_duration_str = None

                if user_fills and coin and abs(position_size) > 1e-8:
                    opened_at = self._calculate_position_opened_time(coin, position_size, user_fills)
                    if opened_at:
                        from datetime import datetime, timezone
                        import time as time_module

                        # Use UTC time (consistent with session context display)
                        utc_dt = datetime.fromtimestamp(opened_at / 1000, tz=timezone.utc)
                        opened_at_str = utc_dt.strftime('%Y-%m-%d %H:%M:%S UTC')

                        # Calculate holding duration
                        current_time_ms = int(time_module.time() * 1000)
                        holding_duration_seconds = (current_time_ms - opened_at) / 1000

                        # Format duration as human-readable
                        hours = int(holding_duration_seconds // 3600)
                        minutes = int((holding_duration_seconds % 3600) // 60)
                        if hours > 0:
                            holding_duration_str = f"{hours}h {minutes}m"
                        else:
                            holding_duration_str = f"{minutes}m"

                positions.append({
                    'coin': coin,
                    'szi': position_size,  # Correct signed size
                    'entry_px': float(info_position.get('entryPx', 0)),
                    'position_value': float(info_position.get('positionValue', 0)),
                    'unrealized_pnl': float(info_position.get('unrealizedPnl', 0)),
                    'margin_used': float(info_position.get('marginUsed', 0)),
                    'liquidation_px': float(info_position.get('liquidationPx') or 0),
                    'leverage': float((info_position.get('leverage') or {}).get('value', 0)),
                    'side': side,  # Correct direction from CCXT

                    # Position timing information (NEW)
                    'opened_at': opened_at,
                    'opened_at_str': opened_at_str,
                    'holding_duration_seconds': holding_duration_seconds,
                    'holding_duration_str': holding_duration_str,

                    # Hyperliquid specific fields
                    'return_on_equity': float(info_position.get('returnOnEquity', 0)),
                    'max_leverage': float(info_position.get('maxLeverage', 0)),
                    'cum_funding_all_time': float((info_position.get('cumFunding') or {}).get('allTime', 0)),
                    'cum_funding_since_open': float((info_position.get('cumFunding') or {}).get('sinceOpen', 0)),
                    'leverage_type': (info_position.get('leverage') or {}).get('type'),

                    # CCXT calculated fields
                    'notional': float(pos.get('notional', 0)),
                    'percentage': float(pos.get('percentage', 0)),
                    'contract_size': float(pos.get('contractSize', 1)),
                    'margin_mode': pos.get('marginMode', '')
                })

            logger.debug(f"Found {len(positions)} open positions")
            update_positions_cache(self.account_id, positions, self.environment)
            self._record_exchange_action(
                action_type="fetch_positions",
                status="success",
                symbol=None,
                request_payload={
                    "account_id": self.account_id,
                    "environment": self.environment,
                },
                response_payload=None,
            )

            return positions

        except Exception as e:
            self._record_exchange_action(
                action_type="fetch_positions",
                status="error",
                symbol=None,
                request_payload={
                    "account_id": self.account_id,
                    "environment": self.environment,
                },
                response_payload=None,
                error_message=str(e),
            )
            logger.error(f"Failed to get positions: {e}", exc_info=True)
            raise

    def _get_user_fills(self, db: Session) -> List[Dict[str, Any]]:
        """
        Get all user fills (trade executions) from Hyperliquid SDK

        This method uses Hyperliquid SDK's Info.user_fills() to retrieve
        ALL historical trade executions for this wallet address.

        Args:
            db: Database session (for environment validation)

        Returns:
            List of fill dicts with fields:
                - coin: Symbol name
                - side: "A" (ask/sell) or "B" (bid/buy)
                - px: Execution price
                - sz: Size filled
                - time: Execution timestamp (milliseconds)
                - startPosition: Position before this fill
                - dir: Direction ("Open Long", "Close Long", etc.)
                - closedPnl: Realized PnL if position closed
                - oid: Order ID

        Raises:
            EnvironmentMismatchError: If environment validation fails
        """
        self._validate_environment(db)

        try:
            logger.info(f"Fetching user fills for wallet {self.wallet_address} on {self.environment}")

            # Use SDK Info to get all user fills
            fills = self.sdk_info.user_fills(self.wallet_address)

            logger.debug(f"Retrieved {len(fills)} fills for wallet {self.wallet_address}")

            self._record_exchange_action(
                action_type="fetch_user_fills",
                status="success",
                symbol=None,
                request_payload={
                    "account_id": self.account_id,
                    "wallet_address": self.wallet_address,
                    "environment": self.environment,
                },
                response_payload=None,
            )

            return fills

        except Exception as e:
            self._record_exchange_action(
                action_type="fetch_user_fills",
                status="error",
                symbol=None,
                request_payload={
                    "account_id": self.account_id,
                    "wallet_address": self.wallet_address,
                    "environment": self.environment,
                },
                response_payload=None,
                error_message=str(e),
            )
            logger.error(f"Failed to get user fills: {e}", exc_info=True)
            raise

    def _get_historical_orders(self, db: Session) -> List[Dict[str, Any]]:
        """
        Get historical orders from Hyperliquid SDK

        This method uses Hyperliquid SDK's Info.historical_orders() to retrieve
        up to 2000 most recent orders for this wallet address.

        Args:
            db: Database session (for environment validation)

        Returns:
            List of order dicts with status, fills, and execution details

        Raises:
            EnvironmentMismatchError: If environment validation fails
        """
        self._validate_environment(db)

        try:
            logger.info(f"Fetching historical orders for wallet {self.wallet_address} on {self.environment}")

            # Use SDK Info to get historical orders (up to 2000 most recent)
            orders = self.sdk_info.historical_orders(self.wallet_address)

            logger.debug(f"Retrieved {len(orders)} historical orders for wallet {self.wallet_address}")

            self._record_exchange_action(
                action_type="fetch_historical_orders",
                status="success",
                symbol=None,
                request_payload={
                    "account_id": self.account_id,
                    "wallet_address": self.wallet_address,
                    "environment": self.environment,
                },
                response_payload=None,
            )

            return orders

        except Exception as e:
            self._record_exchange_action(
                action_type="fetch_historical_orders",
                status="error",
                symbol=None,
                request_payload={
                    "account_id": self.account_id,
                    "wallet_address": self.wallet_address,
                    "environment": self.environment,
                },
                response_payload=None,
                error_message=str(e),
            )
            logger.error(f"Failed to get historical orders: {e}", exc_info=True)
            raise

    def _calculate_position_opened_time(self, symbol: str, current_position_size: float, fills: List[Dict[str, Any]]) -> Optional[int]:
        """
        Calculate when a position was opened based on user fills

        This method walks backwards through fills starting from the current position,
        subtracting each fill's effect until we reach the point where the position
        was first opened (when going back further would cross zero or change direction).

        Args:
            symbol: Asset symbol (e.g., "BTC")
            current_position_size: Current position size (signed: positive=long, negative=short)
            fills: List of all user fills (from _get_user_fills)

        Returns:
            Timestamp in milliseconds when position was first opened,
            or None if no fills found for this symbol
        """
        if not fills or abs(current_position_size) < 1e-8:
            return None

        # Filter fills for this symbol and sort by time (newest first)
        symbol_fills = [f for f in fills if f.get('coin') == symbol]
        symbol_fills.sort(key=lambda x: x.get('time', 0), reverse=True)

        if not symbol_fills:
            return None

        # Start from current position and walk backwards
        # Subtract each fill's effect to find when position started
        position_tracker = current_position_size
        earliest_time = None

        for fill in symbol_fills:
            sz = float(fill.get('sz', 0))
            side = fill.get('side', '')

            # Calculate what the position was BEFORE this fill
            # side "B" = buy (adds to position), "A" = sell (reduces position)
            if side == "B":
                position_before = position_tracker - sz
            elif side == "A":
                position_before = position_tracker + sz
            else:
                continue

            # Check if going back past this fill would cross zero or change direction
            # If so, this fill is where the current position started
            if abs(position_before) < 1e-8:
                # Position was zero before this fill - this is the opening fill
                earliest_time = fill.get('time')
                break
            elif (position_tracker > 0 and position_before < 0) or (position_tracker < 0 and position_before > 0):
                # Position changed direction - this fill opened the current position
                earliest_time = fill.get('time')
                break
            else:
                # This fill is part of the current position, keep going back
                earliest_time = fill.get('time')
                position_tracker = position_before

        return earliest_time

    def get_recent_closed_trades(self, db: Session, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get recent closed trades summary from historical orders

        This method analyzes historical orders to find recently closed positions
        and returns a summary with:
        - Symbol
        - Entry/exit time and prices
        - Holding duration
        - Realized PnL
        - Direction (long/short)

        Args:
            db: Database session (for environment validation)
            limit: Maximum number of closed trades to return (default 5)

        Returns:
            List of closed trade summaries, sorted by close time (most recent first)

        Raises:
            EnvironmentMismatchError: If environment validation fails
        """
        self._validate_environment(db)

        try:
            # Get user fills which contain closedPnl information
            fills = self._get_user_fills(db)

            # Filter for fills that closed positions (have closedPnl)
            closed_fills = []
            for fill in fills:
                closed_pnl = fill.get('closedPnl')
                if closed_pnl and closed_pnl != '0.0':
                    closed_fills.append(fill)

            # Sort by time (newest first) and limit
            closed_fills.sort(key=lambda x: x.get('time', 0), reverse=True)
            closed_fills = closed_fills[:limit]

            # Build trade summaries
            trades = []
            for fill in closed_fills:
                from datetime import datetime, timezone

                close_time_ms = fill.get('time', 0)
                # Use UTC time (consistent with session context display)
                utc_dt = datetime.fromtimestamp(close_time_ms / 1000, tz=timezone.utc)
                close_time = utc_dt.strftime('%Y-%m-%d %H:%M:%S UTC')

                trade = {
                    'symbol': fill.get('coin'),
                    'side': 'Long' if fill.get('side') == 'A' else 'Short',  # Closing long = selling (A)
                    'close_price': float(fill.get('px', 0)),
                    'size': float(fill.get('sz', 0)),
                    'close_time': close_time,
                    'close_timestamp': close_time_ms,
                    'realized_pnl': float(fill.get('closedPnl', 0)),
                    'direction': fill.get('dir', ''),
                }

                trades.append(trade)

            logger.info(f"Found {len(trades)} recent closed trades")
            return trades

        except Exception as e:
            logger.error(f"Failed to get recent closed trades: {e}", exc_info=True)
            return []

    def get_open_orders(self, db: Session) -> List[Dict[str, Any]]:
        """
        Get current open orders (unfilled/partially filled orders)

        This method uses Hyperliquid SDK's Info.frontend_open_orders() to retrieve
        all open orders with complete frontend information including trigger conditions,
        TP/SL flags, and order types.

        Args:
            db: Database session (for environment validation)

        Returns:
            List of open order dicts with fields:
                - order_id: Order ID
                - symbol: Symbol name
                - side: "Buy" or "Sell"
                - direction: "Close Short", "Close Long", "Open Long", "Open Short"
                - order_type: Order type (e.g., "Stop Limit", "Take Profit Limit", "Limit")
                - size: Current remaining size
                - original_size: Original order size
                - price: Limit price
                - order_value: Calculated order value (size * price)
                - reduce_only: Whether this is a reduce-only order
                - is_trigger: Whether this is a trigger order
                - trigger_condition: Trigger condition string (e.g., "Price above 87500")
                - trigger_price: Trigger price
                - is_position_tpsl: Whether this is a position-level TP/SL
                - tif: Time in force (may be null for trigger orders)
                - order_time: Order placement time (UTC string)
                - timestamp: Order placement timestamp (milliseconds)

        Raises:
            EnvironmentMismatchError: If environment validation fails
        """
        self._validate_environment(db)

        try:
            logger.info(f"Fetching open orders for wallet {self.wallet_address} on {self.environment}")

            # Use SDK Info to get frontend open orders (includes trigger conditions, TP/SL info)
            raw_orders = self.sdk_info.frontend_open_orders(self.wallet_address)

            # Transform to simplified format for AI prompt
            orders = []
            for order in raw_orders:
                from datetime import datetime, timezone

                # Parse order timestamp
                timestamp_ms = order.get('timestamp', 0)
                utc_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
                order_time = utc_dt.strftime('%Y-%m-%d %H:%M:%S UTC')

                # Determine direction based on side and reduce_only
                side_raw = order.get('side', '')
                reduce_only = order.get('reduceOnly', False)

                if side_raw == 'B':  # Buy
                    side = 'Buy'
                    direction = 'Close Short' if reduce_only else 'Open Long'
                else:  # 'A' = Ask/Sell
                    side = 'Sell'
                    direction = 'Close Long' if reduce_only else 'Open Short'

                # Calculate order value
                size = float(order.get('sz', 0))
                price = float(order.get('limitPx', 0))
                order_value = size * price

                # Extract trigger information
                trigger_condition = order.get('triggerCondition', '')
                trigger_price = order.get('triggerPx')

                order_summary = {
                    'order_id': order.get('oid'),
                    'symbol': order.get('coin', ''),
                    'side': side,
                    'direction': direction,
                    'order_type': order.get('orderType', 'Limit'),
                    'size': size,
                    'original_size': float(order.get('origSz', 0)),
                    'price': price,
                    'order_value': order_value,
                    'reduce_only': reduce_only,
                    'is_trigger': order.get('isTrigger', False),
                    'trigger_condition': trigger_condition if trigger_condition else None,
                    'trigger_price': float(trigger_price) if trigger_price else None,
                    'is_position_tpsl': order.get('isPositionTpsl', False),
                    'tif': order.get('tif'),
                    'order_time': order_time,
                    'timestamp': timestamp_ms,
                }

                orders.append(order_summary)

            # Sort by timestamp (newest first)
            orders.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

            logger.info(f"Found {len(orders)} open orders")

            self._record_exchange_action(
                action_type="fetch_open_orders",
                status="success",
                symbol=None,
                request_payload={
                    "account_id": self.account_id,
                    "wallet_address": self.wallet_address,
                    "environment": self.environment,
                },
                response_payload=None,
            )

            return orders

        except Exception as e:
            self._record_exchange_action(
                action_type="fetch_open_orders",
                status="error",
                symbol=None,
                request_payload={
                    "account_id": self.account_id,
                    "wallet_address": self.wallet_address,
                    "environment": self.environment,
                },
                response_payload=None,
                error_message=str(e),
            )
            logger.error(f"Failed to get open orders: {e}", exc_info=True)
            return []

    def place_order(
        self,
        db: Session,
        symbol: str,
        is_buy: bool,
        size: float,
        order_type: str = "market",
        price: Optional[float] = None,
        reduce_only: bool = False,
        leverage: int = 1
    ) -> Dict[str, Any]:
        """
        Place order on Hyperliquid

        Args:
            db: Database session
            symbol: Asset symbol (e.g., "BTC")
            is_buy: True for long, False for short
            size: Order quantity (absolute value)
            order_type: "market" or "limit"
            price: Limit price (required for limit orders)
            reduce_only: Only close existing positions
            leverage: Position leverage (1-50)

        Returns:
            Dict with:
                - status: "resting" | "filled" | "error"
                - oid: Order ID (if resting)
                - filled: Execution details (if filled)
                - error: Error message (if error)

        Raises:
            EnvironmentMismatchError: If environment validation fails
            ValueError: If parameters invalid
        """
        self._validate_environment(db)

        # Validate parameters
        if order_type not in ["market", "limit"]:
            raise ValueError(f"Invalid order_type: {order_type}")

        if order_type == "limit" and price is None:
            raise ValueError("Limit orders require price parameter")

        if leverage < 1 or leverage > 50:
            raise ValueError(f"Invalid leverage: {leverage}. Must be 1-50")

        if size <= 0:
            raise ValueError(f"Invalid size: {size}. Must be positive")

        # Log order attempt with environment
        logger.warning(
            f"PLACING ORDER on {self.environment.upper()}: "
            f"account={self.account_id} {symbol} {'BUY' if is_buy else 'SELL'} "
            f"size={size} leverage={leverage}x type={order_type} reduce_only={reduce_only}"
        )

        action_payload: Optional[Dict[str, Any]] = None

        try:
            # Set leverage before placing order (if different from current)
            try:
                self.exchange.set_leverage(leverage, f"{symbol}/USDC:USDC")
                logger.debug(f"Set leverage to {leverage}x for {symbol}")
                self._record_exchange_action(
                    action_type="set_leverage",
                    status="success",
                    symbol=symbol,
                    leverage=leverage,
                    request_payload={"symbol": symbol, "leverage": leverage},
                )
            except Exception as lev_err:
                logger.warning(f"Failed to set leverage (may already be set): {lev_err}")
                self._record_exchange_action(
                    action_type="set_leverage",
                    status="error",
                    symbol=symbol,
                    leverage=leverage,
                    request_payload={"symbol": symbol, "leverage": leverage},
                    error_message=str(lev_err),
                )

            # Prepare CCXT order parameters
            # Hyperliquid perpetual contract format: BASE/QUOTE:SETTLE
            ccxt_symbol = f"{symbol}/USDC:USDC"  # Hyperliquid perpetual format
            logger.debug(f"Using symbol format: {ccxt_symbol}")
            ccxt_type = order_type  # "market" or "limit"
            ccxt_side = "buy" if is_buy else "sell"
            ccxt_amount = size

            # Hyperliquid market orders require price parameter to calculate slippage protection
            # CCXT will use price * (1 +/- 5% slippage) as the max acceptable execution price
            # For limit orders, price is the exact limit price
            # For market orders, price is the reference price for slippage calculation
            if order_type == "market" and price is None:
                # If no price provided for market order, fetch current market price
                try:
                    ticker = self.exchange.fetch_ticker(ccxt_symbol)
                    price = ticker['last']
                    logger.debug(f"Fetched current price for market order: {price}")
                except Exception as e:
                    raise ValueError(f"Market order requires price parameter or valid market price. Error: {e}")

            ccxt_price = price

            # Additional parameters for Hyperliquid
            params = {
                'reduceOnly': reduce_only
            }

            logger.debug(
                f"CCXT order params: symbol={ccxt_symbol} type={ccxt_type} "
                f"side={ccxt_side} amount={ccxt_amount} price={ccxt_price} params={params}"
            )

            action_payload = {
                'symbol': ccxt_symbol,
                'side': ccxt_side,
                'amount': ccxt_amount,
                'price': ccxt_price,
                'order_type': ccxt_type,
                'params': params
            }

            # Place order via CCXT
            order = self.exchange.create_order(
                symbol=ccxt_symbol,
                type=ccxt_type,
                side=ccxt_side,
                amount=ccxt_amount,
                price=ccxt_price,
                params=params
            )

            # DEBUG: Print raw CCXT order response
            logger.warning(f"[DEBUG] CCXT Raw Order Response: {order}")

            # Parse CCXT order response
            order_id = order.get('id')
            order_status = order.get('status')  # "open", "closed", "canceled"
            filled_amount = float(order.get('filled') or 0)
            average_price = float(order.get('average') or 0) if order.get('average') else None

            # Map CCXT status to our status
            # First check for Hyperliquid-specific errors
            hyperliquid_info = order.get('info', {})
            hyperliquid_response = hyperliquid_info.get('response', {})
            hyperliquid_data = hyperliquid_response.get('data', {})
            hyperliquid_statuses = hyperliquid_data.get('statuses', [])

            # Check for errors in Hyperliquid response
            hyperliquid_error = None
            if hyperliquid_statuses:
                for status_item in hyperliquid_statuses:
                    if 'error' in status_item:
                        hyperliquid_error = status_item['error']
                        break

            if hyperliquid_error:
                # Hyperliquid returned an error
                status = 'error'
                error_msg = hyperliquid_error
            else:
                # Check for successful execution
                hyperliquid_filled = hyperliquid_info.get('filled')
                logger.warning(f"[DEBUG] hyperliquid_filled: {hyperliquid_filled}")

                if hyperliquid_filled and hyperliquid_filled.get('totalSz'):
                    # Hyperliquid shows filled info, order was executed
                    status = 'filled'
                    error_msg = None
                    # Update filled_amount and average_price from Hyperliquid data
                    filled_amount = float(hyperliquid_filled.get('totalSz', 0))
                    average_price = float(hyperliquid_filled.get('avgPx', 0))
                elif order_status == 'closed' or (filled_amount > 0 and filled_amount >= ccxt_amount * 0.99):
                    # CCXT shows closed or nearly fully filled
                    status = 'filled'
                    error_msg = None
                elif order_status == 'open':
                    # Order is on the book
                    status = 'resting'
                    error_msg = None
                elif order_status == 'canceled':
                    # Order was canceled
                    status = 'canceled'
                    error_msg = None
                else:
                    # Unknown status
                    status = 'error'
                    error_msg = f"Unknown order status: {order_status}"

            result = {
                'status': status,
                'environment': self.environment,
                'symbol': symbol,
                'is_buy': is_buy,
                'size': size,
                'leverage': leverage,
                'order_type': order_type,
                'reduce_only': reduce_only,
                'order_id': order_id,
                'filled_amount': filled_amount,
                'average_price': average_price,
                'raw_order': order,  # Full CCXT response for debugging
                'wallet_address': self.wallet_address,
                'timestamp': int(time.time() * 1000)
            }

            # Add error message if present
            if error_msg:
                result['error'] = error_msg

            logger.info(
                f"Order result: status={status} order_id={order_id} "
                f"filled={filled_amount}/{size} avg_price={average_price}"
            )

            self._record_exchange_action(
                action_type="create_order",
                status="success" if status != 'error' else 'error',
                symbol=symbol,
                side=ccxt_side,
                leverage=leverage,
                size=ccxt_amount,
                price=ccxt_price,
                request_payload=action_payload,
                response_payload=order,
                error_message=result.get('error'),
            )

            return result

        except Exception as e:
            self._record_exchange_action(
                action_type="create_order",
                status="error",
                symbol=symbol,
                side="buy" if is_buy else "sell",
                leverage=leverage,
                size=size,
                price=price,
                request_payload=locals().get('action_payload'),
                response_payload=None,
                error_message=str(e),
            )
            logger.error(f"Failed to place order: {e}", exc_info=True)
            return {
                'status': 'error',
                'error': str(e),
                'environment': self.environment,
                'symbol': symbol
            }

    def set_leverage(self, db: Session, symbol: str, leverage: int) -> bool:
        """
        Set leverage for a specific asset

        Args:
            db: Database session
            symbol: Asset symbol (e.g., "BTC")
            leverage: Leverage to set (1-50)

        Returns:
            True if successful

        Raises:
            EnvironmentMismatchError: If environment validation fails
            ValueError: If leverage invalid
        """
        self._validate_environment(db)

        if leverage < 1 or leverage > 50:
            raise ValueError(f"Invalid leverage: {leverage}. Must be 1-50")

        try:
            logger.info(f"Setting leverage for {symbol} to {leverage}x on {self.environment}")

            # TODO: Implement actual Hyperliquid leverage setting
            # For reference, Hyperliquid exchange endpoint:
            # POST /exchange with action type "updateLeverage"

            return True

        except Exception as e:
            logger.error(f"Failed to set leverage: {e}")
            raise

    def cancel_order(self, db: Session, order_id: Any, symbol: str) -> bool:
        """
        Cancel an open order using Hyperliquid SDK

        Args:
            db: Database session
            order_id: Hyperliquid order ID (oid) - can be int or string
            symbol: Asset symbol

        Returns:
            True if successful

        Raises:
            EnvironmentMismatchError: If environment validation fails
        """
        self._validate_environment(db)

        try:
            # Ensure order_id is an integer (SDK requires int)
            if isinstance(order_id, str):
                order_id = int(order_id)
            
            logger.info(f"[CANCEL] Cancelling order {order_id} (type={type(order_id).__name__}) for {symbol} on {self.environment}")

            # Use SDK to cancel order
            result = self.sdk_exchange.cancel(symbol, order_id)
            
            logger.info(f"[CANCEL] SDK cancel result: {result}")
            
            # Check for success - SDK returns {"status": "ok", "response": {"type": "cancel", "data": {"statuses": ["success"]}}}
            if result.get("status") == "ok":
                response_data = result.get("response", {})
                if isinstance(response_data, dict):
                    statuses = response_data.get("data", {}).get("statuses", [])
                    if statuses and statuses[0] == "success":
                        logger.info(f"[CANCEL] Successfully cancelled order {order_id} for {symbol}")
                        self._record_exchange_action(
                            action_type="cancel_order",
                            status="success",
                            symbol=symbol,
                            request_payload={"order_id": order_id, "symbol": symbol},
                            response_payload=result,
                        )
                        return True
                    elif statuses and "error" in str(statuses[0]).lower():
                        error_msg = statuses[0]
                        logger.error(f"[CANCEL] Failed to cancel order {order_id}: {error_msg}")
                        self._record_exchange_action(
                            action_type="cancel_order",
                            status="error",
                            symbol=symbol,
                            request_payload={"order_id": order_id, "symbol": symbol},
                            response_payload=result,
                            error_message=str(error_msg),
                        )
                        return False
                
                # If we got here with status "ok", assume success
                logger.info(f"[CANCEL] Order {order_id} cancelled (status=ok)")
                self._record_exchange_action(
                    action_type="cancel_order",
                    status="success",
                    symbol=symbol,
                    request_payload={"order_id": order_id, "symbol": symbol},
                    response_payload=result,
                )
                return True
            else:
                error_msg = result.get("response", "Unknown error")
                self._record_exchange_action(
                    action_type="cancel_order",
                    status="error",
                    symbol=symbol,
                    request_payload={"order_id": order_id, "symbol": symbol},
                    response_payload=result,
                    error_message=str(error_msg),
                )
                logger.error(f"[CANCEL] Failed to cancel order {order_id}: {error_msg}")
                return False

        except ValueError as ve:
            logger.error(f"[CANCEL] Invalid order_id format: {order_id} - {ve}")
            self._record_exchange_action(
                action_type="cancel_order",
                status="error",
                symbol=symbol,
                request_payload={"order_id": order_id, "symbol": symbol},
                error_message=f"Invalid order_id format: {ve}",
            )
            return False
        except Exception as e:
            self._record_exchange_action(
                action_type="cancel_order",
                status="error",
                symbol=symbol,
                request_payload={"order_id": order_id, "symbol": symbol},
                error_message=str(e),
            )
            logger.error(f"[CANCEL] Failed to cancel order: {e}", exc_info=True)
            raise

    def get_open_orders(self, db: Session, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all open orders (including TP/SL trigger orders) from Hyperliquid

        Args:
            db: Database session
            symbol: Optional symbol filter (e.g., "BTC"). If None, returns all symbols.

        Returns:
            List of open order dicts, each with:
                - oid: Order ID
                - coin: Symbol name
                - side: "B" (buy) or "A" (sell/ask)
                - sz: Order size
                - limitPx: Limit price
                - orderType: Order type info
                - triggerPx: Trigger price (for TP/SL orders)
                - tpsl: "tp" or "sl" (for TP/SL orders)
                - reduceOnly: Whether order is reduce-only

        Raises:
            EnvironmentMismatchError: If environment validation fails
        """
        self._validate_environment(db)

        try:
            logger.info(f"Fetching open orders for wallet {self.wallet_address} on {self.environment}")

            # Use SDK Info to get open orders (frontend_open_orders includes trigger orders)
            open_orders = self.sdk_info.frontend_open_orders(self.wallet_address)

            logger.debug(f"Retrieved {len(open_orders)} open orders for wallet {self.wallet_address}")

            # Filter by symbol if specified
            if symbol:
                open_orders = [o for o in open_orders if o.get('coin') == symbol]
                logger.debug(f"Filtered to {len(open_orders)} orders for symbol {symbol}")

            self._record_exchange_action(
                action_type="fetch_open_orders",
                status="success",
                symbol=symbol,
                request_payload={
                    "account_id": self.account_id,
                    "wallet_address": self.wallet_address,
                    "symbol_filter": symbol,
                },
                response_payload=None,
            )

            return open_orders

        except Exception as e:
            self._record_exchange_action(
                action_type="fetch_open_orders",
                status="error",
                symbol=symbol,
                request_payload={
                    "account_id": self.account_id,
                    "wallet_address": self.wallet_address,
                    "symbol_filter": symbol,
                },
                error_message=str(e),
            )
            logger.error(f"Failed to get open orders: {e}", exc_info=True)
            raise

    def get_tpsl_orders(self, db: Session, symbol: str) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Get current TP and SL orders for a specific symbol

        Args:
            db: Database session
            symbol: Asset symbol (e.g., "BTC")

        Returns:
            Dict with:
                - tp: TP order dict or None (most recent if multiple exist)
                - sl: SL order dict or None (most recent if multiple exist)
                - all_tp_orders: List of ALL TP orders found
                - all_sl_orders: List of ALL SL orders found
        """
        open_orders = self.get_open_orders(db, symbol)
        
        # Debug: log all open orders to understand structure
        import sys
        print(f"[TPSL DEBUG] {symbol} - Found {len(open_orders)} open orders", file=sys.stderr, flush=True)
        logger.info(f"[TPSL DEBUG] {symbol} - Found {len(open_orders)} open orders")
        for i, order in enumerate(open_orders):
            print(f"[TPSL DEBUG] Order {i}: {order}", file=sys.stderr, flush=True)
            logger.info(f"[TPSL DEBUG] Order {i}: {order}")
        
        # Collect ALL TP and SL orders (not just the first one)
        all_tp_orders = []
        all_sl_orders = []
        
        for order in open_orders:
            order_type = order.get('orderType', {})
            is_trigger = order.get('isTrigger', False)
            trigger_px = order.get('triggerPx')
            trigger_condition = order.get('triggerCondition', '')
            
            # Debug: log order type structure
            logger.debug(f"[TPSL DEBUG] Order type: {order_type}, type={type(order_type)}, isTrigger={is_trigger}")
            
            # Determine if this is a TP or SL order
            # Support BOTH formats:
            # 1. Dict format: orderType = {"trigger": {"tpsl": "tp", "triggerPx": ...}}
            # 2. String format: orderType = "Take Profit Limit" or "Stop Limit"
            
            tpsl_type = None
            trigger_price = None
            
            # Format 1: Dict with trigger info
            if isinstance(order_type, dict) and 'trigger' in order_type:
                trigger_info = order_type.get('trigger', {})
                tpsl_type = trigger_info.get('tpsl')
                trigger_price = float(trigger_info.get('triggerPx', 0))
                logger.info(f"[TPSL DEBUG] Found dict trigger order: tpsl={tpsl_type}, trigger_price={trigger_price}")
            
            # Format 2: String orderType (from frontend_open_orders)
            elif isinstance(order_type, str) and is_trigger:
                # Parse orderType string: "Take Profit Limit" or "Stop Limit"
                order_type_lower = order_type.lower()
                if 'take profit' in order_type_lower:
                    tpsl_type = 'tp'
                elif 'stop' in order_type_lower and 'limit' in order_type_lower:
                    tpsl_type = 'sl'
                
                # Get trigger price from triggerPx field
                if trigger_px:
                    try:
                        trigger_price = float(trigger_px)
                    except (ValueError, TypeError):
                        trigger_price = 0
                
                logger.info(f"[TPSL DEBUG] Found string trigger order: orderType='{order_type}', tpsl={tpsl_type}, trigger_price={trigger_price}")
            
            # Format 3: Check triggerCondition as fallback
            elif is_trigger and trigger_condition:
                # Parse triggerCondition: "Price above 130" (TP) or "Price below 125.5" (SL)
                if 'above' in trigger_condition.lower():
                    tpsl_type = 'tp'
                elif 'below' in trigger_condition.lower():
                    tpsl_type = 'sl'
                
                if trigger_px:
                    try:
                        trigger_price = float(trigger_px)
                    except (ValueError, TypeError):
                        trigger_price = 0
                
                logger.info(f"[TPSL DEBUG] Found trigger by condition: condition='{trigger_condition}', tpsl={tpsl_type}, trigger_price={trigger_price}")
            
            # If we identified a TP or SL order, add it to the list
            if tpsl_type and trigger_price:
                order_dict = {
                    'oid': order.get('oid'),
                    'trigger_price': trigger_price,
                    'limit_price': float(order.get('limitPx', 0)),
                    'size': float(order.get('sz', 0)),
                    'side': order.get('side'),
                    'reduce_only': order.get('reduceOnly', True),
                    'timestamp': order.get('timestamp', 0),
                }
                
                if tpsl_type == 'tp':
                    all_tp_orders.append(order_dict)
                    logger.info(f"[TPSL DEBUG] Identified TP order: {order_dict}")
                elif tpsl_type == 'sl':
                    all_sl_orders.append(order_dict)
                    logger.info(f"[TPSL DEBUG] Identified SL order: {order_dict}")
        
        # Return the most recent order of each type (for backward compatibility)
        # but also include all orders for cleanup
        tp_order = all_tp_orders[0] if all_tp_orders else None
        sl_order = all_sl_orders[0] if all_sl_orders else None
        
        logger.info(f"[TPSL] {symbol} - Found {len(all_tp_orders)} TP orders, {len(all_sl_orders)} SL orders")
        logger.info(f"[TPSL] {symbol} - Primary TP={tp_order}, Primary SL={sl_order}")
        
        return {
            'tp': tp_order, 
            'sl': sl_order,
            'all_tp_orders': all_tp_orders,
            'all_sl_orders': all_sl_orders,
        }

    def update_tpsl(
        self,
        db: Session,
        symbol: str,
        new_tp_price: Optional[float] = None,
        new_sl_price: Optional[float] = None,
        position_size: Optional[float] = None,
        is_long: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Update TP and/or SL orders for an existing position

        This method:
        1. Gets current TP/SL orders from Hyperliquid API FIRST
        2. Compares existing prices with requested prices
        3. If prices match (within 0.1%) → SKIP entirely (no duplicate orders)
        4. If prices differ → Cancel old orders and place new ones
        5. Updates in-memory cache after successful operations

        Args:
            db: Database session
            symbol: Asset symbol (e.g., "BTC")
            new_tp_price: New take profit price (None to keep current or skip)
            new_sl_price: New stop loss price (None to keep current or skip)
            position_size: Position size for new orders (required if placing new orders)
            is_long: True if position is long, False if short (required for order direction)

        Returns:
            Dict with:
                - success: Boolean indicating overall success
                - tp_updated: Boolean indicating if TP was updated
                - sl_updated: Boolean indicating if SL was updated
                - old_tp: Previous TP price (if existed)
                - old_sl: Previous SL price (if existed)
                - new_tp: New TP price (if updated)
                - new_sl: New SL price (if updated)
                - errors: List of error messages (if any)
        """
        self._validate_environment(db)

        result = {
            'success': True,
            'tp_updated': False,
            'sl_updated': False,
            'old_tp': None,
            'old_sl': None,
            'new_tp': None,
            'new_sl': None,
            'errors': [],
        }

        # 0.1% threshold to account for rounding differences
        PRICE_CHANGE_THRESHOLD_PERCENT = 0.001  # 0.1%

        try:
            import sys
            
            # ============================================================
            # STEP 1: Get current TP/SL orders from Hyperliquid API FIRST
            # This is the source of truth - not the in-memory cache
            # ============================================================
            print(f"[TPSL UPDATE] {symbol} - Fetching current orders from Hyperliquid API...", file=sys.stderr, flush=True)
            logger.info(f"[TPSL UPDATE] {symbol} - Fetching current orders from Hyperliquid API")
            
            current_tpsl = self.get_tpsl_orders(db, symbol)
            current_tp = current_tpsl.get('tp')
            current_sl = current_tpsl.get('sl')
            all_tp_orders = current_tpsl.get('all_tp_orders', [])
            all_sl_orders = current_tpsl.get('all_sl_orders', [])

            # Extract current prices from API
            current_tp_price = current_tp.get('trigger_price') if current_tp else None
            current_sl_price = current_sl.get('trigger_price') if current_sl else None
            
            # Record old values
            result['old_tp'] = current_tp_price
            result['old_sl'] = current_sl_price
            
            print(f"[TPSL UPDATE] {symbol} - API returned: TP={current_tp_price}, SL={current_sl_price}", file=sys.stderr, flush=True)
            print(f"[TPSL UPDATE] {symbol} - Requested: TP={new_tp_price}, SL={new_sl_price}", file=sys.stderr, flush=True)
            print(f"[TPSL UPDATE] {symbol} - Found {len(all_tp_orders)} TP orders, {len(all_sl_orders)} SL orders", file=sys.stderr, flush=True)
            logger.info(f"[TPSL UPDATE] {symbol} - API: TP={current_tp_price}, SL={current_sl_price} | Requested: TP={new_tp_price}, SL={new_sl_price}")
            
            # ============================================================
            # STEP 2: Compare existing prices with requested prices
            # If they match within threshold → SKIP to avoid duplicates
            # ============================================================
            tp_matches_existing = False
            sl_matches_existing = False
            
            # Check if TP matches existing order
            if new_tp_price is not None and current_tp_price is not None and current_tp_price > 0:
                tp_diff_percent = abs(current_tp_price - new_tp_price) / current_tp_price
                if tp_diff_percent <= PRICE_CHANGE_THRESHOLD_PERCENT:
                    tp_matches_existing = True
                    print(f"[TPSL UPDATE] {symbol} TP MATCHES existing: {current_tp_price} ≈ {new_tp_price} (diff={tp_diff_percent:.4%}) - SKIP", file=sys.stderr, flush=True)
                    logger.info(f"[TPSL UPDATE] {symbol} TP matches existing order - SKIPPING to avoid duplicate")
                else:
                    print(f"[TPSL UPDATE] {symbol} TP DIFFERS: {current_tp_price} vs {new_tp_price} (diff={tp_diff_percent:.4%}) - WILL UPDATE", file=sys.stderr, flush=True)
                    logger.info(f"[TPSL UPDATE] {symbol} TP differs from existing - will update")
            elif new_tp_price is None:
                # No new TP requested, skip TP update
                tp_matches_existing = True
                print(f"[TPSL UPDATE] {symbol} No new TP requested - SKIP", file=sys.stderr, flush=True)
            
            # Check if SL matches existing order
            if new_sl_price is not None and current_sl_price is not None and current_sl_price > 0:
                sl_diff_percent = abs(current_sl_price - new_sl_price) / current_sl_price
                if sl_diff_percent <= PRICE_CHANGE_THRESHOLD_PERCENT:
                    sl_matches_existing = True
                    print(f"[TPSL UPDATE] {symbol} SL MATCHES existing: {current_sl_price} ≈ {new_sl_price} (diff={sl_diff_percent:.4%}) - SKIP", file=sys.stderr, flush=True)
                    logger.info(f"[TPSL UPDATE] {symbol} SL matches existing order - SKIPPING to avoid duplicate")
                else:
                    print(f"[TPSL UPDATE] {symbol} SL DIFFERS: {current_sl_price} vs {new_sl_price} (diff={sl_diff_percent:.4%}) - WILL UPDATE", file=sys.stderr, flush=True)
                    logger.info(f"[TPSL UPDATE] {symbol} SL differs from existing - will update")
            elif new_sl_price is None:
                # No new SL requested, skip SL update
                sl_matches_existing = True
                print(f"[TPSL UPDATE] {symbol} No new SL requested - SKIP", file=sys.stderr, flush=True)
            
            # ============================================================
            # STEP 3: If BOTH match existing orders → SKIP ENTIRELY
            # ============================================================
            if tp_matches_existing and sl_matches_existing:
                print(f"[TPSL UPDATE] {symbol} - BOTH TP and SL match existing orders - SKIPPING UPDATE ENTIRELY", file=sys.stderr, flush=True)
                logger.info(f"[TPSL UPDATE] {symbol} - Both TP and SL match existing orders, SKIPPING update entirely")
                
                # Update cache with current values from API
                _set_cached_tpsl(self.wallet_address, symbol, current_tp_price, current_sl_price)
                
                return result

            # Get position info if not provided
            if position_size is None or is_long is None:
                positions = self.get_positions(db)
                position = next((p for p in positions if p.get('coin') == symbol), None)
                if position:
                    position_size = abs(position.get('szi', 0))
                    is_long = position.get('szi', 0) > 0
                else:
                    result['success'] = False
                    result['errors'].append(f"No position found for {symbol}")
                    return result

            if position_size <= 0:
                result['success'] = False
                result['errors'].append(f"Invalid position size: {position_size}")
                return result

            # Get precision for price rounding
            precision = self._get_asset_precision(symbol)
            price_tick = precision.get('price_tick')
            price_decimals = precision.get('price_decimals', 2)
            size_decimals = precision.get('size_decimals', 5)

            # ============================================================
            # STEP 4: Determine which orders need to be updated
            # At this point, we know at least one of TP or SL needs updating
            # ============================================================
            tp_needs_update = not tp_matches_existing and new_tp_price is not None
            sl_needs_update = not sl_matches_existing and new_sl_price is not None
            
            print(f"[TPSL UPDATE] {symbol} - Update decision: TP_update={tp_needs_update}, SL_update={sl_needs_update}", file=sys.stderr, flush=True)
            logger.info(f"[TPSL UPDATE] {symbol} - Update decision: TP_update={tp_needs_update}, SL_update={sl_needs_update}")

            # Cancel and replace TP if needed
            if tp_needs_update:
                # Cancel ALL existing TP orders first (not just the first one)
                tp_cancel_success = True
                all_tp_orders = current_tpsl.get('all_tp_orders', [])
                
                if all_tp_orders:
                    logger.info(f"[TPSL] Found {len(all_tp_orders)} existing TP orders to cancel for {symbol}")
                    for tp_order_to_cancel in all_tp_orders:
                        oid = tp_order_to_cancel.get('oid')
                        if oid:
                            try:
                                logger.info(f"[TPSL] Attempting to cancel TP order {oid} for {symbol}")
                                cancel_result = self.cancel_order(db, oid, symbol)
                                if cancel_result:
                                    logger.info(f"[TPSL] Successfully cancelled TP order {oid} for {symbol}")
                                else:
                                    logger.warning(f"[TPSL] Failed to cancel TP order {oid}")
                                    result['errors'].append(f"Failed to cancel TP order {oid}")
                            except Exception as cancel_err:
                                logger.warning(f"[TPSL] Exception cancelling TP order {oid}: {cancel_err}")
                                result['errors'].append(f"Failed to cancel TP {oid}: {str(cancel_err)}")
                    
                    # Small delay to ensure exchange processes all cancellations
                    import time as time_module
                    time_module.sleep(0.5)
                elif current_tp and current_tp.get('oid'):
                    # Fallback: cancel single TP order if all_tp_orders not available
                    try:
                        logger.info(f"[TPSL] Attempting to cancel old TP order {current_tp['oid']} for {symbol}")
                        cancel_result = self.cancel_order(db, current_tp['oid'], symbol)
                        if cancel_result:
                            logger.info(f"[TPSL] Successfully cancelled old TP order {current_tp['oid']} for {symbol}")
                            import time as time_module
                            time_module.sleep(0.5)
                        else:
                            logger.warning(f"[TPSL] Failed to cancel old TP order {current_tp['oid']} - will not place new TP")
                            tp_cancel_success = False
                            result['errors'].append(f"Failed to cancel old TP order {current_tp['oid']}")
                    except Exception as cancel_err:
                        logger.warning(f"[TPSL] Exception cancelling old TP order: {cancel_err}")
                        tp_cancel_success = False
                        result['errors'].append(f"Failed to cancel old TP: {str(cancel_err)}")

                # Only place new TP order if cancellation succeeded (or there was no existing order)
                if tp_cancel_success:
                    try:
                        # Round TP price
                        rounded_tp = self._round_to_precision(
                            new_tp_price,
                            price_decimals,
                            size_decimals,
                            is_price=True,
                            price_tick=price_tick,
                            is_buy=not is_long,  # TP closes position (opposite direction)
                        )

                        tp_order_type = {"trigger": {
                            "triggerPx": rounded_tp,
                            "isMarket": False,
                            "tpsl": "tp"
                        }}

                        tp_result = self.sdk_exchange.order(
                            name=symbol,
                            is_buy=not is_long,  # Opposite direction to close
                            sz=position_size,
                            limit_px=rounded_tp,
                            order_type=tp_order_type,
                            reduce_only=True
                        )

                        if tp_result.get("status") == "ok":
                            result['tp_updated'] = True
                            result['new_tp'] = rounded_tp
                            logger.info(f"[TPSL] Placed new TP order for {symbol} at ${rounded_tp}")
                        else:
                            error_msg = tp_result.get("response", "Unknown error")
                            result['errors'].append(f"Failed to place new TP: {error_msg}")
                            logger.error(f"[TPSL] Failed to place new TP order: {error_msg}")

                    except Exception as tp_err:
                        result['errors'].append(f"TP order error: {str(tp_err)}")
                        logger.error(f"[TPSL] Error placing TP order: {tp_err}", exc_info=True)

            # Cancel and replace SL if needed
            if sl_needs_update:
                # Cancel ALL existing SL orders first (not just the first one)
                sl_cancel_success = True
                all_sl_orders = current_tpsl.get('all_sl_orders', [])
                
                if all_sl_orders:
                    logger.info(f"[TPSL] Found {len(all_sl_orders)} existing SL orders to cancel for {symbol}")
                    for sl_order_to_cancel in all_sl_orders:
                        oid = sl_order_to_cancel.get('oid')
                        if oid:
                            try:
                                logger.info(f"[TPSL] Attempting to cancel SL order {oid} for {symbol}")
                                cancel_result = self.cancel_order(db, oid, symbol)
                                if cancel_result:
                                    logger.info(f"[TPSL] Successfully cancelled SL order {oid} for {symbol}")
                                else:
                                    logger.warning(f"[TPSL] Failed to cancel SL order {oid}")
                                    result['errors'].append(f"Failed to cancel SL order {oid}")
                            except Exception as cancel_err:
                                logger.warning(f"[TPSL] Exception cancelling SL order {oid}: {cancel_err}")
                                result['errors'].append(f"Failed to cancel SL {oid}: {str(cancel_err)}")
                    
                    # Small delay to ensure exchange processes all cancellations
                    import time as time_module
                    time_module.sleep(0.5)
                elif current_sl and current_sl.get('oid'):
                    # Fallback: cancel single SL order if all_sl_orders not available
                    try:
                        logger.info(f"[TPSL] Attempting to cancel old SL order {current_sl['oid']} for {symbol}")
                        cancel_result = self.cancel_order(db, current_sl['oid'], symbol)
                        if cancel_result:
                            logger.info(f"[TPSL] Successfully cancelled old SL order {current_sl['oid']} for {symbol}")
                            import time as time_module
                            time_module.sleep(0.5)
                        else:
                            logger.warning(f"[TPSL] Failed to cancel old SL order {current_sl['oid']} - will not place new SL")
                            sl_cancel_success = False
                            result['errors'].append(f"Failed to cancel old SL order {current_sl['oid']}")
                    except Exception as cancel_err:
                        logger.warning(f"[TPSL] Exception cancelling old SL order: {cancel_err}")
                        sl_cancel_success = False
                        result['errors'].append(f"Failed to cancel old SL: {str(cancel_err)}")

                # Only place new SL order if cancellation succeeded (or there was no existing order)
                if sl_cancel_success:
                    try:
                        # Round SL price
                        rounded_sl = self._round_to_precision(
                            new_sl_price,
                            price_decimals,
                            size_decimals,
                            is_price=True,
                            price_tick=price_tick,
                            is_buy=not is_long,  # SL closes position (opposite direction)
                        )

                        sl_order_type = {"trigger": {
                            "triggerPx": rounded_sl,
                            "isMarket": False,
                            "tpsl": "sl"
                        }}

                        sl_result = self.sdk_exchange.order(
                            name=symbol,
                            is_buy=not is_long,  # Opposite direction to close
                            sz=position_size,
                            limit_px=rounded_sl,
                            order_type=sl_order_type,
                            reduce_only=True
                        )

                        if sl_result.get("status") == "ok":
                            result['sl_updated'] = True
                            result['new_sl'] = rounded_sl
                            logger.info(f"[TPSL] Placed new SL order for {symbol} at ${rounded_sl}")
                        else:
                            error_msg = sl_result.get("response", "Unknown error")
                            result['errors'].append(f"Failed to place new SL: {error_msg}")
                            logger.error(f"[TPSL] Failed to place new SL order: {error_msg}")

                    except Exception as sl_err:
                        result['errors'].append(f"SL order error: {str(sl_err)}")
                        logger.error(f"[TPSL] Error placing SL order: {sl_err}", exc_info=True)

            # Set overall success based on errors
            if result['errors']:
                result['success'] = False

            # ============================================================
            # STEP 5: Update cache after successful operations
            # ============================================================
            # Determine final TP/SL prices to cache (use new prices if updated, otherwise keep old)
            final_tp_price = result['new_tp'] if result['tp_updated'] else result['old_tp']
            final_sl_price = result['new_sl'] if result['sl_updated'] else result['old_sl']
            
            # Update cache with current state
            if final_tp_price is not None or final_sl_price is not None:
                _set_cached_tpsl(self.wallet_address, symbol, final_tp_price, final_sl_price)
                print(f"[TPSL CACHE] {symbol} - Updated cache after operation: TP={final_tp_price}, SL={final_sl_price}", file=sys.stderr, flush=True)

            # Log summary
            logger.info(
                f"[TPSL] Update complete for {symbol}: "
                f"TP {result['old_tp']}→{result['new_tp']} (updated={result['tp_updated']}), "
                f"SL {result['old_sl']}→{result['new_sl']} (updated={result['sl_updated']})"
            )

            self._record_exchange_action(
                action_type="update_tpsl",
                status="success" if result['success'] else "partial",
                symbol=symbol,
                request_payload={
                    "symbol": symbol,
                    "new_tp_price": new_tp_price,
                    "new_sl_price": new_sl_price,
                    "position_size": position_size,
                    "is_long": is_long,
                },
                response_payload=result,
                error_message="; ".join(result['errors']) if result['errors'] else None,
            )

            return result

        except Exception as e:
            result['success'] = False
            result['errors'].append(str(e))
            self._record_exchange_action(
                action_type="update_tpsl",
                status="error",
                symbol=symbol,
                request_payload={
                    "symbol": symbol,
                    "new_tp_price": new_tp_price,
                    "new_sl_price": new_sl_price,
                },
                error_message=str(e),
            )
            logger.error(f"[TPSL] Failed to update TP/SL for {symbol}: {e}", exc_info=True)
            return result

    def get_order_status(self, db: Session, order_id: int) -> Dict[str, Any]:
        """
        Query order status

        Args:
            db: Database session
            order_id: Hyperliquid order ID (oid)

        Returns:
            Order status dict

        Raises:
            EnvironmentMismatchError: If environment validation fails
        """
        self._validate_environment(db)

        try:
            logger.debug(f"Querying order status for {order_id} on {self.environment}")

            # TODO: Implement actual order status query

            return {
                'order_id': order_id,
                'status': 'unknown',
                'environment': self.environment
            }

        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            raise

    def test_connection(self, db: Session) -> Dict[str, Any]:
        """
        Test API connection and authentication

        Args:
            db: Database session

        Returns:
            Connection test result
        """
        try:
            self._validate_environment(db)
            account_state = self.get_account_state(db)

            return {
                'success': True,
                'connected': True,
                'environment': self.environment,
                'address': self.wallet_address,
                'account_id': self.account_id,
                'balance': account_state.get('available_balance'),
                'api_url': self.api_url
            }
        except Exception as e:
            return {
                'success': False,
                'connected': False,
                'environment': self.environment,
                'message': str(e),
                'error': str(e)
            }

    def get_user_rate_limit(self, db: Session) -> Dict[str, Any]:
        """
        Query user's API request rate limit status

        This endpoint queries Hyperliquid's userRateLimit to check the address-based
        request quota. Users get a base quota of 10,000 requests, plus 1 additional
        request per USDC of cumulative trading volume.

        Args:
            db: Database session

        Returns:
            Dict containing:
                - cumVlm: Cumulative trading volume (USDC)
                - nRequestsUsed: Number of requests already consumed
                - nRequestsCap: Maximum requests allowed (10000 + cumVlm)
                - nRequestsSurplus: Reserved quota surplus (usually 0)
                - remaining: Calculated remaining requests (cap - used)
                - usagePercent: Usage percentage (0-100+)
                - isOverLimit: Boolean indicating if quota is exceeded

        Raises:
            EnvironmentMismatchError: If environment validation fails
            Exception: If API request fails
        """
        self._validate_environment(db)

        try:
            import requests

            # Select API endpoint based on environment
            info_url = f"{self.api_url}/info"

            # Construct payload for userRateLimit query
            payload = {
                "type": "userRateLimit",
                "user": self.wallet_address
            }

            logger.info(f"Querying rate limit for {self.wallet_address} on {self.environment}")

            # Call Hyperliquid Info API (disable proxy to avoid connection issues)
            proxies = {
                'http': None,
                'https': None
            }
            response = requests.post(info_url, json=payload, timeout=10, proxies=proxies)
            response.raise_for_status()

            data = response.json()

            # Parse response fields
            cum_vlm = float(data.get('cumVlm', 0))
            n_requests_used = int(data.get('nRequestsUsed', 0))
            n_requests_cap = int(data.get('nRequestsCap', 10000))
            n_requests_surplus = int(data.get('nRequestsSurplus', 0))

            # Calculate additional metrics
            remaining = n_requests_cap - n_requests_used
            usage_percent = (n_requests_used / n_requests_cap * 100) if n_requests_cap > 0 else 0
            is_over_limit = n_requests_used > n_requests_cap

            result = {
                'cumVlm': cum_vlm,
                'nRequestsUsed': n_requests_used,
                'nRequestsCap': n_requests_cap,
                'nRequestsSurplus': n_requests_surplus,
                'remaining': remaining,
                'usagePercent': round(usage_percent, 2),
                'isOverLimit': is_over_limit,
                'environment': self.environment,
                'walletAddress': self.wallet_address
            }

            logger.info(
                f"Rate limit status: {n_requests_used}/{n_requests_cap} requests "
                f"({usage_percent:.1f}%), Volume: ${cum_vlm:.2f}"
            )

            if is_over_limit:
                shortage = n_requests_used - n_requests_cap
                logger.warning(
                    f"⚠️ Rate limit EXCEEDED by {shortage} requests! "
                    f"Need to trade ${shortage} USDC to free up quota."
                )

            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to query rate limit: {e}")
            raise Exception(f"Rate limit query failed: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing rate limit data: {e}")
            raise


    def _get_asset_precision(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch asset precision requirements from Hyperliquid /info endpoint

        Returns:
            Dict with:
                - price_decimals: Inferred decimal places for price (for logging/fallback)
                - size_decimals: Size decimal places from meta
                - price_tick: Decimal tick size for price alignment
                - size_step: Decimal step for size alignment
        """
        proxies = {'http': None, 'https': None}
        info_url = f"{self.api_url}/info"

        try:
            # Default fallbacks
            price_decimals = 1
            price_tick = Decimal('0.1')
            size_decimals = 5
            size_step = Decimal('1').scaleb(-size_decimals)

            # Fetch meta for size precision
            meta_payload = {"type": "meta"}
            response = requests.post(info_url, json=meta_payload, timeout=10, proxies=proxies)
            response.raise_for_status()

            data = response.json()
            universe = data.get('universe', [])

            for asset in universe:
                if asset.get('name') == symbol:
                    size_decimals = asset.get('szDecimals', 5)
                    break

            size_step = Decimal('1').scaleb(-size_decimals)

            # Fetch order book to infer tick size
            try:
                l2_payload = {"type": "l2Book", "coin": symbol}
                l2_response = requests.post(info_url, json=l2_payload, timeout=10, proxies=proxies)
                l2_response.raise_for_status()
                l2_data = l2_response.json()

                price_samples: List[Decimal] = []
                levels = l2_data.get('levels', [])
                for side in levels:
                    for level in side[:10]:
                        px = level.get('px')
                        if px is not None:
                            try:
                                price_samples.append(Decimal(str(px)))
                            except (InvalidOperation, ValueError):
                                continue

                if price_samples:
                    inferred_tick = self._infer_price_tick(price_samples)
                    if inferred_tick is not None and inferred_tick > 0:
                        price_tick = inferred_tick
                        price_decimals = max(0, -price_tick.as_tuple().exponent)
                        logger.info(
                            f"[PRECISION] {symbol} inferred tick={price_tick} "
                            f"(price_decimals={price_decimals})"
                        )
                    else:
                        max_decimals = max(0, max(-p.as_tuple().exponent for p in price_samples))
                        price_decimals = max_decimals
                        price_tick = Decimal('1').scaleb(-price_decimals)
                        logger.warning(
                            f"[PRECISION] {symbol} unable to compute tick, "
                            f"using decimals-based fallback price_tick={price_tick}"
                        )
                else:
                    logger.warning(f"[PRECISION] {symbol} no order book data, using default tick={price_tick}")

            except Exception as e:
                logger.warning(f"[PRECISION] Failed to fetch order book for {symbol}: {e}, using defaults")

            logger.info(
                f"[PRECISION] {symbol} final precision: price_tick={price_tick}, size_step={size_step}, "
                f"price_decimals={price_decimals}, size_decimals={size_decimals}"
            )

            return {
                'price_decimals': price_decimals,
                'size_decimals': size_decimals,
                'price_tick': price_tick,
                'size_step': size_step,
            }

        except Exception as e:
            logger.error(f"[PRECISION] Failed to fetch precision for {symbol}: {e}")
            # Fallback to conservative defaults
            return {
                'price_decimals': 1,
                'size_decimals': 5,
                'price_tick': Decimal('0.1'),
                'size_step': Decimal('1e-5'),
            }

    def _round_to_precision(
        self,
        value: float,
        price_decimals: int,
        size_decimals: int,
        is_price: bool = True,
        price_tick: Optional[Decimal] = None,
        size_step: Optional[Decimal] = None,
        is_buy: Optional[bool] = None,
        force_aggressive: bool = False,
    ) -> float:
        """
        Round a price or size to the required precision/tick size.

        Args:
            value: Value to round
            price_decimals: Number of decimal places for prices (fallback)
            size_decimals: Number of decimal places for sizes (fallback)
            is_price: True for prices, False for sizes
            price_tick: Explicit tick size for prices
            size_step: Explicit step for sizes
        """
        if value is None or math.isnan(value) or math.isinf(value):
            return value

        if is_price and force_aggressive and is_buy is not None:
            slippage = Decimal('1.0005') if is_buy else Decimal('0.9995')
            try:
                value = float(Decimal(str(value)) * slippage)
            except (InvalidOperation, TypeError, ValueError):
                value = value * float(slippage)

        if is_price:
            step = price_tick if price_tick is not None else Decimal('1').scaleb(-price_decimals)
            return self._round_to_step(value, step, sigfigs=5, prefer_up=is_buy, force_aggressive=force_aggressive)
        else:
            step = size_step if size_step is not None else Decimal('1').scaleb(-size_decimals)
            return self._round_to_step(value, step)

    def _round_to_step(
        self,
        value: float,
        step: Decimal,
        sigfigs: Optional[int] = None,
        prefer_up: Optional[bool] = None,
        force_aggressive: bool = False,
    ) -> float:
        """
        Snap a numeric value to the nearest multiple of `step`, optionally limiting significant figures.
        """
        try:
            step_dec = step if isinstance(step, Decimal) else Decimal(str(step))
        except (InvalidOperation, TypeError, ValueError):
            step_dec = Decimal('0')

        if step_dec <= 0:
            base_dec = self._limit_sigfigs(value, sigfigs, prefer_up) if sigfigs else Decimal(str(value))
            return float(base_dec)

        try:
            base_dec = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            base_dec = Decimal(str(float(value)))

        limited_base = self._limit_sigfigs(base_dec, sigfigs, prefer_up) if sigfigs else base_dec

        try:
            steps = (limited_base / step_dec).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            quantized = steps * step_dec
        except InvalidOperation:
            return float(limited_base)

        if prefer_up is True and quantized < limited_base:
            quantized += step_dec
        elif prefer_up is False and quantized > limited_base:
            quantized -= step_dec

        if quantized <= 0:
            quantized = step_dec

        if force_aggressive:
            if prefer_up is True:
                quantized += step_dec
            elif prefer_up is False:
                quantized -= step_dec
                if quantized <= 0:
                    quantized = step_dec

        return float(quantized.normalize())

    def _limit_sigfigs(self, value: Any, sigfigs: Optional[int], prefer_up: Optional[bool] = None) -> Decimal:
        """
        Limit a numeric value to a maximum number of significant figures.
        """
        if not sigfigs or sigfigs <= 0:
            return Decimal(str(value))

        try:
            dec = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            dec = Decimal(str(float(value)))

        if dec.is_zero():
            return Decimal('0')

        numeric = float(dec)
        if math.isnan(numeric) or math.isinf(numeric):
            return dec

        exponent = math.floor(math.log10(abs(numeric)))
        quant_exp = exponent - sigfigs + 1
        quant = Decimal('1').scaleb(quant_exp)

        rounding_mode = ROUND_HALF_UP
        if prefer_up is True:
            rounding_mode = ROUND_CEILING if dec >= 0 else ROUND_FLOOR
        elif prefer_up is False:
            rounding_mode = ROUND_FLOOR if dec >= 0 else ROUND_CEILING

        try:
            return dec.quantize(quant, rounding=rounding_mode)
        except InvalidOperation:
            return dec

    def _infer_price_tick(self, prices: List[Decimal]) -> Optional[Decimal]:
        """
        Infer the minimal tick size from a list of Decimal price samples.
        """
        unique_prices = sorted(set([p for p in prices if p is not None]))
        if len(unique_prices) < 2:
            return None

        diffs: List[Decimal] = []
        for first, second in zip(unique_prices, unique_prices[1:]):
            diff = second - first
            if diff > 0:
                diffs.append(diff)

        if not diffs:
            return None

        tick = diffs[0]
        for diff in diffs[1:]:
            tick = self._decimal_gcd(tick, diff)
            if tick == 0:
                tick = diff

        if tick <= 0:
            tick = min(diffs)

        return tick.normalize()

    def _decimal_gcd(self, a: Decimal, b: Decimal) -> Decimal:
        """
        Compute the GCD for two Decimal numbers by scaling to integers.
        """
        from math import gcd

        a = abs(a)
        b = abs(b)

        if a == 0:
            return b
        if b == 0:
            return a

        scale = max(-a.as_tuple().exponent, -b.as_tuple().exponent, 0)
        factor = Decimal(10) ** scale

        try:
            a_int = int((a * factor).to_integral_value(rounding=ROUND_HALF_UP))
            b_int = int((b * factor).to_integral_value(rounding=ROUND_HALF_UP))
        except InvalidOperation:
            return Decimal('0')

        gcd_value = gcd(a_int, b_int)
        if gcd_value == 0:
            return Decimal('0')

        result = Decimal(gcd_value) / factor
        return result.normalize()

    def place_order_with_tpsl(
        self,
        db: Session,
        symbol: str,
        is_buy: bool,
        size: float,
        price: float,
        leverage: int = 1,
        time_in_force: str = "Ioc",
        reduce_only: bool = False,
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Place order with take profit and stop loss using Hyperliquid official SDK

        Args:
            db: Database session
            symbol: Asset symbol (e.g., "BTC")
            is_buy: True for long, False for short
            size: Order quantity
            price: Order price
            leverage: Position leverage (1-50)
            time_in_force: Order time in force - "Ioc" (market-like), "Gtc" (limit), "Alo" (maker only)
            reduce_only: Only close existing positions
            take_profit_price: Optional take profit trigger price
            stop_loss_price: Optional stop loss trigger price

        Returns:
            Dict with order results including TP/SL order IDs
        """
        import sys
        print(f"[DEBUG ENTRY] place_order_with_tpsl called: symbol={symbol}, price={price}, size={size}, TP={take_profit_price}, SL={stop_loss_price}", file=sys.stderr, flush=True)

        self._validate_environment(db)

        # Validate parameters
        if leverage < 1 or leverage > 50:
            raise ValueError(f"Invalid leverage: {leverage}. Must be 1-50")
        if size <= 0 or not isinstance(size, (int, float)) or size != size:  # Check for NaN
            raise ValueError(f"Invalid size: {size}. Must be a positive number")
        if price <= 0 or not isinstance(price, (int, float)) or price != price:  # Check for NaN
            raise ValueError(f"Invalid price: {price}. Must be a positive number")

        # Validate time_in_force
        valid_tif = ["Ioc", "Gtc", "Alo"]
        if time_in_force not in valid_tif:
            raise ValueError(f"Invalid time_in_force: {time_in_force}. Must be one of {valid_tif}")

        # ===== Dynamic Precision Handling =====
        # Fetch asset-specific precision requirements from Hyperliquid
        # This works for ALL assets (BTC, ETH, SOL, etc.) and handles AI-generated imprecise numbers
        print(f"[PRECISION] Fetching precision for {symbol}...", file=sys.stderr, flush=True)

        precision = self._get_asset_precision(symbol)
        price_decimals = precision['price_decimals']
        size_decimals = precision['size_decimals']
        price_tick = precision.get('price_tick')
        size_step = precision.get('size_step')

        print(
            f"[PRECISION] {symbol} - price_decimals: {price_decimals}, size_decimals: {size_decimals}, "
            f"price_tick: {price_tick}, size_step: {size_step}",
            file=sys.stderr,
            flush=True,
        )
        print(f"[PRECISION] Original values - price: {price}, size: {size}, TP: {take_profit_price}, SL: {stop_loss_price}", file=sys.stderr, flush=True)

        # Round price to tick precision
        original_price = price
        is_ioc_order = time_in_force.lower() == "ioc"

        price = self._round_to_precision(
            price,
            price_decimals,
            size_decimals,
            is_price=True,
            price_tick=price_tick,
            size_step=size_step,
            is_buy=is_buy,
            force_aggressive=is_ioc_order,
        )
        print(f"[PRECISION] Price adjusted: {original_price} -> {price}", file=sys.stderr, flush=True)

        # Round size using official step
        original_size = size
        size = self._round_to_precision(
            size,
            price_decimals,
            size_decimals,
            is_price=False,
            price_tick=price_tick,
            size_step=size_step,
        )
        print(f"[PRECISION] Size adjusted: {original_size} -> {size}", file=sys.stderr, flush=True)

        # Round TP/SL prices if provided
        if take_profit_price is not None:
            original_tp = take_profit_price
            take_profit_price = self._round_to_precision(
                take_profit_price,
                price_decimals,
                size_decimals,
                is_price=True,
                price_tick=price_tick,
                size_step=size_step,
                is_buy=not is_buy,
            )
            print(f"[PRECISION] TP adjusted: {original_tp} -> {take_profit_price}", file=sys.stderr, flush=True)

        if stop_loss_price is not None:
            original_sl = stop_loss_price
            stop_loss_price = self._round_to_precision(
                stop_loss_price,
                price_decimals,
                size_decimals,
                is_price=True,
                price_tick=price_tick,
                size_step=size_step,
                is_buy=not is_buy,
            )
            print(f"[PRECISION] SL adjusted: {original_sl} -> {stop_loss_price}", file=sys.stderr, flush=True)

        logger.info(
            f"[SDK] Placing order on {self.environment.upper()}: "
            f"{symbol} {'BUY' if is_buy else 'SELL'} size={size} price={price} "
            f"leverage={leverage}x TIF={time_in_force} TP={take_profit_price} SL={stop_loss_price}"
        )

        try:
            # Set leverage before placing order
            try:
                self.exchange.set_leverage(leverage, f"{symbol}/USDC:USDC")
                logger.debug(f"Set leverage to {leverage}x for {symbol}")
                self._record_exchange_action(
                    action_type="set_leverage",
                    status="success",
                    symbol=symbol,
                    leverage=leverage,
                    request_payload={"symbol": symbol, "leverage": leverage},
                )
            except Exception as lev_err:
                logger.warning(f"Failed to set leverage (may already be set): {lev_err}")
                self._record_exchange_action(
                    action_type="set_leverage",
                    status="error",
                    symbol=symbol,
                    leverage=leverage,
                    request_payload={"symbol": symbol, "leverage": leverage},
                    error_message=str(lev_err),
                )

            # Prepare order type with TIF
            order_type = {"limit": {"tif": time_in_force}}

            # Place main order using SDK
            logger.info(f"[SDK] Placing main order: {symbol} {'BUY' if is_buy else 'SELL'} {size}@{price} TIF={time_in_force}")

            main_result = self.sdk_exchange.order(
                name=symbol,
                is_buy=is_buy,
                sz=size,
                limit_px=price,
                order_type=order_type,
                reduce_only=reduce_only
            )

            logger.info(f"[SDK] Main order result: {main_result}")

            # Parse main order result
            order_status = main_result.get("status", "error")
            order_id = None
            filled_amount = 0
            average_price = 0
            error_msg = None

            if order_status == "ok":
                data = main_result.get("response", {}).get("data", {})
                statuses = data.get("statuses", [])

                if statuses:
                    main_status = statuses[0]

                    if "filled" in main_status:
                        filled_info = main_status["filled"]
                        order_id = str(filled_info.get("oid", ""))
                        filled_amount = float(filled_info.get("totalSz", 0))
                        average_price = float(filled_info.get("avgPx", 0))
                        status = "filled"
                    elif "resting" in main_status:
                        resting_info = main_status["resting"]
                        order_id = str(resting_info.get("oid", ""))
                        status = "resting"
                    elif "error" in main_status:
                        error_msg = main_status["error"]
                        status = "error"
                    else:
                        status = "error"
                        error_msg = f"Unknown status in response: {main_status}"
                else:
                    status = "error"
                    error_msg = "No statuses in response"
            else:
                status = "error"
                error_msg = main_result.get("response", "Unknown error")

            # Place TP/SL orders if main order succeeded and prices provided
            tp_order_id = None
            sl_order_id = None

            if status in ["filled", "resting"] and (take_profit_price or stop_loss_price):
                # Place TP order
                if take_profit_price:
                    try:
                        logger.info(f"[SDK] Placing TP order: {symbol} {'SELL' if is_buy else 'BUY'} {size}@{take_profit_price}")

                        tp_order_type = {"trigger": {
                            "triggerPx": take_profit_price,
                            "isMarket": False,
                            "tpsl": "tp"
                        }}

                        tp_result = self.sdk_exchange.order(
                            name=symbol,
                            is_buy=not is_buy,  # Opposite direction
                            sz=size,
                            limit_px=take_profit_price,
                            order_type=tp_order_type,
                            reduce_only=True
                        )

                        logger.info(f"[SDK] TP order result: {tp_result}")

                        if tp_result.get("status") == "ok":
                            tp_statuses = tp_result.get("response", {}).get("data", {}).get("statuses", [])
                            if tp_statuses:
                                tp_status = tp_statuses[0]
                                if "resting" in tp_status:
                                    tp_order_id = str(tp_status["resting"].get("oid", ""))
                                elif "filled" in tp_status:
                                    tp_order_id = str(tp_status["filled"].get("oid", ""))
                    except Exception as tp_err:
                        logger.error(f"[SDK] Failed to place TP order: {tp_err}", exc_info=True)

                # Place SL order
                if stop_loss_price:
                    try:
                        logger.info(f"[SDK] Placing SL order: {symbol} {'SELL' if is_buy else 'BUY'} {size}@{stop_loss_price}")

                        sl_order_type = {"trigger": {
                            "triggerPx": stop_loss_price,
                            "isMarket": False,
                            "tpsl": "sl"
                        }}

                        sl_result = self.sdk_exchange.order(
                            name=symbol,
                            is_buy=not is_buy,  # Opposite direction
                            sz=size,
                            limit_px=stop_loss_price,
                            order_type=sl_order_type,
                            reduce_only=True
                        )

                        logger.info(f"[SDK] SL order result: {sl_result}")

                        if sl_result.get("status") == "ok":
                            sl_statuses = sl_result.get("response", {}).get("data", {}).get("statuses", [])
                            if sl_statuses:
                                sl_status = sl_statuses[0]
                                if "resting" in sl_status:
                                    sl_order_id = str(sl_status["resting"].get("oid", ""))
                                elif "filled" in sl_status:
                                    sl_order_id = str(sl_status["filled"].get("oid", ""))
                    except Exception as sl_err:
                        logger.error(f"[SDK] Failed to place SL order: {sl_err}", exc_info=True)

            # Construct result
            order_result = {
                "status": status,
                "environment": self.environment,
                "symbol": symbol,
                "is_buy": is_buy,
                "size": size,
                "leverage": leverage,
                "order_id": order_id,
                "filled_amount": filled_amount,
                "average_price": average_price,
                "wallet_address": self.wallet_address,
                "timestamp": int(time.time() * 1000),
                # TP/SL specific fields
                "tp_order_id": tp_order_id,
                "tp_trigger_price": take_profit_price,
                "sl_order_id": sl_order_id,
                "sl_trigger_price": stop_loss_price,
            }

            if error_msg:
                order_result["error"] = error_msg

            # Update TPSL cache after successful order placement with TP/SL
            if status in ["filled", "resting"] and (take_profit_price or stop_loss_price):
                _set_cached_tpsl(self.wallet_address, symbol, take_profit_price, stop_loss_price)
                print(f"[TPSL CACHE] {symbol} - Cached new TP/SL from place_order_with_tpsl: TP={take_profit_price}, SL={stop_loss_price}", file=sys.stderr, flush=True)

            logger.info(
                f"[SDK] Order result: status={status} order_id={order_id} "
                f"filled={filled_amount}/{size} avg_price={average_price} "
                f"TP={tp_order_id} SL={sl_order_id}"
            )

            self._record_exchange_action(
                action_type="create_order_with_tpsl",
                status="success" if status != "error" else "error",
                symbol=symbol,
                side="buy" if is_buy else "sell",
                leverage=leverage,
                size=size,
                price=price,
                request_payload={
                    "symbol": symbol,
                    "is_buy": is_buy,
                    "size": size,
                    "price": price,
                    "leverage": leverage,
                    "time_in_force": time_in_force,
                    "take_profit_price": take_profit_price,
                    "stop_loss_price": stop_loss_price
                },
                response_payload=main_result,
                error_message=error_msg,
            )

            return order_result

        except Exception as e:
            logger.error(f"[SDK] Failed to place order: {e}", exc_info=True)
            self._record_exchange_action(
                action_type="create_order_with_tpsl",
                status="error",
                symbol=symbol,
                side="buy" if is_buy else "sell",
                leverage=leverage,
                size=size,
                price=price,
                request_payload={
                    "symbol": symbol,
                    "is_buy": is_buy,
                    "size": size,
                    "price": price
                },
                response_payload=None,
                error_message=str(e),
            )
            return {
                "status": "error",
                "error": str(e),
                "environment": self.environment,
                "symbol": symbol
            }


# Factory function for creating clients
def create_hyperliquid_client(
    account_id: int,
    private_key: str,
    environment: str,
    wallet_address: str = None
) -> HyperliquidTradingClient:
    """
    Factory function to create Hyperliquid trading client

    Args:
        account_id: Database account ID
        private_key: Hyperliquid private key
        environment: "testnet" or "mainnet"
        wallet_address: Optional wallet address (if not provided, derived from private key)

    Returns:
        Initialized HyperliquidTradingClient
    """
    return HyperliquidTradingClient(
        account_id=account_id,
        private_key=private_key,
        wallet_address=wallet_address,
        environment=environment
    )
