"""
K线数据采集器 - 交易所分流架构
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class KlineData:
    """标准化的K线数据结构"""
    exchange: str
    symbol: str
    timestamp: int  # Unix timestamp in seconds
    period: str     # "1m", "5m", "1h", etc.
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float


class BaseKlineCollector(ABC):
    """K线采集器基类 - 定义统一接口"""

    def __init__(self, exchange_id: str):
        self.exchange_id = exchange_id
        self.logger = logging.getLogger(f"{__name__}.{exchange_id}")

    @abstractmethod
    async def fetch_current_kline(self, symbol: str, period: str = "1m") -> Optional[KlineData]:
        """获取当前分钟的K线数据"""
        pass

    @abstractmethod
    async def fetch_historical_klines(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        period: str = "1m"
    ) -> List[KlineData]:
        """获取历史K线数据"""
        pass

    @abstractmethod
    def get_supported_symbols(self) -> List[str]:
        """获取支持的交易对列表"""
        pass


class HyperliquidKlineCollector(BaseKlineCollector):
    """Hyperliquid K线采集器"""

    def __init__(self):
        super().__init__("hyperliquid")
        # 复用现有的 hyperliquid_market_data 服务
        from .hyperliquid_market_data import HyperliquidClient
        self.market_data = HyperliquidClient()

    async def fetch_current_kline(self, symbol: str, period: str = "1m") -> Optional[KlineData]:
        """获取当前分钟K线"""
        try:
            # 调用现有的K线获取方法 (同步方法，不需要 await)
            klines = self.market_data.get_kline_data(symbol, period, count=1)
            if not klines:
                return None

            latest = klines[0]
            return KlineData(
                exchange=self.exchange_id,
                symbol=symbol,
                timestamp=int(latest['timestamp']),
                period=period,
                open_price=float(latest['open']),
                high_price=float(latest['high']),
                low_price=float(latest['low']),
                close_price=float(latest['close']),
                volume=float(latest['volume'])
            )
        except Exception as e:
            self.logger.error(f"Failed to fetch current kline for {symbol}: {e}")
            return None

    async def fetch_historical_klines(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        period: str = "1m"
    ) -> List[KlineData]:
        """获取历史K线数据"""
        try:
            # 计算需要的数据量
            time_diff = end_time - start_time
            if period == "1m":
                limit = int(time_diff.total_seconds() / 60)
            else:
                # 其他周期的计算逻辑
                limit = 1000  # 默认限制

            # 调用现有方法获取历史数据
            klines = await self.market_data.get_kline_data(
                symbol, period, limit=min(limit, 5000)
            )

            result = []
            for kline in klines:
                kline_time = datetime.fromtimestamp(kline['timestamp'])
                if start_time <= kline_time <= end_time:
                    result.append(KlineData(
                        exchange=self.exchange_id,
                        symbol=symbol,
                        timestamp=int(kline['timestamp']),
                        period=period,
                        open_price=float(kline['open']),
                        high_price=float(kline['high']),
                        low_price=float(kline['low']),
                        close_price=float(kline['close']),
                        volume=float(kline['volume'])
                    ))

            return result
        except Exception as e:
            self.logger.error(f"Failed to fetch historical klines for {symbol}: {e}")
            return []

    def get_supported_symbols(self) -> List[str]:
        """获取用户Watch List中选择的交易对（实时采集用）"""
        try:
            from .hyperliquid_symbol_service import get_selected_symbols
            symbols = get_selected_symbols()
            if symbols:
                return symbols
        except Exception as e:
            self.logger.warning(f"Failed to get symbols from hyperliquid_symbol_service: {e}")

        # 降级到默认列表
        return ["BTC", "ETH", "SOL", "BNB"]


class BinanceKlineCollector(BaseKlineCollector):
    """Binance K线采集器 - 预留实现"""

    def __init__(self):
        super().__init__("binance")

    async def fetch_current_kline(self, symbol: str, period: str = "1m") -> Optional[KlineData]:
        # TODO: 实现Binance API调用
        self.logger.warning("Binance collector not implemented yet")
        return None

    async def fetch_historical_klines(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        period: str = "1m"
    ) -> List[KlineData]:
        # TODO: 实现Binance历史数据获取
        self.logger.warning("Binance historical data not implemented yet")
        return []

    def get_supported_symbols(self) -> List[str]:
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]  # 示例


class AsterKlineCollector(BaseKlineCollector):
    """Aster DEX K线采集器 - 预留实现"""

    def __init__(self):
        super().__init__("aster")

    async def fetch_current_kline(self, symbol: str, period: str = "1m") -> Optional[KlineData]:
        # TODO: 实现Aster API调用
        self.logger.warning("Aster collector not implemented yet")
        return None

    async def fetch_historical_klines(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        period: str = "1m"
    ) -> List[KlineData]:
        # TODO: 实现Aster历史数据获取
        self.logger.warning("Aster historical data not implemented yet")
        return []

    def get_supported_symbols(self) -> List[str]:
        return ["BTC/USDT", "ETH/USDT"]  # 示例


class ExchangeDataSourceFactory:
    """交易所数据源工厂 - 根据配置返回对应采集器"""

    _collectors = {
        "hyperliquid": HyperliquidKlineCollector,
        "binance": BinanceKlineCollector,
        "aster": AsterKlineCollector
    }

    @classmethod
    def get_collector(cls, exchange_id: str) -> BaseKlineCollector:
        """根据交易所ID获取对应的采集器实例"""
        if exchange_id not in cls._collectors:
            raise ValueError(f"Unsupported exchange: {exchange_id}")

        collector_class = cls._collectors[exchange_id]
        return collector_class()

    @classmethod
    def get_supported_exchanges(cls) -> List[str]:
        """获取支持的交易所列表"""
        return list(cls._collectors.keys())