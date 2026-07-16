"""
Alpha Arena aggregated data routes.
Provides completed trades, model chat summaries, and consolidated positions
for showcasing multi-model trading activity on the dashboard.
"""

from datetime import datetime, timezone
from math import sqrt
from statistics import mean, pstdev
from typing import Dict, List, Optional, Tuple
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database.connection import SessionLocal
from database.snapshot_connection import SnapshotSessionLocal
from database.models import (
    Account,
    Trade,
    Position,
    AIDecisionLog,
    Order,
    AccountStrategyConfig,
    PromptTemplate,
    TradingProgram,
    BinanceWallet,
)
from database.snapshot_models import HyperliquidTrade
from services.asset_calculator import calc_positions_value
from services.price_cache import get_cached_price, cache_price
from services.market_data import get_last_price
from services.hyperliquid_trading_client import HyperliquidTradingClient, get_cached_trading_client
from services.hyperliquid_environment import get_hyperliquid_client
from services.hyperliquid_cache import (
    get_cached_account_state,
    get_cached_positions,
)
from utils.encryption import decrypt_private_key
from utils.runtime_diagnostics import get_current_thread_count, log_hot_path_delta
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/arena", tags=["arena"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_latest_price(symbol: str, market: str = "CRYPTO") -> Optional[float]:
    """Get the latest price using cache when possible, fallback to market feed."""
    price = get_cached_price(symbol, market)
    if price is not None:
        return price

    try:
        price = get_last_price(symbol, market)
        if price:
            cache_price(symbol, market, price)
        return price

    except Exception:
        return None


def _get_hyperliquid_positions(db: Session, account_id: Optional[int], environment: str) -> dict:
    """
    Get real-time positions from Hyperliquid API (testnet or mainnet)

    Args:
        db: Database session
        account_id: Optional account ID to filter
        environment: "testnet" or "mainnet"

    Returns:
        Dict with generated_at, trading_mode, and accounts list
    """
    from database.models import HyperliquidWallet

    # Get all AI accounts or specific account (filter hidden accounts for Dashboard)
    accounts_query = db.query(Account).filter(
        Account.account_type == "AI",
        Account.is_active == "true",
        Account.show_on_dashboard == True,
        Account.is_deleted != True
    )

    if account_id:
        accounts_query = accounts_query.filter(Account.id == account_id)

    accounts = accounts_query.all()
    snapshots = []

    for account in accounts:
        # Check if wallet exists for this environment (multi-wallet architecture)
        wallet = db.query(HyperliquidWallet).filter(
            HyperliquidWallet.account_id == account.id,
            HyperliquidWallet.environment == environment,
            HyperliquidWallet.is_active == "true"
        ).first()

        if not wallet:
            logger.debug(f"Account {account.name} (ID: {account.id}) has no {environment} wallet configured, skipping")
            continue

        encrypted_key = wallet.private_key_encrypted

        try:
            cached_state = get_cached_account_state(account.id, environment)
            account_state = cached_state["data"] if cached_state else None

            cached_positions = get_cached_positions(account.id, environment)
            positions_data = cached_positions["data"] if cached_positions else None

            wallet_address = None
            if isinstance(account_state, dict):
                wallet_address = account_state.get("wallet_address")

            client: Optional[HyperliquidTradingClient] = None
            needs_state = account_state is None
            needs_positions = positions_data is None
            needs_wallet = wallet_address is None

            if needs_state or needs_positions or needs_wallet:
                # Use get_hyperliquid_client to support API Wallet mode
                client = get_hyperliquid_client(
                    db, account.id, override_environment=environment
                )

                if needs_state:
                    account_state = client.get_account_state(db)
                    wallet_address = account_state.get("wallet_address") or client.wallet_address
                if needs_positions:
                    positions_data = client.get_positions(db)
                if wallet_address is None:
                    wallet_address = client.wallet_address

            if account_state is None or positions_data is None:
                logger.warning(f"Account {account.id} has no Hyperliquid data available, skipping")
                continue

            # Transform Hyperliquid positions to frontend format
            position_items = []
            total_unrealized = 0.0

            for p in positions_data:
                unrealized_pnl = p.get("unrealized_pnl", 0)
                total_unrealized += unrealized_pnl

                szi = float(p.get("szi", 0) or 0)
                entry_px = float(p.get("entry_px", 0) or 0)
                position_value = float(p.get("position_value", 0) or 0)
                notional = abs(szi) * entry_px
                avg_cost = entry_px
                current_price = position_value / abs(szi) if szi != 0 else entry_px

                position_items.append({
                    "id": 0,  # Hyperliquid positions don't have local DB ID
                    "symbol": p.get("coin", "") or "",
                    "name": p.get("coin", "") or "",
                    "market": "HYPERLIQUID_PERP",
                    "side": "LONG" if szi > 0 else "SHORT",
                    "quantity": abs(szi),
                    "avg_cost": avg_cost,
                    "current_price": current_price,
                    "notional": notional,
                    "current_value": position_value,
                    "unrealized_pnl": float(unrealized_pnl),
                    "leverage": p.get("leverage"),
                    "margin_used": float(p.get("margin_used", 0) or 0),
                    "return_on_equity": float(p.get("return_on_equity", 0) or 0),
                    "percentage": float(p.get("percentage", 0) or 0),
                    "margin_mode": p.get("margin_mode", "cross"),
                    "liquidation_px": float(p.get("liquidation_px", 0) or 0),
                    "max_leverage": p.get("max_leverage"),
                    "leverage_type": p.get("leverage_type"),
                })

            # Calculate total return
            total_equity = account_state.get("total_equity", 0)
            available_balance = account_state.get("available_balance", 0)
            used_margin = account_state.get("used_margin", 0)

            # Positions value is the used margin (capital tied up in positions)
            # Or equivalently: total_equity - available_balance
            positions_value = used_margin

            initial_capital = float(account.initial_capital or 0)
            total_return = None
            if initial_capital > 0:
                total_return = (total_equity - initial_capital) / initial_capital

            snapshots.append({
                "account_id": account.id,
                "account_name": account.name,
                "model": account.model,
                "environment": environment,
                "exchange": "hyperliquid",
                "wallet_address": wallet_address,
                "total_unrealized_pnl": total_unrealized,
                "available_cash": available_balance,
                "used_margin": used_margin,
                "positions_value": positions_value,  # Add positions_value from Hyperliquid data
                "positions": position_items,
                "total_assets": total_equity,
                "margin_usage_percent": account_state.get("margin_usage_percent", 0),
                "margin_mode": "cross",
                "initial_capital": initial_capital,
                "total_return": total_return,
            })

        except Exception as e:
            logger.error(f"Failed to get Hyperliquid positions for account {account.id}: {e}", exc_info=True)
            # Fallback: still expose the account so frontend doesn't think it's missing
            snapshots.append({
                "account_id": account.id,
                "account_name": account.name,
                "model": account.model,
                "environment": environment,
                "wallet_address": wallet.wallet_address if 'wallet' in locals() and wallet else None,
                "total_unrealized_pnl": 0.0,
                "available_cash": 0.0,
                "used_margin": 0.0,
                "positions_value": 0.0,
                "positions": [],
                "total_assets": float(account.initial_capital or 0),
                "margin_usage_percent": 0.0,
                "margin_mode": "cross",
                "initial_capital": float(account.initial_capital or 0),
                "total_return": 0.0,
            })
            continue

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "trading_mode": environment,
        "accounts": snapshots,
    }


def _get_binance_positions(db: Session, account_id: Optional[int], environment: str) -> list:
    """
    Get real-time positions from Binance Futures API.

    Returns:
        List of account snapshot dicts (same format as Hyperliquid snapshots)
    """
    from database.models import BinanceWallet
    from services.binance_trading_client import BinanceTradingClient

    accounts_query = db.query(Account).filter(
        Account.account_type == "AI",
        Account.is_active == "true",
        Account.show_on_dashboard == True,
        Account.is_deleted != True
    )
    if account_id:
        accounts_query = accounts_query.filter(Account.id == account_id)

    accounts = accounts_query.all()
    snapshots = []

    for account in accounts:
        wallet = db.query(BinanceWallet).filter(
            BinanceWallet.account_id == account.id,
            BinanceWallet.environment == environment,
            BinanceWallet.is_active == "true"
        ).first()

        if not wallet:
            continue

        try:
            api_key = decrypt_private_key(wallet.api_key_encrypted)
            secret_key = decrypt_private_key(wallet.secret_key_encrypted)
            client = BinanceTradingClient(
                api_key=api_key,
                secret_key=secret_key,
                environment=environment
            )

            balance = client.get_balance()
            positions_data = client.get_positions()
            rate_limit = client.get_rate_limit()

            snapshots.append(
                _build_binance_snapshot(
                    account, environment, balance,
                    positions_data, rate_limit
                )
            )
        except Exception as e:
            logger.error(
                f"Failed to get Binance positions for account {account.id}: {e}",
                exc_info=True
            )
            snapshots.append(_build_binance_fallback(account, environment))

    return snapshots


