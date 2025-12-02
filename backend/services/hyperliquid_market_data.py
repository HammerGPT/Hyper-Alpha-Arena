"""
Hyperliquid market data service using CCXT and native API
"""
import ccxt
import logging
import requests
import threading
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import time

logger = logging.getLogger(__name__)


class PriceCache:
    """Thread-safe price cache with TTL for Hyperliquid prices"""
    
    def __init__(self, ttl_seconds: float = 2.0):
        self._cache: Dict[str, float] = {}
        self._last_update: float = 0
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._environment = "mainnet"
    
    def set_environment(self, environment: str):
        """Set the environment for API calls"""
        with self._lock:
            if self._environment != environment:
                self._environment = environment
                self._cache.clear()
                self._last_update = 0
    
    def get_price(self, symbol: str) -> Optional[float]:
        """Get price for a symbol, refreshing cache if needed"""
        symbol_upper = symbol.upper().replace("/USDC", "").replace(":USDC", "").replace("/USD", "")
        
        with self._lock:
            current_time = time.time()
            
            # Check if cache is still valid
            if current_time - self._last_update < self._ttl and symbol_upper in self._cache:
                return self._cache.get(symbol_upper)
        
        # Cache expired or symbol not found, refresh
        self._refresh_cache()
        
        with self._lock:
            return self._cache.get(symbol_upper)
    
    def get_all_prices(self) -> Dict[str, float]:
        """Get all cached prices, refreshing if needed"""
        with self._lock:
            current_time = time.time()
            if current_time - self._last_update < self._ttl:
                return self._cache.copy()
        
        self._refresh_cache()
        
        with self._lock:
            return self._cache.copy()
    
    def _refresh_cache(self):
        """Refresh the price cache from Hyperliquid API"""
        try:
            # Use environment-specific API endpoint
            if self._environment == "testnet":
                api_url = "https://api.hyperliquid-testnet.xyz/info"
            else:
                api_url = "https://api.hyperliquid.xyz/info"
            
            response = requests.post(
                api_url,
                json={"type": "allMids"},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            with self._lock:
                self._cache.clear()
                if isinstance(data, dict):
                    for symbol, price_str in data.items():
                        try:
                            self._cache[symbol.upper()] = float(price_str)
                        except (ValueError, TypeError):
                            continue
                
                self._last_update = time.time()
                logger.debug(f"Price cache refreshed with {len(self._cache)} symbols")
                
        except Exception as e:
            logger.error(f"Failed to refresh price cache: {e}")


# Global price cache instances per environment
_price_caches: Dict[str, PriceCache] = {}


def get_price_cache(environment: str = "mainnet") -> PriceCache:
    """Get or create price cache for environment"""
    if environment not in _price_caches:
        cache = PriceCache(ttl_seconds=2.0)
        cache.set_environment(environment)
        _price_caches[environment] = cache
    return _price_caches[environment]

class HyperliquidClient:
    def __init__(self, environment: str = "mainnet"):
        self.environment = environment
        self.exchange = None
        self._initialize_exchange()

    def _initialize_exchange(self):
        """Initialize CCXT Hyperliquid exchange"""
        try:
            # Dynamic sandbox mode based on environment
            sandbox_mode = self.environment == "testnet"

            self.exchange = ccxt.hyperliquid({
                'sandbox': sandbox_mode,  # Dynamic based on environment
                'enableRateLimit': True,
                'options': {
                    'fetchMarkets': {
                        'hip3': {
                            'dex': []  # Empty list to skip HIP3 DEX markets (we only need perp markets)
                        }
                    }
                }
            })
            self._disable_hip3_markets()
            logger.info(f"Hyperliquid exchange initialized successfully for {self.environment} environment")
        except Exception as e:
            logger.error(f"Failed to initialize Hyperliquid exchange for {self.environment}: {e}")
            raise

    def _disable_hip3_markets(self) -> None:
        """Ensure HIP3 market fetching is disabled."""
        try:
            fetch_markets_options = self.exchange.options.setdefault('fetchMarkets', {})
            hip3_options = fetch_markets_options.setdefault('hip3', {})
            hip3_options['enabled'] = False
            hip3_options['dex'] = []
        except Exception as options_error:
            logger.debug(f"Unable to update HIP3 fetch options: {options_error}")

        if hasattr(self.exchange, 'fetch_hip3_markets'):
            def _skip_hip3_markets(exchange_self, params=None):
                logger.debug("Skipping HIP3 market fetch in market data client")
                return []
            self.exchange.fetch_hip3_markets = _skip_hip3_markets.__get__(self.exchange, type(self.exchange))
            logger.info("HIP3 market fetch disabled for market data client")

    def get_last_price(self, symbol: str) -> Optional[float]:
        """Get the last price for a symbol using native API with caching"""
        try:
            # Try native API cache first (faster, more symbols)
            cache = get_price_cache(self.environment)
            price = cache.get_price(symbol)
            
            if price is not None:
                logger.debug(f"Got price for {symbol} from cache: {price}")
                return price
            
            # Fallback to CCXT for symbols not in native API
            if not self.exchange:
                self._initialize_exchange()

            formatted_symbol = self._format_symbol(symbol)
            ticker = self.exchange.fetch_ticker(formatted_symbol)
            price = ticker['last']

            logger.info(f"Got price for {formatted_symbol} from CCXT: {price}")
            return float(price) if price else None

        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
            return None

    def get_ticker_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get complete ticker data using Hyperliquid native API"""
        try:
            import requests

            # Use environment-specific API endpoint
            if self.environment == "testnet":
                api_url = "https://api.hyperliquid-testnet.xyz/info"
            else:
                api_url = "https://api.hyperliquid.xyz/info"

            # Use Hyperliquid native API for complete market data
            response = requests.post(
                api_url,
                json={"type": "metaAndAssetCtxs"},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list) or len(data) < 2:
                raise Exception("Invalid API response structure")

            # Find symbol index in universe (meta data)
            symbol_upper = symbol.upper()
            symbol_index = None

            if isinstance(data[0], dict) and 'universe' in data[0]:
                for i, asset_meta in enumerate(data[0]['universe']):
                    if isinstance(asset_meta, dict):
                        asset_name = asset_meta.get('name', '').upper()
                        if asset_name == symbol_upper or asset_name == symbol_upper.replace('/', ''):
                            symbol_index = i
                            break

            if symbol_index is None or symbol_index >= len(data[1]):
                # Fallback to CCXT for unsupported symbols
                return self._get_ccxt_ticker_fallback(symbol)

            # Get asset data by index
            asset_data = data[1][symbol_index]
            if not isinstance(asset_data, dict):
                return self._get_ccxt_ticker_fallback(symbol)

            # Extract data from Hyperliquid API
            mark_px = float(asset_data.get('markPx', 0))
            oracle_px = float(asset_data.get('oraclePx', 0))
            prev_day_px = float(asset_data.get('prevDayPx', 0))
            day_ntl_vlm = float(asset_data.get('dayNtlVlm', 0))
            open_interest = float(asset_data.get('openInterest', 0))
            funding_rate = float(asset_data.get('funding', 0))

            # Calculate 24h change
            change_24h = mark_px - prev_day_px if prev_day_px else 0
            percentage_24h = (change_24h / prev_day_px * 100) if prev_day_px else 0

            # Convert open interest to USD value (OI * price)
            open_interest_usd = open_interest * mark_px

            result = {
                'symbol': symbol,
                'price': mark_px,
                'oracle_price': oracle_px,
                'change24h': change_24h,
                'volume24h': day_ntl_vlm,
                'percentage24h': percentage_24h,
                'open_interest': open_interest_usd,
                'funding_rate': funding_rate,
            }

            logger.info(f"Got Hyperliquid ticker for {symbol}: price={result['price']}, change24h={result['change24h']:.2f}")
            return result

        except Exception as e:
            logger.error(f"Error fetching Hyperliquid ticker for {symbol}: {e}")
            # Fallback to CCXT
            return self._get_ccxt_ticker_fallback(symbol)

    def _get_ccxt_ticker_fallback(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fallback to CCXT ticker for unsupported symbols"""
        try:
            if not self.exchange:
                self._initialize_exchange()

            formatted_symbol = self._format_symbol(symbol)
            ticker = self.exchange.fetch_ticker(formatted_symbol)

            result = {
                'symbol': symbol,
                'price': float(ticker['last']) if ticker['last'] else 0,
                'change24h': float(ticker['change']) if ticker['change'] else 0,
                'volume24h': float(ticker['baseVolume']) if ticker['baseVolume'] else 0,
                'percentage24h': float(ticker['percentage']) if ticker['percentage'] else 0,
            }
            return result
        except Exception as e:
            logger.error(f"CCXT fallback failed for {symbol}: {e}")
            return None

    def check_symbol_tradability(self, symbol: str) -> bool:
        """
        Check if a symbol is tradable (can fetch price data).

        This method is designed for validation purposes during symbol refresh
        and won't log errors for invalid symbols.

        Returns:
            True if symbol can fetch valid price data, False otherwise
        """
        try:
            if not self.exchange:
                self._initialize_exchange()

            formatted_symbol = self._format_symbol(symbol)
            ticker = self.exchange.fetch_ticker(formatted_symbol)
            price = ticker['last']

            is_valid = price is not None and price > 0
            if is_valid:
                logger.debug(f"Symbol {symbol} is tradable (price: {price})")
            return is_valid

        except Exception:
            # Silently return False for invalid symbols during validation
            return False

    def get_kline_data(self, symbol: str, period: str = '1d', count: int = 100, persist: bool = True) -> List[Dict[str, Any]]:
        """Get kline/candlestick data for a symbol"""
        try:
            if not self.exchange:
                self._initialize_exchange()

            formatted_symbol = self._format_symbol(symbol)

            # Map period to CCXT timeframe (Hyperliquid supported)
            timeframe_map = {
                '1m': '1m',
                '3m': '3m',
                '5m': '5m',
                '15m': '15m',
                '30m': '30m',
                '1h': '1h',
                '2h': '2h',
                '4h': '4h',
                '8h': '8h',
                '12h': '12h',
                '1d': '1d',
                '3d': '3d',
                '1w': '1w',
                '1M': '1M',
            }
            timeframe = timeframe_map.get(period, '1d')

            # Fetch OHLCV data
            ohlcv = self.exchange.fetch_ohlcv(formatted_symbol, timeframe, limit=count)

            # Convert to our format
            klines = []
            for candle in ohlcv:
                timestamp_ms = candle[0]
                open_price = candle[1]
                high_price = candle[2]
                low_price = candle[3]
                close_price = candle[4]
                volume = candle[5]

                # Calculate change
                change = close_price - open_price if open_price else 0
                percent = (change / open_price * 100) if open_price else 0

                klines.append({
                    'timestamp': int(timestamp_ms / 1000),  # Convert to seconds
                    'datetime': datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat(),
                    'open': float(open_price) if open_price else None,
                    'high': float(high_price) if high_price else None,
                    'low': float(low_price) if low_price else None,
                    'close': float(close_price) if close_price else None,
                    'volume': float(volume) if volume else None,
                    'amount': float(volume * close_price) if volume and close_price else None,
                    'chg': float(change),
                    'percent': float(percent),
                })

            # Auto-persist data to database (边用边存)
            if persist and klines:
                try:
                    self._persist_kline_data(symbol, period, klines)
                except Exception as persist_error:
                    logger.warning(f"Failed to persist kline data for {symbol}: {persist_error}")

            logger.info(f"Got {len(klines)} klines for {formatted_symbol}")
            return klines

        except Exception as e:
            logger.error(f"Error fetching klines for {symbol}: {e}")
            return []

    def _persist_kline_data(self, symbol: str, period: str, klines: List[Dict[str, Any]]):
        """Persist kline data to database

        IMPORTANT DESIGN DECISION:
        Only mainnet K-line data is persisted to database.
        Testnet data is fetched in real-time on-demand and NOT stored.

        This design ensures:
        1. Database contains consistent historical data (mainnet only)
        2. Testnet trading uses real-time API calls without database overhead
        3. No environment mixing in stored K-line data
        """
        # CRITICAL: Only persist mainnet data per design specification
        if self.environment != "mainnet":
            logger.debug(f"Skipping K-line persistence for {symbol} {period} (environment={self.environment}, only mainnet data is stored)")
            return

        try:
            from database.connection import SessionLocal
            from repositories.kline_repo import KlineRepository

            db = SessionLocal()
            try:
                kline_repo = KlineRepository(db)
                result = kline_repo.save_kline_data(
                    symbol=symbol,
                    market="CRYPTO",
                    period=period,
                    kline_data=klines,
                    exchange="hyperliquid",
                    environment="mainnet"  # Always store as mainnet per design
                )
                logger.debug(f"Persisted {result['total']} kline records for {symbol} {period}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error persisting kline data: {e}")
            raise

    def get_market_status(self, symbol: str) -> Dict[str, Any]:
        """Get market status for a symbol"""
        try:
            if not self.exchange:
                self._initialize_exchange()
            
            formatted_symbol = self._format_symbol(symbol)
            
            # Hyperliquid is 24/7, but we can check if the market exists
            markets = self.exchange.load_markets()
            market_exists = formatted_symbol in markets
            
            status = {
                'market_status': 'OPEN' if market_exists else 'CLOSED',
                'is_trading': market_exists,
                'symbol': formatted_symbol,
                'exchange': 'Hyperliquid',
                'market_type': 'crypto',
            }
            
            if market_exists:
                market_info = markets[formatted_symbol]
                status.update({
                    'base_currency': market_info.get('base'),
                    'quote_currency': market_info.get('quote'),
                    'active': market_info.get('active', True),
                })
            
            logger.info(f"Market status for {formatted_symbol}: {status['market_status']}")
            return status
            
        except Exception as e:
            logger.error(f"Error getting market status for {symbol}: {e}")
            return {
                'market_status': 'ERROR',
                'is_trading': False,
                'error': str(e)
            }

    def get_all_symbols(self) -> List[str]:
        """Get all available trading symbols"""
        try:
            if not self.exchange:
                self._initialize_exchange()
            
            markets = self.exchange.load_markets()
            symbols = list(markets.keys())
            
            # Filter for USDC pairs (both spot and perpetual)
            usdc_symbols = [s for s in symbols if '/USDC' in s]
            
            # Prioritize mainstream cryptos (perpetual swaps) and popular spot pairs
            mainstream_perps = [s for s in usdc_symbols if any(crypto in s for crypto in ['BTC/', 'ETH/', 'SOL/', 'DOGE/', 'BNB/', 'XRP/'])]
            other_symbols = [s for s in usdc_symbols if s not in mainstream_perps]
            
            # Return mainstream first, then others
            result = mainstream_perps + other_symbols[:50]
            
            logger.info(f"Found {len(usdc_symbols)} USDC trading pairs, returning {len(result)}")
            return result
            
        except Exception as e:
            logger.error(f"Error getting symbols: {e}")
            return ['BTC/USD', 'ETH/USD', 'SOL/USD']  # Fallback popular pairs

    def _format_symbol(self, symbol: str) -> str:
        """Format symbol for CCXT (e.g., 'BTC' -> 'BTC/USDC:USDC')
        
        Hyperliquid primarily offers perpetual contracts, so we default to
        perpetual format for all symbols. The exchange will return an error
        if the symbol doesn't exist.
        """
        if '/' in symbol and ':' in symbol:
            return symbol
        elif '/' in symbol:
            # If it's BTC/USDC, convert to BTC/USDC:USDC for Hyperliquid
            return f"{symbol}:USDC"
        
        # For single symbols like 'BTC', always use perpetual swap format
        # Hyperliquid is primarily a perpetual exchange, so all tradable
        # assets should be available as perpetuals
        symbol_upper = symbol.upper()
        return f"{symbol_upper}/USDC:USDC"


# Client factory functions
_client_cache = {}

def create_hyperliquid_client(environment: str = "mainnet") -> HyperliquidClient:
    """Create a new HyperliquidClient instance for the specified environment"""
    return HyperliquidClient(environment=environment)

def get_hyperliquid_client_for_environment(environment: str = "mainnet") -> HyperliquidClient:
    """Get cached HyperliquidClient instance for the specified environment"""
    if environment not in _client_cache:
        _client_cache[environment] = create_hyperliquid_client(environment)
    return _client_cache[environment]

# Backward compatibility - default to mainnet
def get_default_hyperliquid_client() -> HyperliquidClient:
    """Get default HyperliquidClient (mainnet) for backward compatibility"""
    return get_hyperliquid_client_for_environment("mainnet")


def get_last_price_from_hyperliquid(symbol: str, environment: str = "mainnet") -> Optional[float]:
    """Get last price from Hyperliquid"""
    client = get_hyperliquid_client_for_environment(environment)
    return client.get_last_price(symbol)


def get_kline_data_from_hyperliquid(symbol: str, period: str = '1d', count: int = 100, persist: bool = True, environment: str = "mainnet") -> List[Dict[str, Any]]:
    """Get kline data from Hyperliquid"""
    client = get_hyperliquid_client_for_environment(environment)
    return client.get_kline_data(symbol, period, count, persist)


def get_market_status_from_hyperliquid(symbol: str, environment: str = "mainnet") -> Dict[str, Any]:
    """Get market status from Hyperliquid"""
    client = get_hyperliquid_client_for_environment(environment)
    return client.get_market_status(symbol)


def get_all_symbols_from_hyperliquid(environment: str = "mainnet") -> List[str]:
    """Get all available symbols from Hyperliquid"""
    client = get_hyperliquid_client_for_environment(environment)
    return client.get_all_symbols()


def get_ticker_data_from_hyperliquid(symbol: str, environment: str = "mainnet") -> Optional[Dict[str, Any]]:
    """Get complete ticker data from Hyperliquid"""
    client = get_hyperliquid_client_for_environment(environment)
    return client.get_ticker_data(symbol)
