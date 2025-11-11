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
    AI_TRADING_SYMBOLS,
)

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
            print(f"Strategy for account {self.account_id} is disabled")
            return False

        now_ts = event_time.timestamp()
        last_ts = self.last_trigger_at.timestamp() if self.last_trigger_at else 0

        # Check time interval trigger
        time_trigger = (now_ts - last_ts) >= self.trigger_interval
        print(f"Time check for {symbol}: now={now_ts}, last={last_ts}, interval={self.trigger_interval}, trigger={time_trigger}")

        # Check price threshold trigger
        price_change = sampling_pool.get_price_change_percent(symbol)
        price_trigger = (price_change is not None and
                        abs(price_change) >= self.price_threshold)
        print(f"Price check for {symbol}: change={price_change}, threshold={self.price_threshold}, trigger={price_trigger}")

        result = time_trigger or price_trigger
        print(f"Strategy trigger result for {symbol}: {result}")
        return result


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
            print(f"StrategyManager handling price update: {symbol} = {price}")
            # Add to sampling pool if needed
            with SessionLocal() as db:
                global_config = db.query(GlobalSamplingConfig).first()
                sampling_interval = global_config.sampling_interval if global_config else 18

            if sampling_pool.should_sample(symbol, sampling_interval):
                sampling_pool.add_sample(symbol, price, event_time.timestamp())

            # Check each strategy for triggers
            print(f"Checking {len(self.strategies)} strategies for triggers")
            for account_id, state in self.strategies.items():
                print(f"Checking strategy for account {account_id}")
                if state.should_trigger(symbol, event_time):
                    print(f"Strategy triggered for account {account_id}!")
                    self._execute_strategy(account_id, symbol, event_time)

        except Exception as e:
            logger.error(f"Error handling price update for {symbol}: {e}")
            print(f"Error in strategy manager: {e}")

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

            # Check account configuration
            with SessionLocal() as db:
                account = db.query(Account).filter(Account.id == account_id).first()
                if not account or account.auto_trading_enabled != "true":
                    logger.debug(f"Account {account_id} auto trading disabled, skipping strategy execution")
                    return

            # Execute AI trading decision for Hyperliquid account
            logger.info(f"Account {account_id} executing Hyperliquid trading")
            from services.trading_commands import place_ai_driven_hyperliquid_order
            place_ai_driven_hyperliquid_order(account_id=account_id)

            # Update last trigger time
            state.last_trigger_at = event_time

            # Update database
            with SessionLocal() as db:
                from database.models import AccountStrategyConfig
                strategy = db.query(AccountStrategyConfig).filter_by(account_id=account_id).first()
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

        with state.lock:
            if state.running:
                logger.debug(f"[HyperliquidStrategy] Account {account_id} already running, skipping")
                return
            state.running = True

        try:
            logger.info(f"[HyperliquidStrategy] Executing strategy for account {account_id}, symbol {symbol}")

            with SessionLocal() as db:
                account = db.query(Account).filter(Account.id == account_id).first()
                if not account or account.auto_trading_enabled != "true":
                    logger.debug(f"[HyperliquidStrategy] Account {account_id} auto trading disabled, skipping")
                    return

            # Execute Hyperliquid trading decision
            place_ai_driven_hyperliquid_order(account_id=account_id)

            # Update in-memory timestamp
            state.last_trigger_at = event_time

            # Persist last trigger time
            with SessionLocal() as db:
                strategy = db.query(AccountStrategyConfig).filter_by(account_id=account_id).first()
                if strategy:
                    strategy.last_trigger_at = event_time
                    db.commit()

        except Exception as e:
            logger.error(f"[HyperliquidStrategy] Error executing strategy for account {account_id}: {e}")
        finally:
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

    print(f"Global handle_price_update called: {symbol} = {price}")

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
