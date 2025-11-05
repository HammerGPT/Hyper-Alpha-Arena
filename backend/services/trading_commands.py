"""
Trading Commands Service - Handles order execution and trading logic
"""
import logging
import random
from decimal import Decimal
from typing import Dict, Optional, Tuple, List, Iterable

from sqlalchemy.orm import Session
from sqlalchemy import text

from database.connection import SessionLocal
from database.models import (
    Position,
    Account,
    CRYPTO_MIN_COMMISSION,
    CRYPTO_COMMISSION_RATE,
)
from services.asset_calculator import calc_positions_value
from services.market_data import get_last_price
from services.order_matching import create_order, check_and_execute_order
from services.ai_decision_service import (
    call_ai_for_decision, 
    save_ai_decision, 
    get_active_ai_accounts, 
    _get_portfolio_data,
    SUPPORTED_SYMBOLS
)


logger = logging.getLogger(__name__)

AI_TRADING_SYMBOLS: List[str] = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]


def _estimate_buy_cash_needed(price: float, quantity: float) -> Decimal:
    """Estimate cash required for a BUY including commission."""
    notional = Decimal(str(price)) * Decimal(str(quantity))
    commission = max(
        notional * Decimal(str(CRYPTO_COMMISSION_RATE)),
        Decimal(str(CRYPTO_MIN_COMMISSION)),
    )
    return notional + commission


def _get_market_prices(symbols: List[str]) -> Dict[str, float]:
    """Get latest prices for given symbols"""
    prices = {}
    for symbol in symbols:
        try:
            price = float(get_last_price(symbol, "CRYPTO"))
            if price > 0:
                prices[symbol] = price
        except Exception as err:
            logger.warning(f"Failed to get price for {symbol}: {err}")
    return prices


