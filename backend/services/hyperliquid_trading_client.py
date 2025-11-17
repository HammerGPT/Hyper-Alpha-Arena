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
            })

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
            from eth_account import Account as EthAccount

            # Create eth_account wallet for SDK
            self.eth_wallet = EthAccount.from_key(private_key)

            # Initialize SDK Exchange
            self.sdk_exchange = Exchange(
                wallet=self.eth_wallet,
                base_url=self.api_url,
                account_address=self.wallet_address
            )

            logger.info(
                f"Official SDK Exchange initialized: account_id={account_id} "
                f"environment={environment.upper()} wallet={self.wallet_address}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Hyperliquid SDK: {e}")
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
