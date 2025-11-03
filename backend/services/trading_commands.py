"""
Trading Commands Service - Handles order execution and trading logic
"""
import logging
import random
from decimal import Decimal
from typing import Dict, Optional, Tuple, List, Iterable

from sqlalchemy.orm import Session

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
            if not account or account.is_active != "true":
                logger.debug(f"Account {account_id} not found or inactive, skipping AI trading")
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

                # Get portfolio data for this account (with current market prices)
                portfolio = _get_portfolio_data(db, account, prices)

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