def _select_side(db: Session, account: Account, symbol: str, max_value: float) -> Optional[Tuple[str, int]]:
    """Select random trading side and quantity for legacy random trading"""
    market = "CRYPTO"
    try:
        price = float(get_last_price(symbol, market))
    except Exception as err:
        logger.warning("Cannot get price for %s: %s", symbol, err)
        return None

    if price <= 0:
        logger.debug("%s returned non-positive price %s", symbol, price)
        return None

    max_quantity_by_value = int(Decimal(str(max_value)) // Decimal(str(price)))
    position = (
        db.query(Position)
        .filter(Position.account_id == account.id, Position.symbol == symbol, Position.market == market)
        .first()
    )
    available_quantity = int(position.available_quantity) if position else 0

    choices = []

    if float(account.current_cash) >= price and max_quantity_by_value >= 1:
        choices.append(("BUY", max_quantity_by_value))

    if available_quantity > 0:
        max_sell_quantity = min(available_quantity, max_quantity_by_value if max_quantity_by_value >= 1 else available_quantity)
        if max_sell_quantity >= 1:
            choices.append(("SELL", max_sell_quantity))

    if not choices:
        return None

    side, max_qty = random.choice(choices)
    quantity = random.randint(1, max_qty)
    return side, quantity


def place_ai_driven_crypto_order(max_ratio: float = 0.2, account_ids: Optional[Iterable[int]] = None, account_id: Optional[int] = None, symbol: Optional[str] = None, samples: Optional[List] = None) -> None:
    """Place crypto order based on AI model decision.

    Args:
        max_ratio: maximum portion of portfolio to allocate per trade.
        account_ids: optional iterable of account IDs to process (defaults to all active accounts).
    """
    db = SessionLocal()
    try:
        # Handle single account strategy trigger
        if account_id is not None:
            account = db.query(Account).filter(Account.id == account_id).first()
            if not account or account.is_active != "true" or account.auto_trading_enabled != "true":
                logger.debug(f"Account {account_id} not found, inactive, or auto trading disabled, skipping AI trading")
                return
            accounts = [account]
        else:
            accounts = get_active_ai_accounts(db)
            if not accounts:
                logger.debug("No available accounts, skipping AI trading")
                return

            if account_ids is not None:
                id_set = {int(acc_id) for acc_id in account_ids}
                accounts = [acc for acc in accounts if acc.id in id_set]
                if not accounts:
                    logger.debug("No matching accounts for provided IDs: %s", account_ids)
                    return

        # Get latest market prices once for all accounts
        prices = _get_market_prices(AI_TRADING_SYMBOLS)
        if not prices:
            logger.warning("Failed to fetch market prices, skipping AI trading")
            return

        # Get all symbols with available sampling data
        from services.sampling_pool import sampling_pool
        available_symbols = []
        for sym in SUPPORTED_SYMBOLS.keys():
            samples_data = sampling_pool.get_samples(sym)
            if samples_data:
                available_symbols.append(sym)

        if available_symbols:
            logger.info(f"Available sampling pool symbols: {', '.join(available_symbols)}")
        else:
            logger.warning("No sampling data available for any symbol")

        # Iterate through all active accounts
        for account in accounts:
            try:
                logger.info(f"Processing AI trading for account: {account.name}")

                if getattr(account, "hyperliquid_enabled", "false") == "true":
                    logger.info(
                        f"Redirecting Hyperliquid-enabled account {account.name} to Hyperliquid trading pipeline"
                    )
                    place_ai_driven_hyperliquid_order(account_id=account.id)
                    continue

                # Get portfolio data for this account
                portfolio = _get_portfolio_data(db, account)

                if portfolio['total_assets'] <= 0:
                    logger.debug(f"Account {account.name} has non-positive total assets, skipping")
                    continue

                # Call AI for trading decision with all available sampling symbols
                # Always use all available symbols from pool (not just single symbol from strategy)
                # This allows controlling AI trading scope via sampling pool, not strategy parameters
                decision = call_ai_for_decision(
                    db, account, portfolio, prices,
                    samples=samples, target_symbol=symbol,  # Legacy params for backward compatibility
                    symbols=available_symbols if available_symbols else None  # New multi-symbol param
                )
                if not decision or not isinstance(decision, dict):
                    logger.warning(f"Failed to get AI decision for {account.name}, skipping")
                    continue

                operation = decision.get("operation", "").lower() if decision.get("operation") else ""
                symbol = decision.get("symbol", "").upper() if decision.get("symbol") else ""
                target_portion = float(decision.get("target_portion_of_balance", 0)) if decision.get("target_portion_of_balance") is not None else 0
                reason = decision.get("reason", "No reason provided")

                logger.info(f"AI decision for {account.name}: {operation} {symbol} (portion: {target_portion:.2%}) - {reason}")

                # Validate decision
                if operation not in ["buy", "sell", "hold", "close"]:
                    logger.warning(f"Invalid operation '{operation}' from AI for {account.name}, skipping")
                    # Save invalid decision for debugging
                    save_ai_decision(db, account, decision, portfolio, executed=False)
                    continue
                
                if operation == "hold":
                    logger.info(f"AI decided to HOLD for {account.name}")
                    # Save hold decision
                    save_ai_decision(db, account, decision, portfolio, executed=True)
                    continue

                if symbol not in SUPPORTED_SYMBOLS:
                    logger.warning(f"Invalid symbol '{symbol}' from AI for {account.name}, skipping")
                    # Save invalid decision for debugging
                    save_ai_decision(db, account, decision, portfolio, executed=False)
                    continue

                if target_portion <= 0 or target_portion > 1:
                    logger.warning(f"Invalid target_portion {target_portion} from AI for {account.name}, skipping")
                    # Save invalid decision for debugging
                    save_ai_decision(db, account, decision, portfolio, executed=False)
                    continue

                # Get current price
                price = prices.get(symbol)
                if not price or price <= 0:
                    logger.warning(f"Invalid price for {symbol} for {account.name}, skipping")
                    # Save decision with execution failure
                    save_ai_decision(db, account, decision, portfolio, executed=False)
                    continue

                # Calculate quantity based on operation
                if operation == "buy":
                    # Calculate quantity based on available cash and target portion
                    available_cash = float(account.current_cash)
                    available_cash_dec = Decimal(str(account.current_cash))
                    order_value = available_cash * target_portion
                    # For crypto, support fractional quantities - use float instead of int
                    quantity = float(Decimal(str(order_value)) / Decimal(str(price)))
                    
                    # Round to reasonable precision (6 decimal places for crypto)
                    quantity = round(quantity, 6)
                    
                    if quantity <= 0:
                        logger.info(f"Calculated BUY quantity <= 0 for {symbol} for {account.name}, skipping")
                        # Save decision with execution failure
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue

                    cash_needed = _estimate_buy_cash_needed(price, quantity)
                    if available_cash_dec < cash_needed:
                        logger.info(
                            "Skipping BUY for %s due to insufficient cash after fees: need $%.2f, current cash $%.2f",
                            account.name,
                            float(cash_needed),
                            float(available_cash_dec),
                        )
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue
                    
                    side = "BUY"

                elif operation == "sell":
                    # Calculate quantity based on position and target portion
                    position = (
                        db.query(Position)
                        .filter(Position.account_id == account.id, Position.symbol == symbol, Position.market == "CRYPTO")
                        .first()
                    )

                    if not position or float(position.available_quantity) <= 0:
                        logger.info(f"No position available to SELL for {symbol} for {account.name}, skipping")
                        # Save decision with execution failure
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue

                    available_quantity = float(position.available_quantity)
                    quantity = float(available_quantity * target_portion)

                    if quantity > available_quantity:
                        quantity = available_quantity

                    side = "SELL"

                elif operation == "close":
                    # Close entire position (sell 100%)
                    position = (
                        db.query(Position)
                        .filter(Position.account_id == account.id, Position.symbol == symbol, Position.market == "CRYPTO")
                        .first()
                    )

                    if not position or float(position.available_quantity) <= 0:
                        logger.info(f"No position available to CLOSE for {symbol} for {account.name}, skipping")
                        # Save decision with execution failure
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue

                    # Close entire position regardless of target_portion
                    quantity = float(position.available_quantity)
                    side = "CLOSE"

                else:
                    continue

                # Create and execute order
                name = SUPPORTED_SYMBOLS[symbol]
                
                try:
                    order = create_order(
                        db=db,
                        account=account,
                        symbol=symbol,
                        name=name,
                        side=side,
                        order_type="MARKET",
                        price=None,
                        quantity=quantity,
                    )
                except ValueError as create_err:
                    message = str(create_err)
                    if "Insufficient cash" in message or "Insufficient positions" in message:
                        logger.info(
                            "Skipping order for %s (%s %s): %s",
                            account.name,
                            side,
                            symbol,
                            message,
                        )
                        db.rollback()
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue
                    # Unexpected validation error - re-raise
                    raise

                db.commit()
                db.refresh(order)

                executed = check_and_execute_order(db, order)
                if executed:
                    db.refresh(order)
                    logger.info(
                        f"AI order executed: account={account.name} {side} {symbol} {order.order_no} "
                        f"quantity={quantity} reason='{reason}'"
                    )
                else:
                    logger.info(
                        f"AI order created but not executed: account={account.name} {side} {symbol} "
                        f"quantity={quantity} order_id={order.order_no} reason='{reason}'"
                    )
                
                # Save decision with final execution status (only called once)
                save_ai_decision(db, account, decision, portfolio, executed=executed, order_id=order.id)

            except Exception as account_err:
                logger.error(f"AI-driven order placement failed for account {account.name}: {account_err}", exc_info=True)
                # Continue with next account even if one fails

    except Exception as err:
        logger.error(f"AI-driven order placement failed: {err}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def place_random_crypto_order(max_ratio: float = 0.2) -> None:
    """Legacy random order placement (kept for backward compatibility)"""
    db = SessionLocal()
    try:
        accounts = get_active_ai_accounts(db)
        if not accounts:
            logger.debug("No available accounts, skipping auto order placement")
            return
        
        # For legacy compatibility, just pick a random account from the list
        account = random.choice(accounts)

        positions_value = calc_positions_value(db, account.id)
        total_assets = positions_value + float(account.current_cash)

        if total_assets <= 0:
            logger.debug("Account %s total assets non-positive, skipping auto order placement", account.name)
            return

        max_order_value = total_assets * max_ratio
        if max_order_value <= 0:
            logger.debug("Account %s maximum order amount is 0, skipping", account.name)
            return

        symbol = random.choice(list(SUPPORTED_SYMBOLS.keys()))
        side_info = _select_side(db, account, symbol, max_order_value)
        if not side_info:
            logger.debug("Account %s has no executable direction for %s, skipping", account.name, symbol)
            return

        side, quantity = side_info
        name = SUPPORTED_SYMBOLS[symbol]

        order = create_order(
            db=db,
            account=account,
            symbol=symbol,
            name=name,
            side=side,
            order_type="MARKET",
            price=None,
            quantity=quantity,
        )

        db.commit()
        db.refresh(order)

        executed = check_and_execute_order(db, order)
        if executed:
            db.refresh(order)
            logger.info("Auto order executed: account=%s %s %s %s quantity=%s", account.name, side, symbol, order.order_no, quantity)
        else:
            logger.info("Auto order created: account=%s %s %s quantity=%s order_id=%s", account.name, side, symbol, quantity, order.order_no)

    except Exception as err:
        logger.error("Auto order placement failed: %s", err)
        db.rollback()
    finally:
        db.close()


AUTO_TRADE_JOB_ID = "auto_crypto_trade"
AI_TRADE_JOB_ID = "ai_crypto_trade"


def test_hyperliquid_function():
    return "test_success"

def place_ai_driven_hyperliquid_order(account_ids: Optional[Iterable[int]] = None, account_id: Optional[int] = None) -> None:
    """Place Hyperliquid perpetual contract order based on AI decision.

    This function handles real trading on Hyperliquid exchange, supporting:
    - Perpetual contract trading (long/short)
    - Leverage (1x-50x based on account configuration)
    - Environment isolation (testnet/mainnet)
    - Position management

    Args:
        account_ids: Optional iterable of account IDs to process
        account_id: Optional single account ID to process
    """

    try:
        from services.hyperliquid_environment import get_hyperliquid_client
        from database.models import HyperliquidPosition
    except Exception as e:
        logger.error(f"Error in place_ai_driven_hyperliquid_order start: {e}", exc_info=True)
        return

    # First, get accounts list with minimal database connection
    accounts = []
    db = SessionLocal()
    # PostgreSQL handles concurrent access natively
    try:
        # Handle single account strategy trigger (manual trigger)
        if account_id is not None:
            account = db.query(Account).filter(Account.id == account_id).first()
            if not account or account.is_active != "true":
                logger.debug(f"Account {account_id} not found or inactive")
                return

            # Check if Hyperliquid enabled
            if getattr(account, "hyperliquid_enabled", "false") != "true":
                logger.debug(f"Account {account_id} does not have Hyperliquid enabled")
                return

            # For manual trigger, bypass auto_trading_enabled check
            accounts = [account]
        else:
            # Get all active accounts with Hyperliquid enabled
            accounts = db.query(Account).filter(
                Account.is_active == "true",
                Account.auto_trading_enabled == "true",
                Account.hyperliquid_enabled == "true"
            ).all()

            if not accounts:
                logger.debug("No Hyperliquid-enabled accounts available")
                return

            if account_ids is not None:
                id_set = {int(acc_id) for acc_id in account_ids}
                accounts = [acc for acc in accounts if acc.id in id_set]
                if not accounts:
                    logger.debug(f"No matching Hyperliquid accounts for provided IDs: {account_ids}")
                    return
    finally:
        db.close()

    # Get latest market prices (no database needed)
    prices = _get_market_prices(AI_TRADING_SYMBOLS)
    if not prices:
        logger.warning("Failed to fetch market prices, skipping Hyperliquid trading")
        return

    # Get available symbols from sampling pool
    from services.sampling_pool import sampling_pool
    available_symbols = []
    for sym in SUPPORTED_SYMBOLS.keys():
        samples_data = sampling_pool.get_samples(sym)
        if samples_data:
            available_symbols.append(sym)

    if available_symbols:
        logger.info(f"Available sampling symbols for Hyperliquid: {', '.join(available_symbols)}")
    else:
        logger.warning("No sampling data available for Hyperliquid trading")

    # Process each account with separate database connections
    for account in accounts:
        # Each account gets its own database connection
        db = SessionLocal()
        # PostgreSQL handles concurrent access natively
        try:
            environment = getattr(account, "hyperliquid_environment", "testnet")
            logger.info(f"Processing Hyperliquid trading for account: {account.name} (environment: {environment})")

            # Get Hyperliquid client
            try:
                client = get_hyperliquid_client(db, account.id)
            except Exception as client_err:
                logger.error(f"Failed to get Hyperliquid client for {account.name}: {client_err}")
                continue

            # Get real account state from Hyperliquid
            try:
                account_state = client.get_account_state(db)
                available_balance = account_state['available_balance']
                total_equity = account_state['total_equity']
                margin_usage = account_state['margin_usage_percent']

                logger.info(
                    f"Hyperliquid account state for {account.name}: "
                    f"equity=${total_equity:.2f}, available=${available_balance:.2f}, "
                    f"margin_usage={margin_usage:.1f}%"
                )

                if total_equity <= 0:
                    logger.debug(f"Account {account.name} has non-positive equity, skipping")
                    continue

            except Exception as state_err:
                logger.error(f"Failed to get account state for {account.name}: {state_err}")
                continue

            # Get open positions from Hyperliquid
            try:
                positions = client.get_positions(db)
                logger.info(f"Account {account.name} has {len(positions)} open positions")
            except Exception as pos_err:
                logger.error(f"Failed to get positions for {account.name}: {pos_err}")
                positions = []

            # Build portfolio data for AI (using Hyperliquid real data)
            portfolio = {
                'cash': available_balance,
                'frozen_cash': account_state.get('used_margin', 0),
                'positions': {},
                'total_assets': total_equity
            }

            for pos in positions:
                symbol = pos['coin']
                portfolio['positions'][symbol] = {
                    'quantity': pos['szi'],  # Signed size
                    'avg_cost': pos['entry_px'],
                    'current_value': pos['position_value'],
                    'unrealized_pnl': pos['unrealized_pnl'],
                    'leverage': pos['leverage']
                }

            # Build Hyperliquid state for prompt context
            hyperliquid_state = {
                'total_equity': total_equity,
                'available_balance': available_balance,
                'used_margin': account_state.get('used_margin', 0),
                'margin_usage_percent': margin_usage,
                'maintenance_margin': account_state.get('maintenance_margin', 0),
                'positions': positions
            }

            # Call AI for trading decision
            decision = call_ai_for_decision(
                db, account, portfolio, prices,
                symbols=available_symbols if available_symbols else None,
                hyperliquid_state=hyperliquid_state
            )

            if not decision or not isinstance(decision, dict):
                logger.warning(f"Failed to get AI decision for {account.name}, skipping")
                continue


            operation = decision.get("operation", "").lower()
            symbol = decision.get("symbol", "").upper()
            target_portion = float(decision.get("target_portion_of_balance", 0))
            leverage = int(decision.get("leverage", getattr(account, "default_leverage", 1)))
            max_price = decision.get("max_price")
            min_price = decision.get("min_price")
            reason = decision.get("reason", "No reason provided")


            logger.info(
                f"AI decision for {account.name}: {operation} {symbol} "
                f"(portion: {target_portion:.2%}, leverage: {leverage}x, max_price: {max_price}, min_price: {min_price}) - {reason}"
            )

            # Validate decision
            if operation not in ["buy", "sell", "hold", "close"]:
                logger.warning(f"Invalid operation '{operation}' from AI for {account.name}")
                save_ai_decision(db, account, decision, portfolio, executed=False)
                continue

            if operation == "hold":
                logger.info(f"AI decided to HOLD for {account.name}")
                save_ai_decision(db, account, decision, portfolio, executed=True)
                continue

            if symbol not in SUPPORTED_SYMBOLS:
                logger.warning(f"Invalid symbol '{symbol}' from AI for {account.name}")
                save_ai_decision(db, account, decision, portfolio, executed=False)
                continue

            # Validate leverage
            max_leverage = getattr(account, "max_leverage", 3)
            if leverage < 1 or leverage > max_leverage:
                logger.warning(
                    f"Invalid leverage {leverage}x from AI (max: {max_leverage}x), "
                    f"using default {getattr(account, 'default_leverage', 1)}x"
                )
                leverage = getattr(account, "default_leverage", 1)

            if target_portion <= 0 or target_portion > 1:
                logger.warning(f"Invalid target_portion {target_portion} from AI for {account.name}")
                save_ai_decision(db, account, decision, portfolio, executed=False)
                continue

            # Get current price
            price = prices.get(symbol)
            if not price or price <= 0:
                logger.warning(f"Invalid price for {symbol} for {account.name}")
                save_ai_decision(db, account, decision, portfolio, executed=False)
                continue

            # Execute order based on operation
            order_result = None

            if operation == "buy":
                # Open long position
                order_value = available_balance * target_portion
                quantity = round(order_value / price, 6)

                if quantity <= 0.0001:  # Minimum size check
                    logger.warning(f"Calculated BUY quantity too small ({quantity}) for {symbol}, skipping")
                    save_ai_decision(db, account, decision, portfolio, executed=False)
                    continue

                logger.info(
                    f"[HYPERLIQUID {environment.upper()}] Placing BUY order: "
                    f"{symbol} size={quantity} leverage={leverage}x"
                )

                order_result = client.place_order(
                    db=db,
                    symbol=symbol,
                    is_buy=True,
                    size=quantity,
                    order_type="market",
                    price=max_price,
                    leverage=leverage,
                    reduce_only=False
                )

            elif operation == "sell":
                # Open short position
                order_value = available_balance * target_portion
                quantity = round(order_value / price, 6)

                if quantity <= 0.0001:  # Minimum size check
                    logger.info(f"Calculated SELL quantity too small ({quantity}) for {symbol}, skipping")
                    save_ai_decision(db, account, decision, portfolio, executed=False)
                    continue

                logger.info(
                    f"[HYPERLIQUID {environment.upper()}] Placing SELL order: "
                    f"{symbol} size={quantity} leverage={leverage}x"
                )

                order_result = client.place_order(
                    db=db,
                    symbol=symbol,
                    is_buy=False,
                    size=quantity,
                    order_type="market",
                    price=min_price,
                    leverage=leverage,
                    reduce_only=False
                )

            elif operation == "close":
                # Close existing position
                position_to_close = None
                for pos in positions:
                    if pos['coin'] == symbol:
                        position_to_close = pos
                        break

                if not position_to_close:
                    logger.info(f"No position to close for {symbol} for {account.name}")
                    save_ai_decision(db, account, decision, portfolio, executed=False)
                    continue

                position_size = abs(position_to_close['szi'])
                close_size = position_size * target_portion
                is_long = position_to_close['szi'] > 0

                logger.info(
                    f"[HYPERLIQUID {environment.upper()}] Closing position: "
                    f"{symbol} size={close_size} (closing {'long' if is_long else 'short'})"
                )

                # Use AI price or fallback to market price with slippage
                current_price = prices.get(symbol, 0)
                close_price = min_price if min_price else current_price * (0.95 if is_long else 1.05)

                order_result = client.place_order(
                    db=db,
                    symbol=symbol,
                    is_buy=(not is_long),  # Close long by selling, close short by buying
                    size=close_size,
                    order_type="market",
                    price=close_price,
                    leverage=1,
                    reduce_only=True
                )


            # Process order result (shared by all operations)
            if order_result:
                print(f"[DEBUG] {operation.upper()} order_result: {order_result}")
                order_status = order_result.get('status')
                order_id = order_result.get('order_id')

                if order_status == 'filled':
                    logger.info(
                        f"[HYPERLIQUID] Order executed successfully for {account.name}: "
                        f"{operation.upper()} {symbol} order_id={order_id}"
                    )
                    save_ai_decision(db, account, decision, portfolio, executed=True)

                    # Create Hyperliquid trade record
                    try:
                        from database.snapshot_connection import SnapshotSessionLocal
                        from database.snapshot_models import HyperliquidTrade
                        from decimal import Decimal

                        snapshot_db = SnapshotSessionLocal()
                        try:
                            trade_record = HyperliquidTrade(
                                account_id=account.id,
                                environment=environment,
                                symbol=symbol,
                                side=operation,
                                quantity=Decimal(str(order_result.get('filled_amount', 0))),
                                price=Decimal(str(order_result.get('average_price', 0))),
                                leverage=leverage,
                                order_id=order_id,
                                order_status=order_status,
                                trade_value=Decimal(str(order_result.get('filled_amount', 0))) * Decimal(str(order_result.get('average_price', 0))),
                                fee=Decimal(str(order_result.get('fee', 0)))
                            )
                            snapshot_db.add(trade_record)
                            snapshot_db.commit()
                            logger.info(f"[HYPERLIQUID] Trade record saved for {account.name}")
                        finally:
                            snapshot_db.close()
                    except Exception as trade_err:
                        logger.warning(f"Failed to save Hyperliquid trade record: {trade_err}")

                elif order_status == 'resting':
                    logger.info(
                        f"[HYPERLIQUID] Order placed (resting) for {account.name}: "
                        f"{operation.upper()} {symbol} order_id={order_id}"
                    )
                    save_ai_decision(db, account, decision, portfolio, executed=True)

                else:
                    error_msg = order_result.get('error', 'Unknown error')
                    logger.error(
                        f"[HYPERLIQUID] Order failed for {account.name}: "
                        f"{operation.upper()} {symbol} - {error_msg}"
                    )
                    save_ai_decision(db, account, decision, portfolio, executed=False)
            else:
                logger.error(f"No order result received for {account.name}")
                save_ai_decision(db, account, decision, portfolio, executed=False)

        except Exception as account_err:
            logger.error(f"Error processing Hyperliquid account {account.name}: {account_err}", exc_info=True)
            db.rollback()
        finally:
            db.close()


HYPERLIQUID_TRADE_JOB_ID = "hyperliquid_ai_trade"
