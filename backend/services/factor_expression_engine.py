"""
Factor Expression Engine

Safely evaluates user/AI-submitted factor expressions against K-line data.
Uses asteval (safe expression evaluator) + fin-primitives (TA indicators).

Example expressions:
    EMA(close, 7) / EMA(close, 21) - 1
    RSI(close, 14) - 50
    ATR(high, low, close, 14) / close
    TS_CORR(close, volume, 20)
    IF(ROC(close,5) > 0, 1, -1)
"""

import logging
import numpy as np
import pandas as pd
from asteval import Interpreter
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Single Source of Truth: Function Registry ───
# Every supported function is defined here with full metadata.
# _build_functions() registers the actual implementations keyed by name.
# GET /api/factors/expression-functions serves this to frontend + AI.

FUNCTION_REGISTRY: Dict[str, dict] = {}


def _reg(name, cat, sig, desc, desc_zh, example, params=None):
    FUNCTION_REGISTRY[name] = {
        "category": cat,
        "signature": sig,
        "description": desc,
        "description_zh": desc_zh,
        "example": example,
        "params": params or [],
    }


# ── Moving Average ──
_reg("SMA", "moving_average", "SMA(series, period)", "Simple Moving Average", "简单移动平均", "SMA(close, 20)")
_reg("EMA", "moving_average", "EMA(series, period)", "Exponential Moving Average", "指数移动平均", "EMA(close, 12)")
_reg("WMA", "moving_average", "WMA(series, period)", "Weighted Moving Average", "加权移动平均", "WMA(close, 20)")
_reg("DEMA", "moving_average", "DEMA(series, period)", "Double Exponential Moving Average", "双重指数移动平均", "DEMA(close, 20)")
_reg("TEMA", "moving_average", "TEMA(series, period)", "Triple Exponential Moving Average", "三重指数移动平均", "TEMA(close, 20)")
_reg("HMA", "moving_average", "HMA(series, period)", "Hull Moving Average (less lag)", "Hull移动平均(低延迟)", "HMA(close, 20)")
_reg("KAMA", "moving_average", "KAMA(series, period)", "Kaufman Adaptive Moving Average", "考夫曼自适应移动平均", "KAMA(close, 20)")

# ── Momentum ──
_reg("RSI", "momentum", "RSI(series, period)", "Relative Strength Index (0-100)", "相对强弱指数", "RSI(close, 14)")
_reg("ROC", "momentum", "ROC(series, period)", "Rate of Change (%)", "变化率", "ROC(close, 10)")
_reg("MOM", "momentum", "MOM(series, period)", "Momentum (price difference)", "动量(价差)", "MOM(close, 10)")
_reg("MACD", "momentum", "MACD(series, fast, slow, signal)", "MACD line", "MACD线", "MACD(close, 12, 26, 9)")
_reg("MACD_SIGNAL", "momentum", "MACD_SIGNAL(series, fast, slow, signal)", "MACD signal line", "MACD信号线", "MACD_SIGNAL(close, 12, 26, 9)")
_reg("MACD_HIST", "momentum", "MACD_HIST(series, fast, slow, signal)", "MACD histogram", "MACD柱状图", "MACD_HIST(close, 12, 26, 9)")
_reg("STOCH_K", "momentum", "STOCH_K(high, low, close, period)", "Stochastic %K", "随机指标%K", "STOCH_K(high, low, close, 14)")
_reg("STOCH_D", "momentum", "STOCH_D(high, low, close, period)", "Stochastic %D", "随机指标%D", "STOCH_D(high, low, close, 14)")
_reg("CCI", "momentum", "CCI(high, low, close, period)", "Commodity Channel Index", "顺势指标", "CCI(high, low, close, 20)")
_reg("WILLR", "momentum", "WILLR(high, low, close, period)", "Williams %R (-100~0)", "威廉指标", "WILLR(high, low, close, 14)")
_reg("PPO", "momentum", "PPO(series, fast, slow)", "Percentage Price Oscillator", "百分比价格振荡器", "PPO(close, 12, 26)")
_reg("TRIX", "momentum", "TRIX(series, period)", "Triple EMA Rate of Change", "三重EMA变化率", "TRIX(close, 15)")

