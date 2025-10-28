"""
K-line data repository module
Provides K-line data database operations
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from database.models import cryptoKline
from database.connection import get_db


class KlineRepository:
    def __init__(self, db: Session):
        self.db = db

    def save_kline_data(self, symbol: str, market: str, period: str, kline_data: List[dict]) -> dict:
        """
        Save K-line data to database (using upsert mode)

        Args:
            symbol: Stock symbol
            market: Market symbol
            period: Time period
            kline_data: K-line data list

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
            existing = self.db.query(cryptoKline).filter(
                and_(
                    cryptoKline.symbol == symbol,
                    cryptoKline.market == market,
                    cryptoKline.period == period,
                    cryptoKline.timestamp == timestamp
                )
            ).first()
            
            kline_data_dict = {
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
                    if key not in ['symbol', 'market', 'period', 'timestamp']:  # Don't update primary key fields
                        setattr(existing, key, value)
                updated_count += 1
            else:
                # Insert new record
                kline_record = cryptoKline(**kline_data_dict)
                self.db.add(kline_record)
                inserted_count += 1
        
        if inserted_count > 0 or updated_count > 0:
            self.db.commit()
            
        return {
            'inserted': inserted_count,
            'updated': updated_count,
            'total': inserted_count + updated_count
        }

    def get_kline_data(self, symbol: str, market: str, period: str, limit: int = 100) -> List[cryptoKline]:
        """
        Get K-line data

        Args:
            symbol: Stock symbol
            market: Market symbol
            period: Time period
            limit: Limit count

        Returns:
            K-line data list
        """
        return self.db.query(cryptoKline).filter(
            and_(
                cryptoKline.symbol == symbol,
                cryptoKline.market == market,
                cryptoKline.period == period
            )
        ).order_by(cryptoKline.timestamp.desc()).limit(limit).all()

    def delete_old_kline_data(self, symbol: str, market: str, period: str, keep_days: int = 30):
        """
        Delete old K-line data

        Args:
            symbol: Stock symbol
            market: Market symbol
            period: Time period
            keep_days: Days to keep
        """
        import time
        cutoff_timestamp = int((time.time() - keep_days * 24 * 3600) * 1000)
        
        self.db.query(cryptoKline).filter(
            and_(
                cryptoKline.symbol == symbol,
                cryptoKline.market == market,
                cryptoKline.period == period,
                cryptoKline.timestamp < cutoff_timestamp
            )
        ).delete()
        
        self.db.commit()