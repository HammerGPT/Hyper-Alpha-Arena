"""
System Log Collector Service
实时收集系统日志：价格更新、AI决策、错误异常
"""

import logging
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Deque
from dataclasses import dataclass, asdict
import threading
import json


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str
    level: str  # INFO, WARNING, ERROR
    category: str  # price_update, ai_decision, system_error
    message: str
    details: Optional[Dict] = None

    def to_dict(self):
        """转换为字典"""
        return asdict(self)


class SystemLogCollector:
    """系统日志收集器"""

    def __init__(self, max_logs: int = 500):
        """
        初始化日志收集器

        Args:
            max_logs: 内存中保存的最大日志数量
        """
        self._logs: Deque[LogEntry] = deque(maxlen=max_logs)
        self._lock = threading.Lock()
        self._listeners = []  # WebSocket监听器

    def add_log(self, level: str, category: str, message: str, details: Optional[Dict] = None):
        """
        添加日志条目

        Args:
            level: 日志级别 (INFO, WARNING, ERROR)
            category: 日志分类 (price_update, ai_decision, system_error)
            message: 日志消息
            details: 详细信息字典
        """
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            category=category,
            message=message,
            details=details or {}
        )

        with self._lock:
            self._logs.append(entry)

        # 通知所有监听器
        self._notify_listeners(entry)

    _LEVEL_ORDER = {
        "INFO": 1,
        "WARNING": 2,
        "ERROR": 3,
    }

    def get_logs(
        self,
        level: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
        min_level: Optional[str] = None,
    ) -> List[Dict]:
        """
        获取日志列表

        Args:
            level: 过滤日志级别
            category: 过滤日志分类
            limit: 返回的最大日志数量

        Returns:
            日志字典列表
        """
        with self._lock:
            logs = list(self._logs)

        # 反转顺序（最新的在前）
        logs.reverse()

        # 过滤
        if level:
            logs = [log for log in logs if log.level == level]
        elif min_level:
            threshold = self._LEVEL_ORDER.get(min_level.upper(), 1)
            logs = [
                log for log in logs
                if self._LEVEL_ORDER.get(log.level.upper(), 1) >= threshold
            ]

        if category:
            logs = [log for log in logs if log.category == category]

        # 限制数量
        logs = logs[:limit]

        return [log.to_dict() for log in logs]

    def clear_logs(self):
        """清空所有日志"""
        with self._lock:
            self._logs.clear()

    def add_listener(self, callback):
        """添加WebSocket监听器"""
        self._listeners.append(callback)

    def remove_listener(self, callback):
        """移除WebSocket监听器"""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify_listeners(self, entry: LogEntry):
        """通知所有监听器有新日志"""
        for callback in self._listeners:
            try:
                callback(entry.to_dict())
            except Exception as e:
                logging.error(f"Failed to notify log listener: {e}")

    def log_price_update(self, symbol: str, price: float, change_percent: Optional[float] = None):
        """记录价格更新"""
        details = {
            "symbol": symbol,
            "price": price
        }
        if change_percent is not None:
            details["change_percent"] = change_percent

        self.add_log(
            level="INFO",
            category="price_update",
            message=f"{symbol} price updated: ${price:.4f}",
            details=details
        )

    def log_ai_decision(
        self,
        account_name: str,
        model: str,
        operation: str,
        symbol: Optional[str],
        reason: str,
        success: bool = True
    ):
        """记录AI决策"""
        self.add_log(
            level="INFO" if success else "WARNING",
            category="ai_decision",
            message=f"[{account_name}] {operation.upper()} {symbol or 'N/A'}: {reason[:100]}",
            details={
                "account": account_name,
                "model": model,
                "operation": operation,
                "symbol": symbol,
                "reason": reason,
                "success": success
            }
        )

    def log_error(self, error_type: str, message: str, details: Optional[Dict] = None):
        """记录系统错误"""
        self.add_log(
            level="ERROR",
            category="system_error",
            message=f"[{error_type}] {message}",
            details=details or {}
        )

    def log_warning(self, warning_type: str, message: str, details: Optional[Dict] = None):
        """记录系统警告"""
        self.add_log(
            level="WARNING",
            category="system_error",
            message=f"[{warning_type}] {message}",
            details=details or {}
        )