def _build_binance_snapshot(
    account, environment, balance, positions_data, rate_limit
) -> dict:
    """Build a Binance account snapshot dict."""
    position_items = []
    total_unrealized = 0.0

    for p in positions_data:
        unrealized_pnl = p.get("unrealized_pnl", 0)
        total_unrealized += unrealized_pnl
        szi = float(p.get("szi", 0) or 0)
        entry_px = float(p.get("entry_px", 0) or 0)
        position_value = float(p.get("position_value", 0) or 0)
        notional = abs(szi) * entry_px
        current_price = position_value / abs(szi) if szi != 0 else entry_px

        position_items.append({
            "id": 0,
            "symbol": p.get("coin", ""),
            "name": p.get("coin", ""),
            "market": "BINANCE_PERP",
            "side": "LONG" if szi > 0 else "SHORT",
            "quantity": abs(szi),
            "avg_cost": entry_px,
            "current_price": current_price,
            "notional": notional,
            "current_value": position_value,
            "unrealized_pnl": float(unrealized_pnl),
            "leverage": p.get("leverage"),
            "margin_used": float(p.get("margin_used", 0) or 0),
            "return_on_equity": 0.0,
            "percentage": 0.0,
            "margin_mode": p.get("leverage_type", "cross"),
            "liquidation_px": float(p.get("liquidation_px", 0) or 0),
            "max_leverage": None,
            "leverage_type": p.get("leverage_type"),
        })

    total_equity = balance.get("total_equity", 0)
    available_balance = balance.get("available_balance", 0)
    used_margin = balance.get("used_margin", 0)
    initial_capital = float(account.initial_capital or 0)
    total_return = None
    if initial_capital > 0:
        total_return = (total_equity - initial_capital) / initial_capital
    margin_pct = (used_margin / total_equity * 100) if total_equity > 0 else 0

    return {
        "account_id": account.id,
        "account_name": account.name,
        "model": account.model,
        "environment": environment,
        "exchange": "binance",
        "wallet_address": None,
        "total_unrealized_pnl": total_unrealized,
        "available_cash": available_balance,
        "used_margin": used_margin,
        "positions_value": used_margin,
        "positions": position_items,
        "total_assets": total_equity,
        "margin_usage_percent": round(margin_pct, 1),
        "margin_mode": "cross",
        "initial_capital": initial_capital,
        "total_return": total_return,
        "rate_limit": rate_limit,
    }


def _build_binance_fallback(account, environment) -> dict:
    """Build a fallback snapshot when Binance API call fails."""
    return {
        "account_id": account.id,
        "account_name": account.name,
        "model": account.model,
        "environment": environment,
        "exchange": "binance",
        "wallet_address": None,
        "total_unrealized_pnl": 0.0,
        "available_cash": 0.0,
        "used_margin": 0.0,
        "positions_value": 0.0,
        "positions": [],
        "total_assets": float(account.initial_capital or 0),
        "margin_usage_percent": 0.0,
        "margin_mode": "cross",
        "initial_capital": float(account.initial_capital or 0),
        "total_return": 0.0,
        "rate_limit": None,
    }


def _analyze_balance_series(balances: List[float]) -> Tuple[float, float, List[float], float]:
    '''Return biggest gain/loss deltas, percentage returns, and balance volatility.'''
    if len(balances) < 2:
        return 0.0, 0.0, [], 0.0

    biggest_gain = float('-inf')
    biggest_loss = float('inf')
    returns: List[float] = []

    previous = balances[0]

    for current in balances[1:]:
        delta = current - previous
        if delta > biggest_gain:
            biggest_gain = delta
        if delta < biggest_loss:
            biggest_loss = delta

        if previous not in (0, None):
            try:
                returns.append(delta / previous)
            except ZeroDivisionError:
                pass

        previous = current

    if biggest_gain == float('-inf'):
        biggest_gain = 0.0
    if biggest_loss == float('inf'):
        biggest_loss = 0.0

    volatility = pstdev(balances) if len(balances) > 1 else 0.0

    return biggest_gain, biggest_loss, returns, volatility


def _compute_sharpe_ratio(returns: List[float]) -> Optional[float]:
    '''Compute a simple Sharpe ratio approximation using sample returns.'''
    if len(returns) < 2:
        return None

    avg_return = mean(returns)
    volatility = pstdev(returns)
    if volatility == 0:
        return None

    scaled_factor = sqrt(len(returns))
    return avg_return / volatility * scaled_factor


def _aggregate_account_stats(db: Session, account: Account) -> Dict[str, Optional[float]]:
    '''Aggregate trade and decision statistics for a given account.'''
    initial_capital = float(account.initial_capital or 0)
    current_cash = float(account.current_cash or 0)
    positions_value = calc_positions_value(db, account.id)
    total_assets = positions_value + current_cash
    total_pnl = total_assets - initial_capital
    total_return_pct = (
        (total_assets - initial_capital) / initial_capital if initial_capital else None
    )

    trades: List[Trade] = (
        db.query(Trade)
        .filter(Trade.account_id == account.id)
        .order_by(Trade.trade_time.asc())
        .all()
    )
    trade_count = len(trades)
    total_fees = sum(float(trade.commission or 0) for trade in trades)
    total_volume = sum(
        abs(float(trade.price or 0) * float(trade.quantity or 0)) for trade in trades
    )
    first_trade_time = trades[0].trade_time.isoformat() if trades else None
    last_trade_time = trades[-1].trade_time.isoformat() if trades else None

    decisions: List[AIDecisionLog] = (
        db.query(AIDecisionLog)
        .filter(AIDecisionLog.account_id == account.id)
        .order_by(AIDecisionLog.decision_time.asc())
        .all()
    )
    balances = [
        float(dec.total_balance)
        for dec in decisions
        if dec.total_balance is not None
    ]

    biggest_gain, biggest_loss, returns, balance_volatility = _analyze_balance_series(
        balances
    )
    sharpe_ratio = _compute_sharpe_ratio(returns)

    wins = len([r for r in returns if r > 0])
    losses = len([r for r in returns if r < 0])
    win_rate = wins / len(returns) if returns else None
    loss_rate = losses / len(returns) if returns else None

    executed_decisions = len([d for d in decisions if d.executed == 'true'])
    decision_execution_rate = (
        executed_decisions / len(decisions) if decisions else None
    )
    avg_target_portion = (
        mean(float(d.target_portion or 0) for d in decisions) if decisions else None
    )

    avg_decision_interval_minutes = None
    if len(decisions) > 1:
        intervals = []
        previous = decisions[0].decision_time
        for decision in decisions[1:]:
            if decision.decision_time and previous:
                delta = decision.decision_time - previous
                intervals.append(delta.total_seconds() / 60.0)
            previous = decision.decision_time
        avg_decision_interval_minutes = mean(intervals) if intervals else None

    return {
        'account_id': account.id,
        'account_name': account.name,
        'model': account.model,
        'initial_capital': initial_capital,
        'current_cash': current_cash,
        'positions_value': positions_value,
        'total_assets': total_assets,
        'total_pnl': total_pnl,
        'total_return_pct': total_return_pct,
        'total_fees': total_fees,
        'trade_count': trade_count,
        'total_volume': total_volume,
        'first_trade_time': first_trade_time,
        'last_trade_time': last_trade_time,
        'biggest_gain': biggest_gain,
        'biggest_loss': biggest_loss,
        'win_rate': win_rate,
        'loss_rate': loss_rate,
        'sharpe_ratio': sharpe_ratio,
        'balance_volatility': balance_volatility,
        'decision_count': len(decisions),
        'executed_decisions': executed_decisions,
        'decision_execution_rate': decision_execution_rate,
        'avg_target_portion': avg_target_portion,
        'avg_decision_interval_minutes': avg_decision_interval_minutes,
    }


