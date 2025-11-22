"""
K-line data repository module
Provides K-line data database operations
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text
from typing import List, Optional, Tuple
from database.models import CryptoKline
from database.connection import get_db
import time
import ccxt


class KlineRepository:
    def __init__(self, db: Session):
        self.db = db

    def save_kline_data(self, symbol: str, market: str, period: str, kline_data: List[dict], exchange: str = "hyperliquid") -> dict:
        """
        Save K-line data to database (using upsert mode)

        Args:
            symbol: Trading symbol
            market: Market symbol
            period: Time period
            kline_data: K-line data list
            exchange: Exchange name (hyperliquid, binance, etc.)

        Returns:
            Save result dict, contains inserted and updated counts
        """
        inserted_count = 0
        updated_count = 0
        
        for item in kline_data:
            timestamp = item.get('timestamp')
            if not timestamp:
                continue
                
            # Check if record with same timestamp already exists
            existing = self.db.query(CryptoKline).filter(
                and_(
                    CryptoKline.exchange == exchange,
                    CryptoKline.symbol == symbol,
                    CryptoKline.market == market,
                    CryptoKline.period == period,
                    CryptoKline.timestamp == timestamp
                )
            ).first()

            kline_data_dict = {
                'exchange': exchange,
                'symbol': symbol,
                'market': market,
                'period': period,
                'timestamp': timestamp,
                'datetime_str': item.get('datetime', ''),
                'open_price': item.get('open'),
                'high_price': item.get('high'),
                'low_price': item.get('low'),
                'close_price': item.get('close'),
                'volume': item.get('volume'),
                'amount': item.get('amount'),
                'change': item.get('chg'),
                'percent': item.get('percent')
            }

            if existing:
                # Update existing record
                for key, value in kline_data_dict.items():
                    if key not in ['exchange', 'symbol', 'market', 'period', 'timestamp']:  # Don't update primary key fields
                        setattr(existing, key, value)
                updated_count += 1
            else:
                # Insert new record
                kline_record = CryptoKline(**kline_data_dict)
                self.db.add(kline_record)
                inserted_count += 1
        
        if inserted_count > 0 or updated_count > 0:
            self.db.commit()
            
        return {
            'inserted': inserted_count,
            'updated': updated_count,
            'total': inserted_count + updated_count
        }

    def get_kline_data(self, symbol: str, market: str, period: str, limit: int = 100, exchange: str = "hyperliquid") -> List[CryptoKline]:
        """
        Get K-line data

        Args:
            symbol: Trading symbol
            market: Market symbol
            period: Time period
            limit: Limit count
            exchange: Exchange name

        Returns:
            K-line data list
        """
        return self.db.query(CryptoKline).filter(
            and_(
                CryptoKline.exchange == exchange,
                CryptoKline.symbol == symbol,
                CryptoKline.market == market,
                CryptoKline.period == period
            )
        ).order_by(CryptoKline.timestamp.desc()).limit(limit).all()

    def delete_old_kline_data(self, symbol: str, market: str, period: str, keep_days: int = 30, exchange: str = "hyperliquid"):
        """
        Delete old K-line data

        Args:
            symbol: Trading symbol
            market: Market symbol
            period: Time period
            keep_days: Days to keep
            exchange: Exchange name
        """
        cutoff_timestamp = int((time.time() - keep_days * 24 * 3600) * 1000)

        self.db.query(CryptoKline).filter(
            and_(
                CryptoKline.exchange == exchange,
                CryptoKline.symbol == symbol,
                CryptoKline.market == market,
                CryptoKline.period == period,
                CryptoKline.timestamp < cutoff_timestamp
            )
        ).delete()

        self.db.commit()

    def get_missing_ranges(self, exchange: str, symbol: str, period: str, start_ts: int, end_ts: int) -> List[Tuple[int, int]]:
        """
        Find missing time ranges in stored K-line data

        Args:
            exchange: Exchange name
            symbol: Trading symbol
            period: Time period (1m, 5m, 1h, etc.)
            start_ts: Start timestamp (Unix timestamp in seconds)
            end_ts: End timestamp (Unix timestamp in seconds)

        Returns:
            List of (start, end) timestamp tuples for missing ranges
        """
        # Convert period to seconds
        period_seconds = self._period_to_seconds(period)
        if not period_seconds:
            return [(start_ts, end_ts)]

        # Get existing timestamps in the range
        existing_data = self.db.query(CryptoKline.timestamp).filter(
            and_(
                CryptoKline.exchange == exchange,
                CryptoKline.symbol == symbol,
                CryptoKline.period == period,
                CryptoKline.timestamp >= start_ts,
                CryptoKline.timestamp <= end_ts
            )
        ).order_by(CryptoKline.timestamp).all()

        if not existing_data:
            return [(start_ts, end_ts)]

        existing_timestamps = [row[0] for row in existing_data]
        missing_ranges = []

        # Check for gaps
        current_ts = start_ts
        for ts in existing_timestamps:
            if ts > current_ts:
                missing_ranges.append((current_ts, ts - period_seconds))
            current_ts = max(current_ts, ts + period_seconds)

        # Check final gap
        if current_ts <= end_ts:
            missing_ranges.append((current_ts, end_ts))

        return missing_ranges

    def ensure_history(self, exchange: str, symbol: str, period: str, start_ts: int, end_ts: int) -> List[CryptoKline]:
        """
        Ensure K-line history is available for the given range, fetch missing data if needed

        Args:
            exchange: Exchange name
            symbol: Trading symbol
            period: Time period
            start_ts: Start timestamp (Unix timestamp in seconds)
            end_ts: End timestamp (Unix timestamp in seconds)

        Returns:
            Complete K-line data for the requested range
        """
        # Find missing ranges
        missing_ranges = self.get_missing_ranges(exchange, symbol, period, start_ts, end_ts)

        # Fetch missing data for each range
        for range_start, range_end in missing_ranges:
            try:
                self._fetch_and_store_range(exchange, symbol, period, range_start, range_end)
            except Exception as e:
                print(f"Failed to fetch data for {exchange}:{symbol} {period} [{range_start}-{range_end}]: {e}")

        # Return complete data
        return self.db.query(CryptoKline).filter(
            and_(
                CryptoKline.exchange == exchange,
                CryptoKline.symbol == symbol,
                CryptoKline.period == period,
                CryptoKline.timestamp >= start_ts,
                CryptoKline.timestamp <= end_ts
            )
        ).order_by(CryptoKline.timestamp).all()

    def _period_to_seconds(self, period: str) -> Optional[int]:
        """Convert period string to seconds"""
        period_map = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '30m': 1800,
            '1h': 3600,
            '4h': 14400,
            '1d': 86400
        }
        return period_map.get(period)

    def _fetch_and_store_range(self, exchange: str, symbol: str, period: str, start_ts: int, end_ts: int):
        """
        Fetch K-line data from exchange API and store to database

        This is a placeholder - actual implementation depends on exchange API
        """
        if exchange == "hyperliquid":
            # Use existing hyperliquid market data service
            from services.hyperliquid_market_data import HyperliquidMarketData
            market_data = HyperliquidMarketData()

            # Convert timestamps to milliseconds for API
            since_ms = start_ts * 1000
            limit = min(1000, (end_ts - start_ts) // self._period_to_seconds(period))

            # Fetch data (this would need to be implemented in HyperliquidMarketData)
            # kline_data = market_data.get_historical_klines(symbol, period, since_ms, limit)
            # self.save_kline_data(symbol, "CRYPTO", period, kline_data, exchange)
            pass
        else:
            raise NotImplementedError(f"Exchange {exchange} not supported yet")