# ── Trend ──
_reg("ADX", "trend", "ADX(high, low, close, period)", "Average Directional Index (trend strength)", "平均趋向指数(趋势强度)", "ADX(high, low, close, 14)")
_reg("PLUS_DI", "trend", "PLUS_DI(high, low, close, period)", "Plus Directional Indicator", "正方向指标", "PLUS_DI(high, low, close, 14)")
_reg("MINUS_DI", "trend", "MINUS_DI(high, low, close, period)", "Minus Directional Indicator", "负方向指标", "MINUS_DI(high, low, close, 14)")
_reg("AROON_UP", "trend", "AROON_UP(high, low, period)", "Aroon Up (0-100)", "阿隆上升线", "AROON_UP(high, low, 25)")
_reg("AROON_DOWN", "trend", "AROON_DOWN(high, low, period)", "Aroon Down (0-100)", "阿隆下降线", "AROON_DOWN(high, low, 25)")

# ── Volatility ──
_reg("ATR", "volatility", "ATR(high, low, close, period)", "Average True Range", "平均真实波幅", "ATR(high, low, close, 14)")
_reg("NATR", "volatility", "NATR(high, low, close, period)", "Normalized ATR (% of close)", "标准化ATR(收盘价百分比)", "NATR(high, low, close, 14)")
_reg("TRUE_RANGE", "volatility", "TRUE_RANGE(high, low, close)", "True Range (single bar)", "真实波幅(单根)", "TRUE_RANGE(high, low, close)")
_reg("STDDEV", "volatility", "STDDEV(series, period)", "Rolling Standard Deviation", "滚动标准差", "STDDEV(close, 20)")
_reg("BBANDS_UPPER", "volatility", "BBANDS_UPPER(series, period)", "Bollinger upper band", "布林带上轨", "BBANDS_UPPER(close, 20)")
_reg("BBANDS_MID", "volatility", "BBANDS_MID(series, period)", "Bollinger middle band", "布林带中轨", "BBANDS_MID(close, 20)")
_reg("BBANDS_LOWER", "volatility", "BBANDS_LOWER(series, period)", "Bollinger lower band", "布林带下轨", "BBANDS_LOWER(close, 20)")

# ── Volume ──
_reg("OBV", "volume", "OBV(close, volume)", "On-Balance Volume", "能量潮", "OBV(close, volume)")
_reg("VWAP", "volume", "VWAP(high, low, close, volume)", "Volume Weighted Average Price", "成交量加权均价", "VWAP(high, low, close, volume)")
_reg("AD", "volume", "AD(high, low, close, volume)", "Accumulation/Distribution Line", "累积/派发线", "AD(high, low, close, volume)")
_reg("CMF", "volume", "CMF(high, low, close, volume, period)", "Chaikin Money Flow", "蔡金资金流", "CMF(high, low, close, volume, 20)")
_reg("MFI", "volume", "MFI(high, low, close, volume, period)", "Money Flow Index (0-100)", "资金流量指数", "MFI(high, low, close, volume, 14)")

# ── Time Series Operators ──
_reg("DELAY", "time_series", "DELAY(series, period)", "Value N bars ago", "N根K线前的值", "DELAY(close, 5)")
_reg("DELTA", "time_series", "DELTA(series, period)", "Difference from N bars ago: x - x[N]", "与N根前的差值", "DELTA(close, 5)")
_reg("TS_SUM", "time_series", "TS_SUM(series, period)", "Rolling sum over N bars", "N根滚动求和", "TS_SUM(volume, 20)")
_reg("TS_MEAN", "time_series", "TS_MEAN(series, period)", "Rolling mean over N bars", "N根滚动均值", "TS_MEAN(close, 20)")
_reg("TS_STD", "time_series", "TS_STD(series, period)", "Rolling standard deviation", "滚动标准差", "TS_STD(close, 20)")
_reg("TS_MAX", "time_series", "TS_MAX(series, period)", "Rolling maximum", "滚动最大值", "TS_MAX(high, 20)")
_reg("TS_MIN", "time_series", "TS_MIN(series, period)", "Rolling minimum", "滚动最小值", "TS_MIN(low, 20)")
_reg("TS_RANK", "time_series", "TS_RANK(series, period)", "Rolling percentile rank (0-1)", "滚动百分位排名", "TS_RANK(close, 20)")
_reg("TS_ARGMAX", "time_series", "TS_ARGMAX(series, period)", "Bars since rolling max (0=today)", "距最高点的K线数", "TS_ARGMAX(high, 20)")
_reg("TS_ARGMIN", "time_series", "TS_ARGMIN(series, period)", "Bars since rolling min (0=today)", "距最低点的K线数", "TS_ARGMIN(low, 20)")
_reg("TS_CORR", "time_series", "TS_CORR(a, b, period)", "Rolling Pearson correlation", "滚动相关系数", "TS_CORR(close, volume, 20)")
_reg("TS_COV", "time_series", "TS_COV(a, b, period)", "Rolling covariance", "滚动协方差", "TS_COV(close, volume, 20)")
_reg("TS_SKEW", "time_series", "TS_SKEW(series, period)", "Rolling skewness", "滚动偏度", "TS_SKEW(close, 20)")
_reg("TS_KURT", "time_series", "TS_KURT(series, period)", "Rolling kurtosis", "滚动峰度", "TS_KURT(close, 20)")
_reg("DECAYLINEAR", "time_series", "DECAYLINEAR(series, period)", "Linearly decaying weighted average", "线性衰减加权平均", "DECAYLINEAR(close, 10)")
_reg("LOG_RETURN", "time_series", "LOG_RETURN(series, period)", "Log return: ln(x / x[N])", "对数收益率", "LOG_RETURN(close, 1)")
_reg("TS_PCT_CHANGE", "time_series", "TS_PCT_CHANGE(series, period)", "Percentage change: (x - x[N]) / x[N]", "百分比变化", "TS_PCT_CHANGE(close, 1)")

