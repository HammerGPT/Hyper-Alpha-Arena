"""
AI trading strategy trigger management.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, List

from database.connection import SessionLocal
from database.models import Account, AccountStrategyConfig
from repositories.strategy_repo import (
    get_strategy_by_account,
    list_strategies,
    upsert_strategy,
)
from services.market_events import subscribe_price_updates, unsubscribe_price_updates
from services.market_stream import start_market_stream
from services.trading_commands import place_ai_driven_crypto_order, AI_TRADING_SYMBOLS

logger = logging.getLogger(__name__)

MIN_REALTIME_INTERVAL = 1.0  # seconds
STRATEGY_REFRESH_INTERVAL = 60.0  # seconds


@dataclass
class StrategyState:
    account_id: int
    trigger_mode: str
    interval_seconds: Optional[int]
    tick_batch_size: Optional[int]
    enabled: bool
    last_trigger_at: Optional[datetime]
    tick_counter: int = 0
    running: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def should_trigger(self, event_time: datetime) -> bool:
        if not self.enabled:
            return False

        now_ts = event_time.timestamp()
        last_ts = self.last_trigger_at.timestamp() if self.last_trigger_at else None

        if self.trigger_mode == "realtime":
            if last_ts is None:
                return True
            return (now_ts - last_ts) >= MIN_REALTIME_INTERVAL

        if self.trigger_mode == "interval":
            if not self.interval_seconds or self.interval_seconds <= 0:
                return True
            if last_ts is None:
                return True
            return (now_ts - last_ts) >= self.interval_seconds

        if self.trigger_mode == "tick_batch":
            if not self.tick_batch_size or self.tick_batch_size <= 1:
                return True
            return self.tick_counter + 1 >= self.tick_batch_size

        # Fallback: treat as realtime
        if last_ts is None:
            return True
        return (now_ts - last_ts) >= MIN_REALTIME_INTERVAL

    def update_after_trigger(self, event_time: datetime) -> None:
        self.last_trigger_at = event_time
        self.tick_counter = 0

    def increment_tick(self) -> None:
        self.tick_counter += 1


class StrategyManager:
    def __init__(self) -> None:
        self._states: Dict[int, StrategyState] = {}
        self._lock = threading.Lock()
        self._last_refresh = 0.0

    def start(self) -> None:
        self.refresh_strategies(force=True)
        subscribe_price_updates(self.handle_price_update)
        logger.info("Trading strategy manager subscribed to price updates")

    def stop(self) -> None:
        unsubscribe_price_updates(self.handle_price_update)
        logger.info("Trading strategy manager unsubscribed from price updates")

    def refresh_strategies(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._last_refresh) < STRATEGY_REFRESH_INTERVAL:
            return

        session = SessionLocal()
        try:
            accounts = (
                session.query(Account)
                .filter(
                    Account.is_active == "true",
                    Account.account_type == "AI",
                )
                .all()
            )

            configs = list_strategies(session)
            config_map = {cfg.account_id: cfg for cfg in configs}

            new_states: Dict[int, StrategyState] = {}
            for account in accounts:
                cfg = config_map.get(account.id)
                if cfg is None:
                    cfg = upsert_strategy(
                        session,
                        account_id=account.id,
                        trigger_mode="realtime",
                        interval_seconds=1,
                        tick_batch_size=1,
                        enabled=(account.auto_trading_enabled == "true"),
                    )
                enabled = cfg.enabled == "true" and account.auto_trading_enabled == "true"
                existing_state = self._states.get(account.id)

                # If state exists, update in-place instead of replacing
                # This prevents race conditions with running threads
                if existing_state:
                    existing_state.trigger_mode = cfg.trigger_mode or "realtime"
                    existing_state.interval_seconds = cfg.interval_seconds
                    existing_state.tick_batch_size = cfg.tick_batch_size
                    existing_state.enabled = enabled
                    existing_state.last_trigger_at = cfg.last_trigger_at
                    new_states[account.id] = existing_state
                else:
                    # Create new state only if it doesn't exist
                    state = StrategyState(
                        account_id=account.id,
                        trigger_mode=cfg.trigger_mode or "realtime",
                        interval_seconds=cfg.interval_seconds,
                        tick_batch_size=cfg.tick_batch_size,
                        enabled=enabled,
                        last_trigger_at=cfg.last_trigger_at,
                    )
                    new_states[account.id] = state

            with self._lock:
                self._states = new_states
                self._last_refresh = now

        except Exception as err:
            logger.error("Failed to refresh strategy configs: %s", err)
        finally:
            session.close()

    def handle_price_update(self, event: Dict[str, Any]) -> None:
        from services.system_logger import system_logger

        symbol = event.get("symbol", "UNKNOWN")
        price = event.get("price", 0)

        # Log every price update event
        system_logger.add_log(
            level="INFO",
            category="price_update",
            message=f"Market stream event: {symbol}=${price:.4f}",
            details={"symbol": symbol, "price": price, "source": "market_stream"}
        )

        self.refresh_strategies()
        event_time: datetime = event.get("event_time") or datetime.now(tz=timezone.utc)
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)

        states_snapshot: List[StrategyState]
        with self._lock:
            states_snapshot = list(self._states.values())

        for state in states_snapshot:
            if state.trigger_mode == "tick_batch":
                state.increment_tick()
            else:
                state.tick_counter = 0

            should_trigger = state.should_trigger(event_time)

            # Log trigger decision
            if state.enabled:
                system_logger.add_log(
                    level="INFO",
                    category="ai_decision",
                    message=f"Strategy check for account {state.account_id}: should_trigger={should_trigger}, enabled={state.enabled}, running={state.running}",
                    details={
                        "account_id": state.account_id,
                        "trigger_mode": state.trigger_mode,
                        "should_trigger": should_trigger,
                        "enabled": state.enabled,
                        "running": state.running,
                        "last_trigger_at": state.last_trigger_at.isoformat() if state.last_trigger_at else None
                    }
                )

            if not should_trigger:
                continue
            self._trigger_account(state, event_time)

    def _trigger_account(self, state: StrategyState, event_time: datetime) -> None:
        from services.system_logger import system_logger

        if not state.enabled:
            state.tick_counter = 0
            return

        if state.running:
            system_logger.add_log(
                level="WARNING",
                category="ai_decision",
                message=f"Account {state.account_id} trading still running, skipping trigger",
                details={"account_id": state.account_id, "running": state.running}
            )
            return

        def runner():
            with state.lock:
                if state.running:
                    return
                state.running = True

            system_logger.add_log(
                level="INFO",
                category="ai_decision",
                message=f"Starting AI trading thread for account {state.account_id}",
                details={"account_id": state.account_id}
            )

            try:
                place_ai_driven_crypto_order(account_ids=[state.account_id])
                state.update_after_trigger(event_time)
                system_logger.add_log(
                    level="INFO",
                    category="ai_decision",
                    message=f"AI trading completed successfully for account {state.account_id}",
                    details={"account_id": state.account_id}
                )
            except Exception as err:
                logger.error("Strategy trigger failed for account %s: %s", state.account_id, err)
                system_logger.add_log(
                    level="ERROR",
                    category="ai_decision",
                    message=f"AI trading failed for account {state.account_id}: {str(err)[:200]}",
                    details={"account_id": state.account_id, "error": str(err)}
                )
            finally:
                with state.lock:
                    state.running = False
                    state.tick_counter = 0
                system_logger.add_log(
                    level="INFO",
                    category="ai_decision",
                    message=f"AI trading thread finished for account {state.account_id}, set running=False",
                    details={"account_id": state.account_id, "running": False}
                )

        threading.Thread(target=runner, name=f"strategy-trigger-{state.account_id}", daemon=True).start()


strategy_manager = StrategyManager()


def start_trading_strategy_manager() -> None:
    strategy_manager.start()
    # Ensure market stream covers relevant symbols
    start_market_stream(AI_TRADING_SYMBOLS, interval_seconds=1.5)


def stop_trading_strategy_manager() -> None:
    strategy_manager.stop()
