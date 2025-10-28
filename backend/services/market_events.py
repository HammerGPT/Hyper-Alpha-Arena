"""
Market data event dispatcher for price updates.
"""

from typing import Callable, List, Dict, Any
from threading import Lock

PriceEventHandler = Callable[[Dict[str, Any]], None]


class MarketEventDispatcher:
    """Simple thread-safe publish/subscribe dispatcher for market events."""

    def __init__(self) -> None:
        self._handlers: List[PriceEventHandler] = []
        self._lock = Lock()

    def subscribe(self, handler: PriceEventHandler) -> None:
        """Register a handler for price update events."""
        with self._lock:
            if handler not in self._handlers:
                self._handlers.append(handler)

    def unsubscribe(self, handler: PriceEventHandler) -> None:
        """Remove a previously registered handler."""
        with self._lock:
            if handler in self._handlers:
                self._handlers.remove(handler)

    def publish(self, event: Dict[str, Any]) -> None:
        """Broadcast an event to all handlers."""
        # Copy to avoid race conditions if handlers mutate list
        handlers_snapshot: List[PriceEventHandler]
        with self._lock:
            handlers_snapshot = list(self._handlers)

        for handler in handlers_snapshot:
            try:
                handler(event)
            except Exception:
                # Handler errors should not block other subscribers
                import logging

                logger = logging.getLogger(__name__)
                logger.exception("Market event handler failed")


# Global dispatcher instance
market_event_dispatcher = MarketEventDispatcher()


def subscribe_price_updates(handler: PriceEventHandler) -> None:
    market_event_dispatcher.subscribe(handler)


def unsubscribe_price_updates(handler: PriceEventHandler) -> None:
    market_event_dispatcher.unsubscribe(handler)


def publish_price_update(event: Dict[str, Any]) -> None:
    market_event_dispatcher.publish(event)
