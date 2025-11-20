"""
Unified sampling pool for AI decision making
"""
import time
from collections import deque
from typing import Dict, Optional, List
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class SamplingPool:
    def __init__(self, default_max_samples: int = 10):
        self.pools: Dict[str, deque] = {}
        self.max_samples_per_symbol: Dict[str, int] = {}  # Per-symbol max depth
        self.default_max_samples = default_max_samples
        self.last_sample_time: Dict[str, float] = {}

    def set_max_samples(self, symbol: str, max_samples: int):
        """Set maximum samples for a specific symbol"""
        if max_samples < 1:
            raise ValueError(f"max_samples must be >= 1, got {max_samples}")

        self.max_samples_per_symbol[symbol] = max_samples

        # If pool already exists, recreate it with new maxlen
        if symbol in self.pools:
            old_samples = list(self.pools[symbol])
            self.pools[symbol] = deque(old_samples, maxlen=max_samples)
            logger.info(f"Updated sampling depth for {symbol}: {max_samples} samples")

    def get_max_samples(self, symbol: str) -> int:
        """Get maximum samples configured for a symbol"""
        return self.max_samples_per_symbol.get(symbol, self.default_max_samples)

    def add_sample(self, symbol: str, price: float, timestamp: Optional[float] = None):
        """Add price sample to symbol pool"""
        if timestamp is None:
            timestamp = time.time()

        # Get max samples for this symbol
        max_samples = self.get_max_samples(symbol)

        # Create pool if not exists
        if symbol not in self.pools:
            self.pools[symbol] = deque(maxlen=max_samples)

        # Add sample
        sample = {
            'price': price,
            'timestamp': timestamp,
            'datetime': datetime.fromtimestamp(timestamp, tz=timezone.utc)
        }

        self.pools[symbol].append(sample)
        self.last_sample_time[symbol] = timestamp

    def get_samples(self, symbol: str) -> List[Dict]:
        """Get all samples for symbol"""
        return list(self.pools.get(symbol, []))

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get latest price for symbol"""
        if symbol in self.pools and self.pools[symbol]:
            return self.pools[symbol][-1]['price']
        return None

    def should_sample(self, symbol: str, interval_seconds: int = 18) -> bool:
        """Check if should add new sample based on interval"""
        if symbol not in self.last_sample_time:
            return True
        return time.time() - self.last_sample_time[symbol] >= interval_seconds

    def get_price_change_percent(self, symbol: str) -> Optional[float]:
        """Calculate price change percentage from oldest to latest sample"""
        if symbol not in self.pools or len(self.pools[symbol]) < 2:
            return None

        oldest_price = self.pools[symbol][0]['price']
        latest_price = self.pools[symbol][-1]['price']

        if oldest_price == 0:
            return None

        return ((latest_price - oldest_price) / oldest_price) * 100

    def get_pool_status(self) -> Dict:
        """Get status of all pools for monitoring"""
        status = {}
        for symbol, pool in self.pools.items():
            if pool:
                price_change = self.get_price_change_percent(symbol)
                status[symbol] = {
                    'sample_count': len(pool),
                    'latest_price': pool[-1]['price'],
                    'latest_time': pool[-1]['datetime'].isoformat(),
                    'oldest_time': pool[0]['datetime'].isoformat(),
                    'price_change_percent': round(price_change, 2) if price_change else None
                }
            else:
                status[symbol] = {
                    'sample_count': 0,
                    'latest_price': None,
                    'latest_time': None,
                    'oldest_time': None,
                    'price_change_percent': None
                }
        return status

# Global sampling pool instance
sampling_pool = SamplingPool()