@router.get("/trades")
def get_completed_trades(
    limit: int = Query(100, ge=1, le=500),
    account_id: Optional[int] = None,
    trading_mode: Optional[str] = Query(None, regex="^(paper|testnet|mainnet)$"),
    wallet_address: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    exchange: Optional[str] = Query(None, regex="^(hyperliquid|binance)$"),
    db: Session = Depends(get_db),
):
    """Return recent trades across all AI accounts, filtered by trading mode."""
    start_threads = get_current_thread_count()
    start_time = time.monotonic()

    def _log_request() -> None:
        log_hot_path_delta(
            logger,
            "arena:trades",
            "/api/arena/trades",
            start_threads,
            start_time,
            account_id=account_id,
            trading_mode=trading_mode,
            limit=limit,
            exchange=exchange,
        )

    if wallet_address and trading_mode not in ("testnet", "mainnet"):
        _log_request()
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "accounts": [],
            "trades": [],
        }
    if trading_mode in ("testnet", "mainnet"):
        snapshot_db = SnapshotSessionLocal()
        try:
            query = snapshot_db.query(HyperliquidTrade).order_by(desc(HyperliquidTrade.trade_time))
            # Strictly filter by environment and exclude NULL
            query = query.filter(
                HyperliquidTrade.environment == trading_mode,
                HyperliquidTrade.environment.isnot(None)
            )
            if account_id:
                query = query.filter(HyperliquidTrade.account_id == account_id)
            if wallet_address:
                query = query.filter(HyperliquidTrade.wallet_address == wallet_address)
            if symbol:
                query = query.filter(HyperliquidTrade.symbol == symbol)

            hyper_trades = query.limit(limit).all()
        finally:
            snapshot_db.close()

        if not hyper_trades:
            _log_request()
            return {
                "generated_at": datetime.utcnow().isoformat(),
                "accounts": [],
                "trades": [],
            }

        account_ids = {trade.account_id for trade in hyper_trades}
        account_map = {
            acc.id: acc
            for acc in db.query(Account).filter(Account.id.in_(account_ids), Account.is_deleted != True).all()
        }

        # Batch fetch decision logs to build order relationships
        # We need to identify: main orders, SL orders, TP orders
        order_ids = {trade.order_id for trade in hyper_trades if trade.order_id}

        # Query decisions that have any of these order IDs as main/sl/tp
        from sqlalchemy import or_
        decisions = []
        if order_ids:
            decisions = db.query(AIDecisionLog).filter(
                or_(
                    AIDecisionLog.hyperliquid_order_id.in_(order_ids),
                    AIDecisionLog.sl_order_id.in_(order_ids),
                    AIDecisionLog.tp_order_id.in_(order_ids),
                )
            ).all()

        # Build mappings:
        # 1. main_order_id -> decision (for signal/prompt info)
        # 2. sl/tp_order_id -> main_order_id (for nesting)
        decision_by_main_order = {}
        sl_to_main = {}  # sl_order_id -> hyperliquid_order_id
        tp_to_main = {}  # tp_order_id -> hyperliquid_order_id
        prompt_template_ids = set()
        program_ids = set()

        for d in decisions:
            if d.hyperliquid_order_id:
                decision_by_main_order[str(d.hyperliquid_order_id)] = d
                if d.prompt_template_id:
                    # Separate by decision_source_type
                    source_type = d.decision_source_type or "prompt_template"
                    if source_type == "program":
                        program_ids.add(d.prompt_template_id)
                    else:
                        prompt_template_ids.add(d.prompt_template_id)
            if d.sl_order_id and d.hyperliquid_order_id:
                sl_to_main[str(d.sl_order_id)] = str(d.hyperliquid_order_id)
            if d.tp_order_id and d.hyperliquid_order_id:
                tp_to_main[str(d.tp_order_id)] = str(d.hyperliquid_order_id)

        # Batch fetch prompt template names
        prompt_template_map = {}
        if prompt_template_ids:
            templates = db.query(PromptTemplate).filter(PromptTemplate.id.in_(prompt_template_ids), PromptTemplate.is_deleted == "false").all()
            prompt_template_map = {t.id: t.name for t in templates}

        # Batch fetch program names
        program_map = {}
        if program_ids:
            programs = db.query(TradingProgram).filter(TradingProgram.id.in_(program_ids), TradingProgram.is_deleted != True).all()
            program_map = {p.id: p.name for p in programs}

        # Also query ProgramExecutionLog for orders not in AIDecisionLog
        # This handles Program Trader orders that don't go through save_ai_decision
        from database.models import ProgramExecutionLog, SignalPool
        program_logs = []
        if order_ids:
            program_logs = db.query(ProgramExecutionLog).filter(
                or_(
                    ProgramExecutionLog.hyperliquid_order_id.in_(order_ids),
                    ProgramExecutionLog.sl_order_id.in_(order_ids),
                    ProgramExecutionLog.tp_order_id.in_(order_ids),
                )
            ).all()

        # Build mappings for ProgramExecutionLog
        program_log_by_main_order = {}
        program_sl_to_main = {}
        program_tp_to_main = {}
        program_log_program_ids = set()
        program_log_signal_pool_ids = set()

        for pl in program_logs:
            if pl.hyperliquid_order_id:
                program_log_by_main_order[str(pl.hyperliquid_order_id)] = pl
                if pl.program_id:
                    program_log_program_ids.add(pl.program_id)
                if pl.signal_pool_id:
                    program_log_signal_pool_ids.add(pl.signal_pool_id)
            if pl.sl_order_id and pl.hyperliquid_order_id:
                program_sl_to_main[str(pl.sl_order_id)] = str(pl.hyperliquid_order_id)
            if pl.tp_order_id and pl.hyperliquid_order_id:
                program_tp_to_main[str(pl.tp_order_id)] = str(pl.hyperliquid_order_id)

        # Batch fetch program names for ProgramExecutionLog
        if program_log_program_ids:
            extra_programs = db.query(TradingProgram).filter(TradingProgram.id.in_(program_log_program_ids), TradingProgram.is_deleted != True).all()
            for p in extra_programs:
                program_map[p.id] = p.name

        # Batch fetch signal pool names
        signal_pool_map = {}
        if program_log_signal_pool_ids:
            pools = db.query(SignalPool).filter(SignalPool.id.in_(program_log_signal_pool_ids)).all()
            signal_pool_map = {p.id: p.pool_name for p in pools}

        # For Binance: build mapping from triggered order ID to main order ID
        # Binance TP/SL orders have two IDs:
        # 1. Algo Order ID (stored in sl_order_id/tp_order_id) - e.g., 1000000012523017
        # 2. Triggered Order ID (in HyperliquidTrade) - e.g., 12165552060
        # We need to map triggered order IDs to main order IDs for proper nesting
        binance_triggered_sl_to_main = {}  # triggered_order_id -> main_order_id
        binance_triggered_tp_to_main = {}  # triggered_order_id -> main_order_id

        # Get Binance wallets to fetch order info
        bn_wallets = db.query(BinanceWallet).filter(BinanceWallet.is_active == "true").all()
        if bn_wallets:
            from services.binance_trading_client import BinanceTradingClient
            from utils.encryption import decrypt_private_key

            for wallet in bn_wallets:
                try:
                    api_key = decrypt_private_key(wallet.api_key_encrypted)
                    secret_key = decrypt_private_key(wallet.secret_key_encrypted)
                    client = BinanceTradingClient(api_key, secret_key, wallet.environment)
                    fills = client.get_user_fills(limit=500)

                    for fill in fills:
                        main_order_id = fill.get("main_order_id")
                        if main_order_id:
                            triggered_oid = fill.get("oid")
                            order_type = fill.get("order_type")
                            if order_type == "sl":
                                binance_triggered_sl_to_main[triggered_oid] = main_order_id
                            elif order_type == "tp":
                                binance_triggered_tp_to_main[triggered_oid] = main_order_id
                except Exception as e:
                    logger.warning(f"Failed to get Binance fills for TP/SL mapping: {e}")

        # First pass: build trade objects and separate main orders from sl/tp orders
        main_trades: Dict[str, dict] = {}  # order_id -> trade dict
        sl_trades: Dict[str, dict] = {}    # order_id -> trade dict (to be nested)
        tp_trades: Dict[str, dict] = {}    # order_id -> trade dict (to be nested)
        other_trades: List[dict] = []      # trades not linked to any AI decision
        accounts_meta: Dict[int, dict] = {}

        for trade in hyper_trades:
            account = account_map.get(trade.account_id)
            if not account:
                logger.warning(f"Hyperliquid trade references missing account_id={trade.account_id}")
                continue

            order_id_str = str(trade.order_id) if trade.order_id else None
            quantity = float(trade.quantity)
            price = float(trade.price)
            notional = float(trade.trade_value)
            commission = float(trade.fee or 0)
            side = trade.side.upper()

            trade_dict = {
                "trade_id": trade.id,
                "order_id": None,
                "order_no": trade.order_id,
                "account_id": account.id,
                "account_name": account.name,
                "model": account.model,
                "side": side,
                "direction": "LONG" if side == "BUY" else "SHORT",
                "symbol": trade.symbol,
                "market": "HYPERLIQUID_PERP",
                "price": price,
                "quantity": quantity,
                "notional": notional,
                "commission": commission,
                "trade_time": trade.trade_time.isoformat() if trade.trade_time else None,
                "wallet_address": trade.wallet_address,
                # Exchange will be set based on decision source, default to hyperliquid
                "exchange": "hyperliquid",
            }

            accounts_meta[account.id] = {
                "account_id": account.id,
                "name": account.name,
                "model": account.model,
            }

            # Classify this trade: main order, SL, TP, or other
            # First check AIDecisionLog (AI Trader)
            if order_id_str and order_id_str in decision_by_main_order:
                # This is a main order from AI Trader
                decision = decision_by_main_order[order_id_str]
                source_type = decision.decision_source_type or "prompt_template"
                trade_dict["signal_trigger_id"] = decision.signal_trigger_id
                trade_dict["prompt_template_id"] = decision.prompt_template_id
                trade_dict["decision_source_type"] = source_type
                # Get exchange from decision (NULL treated as "hyperliquid")
                trade_dict["exchange"] = decision.exchange or "hyperliquid"
                # Get name from correct table based on source type
                if source_type == "program":
                    trade_dict["prompt_template_name"] = program_map.get(decision.prompt_template_id)
                else:
                    trade_dict["prompt_template_name"] = prompt_template_map.get(decision.prompt_template_id)
                trade_dict["related_orders"] = []  # Will be populated later
                main_trades[order_id_str] = trade_dict
            elif order_id_str and order_id_str in sl_to_main:
                # This is a stop-loss order from AI Trader
                trade_dict["order_type"] = "sl"
                sl_trades[order_id_str] = trade_dict
            elif order_id_str and order_id_str in tp_to_main:
                # This is a take-profit order from AI Trader
                trade_dict["order_type"] = "tp"
                tp_trades[order_id_str] = trade_dict
            # Then check ProgramExecutionLog (Program Trader)
            elif order_id_str and order_id_str in program_log_by_main_order:
                # This is a main order from Program Trader
                pl = program_log_by_main_order[order_id_str]
                trade_dict["signal_trigger_id"] = pl.signal_pool_id  # Use signal_pool_id
                trade_dict["prompt_template_id"] = pl.program_id
                trade_dict["decision_source_type"] = "program"
                trade_dict["prompt_template_name"] = program_map.get(pl.program_id) or pl.program_name
                trade_dict["signal_pool_name"] = signal_pool_map.get(pl.signal_pool_id)
                # Get exchange from program log (NULL treated as "hyperliquid")
                trade_dict["exchange"] = pl.exchange or "hyperliquid"
                trade_dict["related_orders"] = []
                main_trades[order_id_str] = trade_dict
            elif order_id_str and order_id_str in program_sl_to_main:
                # This is a stop-loss order from Program Trader
                trade_dict["order_type"] = "sl"
                sl_trades[order_id_str] = trade_dict
            elif order_id_str and order_id_str in program_tp_to_main:
                # This is a take-profit order from Program Trader
                trade_dict["order_type"] = "tp"
                tp_trades[order_id_str] = trade_dict
            # Check Binance triggered TP/SL orders (triggered order ID != algo order ID)
            elif order_id_str and order_id_str in binance_triggered_sl_to_main:
                # This is a Binance triggered stop-loss order
                trade_dict["order_type"] = "sl"
                sl_trades[order_id_str] = trade_dict
            elif order_id_str and order_id_str in binance_triggered_tp_to_main:
                # This is a Binance triggered take-profit order
                trade_dict["order_type"] = "tp"
                tp_trades[order_id_str] = trade_dict
            else:
                # Not linked to any decision (manual trade or unknown)
                trade_dict["signal_trigger_id"] = None
                trade_dict["prompt_template_id"] = None
                trade_dict["prompt_template_name"] = None
                trade_dict["decision_source_type"] = None
                trade_dict["related_orders"] = []
                other_trades.append(trade_dict)

        # Second pass: nest SL/TP trades under their main orders
        # Check AIDecisionLog, ProgramExecutionLog, and Binance triggered order mappings
        for sl_order_id, sl_trade in sl_trades.items():
            main_order_id = (
                sl_to_main.get(sl_order_id) or
                program_sl_to_main.get(sl_order_id) or
                binance_triggered_sl_to_main.get(sl_order_id)
            )
            if main_order_id and main_order_id in main_trades:
                main_trades[main_order_id]["related_orders"].append({
                    "type": "sl",
                    "price": sl_trade["price"],
                    "quantity": sl_trade["quantity"],
                    "notional": sl_trade["notional"],
                    "commission": sl_trade["commission"],
                    "trade_time": sl_trade["trade_time"],
                })

        for tp_order_id, tp_trade in tp_trades.items():
            main_order_id = (
                tp_to_main.get(tp_order_id) or
                program_tp_to_main.get(tp_order_id) or
                binance_triggered_tp_to_main.get(tp_order_id)
            )
            if main_order_id and main_order_id in main_trades:
                main_trades[main_order_id]["related_orders"].append({
                    "type": "tp",
                    "price": tp_trade["price"],
                    "quantity": tp_trade["quantity"],
                    "notional": tp_trade["notional"],
                    "commission": tp_trade["commission"],
                    "trade_time": tp_trade["trade_time"],
                })

        # Combine main trades and other trades, sort by trade_time desc
        all_trades = list(main_trades.values()) + other_trades
        all_trades.sort(key=lambda t: t.get("trade_time") or "", reverse=True)

        # Filter by exchange if specified
        if exchange:
            if exchange == "hyperliquid":
                # Include trades with exchange=hyperliquid or NULL (legacy data)
                all_trades = [t for t in all_trades if t.get("exchange") in ("hyperliquid", None)]
            else:
                all_trades = [t for t in all_trades if t.get("exchange") == exchange]

        _log_request()
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "accounts": list(accounts_meta.values()),
            "trades": all_trades,
        }

    # Paper mode (or no filter) falls back to paper trades table
    query = (
        db.query(Trade, Account)
        .join(Account, Trade.account_id == Account.id)
        .order_by(desc(Trade.trade_time))
    )

    if account_id:
        query = query.filter(Trade.account_id == account_id)

    if trading_mode == "paper":
        query = query.filter(Trade.hyperliquid_environment == None)
    elif trading_mode in ("testnet", "mainnet"):
        query = query.filter(Trade.hyperliquid_environment == trading_mode)

    trade_rows = query.limit(limit).all()

    if not trade_rows:
        _log_request()
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "accounts": [],
            "trades": [],
        }

    trades: List[dict] = []
    accounts_meta = {}

    for trade, account in trade_rows:
        quantity = float(trade.quantity)
        price = float(trade.price)
        notional = price * quantity

        order_no = None
        if trade.order_id:
            order = db.query(Order).filter(Order.id == trade.order_id).first()
            if order:
                order_no = order.order_no

        trades.append(
            {
                "trade_id": trade.id,
                "order_id": trade.order_id,
                "order_no": order_no,
                "account_id": account.id,
                "account_name": account.name,
                "model": account.model,
                "side": trade.side,
                "direction": "LONG" if (trade.side or "").upper() == "BUY" else "SHORT",
                "symbol": trade.symbol,
                "market": trade.market,
                "price": price,
                "quantity": quantity,
                "notional": notional,
                "commission": float(trade.commission),
                "trade_time": trade.trade_time.isoformat() if trade.trade_time else None,
                "wallet_address": None,
            }
        )

        accounts_meta[account.id] = {
            "account_id": account.id,
            "name": account.name,
            "model": account.model,
        }

    _log_request()
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "accounts": list(accounts_meta.values()),
        "trades": trades,
    }


