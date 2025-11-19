"""
Trading Commands Service - Handles order execution and trading logic
"""
import logging
import random
from decimal import Decimal
from typing import Dict, Optional, Tuple, List, Iterable, Any

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
    SUPPORTED_SYMBOLS,
)
from services.hyperliquid_symbol_service import (
    get_selected_symbols as get_hyperliquid_selected_symbols,
    get_available_symbol_map as get_hyperliquid_symbol_map,
    get_symbol_display as get_hyperliquid_symbol_display,
)


logger = logging.getLogger(__name__)

AI_TRADING_SYMBOLS: List[str] = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]
ORACLE_PRICE_DEVIATION_LIMIT_PERCENT = 1.0


def _enforce_price_bounds(
    *,
    symbol: str,
    account_name: str,
    operation: str,
    current_price: float,
    requested_price: float,
) -> Tuple[float, float, bool]:
    """Clamp requested price into ±1% oracle window and log adjustments."""

    if current_price <= 0 or requested_price <= 0:
        return requested_price, 0.0, False

    limit = ORACLE_PRICE_DEVIATION_LIMIT_PERCENT / 100
    lower_bound = current_price * (1 - limit)
    upper_bound = current_price * (1 + limit)

    clamped_price = max(min(requested_price, upper_bound), lower_bound)
    deviation_percent = abs(requested_price - current_price) / current_price * 100
    was_adjusted = clamped_price != requested_price

    if was_adjusted:
        logger.warning(
            f"[AI COMPLIANCE] {operation.upper()} {symbol} price from AI for {account_name} "
            f"violates Hyperliquid ±1% rule. market=${current_price:.2f}, "
            f"requested=${requested_price:.2f}, deviation={deviation_percent:.2f}%. "
            f"Adjusted to ${clamped_price:.2f}."
        )

    return clamped_price, deviation_percent, was_adjusted


def _get_symbol_name(symbol: str) -> str:
    return SUPPORTED_SYMBOLS.get(symbol, symbol)


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

                # All accounts now use Hyperliquid trading pipeline
                logger.info(f"Processing Hyperliquid trading for account {account.name}")
                place_ai_driven_hyperliquid_order(account_id=account.id)

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
        name = _get_symbol_name(symbol)

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

