"""
Hyperliquid market data service using CCXT
"""
import ccxt
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import time

logger = logging.getLogger(__name__)

class HyperliquidClient:
    def __init__(self):
        self.exchange = None
        self._initialize_exchange()
    
    def _initialize_exchange(self):
        """Initialize CCXT Hyperliquid exchange"""
        try:
            self.exchange = ccxt.hyperliquid({
                'sandbox': False,  # Set to True for testnet
                'enableRateLimit': True,
            })
            logger.info("Hyperliquid exchange initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Hyperliquid exchange: {e}")
            raise

    def get_last_price(self, symbol: str) -> Optional[float]:
        """Get the last price for a symbol"""
        try:
            if not self.exchange:
                self._initialize_exchange()

            # Ensure symbol is in CCXT format (e.g., 'BTC/USD')
            formatted_symbol = self._format_symbol(symbol)

            ticker = self.exchange.fetch_ticker(formatted_symbol)
            price = ticker['last']

            logger.info(f"Got price for {formatted_symbol}: {price}")
            return float(price) if price else None

        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
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

    def get_kline_data(self, symbol: str, period: str = '1d', count: int = 100) -> List[Dict[str, Any]]:
        """Get kline/candlestick data for a symbol"""
        try:
            if not self.exchange:
                self._initialize_exchange()
            
            formatted_symbol = self._format_symbol(symbol)
            
            # Map period to CCXT timeframe
            timeframe_map = {
                '1m': '1m',
                '5m': '5m', 
                '15m': '15m',
                '30m': '30m',
                '1h': '1h',
                '1d': '1d',
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
                    'datetime_str': datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat(),
                    'open': float(open_price) if open_price else None,
                    'high': float(high_price) if high_price else None,
                    'low': float(low_price) if low_price else None,
                    'close': float(close_price) if close_price else None,
                    'volume': float(volume) if volume else None,
                    'amount': float(volume * close_price) if volume and close_price else None,
                    'change': float(change),
                    'percent': float(percent),
                })
            
            logger.info(f"Got {len(klines)} klines for {formatted_symbol}")
            return klines
            
        except Exception as e:
            logger.error(f"Error fetching klines for {symbol}: {e}")
            return []

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
        """Format symbol for CCXT (e.g., 'BTC' -> 'BTC/USDC:USDC')"""
        if '/' in symbol and ':' in symbol:
            return symbol
        elif '/' in symbol:
            # If it's BTC/USDC, convert to BTC/USDC:USDC for Hyperliquid
            return f"{symbol}:USDC"
        
        # For single symbols like 'BTC', check if it's a mainstream crypto
        symbol_upper = symbol.upper()
        mainstream_cryptos = ['BTC', 'ETH', 'SOL', 'DOGE', 'BNB', 'XRP']
        
        if symbol_upper in mainstream_cryptos:
            # Use perpetual swap format for mainstream cryptos
            return f"{symbol_upper}/USDC:USDC"
        else:
            # Use spot format for other cryptos
            return f"{symbol_upper}/USDC"


# Global client instance
hyperliquid_client = HyperliquidClient()


def get_last_price_from_hyperliquid(symbol: str) -> Optional[float]:
    """Get last price from Hyperliquid"""
    return hyperliquid_client.get_last_price(symbol)


def get_kline_data_from_hyperliquid(symbol: str, period: str = '1d', count: int = 100) -> List[Dict[str, Any]]:
    """Get kline data from Hyperliquid"""
    return hyperliquid_client.get_kline_data(symbol, period, count)


def get_market_status_from_hyperliquid(symbol: str) -> Dict[str, Any]:
    """Get market status from Hyperliquid"""
    return hyperliquid_client.get_market_status(symbol)


def get_all_symbols_from_hyperliquid() -> List[str]:
    """Get all available symbols from Hyperliquid"""
    return hyperliquid_client.get_all_symbols()