@router.get("/model-chat")
def get_model_chat(
    limit: int = Query(60, ge=1, le=200),
    account_id: Optional[int] = None,
    trading_mode: Optional[str] = Query(None, regex="^(paper|testnet|mainnet)$"),
    wallet_address: Optional[str] = Query(None),
    before_time: Optional[str] = Query(None, description="ISO format timestamp for cursor-based pagination"),
    after_time: Optional[str] = Query(None, description="ISO format UTC timestamp, return records after this time"),
    operation: Optional[str] = Query(None, regex="^(buy|sell|hold|close)$", description="Filter by operation type"),
    include_snapshots: bool = Query(False, description="Include prompt/reasoning/decision snapshots (heavy data)"),
    symbol: Optional[str] = Query(None),
    ids: Optional[str] = Query(None, description="Comma-separated list of decision IDs to fetch"),
    exchange: Optional[str] = Query(None, regex="^(hyperliquid|binance)$"),
    db: Session = Depends(get_db),
):
    """Return recent AI decision logs as chat-style summaries, filtered by trading mode."""
    query = (
        db.query(AIDecisionLog, Account)
        .join(Account, AIDecisionLog.account_id == Account.id)
        .order_by(desc(AIDecisionLog.decision_time))
    )

    # If specific IDs are requested, filter by them
    if ids:
        try:
            id_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
            if id_list:
                query = query.filter(AIDecisionLog.id.in_(id_list))
        except ValueError:
            pass

    if account_id:
        query = query.filter(AIDecisionLog.account_id == account_id)

    if wallet_address:
        query = query.filter(AIDecisionLog.wallet_address == wallet_address)

    # Cursor-based pagination: only get records before the specified time
    if before_time:
        try:
            before_dt = datetime.fromisoformat(before_time.replace('Z', '+00:00'))
            query = query.filter(AIDecisionLog.decision_time < before_dt)
        except (ValueError, AttributeError) as e:
            logger.warning(f"Invalid before_time parameter: {before_time}, error: {e}")

    # Time range filter: only get records after the specified time
    if after_time:
        try:
            after_dt = datetime.fromisoformat(after_time.replace('Z', '+00:00'))
            query = query.filter(AIDecisionLog.decision_time >= after_dt)
        except (ValueError, AttributeError) as e:
            logger.warning(f"Invalid after_time parameter: {after_time}, error: {e}")

    # Filter by operation type (buy/sell/hold/close)
    if operation:
        query = query.filter(AIDecisionLog.operation == operation)

    if symbol:
        query = query.filter(AIDecisionLog.symbol == symbol)

    # Filter by trading mode based on hyperliquid_environment field
    if trading_mode:
        if trading_mode == "paper":
            query = query.filter(AIDecisionLog.hyperliquid_environment == None)
        else:
            # For testnet/mainnet, strictly match environment and exclude NULL
            query = query.filter(
                AIDecisionLog.hyperliquid_environment == trading_mode,
                AIDecisionLog.hyperliquid_environment.isnot(None)
            )

    # Filter by exchange
    if exchange:
        if exchange == "hyperliquid":
            # Include hyperliquid or NULL (legacy data)
            query = query.filter(
                (AIDecisionLog.exchange == "hyperliquid") | (AIDecisionLog.exchange == None)
            )
        else:
            query = query.filter(AIDecisionLog.exchange == exchange)

    decision_rows = query.limit(limit).all()

    if not decision_rows:
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "entries": [],
        }

    entries: List[dict] = []

    account_ids = {account.id for _, account in decision_rows}
    strategy_map = {
        cfg.account_id: cfg
        for cfg in db.query(AccountStrategyConfig)
        .filter(AccountStrategyConfig.account_id.in_(account_ids))
        .all()
    }

    # Batch fetch prompt template names
    prompt_template_ids = {log.prompt_template_id for log, _ in decision_rows if log.prompt_template_id}
    prompt_template_map = {}
    if prompt_template_ids:
        templates = db.query(PromptTemplate).filter(PromptTemplate.id.in_(prompt_template_ids), PromptTemplate.is_deleted == "false").all()
        prompt_template_map = {t.id: t.name for t in templates}

    for log, account in decision_rows:
        strategy = strategy_map.get(account.id)
        last_trigger_iso = None
        trigger_latency = None
        trigger_mode = None
        strategy_enabled = None

        if strategy:
            trigger_mode = "unified"
            strategy_enabled = strategy.enabled == "true"
            if strategy.last_trigger_at:
                last_dt = strategy.last_trigger_at
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                last_trigger_iso = last_dt.isoformat()

                log_dt = log.decision_time
                if log_dt:
                    if log_dt.tzinfo is None:
                        log_dt = log_dt.replace(tzinfo=timezone.utc)
                    try:
                        trigger_latency = abs((log_dt - last_dt).total_seconds())
                    except Exception:
                        trigger_latency = None

        entry = {
            "id": log.id,
            "account_id": account.id,
            "account_name": account.name,
            "model": account.model,
            "operation": log.operation,
            "symbol": log.symbol,
            "reason": log.reason,
            "executed": log.executed == "true",
            "prev_portion": float(log.prev_portion or 0),
            "target_portion": float(log.target_portion or 0),
            "total_balance": float(log.total_balance or 0),
            "order_id": log.order_id,
            "decision_time": log.decision_time.isoformat()
            if log.decision_time
            else None,
            "trigger_mode": trigger_mode,
            "strategy_enabled": strategy_enabled,
            "last_trigger_at": last_trigger_iso,
            "trigger_latency_seconds": trigger_latency,
            "wallet_address": log.wallet_address,
            "signal_trigger_id": log.signal_trigger_id,
            "prompt_template_id": log.prompt_template_id,
            "prompt_template_name": prompt_template_map.get(log.prompt_template_id) if log.prompt_template_id else None,
            "realized_pnl": float(log.realized_pnl) if log.realized_pnl else None,
            "has_snapshot": bool(log.prompt_snapshot),
            # Exchange identifier (NULL treated as "hyperliquid" for backward compatibility)
            "exchange": log.exchange or "hyperliquid",
        }

        # Only include heavy snapshot fields when explicitly requested
        if include_snapshots:
            entry["prompt_snapshot"] = log.prompt_snapshot
            entry["reasoning_snapshot"] = log.reasoning_snapshot
            entry["decision_snapshot"] = log.decision_snapshot

        entries.append(entry)

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "entries": entries,
    }


