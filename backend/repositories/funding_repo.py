"""
Perpetual funding rate repository module
Provides funding rate data database operations
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from typing import List, Optional
from database.models import PerpFunding
from database.connection import get_db
import time


class FundingRepository:
    def __init__(self, db: Session):
        self.db = db

    def save_funding_data(self, exchange: str, symbol: str, funding_list: List[dict]) -> dict:
        """
        Save funding rate data to database (using upsert mode)

        Args:
            exchange: Exchange name (hyperliquid, binance, etc.)
            symbol: Trading symbol
            funding_list: List of funding rate data

        Returns:
            Save result dict, contains inserted and updated counts
        """
        inserted_count = 0
        updated_count = 0

        for item in funding_list:
            timestamp = item.get('timestamp')
            if not timestamp:
                continue

            # Check if record with same timestamp already exists
            existing = self.db.query(PerpFunding).filter(
                and_(
                    PerpFunding.exchange == exchange,
                    PerpFunding.symbol == symbol,
                    PerpFunding.timestamp == timestamp
                )
            ).first()

            funding_data_dict = {
                'exchange': exchange,
                'symbol': symbol,
                'timestamp': timestamp,
                'funding_rate': item.get('funding_rate', 0),
                'mark_price': item.get('mark_price')
            }

            if existing:
                # Update existing record
                for key, value in funding_data_dict.items():
                    if key not in ['exchange', 'symbol', 'timestamp']:  # Don't update primary key fields
                        setattr(existing, key, value)
                updated_count += 1
            else:
                # Insert new record
                funding_record = PerpFunding(**funding_data_dict)
                self.db.add(funding_record)
                inserted_count += 1

        if inserted_count > 0 or updated_count > 0:
            self.db.commit()

        return {
            'inserted': inserted_count,
            'updated': updated_count,
            'total': inserted_count + updated_count
        }

    def get_funding_history(self, exchange: str, symbol: str, start_ts: int = None, end_ts: int = None, limit: int = 100) -> List[PerpFunding]:
        """
        Get funding rate history

        Args:
            exchange: Exchange name
            symbol: Trading symbol
            start_ts: Start timestamp (Unix timestamp in seconds)
            end_ts: End timestamp (Unix timestamp in seconds)
            limit: Limit count

        Returns:
            Funding rate data list
        """
        query = self.db.query(PerpFunding).filter(
            and_(
                PerpFunding.exchange == exchange,
                PerpFunding.symbol == symbol
            )
        )

        if start_ts:
            query = query.filter(PerpFunding.timestamp >= start_ts)
        if end_ts:
            query = query.filter(PerpFunding.timestamp <= end_ts)

        return query.order_by(desc(PerpFunding.timestamp)).limit(limit).all()

    def get_latest_funding(self, exchange: str, symbol: str) -> Optional[PerpFunding]:
        """
        Get the latest funding rate for a symbol

        Args:
            exchange: Exchange name
            symbol: Trading symbol

        Returns:
            Latest funding rate record or None
        """
        return self.db.query(PerpFunding).filter(
            and_(
                PerpFunding.exchange == exchange,
                PerpFunding.symbol == symbol
            )
        ).order_by(desc(PerpFunding.timestamp)).first()

    def delete_old_funding_data(self, exchange: str, symbol: str, keep_days: int = 90):
        """
        Delete old funding rate data

        Args:
            exchange: Exchange name
            symbol: Trading symbol
            keep_days: Days to keep (default 90 days for funding rates)
        """
        cutoff_timestamp = int(time.time() - keep_days * 24 * 3600)

        self.db.query(PerpFunding).filter(
            and_(
                PerpFunding.exchange == exchange,
                PerpFunding.symbol == symbol,
                PerpFunding.timestamp < cutoff_timestamp
            )
        ).delete()

        self.db.commit()

    def get_funding_stats(self, exchange: str, symbol: str, days: int = 30) -> dict:
        """
        Get funding rate statistics for the past N days

        Args:
            exchange: Exchange name
            symbol: Trading symbol
            days: Number of days to analyze

        Returns:
            Statistics dict with avg, min, max funding rates
        """
        cutoff_timestamp = int(time.time() - days * 24 * 3600)

        from sqlalchemy import func
        result = self.db.query(
            func.avg(PerpFunding.funding_rate).label('avg_rate'),
            func.min(PerpFunding.funding_rate).label('min_rate'),
            func.max(PerpFunding.funding_rate).label('max_rate'),
            func.count(PerpFunding.id).label('count')
        ).filter(
            and_(
                PerpFunding.exchange == exchange,
                PerpFunding.symbol == symbol,
                PerpFunding.timestamp >= cutoff_timestamp
            )
        ).first()

        if result and result.count > 0:
            return {
                'avg_funding_rate': float(result.avg_rate or 0),
                'min_funding_rate': float(result.min_rate or 0),
                'max_funding_rate': float(result.max_rate or 0),
                'sample_count': result.count,
                'days': days
            }
        else:
            return {
                'avg_funding_rate': 0,
                'min_funding_rate': 0,
                'max_funding_rate': 0,
                'sample_count': 0,
                'days': days
            }