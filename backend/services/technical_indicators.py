#!/usr/bin/env python3
"""
技术指标计算服务
使用fin-primitives库计算各种技术指标
"""

import pandas as pd
import fin_primitives.pandas  # noqa: F401  (registers the .fp accessor)
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def calculate_indicators(kline_data: List[Dict[str, Any]], indicators: List[str]) -> Dict[str, Any]:
    """
    计算技术指标

    Args:
        kline_data: K线数据列表，包含timestamp, open, high, low, close, volume
        indicators: 需要计算的指标列表，如 ['EMA20', 'EMA50', 'MACD', 'RSI14']

    Returns:
        Dict: 计算结果，格式为 {'EMA20': [...], 'MACD': {...}, ...}
    """
    if not kline_data:
        return {}

    try:
        # 转换为DataFrame
        df = pd.DataFrame(kline_data)

        # 确保数据类型正确
        df['open'] = pd.to_numeric(df['open'], errors='coerce')
        df['high'] = pd.to_numeric(df['high'], errors='coerce')
        df['low'] = pd.to_numeric(df['low'], errors='coerce')
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')

        # 按时间排序
        df = df.sort_values('timestamp')

        results = {}

        for indicator in indicators:
            try:
                if indicator == 'EMA20':
                    results['EMA20'] = _calculate_ema(df, 20)
                elif indicator == 'EMA50':
                    results['EMA50'] = _calculate_ema(df, 50)
                elif indicator == 'EMA100':
                    results['EMA100'] = _calculate_ema(df, 100)
                elif indicator == 'MA5':
                    results['MA5'] = _calculate_sma(df, 5)
                elif indicator == 'MA10':
                    results['MA10'] = _calculate_sma(df, 10)
                elif indicator == 'MA20':
                    results['MA20'] = _calculate_sma(df, 20)
                elif indicator == 'MACD':
                    results['MACD'] = _calculate_macd(df)
                elif indicator == 'RSI14':
                    results['RSI14'] = _calculate_rsi(df, 14)
                elif indicator == 'RSI7':
                    results['RSI7'] = _calculate_rsi(df, 7)
                elif indicator == 'BOLL':
                    results['BOLL'] = _calculate_bollinger_bands(df)
                elif indicator == 'ATR14':
                    results['ATR14'] = _calculate_atr(df, 14)
                elif indicator == 'VWAP':
                    results['VWAP'] = _calculate_vwap(df)
                elif indicator == 'STOCH':
                    results['STOCH'] = _calculate_stochastic(df)
                elif indicator == 'OBV':
                    results['OBV'] = _calculate_obv(df)
                else:
                    logger.warning(f"Unknown indicator: {indicator}")

            except Exception as e:
                logger.error(f"Error calculating {indicator}: {e}")
                results[indicator] = None

        return results

    except Exception as e:
        logger.error(f"Error in calculate_indicators: {e}")
        return {}


def _calculate_ema(df: pd.DataFrame, period: int) -> List[float]:
    """计算指数移动平均线"""
    ema = df['close'].fp.ema(length=period)
    if ema is None:
        return []
    return ema.fillna(0).tolist()


def _calculate_sma(df: pd.DataFrame, period: int) -> List[float]:
    """计算简单移动平均线"""
    sma = df['close'].fp.sma(length=period)
    if sma is None:
        return []
    return sma.fillna(0).tolist()


def _calculate_macd(df: pd.DataFrame) -> Dict[str, List[float]]:
    """计算MACD指标"""
    macd_data = df['close'].fp.macd()
    if macd_data is None or macd_data.empty:
        return {'macd': [], 'signal': [], 'histogram': []}

    # Dynamic column name lookup to handle pandas-ta version differences
    macd_col = [c for c in macd_data.columns if c.startswith('MACD_')]
    signal_col = [c for c in macd_data.columns if c.startswith('MACDs_')]
    hist_col = [c for c in macd_data.columns if c.startswith('MACDh_')]

    return {
        'macd': macd_data[macd_col[0]].fillna(0).tolist() if macd_col else [],
        'signal': macd_data[signal_col[0]].fillna(0).tolist() if signal_col else [],
        'histogram': macd_data[hist_col[0]].fillna(0).tolist() if hist_col else []
    }


