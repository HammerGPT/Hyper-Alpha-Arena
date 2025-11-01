"""
Background market data polling to keep cache and event stream in sync.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from database.connection import SessionLocal
from database.models import CryptoPriceTick
from services.hyperliquid_market_data import hyperliquid_client
from services.price_cache import record_price_update
from services.market_events import publish_price_update
from services.trading_strategy import handle_price_update

logger = logging.getLogger(__name__)


class MarketDataStream:
    """Background thread fetching market data at a steady cadence."""

    def __init__(
        self,
        symbols: Iterable[str],
        market: str = "CRYPTO",
        interval_seconds: float = 1.5,
        retention_seconds: int = 3600,
    ) -> None:
        self.symbols = list(symbols)
        self.market = market
        self.interval_seconds = interval_seconds
        self.retention_seconds = retention_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="market-data-stream", daemon=True)
        self._thread.start()
        logger.info(
            "Market data stream started for %d symbols (interval=%.2fs)",
            len(self.symbols),
            self.interval_seconds,
        )

    def stop(self) -> None:
        if not self._thread:
            return
        self._stop_event.set()
        self._thread.join(timeout=5)
        logger.info("Market data stream stopped")

    def update_symbols(self, symbols: Iterable[str]) -> None:
        self.symbols = list(symbols)
        logger.info("Market data stream symbol set updated: %s", ", ".join(self.symbols))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            start_time = time.time()
            for symbol in self.symbols:
                if self._stop_event.is_set():
                    break
                self._process_symbol(symbol)
            elapsed = time.time() - start_time
            sleep_for = max(0.0, self.interval_seconds - elapsed)
            if sleep_for > 0:
                time.sleep(sleep_for)

    def _process_symbol(self, symbol: str) -> None:
        """Fetch ticker for symbol, update cache, persist tick, publish event."""
        try:
            ticker_price = hyperliquid_client.get_last_price(symbol)
        except Exception as fetch_err:
            logger.warning("Failed to fetch price for %s: %s", symbol, fetch_err)
            return

        if ticker_price is None:
            logger.debug("No price returned for %s", symbol)
            return

        event_time = datetime.now(tz=timezone.utc)
        timestamp = event_time.timestamp()

        record_price_update(symbol, self.market, float(ticker_price), timestamp)
        self._persist_tick(symbol, float(ticker_price), event_time)

        publish_price_update(
            {
                "symbol": symbol,
                "market": self.market,
                "price": float(ticker_price),
                "event_time": event_time,
                "timestamp": timestamp,
            }
        )

        # Handle strategy triggers and sampling
        handle_price_update(symbol, float(ticker_price), event_time)

    def _persist_tick(self, symbol: str, price: float, event_time: datetime) -> None:
        """Persist tick data and prune old entries beyond retention window."""
        session = SessionLocal()
        try:
            tick = CryptoPriceTick(
                symbol=symbol,
                market=self.market,
                price=price,
                event_time=event_time,
            )
            session.add(tick)
            session.commit()

            cutoff = event_time.timestamp() - self.retention_seconds
            cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)

            deleted = (
                session.query(CryptoPriceTick)
                .filter(
                    CryptoPriceTick.symbol == symbol,
                    CryptoPriceTick.event_time < cutoff_dt,
                )
                .delete(synchronize_session=False)
            )
            if deleted:
                session.commit()
                logger.debug("Purged %d old ticks for %s", deleted, symbol)
        except Exception as err:
            session.rollback()
            logger.error("Failed to persist tick for %s: %s", symbol, err)
        finally:
            session.close()


# Global stream holder (initialized in startup)
market_data_stream: Optional[MarketDataStream] = None


def start_market_stream(symbols: List[str], interval_seconds: float = 1.5) -> None:
    global market_data_stream
    if market_data_stream and market_data_stream._thread and market_data_stream._thread.is_alive():
        market_data_stream.update_symbols(symbols)
        return

    market_data_stream = MarketDataStream(symbols=symbols, interval_seconds=interval_seconds)
    market_data_stream.start()


def stop_market_stream() -> None:
    global market_data_stream
    if market_data_stream:
        market_data_stream.stop()
        market_data_stream = None