@router.get("/model-chat/{decision_id}/snapshots")
def get_model_chat_snapshots(
    decision_id: int,
    db: Session = Depends(get_db),
):
    """Return snapshot fields for a single AI decision log entry."""
    log = db.query(AIDecisionLog).filter(AIDecisionLog.id == decision_id).first()

    if not log:
        return {
            "error": "Decision not found",
            "id": decision_id,
        }

    return {
        "id": log.id,
        "prompt_snapshot": log.prompt_snapshot,
        "reasoning_snapshot": log.reasoning_snapshot,
        "decision_snapshot": log.decision_snapshot,
    }


@router.get("/positions")
def get_positions_snapshot(
    account_id: Optional[int] = None,
    trading_mode: Optional[str] = Query(None, regex="^(paper|testnet|mainnet)$"),
    db: Session = Depends(get_db),
):
    """Return consolidated positions and cash for active AI accounts, filtered by trading mode."""
    start_threads = get_current_thread_count()
    start_time = time.monotonic()

    def _log_request() -> None:
        log_hot_path_delta(
            logger,
            "arena:positions",
            "/api/arena/positions",
            start_threads,
            start_time,
            account_id=account_id,
            trading_mode=trading_mode,
        )

    # For Hyperliquid modes (testnet/mainnet), fetch real-time data from exchanges
    if trading_mode and trading_mode in ["testnet", "mainnet"]:
        result = _get_hyperliquid_positions(db, account_id, trading_mode)
        # Also include Binance accounts
        binance_accounts = _get_binance_positions(db, account_id, trading_mode)
        result["accounts"] = result.get("accounts", []) + binance_accounts
        _log_request()
        return result

    # For paper mode (or no mode specified), query local database
    accounts_query = db.query(Account).filter(
        Account.account_type == "AI",
        Account.is_active == "true",
        Account.show_on_dashboard == True,
        Account.is_deleted != True,
    )

    if account_id:
        accounts_query = accounts_query.filter(Account.id == account_id)

    accounts = accounts_query.all()

    snapshots: List[dict] = []

    for account in accounts:
        positions = (
            db.query(Position)
            .filter(Position.account_id == account.id, Position.quantity > 0)
            .order_by(Position.symbol.asc())
            .all()
        )

        position_items: List[dict] = []
        total_unrealized = 0.0

        for pos in positions:
            quantity = float(pos.quantity)
            avg_cost = float(pos.avg_cost)
            base_notional = quantity * avg_cost

            last_price = _get_latest_price(pos.symbol, pos.market)
            if last_price is None:
                last_price = avg_cost

            current_value = last_price * quantity
            unrealized = current_value - base_notional
            total_unrealized += unrealized

            position_items.append(
                {
                    "id": pos.id,
                    "symbol": pos.symbol,
                    "name": pos.name,
                    "market": pos.market,
                    "side": "LONG" if quantity >= 0 else "SHORT",
                    "quantity": quantity,
                    "avg_cost": avg_cost,
                    "current_price": last_price,
                    "notional": base_notional,
                    "current_value": current_value,
                    "unrealized_pnl": unrealized,
                }
            )

        total_assets = (
            calc_positions_value(db, account.id) + float(account.current_cash or 0)
        )
        total_return = None
        if account.initial_capital:
            try:
                total_return = (
                    (total_assets - float(account.initial_capital))
                    / float(account.initial_capital)
                )
            except ZeroDivisionError:
                total_return = None

        snapshots.append(
            {
                "account_id": account.id,
                "account_name": account.name,
                "model": account.model,
                "total_unrealized_pnl": total_unrealized,
                "available_cash": float(account.current_cash or 0),
                "positions": position_items,
                "total_assets": total_assets,
                "initial_capital": float(account.initial_capital or 0),
                "total_return": total_return,
            }
        )

    _log_request()
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "trading_mode": trading_mode or "paper",
        "accounts": snapshots,
    }



@router.get("/analytics")
def get_aggregated_analytics(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    '''Return leaderboard-style analytics for AI accounts.'''
    accounts_query = db.query(Account).filter(
        Account.account_type == "AI",
        Account.is_deleted != True,
    )

    if account_id:
        accounts_query = accounts_query.filter(Account.id == account_id)

    accounts = accounts_query.all()

    if not accounts:
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "accounts": [],
            "summary": {
                "total_assets": 0.0,
                "total_pnl": 0.0,
                "total_return_pct": None,
                "total_fees": 0.0,
                "total_volume": 0.0,
                "average_sharpe_ratio": None,
            },
        }

    analytics = []
    total_assets_all = 0.0
    total_initial = 0.0
    total_fees_all = 0.0
    total_volume_all = 0.0
    sharpe_values = []

    for account in accounts:
        stats = _aggregate_account_stats(db, account)
        analytics.append(stats)
        total_assets_all += stats.get("total_assets") or 0.0
        total_initial += stats.get("initial_capital") or 0.0
        total_fees_all += stats.get("total_fees") or 0.0
        total_volume_all += stats.get("total_volume") or 0.0
        if stats.get("sharpe_ratio") is not None:
            sharpe_values.append(stats["sharpe_ratio"])

    analytics.sort(
        key=lambda item: item.get("total_return_pct") if item.get("total_return_pct") is not None else float("-inf"),
        reverse=True,
    )

    average_sharpe = mean(sharpe_values) if sharpe_values else None
    total_pnl_all = total_assets_all - total_initial
    total_return_pct = (
        total_pnl_all / total_initial if total_initial else None
    )

    summary = {
        "total_assets": total_assets_all,
        "total_pnl": total_pnl_all,
        "total_return_pct": total_return_pct,
        "total_fees": total_fees_all,
        "total_volume": total_volume_all,
        "average_sharpe_ratio": average_sharpe,
    }

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "accounts": analytics,
        "summary": summary,
    }