def _calculate_rsi(df: pd.DataFrame, period: int) -> List[float]:
    """计算相对强弱指数"""
    rsi = df['close'].fp.rsi(length=period)
    return rsi.fillna(50).tolist()  # RSI默认值设为50


def _calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std: float = 2) -> Dict[str, List[float]]:
    """计算布林带"""
    logger.info(f"Starting BOLL calculation with {len(df)} data points, period={period}, std={std}")

    try:
        # 检查输入数据
        if len(df) < period:
            logger.error(f"Insufficient data for BOLL calculation: {len(df)} < {period}")
            return None

        logger.info(f"Close price sample: {df['close'].head().tolist()}")

        bb = df['close'].fp.bbands(length=period, std=std)
        logger.info(f"BOLL calculation completed, result type: {type(bb)}")

        if bb is None:
            logger.error("BOLL calculation returned None")
            return None

        if bb.empty:
            logger.error("BOLL calculation returned empty DataFrame")
            return None

        # 打印列名以调试
        logger.info(f"BOLL columns: {bb.columns.tolist()}")
        logger.info(f"BOLL shape: {bb.shape}")
        logger.info(f"BOLL sample data:\n{bb.head()}")

        # 尝试不同的列名格式
        upper_col = None
        middle_col = None
        lower_col = None

        for col in bb.columns:
            logger.info(f"Checking column: {col}")
            if 'BBU' in col or 'upper' in col.lower():
                upper_col = col
                logger.info(f"Found upper column: {col}")
            elif 'BBM' in col or 'middle' in col.lower():
                middle_col = col
                logger.info(f"Found middle column: {col}")
            elif 'BBL' in col or 'lower' in col.lower():
                lower_col = col
                logger.info(f"Found lower column: {col}")

        if not all([upper_col, middle_col, lower_col]):
            logger.error(f"Could not find all BOLL columns. Found: upper={upper_col}, middle={middle_col}, lower={lower_col}")
            logger.error(f"Available columns: {bb.columns.tolist()}")
            return None

        result = {
            'upper': bb[upper_col].fillna(0).tolist(),
            'middle': bb[middle_col].fillna(0).tolist(),
            'lower': bb[lower_col].fillna(0).tolist()
        }

        logger.info(f"BOLL calculation successful, returning {len(result['upper'])} data points")
        return result

    except Exception as e:
        logger.error(f"Error calculating BOLL: {e}", exc_info=True)
        return None


def _calculate_atr(df: pd.DataFrame, period: int) -> List[float]:
    """计算平均真实波幅"""
    atr = df.fp.atr(length=period)
    if atr is None:
        return []
    return atr.fillna(0).tolist()


def _calculate_vwap(df: pd.DataFrame) -> List[float]:
    """计算成交量加权平均价"""
    try:
        # VWAP 需要 DatetimeIndex
        # Note: timestamp is stored in seconds (not milliseconds)
        df_copy = df.copy()
        df_copy['datetime'] = pd.to_datetime(df_copy['timestamp'], unit='s')
        df_copy = df_copy.set_index('datetime')
        vwap = df_copy.fp.vwap()
        if vwap is None:
            return []
        return vwap.fillna(0).tolist()
    except Exception as e:
        logger.error(f"Error calculating VWAP: {e}")
        return []


def _calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Dict[str, List[float]]:
    """计算随机震荡指标"""
    stoch = df.fp.stoch(k=k_period, d=d_period)
    if stoch is None or stoch.empty:
        return {'k': [], 'd': []}

    # Dynamic column name lookup to handle pandas-ta version differences
    k_col = [c for c in stoch.columns if c.startswith('STOCHk_')]
    d_col = [c for c in stoch.columns if c.startswith('STOCHd_')]

    return {
        'k': stoch[k_col[0]].fillna(50).tolist() if k_col else [],
        'd': stoch[d_col[0]].fillna(50).tolist() if d_col else []
    }


