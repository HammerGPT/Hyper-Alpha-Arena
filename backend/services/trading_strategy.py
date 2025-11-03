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
from repositories.strategy_repo import (
    get_strategy_by_account,
    list_strategies,
    upsert_strategy,
)
from services.sampling_pool import sampling_pool
from services.trading_commands import place_ai_driven_crypto_order, AI_TRADING_SYMBOLS

logger = logging.getLogger(__name__)

STRATEGY_REFRESH_INTERVAL = 60.0  # seconds


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure stored timestamps are timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
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

        now_ts = event_time.timestamp()
        last_ts = self.last_trigger_at.timestamp() if self.last_trigger_at else 0

        # Check time interval trigger
        time_trigger = (now_ts - last_ts) >= self.trigger_interval

        # Check price threshold trigger
        price_change = sampling_pool.get_price_change_percent(symbol)
        price_trigger = (price_change is not None and
                        abs(price_change) >= self.price_threshold)

        return time_trigger or price_trigger


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
            with SessionLocal() as db:
                strategies = list_strategies(db)

                for strategy in strategies:
                    state = StrategyState(
                        account_id=strategy.account_id,
                        price_threshold=strategy.price_threshold,
                        trigger_interval=strategy.trigger_interval,
                        enabled=strategy.enabled == "true",
                        last_trigger_at=_as_aware(strategy.last_trigger_at),
                    )
                    self.strategies[strategy.account_id] = state

                logger.info(f"Loaded {len(self.strategies)} strategies")

        except Exception as e:
            logger.error(f"Failed to load strategies: {e}")

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
            # Create snapshot to avoid "dictionary changed size during iteration" error
            for account_id, state in list(self.strategies.items()):
                if state.should_trigger(symbol, event_time):
                    self._execute_strategy(account_id, symbol, event_time)

        except Exception as e:
            logger.error(f"Error handling price update for {symbol}: {e}")

    def _execute_strategy(self, account_id: int, symbol: str, event_time: datetime):
        """Execute strategy for account"""
        state = self.strategies.get(account_id)
        if not state:
            return

        with state.lock:
            if state.running:
                logger.debug(f"Strategy for account {account_id} already running, skipping")
                return

            state.running = True

        try:
            logger.info(f"Executing strategy for account {account_id}, symbol {symbol}")

            # Get sampling data for AI decision
            samples = sampling_pool.get_samples(symbol)

            # Execute AI trading decision
            place_ai_driven_crypto_order(
                account_id=account_id,
                symbol=symbol,
                samples=samples
            )

            # Update last trigger time
            state.last_trigger_at = event_time

            # Update database
            with SessionLocal() as db:
                strategy = get_strategy_by_account(db, account_id)
                if strategy:
                    strategy.last_trigger_at = event_time
                    db.commit()

        except Exception as e:
            logger.error(f"Error executing strategy for account {account_id}: {e}")
        finally:
            state.running = False

    def get_strategy_status(self) -> Dict[str, Any]:
        """Get status of all strategies"""
        status = {
            "running": self.running,
            "strategy_count": len(self.strategies),
            "strategies": {}
        }

        # Create snapshot to avoid "dictionary changed size during iteration" error
        for account_id, state in list(self.strategies.items()):
            status["strategies"][account_id] = {
                "enabled": state.enabled,
                "running": state.running,
                "price_threshold": state.price_threshold,
                "trigger_interval": state.trigger_interval,
                "last_trigger_at": state.last_trigger_at.isoformat() if state.last_trigger_at else None
            }

        return status


# Global strategy manager instance
strategy_manager = StrategyManager()


def start_strategy_manager():
    """Start the global strategy manager"""
    strategy_manager.start()


def stop_strategy_manager():
    """Stop the global strategy manager"""
    strategy_manager.stop()


def handle_price_update(symbol: str, price: float, event_time: Optional[datetime] = None):
    """Handle price update from market data"""
    if event_time is None:
        event_time = datetime.now(timezone.utc)

    strategy_manager.handle_price_update(symbol, price, event_time)


def get_strategy_status() -> Dict[str, Any]:
    """Get strategy manager status"""
    return strategy_manager.get_strategy_status()