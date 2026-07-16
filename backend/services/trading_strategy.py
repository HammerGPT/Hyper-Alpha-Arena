"""
AI trading strategy trigger management with simplified logic.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, Any, List

from database.connection import SessionLocal
from database.models import Account, AccountStrategyConfig, GlobalSamplingConfig
from sqlalchemy import text
from repositories.strategy_repo import (
    get_strategy_by_account,
    list_strategies,
    upsert_strategy,
)
from services.sampling_pool import sampling_pool
from services.trading_commands import (
    place_ai_driven_crypto_order,
    place_ai_driven_hyperliquid_order,
)
from services.hyperliquid_symbol_service import get_selected_symbols as get_hyperliquid_selected_symbols

logger = logging.getLogger(__name__)

STRATEGY_REFRESH_INTERVAL = 60.0  # seconds


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure stored timestamps are timezone-aware UTC.

    Note: Database stores UTC time in 'timestamp without time zone' columns.
    The naive datetime from DB is already UTC, just missing the timezone marker.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Database stores UTC time, so treat naive datetime as UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class StrategyState:
    account_id: int
    price_threshold: float  # Deprecated, kept for compatibility
    trigger_interval: int   # Trigger interval (seconds) - scheduled trigger fallback
    signal_pool_ids: List[int]  # Signal pool bindings for signal-based triggering (OR relationship)
    enabled: bool
    scheduled_trigger_enabled: bool  # Enable/disable scheduled trigger
    last_trigger_at: Optional[datetime]
    exchange: str = "hyperliquid"  # "hyperliquid" or "binance"
    execution_mode: str = "real"  # "real" or "paper"
    running: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    # Backward compatibility property
    @property
    def signal_pool_id(self) -> Optional[int]:
        return self.signal_pool_ids[0] if self.signal_pool_ids else None

    def should_trigger_scheduled(self, event_time: datetime) -> bool:
        """Check if strategy should trigger based on scheduled time interval (fallback)"""
        if not self.enabled:
            return False

        # Check if scheduled trigger is disabled
        if not self.scheduled_trigger_enabled:
            return False

        # Quick check without lock to avoid unnecessary contention
        if self.running:
            return False

        with self.lock:
            # Double-check after acquiring lock
            if self.running:
                return False

            now_ts = event_time.timestamp()
            last_ts = self.last_trigger_at.timestamp() if self.last_trigger_at else 0
            time_diff = now_ts - last_ts

            # Check time interval trigger (scheduled fallback)
            if time_diff >= self.trigger_interval:
                self.last_trigger_at = event_time
                self.running = True
                logger.info(
                    f"Strategy scheduled trigger for account {self.account_id}: "
                    f"Time interval ({time_diff:.1f}s / {self.trigger_interval}s)"
                )
                return True

            return False

    def mark_triggered_by_signal(self, event_time: datetime) -> bool:
        """Mark strategy as triggered by signal (called from signal callback)"""
        if not self.enabled:
            return False

        with self.lock:
            if self.running:
                return False
            self.last_trigger_at = event_time
            self.running = True
            return True


class StrategyManager:
    def __init__(self):
        self.strategies: Dict[int, StrategyState] = {}
        self.lock = threading.Lock()
        self.running = False
        self.refresh_thread: Optional[threading.Thread] = None

    def start(self):
        """Start the strategy manager"""
        with self.lock:
            if self.running:
                logger.warning("Strategy manager already running")
                return

            self.running = True
            self._load_strategies()

            # Start refresh thread
            self.refresh_thread = threading.Thread(
                target=self._refresh_strategies_loop,
                daemon=True
            )
            self.refresh_thread.start()

            logger.info("Strategy manager started")

    def stop(self):
        """Stop the strategy manager"""
        with self.lock:
            if not self.running:
                return

            self.running = False

        if self.refresh_thread:
            self.refresh_thread.join(timeout=5.0)

        logger.info("Strategy manager stopped")

    def _load_strategies(self):
        """Load strategies from database"""
        from repositories.strategy_repo import parse_signal_pool_ids

        try:
            # PostgreSQL handles concurrent access natively
            db = SessionLocal()
            try:
                rows = (
                    db.query(AccountStrategyConfig, Account)
                    .join(Account, AccountStrategyConfig.account_id == Account.id)
                    .all()
                )

                self.strategies.clear()
                for strategy, account in rows:
                    pool_ids = parse_signal_pool_ids(strategy)
                    state = StrategyState(
                        account_id=strategy.account_id,
                        price_threshold=strategy.price_threshold,
                        trigger_interval=strategy.trigger_interval,
                        signal_pool_ids=pool_ids,
                        enabled=strategy.enabled == "true",
                        scheduled_trigger_enabled=strategy.scheduled_trigger_enabled,
                        last_trigger_at=_as_aware(strategy.last_trigger_at),
                        exchange=getattr(strategy, 'exchange', None) or "hyperliquid",
                        execution_mode=getattr(strategy, "execution_mode", None) or "real",
                    )
                    self.strategies[strategy.account_id] = state

                    # DEBUG: Print loaded strategy configuration
                    print(
                        f"[DEBUG] Loaded strategy for account {strategy.account_id} ({account.name}): "
                        f"interval={strategy.trigger_interval}s ({strategy.trigger_interval/60:.1f}min), "
                        f"signal_pool_ids={pool_ids}, enabled={strategy.enabled}, "
                        f"scheduled_trigger={strategy.scheduled_trigger_enabled}, "
                        f"last_trigger={state.last_trigger_at}"
                    )

                logger.info(f"Loaded {len(self.strategies)} strategies")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Failed to load strategies: {e}")
            # Don't retry immediately on database lock
            if "database is locked" in str(e):
                logger.warning("Database locked, skipping strategy refresh")

    def _refresh_strategies_loop(self):
        """Periodically refresh strategies from database"""
        while self.running:
            try:
                time.sleep(STRATEGY_REFRESH_INTERVAL)
                if self.running:
                    self._load_strategies()
            except Exception as e:
                logger.error(f"Error in strategy refresh loop: {e}")

    def handle_price_update(self, symbol: str, price: float, event_time: datetime):
        """Handle price update and check for scheduled strategy triggers (fallback)"""
        try:
            # Add to sampling pool if needed
            with SessionLocal() as db:
                global_config = db.query(GlobalSamplingConfig).first()
                sampling_interval = global_config.sampling_interval if global_config else 18

            if sampling_pool.should_sample(symbol, sampling_interval):
                sampling_pool.add_sample(symbol, price, event_time.timestamp())

            # Check each strategy for scheduled triggers (fallback mechanism)
            # Signal-based triggers are handled via callback from signal_detection_service
            for account_id, state in self.strategies.items():
                if state.should_trigger_scheduled(event_time):
                    # Build trigger context for scheduled triggers
                    scheduled_trigger_context = {
                        "trigger_type": "scheduled",
                        "trigger_interval": state.trigger_interval,
                    }
                    self._execute_strategy(
                        account_id, symbol, event_time,
                        trigger_type="scheduled",
                        trigger_context=scheduled_trigger_context
                    )

        except Exception as e:
            logger.error(f"Error handling price update for {symbol}: {e}")
            print(f"Error in strategy manager: {e}")

    def _execute_strategy(
        self,
        account_id: int,
        symbol: str,
        event_time: datetime,
        trigger_type: str = "scheduled",
        trigger_context: Optional[Dict[str, Any]] = None
    ):
        """Execute strategy for account with trigger context"""
        state = self.strategies.get(account_id)
        if not state:
            return

        # Note: running state and timestamp already set in should_trigger or mark_triggered_by_signal
        try:
            # Immediately persist timestamp to database (before AI call)
            with SessionLocal() as db:
                from database.models import AccountStrategyConfig
                strategy = db.query(AccountStrategyConfig).filter_by(account_id=account_id).first()
                if strategy:
                    strategy.last_trigger_at = event_time
                    db.commit()
                    logger.info(
                        f"Strategy execution started for account {account_id} (trigger: {trigger_type}), "
                        f"next scheduled trigger in {strategy.trigger_interval}s ({strategy.trigger_interval/60:.1f}min)"
                    )

            # Check account configuration
            with SessionLocal() as db:
                account = db.query(Account).filter(Account.id == account_id, Account.is_deleted != True).first()
                if not account or account.auto_trading_enabled != "true":
                    logger.debug(f"Account {account_id} auto trading disabled, skipping strategy execution")
                    return

            # Execute AI trading decision based on exchange configuration
            exchange = state.exchange
            logger.info(f"Account {account_id} executing {exchange} trading (trigger: {trigger_type})")

            if exchange == "binance":
                from services.trading_commands import place_ai_driven_binance_order
                place_ai_driven_binance_order(account_id=account_id, trigger_context=trigger_context)
            else:
                # Default to Hyperliquid
                from services.trading_commands import place_ai_driven_hyperliquid_order
                place_ai_driven_hyperliquid_order(account_id=account_id, trigger_context=trigger_context)

        except Exception as e:
            logger.error(f"Error executing strategy for account {account_id}: {e}")
        finally:
            # Always reset running state
            state.running = False

    def get_strategy_status(self) -> Dict[str, Any]:
        """Get status of all strategies"""
        status = {
            "running": self.running,
            "strategy_count": len(self.strategies),
            "strategies": {}
        }

        for account_id, state in self.strategies.items():
            status["strategies"][account_id] = {
                "enabled": state.enabled,
                "running": state.running,
                "price_threshold": state.price_threshold,
                "trigger_interval": state.trigger_interval,
                "last_trigger_at": state.last_trigger_at.isoformat() if state.last_trigger_at else None
            }

        return status


# Hyperliquid-only strategy manager with signal pool support
class HyperliquidStrategyManager(StrategyManager):
    def __init__(self):
        super().__init__()
        self._signal_callback_registered = False

    def start(self):
        """Start the strategy manager and register signal callback"""
        super().start()
        self._register_signal_callback()

    def stop(self):
        """Stop the strategy manager and unregister signal callback"""
        self._unregister_signal_callback()
        super().stop()

    def _register_signal_callback(self):
        """Register callback with signal detection service"""
        logger.warning("[HyperliquidStrategy] _register_signal_callback() called")
        if self._signal_callback_registered:
            logger.warning("[HyperliquidStrategy] Callback already registered, skipping")
            return
        try:
            from services.signal_detection_service import signal_detection_service
            logger.warning(f"[HyperliquidStrategy] Callbacks before register: {len(signal_detection_service._trigger_callbacks)}")
            signal_detection_service.subscribe_signal_triggers(self._on_signal_triggered)
            self._signal_callback_registered = True
            logger.warning(f"[HyperliquidStrategy] Signal trigger callback registered! Callbacks after: {len(signal_detection_service._trigger_callbacks)}")
        except Exception as e:
            logger.error(f"[HyperliquidStrategy] Failed to register signal callback: {e}", exc_info=True)

    def _unregister_signal_callback(self):
        """Unregister callback from signal detection service"""
        if not self._signal_callback_registered:
            return
        try:
            from services.signal_detection_service import signal_detection_service
            signal_detection_service.unsubscribe_signal_triggers(self._on_signal_triggered)
            self._signal_callback_registered = False
            logger.info("[HyperliquidStrategy] Signal trigger callback unregistered")
        except Exception as e:
            logger.error(f"[HyperliquidStrategy] Failed to unregister signal callback: {e}")

    def _on_signal_triggered(self, symbol: str, pool: dict, market_data: dict, triggered_signals: list):
        """Callback when a signal pool triggers - find and execute bound strategies"""
        pool_id = pool.get("pool_id")  # Fixed: key is "pool_id" not "id"
        pool_name = pool.get("pool_name", "Unknown")
        event_time = datetime.now(timezone.utc)
        trigger_type = pool.get("trigger_type", "signal")
        wallet_event = pool.get("wallet_event")

        print(f"[HyperliquidStrategy] Signal pool triggered: {pool_name} (pool_id={pool_id}) on {symbol}")
        print(f"[HyperliquidStrategy] Checking {len(self.strategies)} strategies for pool_id={pool_id}")

        # Also trigger Program Trader execution
        try:
            from services.program_execution_service import program_execution_service
            program_execution_service.on_signal_triggered(symbol, pool, market_data, triggered_signals)
        except Exception as e:
            logger.error(f"[HyperliquidStrategy] Failed to trigger program execution: {e}")

        # Find all strategies bound to this signal pool (check if pool_id in signal_pool_ids)
        found_match = False
        for account_id, state in self.strategies.items():
            print(f"[HyperliquidStrategy] Account {account_id}: signal_pool_ids={state.signal_pool_ids}, enabled={state.enabled}")
            if pool_id in state.signal_pool_ids:
                found_match = True
                # Try to mark as triggered (handles running state check)
                if state.mark_triggered_by_signal(event_time):
                    # Build trigger context for AI prompt
                    trigger_context = {
                        "signal_pool_id": pool_id,
                        "signal_pool_name": pool_name,
                        "pool_logic": pool.get("logic", "OR"),
                        "trigger_symbol": symbol,
                        "market_data_snapshot": market_data,
                        "signal_trigger_id": pool.get("trigger_log_id"),  # For decision tracking
                    }
                    if trigger_type == "wallet_signal":
                        trigger_context["trigger_type"] = "wallet_signal"
                        trigger_context["wallet_event"] = wallet_event
                    else:
                        trigger_context["trigger_type"] = "signal"
                        trigger_context["triggered_signals"] = triggered_signals
                    print(f"[HyperliquidStrategy] Executing strategy for account {account_id} (signal pool: {pool_name})")
                    self._execute_strategy(
                        account_id, symbol, event_time,
                        trigger_type=trigger_type, trigger_context=trigger_context
                    )
                else:
                    print(f"[HyperliquidStrategy] Account {account_id} mark_triggered_by_signal returned False (already running?)")

        if not found_match:
            print(f"[HyperliquidStrategy] No strategy found bound to pool_id={pool_id}")

    def _load_strategies(self):
        """Load only Hyperliquid-enabled strategies from database"""
        from repositories.strategy_repo import parse_signal_pool_ids

        try:
            db = SessionLocal()
            try:
                rows = (
                    db.query(AccountStrategyConfig, Account)
                    .join(Account, AccountStrategyConfig.account_id == Account.id)
                    .all()
                )

                self.strategies.clear()
                for strategy, account in rows:
                    pool_ids = parse_signal_pool_ids(strategy)
                    state = StrategyState(
                        account_id=strategy.account_id,
                        price_threshold=strategy.price_threshold,
                        trigger_interval=strategy.trigger_interval,
                        signal_pool_ids=pool_ids,
                        enabled=strategy.enabled == "true",
                        scheduled_trigger_enabled=strategy.scheduled_trigger_enabled,
                        last_trigger_at=_as_aware(strategy.last_trigger_at),
                        exchange=getattr(strategy, 'exchange', None) or "hyperliquid",
                        execution_mode=getattr(strategy, "execution_mode", None) or "real",
                    )
                    self.strategies[strategy.account_id] = state

                    print(
                        f"[HyperliquidStrategy DEBUG] Loaded strategy for account {strategy.account_id} ({account.name}): "
                        f"interval={strategy.trigger_interval}s ({strategy.trigger_interval/60:.1f}min), "
                        f"signal_pool_ids={pool_ids}, enabled={strategy.enabled}, exchange={state.exchange}, "
                        f"scheduled_trigger={strategy.scheduled_trigger_enabled}, "
                        f"last_trigger={state.last_trigger_at}"
                    )

                logger.info(f"[HyperliquidStrategy] Loaded {len(self.strategies)} strategies")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"[HyperliquidStrategy] Failed to load strategies: {e}")
            if "database is locked" in str(e):
                logger.warning("[HyperliquidStrategy] Database locked, skipping strategy refresh")


# Global strategy manager instance (Hyperliquid only)
hyper_strategy_manager = HyperliquidStrategyManager()


def start_strategy_manager():
    """Start the global strategy manager"""
    hyper_strategy_manager.start()


def stop_strategy_manager():
    """Stop the global strategy manager"""
    hyper_strategy_manager.stop()


def handle_price_update(symbol: str, price: float, event_time: Optional[datetime] = None):
    """Handle price update from market data"""
    if event_time is None:
        event_time = datetime.now(timezone.utc)


    # Use Hyperliquid strategy manager only
    hyper_strategy_manager.handle_price_update(symbol, price, event_time)


def _execute_strategy_direct(account_id: int, symbol: str, event_time: datetime, db, is_hyper: bool = False):
    """Execute strategy directly without going through StrategyManager"""
    try:
        from database.models import AccountStrategyConfig

        # Update last trigger time
        strategy = db.query(AccountStrategyConfig).filter_by(account_id=account_id).first()
        if strategy:
            strategy.last_trigger_at = event_time
            db.commit()

        # Execute the trade
        if is_hyper:
            logger.info(f"[DirectStrategy] Executing Hyperliquid trade for account {account_id}")
            place_ai_driven_hyperliquid_order(account_id=account_id)
        else:
            from services.auto_trader import place_ai_driven_crypto_order
            place_ai_driven_crypto_order(max_ratio=0.2, account_id=account_id)
        logger.info(f"Strategy executed for account {account_id} on {symbol} price update")

    except Exception as e:
        logger.error(f"Failed to execute strategy for account {account_id}: {e}")
        import traceback
        traceback.print_exc()


def get_strategy_status() -> Dict[str, Any]:
    """Get strategy manager status"""
    status = {
        "hyperliquid": hyper_strategy_manager.get_strategy_status(),
    }
    return status