def _calculate_obv(df: pd.DataFrame) -> List[float]:
    """计算能量潮指标"""
    obv = df.fp.obv()
    if obv is None:
        return []
    return obv.fillna(0).tolist()


def get_available_indicators() -> List[Dict[str, str]]:
    """获取支持的技术指标列表"""
    return [
        {'name': 'MA5', 'description': '5期简单移动平均线'},
        {'name': 'MA10', 'description': '10期简单移动平均线'},
        {'name': 'MA20', 'description': '20期简单移动平均线'},
        {'name': 'EMA20', 'description': '20期指数移动平均线'},
        {'name': 'EMA50', 'description': '50期指数移动平均线'},
        {'name': 'EMA100', 'description': '100期指数移动平均线'},
        {'name': 'MACD', 'description': '移动平均收敛发散指标'},
        {'name': 'RSI14', 'description': '14期相对强弱指数'},
        {'name': 'RSI7', 'description': '7期相对强弱指数'},
        {'name': 'BOLL', 'description': '布林带'},
        {'name': 'ATR14', 'description': '14期平均真实波幅'},
        {'name': 'VWAP', 'description': '成交量加权平均价'},
        {'name': 'STOCH', 'description': '随机震荡指标'},
        {'name': 'OBV', 'description': '能量潮指标'},
    ]


def calculate_indicator(
    db,
    symbol: str,
    indicator: str,
    period: str,
    current_time_ms: int
) -> Optional[Dict[str, Any]]:
    """
    Calculate a single technical indicator for Program Trader.

    Args:
        db: Database session
        symbol: Trading symbol (e.g., 'BTC')
        indicator: Indicator name (e.g., 'RSI14', 'EMA20', 'MACD')
        period: K-line period (e.g., '1h', '4h', '1d')
        current_time_ms: Current timestamp in milliseconds

    Returns:
        Dict with indicator values, or None if calculation fails
    """
    from database.models import CryptoKline
    from sqlalchemy import desc

    try:
        # Determine how many candles we need based on indicator
        count = 100  # Default
        if 'EMA100' in indicator or 'MA100' in indicator:
            count = 150
        elif 'EMA50' in indicator or 'MA50' in indicator:
            count = 100

        # Fetch K-line data from database
        rows = (
            db.query(CryptoKline)
            .filter(CryptoKline.symbol == symbol, CryptoKline.period == period)
            .order_by(desc(CryptoKline.timestamp))
            .limit(count)
            .all()
        )

        if not rows:
            logger.warning(f"No kline data for {symbol} {period}")
            return None

        # Convert to list of dicts for calculate_indicators
        # Note: CryptoKline uses open_price/high_price/etc and timestamp is integer (seconds)
        kline_data = [
            {
                'timestamp': int(row.timestamp),
                'open': float(row.open_price) if row.open_price else 0.0,
                'high': float(row.high_price) if row.high_price else 0.0,
                'low': float(row.low_price) if row.low_price else 0.0,
                'close': float(row.close_price) if row.close_price else 0.0,
                'volume': float(row.volume) if row.volume else 0.0,
            }
            for row in reversed(rows)
        ]

        # Calculate the indicator
        results = calculate_indicators(kline_data, [indicator])

        if indicator in results and results[indicator] is not None:
            value = results[indicator]
            # Return the latest value(s)
            if isinstance(value, list):
                return {'value': value[-1] if value else None, 'series': value}
            elif isinstance(value, dict):
                # For MACD, BOLL, STOCH etc. - return latest values
                latest = {}
                for k, v in value.items():
                    if isinstance(v, list) and v:
                        latest[k] = v[-1]
                    else:
                        latest[k] = v
                return latest
            return {'value': value}

        return None

    except Exception as e:
        logger.error(f"Error in calculate_indicator({symbol}, {indicator}, {period}): {e}")
        return None


