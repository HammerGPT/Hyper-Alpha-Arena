"""
Price caching service to reduce API calls and improve performance
"""

import time
from typing import Dict, Optional, Tuple
import logging
from threading import Lock

logger = logging.getLogger(__name__)


class PriceCache:
    """Simple in-memory price cache with TTL"""
    
    def __init__(self, ttl_seconds: int = 30):
        self.cache: Dict[Tuple[str, str], Tuple[float, float]] = {}  # key: (symbol, market), value: (price, timestamp)
        self.ttl_seconds = ttl_seconds
        self.lock = Lock()
    
    def get(self, symbol: str, market: str) -> Optional[float]:
        """Get cached price if still valid"""
        key = (symbol, market)
        current_time = time.time()
        
        with self.lock:
            if key in self.cache:
                price, timestamp = self.cache[key]
                if current_time - timestamp < self.ttl_seconds:
                    logger.debug(f"Cache hit for {symbol}.{market}: {price}")
                    return price
                else:
                    # Remove expired entry
                    del self.cache[key]
                    logger.debug(f"Cache expired for {symbol}.{market}")
        
        return None
    
    def set(self, symbol: str, market: str, price: float):
        """Cache a price with current timestamp"""
        key = (symbol, market)
        current_time = time.time()
        
        with self.lock:
            self.cache[key] = (price, current_time)
            logger.debug(f"Cached price for {symbol}.{market}: {price}")
    
    def clear_expired(self):
        """Remove all expired entries"""
        current_time = time.time()
        expired_keys = []
        
        with self.lock:
            for key, (price, timestamp) in self.cache.items():
                if current_time - timestamp >= self.ttl_seconds:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.cache[key]
        
        if expired_keys:
            logger.debug(f"Cleared {len(expired_keys)} expired cache entries")
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        current_time = time.time()
        total_entries = 0
        valid_entries = 0
        
        with self.lock:
            total_entries = len(self.cache)
            for price, timestamp in self.cache.values():
                if current_time - timestamp < self.ttl_seconds:
                    valid_entries += 1
        
        return {
            "total_entries": total_entries,
            "valid_entries": valid_entries,
            "ttl_seconds": self.ttl_seconds
        }


# Global price cache instance
price_cache = PriceCache(ttl_seconds=30)  # Cache prices for 30 seconds


def get_cached_price(symbol: str, market: str = "CRYPTO") -> Optional[float]:
    """Get price from cache if available"""
    return price_cache.get(symbol, market)


def cache_price(symbol: str, market: str, price: float):
    """Cache a price"""
    price_cache.set(symbol, market, price)


def clear_expired_prices():
    """Clear expired price entries"""
    price_cache.clear_expired()


def get_price_cache_stats() -> Dict:
    """Get cache statistics"""
    return price_cache.get_cache_stats()