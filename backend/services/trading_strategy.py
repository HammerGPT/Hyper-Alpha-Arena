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
    """Ensure stored timestamps are timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        return dt.replace(tzinfo=local_tz).astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class StrategyState:
    account_id: int
    price_threshold: float  # Price change threshold (%)
    trigger_interval: int   # Trigger interval (seconds)
    enabled: bool
    last_trigger_at: Optional[datetime]
    running: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def should_trigger(self, symbol: str, event_time: datetime) -> bool:
        """Check if strategy should trigger based on price threshold or time interval"""
        if not self.enabled:
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

            # Check time interval trigger
            time_trigger = time_diff >= self.trigger_interval

            # Check price threshold trigger
            price_change = sampling_pool.get_price_change_percent(symbol)
            price_trigger = (price_change is not None and
                            abs(price_change) >= self.price_threshold)

            if time_trigger or price_trigger:
                # Immediately update timestamp and set running state
                # This prevents duplicate triggers while AI is executing
                self.last_trigger_at = event_time
                self.running = True

                # Build trigger reason for logging
                trigger_reasons = []
                if time_trigger:
                    trigger_reasons.append(f"Time interval ({time_diff:.1f}s / {self.trigger_interval}s)")
                if price_trigger:
                    trigger_reasons.append(f"Price change ({price_change:.2f}% / {self.price_threshold}%)")

                logger.info(
                    f"Strategy triggered for account {self.account_id} on {symbol}: "
                    f"{', '.join(trigger_reasons)}"
                )
                return True

            return False


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
                    state = StrategyState(
                        account_id=strategy.account_id,
                        price_threshold=strategy.price_threshold,
                        trigger_interval=strategy.trigger_interval,
                        enabled=strategy.enabled == "true",
                        last_trigger_at=_as_aware(strategy.last_trigger_at),
                    )
                    self.strategies[strategy.account_id] = state

                    # DEBUG: Print loaded strategy configuration
                    print(
                        f"[DEBUG] Loaded strategy for account {strategy.account_id} ({account.name}): "
                        f"interval={strategy.trigger_interval}s ({strategy.trigger_interval/60:.1f}min), "
                        f"threshold={strategy.price_threshold}%, enabled={strategy.enabled}, "
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
        """Handle price update and check for strategy triggers"""
        try:
            # Add to sampling pool if needed
            with SessionLocal() as db:
                global_config = db.query(GlobalSamplingConfig).first()
                sampling_interval = global_config.sampling_interval if global_config else 18

            if sampling_pool.should_sample(symbol, sampling_interval):
                sampling_pool.add_sample(symbol, price, event_time.timestamp())

            # Check each strategy for triggers
            for account_id, state in self.strategies.items():
                if state.should_trigger(symbol, event_time):
                    self._execute_strategy(account_id, symbol, event_time)

        except Exception as e:
            logger.error(f"Error handling price update for {symbol}: {e}")
            print(f"Error in strategy manager: {e}")

    def _execute_strategy(self, account_id: int, symbol: str, event_time: datetime):
        """Execute strategy for account"""
        state = self.strategies.get(account_id)
        if not state:
            return

        # Note: running state and timestamp already set in should_trigger
        try:
            # Immediately persist timestamp to database (before AI call)
            with SessionLocal() as db:
                from database.models import AccountStrategyConfig
                strategy = db.query(AccountStrategyConfig).filter_by(account_id=account_id).first()
                if strategy:
                    strategy.last_trigger_at = event_time
                    db.commit()
                    logger.info(
                        f"Strategy execution started for account {account_id}, "
                        f"next trigger in {strategy.trigger_interval}s ({strategy.trigger_interval/60:.1f}min)"
                    )

            # Check account configuration
            with SessionLocal() as db:
                account = db.query(Account).filter(Account.id == account_id).first()
                if not account or account.auto_trading_enabled != "true":
                    logger.debug(f"Account {account_id} auto trading disabled, skipping strategy execution")
                    return

            # Execute AI trading decision (may take 10-30 seconds, but won't block next trigger check)
            logger.info(f"Account {account_id} executing Hyperliquid trading")
            from services.trading_commands import place_ai_driven_hyperliquid_order
            place_ai_driven_hyperliquid_order(account_id=account_id)

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


# Hyperliquid-only strategy manager
class HyperliquidStrategyManager(StrategyManager):
    def _load_strategies(self):
        """Load only Hyperliquid-enabled strategies from database"""
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
                    state = StrategyState(
                        account_id=strategy.account_id,
                        price_threshold=strategy.price_threshold,
                        trigger_interval=strategy.trigger_interval,
                        enabled=strategy.enabled == "true",
                        last_trigger_at=_as_aware(strategy.last_trigger_at),
                    )
                    self.strategies[strategy.account_id] = state

                # DEBUG: Print loaded strategy configuration
                    print(
                        f"[HyperliquidStrategy DEBUG] Loaded strategy for account {strategy.account_id} ({account.name}): "
                        f"interval={strategy.trigger_interval}s ({strategy.trigger_interval/60:.1f}min), "
                        f"threshold={strategy.price_threshold}%, enabled={strategy.enabled}, "
                        f"last_trigger={state.last_trigger_at}"
                    )

                logger.info(f"[HyperliquidStrategy] Loaded {len(self.strategies)} strategies")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"[HyperliquidStrategy] Failed to load strategies: {e}")
            if "database is locked" in str(e):
                logger.warning("[HyperliquidStrategy] Database locked, skipping strategy refresh")

    def _execute_strategy(self, account_id: int, symbol: str, event_time: datetime):
        """Execute strategy for Hyperliquid account"""
        state = self.strategies.get(account_id)
        if not state:
            return

        # Note: running state and timestamp already set in should_trigger
        try:
            # Immediately persist timestamp to database (before AI call)
            with SessionLocal() as db:
                strategy = db.query(AccountStrategyConfig).filter_by(account_id=account_id).first()
                if strategy:
                    strategy.last_trigger_at = event_time
                    db.commit()
                    logger.info(
                        f"[HyperliquidStrategy] Strategy execution started for account {account_id}, "
                        f"next trigger in {strategy.trigger_interval}s ({strategy.trigger_interval/60:.1f}min)"
                    )

            # Check account configuration
            with SessionLocal() as db:
                account = db.query(Account).filter(Account.id == account_id).first()
                if not account or account.auto_trading_enabled != "true":
                    logger.debug(f"[HyperliquidStrategy] Account {account_id} auto trading disabled, skipping")
                    return

            # Execute Hyperliquid trading decision (may take 10-30 seconds, but won't block next trigger check)
            place_ai_driven_hyperliquid_order(account_id=account_id)

        except Exception as e:
            logger.error(f"[HyperliquidStrategy] Error executing strategy for account {account_id}: {e}")
        finally:
            # Always reset running state
            state.running = False


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