# ── Cross-section ──
_reg("RANK", "cross_section", "RANK(series)", "Percentile rank across all bars (0-1)", "全序列百分位排名", "RANK(close)")
_reg("ZSCORE", "cross_section", "ZSCORE(series)", "Z-score: (x - mean) / std", "Z分数标准化", "ZSCORE(RSI(close, 14))")
_reg("NORMALIZE", "cross_section", "NORMALIZE(series, period)", "Rolling Z-score: (x - rolling_mean) / rolling_std", "滚动Z分数标准化", "NORMALIZE(close, 20)")

# ── Math ──
_reg("ABS", "math", "ABS(x)", "Absolute value", "绝对值", "ABS(DELTA(close, 5))")
_reg("LOG", "math", "LOG(x)", "Natural logarithm (ln)", "自然对数", "LOG(volume)")
_reg("SIGN", "math", "SIGN(x)", "Sign: -1, 0, or 1", "符号函数", "SIGN(ROC(close, 5))")
_reg("SQRT", "math", "SQRT(x)", "Square root", "平方根", "SQRT(ATR(high,low,close,14))")
_reg("EXP", "math", "EXP(x)", "Exponential (e^x)", "指数函数", "EXP(-RSI(close,14)/100)")
_reg("POW", "math", "POW(x, n)", "Power: x^n", "幂运算", "POW(ROC(close,10), 2)")
_reg("MAX", "math", "MAX(a, b)", "Element-wise maximum", "逐元素取最大", "MAX(SMA(close,10), SMA(close,20))")
_reg("MIN", "math", "MIN(a, b)", "Element-wise minimum", "逐元素取最小", "MIN(low, DELAY(low,1))")
_reg("CLAMP", "math", "CLAMP(x, lo, hi)", "Clip values to [lo, hi] range", "截断到范围", "CLAMP(RSI(close,14), 30, 70)")

# ── Conditional ──
_reg("IF", "conditional", "IF(cond, then_val, else_val)", "Conditional: if cond then A else B", "条件选择", "IF(ROC(close,5) > 0, 1, -1)")
_reg("AND", "conditional", "AND(a, b)", "Logical AND (element-wise)", "逻辑与", "AND(RSI(close,14) > 30, RSI(close,14) < 70)")
_reg("OR", "conditional", "OR(a, b)", "Logical OR (element-wise)", "逻辑或", "OR(RSI(close,14) < 30, RSI(close,14) > 70)")
_reg("NOT", "conditional", "NOT(x)", "Logical NOT (element-wise)", "逻辑非", "NOT(ROC(close,5) > 0)")

