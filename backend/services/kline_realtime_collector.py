"""
K线实时采集服务 - 每分钟定时采集当前K线数据
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Set
import logging

from .kline_data_service import kline_service

logger = logging.getLogger(__name__)


class KlineRealtimeCollector:
    """K线实时采集服务"""

    def __init__(self):
        self.running = False
        self.collection_task = None
        self.gap_detection_task = None

        # 默认采集的交易对
        self.default_symbols = ["BTC", "ETH", "SOL", "ARB", "OP"]

    async def start(self):
        """启动实时采集服务"""
        if self.running:
            logger.warning("Realtime collector is already running")
            return

        try:
            # 初始化数据服务
            await kline_service.initialize()

            self.running = True
            logger.info("Starting K-line realtime collection service")

            # 启动实时采集任务
            self.collection_task = asyncio.create_task(self._realtime_collection_loop())

            # 启动缺失检测任务（每小时执行一次）
            self.gap_detection_task = asyncio.create_task(self._gap_detection_loop())

            logger.info("K-line realtime collector started successfully")

        except Exception as e:
            logger.error(f"Failed to start realtime collector: {e}")
            self.running = False
            raise

    async def stop(self):
        """停止实时采集服务"""
        if not self.running:
            return

        logger.info("Stopping K-line realtime collection service")
        self.running = False

        # 取消任务
        if self.collection_task:
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                pass

        if self.gap_detection_task:
            self.gap_detection_task.cancel()
            try:
                await self.gap_detection_task
            except asyncio.CancelledError:
                pass

        logger.info("K-line realtime collector stopped")

    async def _realtime_collection_loop(self):
        """实时采集循环 - 每分钟整点执行"""
        logger.info("Starting realtime collection loop")

        while self.running:
            try:
                # 等待到下一个整分钟
                await self._wait_for_next_minute()

                if not self.running:
                    break

                # 执行采集
                await self._collect_current_minute()

            except asyncio.CancelledError:
                logger.info("Realtime collection loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in realtime collection loop: {e}")
                # 出错后等待30秒再继续
                await asyncio.sleep(30)

    async def _wait_for_next_minute(self):
        """等待到下一个整分钟"""
        now = datetime.now()
        # 计算到下一个整分钟的秒数
        seconds_to_wait = 60 - now.second - now.microsecond / 1000000

        # 最少等待1秒，避免在同一分钟内重复执行
        if seconds_to_wait < 1:
            seconds_to_wait += 60

        logger.debug(f"Waiting {seconds_to_wait:.1f} seconds for next minute")
        await asyncio.sleep(seconds_to_wait)

    async def _collect_current_minute(self):
        """采集当前分钟的K线数据"""
        current_time = datetime.now()
        logger.info(f"Collecting K-lines at {current_time.strftime('%Y-%m-%d %H:%M:%S')}")

        # 获取支持的交易对
        symbols = kline_service.get_supported_symbols()
        if not symbols:
            symbols = self.default_symbols

        # 并发采集所有交易对
        tasks = []
        for symbol in symbols:
            task = asyncio.create_task(
                self._collect_symbol_kline(symbol),
                name=f"collect_{symbol}"
            )
            tasks.append(task)

        # 等待所有采集任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计结果
        success_count = 0
        error_count = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to collect {symbols[i]}: {result}")
                error_count += 1
            elif result:
                success_count += 1
            else:
                error_count += 1

        logger.info(f"Collection completed: {success_count} success, {error_count} errors")

    async def _collect_symbol_kline(self, symbol: str) -> bool:
        """采集单个交易对的K线数据"""
        try:
            return await kline_service.collect_current_kline(symbol, "1m")
        except Exception as e:
            logger.error(f"Failed to collect kline for {symbol}: {e}")
            return False

    async def _gap_detection_loop(self):
        """缺失检测循环 - 每小时执行一次"""
        logger.info("Starting gap detection loop")

        while self.running:
            try:
                # 等待1小时
                await asyncio.sleep(3600)

                if not self.running:
                    break

                # 执行缺失检测
                await self._detect_and_fill_gaps()

            except asyncio.CancelledError:
                logger.info("Gap detection loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in gap detection loop: {e}")

    async def _detect_and_fill_gaps(self):
        """检测并自动填补数据缺失"""
        logger.info("Starting gap detection and auto-fill")

        # 检查过去24小时的数据完整性
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)

        symbols = kline_service.get_supported_symbols()
        if not symbols:
            symbols = self.default_symbols

        for symbol in symbols:
            try:
                # 检测缺失的时间段
                missing_ranges = await kline_service.detect_missing_ranges(
                    symbol, start_time, end_time, "1m"
                )

                if missing_ranges:
                    logger.info(f"Found {len(missing_ranges)} missing ranges for {symbol}")

                    # 自动补充缺失数据
                    for range_start, range_end in missing_ranges:
                        # 限制单次补充的时间范围（最多6小时）
                        if (range_end - range_start).total_seconds() > 6 * 3600:
                            logger.warning(f"Large gap detected for {symbol}: {range_start} to {range_end}, skipping auto-fill")
                            continue

                        collected = await kline_service.collect_historical_klines(
                            symbol, range_start, range_end, "1m"
                        )

                        if collected > 0:
                            logger.info(f"Auto-filled {collected} records for {symbol} from {range_start} to {range_end}")
                        else:
                            logger.warning(f"Failed to auto-fill gap for {symbol} from {range_start} to {range_end}")

                        # 避免API限流，每次补充后等待一下
                        await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error detecting gaps for {symbol}: {e}")

        logger.info("Gap detection and auto-fill completed")


# 全局实时采集器实例
realtime_collector = KlineRealtimeCollector()