@router.get("/check-pnl-status")
def check_pnl_sync_status(
    trading_mode: Optional[str] = Query(None, regex="^(paper|testnet|mainnet)$"),
    db: Session = Depends(get_db),
):
    """
    Check if there are trades that need PnL synchronization.
    Returns the count of unsynchronized trades for both AI Decision and Program.
    Only counts trades that have order IDs (can be synced).
    """
    from sqlalchemy import or_
    from database.models import ProgramExecutionLog

    # Check AI Decision logs
    ai_query = db.query(AIDecisionLog).filter(
        AIDecisionLog.operation.in_(["buy", "sell", "close"]),
        AIDecisionLog.executed == "true",
        AIDecisionLog.pnl_updated_at == None,
        or_(
            AIDecisionLog.hyperliquid_order_id != None,
            AIDecisionLog.tp_order_id != None,
            AIDecisionLog.sl_order_id != None,
        ),
    )

    if trading_mode:
        # "paper" now means the new paper-trading environment (environment == "paper"),
        # not the legacy deprecated internal paper mode (environment IS NULL).
        ai_query = ai_query.filter(AIDecisionLog.hyperliquid_environment == trading_mode)
    else:
        ai_query = ai_query.filter(AIDecisionLog.hyperliquid_environment.isnot(None))

    ai_unsync_count = ai_query.count()

    # Check Program execution logs
    prog_query = db.query(ProgramExecutionLog).filter(
        ProgramExecutionLog.success == True,
        ProgramExecutionLog.decision_action.in_(["buy", "sell", "close"]),
        ProgramExecutionLog.pnl_updated_at == None,
        or_(
            ProgramExecutionLog.hyperliquid_order_id != None,
            ProgramExecutionLog.tp_order_id != None,
            ProgramExecutionLog.sl_order_id != None,
        ),
    )

    if trading_mode:
        # Same repointing as the ai_query filter above: "paper" == new paper environment.
        prog_query = prog_query.filter(ProgramExecutionLog.environment == trading_mode)
    else:
        prog_query = prog_query.filter(ProgramExecutionLog.environment.isnot(None))

    prog_unsync_count = prog_query.count()

    total_unsync = ai_unsync_count + prog_unsync_count

    return {
        "needs_sync": total_unsync > 0,
        "unsync_count": total_unsync,
        "ai_unsync_count": ai_unsync_count,
        "program_unsync_count": prog_unsync_count,
    }


def _backfill_paper_pnl(db: Session, snapshot_db: Session) -> dict:
    """
    Paper trading PnL backfill safety net for /update-pnl.

    paper_trading/monitor.py's PaperMonitor._backfill_decision_pnl backfills
    AIDecisionLog/ProgramExecutionLog.realized_pnl + pnl_updated_at in real time
    the moment a TP/SL PaperOrder fills. This function is the safety net for
    anything the monitor missed (e.g. it was down when the fill happened): for
    executed/successful paper-environment decision/program rows that are still
    unsynced (pnl_updated_at IS NULL), check whether their TP/SL PaperOrder has
    since filled.

    DEVIATION from the Task 13 brief: the brief's literal snippet only ever
    stamps `pnl_updated_at` and never touches `realized_pnl` -- so a record the
    monitor missed would be marked "synced" while realized_pnl stays NULL
    forever (it silently drops out of the "needs sync" count with no PnL ever
    recorded). That is incoherent, so this implementation additionally
    recovers the PnL when possible: it reads the fill's price/quantity from the
    snapshot DB's HyperliquidTrade row (environment="paper",
    order_id=<tp/sl order_no>) and combines it with the PaperOrder's
    entry_price/side (recorded at TP/SL registration time -- see
    PaperEngine._register_tpsl), mirroring the exact math PaperEngine._close_qty
    uses:
        pnl = (fill_price - entry_price) * qty   if close side == "sell" (was long)
        pnl = (entry_price - fill_price) * qty   if close side == "buy"  (was short)
    Only when that recovery isn't possible (no matching fill row, or the
    PaperOrder has no entry_price -- e.g. legacy rows) does it fall back to the
    brief's literal behavior of stamping pnl_updated_at alone, leaving
    realized_pnl untouched (NULL).

    Caller (update_pnl_data) owns both sessions' lifecycle: db is the FastAPI
    request-scoped session, snapshot_db is opened/closed around the whole
    endpoint. This helper only reads/writes/commits `db`; it never opens or
    closes either session, so it is safe to call directly with test fixture
    sessions too.
    """
    from database.models import AIDecisionLog, ProgramExecutionLog, PaperOrder
    from decimal import Decimal

    paper_updated = 0

    paper_decisions = db.query(AIDecisionLog).filter(
        AIDecisionLog.hyperliquid_environment == "paper",
        AIDecisionLog.executed == "true",
        AIDecisionLog.operation.in_(["buy", "sell", "close"]),
        AIDecisionLog.pnl_updated_at == None,
    ).all()
    paper_programs = db.query(ProgramExecutionLog).filter(
        ProgramExecutionLog.environment == "paper",
        ProgramExecutionLog.success == True,
        ProgramExecutionLog.decision_action.in_(["buy", "sell", "close"]),
        ProgramExecutionLog.pnl_updated_at == None,
    ).all()

    def _filled_order(order_no):
        if not order_no:
            return None
        return db.query(PaperOrder).filter(
            PaperOrder.order_no == order_no,
            PaperOrder.status == "filled",
        ).first()

    for rec in list(paper_decisions) + list(paper_programs):
        # Entry orders with TP/SL still pending stay unsynced (position not closed yet).
        po = _filled_order(rec.tp_order_id) or _filled_order(rec.sl_order_id)
        if po is None or po.filled_at is None:
            continue
        if rec.realized_pnl is not None:
            # Already has PnL via some other path; nothing to backfill here.
            continue

        recovered_pnl = None
        fill = snapshot_db.query(HyperliquidTrade).filter(
            HyperliquidTrade.environment == "paper",
            HyperliquidTrade.order_id == po.order_no,
        ).order_by(HyperliquidTrade.id.desc()).first()
        if fill is not None and po.entry_price is not None:
            entry = Decimal(str(po.entry_price))
            qty = Decimal(str(fill.quantity))
            price = Decimal(str(fill.price))
            was_long = po.side == "sell"  # close side "sell" => original position was long
            recovered_pnl = (price - entry) * qty if was_long else (entry - price) * qty

        # Monitor normally backfills in real time; this is the safety net for missed fills.
        rec.pnl_updated_at = po.filled_at
        if recovered_pnl is not None:
            rec.realized_pnl = recovered_pnl
        paper_updated += 1

    if paper_updated:
        db.commit()
    return {"backfilled": paper_updated}


@router.post("/update-pnl")
def update_pnl_data(db: Session = Depends(get_db)):
    """
    Update realized PnL and fee data for all trades by fetching from exchange APIs.

    This endpoint:
    1. Fetches user_fills from all configured wallets (Hyperliquid + Binance, testnet + mainnet)
    2. Updates HyperliquidTrade.fee with actual fee data
    3. Creates missing HyperliquidTrade records for resting orders that later filled
    4. Updates AIDecisionLog.realized_pnl for closed positions
    5. Backfills paper trading PnL missed by the real-time paper monitor (safety net)

    Returns summary of updated records.
    """
    from database.models import (
        HyperliquidWallet,
        BinanceWallet,
        AccountPromptBinding,
        AIDecisionLog,
        ProgramExecutionLog,
    )
    from services.hyperliquid_environment import get_hyperliquid_client
    from decimal import Decimal
    from collections import defaultdict
    from sqlalchemy import or_

    result = {
        "success": True,
        "hyperliquid": {},
        "binance": {},
        "errors": [],
    }

    snapshot_db = SnapshotSessionLocal()

    try:
        # ---- Paper trading backfill (no exchange API; fills already in snapshot DB) ----
        try:
            result["paper"] = _backfill_paper_pnl(db, snapshot_db)
        except Exception as e:
            result["errors"].append(f"paper backfill: {e}")

        # ========== Process Hyperliquid wallets ==========
        hl_wallets = db.query(HyperliquidWallet).all()
        if hl_wallets:
            hl_wallet_configs = {}
            fetched_historical_addresses = set()
            for w in hl_wallets:
                key = (w.account_id, w.environment)
                if key not in hl_wallet_configs:
                    hl_wallet_configs[key] = w

            all_hl_fills_by_env = defaultdict(list)
            for (account_id, environment), wallet in hl_wallet_configs.items():
                try:
                    client = get_hyperliquid_client(db, account_id, override_environment=environment)
                    fills = client._get_user_fills(db)
                    all_hl_fills_by_env[environment].extend(fills)
                    logger.info(f"[Hyperliquid] Fetched {len(fills)} fills for account {account_id} on {environment}")

                    current_query_addresses = {client.query_address.lower()}
                    if getattr(client, "wallet_address", None):
                        current_query_addresses.add(client.wallet_address.lower())

                    historical_addresses = set()

                    ai_rows = db.query(AIDecisionLog.wallet_address).filter(
                        AIDecisionLog.account_id == account_id,
                        AIDecisionLog.hyperliquid_environment == environment,
                        AIDecisionLog.executed == "true",
                        AIDecisionLog.pnl_updated_at == None,
                        AIDecisionLog.wallet_address.isnot(None),
                        or_(
                            AIDecisionLog.hyperliquid_order_id != None,
                            AIDecisionLog.tp_order_id != None,
                            AIDecisionLog.sl_order_id != None,
                        ),
                    ).distinct().all()
                    historical_addresses.update(
                        addr.lower()
                        for (addr,) in ai_rows
                        if addr and addr.lower() not in current_query_addresses
                    )

                    prog_rows = db.query(ProgramExecutionLog.wallet_address).filter(
                        ProgramExecutionLog.account_id == account_id,
                        ProgramExecutionLog.environment == environment,
                        ProgramExecutionLog.success == True,
                        ProgramExecutionLog.pnl_updated_at == None,
                        ProgramExecutionLog.wallet_address.isnot(None),
                        or_(
                            ProgramExecutionLog.hyperliquid_order_id != None,
                            ProgramExecutionLog.tp_order_id != None,
                            ProgramExecutionLog.sl_order_id != None,
                        ),
                    ).distinct().all()
                    historical_addresses.update(
                        addr.lower()
                        for (addr,) in prog_rows
                        if addr and addr.lower() not in current_query_addresses
                    )

                    for historical_address in sorted(historical_addresses):
                        historical_key = (environment, historical_address)
                        if historical_key in fetched_historical_addresses:
                            continue
                        try:
                            historical_fills = client.sdk_info.user_fills(historical_address)
                            all_hl_fills_by_env[environment].extend(historical_fills)
                            fetched_historical_addresses.add(historical_key)
                            logger.info(
                                f"[Hyperliquid] Fetched {len(historical_fills)} historical fills "
                                f"for address {historical_address} on {environment}"
                            )
                        except Exception as historical_err:
                            logger.warning(
                                f"[Hyperliquid] Failed to fetch historical fills for address "
                                f"{historical_address} on {environment}: {historical_err}"
                            )
                except Exception as e:
                    error_msg = f"[Hyperliquid] Failed to fetch fills for account {account_id} on {environment}: {str(e)}"
                    logger.warning(error_msg)
                    result["errors"].append(error_msg)

            for environment, fills in all_hl_fills_by_env.items():
                env_result = _process_fills_for_environment(
                    db, snapshot_db, environment, fills, hl_wallet_configs, exchange="hyperliquid"
                )
                result["hyperliquid"][environment] = env_result

        # ========== Process Binance wallets ==========
        bn_wallets = db.query(BinanceWallet).filter(BinanceWallet.is_active == "true").all()
        if bn_wallets:
            from services.binance_trading_client import BinanceTradingClient
            from utils.encryption import decrypt_private_key

            bn_wallet_configs = {}
            for w in bn_wallets:
                key = (w.account_id, w.environment)
                if key not in bn_wallet_configs:
                    bn_wallet_configs[key] = w

            all_bn_fills_by_env = defaultdict(list)
            for (account_id, environment), wallet in bn_wallet_configs.items():
                try:
                    api_key = decrypt_private_key(wallet.api_key_encrypted)
                    secret_key = decrypt_private_key(wallet.secret_key_encrypted)
                    client = BinanceTradingClient(api_key, secret_key, environment)
                    fills = client.get_user_fills()
                    all_bn_fills_by_env[environment].extend(fills)
                    logger.info(f"[Binance] Fetched {len(fills)} fills for account {account_id} on {environment}")
                except Exception as e:
                    error_msg = f"[Binance] Failed to fetch fills for account {account_id} on {environment}: {str(e)}"
                    logger.warning(error_msg)
                    result["errors"].append(error_msg)

            for environment, fills in all_bn_fills_by_env.items():
                env_result = _process_fills_for_environment(
                    db, snapshot_db, environment, fills, bn_wallet_configs, exchange="binance"
                )
                result["binance"][environment] = env_result

        # Commit all changes
        snapshot_db.commit()
        db.commit()

    except Exception as e:
        logger.error(f"Error updating PnL data: {e}", exc_info=True)
        result["success"] = False
        result["errors"].append(str(e))
        snapshot_db.rollback()
        db.rollback()
    finally:
        snapshot_db.close()

    return result