def place_ai_driven_hyperliquid_order(
    account_ids: Optional[Iterable[int]] = None,
    account_id: Optional[int] = None,
    bypass_auto_trading: bool = False,
) -> None:
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

            if not bypass_auto_trading and getattr(account, "auto_trading_enabled", "false") != "true":
                logger.debug(
                    "Account %s auto trading disabled - skipping Hyperliquid AI order",
                    account_id,
                )
                return

            accounts = [account]
        else:
            # Get all active accounts with auto trading enabled
            accounts = db.query(Account).filter(
                Account.is_active == "true",
                Account.auto_trading_enabled == "true"
            ).all()

            if not accounts:
                logger.debug("No active accounts with auto trading enabled")
                return

            if account_ids is not None:
                id_set = {int(acc_id) for acc_id in account_ids}
                accounts = [acc for acc in accounts if acc.id in id_set]
                if not accounts:
                    logger.debug(f"No matching Hyperliquid accounts for provided IDs: {account_ids}")
                    return
    finally:
        db.close()

    # Determine configured Hyperliquid symbols
    selected_symbols = get_hyperliquid_selected_symbols()
    if not selected_symbols:
        logger.warning("No Hyperliquid watchlist configured, skipping Hyperliquid trading")
        return

    prices = _get_market_prices(selected_symbols)
    if not prices:
        logger.warning("Failed to fetch market prices, skipping Hyperliquid trading")
        return

    # Sampling data availability (informational)
    from services.sampling_pool import sampling_pool
    available_symbols = []
    for sym in selected_symbols:
        samples_data = sampling_pool.get_samples(sym)
        if samples_data:
            available_symbols.append(sym)

    if available_symbols:
        logger.info(f"Available sampling symbols for Hyperliquid: {', '.join(available_symbols)}")
    else:
        logger.warning("No sampling data available for configured Hyperliquid symbols")

    symbol_metadata_map = get_hyperliquid_symbol_map()
    prompt_symbol_metadata = {}
    for sym in selected_symbols:
        entry = dict(symbol_metadata_map.get(sym, {}))
        entry.setdefault("name", sym)
        prompt_symbol_metadata[sym] = entry
    symbol_whitelist = set(selected_symbols)

    # Process each account with separate database connections
    for account in accounts:
        # Each account gets its own database connection
        db = SessionLocal()
        # PostgreSQL handles concurrent access natively
        try:
            # Validate account configuration completeness
            validation_errors = []

            # Check model configuration
            if not account.api_key or not account.model:
                validation_errors.append("AI model/API key not configured")

            # Check strategy configuration
            from database.models import AccountStrategyConfig
            strategy = db.query(AccountStrategyConfig).filter(
                AccountStrategyConfig.account_id == account.id,
                AccountStrategyConfig.enabled == "true"
            ).first()
            if not strategy:
                validation_errors.append("trading strategy not configured or disabled")

            # If there are validation errors, skip this account with clear warning
            if validation_errors:
                logger.warning(
                    f"⚠️  AI Trader '{account.name}' (ID: {account.id}) skipped - "
                    f"Configuration incomplete: {', '.join(validation_errors)}. "
                    f"Please complete configuration in AI Traders management page."
                )
                continue

            # Get global trading mode (environment) for Hyperliquid
            from services.hyperliquid_environment import get_global_trading_mode
            environment = get_global_trading_mode(db)
            logger.info(f"Processing Hyperliquid trading for account: {account.name} (environment: {environment})")

            # Get Hyperliquid client (will check wallet configuration)
            try:
                client = get_hyperliquid_client(db, account.id, override_environment=environment)
            except ValueError as wallet_err:
                # Wallet not configured - log clear warning
                logger.warning(
                    f"⚠️  AI Trader '{account.name}' (ID: {account.id}) skipped - "
                    f"Hyperliquid wallet not configured. {str(wallet_err)} "
                    f"Please configure wallet in AI Traders management page."
                )
                continue
            except Exception as client_err:
                logger.error(f"Failed to get Hyperliquid client for {account.name}: {client_err}")
                continue
            wallet_address = getattr(client, "wallet_address", None)
            decision_kwargs = {"wallet_address": wallet_address}

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

            except Exception as state_err:
                logger.error(f"Failed to get account state for {account.name}: {state_err}")
                continue

            # Get open positions from Hyperliquid (must check before skipping due to equity)
            try:
                positions = client.get_positions(db)
                logger.info(f"Account {account.name} has {len(positions)} open positions")
            except Exception as pos_err:
                logger.error(f"Failed to get positions for {account.name}: {pos_err}")
                positions = []

            # Check equity after getting positions - allow close operations even with zero equity
            if total_equity <= 0 and len(positions) == 0:
                logger.warning(
                    f"⚠️  Account {account.name} (ID: {account.id}) skipped - No balance to trade! "
                    f"Equity: ${total_equity:.2f}, Positions: 0. "
                    f"Please deposit funds to wallet {wallet_address} to enable trading."
                )
                continue

            if total_equity <= 0 and len(positions) > 0:
                logger.warning(
                    f"⚠️  Account {account.name} (ID: {account.id}) has ZERO equity but {len(positions)} open positions! "
                    f"Equity: ${total_equity:.2f}, Allowing AI to decide on close/risk management operations."
                )

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
            decisions = call_ai_for_decision(
                db,
                account,
                portfolio,
                prices,
                symbols=selected_symbols,
                hyperliquid_state=hyperliquid_state,
                symbol_metadata=prompt_symbol_metadata,
            )

            if not decisions:
                logger.warning(f"Failed to get AI decision for {account.name}, skipping")
                continue

            decision_priority = {"close": 0, "sell": 1, "buy": 2, "hold": 3}
            ordered_decisions = sorted(
                decisions,
                key=lambda d: decision_priority.get(str(d.get("operation", "")).lower(), 4),
            )

            for decision in ordered_decisions:
                if not isinstance(decision, dict):
                    logger.warning(f"Skipping malformed Hyperliquid decision for {account.name}: {decision}")
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

                if operation not in ["buy", "sell", "hold", "close"]:
                    logger.warning(f"Invalid operation '{operation}' from AI for {account.name}")
                    save_ai_decision(db, account, decision, portfolio, executed=False, **decision_kwargs)
                    continue

                if operation == "hold":
                    logger.info(f"AI decided to HOLD for {account.name}")
                    save_ai_decision(db, account, decision, portfolio, executed=True, **decision_kwargs)
                    continue

                if symbol not in symbol_whitelist:
                    logger.warning(f"Symbol '{symbol}' not in Hyperliquid watchlist for {account.name}")
                    save_ai_decision(db, account, decision, portfolio, executed=False, **decision_kwargs)
                    continue

                max_leverage = getattr(account, "max_leverage", 3)
                if leverage < 1 or leverage > max_leverage:
                    logger.warning(
                        f"Invalid leverage {leverage}x from AI (max: {max_leverage}x), "
                        f"using default {getattr(account, 'default_leverage', 1)}x"
                    )
                    leverage = getattr(account, "default_leverage", 1)

                if target_portion <= 0 or target_portion > 1:
                    logger.warning(f"Invalid target_portion {target_portion} from AI for {account.name}")
                    save_ai_decision(db, account, decision, portfolio, executed=False, **decision_kwargs)
                    continue

                price = prices.get(symbol)
                if not price or price <= 0:
                    logger.warning(f"Invalid price for {symbol} for {account.name}")
                    save_ai_decision(db, account, decision, portfolio, executed=False, **decision_kwargs)
                    continue

                order_result = None

                if operation == "buy":
                    order_value = available_balance * target_portion
                    quantity = round(order_value / price, 6)

                    # Extract TP/SL and time_in_force from AI decision
                    take_profit_price = decision.get("take_profit_price")
                    stop_loss_price = decision.get("stop_loss_price")
                    time_in_force = decision.get("time_in_force", "Ioc")  # Default to Ioc (market-like)

                    # Price validation for BUY operation
                    if max_price is not None:
                        price_to_use = max_price
                        price_to_use, price_deviation_percent, _ = _enforce_price_bounds(
                            symbol=symbol,
                            account_name=account.name,
                            operation="buy",
                            current_price=price,
                            requested_price=price_to_use,
                        )
                        logger.info(
                            f"Using AI-provided max_price for BUY {symbol}: "
                            f"market=${price:.2f}, order=${price_to_use:.2f}, "
                            f"deviation={price_deviation_percent:.2f}%"
                        )
                    else:
                        # AI did not provide max_price - use market price (already within 1%)
                        price_to_use = price
                        logger.warning(
                            f"⚠️  AI COMPLIANCE ISSUE - BUY {symbol}: "
                            f"AI did not provide max_price in decision. "
                            f"Using market price: ${price_to_use:.2f}. "
                            f"Prompt should require max_price for all BUY operations."
                        )

                    logger.info(
                        f"[HYPERLIQUID {environment.upper()}] Placing BUY order: "
                        f"{symbol} size={quantity} leverage={leverage}x TIF={time_in_force} "
                        f"TP={take_profit_price} SL={stop_loss_price}"
                    )

                    # Use native API for all orders
                    order_result = client.place_order_with_tpsl(
                        db=db,
                        symbol=symbol,
                        is_buy=True,
                        size=quantity,
                        price=price_to_use,
                        leverage=leverage,
                        time_in_force=time_in_force,
                        reduce_only=False,
                        take_profit_price=take_profit_price,
                        stop_loss_price=stop_loss_price
                    )

                elif operation == "sell":
                    order_value = available_balance * target_portion
                    quantity = round(order_value / price, 6)

                    # Extract TP/SL and time_in_force from AI decision
                    take_profit_price = decision.get("take_profit_price")
                    stop_loss_price = decision.get("stop_loss_price")
                    time_in_force = decision.get("time_in_force", "Ioc")  # Default to Ioc (market-like)

                    # Price validation for SELL operation
                    if min_price is not None:
                        price_to_use = min_price
                        price_to_use, price_deviation_percent, _ = _enforce_price_bounds(
                            symbol=symbol,
                            account_name=account.name,
                            operation="sell",
                            current_price=price,
                            requested_price=price_to_use,
                        )
                        logger.info(
                            f"Using AI-provided min_price for SELL {symbol}: "
                            f"market=${price:.2f}, order=${price_to_use:.2f}, "
                            f"deviation={price_deviation_percent:.2f}%"
                        )
                    else:
                        # AI did not provide min_price - use market price
                        price_to_use = price
                        logger.warning(
                            f"⚠️  AI COMPLIANCE ISSUE - SELL {symbol}: "
                            f"AI did not provide min_price in decision. "
                            f"Using market price: ${price_to_use:.2f}. "
                            f"Prompt should require min_price for all SELL operations."
                        )

                    logger.info(
                        f"[HYPERLIQUID {environment.upper()}] Placing SELL order: "
                        f"{symbol} size={quantity} leverage={leverage}x TIF={time_in_force} "
                        f"TP={take_profit_price} SL={stop_loss_price}"
                    )

                    # Use native API for all orders
                    order_result = client.place_order_with_tpsl(
                        db=db,
                        symbol=symbol,
                        is_buy=False,
                        size=quantity,
                        price=price_to_use,
                        leverage=leverage,
                        time_in_force=time_in_force,
                        reduce_only=False,
                        take_profit_price=take_profit_price,
                        stop_loss_price=stop_loss_price
                    )

                elif operation == "close":
                    position_to_close = None
                    for pos in positions:
                        if pos.get('coin') == symbol:
                            position_to_close = pos
                            break

                    if position_to_close:
                        position_size = abs(position_to_close.get('szi', 0))
                        is_long = (position_to_close.get('szi', 0) or 0) > 0
                    else:
                        # Fall back to portfolio snapshot from prompt context
                        logger.warning(
                            f"⚠️  Position {symbol} not found in real-time positions list. "
                            f"Using portfolio snapshot data from AI prompt context. "
                            f"This may indicate position was closed by another operation or data sync issue."
                        )
                        portfolio_positions = portfolio.get('positions') or {}
                        fallback_position = portfolio_positions.get(symbol)
                        if not fallback_position:
                            logger.warning(f"Unable to locate Hyperliquid position data for {symbol}; skipping close.")
                            save_ai_decision(db, account, decision, portfolio, executed=False, **decision_kwargs)
                            continue
                        quantity = float(fallback_position.get('quantity') or 0)
                        position_size = abs(quantity)
                        is_long = quantity > 0

                    # Validate position exists and size is non-zero
                    if position_size <= 0:
                        logger.warning(f"No position to close for {symbol} (size={position_size}), skipping close operation")
                        save_ai_decision(db, account, decision, portfolio, executed=False, **decision_kwargs)
                        continue

                    close_size = position_size * target_portion

                    logger.info(
                        f"[HYPERLIQUID {environment.upper()}] Closing position: "
                        f"{symbol} size={close_size} (closing {'long' if is_long else 'short'})"
                    )

                    current_price = prices.get(symbol, 0)

                    # Price validation for Hyperliquid 1% oracle limit
                    max_price_close = decision.get("max_price")

                    if is_long:
                        ai_close_price = min_price
                        price_field_used = "min_price"
                    else:
                        ai_close_price = max_price_close if max_price_close is not None else min_price
                        price_field_used = "max_price" if max_price_close is not None else "min_price"

                        if max_price_close is None and min_price is not None:
                            logger.warning(
                                f"⚠️  AI COMPLIANCE ISSUE - CLOSE {symbol}: "
                                f"Short position provided min_price instead of max_price. "
                                f"Treating min_price=${min_price:.2f} as max_price for compatibility."
                            )

                    if ai_close_price:
                        close_price = ai_close_price
                        close_price, price_deviation_percent, _ = _enforce_price_bounds(
                            symbol=symbol,
                            account_name=account.name,
                            operation="close",
                            current_price=current_price,
                            requested_price=close_price,
                        )

                        # Check if close price is on the wrong side of market OR too close to oracle boundaries
                        if not is_long and close_price < current_price:
                            # Close Short: buy price too low, raise to slightly above market
                            logger.warning(
                                f"⚠️  AI COMPLIANCE ISSUE - CLOSE {symbol}: "
                                f"Short close limit ${close_price:.2f} sits below market ${current_price:.2f}. "
                                f"Adjusting to ensure IOC buy can match resting asks."
                            )
                            close_price, price_deviation_percent, _ = _enforce_price_bounds(
                                symbol=symbol,
                                account_name=account.name,
                                operation="close",
                                current_price=current_price,
                                requested_price=current_price * 1.005,
                            )
                        elif not is_long and close_price > current_price * 1.005:
                            # Close Short: buy price too close to +1% oracle limit
                            logger.warning(
                                f"⚠️  AI COMPLIANCE ISSUE - CLOSE {symbol}: "
                                f"Short close limit ${close_price:.2f} too close to oracle upper boundary. "
                                f"Market ${current_price:.2f}. Adjusting to 1.005x for safer execution."
                            )
                            close_price, price_deviation_percent, _ = _enforce_price_bounds(
                                symbol=symbol,
                                account_name=account.name,
                                operation="close",
                                current_price=current_price,
                                requested_price=current_price * 1.005,
                            )
                        elif is_long and close_price > current_price:
                            # Close Long: sell price too high, lower to slightly below market
                            logger.warning(
                                f"⚠️  AI COMPLIANCE ISSUE - CLOSE {symbol}: "
                                f"Long close limit ${close_price:.2f} sits above market ${current_price:.2f}. "
                                f"Adjusting to ensure IOC sell can match resting bids."
                            )
                            close_price, price_deviation_percent, _ = _enforce_price_bounds(
                                symbol=symbol,
                                account_name=account.name,
                                operation="close",
                                current_price=current_price,
                                requested_price=current_price * 0.995,
                            )
                        elif is_long and close_price < current_price * 0.995:
                            # Close Long: sell price too close to -1% oracle limit
                            logger.warning(
                                f"⚠️  AI COMPLIANCE ISSUE - CLOSE {symbol}: "
                                f"Long close limit ${close_price:.2f} too close to oracle lower boundary. "
                                f"Market ${current_price:.2f}. Adjusting to 0.995x for safer execution."
                            )
                            close_price, price_deviation_percent, _ = _enforce_price_bounds(
                                symbol=symbol,
                                account_name=account.name,
                                operation="close",
                                current_price=current_price,
                                requested_price=current_price * 0.995,
                            )

                        logger.info(
                            f"Using AI-provided {price_field_used} for CLOSE {symbol}: "
                            f"market=${current_price:.2f}, order=${close_price:.2f}, "
                            f"deviation={price_deviation_percent:.2f}%"
                        )
                    else:
                        # AI did not provide relevant close price - use safe default
                        fallback_multiplier = 0.995 if is_long else 1.005
                        close_price = current_price * fallback_multiplier
                        close_price, _, _ = _enforce_price_bounds(
                            symbol=symbol,
                            account_name=account.name,
                            operation="close",
                            current_price=current_price,
                            requested_price=close_price,
                        )
                        logger.warning(
                            f"⚠️  AI COMPLIANCE ISSUE - CLOSE {symbol}: "
                            f"AI did not provide {'min_price' if is_long else 'max_price'} in decision. "
                            f"Using fallback price: market=${current_price:.2f}, order=${close_price:.2f}. "
                            f"Prompt should require {'min_price for closing longs' if is_long else 'max_price for closing shorts'} in all CLOSE operations."
                        )

                    # Retry logic with progressive price adjustment for IoC close orders
                    max_retries = 4
                    retry_count = 0
                    order_result = None
                    fallback_gtc_attempted = False

                    # Progressive price multipliers for each retry (conservative start + dense sampling)
                    # For long close (sell): move down to increase match probability
                    # For short close (buy): move up to increase match probability
                    # Strategy: Start conservatively, progressively sample through safe zone to boundary
                    if is_long:
                        price_multipliers = [0.996, 0.994, 0.992, 0.99]  # Selling: 0.6% coverage, 4 sampling points
                    else:
                        price_multipliers = [1.004, 1.006, 1.008, 1.01]  # Buying: 0.6% coverage, 4 sampling points

                    while retry_count < max_retries and order_result is None:
                        # Use AI price for first attempt, then use progressive multipliers
                        if retry_count == 0:
                            attempt_price = close_price
                        else:
                            # Refresh market price for retry attempts
                            current_price_retry = prices.get(symbol, current_price)
                            attempt_price = current_price_retry * price_multipliers[retry_count]
                            attempt_price, _, _ = _enforce_price_bounds(
                                symbol=symbol,
                                account_name=account.name,
                                operation="close",
                                current_price=current_price_retry,
                                requested_price=attempt_price,
                            )
                            logger.info(
                                f"[RETRY {retry_count}/{max_retries}] CLOSE {symbol}: "
                                f"Adjusting price to ${attempt_price:.2f} "
                                f"(market=${current_price_retry:.2f}, multiplier={price_multipliers[retry_count]})"
                            )

                        # Attempt order placement
                        attempt_result = client.place_order_with_tpsl(
                            db=db,
                            symbol=symbol,
                            is_buy=(not is_long),
                            size=close_size,
                            price=attempt_price,
                            leverage=1,
                            time_in_force="Ioc",  # Always use Ioc for closing positions
                            reduce_only=True,
                            take_profit_price=None,
                            stop_loss_price=None
                        )

                        # Check if order succeeded
                        if attempt_result and attempt_result.get('status') == 'filled':
                            order_result = attempt_result
                            if retry_count > 0:
                                logger.info(
                                    f"✅ CLOSE {symbol} succeeded on retry {retry_count} "
                                    f"with price ${attempt_price:.2f}"
                                )
                            break

                        # Check if we should retry
                        error_msg = attempt_result.get('error', '') if attempt_result else ''
                        should_retry = (
                            'could not immediately match' in error_msg.lower() or
                            'no resting orders' in error_msg.lower()
                        )

                        if should_retry and retry_count < max_retries - 1:
                            retry_count += 1
                            logger.warning(
                                f"⚠️  CLOSE {symbol} failed (attempt {retry_count}/{max_retries}): {error_msg}. "
                                f"Will retry with more aggressive price..."
                            )
                        else:
                            # Either non-retryable error or max retries reached
                            order_result = attempt_result
                            if retry_count > 0:
                                logger.error(
                                    f"❌ CLOSE {symbol} failed after {retry_count + 1} attempts. "
                                    f"Last error: {error_msg}"
                                )
                            break

                    # If IOC retries failed, place a final reduce-only GTC order at the safe boundary
                    if (not order_result or order_result.get('status') != 'filled') and not fallback_gtc_attempted:
                        fallback_gtc_attempted = True
                        boundary_multiplier = 0.99 if is_long else 1.01
                        latest_price = prices.get(symbol, current_price)
                        if not latest_price or latest_price <= 0:
                            latest_price = current_price or close_price
                        fallback_price = latest_price * boundary_multiplier
                        fallback_price, _, _ = _enforce_price_bounds(
                            symbol=symbol,
                            account_name=account.name,
                            operation="close",
                            current_price=latest_price,
                            requested_price=fallback_price,
                        )
                        logger.warning(
                            f"⚠️  CLOSE {symbol} entering fallback mode: placing reduce-only GTC at ${fallback_price:.2f} "
                            f"(latest=${latest_price:.2f}). Order will rest until filled."
                        )
                        order_result = client.place_order_with_tpsl(
                            db=db,
                            symbol=symbol,
                            is_buy=(not is_long),
                            size=close_size,
                            price=fallback_price,
                            leverage=1,
                            time_in_force="Gtc",
                            reduce_only=True,
                            take_profit_price=None,
                            stop_loss_price=None
                        )

                else:
                    continue

                if order_result:
                    print(f"[DEBUG] {operation.upper()} order_result: {order_result}")
                    order_status = order_result.get('status')
                    order_id = order_result.get('order_id')

                    if order_status == 'filled':
                        logger.info(
                            f"[HYPERLIQUID] Order executed successfully for {account.name}: "
                            f"{operation.upper()} {symbol} order_id={order_id}"
                        )
                        save_ai_decision(db, account, decision, portfolio, executed=True, **decision_kwargs)

                        try:
                            from database.snapshot_connection import SnapshotSessionLocal
                            from database.snapshot_models import HyperliquidTrade
                            from decimal import Decimal

                            snapshot_db = SnapshotSessionLocal()
                            try:
                                trade_record = HyperliquidTrade(
                                    account_id=account.id,
                                    environment=environment,
                                    wallet_address=wallet_address,
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
                        save_ai_decision(db, account, decision, portfolio, executed=True, **decision_kwargs)

                    else:
                        error_msg = order_result.get('error', 'Unknown error')
                        logger.error(
                            f"[HYPERLIQUID] Order failed for {account.name}: "
                            f"{operation.upper()} {symbol} - {error_msg}"
                        )
                        save_ai_decision(db, account, decision, portfolio, executed=False, **decision_kwargs)
                else:
                    logger.error(f"No order result received for {account.name}")
                    save_ai_decision(db, account, decision, portfolio, executed=False, **decision_kwargs)

        except Exception as account_err:
            logger.error(f"Error processing Hyperliquid account {account.name}: {account_err}", exc_info=True)
            db.rollback()
        finally:
            db.close()


HYPERLIQUID_TRADE_JOB_ID = "hyperliquid_ai_trade"