# Category labels for frontend display
CATEGORY_LABELS = {
    "moving_average": {"en": "Moving Average", "zh": "移动平均"},
    "momentum": {"en": "Momentum", "zh": "动量"},
    "trend": {"en": "Trend", "zh": "趋势"},
    "volatility": {"en": "Volatility", "zh": "波动率"},
    "volume": {"en": "Volume", "zh": "成交量"},
    "time_series": {"en": "Time Series Operators", "zh": "时间序列算子"},
    "cross_section": {"en": "Cross-Section", "zh": "截面"},
    "math": {"en": "Math", "zh": "数学"},
    "conditional": {"en": "Conditional / Logic", "zh": "条件/逻辑"},
}

# Cleanup helper
del _reg


class FactorExpressionEngine:
    """Evaluate factor expressions safely using asteval + fin-primitives."""

    # Legacy compat — FUNCTION_DOCS derived from FUNCTION_REGISTRY
    FUNCTION_DOCS = {
        name: f"{meta['signature']} - {meta['description']}"
        for name, meta in FUNCTION_REGISTRY.items()
    }

    def __init__(self):
        self._ta = None

    def _ensure_ta(self):
        if self._ta is None:
            import fin_primitives.pandas  # noqa: F401  (registers the .fp accessor)
            self._ta = True

    def _to_series(self, x) -> pd.Series:
        if isinstance(x, pd.Series):
            return x
        if isinstance(x, pd.DataFrame):
            return x.iloc[:, 0]
        return pd.Series(x, dtype=float)

    def _safe_float(self, x):
        """Ensure Series is float dtype (fixes bool/int ufunc issues)."""
        sr = self._to_series(x)
        if sr.dtype == bool or sr.dtype == object:
            return sr.astype(float)
        return sr

    def _build_functions(self, df: pd.DataFrame) -> Dict:
        """Build function dict bound to the given DataFrame context."""
        self._ensure_ta()
        s = self._to_series
        sf = self._safe_float

        def ohlcv(**cols):
            return pd.DataFrame({k: s(v) for k, v in cols.items()}).fp

        funcs = {}

        # ── Moving Average ──
        funcs["SMA"] = lambda series, period=20: s(series).fp.sma(length=int(period))
        funcs["EMA"] = lambda series, period=20: s(series).fp.ema(length=int(period))
        funcs["WMA"] = lambda series, period=20: s(series).fp.wma(length=int(period))
        funcs["DEMA"] = lambda series, period=20: s(series).fp.dema(length=int(period))
        funcs["TEMA"] = lambda series, period=20: s(series).fp.tema(length=int(period))
        funcs["HMA"] = lambda series, period=20: s(series).fp.hma(length=int(period))
        funcs["KAMA"] = lambda series, period=20: s(series).fp.kama(length=int(period))

        # ── Momentum ──
        funcs["RSI"] = lambda series, period=14: s(series).fp.rsi(length=int(period))
        funcs["ROC"] = lambda series, period=10: s(series).fp.roc(length=int(period))
        funcs["MOM"] = lambda series, period=10: s(series).fp.mom(length=int(period))

        def _macd_col(series, fast=12, slow=26, signal=9, col=0):
            r = s(series).fp.macd(fast=int(fast), slow=int(slow), signal=int(signal))
            if r is not None and r.shape[1] > col:
                return r.iloc[:, col]
            return s(series) * 0

        funcs["MACD"] = lambda series, fast=12, slow=26, signal=9: _macd_col(series, fast, slow, signal, 0)
        funcs["MACD_SIGNAL"] = lambda series, fast=12, slow=26, signal=9: _macd_col(series, fast, slow, signal, 1)
        funcs["MACD_HIST"] = lambda series, fast=12, slow=26, signal=9: _macd_col(series, fast, slow, signal, 2)

        def _stoch_col(high, low, close, period=14, col=0):
            r = ohlcv(high=high, low=low, close=close).stoch(k=int(period))
            if r is not None and r.shape[1] > col:
                return r.iloc[:, col]
            return s(close) * 0

        funcs["STOCH_K"] = lambda h, l, c, period=14: _stoch_col(h, l, c, period, 0)
        funcs["STOCH_D"] = lambda h, l, c, period=14: _stoch_col(h, l, c, period, 1)
        funcs["CCI"] = lambda h, l, c, period=20: ohlcv(high=h, low=l, close=c).cci(length=int(period))
        funcs["WILLR"] = lambda h, l, c, period=14: ohlcv(high=h, low=l, close=c).willr(length=int(period))
        funcs["PPO"] = lambda series, fast=12, slow=26: s(series).fp.ppo(fast=int(fast), slow=int(slow)).iloc[:, 0]
        funcs["TRIX"] = lambda series, period=15: s(series).fp.trix(length=int(period)).iloc[:, 0]

        # ── Trend ──
        def _adx_col(high, low, close, period=14, col=0):
            r = ohlcv(high=high, low=low, close=close).adx(length=int(period))
            if r is not None and r.shape[1] > col:
                return r.iloc[:, col]
            return s(close) * 0

        funcs["ADX"] = lambda h, l, c, period=14: _adx_col(h, l, c, period, 0)
        funcs["PLUS_DI"] = lambda h, l, c, period=14: _adx_col(h, l, c, period, 1)
        funcs["MINUS_DI"] = lambda h, l, c, period=14: _adx_col(h, l, c, period, 2)

        def _aroon_col(high, low, period=25, col=0):
            r = ohlcv(high=high, low=low).aroon(length=int(period))
            if r is not None and r.shape[1] > col:
                return r.iloc[:, col]
            return s(high) * 0

        funcs["AROON_UP"] = lambda h, l, period=25: _aroon_col(h, l, period, 1)
        funcs["AROON_DOWN"] = lambda h, l, period=25: _aroon_col(h, l, period, 0)

        # ── Volatility ──
        funcs["ATR"] = lambda h, l, c, period=14: ohlcv(high=h, low=l, close=c).atr(length=int(period))
        funcs["NATR"] = lambda h, l, c, period=14: ohlcv(high=h, low=l, close=c).natr(length=int(period))
        funcs["TRUE_RANGE"] = lambda h, l, c: ohlcv(high=h, low=l, close=c).true_range()
        funcs["STDDEV"] = lambda series, period=20: s(series).rolling(window=int(period)).std()

        def _bb(series, period=20, col_idx=0):
            r = s(series).fp.bbands(length=int(period))
            if r is not None and r.shape[1] > col_idx:
                return r.iloc[:, col_idx]
            return s(series) * 0

        funcs["BBANDS_LOWER"] = lambda series, period=20: _bb(series, period, 0)
        funcs["BBANDS_MID"] = lambda series, period=20: _bb(series, period, 1)
        funcs["BBANDS_UPPER"] = lambda series, period=20: _bb(series, period, 2)

        # ── Volume ──
        funcs["OBV"] = lambda close, volume: ohlcv(close=close, volume=volume).obv()
        funcs["VWAP"] = lambda h, l, c, v: ohlcv(high=h, low=l, close=c, volume=v).vwap()
        funcs["AD"] = lambda h, l, c, v: ohlcv(high=h, low=l, close=c, volume=v).ad()
        funcs["CMF"] = lambda h, l, c, v, period=20: ohlcv(high=h, low=l, close=c, volume=v).cmf(length=int(period))
        funcs["MFI"] = lambda h, l, c, v, period=14: ohlcv(high=h, low=l, close=c, volume=v).mfi(length=int(period))

        # ── Time Series Operators ──
        funcs["DELAY"] = lambda series, period=1: s(series).shift(int(period))
        funcs["DELTA"] = lambda series, period=1: s(series).diff(int(period))
        funcs["TS_SUM"] = lambda series, period=20: s(series).rolling(window=int(period)).sum()
        funcs["TS_MEAN"] = lambda series, period=20: s(series).rolling(window=int(period)).mean()
        funcs["TS_STD"] = lambda series, period=20: s(series).rolling(window=int(period)).std()
        funcs["TS_MAX"] = lambda series, period=20: s(series).rolling(window=int(period)).max()
        funcs["TS_MIN"] = lambda series, period=20: s(series).rolling(window=int(period)).min()

        def _ts_rank(series, period=20):
            sr = s(series)
            return sr.rolling(window=int(period)).apply(
                lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
            )
        funcs["TS_RANK"] = _ts_rank

        def _ts_argmax(series, period=20):
            sr = s(series)
            return sr.rolling(window=int(period)).apply(
                lambda x: int(period) - 1 - np.argmax(x), raw=True
            )
        funcs["TS_ARGMAX"] = _ts_argmax

        def _ts_argmin(series, period=20):
            sr = s(series)
            return sr.rolling(window=int(period)).apply(
                lambda x: int(period) - 1 - np.argmin(x), raw=True
            )
        funcs["TS_ARGMIN"] = _ts_argmin

        funcs["TS_CORR"] = lambda a, b, period=20: s(a).rolling(window=int(period)).corr(s(b))
        funcs["TS_COV"] = lambda a, b, period=20: s(a).rolling(window=int(period)).cov(s(b))
        funcs["TS_SKEW"] = lambda series, period=20: s(series).rolling(window=int(period)).skew()
        funcs["TS_KURT"] = lambda series, period=20: s(series).rolling(window=int(period)).kurt()

        def _decaylinear(series, period=10):
            sr = s(series)
            w = np.arange(1, int(period) + 1, dtype=float)
            w = w / w.sum()
            return sr.rolling(window=int(period)).apply(lambda x: np.dot(x, w), raw=True)
        funcs["DECAYLINEAR"] = _decaylinear

        funcs["LOG_RETURN"] = lambda series, period=1: np.log(s(series) / s(series).shift(int(period)))
        funcs["TS_PCT_CHANGE"] = lambda series, period=1: s(series).pct_change(periods=int(period))

        # ── Cross-section ──
        funcs["RANK"] = lambda series: s(series).rank(pct=True)
        funcs["ZSCORE"] = lambda series: (s(series) - s(series).mean()) / (s(series).std() + 1e-10)

        def _normalize(series, period=20):
            sr = s(series)
            rm = sr.rolling(window=int(period)).mean()
            rs = sr.rolling(window=int(period)).std()
            return (sr - rm) / (rs + 1e-10)
        funcs["NORMALIZE"] = _normalize

        # ── Math ──
        funcs["ABS"] = lambda x: np.abs(sf(x))
        funcs["LOG"] = lambda x: np.log(sf(x).clip(lower=1e-10))
        funcs["SIGN"] = lambda x: np.sign(sf(x))
        funcs["SQRT"] = lambda x: np.sqrt(sf(x).clip(lower=0))
        funcs["EXP"] = lambda x: np.exp(sf(x).clip(upper=500))
        funcs["POW"] = lambda x, n: np.power(sf(x), float(n))
        funcs["MAX"] = lambda a, b: np.maximum(sf(a), sf(b))
        funcs["MIN"] = lambda a, b: np.minimum(sf(a), sf(b))
        funcs["CLAMP"] = lambda x, lo, hi: sf(x).clip(lower=float(lo), upper=float(hi))

        # ── Conditional ──
        def _if(cond, then_val, else_val):
            c = sf(cond)
            t = sf(then_val) if hasattr(then_val, '__len__') else float(then_val)
            e = sf(else_val) if hasattr(else_val, '__len__') else float(else_val)
            return pd.Series(np.where(c != 0, t, e), index=c.index)
        funcs["IF"] = _if
        # Alias
        funcs["WHERE"] = _if

        funcs["AND"] = lambda a, b: (sf(a) != 0) & (sf(b) != 0)
        funcs["OR"] = lambda a, b: (sf(a) != 0) | (sf(b) != 0)
        funcs["NOT"] = lambda x: ~(sf(x) != 0)

        return funcs

    def get_registry_grouped(self) -> Dict:
        """Return FUNCTION_REGISTRY grouped by category with labels."""
        groups = {}
        for name, meta in FUNCTION_REGISTRY.items():
            cat = meta["category"]
            if cat not in groups:
                labels = CATEGORY_LABELS.get(cat, {"en": cat, "zh": cat})
                groups[cat] = {"label": labels["en"], "label_zh": labels["zh"], "functions": []}
            groups[cat]["functions"].append({"name": name, **meta})
        return groups

    def validate(self, expression: str) -> Tuple[bool, str]:
        """Validate expression syntax without executing. Returns (ok, error_msg)."""
        if not expression or not expression.strip():
            return False, "Expression is empty"
        if len(expression) > 500:
            return False, "Expression too long (max 500 chars)"

        try:
            aeval = Interpreter(minimal=True)
            aeval.parse(expression)
            if aeval.error:
                errors = "; ".join(str(e.get_error()[1]) for e in aeval.error)
                return False, f"Syntax error: {errors}"
        except SyntaxError as e:
            return False, f"Syntax error: {str(e) or 'invalid expression'}"
        except Exception as e:
            return False, f"Parse error: {str(e)}"
        return True, ""

    def execute(self, expression: str, klines: List[Dict]) -> Tuple[Optional[pd.Series], str]:
        """
        Execute expression against K-line data.
        Returns (result_series, error_msg). result_series is None on error.
        """
        ok, err = self.validate(expression)
        if not ok:
            return None, err

        if not klines or len(klines) < 10:
            return None, "Insufficient K-line data (need at least 10 bars)"

        # Build DataFrame from klines
        df = pd.DataFrame(klines)
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Create safe interpreter
        aeval = Interpreter(minimal=True)

        # Inject K-line columns as variables
        aeval.symtable["open"] = df["open"]
        aeval.symtable["high"] = df["high"]
        aeval.symtable["low"] = df["low"]
        aeval.symtable["close"] = df["close"]
        aeval.symtable["volume"] = df["volume"]

        # Inject TA functions
        for name, func in self._build_functions(df).items():
            aeval.symtable[name] = func

        # Inject numpy for arithmetic
        aeval.symtable["np"] = np

        # Execute
        try:
            result = aeval(expression)
        except Exception as e:
            return None, f"Execution error: {str(e)}"

        if aeval.error:
            errors = "; ".join(str(e.get_error()[1]) for e in aeval.error)
            return None, f"Evaluation error: {errors}"

        if result is None:
            return None, "Expression returned None"

        # Convert to Series
        if isinstance(result, pd.Series):
            # Ensure float dtype for downstream IC calculation
            if result.dtype == bool:
                result = result.astype(float)
            return result, ""
        if isinstance(result, pd.DataFrame):
            col = result.iloc[:, 0]
            if col.dtype == bool:
                col = col.astype(float)
            return col, ""
        if isinstance(result, (np.ndarray, list)):
            return pd.Series(result, dtype=float), ""
        if isinstance(result, (int, float)):
            return pd.Series([result] * len(df), dtype=float), ""

        return None, f"Unexpected result type: {type(result).__name__}"

    def evaluate_ic(
        self,
        expression: str,
        klines: List[Dict],
        forward_periods: Dict[str, int] = None,
    ) -> Tuple[Optional[Dict], str]:
        """
        Evaluate expression and compute IC/ICIR/win_rate for each forward period.
        Returns (results_dict, error_msg).
        """
        if forward_periods is None:
            forward_periods = {"1h": 1, "4h": 4, "12h": 12, "24h": 24}

        series, err = self.execute(expression, klines)
        if series is None:
            return None, err

        closes = pd.to_numeric(pd.DataFrame(klines)["close"], errors="coerce")
        factor_vals = series.values.astype(float)
        close_vals = closes.values
        n = len(factor_vals)

        from scipy.stats import spearmanr

        results = {}
        for fp_label, fp_offset in forward_periods.items():
            if fp_offset >= n - 10:
                continue

            aligned_fv, aligned_rt = [], []
            for i in range(n - fp_offset):
                fv = factor_vals[i]
                cv = close_vals[i]
                if pd.isna(fv) or pd.isna(cv) or cv == 0:
                    continue
                ret = (close_vals[i + fp_offset] - cv) / cv
                aligned_fv.append(fv)
                aligned_rt.append(ret)

            if len(aligned_fv) < 10:
                continue

            fv_arr = np.array(aligned_fv)
            rt_arr = np.array(aligned_rt)

            ic, _ = spearmanr(fv_arr, rt_arr)
            ic = float(ic) if not np.isnan(ic) else 0.0

            # Rolling IC for ICIR
            window = min(20, max(5, len(aligned_fv) // 4))
            ics = []
            if window >= 5 and len(aligned_fv) >= window * 2:
                for i in range(len(aligned_fv) - window + 1):
                    c, _ = spearmanr(fv_arr[i:i+window], rt_arr[i:i+window])
                    if not np.isnan(c):
                        ics.append(c)

            ic_mean = float(np.mean(ics)) if ics else ic
            ic_std = float(np.std(ics)) if ics else 0.0
            icir = ic_mean / ic_std if ic_std > 1e-8 else 0.0

            signs_match = np.sign(fv_arr) == np.sign(rt_arr)
            win_rate = float(signs_match.mean())

            results[fp_label] = {
                "ic_mean": round(ic_mean, 6),
                "ic_std": round(ic_std, 6),
                "icir": round(icir, 4),
                "win_rate": round(win_rate, 4),
                "sample_count": len(aligned_fv),
            }

        if not results:
            return None, "Not enough aligned data for IC calculation"

        return results, ""


# Singleton
factor_expression_engine = FactorExpressionEngine()