# 全局单例
system_logger = SystemLogCollector(max_logs=500)


class SystemLogHandler(logging.Handler):
    """Python logging Handler，自动收集日志到SystemLogCollector"""

    def emit(self, record: logging.LogRecord):
        """处理日志记录"""
        try:
            # 判断日志来源和类型
            module = record.name
            level = record.levelname
            message = self.format(record)

            # 分类日志
            category = "system_error"
            if "price" in message.lower() or "market" in module:
                category = "price_update"
            elif "ai_decision" in module or "trading" in module:
                category = "ai_decision"

            # 提取详细信息
            details = {
                "module": module,
                "function": record.funcName,
                "line": record.lineno
            }

            # 添加异常信息
            if record.exc_info:
                import traceback
                details["exception"] = ''.join(traceback.format_exception(*record.exc_info))

            # 记录WARNING及以上级别,或者策略触发相关的INFO日志
            if record.levelno >= logging.WARNING:
                system_logger.add_log(
                    level=level,
                    category=category,
                    message=message,
                    details=details
                )
            elif record.levelno == logging.INFO and "Strategy triggered" in message:
                # 收集策略触发的INFO日志
                system_logger.add_log(
                    level=level,
                    category="ai_decision",
                    message=message,
                    details=details
                )
            elif record.levelno == logging.INFO and "Strategy execution completed" in message:
                # 收集策略执行完成的INFO日志
                system_logger.add_log(
                    level=level,
                    category="ai_decision",
                    message=message,
                    details=details
                )
        except Exception as e:
            # 避免日志处理器本身出错
            print(f"SystemLogHandler error: {e}")


class PriceSnapshotLogger:
    """每60秒记录一次价格快照"""

    def __init__(self):
        self._timer: Optional[threading.Timer] = None
        self._interval = 60  # 60 seconds
        self._running = False
        self._last_prices: Dict[str, float] = {}

    def start(self):
        """启动价格快照记录器"""
        if self._running:
            return
        self._running = True
        self._schedule_next()
        logging.info("Price snapshot logger started (60-second interval)")

    def stop(self):
        """停止价格快照记录器"""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logging.info("Price snapshot logger stopped")

    def _schedule_next(self):
        """安排下一次快照"""
        if not self._running:
            return
        self._timer = threading.Timer(self._interval, self._take_snapshot)
        self._timer.daemon = True
        self._timer.start()

    def _take_snapshot(self):
        """获取并记录所有币种的当前价格"""
        try:
            from services.price_cache import get_cached_price
            from services.trading_commands import AI_TRADING_SYMBOLS

            prices_info = []
            for symbol in AI_TRADING_SYMBOLS:
                price = get_cached_price(symbol, "CRYPTO")
                if price is not None:
                    prices_info.append(f"{symbol}=${price:.4f}")
                    self._last_prices[symbol] = price

            if prices_info:
                message = "Price snapshot: " + ", ".join(prices_info)
                system_logger.add_log(
                    level="INFO",
                    category="price_update",
                    message=message,
                    details={"prices": self._last_prices.copy(), "symbols": AI_TRADING_SYMBOLS}
                )
        except Exception as e:
            logging.error(f"Failed to take price snapshot: {e}")
        finally:
            # 安排下一次快照
            self._schedule_next()


# 全局价格快照记录器
price_snapshot_logger = PriceSnapshotLogger()


def setup_system_logger():
    """设置系统日志处理器（在应用启动时调用）"""
    handler = SystemLogHandler()
    handler.setLevel(logging.WARNING)  # 只收集WARNING及以上

    # 添加到根logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    logging.info("System log collector initialized")
