"""
K线数据统一服务层 - 提供统一的数据操作接口
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

from database.connection import SessionLocal
from database.models import CryptoKline, UserExchangeConfig, KlineCollectionTask
from .kline_collectors import ExchangeDataSourceFactory, BaseKlineCollector, KlineData

logger = logging.getLogger(__name__)


class KlineDataService:
    """K线数据统一服务 - 启动时确定交易所，后续不再判断"""

    def __init__(self):
        self.exchange_id: Optional[str] = None
        self.collector: Optional[BaseKlineCollector] = None
        self._initialized = False

    async def initialize(self):
        """初始化服务 - 读取用户配置并确定交易所"""
        if self._initialized:
            return

        try:
            # 从数据库读取用户选择的交易所
            with SessionLocal() as db:
                config = db.query(UserExchangeConfig).filter(
                    UserExchangeConfig.user_id == 1
                ).first()

                if config:
                    self.exchange_id = config.selected_exchange
                else:
                    self.exchange_id = "hyperliquid"  # 默认值

            # 初始化对应的采集器
            self.collector = ExchangeDataSourceFactory.get_collector(self.exchange_id)
            self._initialized = True

            logger.info(f"KlineDataService initialized with exchange: {self.exchange_id}")

        except Exception as e:
            logger.error(f"Failed to initialize KlineDataService: {e}")
            # 使用默认配置
            self.exchange_id = "hyperliquid"
            self.collector = ExchangeDataSourceFactory.get_collector(self.exchange_id)
            self._initialized = True

    def _ensure_initialized(self):
        """确保服务已初始化"""
        if not self._initialized:
            raise RuntimeError("KlineDataService not initialized. Call initialize() first.")

    async def collect_current_kline(self, symbol: str, period: str = "1m") -> bool:
        """采集当前分钟的K线数据"""
        self._ensure_initialized()

        try:
            # 使用已确定的采集器获取数据
            kline_data = await self.collector.fetch_current_kline(symbol, period)
            if not kline_data:
                logger.warning(f"No kline data received for {symbol}")
                return False

            # 插入数据库（自动去重）
            return await self._insert_kline_data([kline_data])

        except Exception as e:
            logger.error(f"Failed to collect current kline for {symbol}: {e}")
            return False

    async def collect_historical_klines(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        period: str = "1m"
    ) -> int:
        """采集历史K线数据，返回成功插入的记录数"""
        self._ensure_initialized()

        try:
            # 使用已确定的采集器获取历史数据
            klines_data = await self.collector.fetch_historical_klines(
                symbol, start_time, end_time, period
            )

            if not klines_data:
                logger.warning(f"No historical klines received for {symbol}")
                return 0

            # 批量插入数据库
            success = await self._insert_kline_data(klines_data)
            return len(klines_data) if success else 0

        except Exception as e:
            logger.error(f"Failed to collect historical klines for {symbol}: {e}")
            return 0

    async def _insert_kline_data(self, klines_data: List[KlineData]) -> bool:
        """批量插入K线数据到数据库（自动去重）"""
        if not klines_data:
            return True

        try:
            with SessionLocal() as db:
                for kline in klines_data:
                    # Generate datetime_str from timestamp (UTC)
                    datetime_str = datetime.utcfromtimestamp(kline.timestamp).strftime('%Y-%m-%d %H:%M:%S')

                    # 使用原生SQL的ON CONFLICT DO NOTHING实现去重
                    db.execute(text("""
                        INSERT INTO crypto_klines (
                            exchange, symbol, market, timestamp, period, datetime_str,
                            open_price, high_price, low_price, close_price, volume, created_at
                        ) VALUES (
                            :exchange, :symbol, :market, :timestamp, :period, :datetime_str,
                            :open_price, :high_price, :low_price, :close_price, :volume, CURRENT_TIMESTAMP
                        ) ON CONFLICT (exchange, symbol, market, period, timestamp) DO NOTHING
                    """), {
                        'exchange': kline.exchange,
                        'symbol': kline.symbol,
                        'market': 'CRYPTO',
                        'timestamp': kline.timestamp,
                        'period': kline.period,
                        'datetime_str': datetime_str,
                        'open_price': kline.open_price,
                        'high_price': kline.high_price,
                        'low_price': kline.low_price,
                        'close_price': kline.close_price,
                        'volume': kline.volume
                    })

                db.commit()
                logger.debug(f"Inserted {len(klines_data)} klines for {klines_data[0].symbol}")
                return True

        except Exception as e:
            logger.error(f"Failed to insert kline data: {e}")
            return False

    async def get_data_coverage(self, symbols: List[str] = None) -> List[Dict[str, Any]]:
        """获取数据覆盖情况"""
        self._ensure_initialized()

        try:
            with SessionLocal() as db:
                query = """
                    SELECT * FROM kline_coverage_stats
                    WHERE exchange = :exchange
                """
                params = {'exchange': self.exchange_id}

                if symbols:
                    query += " AND symbol = ANY(:symbols)"
                    params['symbols'] = symbols

                query += " ORDER BY symbol, period"

                result = db.execute(text(query), params)
                return [dict(row._mapping) for row in result]

        except Exception as e:
            logger.error(f"Failed to get data coverage: {e}")
            return []

    async def detect_missing_ranges(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        period: str = "1m"
    ) -> List[tuple]:
        """检测缺失的数据时间段"""
        self._ensure_initialized()

        try:
            with SessionLocal() as db:
                # 获取现有的时间戳
                result = db.execute(text("""
                    SELECT timestamp FROM crypto_klines
                    WHERE exchange = :exchange AND symbol = :symbol
                    AND period = :period AND timestamp BETWEEN :start_ts AND :end_ts
                    ORDER BY timestamp
                """), {
                    'exchange': self.exchange_id,
                    'symbol': symbol,
                    'period': period,
                    'start_ts': int(start_time.timestamp()),
                    'end_ts': int(end_time.timestamp())
                })

                existing_timestamps = {row[0] for row in result}

                # 生成期望的时间戳序列（1分钟间隔）
                expected_timestamps = []
                current = start_time
                while current <= end_time:
                    expected_timestamps.append(int(current.timestamp()))
                    current += timedelta(minutes=1)

                # 找出缺失的时间段
                missing_ranges = []
                range_start = None

                for ts in expected_timestamps:
                    if ts not in existing_timestamps:
                        if range_start is None:
                            range_start = ts
                    else:
                        if range_start is not None:
                            missing_ranges.append((
                                datetime.fromtimestamp(range_start),
                                datetime.fromtimestamp(ts - 60)  # 前一分钟
                            ))
                            range_start = None

                # 处理最后一个缺失段
                if range_start is not None:
                    missing_ranges.append((
                        datetime.fromtimestamp(range_start),
                        end_time
                    ))

                return missing_ranges

        except Exception as e:
            logger.error(f"Failed to detect missing ranges: {e}")
            return []

    def get_supported_symbols(self) -> List[str]:
        """获取当前交易所支持的交易对"""
        self._ensure_initialized()
        return self.collector.get_supported_symbols()

    async def refresh_exchange_config(self):
        """刷新交易所配置（当用户切换交易所时调用）"""
        self._initialized = False
        await self.initialize()


# 全局服务实例
kline_service = KlineDataService()