def _process_fills_for_environment(
    db: Session,
    snapshot_db: Session,
    environment: str,
    fills: List[dict],
    wallet_configs: dict,
    exchange: str = "hyperliquid",
) -> dict:
    """
    Process fills for a specific environment and update database records.

    This function:
    1. Updates existing HyperliquidTrade records with fee data
    2. Creates missing HyperliquidTrade records for resting orders that later filled
    3. Updates AIDecisionLog/ProgramExecutionLog.realized_pnl for closed positions

    Args:
        exchange: "hyperliquid" or "binance" - determines which wallet to use for API calls

    Returns summary of updates.
    """
    from decimal import Decimal
    from collections import defaultdict

    result = {
        "fills_count": len(fills),
        "unique_orders": 0,
        "trades_updated": 0,
        "trades_created": 0,
        "decisions_updated": 0,
        "program_logs_updated": 0,
        "skipped": 0,
    }

    if not fills:
        return result

    # Aggregate fills by order ID
    # One order can have multiple fills (partial executions)
    order_aggregates = defaultdict(lambda: {
        "total_fee": Decimal("0"),
        "total_pnl": Decimal("0"),
        "fills": [],
    })

    # For Binance: build mapping from main_order_id to TP/SL order_ids
    # This allows us to match TP/SL fills to the decision that created them
    binance_tpsl_to_main = {}  # TP/SL order_id -> main_order_id

    for fill in fills:
        oid = str(fill.get("oid", ""))
        if not oid:
            continue

        fee = Decimal(str(fill.get("fee", "0")))
        closed_pnl = Decimal(str(fill.get("closedPnl", "0")))

        order_aggregates[oid]["total_fee"] += fee
        order_aggregates[oid]["total_pnl"] += closed_pnl
        order_aggregates[oid]["fills"].append(fill)

        # For Binance TP/SL orders, record the mapping to main order
        if exchange == "binance" and fill.get("main_order_id"):
            binance_tpsl_to_main[oid] = fill.get("main_order_id")

    result["unique_orders"] = len(order_aggregates)

    # Update HyperliquidTrade records
    trades = snapshot_db.query(HyperliquidTrade).filter(
        HyperliquidTrade.environment == environment
    ).all()

    for trade in trades:
        order_id = str(trade.order_id)
        if order_id in order_aggregates:
            agg = order_aggregates[order_id]
            # Update fee
            if trade.fee != agg["total_fee"]:
                trade.fee = agg["total_fee"]
                result["trades_updated"] += 1
        else:
            result["skipped"] += 1

    # Collect existing trade order_ids for deduplication
    existing_trade_order_ids = {str(t.order_id) for t in trades if t.order_id}
    # For Binance: also build order_id -> trade mapping for updates
    existing_trades_by_order_id = {str(t.order_id): t for t in trades if t.order_id}

    # Helper function to get order trigger time from Hyperliquid API (only for Hyperliquid)
    def get_order_trigger_time(account_id: int, order_id: str) -> Optional[datetime]:
        """Get actual trigger time for TP/SL order from Hyperliquid API."""
        if exchange != "hyperliquid":
            return None  # Binance doesn't have this API
        key = (account_id, environment)
        if key not in wallet_configs:
            return None
        try:
            client = get_hyperliquid_client(db, account_id, override_environment=environment)
            return client.get_order_trigger_time(db, int(order_id))
        except Exception as e:
            logger.warning(f"Failed to get trigger time for order {order_id}: {e}")
            return None

    # Update AIDecisionLog records
    # Match by hyperliquid_order_id, tp_order_id, sl_order_id and accumulate PnL
    decisions = db.query(AIDecisionLog).filter(
        AIDecisionLog.operation.in_(["buy", "sell", "close"]),
        AIDecisionLog.executed == "true",
        AIDecisionLog.hyperliquid_environment == environment,
    ).all()

    # Build order_id -> decision mapping for creating missing trades
    order_to_decision = {}
    for decision in decisions:
        for oid in [decision.hyperliquid_order_id, decision.tp_order_id, decision.sl_order_id]:
            if oid:
                order_to_decision[str(oid)] = decision

    # For Binance: also map triggered order IDs to their decisions
    # Binance TP/SL triggered orders have different IDs than the algo order IDs stored in decision
    if exchange == "binance":
        for triggered_oid, main_oid in binance_tpsl_to_main.items():
            # Find the decision that has this main_order_id
            decision = order_to_decision.get(main_oid)
            if decision and triggered_oid not in order_to_decision:
                order_to_decision[triggered_oid] = decision

    # Also build order_id -> program_log mapping for Program Trader orders
    from database.models import ProgramExecutionLog
    program_logs = db.query(ProgramExecutionLog).filter(
        ProgramExecutionLog.success == True,
        ProgramExecutionLog.decision_action.in_(["buy", "sell", "close"]),
    ).all()

    order_to_program_log = {}
    for pl in program_logs:
        for oid in [pl.hyperliquid_order_id, pl.tp_order_id, pl.sl_order_id]:
            if oid:
                order_to_program_log[str(oid)] = pl

    # For Binance: also map triggered order IDs to their program logs
    if exchange == "binance":
        for triggered_oid, main_oid in binance_tpsl_to_main.items():
            pl = order_to_program_log.get(main_oid)
            if pl and triggered_oid not in order_to_program_log:
                order_to_program_log[triggered_oid] = pl

    # Create missing HyperliquidTrade records for resting orders that later filled
    # For Binance: also update existing records with official fill data
    # Check both AIDecisionLog and ProgramExecutionLog
    for oid, agg in order_aggregates.items():
        existing_trade = existing_trades_by_order_id.get(oid) if exchange == "binance" else None

        # For Hyperliquid: skip if already exists
        # For Binance: allow update of existing records
        if oid in existing_trade_order_ids and exchange != "binance":
            continue  # Already exists (Hyperliquid only)

        # Try to find source: AIDecisionLog or ProgramExecutionLog
        decision = order_to_decision.get(oid)
        program_log = order_to_program_log.get(oid)

        if not decision and not program_log:
            continue  # Not from any known source
        fills_list = agg["fills"]
        if not fills_list:
            continue

        # Aggregate fill data for this order
        total_qty = Decimal("0")
        total_value = Decimal("0")
        latest_time = None

        for fill in fills_list:
            qty = Decimal(str(fill.get("sz", "0")))
            px = Decimal(str(fill.get("px", "0")))
            total_qty += qty
            total_value += qty * px

            fill_time = fill.get("time")
            if fill_time and (latest_time is None or fill_time > latest_time):
                latest_time = fill_time

        if total_qty == 0:
            continue

        avg_price = total_value / total_qty

        # Determine side from decision/program_log operation, NOT from exchange fill side
        # Exchange returns B/S (buy/sell), but we want to preserve the original operation (buy/sell/close)
        if decision:
            side = decision.operation.lower() if decision.operation else "sell"
        elif program_log:
            side = program_log.decision_action.lower() if program_log.decision_action else "sell"
        else:
            # Fallback to exchange side (should not reach here due to earlier check)
            fill_side = fills_list[0].get("side", "B")
            side = "buy" if fill_side == "B" else "sell"

        # Parse trade time
        trade_time = None
        if latest_time:
            try:
                trade_time = datetime.fromtimestamp(latest_time / 1000, tz=timezone.utc)
            except Exception:
                trade_time = datetime.utcnow()
        else:
            trade_time = datetime.utcnow()

        # Get account_id, wallet_address, symbol from either source
        if decision:
            account_id = decision.account_id
            wallet_address = decision.wallet_address
            symbol = decision.symbol or fills_list[0].get("coin", "")
            source_info = f"decision {decision.id}"
        else:
            account_id = program_log.account_id
            wallet_address = program_log.wallet_address
            symbol = program_log.decision_symbol or fills_list[0].get("coin", "")
            source_info = f"program_log {program_log.id}"

        # For Binance: update existing record with official fill data
        if existing_trade and exchange == "binance":
            existing_trade.quantity = total_qty
            existing_trade.price = avg_price
            existing_trade.trade_value = total_value
            existing_trade.fee = agg["total_fee"]
            existing_trade.order_status = "filled"
            if trade_time:
                existing_trade.trade_time = trade_time
            result["trades_updated"] += 1
            logger.info(f"Updated HyperliquidTrade for Binance order {oid} with official fill data")
            continue

        # Create new HyperliquidTrade record
        new_trade = HyperliquidTrade(
            account_id=account_id,
            environment=environment,
            wallet_address=wallet_address,
            symbol=symbol,
            side=side,
            quantity=total_qty,
            price=avg_price,
            leverage=1,
            order_id=oid,
            order_status="filled",
            trade_value=total_value,
            fee=agg["total_fee"],
            trade_time=trade_time,
        )
        snapshot_db.add(new_trade)
        existing_trade_order_ids.add(oid)  # Prevent duplicates in same run
        result["trades_created"] += 1
        logger.info(f"Created missing HyperliquidTrade for order {oid}, {source_info}")

    for decision in decisions:
        updated = False
        total_pnl = Decimal("0")
        matched_order_ids = set()

        # Try direct match by hyperliquid_order_id, tp_order_id, sl_order_id
        order_ids_to_check = [
            decision.hyperliquid_order_id,
            decision.tp_order_id,
            decision.sl_order_id,
        ]

        for oid in order_ids_to_check:
            if oid:
                order_id_str = str(oid)
                if order_id_str in order_aggregates and order_id_str not in matched_order_ids:
                    agg = order_aggregates[order_id_str]
                    total_pnl += agg["total_pnl"]
                    matched_order_ids.add(order_id_str)

        # For Binance: also check TP/SL orders that triggered and created new order IDs
        # The triggered order's clientOrderId contains the main order ID (e.g., "SL_12345")
        if exchange == "binance" and decision.hyperliquid_order_id:
            main_oid = str(decision.hyperliquid_order_id)
            for tpsl_oid, linked_main_oid in binance_tpsl_to_main.items():
                if linked_main_oid == main_oid and tpsl_oid not in matched_order_ids:
                    if tpsl_oid in order_aggregates:
                        agg = order_aggregates[tpsl_oid]
                        total_pnl += agg["total_pnl"]
                        matched_order_ids.add(tpsl_oid)
                        logger.info(f"[Binance] Matched TP/SL order {tpsl_oid} to main order {main_oid}, pnl={agg['total_pnl']}, total_pnl={total_pnl}")

        # If matched any order, mark as synced (even if PnL is 0 for opening trades)
        if matched_order_ids:
            decision.realized_pnl = total_pnl

            # Try to get actual trigger time for TP/SL orders
            trigger_time = None
            for oid in [decision.tp_order_id, decision.sl_order_id]:
                if oid and str(oid) in matched_order_ids:
                    trigger_time = get_order_trigger_time(decision.account_id, str(oid))
                    if trigger_time:
                        logger.info(f"Got trigger time {trigger_time} for order {oid}")
                        break

            # Use actual trigger time if available, otherwise use current time
            decision.pnl_updated_at = trigger_time if trigger_time else datetime.utcnow()
            updated = True

        # Fallback: match by time window using HyperliquidTrade (only if no direct match)
        if not updated and decision.decision_time:
            from datetime import timedelta
            time_window = timedelta(minutes=5)

            matching_trade = snapshot_db.query(HyperliquidTrade).filter(
                HyperliquidTrade.account_id == decision.account_id,
                HyperliquidTrade.symbol == decision.symbol,
                HyperliquidTrade.environment == environment,
                HyperliquidTrade.trade_time >= decision.decision_time - time_window,
                HyperliquidTrade.trade_time <= decision.decision_time + time_window,
            ).first()

            if matching_trade:
                order_id = str(matching_trade.order_id)
                if order_id in order_aggregates:
                    agg = order_aggregates[order_id]
                    decision.realized_pnl = agg["total_pnl"]
                    # Use trade time as pnl_updated_at for better accuracy
                    decision.pnl_updated_at = matching_trade.trade_time or datetime.utcnow()
                    updated = True

                    # Also update hyperliquid_order_id for future direct matching
                    if not decision.hyperliquid_order_id:
                        decision.hyperliquid_order_id = order_id

        if updated:
            result["decisions_updated"] += 1

    # Update ProgramExecutionLog records
    # Match by hyperliquid_order_id, tp_order_id, sl_order_id and accumulate PnL
    for program_log in program_logs:
        # Skip if environment doesn't match (for logs that have environment set)
        if program_log.environment and program_log.environment != environment:
            continue

        updated = False
        total_pnl = Decimal("0")
        matched_order_ids = set()

        order_ids_to_check = [
            program_log.hyperliquid_order_id,
            program_log.tp_order_id,
            program_log.sl_order_id,
        ]

        for oid in order_ids_to_check:
            if oid:
                order_id_str = str(oid)
                if order_id_str in order_aggregates and order_id_str not in matched_order_ids:
                    agg = order_aggregates[order_id_str]
                    total_pnl += agg["total_pnl"]
                    matched_order_ids.add(order_id_str)

        # For Binance: also check TP/SL orders that triggered and created new order IDs
        if exchange == "binance" and program_log.hyperliquid_order_id:
            main_oid = str(program_log.hyperliquid_order_id)
            for tpsl_oid, linked_main_oid in binance_tpsl_to_main.items():
                if linked_main_oid == main_oid and tpsl_oid not in matched_order_ids:
                    if tpsl_oid in order_aggregates:
                        agg = order_aggregates[tpsl_oid]
                        total_pnl += agg["total_pnl"]
                        matched_order_ids.add(tpsl_oid)
                        logger.info(f"[Binance] Matched TP/SL order {tpsl_oid} to program main order {main_oid}")

        if matched_order_ids:
            program_log.realized_pnl = total_pnl
            # Also set environment if not already set (for historical records)
            if not program_log.environment:
                program_log.environment = environment

            # Try to get actual trigger time for TP/SL orders
            trigger_time = None
            for oid in [program_log.tp_order_id, program_log.sl_order_id]:
                if oid and str(oid) in matched_order_ids:
                    trigger_time = get_order_trigger_time(program_log.account_id, str(oid))
                    if trigger_time:
                        break

            program_log.pnl_updated_at = trigger_time if trigger_time else datetime.utcnow()
            updated = True

        if updated:
            result["program_logs_updated"] += 1

    # Fix historical data: update pnl_updated_at for records with TP/SL orders
    # that may have been set to button click time instead of actual trigger time
    result["historical_fixed"] = 0
    for decision in decisions:
        # Skip if no TP/SL order or already processed in this run
        if not decision.tp_order_id and not decision.sl_order_id:
            continue
        if not decision.pnl_updated_at:
            continue

        # Check if pnl_updated_at might be inaccurate (set to button click time)
        # We'll try to get the actual trigger time and update if different
        for oid in [decision.tp_order_id, decision.sl_order_id]:
            if not oid:
                continue
            trigger_time = get_order_trigger_time(decision.account_id, str(oid))
            if trigger_time and trigger_time != decision.pnl_updated_at:
                # Only update if the difference is significant (> 1 minute)
                time_diff = abs((trigger_time - decision.pnl_updated_at).total_seconds())
                if time_diff > 60:
                    logger.info(
                        f"Fixing historical pnl_updated_at for decision {decision.id}: "
                        f"{decision.pnl_updated_at} -> {trigger_time}"
                    )
                    decision.pnl_updated_at = trigger_time
                    result["historical_fixed"] += 1
                    break

    return result
