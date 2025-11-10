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
from typing import Dict, List, Optional, Any
from decimal import Decimal

import ccxt
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Account, HyperliquidExchangeAction
from services.hyperliquid_cache import (
    update_account_state_cache,
    update_positions_cache,
)

logger = logging.getLogger(__name__)


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
        self.private_key = private_key

        # Derive wallet address from private key if not provided
        if not wallet_address:
            try:
                from eth_account import Account as EthAccount
                eth_account = EthAccount.from_key(private_key)
                self.wallet_address = eth_account.address
                logger.info(f"Derived wallet address from private key: {self.wallet_address}")
            except Exception as e:
                logger.error(f"Failed to derive wallet address from private key: {e}", exc_info=True)
                self.wallet_address = None
        else:
            self.wallet_address = wallet_address

        if not self.wallet_address:
            raise ValueError("Wallet address could not be derived from private key. Please check key format.")

        # Set API endpoint based on environment
        if environment == "testnet":
            self.api_url = "https://api.hyperliquid-testnet.xyz"
        else:
            self.api_url = "https://api.hyperliquid.xyz"

        # Initialize CCXT exchange with authentication
        try:
            self.exchange = ccxt.hyperliquid({
                'sandbox': (environment == "testnet"),
                'enableRateLimit': True,
                'rateLimit': 100,  # 100ms between requests
                'privateKey': private_key,  # Hyperliquid requires privateKey field
                'walletAddress': self.wallet_address,
            })

            logger.info(
                f"HyperliquidClient initialized: account_id={account_id} "
                f"environment={environment.upper()} wallet={self.wallet_address}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Hyperliquid exchange: {e}")
            raise

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
        Validate that account's configured environment matches client environment

        This is a critical safety check to prevent wrong environment operations.
        Called before every API call that modifies state.

        Args:
            db: Database session

        Returns:
            True if validation passes

        Raises:
            ValueError: If account not found
            EnvironmentMismatchError: If environments don't match
        """
        account = db.query(Account).filter(Account.id == self.account_id).first()
        if not account:
            raise ValueError(f"Account {self.account_id} not found")

        if account.hyperliquid_environment != self.environment:
            raise EnvironmentMismatchError(
                f"Account {account.name} is configured for {account.hyperliquid_environment}, "
                f"but client is using {self.environment}. Operation blocked for safety."
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
            update_account_state_cache(self.account_id, result)
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
        Get all open positions from Hyperliquid

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

                positions.append({
                    'coin': info_position.get('coin'),
                    'szi': position_size,  # Correct signed size
                    'entry_px': float(info_position.get('entryPx', 0)),
                    'position_value': float(info_position.get('positionValue', 0)),
                    'unrealized_pnl': float(info_position.get('unrealizedPnl', 0)),
                    'margin_used': float(info_position.get('marginUsed', 0)),
                    'liquidation_px': float(info_position.get('liquidationPx') or 0),
                    'leverage': float((info_position.get('leverage') or {}).get('value', 0)),
                    'side': side,  # Correct direction from CCXT

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
            update_positions_cache(self.account_id, positions)
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

    def cancel_order(self, db: Session, order_id: int, symbol: str) -> bool:
        """
        Cancel an open order

        Args:
            db: Database session
            order_id: Hyperliquid order ID (oid)
            symbol: Asset symbol

        Returns:
            True if successful

        Raises:
            EnvironmentMismatchError: If environment validation fails
        """
        self._validate_environment(db)

        try:
            logger.info(f"Cancelling order {order_id} for {symbol} on {self.environment}")

            # TODO: Implement actual order cancellation
            # For reference, Hyperliquid exchange endpoint:
            # POST /exchange with action type "cancel"

            return True

        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            raise

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


# Factory function for creating clients
def create_hyperliquid_client(
    account_id: int,
    private_key: str,
    environment: str
) -> HyperliquidTradingClient:
    """
    Factory function to create Hyperliquid trading client

    Args:
        account_id: Database account ID
        private_key: Hyperliquid private key
        environment: "testnet" or "mainnet"

    Returns:
        Initialized HyperliquidTradingClient
    """
    return HyperliquidTradingClient(
        account_id=account_id,
        private_key=private_key,
        environment=environment
    )