def get_macd_for_signal(
    db,
    symbol: str,
    period: str,
    current_time_ms: int,
    exchange: str = "hyperliquid"
) -> Optional[Dict[str, Any]]:
    """
    Get MACD values for signal detection.
    Returns current and previous K-line's MACD values for cross detection.

    Args:
        db: Database session
        symbol: Trading symbol (e.g., 'BTC')
        period: K-line period (e.g., '1h', '4h')
        current_time_ms: Current timestamp in milliseconds
        exchange: Exchange name ('hyperliquid' or 'binance')

    Returns:
        Dict with current and previous MACD values, or None if calculation fails
    """
    from database.models import CryptoKline
    from sqlalchemy import desc

    try:
        # Need at least 35 candles for MACD (26 slow + 9 signal)
        count = 50

        # Fetch K-line data from database
        rows = (
            db.query(CryptoKline)
            .filter(
                CryptoKline.symbol == symbol,
                CryptoKline.period == period,
                CryptoKline.exchange == exchange
            )
            .order_by(desc(CryptoKline.timestamp))
            .limit(count)
            .all()
        )

        if not rows or len(rows) < 35:
            logger.warning(f"Insufficient kline data for MACD: {symbol} {period} {exchange}, got {len(rows) if rows else 0}")
            return None

        # Convert to DataFrame (reverse to chronological order)
        kline_data = [
            {
                'timestamp': int(row.timestamp),
                'open': float(row.open_price) if row.open_price else 0.0,
                'high': float(row.high_price) if row.high_price else 0.0,
                'low': float(row.low_price) if row.low_price else 0.0,
                'close': float(row.close_price) if row.close_price else 0.0,
                'volume': float(row.volume) if row.volume else 0.0,
            }
            for row in reversed(rows)
        ]

        df = pd.DataFrame(kline_data)
        df['close'] = pd.to_numeric(df['close'], errors='coerce')

        # Check data freshness - reject if latest K-line is too old
        # For real-time signal detection, data should be within 2x the period interval
        latest_kline_ts = kline_data[-1]['timestamp']
        current_time_sec = current_time_ms // 1000

        # Calculate max allowed age based on period
        period_seconds = {
            '1m': 60, '3m': 180, '5m': 300, '15m': 900,
            '30m': 1800, '1h': 3600, '4h': 14400, '1d': 86400
        }
        max_age_sec = period_seconds.get(period, 3600) * 2  # Allow 2x period as buffer

        if current_time_sec - latest_kline_ts > max_age_sec:
            logger.warning(
                f"[MACD] Stale K-line data for {symbol}/{period}/{exchange}: "
                f"latest={latest_kline_ts}, current={current_time_sec}, age={current_time_sec - latest_kline_ts}s, max={max_age_sec}s"
            )
            return None

        # Calculate MACD
        macd_data = df['close'].fp.macd()
        if macd_data is None or macd_data.empty:
            return None

        macd_values = macd_data['MACD_12_26_9'].fillna(0).tolist()
        signal_values = macd_data['MACDs_12_26_9'].fillna(0).tolist()
        histogram_values = macd_data['MACDh_12_26_9'].fillna(0).tolist()

        if len(macd_values) < 2:
            return None

        # Get current and previous values
        curr_macd = macd_values[-1]
        curr_signal = signal_values[-1]
        curr_histogram = histogram_values[-1]
        prev_macd = macd_values[-2]
        prev_signal = signal_values[-2]
        prev_histogram = histogram_values[-2]

        # Get the timestamp of the latest K-line for cache validation
        latest_kline_ts = kline_data[-1]['timestamp']

        return {
            'current': {
                'macd': curr_macd,
                'signal': curr_signal,
                'histogram': curr_histogram,
            },
            'previous': {
                'macd': prev_macd,
                'signal': prev_signal,
                'histogram': prev_histogram,
            },
            'latest_kline_ts': latest_kline_ts,
            'cross_strength': abs(curr_histogram - prev_histogram),
        }

    except Exception as e:
        logger.error(f"Error in get_macd_for_signal({symbol}, {period}, {exchange}): {e}")
        return None
