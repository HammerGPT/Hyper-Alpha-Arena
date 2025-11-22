"""
Price sample repository module
Provides price sampling data database operations for persistent sampling pools
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func
from typing import List, Optional
from database.models import PriceSample
from database.connection import get_db
from datetime import datetime, timedelta
import time


class SampleRepository:
    def __init__(self, db: Session):
        self.db = db

    def save_samples(self, exchange: str, symbol: str, samples: List[dict], account_id: int = None) -> dict:
        """
        Save price samples to database

        Args:
            exchange: Exchange name (hyperliquid, binance, etc.)
            symbol: Trading symbol
            samples: List of price sample data
            account_id: Optional account ID for tracking

        Returns:
            Save result dict, contains inserted count
        """
        inserted_count = 0

        for sample in samples:
            price = sample.get('price')
            sample_time = sample.get('sample_time')

            if not price or not sample_time:
                continue

            # Convert sample_time to datetime if it's a timestamp
            if isinstance(sample_time, (int, float)):
                sample_time = datetime.fromtimestamp(sample_time)

            sample_data = {
                'exchange': exchange,
                'symbol': symbol,
                'price': price,
                'sample_time': sample_time,
                'account_id': account_id
            }

            # Insert new record (no upsert needed for samples, they're time-series data)
            sample_record = PriceSample(**sample_data)
            self.db.add(sample_record)
            inserted_count += 1

        if inserted_count > 0:
            self.db.commit()

        return {
            'inserted': inserted_count,
            'total': inserted_count
        }

    def save_sample(self, exchange: str, symbol: str, price: float, account_id: int = None) -> bool:
        """
        Save a single price sample

        Args:
            exchange: Exchange name
            symbol: Trading symbol
            price: Price value
            account_id: Optional account ID

        Returns:
            True if saved successfully
        """
        try:
            sample_record = PriceSample(
                exchange=exchange,
                symbol=symbol,
                price=price,
                sample_time=datetime.now(),
                account_id=account_id
            )
            self.db.add(sample_record)
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            print(f"Failed to save sample: {e}")
            return False

    def get_recent_samples(self, exchange: str, symbol: str, count: int = 10, account_id: int = None) -> List[PriceSample]:
        """
        Get recent price samples

        Args:
            exchange: Exchange name
            symbol: Trading symbol
            count: Number of samples to retrieve
            account_id: Optional account ID filter

        Returns:
            List of recent price samples
        """
        query = self.db.query(PriceSample).filter(
            and_(
                PriceSample.exchange == exchange,
                PriceSample.symbol == symbol
            )
        )

        if account_id is not None:
            query = query.filter(PriceSample.account_id == account_id)

        return query.order_by(desc(PriceSample.sample_time)).limit(count).all()

    def restore_samples(self, exchange: str, symbol: str, since_minutes: int = 60, account_id: int = None) -> List[dict]:
        """
        Restore samples from database for service restart recovery

        Args:
            exchange: Exchange name
            symbol: Trading symbol
            since_minutes: How many minutes back to restore
            account_id: Optional account ID filter

        Returns:
            List of sample dicts suitable for sampling pool restoration
        """
        since_time = datetime.now() - timedelta(minutes=since_minutes)

        query = self.db.query(PriceSample).filter(
            and_(
                PriceSample.exchange == exchange,
                PriceSample.symbol == symbol,
                PriceSample.sample_time >= since_time
            )
        )

        if account_id is not None:
            query = query.filter(PriceSample.account_id == account_id)

        samples = query.order_by(PriceSample.sample_time).all()

        # Convert to dict format for sampling pool
        return [
            {
                'price': float(sample.price),
                'sample_time': sample.sample_time.timestamp(),
                'datetime': sample.sample_time
            }
            for sample in samples
        ]

    def get_sample_stats(self, exchange: str, symbol: str, hours: int = 24, account_id: int = None) -> dict:
        """
        Get sampling statistics for the past N hours

        Args:
            exchange: Exchange name
            symbol: Trading symbol
            hours: Number of hours to analyze
            account_id: Optional account ID filter

        Returns:
            Statistics dict with count, avg, min, max prices
        """
        since_time = datetime.now() - timedelta(hours=hours)

        query = self.db.query(
            func.count(PriceSample.id).label('count'),
            func.avg(PriceSample.price).label('avg_price'),
            func.min(PriceSample.price).label('min_price'),
            func.max(PriceSample.price).label('max_price')
        ).filter(
            and_(
                PriceSample.exchange == exchange,
                PriceSample.symbol == symbol,
                PriceSample.sample_time >= since_time
            )
        )

        if account_id is not None:
            query = query.filter(PriceSample.account_id == account_id)

        result = query.first()

        if result and result.count > 0:
            return {
                'sample_count': result.count,
                'avg_price': float(result.avg_price or 0),
                'min_price': float(result.min_price or 0),
                'max_price': float(result.max_price or 0),
                'hours': hours
            }
        else:
            return {
                'sample_count': 0,
                'avg_price': 0,
                'min_price': 0,
                'max_price': 0,
                'hours': hours
            }

    def cleanup_old_samples(self, exchange: str, symbol: str, keep_hours: int = 72, account_id: int = None):
        """
        Clean up old sample data to prevent database bloat

        Args:
            exchange: Exchange name
            symbol: Trading symbol
            keep_hours: Hours of data to keep (default 72 hours)
            account_id: Optional account ID filter
        """
        cutoff_time = datetime.now() - timedelta(hours=keep_hours)

        query = self.db.query(PriceSample).filter(
            and_(
                PriceSample.exchange == exchange,
                PriceSample.symbol == symbol,
                PriceSample.sample_time < cutoff_time
            )
        )

        if account_id is not None:
            query = query.filter(PriceSample.account_id == account_id)

        deleted_count = query.delete()
        self.db.commit()

        return deleted_count

    def get_sampling_rate(self, exchange: str, symbol: str, minutes: int = 60, account_id: int = None) -> float:
        """
        Calculate the actual sampling rate (samples per minute)

        Args:
            exchange: Exchange name
            symbol: Trading symbol
            minutes: Time window to analyze
            account_id: Optional account ID filter

        Returns:
            Samples per minute rate
        """
        since_time = datetime.now() - timedelta(minutes=minutes)

        query = self.db.query(func.count(PriceSample.id)).filter(
            and_(
                PriceSample.exchange == exchange,
                PriceSample.symbol == symbol,
                PriceSample.sample_time >= since_time
            )
        )

        if account_id is not None:
            query = query.filter(PriceSample.account_id == account_id)

        count = query.scalar() or 0
        return count / minutes if minutes > 0 else 0