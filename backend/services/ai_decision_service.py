"""
AI Decision Service - Handles AI model API calls for trading decisions
"""
import logging
import random
import json
import time
import re
from decimal import Decimal
from typing import Any, Dict, Optional, List
from datetime import datetime

import requests
from sqlalchemy.orm import Session

from database.models import Position, Account, AIDecisionLog
from services.asset_calculator import calc_positions_value
from services.news_feed import fetch_latest_news
from repositories.strategy_repo import set_last_trigger
from services.system_logger import system_logger
from repositories import prompt_repo


logger = logging.getLogger(__name__)

#  mode API keys that should be skipped
DEMO_API_KEYS = {
    "default-key-please-update-in-settings",
    "default",
    "",
    None
}

SUPPORTED_SYMBOLS: Dict[str, str] = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "DOGE": "Dogecoin",
    "XRP": "Ripple",
    "BNB": "Binance Coin",
}


class SafeDict(dict):
    def __missing__(self, key):  # type: ignore[override]
        return "N/A"


def _format_currency(value: Optional[float], precision: int = 2, default: str = "N/A") -> str:
    try:
        if value is None:
            return default
        return f"{float(value):,.{precision}f}"
    except (TypeError, ValueError):
        return default


def _format_quantity(value: Optional[float], precision: int = 6, default: str = "0") -> str:
    try:
        if value is None:
            return default
        return f"{float(value):.{precision}f}"
    except (TypeError, ValueError):
        return default


def _get_metric_unit(metric: str) -> str:
    """Get the unit for a signal metric type."""
    # Percentage-based metrics
    percent_metrics = {
        "oi_delta", "price_change_percent", "volume_change_percent",
        "funding", "funding_rate"
    }
    # Ratio-based metrics (no unit, just a number)
    # taker_ratio is now log-transformed, symmetric around 0
    ratio_metrics = {"depth_ratio", "order_imbalance", "imbalance", "taker_ratio"}
    # USD-based metrics
    usd_metrics = {"oi", "cvd", "volume", "taker_volume"}

    metric_lower = metric.lower() if metric else ""
    if metric_lower in percent_metrics or "percent" in metric_lower:
        return "%"
    elif metric_lower in usd_metrics:
        return ""  # USD values are typically formatted separately
    elif metric_lower in ratio_metrics:
        return ""  # Ratios are dimensionless
    return ""


def get_max_tokens(model: str) -> int:
    """
    Get recommended max_tokens value based on model name.

    Different models have different max output token limits:
    - GPT-4-turbo: 4096 (needs special handling)
    - GPT-4o/4o-mini: 16384 (use 8000 for cost balance)
    - o1/o1-mini: 65536-100000 (use 12000-16000)
    - Claude: 64000 (use 12000 for cost balance)
    - Deepseek V4 Flash: 16000
    - Deepseek V4 Pro: 32000
    - Qwen: 8000-65536 (use 8000-16000)

    Args:
        model: Model name (e.g., "gpt-4-turbo", "claude-3-5-sonnet-20241022")

    Returns:
        Recommended max_tokens value (fallback: 4000 for unknown models)
    """
    model_lower = model.lower()

    # Special case: GPT-4-turbo has max output limit of 4096
    if 'gpt-4-turbo' in model_lower:
        return 4000

    # GPT-4.1 (ultra-large context model)
    if 'gpt-4.1' in model_lower:
        return 16000

    # DeepSeek V4 series (max output 384K, use 32000 for cost balance)
    if 'deepseek-v4-pro' in model_lower:
        return 32000
    if 'deepseek-v4-flash' in model_lower:
        return 16000

    # Legacy DeepSeek reasoning models (mapped to v4-flash by API)
    if 'deepseek-reasoner' in model_lower:
        return 16000

    # o1 series (note order: check o1-mini first, then o1)
    if 'o1-mini' in model_lower:
        return 12000
    if 'o1' in model_lower:
        return 16000

    # GPT-4o series
    if 'gpt-4o' in model_lower:
        return 8000

    # Claude series
    if 'claude' in model_lower:
        return 12000

    # Qwen series (note order: check qwen3 first, then qwen)
    if 'qwen3' in model_lower:
        return 16000
    if 'qwen' in model_lower:
        return 8000

    # GLM series (Z.ai models like GLM-4.7)
    if 'glm' in model_lower:
        return 16000

    # MiniMax M2 series
    if 'minimax' in model_lower:
        return 16000

    # Deepseek V4 series
    if 'deepseek-v4' in model_lower:
        return 16000

    # Legacy Deepseek-chat (mapped to v4-flash by API)
    if 'deepseek' in model_lower:
        return 16000

    # Fallback for unknown models (conservative safe value)
    return 4000


def _build_session_context(account: Account) -> str:
    """Build session context (legacy format for backward compatibility)"""
    now = datetime.utcnow()
    runtime_minutes = "N/A"

    created_at = getattr(account, "created_at", None)
    if isinstance(created_at, datetime):
        created = created_at.replace(tzinfo=None) if created_at.tzinfo else created_at
        runtime_minutes = str(max(0, int((now - created).total_seconds() // 60)))

    lines = [
        f"TRADER_ID: {account.name}",
        f"MODEL: {account.model or 'N/A'}",
        f"RUNTIME_MINUTES: {runtime_minutes}",
        "INVOCATION_COUNT: N/A",
        f"CURRENT_TIME_UTC: {now.isoformat()}",
    ]
    return "\n".join(lines)


def _calculate_runtime_minutes(account: Account) -> str:
    """Calculate runtime minutes for Alpha Arena style prompts"""
    created_at = getattr(account, "created_at", None)
    if isinstance(created_at, datetime):
        now = datetime.utcnow()
        created = created_at.replace(tzinfo=None) if created_at.tzinfo else created_at
        return str(max(0, int((now - created).total_seconds() // 60)))
    return "0"


def _calculate_total_return_percent(account: Account) -> str:
    """Calculate total return percentage"""
    initial_cash = float(getattr(account, "initial_cash", 0) or 10000)
    current_total = float(getattr(account, "current_cash", 0))

    # Add positions value if available
    try:
        from services.asset_calculator import calc_positions_value
        from database.connection import SessionLocal
        db = SessionLocal()
        try:
            positions_value = calc_positions_value(db, account.id)
            current_total += positions_value
        finally:
            db.close()
    except Exception:
        pass

    if initial_cash > 0:
        return_pct = ((current_total - initial_cash) / initial_cash) * 100
        return f"{return_pct:+.2f}"
    return "0.00"


def _build_holdings_detail(positions: Dict[str, Dict[str, Any]]) -> str:
    """Build detailed holdings list for Alpha Arena style prompts"""
    if not positions:
        return "- None (all cash)"

    lines = []
    for symbol, data in positions.items():
        qty = data.get('quantity', 0)
        avg_cost = data.get('avg_cost', 0)
        current_value = data.get('current_value', 0)

        lines.append(
            f"- {symbol}: {_format_quantity(qty)} units @ ${_format_currency(avg_cost, precision=4)} avg "
            f"(current value: ${_format_currency(current_value)})"
        )

    return "\n".join(lines)


def _build_market_prices(
    prices: Dict[str, float],
    symbol_order: Optional[List[str]] = None,
    symbol_names: Optional[Dict[str, str]] = None,
) -> str:
    """Build simple market prices list for Alpha Arena style prompts"""
    order = symbol_order or list(SUPPORTED_SYMBOLS.keys())
    lines = []
    for symbol in order:
        price = prices.get(symbol)
        display_name = (symbol_names or {}).get(symbol)
        label = symbol if not display_name or display_name == symbol else f"{symbol} ({display_name})"
        if price:
            lines.append(f"{label}: ${_format_currency(price, precision=4)}")
        else:
            lines.append(f"{label}: N/A")

    return "\n".join(lines)


def _get_realtime_ticker_snapshot(
    symbols: List[str],
    environment: str = "mainnet",
    exchange: str = "hyperliquid",
) -> Dict[str, Dict[str, Any]]:
    """Fetch a single realtime ticker snapshot for all symbols in this prompt build."""
    from services.market_data import get_ticker_data

    market_param = "binance" if exchange == "binance" else "CRYPTO"
    snapshot: Dict[str, Dict[str, Any]] = {}

    for symbol in symbols:
        try:
            ticker = get_ticker_data(symbol, market_param, environment)
            if ticker and float(ticker.get("price", 0) or 0) > 0:
                snapshot[symbol] = ticker
        except Exception as err:
            logger.warning(f"Failed to fetch realtime ticker for {symbol} ({exchange}/{environment}): {err}")

    return snapshot


def _format_market_data_block(symbol: str, ticker: Dict[str, Any]) -> str:
    """Format {SYMBOL_market_data} from one ticker snapshot."""
    market_data_lines = [
        f"Symbol: {symbol}",
        f"Price: ${ticker['price']:.2f}",
        f"24h Change: {ticker['change24h']:+.2f} ({ticker['percentage24h']:+.2f}%)",
        f"24h Volume: ${ticker['volume24h']:,.0f}",
    ]
    if 'open_interest' in ticker:
        market_data_lines.append(f"Open Interest: ${ticker['open_interest']:,.0f}")
    if 'funding_rate' in ticker:
        market_data_lines.append(f"Funding Rate: {ticker['funding_rate'] * 100:.4f}%")
    return "\n".join(market_data_lines)


def _normalize_symbol_metadata(
    symbol_metadata: Optional[Dict[str, Any]],
    fallback_symbols: List[str],
) -> Dict[str, Dict[str, Optional[str]]]:
    """Normalize symbol metadata into a consistent mapping."""
    normalized: Dict[str, Dict[str, Optional[str]]] = {}

    if symbol_metadata:
        for raw_symbol, meta in symbol_metadata.items():
            symbol = str(raw_symbol).upper()
            if isinstance(meta, dict):
                normalized[symbol] = {
                    "name": meta.get("name") or meta.get("display_name") or symbol,
                    "type": meta.get("type") or meta.get("category"),
                }
            else:
                display = str(meta).strip()
                normalized[symbol] = {
                    "name": display or symbol,
                    "type": None,
                }

    for symbol in fallback_symbols:
        normalized.setdefault(
            symbol,
            {
                "name": SUPPORTED_SYMBOLS.get(symbol, symbol),
                "type": None,
            },
        )

    if not normalized:
        for symbol, display in SUPPORTED_SYMBOLS.items():
            normalized[symbol] = {"name": display, "type": None}

    return normalized


def _build_account_state(portfolio: Dict[str, Any]) -> str:
    positions: Dict[str, Dict[str, Any]] = portfolio.get("positions", {})
    lines = [
        f"Available Cash (USD): {_format_currency(portfolio.get('cash'))}",
        f"Frozen Cash (USD): {_format_currency(portfolio.get('frozen_cash'))}",
        f"Total Assets (USD): {_format_currency(portfolio.get('total_assets'))}",
        "",
        "Open Positions:",
    ]

    if positions:
        for symbol, data in positions.items():
            lines.append(
                f"- {symbol}: qty={_format_quantity(data.get('quantity'))}, "
                f"avg_cost={_format_currency(data.get('avg_cost'))}, "
                f"current_value={_format_currency(data.get('current_value'))}"
            )
    else:
        lines.append("- None")

    return "\n".join(lines)


def _build_sampling_data(samples: Optional[List], target_symbol: Optional[str], sampling_interval: Optional[int] = None) -> str:
    """Build sampling pool data section for Alpha Arena style prompts (single symbol)"""
    if not samples or not target_symbol:
        return "No sampling data available."

    interval_text = f"{sampling_interval}-second intervals" if sampling_interval else "unknown intervals"
    lines = [
        f"Multi-timeframe price data for {target_symbol} ({interval_text}, oldest to newest):",
        f"Total samples: {len(samples)}",
        ""
    ]

    # Format samples in Alpha Arena style - chronological order (oldest to newest)
    for i, sample in enumerate(samples):
        timestamp = sample.get('datetime', 'N/A')
        price = sample.get('price', 0)
        # Format timestamp to be more readable
        if timestamp != 'N/A':
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M:%S')
            except:
                time_str = timestamp
        else:
            time_str = 'N/A'

        lines.append(f"T-{len(samples)-i-1}: ${price:.6f} ({time_str})")

    # Calculate price momentum and trend
    if len(samples) >= 2:
        first_price = samples[0].get('price', 0)
        last_price = samples[-1].get('price', 0)
        if first_price > 0:
            change_pct = ((last_price - first_price) / first_price) * 100
            trend = "BULLISH" if change_pct > 0 else "BEARISH" if change_pct < 0 else "NEUTRAL"
            lines.append("")
            lines.append(f"Price momentum: {change_pct:+.3f}% ({trend})")
            lines.append(f"Range: ${first_price:.6f} → ${last_price:.6f}")

    return "\n".join(lines)


def _build_multi_symbol_sampling_data(symbols: List[str], sampling_pool, sampling_interval: Optional[int] = None) -> str:
    """Build sampling pool data for multiple symbols (Alpha Arena style)"""
    if not symbols:
        return "No symbols selected for sampling data."

    sections = []
    interval_text = f"{sampling_interval}-second intervals" if sampling_interval else "unknown intervals"

    for symbol in symbols:
        samples = sampling_pool.get_samples(symbol)
        if not samples:
            sections.append(f"{symbol}: No sampling data available")
            continue

        lines = [
            f"{symbol} ({interval_text}, oldest to newest):",
            f"Total samples: {len(samples)}",
            ""
        ]

        # Format samples
        for i, sample in enumerate(samples):
            timestamp = sample.get('datetime', 'N/A')
            price = sample.get('price', 0)
            if timestamp != 'N/A':
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime('%H:%M:%S')
                except:
                    time_str = timestamp
            else:
                time_str = 'N/A'

            lines.append(f"T-{len(samples)-i-1}: ${price:.6f} ({time_str})")

        # Calculate momentum
        if len(samples) >= 2:
            first_price = samples[0].get('price', 0)
            last_price = samples[-1].get('price', 0)
            if first_price > 0:
                change_pct = ((last_price - first_price) / first_price) * 100
                trend = "BULLISH" if change_pct > 0 else "BEARISH" if change_pct < 0 else "NEUTRAL"
                lines.append("")
                lines.append(f"Price momentum: {change_pct:+.3f}% ({trend})")
                lines.append(f"Range: ${first_price:.6f} → ${last_price:.6f}")

        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def _build_market_snapshot(
    prices: Dict[str, float],
    positions: Dict[str, Dict[str, Any]],
    symbol_order: Optional[List[str]] = None,
) -> str:
    lines: List[str] = []
    order = symbol_order or list(SUPPORTED_SYMBOLS.keys())
    for symbol in order:
        price = prices.get(symbol)
        position = positions.get(symbol, {})

        parts = [f"{symbol}: price={_format_currency(price, precision=4)}"]
        if position:
            parts.append(f"qty={_format_quantity(position.get('quantity'))}")
            parts.append(f"avg_cost={_format_currency(position.get('avg_cost'), precision=4)}")
            parts.append(f"position_value={_format_currency(position.get('current_value'))}")
        else:
            parts.append("position=flat")

        lines.append(", ".join(parts))

    return "\n".join(lines) if lines else "No market data available."


SYMBOL_PLACEHOLDER = "__SYMBOL_SET__"
OUTPUT_FORMAT_JSON = (
    '{\n'
    '  "decisions": [\n'
    '    {\n'
    '      "operation": "buy" | "sell" | "hold" | "close",\n'
    '      "symbol": "<' + SYMBOL_PLACEHOLDER + '>",\n'
    '      "target_portion_of_balance": <float 0.0-1.0>,\n'
    '      "leverage": <integer 1-20>,\n'
    '      "max_price": <number, required for "buy" operations>,\n'
    '      "min_price": <number, required for "sell"/"close" operations>,\n'
    '      "time_in_force": "Ioc" | "Gtc" | "Alo",\n'
    '      "take_profit_price": <number, optional, take profit trigger price>,\n'
    '      "stop_loss_price": <number, optional, stop loss trigger price>,\n'
    '      "tp_execution": "market" | "limit",\n'
    '      "sl_execution": "market" | "limit",\n'
    '      "reason": "<string explaining primary signals>",\n'
    '      "trading_strategy": "<string covering thesis, risk controls, and exit plan>"\n'
    '    }\n'
    '  ]\n'
    '}'
)

# Placeholder for max leverage in output format template
MAX_LEVERAGE_PLACEHOLDER = "__MAX_LEVERAGE__"

# Complete OUTPUT FORMAT template with all requirements and examples
# Uses double-brace escaping for JSON literals to avoid format_map() conflicts
OUTPUT_FORMAT_COMPLETE = """Respond with ONLY a JSON object using this schema (always emitting the `decisions` array even if it is empty):
{{
  "decisions": [
    {{
      "operation": "buy" | "sell" | "hold" | "close",
      "symbol": "<__SYMBOL_SET__>",
      "target_portion_of_balance": <float 0.0-1.0>,
      "leverage": <integer 1-__MAX_LEVERAGE__>,
      "max_price": <number, required for "buy" operations>,
      "min_price": <number, required for "sell"/"close" operations>,
      "time_in_force": "Ioc" | "Gtc" | "Alo",
      "take_profit_price": <number, optional>,
      "stop_loss_price": <number, optional>,
      "tp_execution": "market" | "limit",
      "sl_execution": "market" | "limit",
      "reason": "<string explaining primary signals>",
      "trading_strategy": "<string covering thesis, risk controls, and exit plan>"
    }}
  ]
}}

CRITICAL OUTPUT REQUIREMENTS:
- Output MUST be a single, valid JSON object only
- NO markdown code blocks (no ```json``` wrappers)
- NO explanatory text before or after the JSON
- NO comments or additional content outside the JSON object
- Ensure all JSON fields are properly quoted and formatted
- Double-check JSON syntax before responding

Example output with multiple simultaneous orders:
{{
  "decisions": [
    {{
      "operation": "buy",
      "symbol": "BTC",
      "target_portion_of_balance": 0.3,
      "leverage": 3,
      "max_price": 49500,
      "time_in_force": "Ioc",
      "take_profit_price": 52000,
      "stop_loss_price": 47500,
      "tp_execution": "limit",
      "sl_execution": "market",
      "reason": "Strong bullish momentum with support holding at $48k, RSI recovering from oversold",
      "trading_strategy": "Opening 3x leveraged long position with 30% balance. Take profit at $52k resistance (+5%), stop loss below $47.5k swing low (-4%). Using IOC for immediate execution."
    }},
    {{
      "operation": "sell",
      "symbol": "ETH",
      "target_portion_of_balance": 0.2,
      "leverage": 2,
      "min_price": 3125,
      "reason": "ETH perp funding flipped elevated negative while momentum weakens",
      "trading_strategy": "Initiating small short hedge until ETH regains strength vs BTC pair. Stop if ETH closes back above $3.2k structural pivot."
    }}
  ]
}}

FIELD TYPE REQUIREMENTS:
- decisions: array (one entry per supported symbol; include HOLD entries with zero allocation when you choose not to act)
- operation: string ("buy" for long, "sell" for short, "hold", or "close")
- symbol: string (exactly one of: __SYMBOL_SET__)
- target_portion_of_balance: number (float between 0.1 and 1.0)
- leverage: integer (between 1 and __MAX_LEVERAGE__, REQUIRED field)
- max_price: number (required for "buy" operations and closing SHORT positions. This is the maximum price you are willing to pay.)
- min_price: number (required for "sell" operations and closing LONG positions. This is the minimum price you are willing to receive.)
- time_in_force: string (optional, default "Ioc") - Order time in force: "Ioc" (immediate or cancel, taker-focused), "Gtc" (good til canceled, may become maker), "Alo" (add liquidity only, maker-only)
- take_profit_price: number (optional but recommended, trigger price for profit taking)
- stop_loss_price: number (optional but recommended, trigger price for loss protection)
- tp_execution: string (optional, default "limit") - TP execution mode: "limit" (attempts maker with 0.05% offset, may save fees but has fill risk), "market" (immediate execution, guarantees fill)
- sl_execution: string (optional, default "limit") - SL execution mode: "limit" (may save fees), "market" (guarantees stop loss execution)
- reason: string explaining the key catalyst, risk, or signal (no strict length limit, but stay focused)
- trading_strategy: string covering entry thesis, leverage reasoning, liquidation awareness, and exit plan

FIELD CLASSIFICATION:
- ALWAYS REQUIRED: operation, symbol, reason, trading_strategy
- REQUIRED FOR buy/sell: target_portion_of_balance, leverage, max_price (buy) or min_price (sell)
- REQUIRED FOR close: target_portion_of_balance, max_price (close short) or min_price (close long)
- OPTIONAL WITH DEFAULTS: time_in_force (default "Ioc"), tp_execution (default "limit"), sl_execution (default "limit")
- OPTIONAL BUT RECOMMENDED: take_profit_price, stop_loss_price

FIELD DEPENDENCIES:
- tp_execution only applies when take_profit_price is set (ignored otherwise)
- sl_execution only applies when stop_loss_price is set (ignored otherwise)"""


DECISION_TASK_TEXT = (
    "You are a systematic trader operating on the Hyper Alpha Arena sandbox (no real funds at risk).\n"
    "- Review every open position and decide: buy_to_enter, sell_to_enter, hold, or close_position.\n"
    "- Avoid pyramiding or increasing size unless an exit plan explicitly allows it.\n"
    "- Respect risk: keep new exposure within reasonable fractions of available cash (default ≤ 0.2).\n"
    "- Close positions when invalidation conditions are met or risk is excessive.\n"
    "- When data is missing (marked N/A), acknowledge uncertainty before deciding.\n"
)


def _build_prompt_context(
    account: Account,
    portfolio: Dict[str, Any],
    prices: Dict[str, float],
    news_section: str,
    samples: Optional[List] = None,
    target_symbol: Optional[str] = None,
    hyperliquid_state: Optional[Dict[str, Any]] = None,
    *,
    db: Optional[Session] = None,
    symbol_metadata: Optional[Dict[str, Any]] = None,
    symbol_order: Optional[List[str]] = None,
    sampling_interval: Optional[int] = None,
    environment: str = "mainnet",
    template_text: Optional[str] = None,
    trigger_context: Optional[Dict[str, Any]] = None,
    exchange: str = "hyperliquid",
) -> Dict[str, Any]:
    """
    Build complete prompt context for AI decision-making.

    ⚠️ CRITICAL: This is the SINGLE and ONLY function responsible for building
    prompt context variables. ALL prompt template variable generation MUST happen
    here to ensure consistency between preview and actual AI decision execution.

    DO NOT create separate context-building logic elsewhere. If you need to add
    new template variables, add them here.

    Args:
        account: Trading account
        portfolio: Portfolio data with positions
        prices: Current market prices
        news_section: Latest news summary
        samples: Legacy price samples (deprecated)
        target_symbol: Legacy single symbol (deprecated)
        hyperliquid_state: Real-time Hyperliquid account state
        db: Database session (required for leverage settings lookup)
        symbol_metadata: Symbol display names and metadata
        symbol_order: Ordered list of symbols
        sampling_interval: Sampling interval in seconds
        environment: Trading environment (mainnet/testnet)
        template_text: Prompt template text for parsing K-line variables
        trigger_context: Context about what triggered this decision (signal or scheduled)
        exchange: Exchange to use for market data ("hyperliquid" or "binance")

    Returns:
        Complete context dictionary ready for template.format_map()
    """
    base_portfolio = portfolio or {}
    base_positions = base_portfolio.get("positions") or {}
    positions: Dict[str, Dict[str, Any]] = {symbol: dict(data) for symbol, data in base_positions.items()}

    symbol_source = symbol_metadata or SUPPORTED_SYMBOLS
    base_order = symbol_order or list(symbol_source.keys())
    ordered_symbols: List[str] = []
    seen_symbols = set()
    for sym in base_order:
        symbol_upper = str(sym).upper()
        if not symbol_upper or symbol_upper in seen_symbols:
            continue
        seen_symbols.add(symbol_upper)
        ordered_symbols.append(symbol_upper)
    if not ordered_symbols:
        ordered_symbols = list(SUPPORTED_SYMBOLS.keys())

    normalized_symbol_metadata = _normalize_symbol_metadata(symbol_metadata, ordered_symbols)
    symbol_display_map = {
        symbol: normalized_symbol_metadata.get(symbol, {}).get("name") or SUPPORTED_SYMBOLS.get(symbol, symbol)
        for symbol in ordered_symbols
    }
    selected_symbols_detail_lines = []
    for symbol in ordered_symbols:
        info = normalized_symbol_metadata.get(symbol, {})
        display_name = info.get("name") or symbol
        symbol_type = info.get("type")
        if symbol_type:
            selected_symbols_detail_lines.append(f"- {symbol}: {display_name} ({symbol_type})")
        else:
            selected_symbols_detail_lines.append(f"- {symbol}: {display_name}")
    selected_symbols_detail = "\n".join(selected_symbols_detail_lines) if selected_symbols_detail_lines else "None configured"
    selected_symbols_csv = ", ".join(ordered_symbols) if ordered_symbols else "N/A"
    output_symbol_choices = "|".join(ordered_symbols) if ordered_symbols else "SYMBOL"

    # NOTE: environment parameter is now passed from caller (call_ai_for_decision)

    # Use Hyperliquid state if provided (indicates Hyperliquid trading mode)
    if hyperliquid_state and environment in ("testnet", "mainnet"):
        hl_positions = hyperliquid_state.get("positions", []) or []
        positions = {}
        for pos in hl_positions:
            symbol = (pos.get("coin") or "").upper()
            if not symbol:
                continue

            quantity = float(pos.get("szi", 0) or 0)
            entry_px = float(pos.get("entry_px", 0) or 0)
            current_value = float(pos.get("position_value", 0) or 0)

            positions[symbol] = {
                "quantity": quantity,
                "avg_cost": entry_px,
                "current_value": current_value,
                "unrealized_pnl": float(pos.get("unrealized_pnl", 0) or 0),
                "leverage": pos.get("leverage"),
                "liquidation_price": pos.get("liquidation_px"),
            }

        portfolio = {
            "cash": float(hyperliquid_state.get("available_balance", 0) or 0),
            "frozen_cash": float(hyperliquid_state.get("used_margin", 0) or 0),
            "total_assets": float(hyperliquid_state.get("total_equity", 0) or 0),
            "positions": positions,
        }
    else:
        portfolio = {
            "cash": base_portfolio.get("cash"),
            "frozen_cash": base_portfolio.get("frozen_cash"),
            "total_assets": base_portfolio.get("total_assets"),
            "positions": positions,
        }

    now = datetime.utcnow()

    realtime_tickers = _get_realtime_ticker_snapshot(ordered_symbols, environment=environment, exchange=exchange)
    effective_prices: Dict[str, float] = dict(prices or {})
    for symbol, ticker in realtime_tickers.items():
        try:
            ticker_price = float((ticker or {}).get("price", 0) or 0)
        except (TypeError, ValueError):
            ticker_price = 0.0
        if ticker_price > 0:
            effective_prices[symbol.upper()] = ticker_price

    # Legacy format variables (for backward compatibility with existing templates)
    account_state = _build_account_state(portfolio)
    market_snapshot = _build_market_snapshot(effective_prices, positions, ordered_symbols)
    session_context = _build_session_context(account)
    sampling_data = _build_sampling_data(samples, target_symbol, sampling_interval)

    # New Alpha Arena style variables
    runtime_minutes = _calculate_runtime_minutes(account)
    current_time_utc = now.isoformat() + "Z"
    total_return_percent = _calculate_total_return_percent(account)
    available_cash = _format_currency(portfolio.get('cash'))
    total_account_value = _format_currency(portfolio.get('total_assets'))
    holdings_detail = _build_holdings_detail(positions)
    market_prices = _build_market_prices(effective_prices, ordered_symbols, symbol_display_map)
    # Legacy format (kept for backward compatibility with old templates)
    output_format_legacy = OUTPUT_FORMAT_JSON.replace(SYMBOL_PLACEHOLDER, output_symbol_choices or "SYMBOL")

    # Get leverage settings from the wallet source that matches the target exchange.
    if db:
        try:
            if exchange == "binance":
                from database.models import BinanceWallet

                wallet = db.query(BinanceWallet).filter(
                    BinanceWallet.account_id == account.id,
                    BinanceWallet.environment == environment,
                    BinanceWallet.is_active == "true"
                ).first()

                if wallet:
                    max_leverage = wallet.max_leverage
                    default_leverage = wallet.default_leverage
                else:
                    logger.warning(
                        f"No Binance wallet found for account {account.id} in {environment}, using defaults"
                    )
                    max_leverage = 20
                    default_leverage = 1
            else:
                from services.hyperliquid_environment import get_leverage_settings

                leverage_settings = get_leverage_settings(db, account.id, environment)
                max_leverage = leverage_settings["max_leverage"]
                default_leverage = leverage_settings["default_leverage"]
        except Exception as e:
            logger.warning(f"Failed to get leverage settings for account {account.id}: {e}, using fallback")
            if exchange == "binance":
                max_leverage = 20
                default_leverage = 1
            else:
                max_leverage = getattr(account, "max_leverage", 3)
                default_leverage = getattr(account, "default_leverage", 1)
    else:
        # Fallback if db not provided (should not happen in normal operation)
        logger.warning(f"No db session provided to _build_prompt_context, using Account table fallback for leverage")
        max_leverage = getattr(account, "max_leverage", 3)
        default_leverage = getattr(account, "default_leverage", 1)

    # Build complete output format with placeholders replaced
    output_format = OUTPUT_FORMAT_COMPLETE.replace(SYMBOL_PLACEHOLDER, output_symbol_choices or "SYMBOL").replace(MAX_LEVERAGE_PLACEHOLDER, str(max_leverage))

    # Use hyperliquid_state to determine if this is Hyperliquid trading mode
    if hyperliquid_state and environment in ("testnet", "mainnet"):
        trading_environment = f"Platform: Hyperliquid Perpetual Contracts | Environment: {environment.upper()}"

        if environment == "mainnet":
            real_trading_warning = "⚠️ REAL MONEY TRADING - All decisions execute on live markets"
            operational_constraints = f"""- Perpetual contract trading with cross margin
- Maximum position size: ≤ 25% of available balance per trade
- Leverage range: 1x to {max_leverage}x (default: {default_leverage}x)
- Margin call threshold: 80% margin usage (CRITICAL - will auto-liquidate)
- Default stop loss: -10% from entry (adjust based on leverage and volatility)
- Default take profit: +20% from entry (adjust based on risk/reward)
- Liquidation protection: NEVER exceed 70% margin usage
- Risk management: Monitor unrealized PnL and margin usage before each trade"""
        else:  # testnet
            real_trading_warning = "Testnet simulation environment (using test funds)"
            operational_constraints = f"""- Perpetual contract trading with cross margin (testnet mode)
- Default position size: ≤ 30% of available balance per trade
- Leverage range: 1x to {max_leverage}x (default: {default_leverage}x)
- Margin call threshold: 80% margin usage
- Default stop loss: -8% from entry (adjust based on leverage)
- Default take profit: +15% from entry
- Liquidation protection: avoid exceeding 70% margin usage"""

        leverage_constraints = f"- Leverage range: 1x to {max_leverage}x (default: {default_leverage}x)"
        margin_info = "\nMargin Mode: Cross margin (shared across all positions)"
    else:
        trading_environment = "Platform: Paper Trading Simulation"
        real_trading_warning = "Sandbox environment (no real funds at risk)"
        operational_constraints = """- No pyramiding or position size increases without explicit exit plan
- Default risk per trade: ≤ 20% of available cash
- Default stop loss: -5% from entry (adjust based on volatility)
- Default take profit: +10% from entry (adjust based on signals)"""
        leverage_constraints = ""
        margin_info = ""

    # Process Hyperliquid account state if provided
    if hyperliquid_state:
        total_equity = _format_currency(hyperliquid_state.get('total_equity'))
        available_balance = _format_currency(hyperliquid_state.get('available_balance'))
        used_margin = _format_currency(hyperliquid_state.get('used_margin', 0))
        margin_usage_percent = f"{hyperliquid_state.get('margin_usage_percent', 0):.1f}"
        maintenance_margin = _format_currency(hyperliquid_state.get('maintenance_margin', 0))

        # Build positions detail from Hyperliquid positions
        hl_positions = hyperliquid_state.get('positions', [])
        if hl_positions:
            pos_lines = []
            for pos in hl_positions:
                symbol = pos.get('coin', 'UNKNOWN')
                size = float(pos.get('szi', 0))
                direction = "Long" if size > 0 else "Short"
                abs_size = abs(size)
                entry_px = float(pos.get('entry_px', 0))
                unrealized_pnl = float(pos.get('unrealized_pnl', 0))
                leverage = float(pos.get('leverage', 1))
                position_max_leverage = float(pos.get('max_leverage', 10))  # Renamed to avoid conflict with account max_leverage
                margin_used = float(pos.get('margin_used', 0))
                position_value = float(pos.get('position_value', 0))
                roe = float(pos.get('return_on_equity', 0))
                funding_since_open = float(pos.get('cum_funding_since_open', 0) or 0)
                net_pnl = unrealized_pnl + funding_since_open
                liquidation_px = float(pos.get('liquidation_px', 0))
                leverage_type = pos.get('leverage_type', 'cross') or 'cross'

                # Position timing information (NEW)
                opened_at_str = pos.get('opened_at_str')
                holding_duration_str = pos.get('holding_duration_str')

                # Get current market price for this symbol
                current_price = effective_prices.get(symbol, entry_px)

                # Format values
                pnl_str = f"+${unrealized_pnl:,.2f}" if unrealized_pnl >= 0 else f"-${abs(unrealized_pnl):,.2f}"
                roe_str = f"+{roe:.2f}%" if roe >= 0 else f"{roe:.2f}%"
                funding_str = f"+${funding_since_open:.4f}" if funding_since_open >= 0 else f"-${abs(funding_since_open):.4f}"
                net_pnl_str = f"+${net_pnl:,.2f}" if net_pnl >= 0 else f"-${abs(net_pnl):,.2f}"
                leverage_type_str = leverage_type.capitalize()

                # Calculate distance to liquidation
                if liquidation_px > 0 and current_price > 0:
                    liq_distance_pct = abs(current_price - liquidation_px) / current_price * 100
                    liq_warning = " ⚠️" if liq_distance_pct < 10 else ""
                else:
                    liq_distance_pct = 0
                    liq_warning = ""

                # Build position timing line
                timing_line = ""
                if opened_at_str and holding_duration_str:
                    timing_line = f"  Opened: {opened_at_str} | Holding: {holding_duration_str}\n"

                pos_lines.append(
                    f"- {symbol}: {direction} {abs_size:.4f} units @ ${entry_px:,.2f} avg\n"
                    f"{timing_line}"
                    f"  Mark price: ${current_price:,.2f} | Position value: ${position_value:,.2f}\n"
                    f"  Unrealized P&L (exchange): {pnl_str} ({roe_str} ROE)\n"
                    f"  Funding Since Open: {funding_str} | Net P&L: {net_pnl_str}\n"
                    f"  Leverage: {leverage:.0f}x {leverage_type_str} (max {position_max_leverage:.0f}x) | Margin: ${margin_used:,.2f}\n"
                    f"  Liquidation: ${liquidation_px:,.2f} ({liq_distance_pct:.1f}% away){liq_warning}"
                )
            positions_detail = "\n".join(pos_lines)
        else:
            positions_detail = "No open positions"
    else:
        total_equity = "N/A"
        available_balance = "N/A"
        used_margin = "N/A"
        margin_usage_percent = "0"
        maintenance_margin = "N/A"
        positions_detail = "No open positions"

    # ============================================================================
    # RECENT TRADES HISTORY SUMMARY
    # ============================================================================
    # Build recent closed trades summary to help AI understand trading patterns
    # and avoid flip-flop behavior (rapid position reversals)
    recent_trades_summary = "No recent trade history available"

    # Support both Hyperliquid and Binance exchanges
    if (hyperliquid_state or exchange == "binance") and environment in ("testnet", "mainnet"):
        try:
            from database.connection import SessionLocal

            with SessionLocal() as db_session:
                recent_trades = []
                open_orders = []

                if exchange == "binance":
                    # Get Binance trading client
                    from services.binance_trading_client import BinanceTradingClient
                    from database.models import BinanceWallet
                    from utils.encryption import decrypt_private_key

                    binance_wallet = db_session.query(BinanceWallet).filter(
                        BinanceWallet.account_id == account.id,
                        BinanceWallet.environment == environment,
                        BinanceWallet.is_active == "true"
                    ).first()

                    if binance_wallet and binance_wallet.api_key_encrypted:
                        api_key = decrypt_private_key(binance_wallet.api_key_encrypted)
                        secret_key = decrypt_private_key(binance_wallet.secret_key_encrypted)
                        client = BinanceTradingClient(
                            api_key=api_key,
                            secret_key=secret_key,
                            environment=binance_wallet.environment or "testnet"
                        )
                        recent_trades = client.get_recent_closed_trades(db_session, limit=5)
                        open_orders = client.get_open_orders_formatted(db_session)
                    else:
                        recent_trades_summary = "Binance wallet not configured"
                else:
                    # Get Hyperliquid trading client (uses get_hyperliquid_client to support API Wallet)
                    from services.hyperliquid_environment import get_hyperliquid_client

                    try:
                        client = get_hyperliquid_client(db_session, account.id, override_environment=environment)
                        recent_trades = client.get_recent_closed_trades(db_session, limit=5)
                        open_orders = client.get_open_orders(db_session)
                    except ValueError:
                        recent_trades_summary = "Wallet not configured for this environment"

                # Build recent trades section (common format for both exchanges)
                if recent_trades or open_orders:
                    trades_section = ""
                    if recent_trades:
                        trade_lines = ["Recent closed trades (last 5 positions):"]
                        for trade in recent_trades:
                            symbol = trade.get('symbol', 'UNKNOWN')
                            side = trade.get('side', 'Unknown')
                            close_time = trade.get('close_time', 'N/A')
                            close_price = trade.get('close_price', 0)
                            realized_pnl = trade.get('realized_pnl', 0)
                            direction = trade.get('direction', '')

                            pnl_str = f"+${realized_pnl:,.2f}" if realized_pnl >= 0 else f"-${abs(realized_pnl):,.2f}"
                            trade_lines.append(
                                f"- {symbol} {side}: Closed at {close_time} @ ${close_price:,.2f} | P&L: {pnl_str} | {direction}"
                            )
                        trades_section = "\n".join(trade_lines)
                    else:
                        trades_section = "Recent closed trades: No recent closed trades found"

                    # Build open orders section
                    orders_section = ""
                    if open_orders:
                        display_orders = open_orders[:10]
                        order_lines = [f"\nOpen orders ({len(open_orders)} pending):"]
                        for order in display_orders:
                            symbol = order.get('symbol', 'UNKNOWN')
                            direction = order.get('direction', 'Unknown')
                            order_type = order.get('order_type', 'Limit')
                            order_id = order.get('order_id', 'N/A')
                            price = order.get('price', 0)
                            size = order.get('size', 0)
                            order_value = order.get('order_value', 0)
                            reduce_only = "Yes" if order.get('reduce_only', False) else "No"
                            trigger_condition = order.get('trigger_condition')
                            order_time = order.get('order_time', 'N/A')

                            trigger_info = f"Trigger: {trigger_condition}" if trigger_condition else "Trigger: None"
                            order_lines.append(
                                f"- {symbol} {direction}: {order_type} Order #{order_id} @ ${price:,.2f} | "
                                f"Size: {size:.5f} | Value: ${order_value:,.2f} | Reduce Only: {reduce_only} | "
                                f"{trigger_info} | Placed: {order_time}"
                            )
                        orders_section = "\n".join(order_lines)
                    else:
                        orders_section = "\nOpen orders: No open orders"

                    recent_trades_summary = orders_section + "\n\n" + trades_section

        except Exception as e:
            logger.warning(f"Failed to get recent trades summary: {e}", exc_info=True)
            recent_trades_summary = f"Error fetching trade history: {str(e)[:100]}"

    # ============================================================================
    # K-LINE AND TECHNICAL INDICATORS PROCESSING
    # ============================================================================
    # Process K-line and technical indicator variables if template_text is provided.
    # This ensures that variables like {BTC_klines_15m}, {BTC_MACD_15m}, etc.
    # are properly populated with real data instead of showing "N/A".
    #
    # IMPORTANT: This processing MUST stay inside _build_prompt_context to ensure
    # preview and AI decision execution use the same logic.
    kline_context = {}
    if template_text:
        try:
            from database.connection import SessionLocal
            variable_groups = _parse_kline_indicator_variables(template_text)
            if variable_groups:
                # Reuse the same realtime ticker snapshot for {SYMBOL_market_data}
                # so market_prices, positions_detail, and market_data stay aligned.
                market_data_groups = {}
                non_market_groups = {}
                for key, requirements in variable_groups.items():
                    symbol, period = key
                    if period is None and requirements.get("market_data"):
                        market_data_groups[key] = requirements
                    else:
                        non_market_groups[key] = requirements

                for (symbol, _period), _requirements in market_data_groups.items():
                    ticker = realtime_tickers.get(symbol)
                    if ticker:
                        kline_context[f"{symbol}_market_data"] = _format_market_data_block(symbol, ticker)

                if non_market_groups:
                    with SessionLocal() as db:
                        kline_context.update(
                            _build_klines_and_indicators_context(
                                non_market_groups,
                                db,
                                environment,
                                exchange,
                            )
                        )
                logger.debug(f"Built K-line context with {len(kline_context)} variables")
        except Exception as e:
            logger.warning(f"Failed to build K-line context: {e}", exc_info=True)

    # ============================================================================
    # FACTOR VARIABLES PROCESSING
    # ============================================================================
    # Process factor variables like {BTC_factor_1h_RSI21} from prompt template.
    # Legacy {BTC_factor_RSI21} syntax still works and defaults to 5m.
    factor_context = {}
    if template_text:
        try:
            factor_vars = _parse_factor_variables(template_text)
            if factor_vars:
                factor_context = _build_factor_context(factor_vars, environment, exchange)
                logger.debug(f"Built factor context with {len(factor_context)} variables")
        except Exception as e:
            logger.warning(f"Failed to build factor context: {e}", exc_info=True)

    # ============================================================================
    # NEWS INTELLIGENCE VARIABLES
    # ============================================================================
    # Process news variables like {BTC_news_sentiment}, {BTC_news_headlines_4h},
    # {macro_news}, {general_news} from prompt template.
    news_context = {}
    if template_text:
        try:
            from services.news_prompt_variables import build_news_context
            from database.connection import SessionLocal
            with SessionLocal() as news_db:
                news_context = build_news_context(template_text, news_db)
            if news_context:
                logger.debug(f"Built news context with {len(news_context)} variables")
        except Exception as e:
            logger.warning(f"Failed to build news context: {e}", exc_info=True)

    # ============================================================================
    # ADANOS MARKET SENTIMENT VARIABLES
    # ============================================================================
    # Process optional Adanos variables like {adanos_sentiment} and
    # {BTC_adanos_sentiment}. This stays prompt-scoped and fail-open.
    adanos_context = {}
    if template_text:
        try:
            from services.adanos_sentiment import build_adanos_sentiment_context
            adanos_context = build_adanos_sentiment_context(template_text, ordered_symbols)
            if adanos_context:
                logger.debug(f"Built Adanos sentiment context with {len(adanos_context)} variables")
        except Exception as e:
            logger.warning(f"Failed to build Adanos sentiment context: {e}", exc_info=True)

    # ============================================================================
    # TRIGGER CONTEXT FORMATTING
    # ============================================================================
    # Format trigger context into structured text for AI prompt.
    # This tells the AI what triggered this decision (signal or scheduled).
    trigger_context_text = ""
    if trigger_context:
        trigger_type = trigger_context.get("trigger_type", "unknown")
        lines = [f"=== TRIGGER CONTEXT ===", f"trigger_type: {trigger_type}"]

        if trigger_type == "signal":
            pool_name = trigger_context.get("signal_pool_name", "Unknown")
            pool_logic = trigger_context.get("pool_logic", "OR")
            trigger_symbol = trigger_context.get("trigger_symbol", "N/A")
            lines.append(f"signal_pool_name: {pool_name}")
            lines.append(f"pool_logic: {pool_logic}")
            lines.append(f"trigger_symbol: {trigger_symbol}")

            triggered_signals = trigger_context.get("triggered_signals", [])
            if triggered_signals:
                lines.append("triggered_signals:")
                for sig in triggered_signals:
                    # Support both "signal_name" (from signal_detection_service) and "name" (fallback)
                    sig_name = sig.get("signal_name") or sig.get("name", "Unknown Signal")
                    description = sig.get("description")
                    metric = sig.get("metric", "N/A")
                    time_window = sig.get("time_window", "N/A")

                    lines.append(f"  - name: {sig_name}")
                    if description:
                        lines.append(f"    description: {description}")

                    # Special handling for taker_volume composite signal
                    if metric == "taker_volume":
                        direction = sig.get("actual_direction") or sig.get("direction", "N/A")
                        buy = sig.get("buy", 0)
                        sell = sig.get("sell", 0)
                        ratio = sig.get("ratio", 0)
                        ratio_threshold = sig.get("ratio_threshold", 1.5)
                        volume_threshold = sig.get("volume_threshold", 0)
                        # Calculate dominant side multiplier for clarity
                        if direction == "buy" and ratio > 0:
                            multiplier = ratio
                            dominant = "buyers"
                        elif direction == "sell" and ratio > 0:
                            multiplier = 1 / ratio if ratio > 0 else 0
                            dominant = "sellers"
                        else:
                            multiplier = ratio
                            dominant = "N/A"
                        lines.append(f"    metric: taker_volume")
                        lines.append(f"    direction: {direction}")
                        lines.append(f"    taker_buy: ${buy/1e6:.2f}M")
                        lines.append(f"    taker_sell: ${sell/1e6:.2f}M")
                        lines.append(f"    dominant: {dominant} {multiplier:.2f}x (threshold: {ratio_threshold}x)")
                    else:
                        # Standard single-value signal
                        operator = sig.get("operator", "N/A")
                        threshold = sig.get("threshold", "N/A")
                        actual_value = sig.get("current_value") or sig.get("actual_value", "N/A")

                        unit = _get_metric_unit(metric)
                        metric_display = f"{metric} ({unit})" if unit else metric
                        threshold_display = f"{threshold}{unit}" if unit else str(threshold)
                        value_display = f"{actual_value:.4f}{unit}" if isinstance(actual_value, (int, float)) and unit else str(actual_value)

                        lines.append(f"    metric: {metric_display}")
                        lines.append(f"    time_window: {time_window}")
                        lines.append(f"    condition: {operator} {threshold_display}")
                        lines.append(f"    current_value: {value_display}")

                        # Factor effectiveness context
                        fe = sig.get("factor_effectiveness")
                        if fe:
                            parts = []
                            if fe.get("ic") is not None:
                                parts.append(f"IC={fe['ic']}")
                            if fe.get("icir") is not None:
                                parts.append(f"ICIR={fe['icir']}")
                            if fe.get("win_rate") is not None:
                                parts.append(f"WinRate={fe['win_rate']}%")
                            dh = fe.get("decay_half_life_hours")
                            if dh is not None:
                                parts.append("Persistent" if dh == -1 else f"Decay={dh}h")
                            if parts:
                                lines.append(f"    factor_effectiveness: {' '.join(parts)}")
        elif trigger_type == "wallet_signal":
            pool_name = trigger_context.get("signal_pool_name", "Unknown")
            trigger_symbol = trigger_context.get("trigger_symbol", "N/A")
            wallet_event = trigger_context.get("wallet_event") or {}
            detail = wallet_event.get("detail") or {}

            lines.append(f"signal_pool_name: {pool_name}")
            lines.append(f"trigger_symbol: {trigger_symbol}")
            lines.append(f"address: {wallet_event.get('address', 'N/A')}")
            lines.append(f"event_type: {wallet_event.get('event_type', 'N/A')}")
            lines.append(f"event_level: {wallet_event.get('event_level', 'N/A')}")
            lines.append(f"summary: {wallet_event.get('summary', 'N/A')}")
            if detail:
                if detail.get("action") is not None:
                    lines.append(f"action: {detail.get('action')}")
                if detail.get("direction") is not None:
                    lines.append(f"direction: {detail.get('direction')}")
                if detail.get("notional_value") is not None:
                    lines.append(f"notional_value: {detail.get('notional_value')}")
                if detail.get("entry_price") is not None:
                    lines.append(f"entry_price: {detail.get('entry_price')}")
                if detail.get("leverage") is not None:
                    lines.append(f"leverage: {detail.get('leverage')}")
                if detail.get("unrealized_pnl") is not None:
                    lines.append(f"unrealized_pnl: {detail.get('unrealized_pnl')}")
                if detail.get("liquidation_price") is not None:
                    lines.append(f"liquidation_price: {detail.get('liquidation_price')}")
                if detail.get("old_value") is not None:
                    lines.append(f"old_value: {detail.get('old_value')}")
                if detail.get("new_value") is not None:
                    lines.append(f"new_value: {detail.get('new_value')}")
                if detail.get("closed_pnl") is not None:
                    lines.append(f"closed_pnl: {detail.get('closed_pnl')}")
                if detail.get("average_price") is not None:
                    lines.append(f"average_price: {detail.get('average_price')}")
                if detail.get("start_position") is not None:
                    lines.append(f"start_position: {detail.get('start_position')}")
                if detail.get("end_position") is not None:
                    lines.append(f"end_position: {detail.get('end_position')}")
                if detail.get("fills_count") is not None:
                    lines.append(f"fills_count: {detail.get('fills_count')}")
        elif trigger_type == "scheduled":
            interval = trigger_context.get("trigger_interval", "N/A")
            lines.append(f"trigger_interval: {interval} seconds")

        trigger_context_text = "\n".join(lines)

    # ============================================================================
    # Market Regime Classification Variables
    # ============================================================================
    # Variables provided:
    # - {market_regime} - summary of all symbols (default 5m timeframe)
    # - {market_regime_description} - indicator calculation methodology
    # - {BTC_market_regime}, {ETH_market_regime} - per-symbol (default 5m)
    # - {BTC_market_regime_1m}, {BTC_market_regime_5m}, {BTC_market_regime_15m}, {BTC_market_regime_1h}
    # - {market_regime_1m}, {market_regime_5m}, {market_regime_15m}, {market_regime_1h}
    market_regime_context = {}

    # Indicator calculation description for AI understanding
    market_regime_context["market_regime_description"] = """Market Regime Indicator Definitions:
- cvd_ratio: CVD / (Taker Buy + Taker Sell). Positive = net buying pressure, negative = net selling
- oi_delta: Open Interest change percentage over the period
- taker: Taker Buy/Sell ratio. >1 = aggressive buying, <1 = aggressive selling
- rsi: RSI(14) momentum indicator. >70 overbought, <30 oversold
- price_atr: (Close - Open) / ATR. Measures price movement relative to volatility

Regime Types:
- breakout: Strong directional move with volume confirmation
- absorption: Large orders absorbed without price impact (potential reversal)
- stop_hunt: Wick beyond range then reversal (liquidity grab)
- exhaustion: Extreme RSI with diverging CVD (trend weakening)
- trap: Price breaks level but CVD/OI diverge (false breakout)
- continuation: Trend continuation with aligned indicators
- noise: No clear pattern, low conviction"""

    if db:
        try:
            from services.market_regime_service import get_market_regime
            supported_timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]

            def format_regime_text(symbol, tf, result):
                """Format regime result with symbol and timeframe context"""
                regime = result['regime']
                direction = result['direction']
                conf = result['confidence']
                ind = result.get('indicators', {})
                if not ind:
                    return f"[{symbol}/{tf}] {regime} ({direction}) conf={conf:.2f} | insufficient data"
                return (
                    f"[{symbol}/{tf}] {regime} ({direction}) conf={conf:.2f} | "
                    f"cvd_ratio={ind.get('cvd_ratio', 0):.3f}, oi_delta={ind.get('oi_delta', 0):.3f}%, "
                    f"taker={ind.get('taker_ratio', 1):.2f}, rsi={ind.get('rsi', 50):.1f}"
                )

            for tf in supported_timeframes:
                tf_regime_lines = []
                for symbol in ordered_symbols:
                    regime_result = get_market_regime(db, symbol, tf, use_realtime=True, exchange=exchange)
                    regime_text = format_regime_text(symbol, tf, regime_result)
                    market_regime_context[f"{symbol}_market_regime_{tf}"] = regime_text
                    tf_regime_lines.append(f"- {regime_text}")
                market_regime_context[f"market_regime_{tf}"] = "\n".join(tf_regime_lines) if tf_regime_lines else "N/A"

            # Default variables (5m) for backward compatibility
            for symbol in ordered_symbols:
                market_regime_context[f"{symbol}_market_regime"] = market_regime_context.get(f"{symbol}_market_regime_5m", "N/A")
            market_regime_context["market_regime"] = market_regime_context.get("market_regime_5m", "N/A")

            # ============================================================================
            # Trigger Market Regime Variable
            # ============================================================================
            # {trigger_market_regime} - The market regime captured at signal trigger time.
            # This is the regime that was calculated when the signal pool triggered,
            # NOT the current real-time regime. Use this to ensure AI sees the same
            # regime that caused the trigger.
            #
            # Only available for signal triggers (trigger_type = "signal").
            # For scheduled triggers, this will be "N/A".
            market_regime_context["trigger_market_regime"] = "N/A"

            if trigger_context and trigger_context.get("trigger_type") == "signal":
                signal_trigger_id = trigger_context.get("signal_trigger_id")
                if signal_trigger_id:
                    # Real trigger - fetch from database
                    try:
                        from sqlalchemy import text
                        result = db.execute(
                            text("SELECT market_regime FROM signal_trigger_logs WHERE id = :id"),
                            {"id": signal_trigger_id}
                        )
                        row = result.fetchone()
                        if row and row[0]:
                            regime_json = row[0]
                            # Parse JSON if it's a string
                            if isinstance(regime_json, str):
                                regime_data = json.loads(regime_json)
                            else:
                                regime_data = regime_json

                            # Format to match other regime variables
                            symbol = regime_data.get("symbol", "N/A")
                            tf = regime_data.get("timeframe", "5m")
                            regime = regime_data.get("regime", "unknown")
                            direction = regime_data.get("direction", "neutral")
                            conf = regime_data.get("confidence", 0)
                            # Get indicators (backward compatible - old data may not have this)
                            ind = regime_data.get("indicators", {})

                            if ind:
                                market_regime_context["trigger_market_regime"] = (
                                    f"[{symbol}/{tf}] {regime} ({direction}) conf={conf:.2f} | "
                                    f"cvd_ratio={ind.get('cvd_ratio', 0):.3f}, oi_delta={ind.get('oi_delta', 0):.3f}%, "
                                    f"taker={ind.get('taker_ratio', 1):.2f}, rsi={ind.get('rsi', 50):.1f} | (trigger snapshot)"
                                )
                            else:
                                # Old data without indicators
                                market_regime_context["trigger_market_regime"] = (
                                    f"[{symbol}/{tf}] {regime} ({direction}) conf={conf:.2f} | (trigger snapshot)"
                                )
                    except Exception as e:
                        logger.warning(f"Failed to get trigger market regime: {e}")
                else:
                    # Preview mode - no signal_trigger_id, provide sample value
                    # Use trigger_symbol from context if available
                    trigger_symbol = trigger_context.get("trigger_symbol", "BTC")
                    # Get time_window from first triggered signal if available
                    triggered_signals = trigger_context.get("triggered_signals", [])
                    if triggered_signals:
                        sample_tf = triggered_signals[0].get("time_window", "5m")
                    else:
                        sample_tf = "5m"
                    market_regime_context["trigger_market_regime"] = (
                        f"[{trigger_symbol}/{sample_tf}] breakout (bullish) conf=0.65 | "
                        f"cvd_ratio=0.286, oi_delta=0.857%, taker=1.80, rsi=50.7 | (trigger snapshot - preview)"
                    )

        except Exception as e:
            logger.warning(f"Failed to get market regime data: {e}")
            market_regime_context["market_regime"] = "N/A"
            market_regime_context["trigger_market_regime"] = "N/A"
    else:
        market_regime_context["market_regime"] = "N/A"
        market_regime_context["trigger_market_regime"] = "N/A"

    return {
        # Legacy variables (for Default prompt and backward compatibility)
        "account_state": account_state,
        "market_snapshot": market_snapshot,
        "session_context": session_context,
        "sampling_data": sampling_data,
        "decision_task": DECISION_TASK_TEXT,
        "output_format": output_format,
        "prices_json": json.dumps(effective_prices, indent=2, sort_keys=True),
        "portfolio_json": json.dumps(portfolio, indent=2, sort_keys=True),
        "portfolio_positions_json": json.dumps(positions, indent=2, sort_keys=True),
        "news_section": news_section,
        "account_name": account.name,
        "model_name": account.model or "",
        # New Alpha Arena style variables (for Pro prompt)
        "runtime_minutes": runtime_minutes,
        "current_time_utc": current_time_utc,
        "total_return_percent": total_return_percent,
        "available_cash": available_cash,
        "total_account_value": total_account_value,
        "holdings_detail": positions_detail if hyperliquid_state else holdings_detail,
        "market_prices": market_prices,
        "selected_symbols_csv": selected_symbols_csv,
        "selected_symbols_detail": selected_symbols_detail,
        "selected_symbols_count": len(ordered_symbols),
        # Hyperliquid-specific variables
        "trading_environment": trading_environment,
        "real_trading_warning": real_trading_warning,
        "operational_constraints": operational_constraints,
        "leverage_constraints": leverage_constraints,
        "margin_info": margin_info,
        "environment": environment,
        "max_leverage": max_leverage,
        "default_leverage": default_leverage,
        # Hyperliquid account state (dynamic from API)
        "total_equity": total_equity,
        "available_balance": available_balance,
        "used_margin": used_margin,
        "margin_usage_percent": margin_usage_percent,
        "maintenance_margin": maintenance_margin,
        "positions_detail": positions_detail,
        # Recent trades history (NEW - helps AI understand trading patterns)
        "recent_trades_summary": recent_trades_summary,
        # Trigger context (signal or scheduled trigger information)
        "trigger_context": trigger_context_text,
        # Optional Adanos Market Sentiment prompt variables
        "adanos_sentiment": adanos_context.get("adanos_sentiment", "N/A"),
        # K-line and technical indicator variables (dynamically generated)
        **kline_context,  # Merge K-line/indicator variables like {BTC_klines_15m}, {BTC_MACD_15m}, etc.
        # Market Regime classification variables (multi-timeframe)
        **market_regime_context,  # Merge {market_regime}, {BTC_market_regime_5m}, etc.
        # Factor variables like {BTC_factor_1h_RSI21}
        **factor_context,
        # News intelligence variables like {BTC_news_sentiment}, {macro_news}, etc.
        **news_context,
        # Adanos Market Sentiment variables like {adanos_sentiment}, {BTC_adanos_sentiment}
        **adanos_context,
    }


def _is_default_api_key(api_key: str) -> bool:
    """Check if the API key is a default/placeholder key that should be skipped"""
    return api_key in DEMO_API_KEYS


def _get_portfolio_data(db: Session, account: Account) -> Dict:
    """Get current portfolio positions and values"""
    positions = db.query(Position).filter(
        Position.account_id == account.id,
        Position.market == "CRYPTO"
    ).all()
    
    portfolio = {}
    for pos in positions:
        if float(pos.quantity) > 0:
            portfolio[pos.symbol] = {
                "quantity": float(pos.quantity),
                "avg_cost": float(pos.avg_cost),
                "current_value": float(pos.quantity) * float(pos.avg_cost)
            }
    
    return {
        "cash": float(account.current_cash),
        "frozen_cash": float(account.frozen_cash),
        "positions": portfolio,
        "total_assets": float(account.current_cash) + calc_positions_value(db, account.id)
    }


def detect_api_format(base_url: str) -> tuple:
    """Detect API format from URL and return (endpoint, format_type).

    Returns:
        tuple: (endpoint_url, format_type) where format_type is 'openai' or 'anthropic'
    """
    if not base_url:
        return (None, None)

    normalized = base_url.strip().rstrip('/')
    if not normalized:
        return (None, None)

    base_lower = normalized.lower()

    # Check if URL already ends with a complete endpoint
    if base_lower.endswith('/messages'):
        # Anthropic native format
        return (normalized, 'anthropic')
    elif base_lower.endswith('/chat/completions'):
        # OpenAI format, already complete
        return (normalized, 'openai')
    elif base_lower.endswith('/anthropic'):
        # Third-party Anthropic-compatible base URL, e.g. MiniMax.
        # Anthropic SDKs append /v1/messages internally; we use requests directly.
        return (f"{normalized}/v1/messages", 'anthropic')
    else:
        # No specific endpoint, append /chat/completions (default OpenAI format)
        return (f"{normalized}/chat/completions", 'openai')


def build_chat_completion_endpoints(base_url: str, model: Optional[str] = None) -> List[str]:
    """Build a list of possible chat completion endpoints for an OpenAI-compatible API.

    Supports Deepseek-specific behavior where both `/chat/completions` and `/v1/chat/completions`
    might be valid, depending on how the base URL is configured.
    Returns:
        List of endpoint URLs to try.
    """
    if not base_url:
        return []

    normalized = base_url.strip().rstrip('/')
    if not normalized:
        return []

    base_lower = normalized.lower()

    # Check if URL already ends with a complete endpoint
    if base_lower.endswith('/messages'):
        # Anthropic native format - use as-is
        return [normalized]
    elif base_lower.endswith('/chat/completions'):
        # OpenAI format, already complete - use as-is
        return [normalized]
    elif base_lower.endswith('/anthropic'):
        # Third-party Anthropic-compatible base URL, e.g. MiniMax.
        # Anthropic SDKs append /v1/messages internally; we use requests directly.
        return [f"{normalized}/v1/messages"]

    # No specific endpoint, build OpenAI-compatible endpoints
    endpoints: List[str] = []
    endpoints.append(f"{normalized}/chat/completions")

    is_deepseek = "deepseek.com" in base_lower

    if is_deepseek:
        # Deepseek supports both /chat/completions and /v1/chat/completions
        if base_lower.endswith('/v1'):
            without_v1 = normalized[:-3]
            endpoints.append(f"{without_v1}/chat/completions")
        else:
            endpoints.append(f"{normalized}/v1/chat/completions")

    # Use dict to preserve order while removing duplicates
    deduped = list(dict.fromkeys(endpoints))
    return deduped


# ---------------------------------------------------------------------------
# Unified LLM payload & headers builders
# ---------------------------------------------------------------------------
# ALL AI features (Trader, Prompt Gen, Program Gen, Signal Gen, Hyper AI,
# K-line Analysis, Attribution, Context Compression, Memory) MUST use these
# two functions to build API payloads and headers.
# When adding a NEW AI feature, import and call these instead of manually
# assembling payload dicts — this ensures correct parameter handling for
# reasoning models, new OpenAI models, Anthropic format, etc.
# ---------------------------------------------------------------------------

# DeepSeek models/aliases that currently use the V4 thinking-mode contract.
DEEPSEEK_REASONING_CONTENT_MODEL_MARKERS = [
    "deepseek-v4",
    "deepseek-reasoner",
    "deepseek-chat",
    "deepseek-r1",
]

# Canonical list of reasoning models that do NOT support temperature
# and require max_completion_tokens (OpenAI format only).
REASONING_MODEL_MARKERS = [
    # OpenAI
    "gpt-5", "o1-preview", "o1-mini", "o1-", "o1", "o3-", "o3", "o4-", "o4",
    # DeepSeek V4 and legacy aliases mapped to V4 behavior
    *DEEPSEEK_REASONING_CONTENT_MODEL_MARKERS,
    # Qwen
    "qwq", "qwen-plus-thinking", "qwen-max-thinking", "qwen3-thinking", "qwen-turbo-thinking",
    # Claude (extended thinking)
    "claude-4", "claude-sonnet-4-5",
    # Gemini (thinking mode)
    "gemini-2.5", "gemini-3", "gemini-2.0-flash-thinking",
    # Grok
    "grok-3-mini",
]

# Models that use max_completion_tokens instead of max_tokens (OpenAI format).
# This includes all reasoning models plus newer non-reasoning models.
NEW_MODEL_MARKERS = ["gpt-4o"]


def is_reasoning_model(model: str) -> bool:
    """Check if a model is a reasoning model (no temperature, special params)."""
    model_lower = (model or "").lower()
    return any(marker in model_lower for marker in REASONING_MODEL_MARKERS)


def requires_deepseek_reasoning_content(model: str) -> bool:
    """DeepSeek V4 thinking-mode models require reasoning_content on tool-call messages."""
    model_lower = (model or "").lower()
    return any(marker in model_lower for marker in DEEPSEEK_REASONING_CONTENT_MODEL_MARKERS)


def is_new_openai_model(model: str) -> bool:
    """Check if a model uses max_completion_tokens instead of max_tokens."""
    return is_reasoning_model(model) or any(
        marker in (model or "").lower() for marker in NEW_MODEL_MARKERS
    )


def is_minimax_anthropic_url(url: Optional[str]) -> bool:
    """Return True for MiniMax's Anthropic-compatible gateway URLs."""
    normalized = (url or "").strip().rstrip("/").lower()
    return (
        "api.minimax.io/anthropic" in normalized
        or "api.minimaxi.com/anthropic" in normalized
    )


def build_llm_headers(api_format: str, api_key: str, base_url: Optional[str] = None) -> dict:
    """Build HTTP headers for LLM API calls.

    Args:
        api_format: 'anthropic' or 'openai'
        api_key: The API key
        base_url: Optional URL used for provider-specific auth quirks
    """
    headers = {"Content-Type": "application/json"}
    if api_format == "anthropic":
        if is_minimax_anthropic_url(base_url):
            # MiniMax's Anthropic-compatible /anthropic gateway uses the
            # Messages schema but rejects Anthropic's official x-api-key header.
            # Keep this scoped to MiniMax URLs so the official Anthropic API is unchanged.
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def convert_tools_to_anthropic(openai_tools: List[Dict]) -> List[Dict]:
    """Convert OpenAI format tools to Anthropic format."""
    anthropic_tools = []
    for tool in openai_tools:
        if tool.get("type") == "function":
            func = tool["function"]
            anthropic_tools.append({
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}})
            })
    return anthropic_tools


def convert_messages_to_anthropic(openai_messages: List[Dict]) -> tuple:
    """Convert OpenAI format messages to Anthropic format.

    Returns: (system_prompt, anthropic_messages)
    Anthropic requires system prompt to be separate from messages.
    Also, multiple consecutive tool results must be merged into one user message.
    """
    system_prompt = ""
    anthropic_messages = []
    pending_tool_results = []

    def flush_tool_results():
        nonlocal pending_tool_results
        if pending_tool_results:
            anthropic_messages.append({
                "role": "user",
                "content": pending_tool_results
            })
            pending_tool_results = []

    def clean_tool_use_blocks(blocks):
        """Fix input field format (some proxies return '' instead of {})."""
        if not isinstance(blocks, list):
            return blocks
        cleaned = []
        for block in blocks:
            if isinstance(block, dict):
                block_copy = block.copy()
                if block_copy.get("type") == "tool_use" and block_copy.get("input") == "":
                    block_copy["input"] = {}
                cleaned.append(block_copy)
            else:
                cleaned.append(block)
        return cleaned

    for msg in openai_messages:
        role = msg.get("role")
        content = msg.get("content", "")

        if role == "system":
            system_prompt = content
        elif role == "user":
            flush_tool_results()
            anthropic_messages.append({"role": "user", "content": content})
        elif role == "assistant":
            flush_tool_results()
            if "tool_use_blocks" in msg:
                cleaned_blocks = clean_tool_use_blocks(msg["tool_use_blocks"])
                anthropic_messages.append({
                    "role": "assistant",
                    "content": cleaned_blocks
                })
            else:
                anthropic_messages.append({"role": "assistant", "content": content})
        elif role == "tool":
            pending_tool_results.append({
                "type": "tool_result",
                "tool_use_id": msg.get("tool_call_id", ""),
                "content": content
            })

    flush_tool_results()
    return system_prompt, anthropic_messages


def extract_reasoning(message: dict) -> str:
    """Extract reasoning/thinking content from LLM API response message.

    Unified extraction for all providers. Currently supports:
    - DeepSeek V4/R1/Reasoner, Qwen QwQ, Grok-3-mini: 'reasoning_content' field
    - Some Qwen models: 'thinking' field

    Note: OpenAI o1/o3/o4 does not expose reasoning via API.
    Note: Claude extended thinking requires enabling in request (not yet supported).

    Args:
        message: The 'message' dict from LLM response (choices[0].message)

    Returns:
        Reasoning text or empty string if none found
    """
    # Strategy 1: reasoning_content (DeepSeek V4/R1, Qwen QwQ, Grok-3-mini)
    rc = message.get("reasoning_content")
    if rc and isinstance(rc, str) and rc.strip():
        return rc
    # Strategy 2: thinking field (some Qwen models via vLLM)
    tk = message.get("thinking")
    if tk and isinstance(tk, str) and tk.strip():
        return tk
    # Strategy 3: Claude thinking blocks in content array
    # {"content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "..."}]}
    try:
        content_array = message.get("content")
        if isinstance(content_array, list):
            parts = []
            for block in content_array:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    t = block.get("thinking")
                    if t and isinstance(t, str) and t.strip():
                        parts.append(t.strip())
            if parts:
                return "\n\n".join(parts)
    except Exception:
        pass
    # Strategy 4: Gemini thought parts
    # {"parts": [{"text": "...", "thought": true}, {"text": "..."}]}
    try:
        parts_array = message.get("parts")
        if isinstance(parts_array, list):
            parts = []
            for part in parts_array:
                if isinstance(part, dict) and part.get("thought"):
                    t = part.get("text")
                    if t and isinstance(t, str) and t.strip():
                        parts.append(t.strip())
            if parts:
                return "\n\n".join(parts)
    except Exception:
        pass
    # Strategy 5: MiniMax reasoning_details
    rd = message.get("reasoning_details")
    if isinstance(rd, list):
        parts = []
        for item in rd:
            if isinstance(item, dict):
                t = item.get("text")
                if t and isinstance(t, str) and t.strip():
                    parts.append(t.strip())
        if parts:
            return "\n\n".join(parts)
    return ""


# Regex to match <thinking>...</thinking> and <think>...</think> tags.
_THINKING_TAG_RE = re.compile(
    r'<think(?:ing)?>\s*([\s\S]*?)\s*</think(?:ing)?>',
    re.IGNORECASE
)


def strip_thinking_tags(content: str) -> tuple:
    """Strip <thinking>...</thinking> text tags from content.

    Some OpenAI-compatible proxies embed Claude's extended thinking as
    <thinking> text tags inside the content field. This extracts the
    thinking text and returns clean content.

    Returns:
        (clean_content, extracted_thinking) tuple.
        extracted_thinking is empty string if no tags found.
    """
    content_lower = (content or "").lower()
    if not content or ('<thinking>' not in content_lower and '<think>' not in content_lower):
        return (content, "")

    parts = []
    for m in _THINKING_TAG_RE.finditer(content):
        parts.append(m.group(1).strip())

    clean = _THINKING_TAG_RE.sub('', content).strip()
    return (clean, "\n\n".join(parts))


def build_llm_payload(
    model: str,
    messages: list,
    api_format: str,
    max_tokens: int = None,
    temperature: float = 0.7,
    tools: list = None,
    tool_choice: str = None,
    stream: bool = False,
) -> dict:
    """Build a correct LLM API payload with proper parameter handling.

    Automatically handles:
    - Reasoning models: omits temperature, uses max_completion_tokens (OpenAI)
    - Anthropic format: separates system messages, always uses max_tokens
    - GPT-5: adds reasoning_effort parameter
    - New OpenAI models (gpt-4o, o1, o3, etc.): max_completion_tokens

    Args:
        model: Model name (e.g. "gpt-4o", "o1", "claude-3-5-sonnet")
        messages: Chat messages list
        api_format: 'anthropic' or 'openai'
        max_tokens: Max output tokens (None = auto via get_max_tokens)
        temperature: Temperature value (ignored for reasoning models)
        tools: Tool definitions (format must match api_format)
        tool_choice: Tool choice strategy (e.g. "auto")
        stream: Whether to enable streaming
    """
    if max_tokens is None:
        max_tokens = get_max_tokens(model)

    reasoning = is_reasoning_model(model)
    new_model = is_new_openai_model(model)

    if api_format == "anthropic":
        # Anthropic: separate system messages, always use max_tokens
        system_parts = []
        api_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_parts.append(msg["content"])
            else:
                api_messages.append(msg)

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }
        if system_parts:
            payload["system"] = "\n".join(system_parts)

        # Claude extended thinking: all Anthropic models support thinking
        # Returns thinking blocks in content array, billed as output tokens
        budget = min(4096, max_tokens - 1)
        if budget >= 1024:
            payload["thinking"] = {"type": "enabled", "budget_tokens": budget}
    else:
        # OpenAI format
        payload = {
            "model": model,
            "messages": messages,
        }
        # Reasoning models don't support temperature
        if not reasoning and temperature is not None:
            payload["temperature"] = temperature

        # New models use max_completion_tokens, older use max_tokens
        if new_model:
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["max_tokens"] = max_tokens

        # GPT-5 family: set reasoning_effort
        if "gpt-5" in (model or "").lower():
            payload["reasoning_effort"] = "low"

        # Gemini thinking: include thoughts in response for reasoning-class models
        # Works via OpenAI-compatible API with google.thinking_config extension
        model_lower = (model or "").lower()
        if reasoning and ("gemini" in model_lower):
            payload["google"] = {
                "thinking_config": {
                    "include_thoughts": True
                }
            }

    # Optional: tools
    if tools:
        payload["tools"] = tools
        if tool_choice and api_format != "anthropic":
            payload["tool_choice"] = tool_choice

    # Optional: streaming
    if stream:
        payload["stream"] = True

    # DeepSeek V4 thinking mode requires prior assistant messages to carry the
    # reasoning_content field when sent back in multi-turn history.
    if api_format != "anthropic":
        if requires_deepseek_reasoning_content(model):
            for msg in payload.get("messages", []):
                if msg.get("role") == "assistant" and "reasoning_content" not in msg:
                    msg["reasoning_content"] = ""

    return payload


def _extract_text_from_message(content: Any) -> str:
    """Normalize OpenAI/Anthropic style message content into a plain string."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                # Anthropic style: {"type": "text", "text": "..."}
                text_value = item.get("text")
                if isinstance(text_value, str):
                    parts.append(text_value)
                    continue

                # Some providers use {"type": "output_text", "content": "..."}
                content_value = item.get("content")
                if isinstance(content_value, str):
                    parts.append(content_value)
                    continue

                # Recursively handle nested content arrays
                nested = item.get("content")
                nested_text = _extract_text_from_message(nested)
                if nested_text:
                    parts.append(nested_text)
        return "\n".join(parts)

    if isinstance(content, dict):
        # Direct text fields
        for key in ("text", "content", "value"):
            value = content.get(key)
            if isinstance(value, str):
                return value

        # Nested structures
        for key in ("text", "content", "parts"):
            nested = content.get(key)
            nested_text = _extract_text_from_message(nested)
            if nested_text:
                return nested_text

    return ""


def call_ai_for_decision(
    db: Session,
    account: Account,
    portfolio: Dict,
    prices: Dict[str, float],
    samples: Optional[List] = None,
    target_symbol: Optional[str] = None,
    symbols: Optional[List[str]] = None,
    hyperliquid_state: Optional[Dict[str, Any]] = None,
    symbol_metadata: Optional[Dict[str, Any]] = None,
    trigger_context: Optional[Dict[str, Any]] = None,
    exchange: str = "hyperliquid",
) -> Optional[List[Dict[str, Any]]]:
    """Call AI model API to get trading decision

    Args:
        db: Database session
        account: Trading account
        portfolio: Portfolio data
        prices: Market prices
        samples: Legacy single-symbol samples (deprecated, use symbols instead)
        target_symbol: Legacy single symbol (deprecated, use symbols instead)
        symbols: List of symbols to include sampling data for (preferred method)
        hyperliquid_state: Optional Hyperliquid account state for real trading
        symbol_metadata: Optional mapping of symbol -> display name overrides
        trigger_context: Optional context about what triggered this decision (signal or scheduled)
        exchange: Exchange to use for market data ("hyperliquid" or "binance")
    """
    # Check if this is a default API key
    if _is_default_api_key(account.api_key):
        logger.info(f"Skipping AI trading for account {account.name} - using default API key")
        return None

    # IMPORTANT: Get global trading mode at the start
    from services.hyperliquid_environment import get_global_trading_mode
    global_environment = get_global_trading_mode(db)

    try:
        news_summary = fetch_latest_news()
        news_section = news_summary if news_summary else "No recent CoinJournal news available."
    except Exception as err:  # pragma: no cover - defensive logging
        logger.warning("Failed to fetch latest news: %s", err)
        news_section = "No recent CoinJournal news available."

    template = prompt_repo.get_prompt_for_account(db, account.id)
    if not template:
        logger.warning(
            "No prompt binding for account %s (%s), skipping AI decision",
            account.id, account.name
        )
        return None

    # Build context with multi-symbol support
    active_symbol_metadata = symbol_metadata or SUPPORTED_SYMBOLS
    symbol_order = symbols if symbols else list(active_symbol_metadata.keys())

    if symbols:
        # New multi-symbol approach
        from services.sampling_pool import sampling_pool
        from database.connection import SessionLocal
        from database.models import GlobalSamplingConfig

        # Get actual sampling interval from config
        sampling_interval = None
        try:
            with SessionLocal() as db:
                config = db.query(GlobalSamplingConfig).first()
                if config:
                    sampling_interval = config.sampling_interval
        except Exception as e:
            logger.warning(f"Failed to get sampling interval: {e}")

        sampling_data = _build_multi_symbol_sampling_data(symbols, sampling_pool, sampling_interval)
        context = _build_prompt_context(
            account,
            portfolio,
            prices,
            news_section,
            None,
            None,
            hyperliquid_state,
            db=db,
            symbol_metadata=active_symbol_metadata,
            symbol_order=symbol_order,
            sampling_interval=sampling_interval,
            environment=global_environment,
            template_text=template.template_text,
            trigger_context=trigger_context,
            exchange=exchange,
        )
        context["sampling_data"] = sampling_data
    else:
        # Legacy single-symbol approach (backward compatibility)
        # Get actual sampling interval from config
        sampling_interval = None
        try:
            from database.connection import SessionLocal
            from database.models import GlobalSamplingConfig
            with SessionLocal() as db:
                config = db.query(GlobalSamplingConfig).first()
                if config:
                    sampling_interval = config.sampling_interval
        except Exception as e:
            logger.warning(f"Failed to get sampling interval: {e}")

        context = _build_prompt_context(
            account,
            portfolio,
            prices,
            news_section,
            samples,
            target_symbol,
            hyperliquid_state,
            db=db,
            symbol_metadata=active_symbol_metadata,
            symbol_order=symbol_order,
            sampling_interval=sampling_interval,
            environment=global_environment,
            template_text=template.template_text,
            trigger_context=trigger_context,
            exchange=exchange,
        )

    # Market Regime variables are now generated inside _build_prompt_context

    try:
        prompt = template.template_text.format_map(SafeDict(context))
    except Exception as exc:  # pragma: no cover - fallback rendering
        logger.error("Failed to render prompt template '%s': %s", template.key, exc)
        prompt = template.template_text

    logger.debug("Using prompt template '%s' for account %s", template.key, account.id)

    # Use unified payload/headers builders (see build_llm_payload docstring)
    headers = build_llm_headers("openai", account.api_key)

    # Enable streaming for DeepSeek reasoning models to handle high-load scenarios
    use_streaming = requires_deepseek_reasoning_content(account.model)

    payload = build_llm_payload(
        model=account.model,
        messages=[{"role": "user", "content": prompt}],
        api_format="openai",
        stream=use_streaming,
    )

    try:
        endpoints = build_chat_completion_endpoints(account.base_url, account.model)
        if not endpoints:
            logger.error("No valid API endpoint built for account %s", account.name)
            system_logger.log_error(
                "API_ENDPOINT_BUILD_FAILED",
                f"Failed to build API endpoint for {account.name} (model: {account.model})",
                {"account": account.name, "model": account.model, "base_url": account.base_url},
            )
            return None

        # Retry logic for rate limiting and transient errors
        max_retries = 3
        response = None
        success = False

        # Reasoning models need longer timeout (they think more, respond slower)
        if is_reasoning_model(account.model):
            request_timeout = 240
        else:
            request_timeout = 120

        for endpoint in endpoints:
            for attempt in range(max_retries):
                try:
                    response = requests.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                        timeout=request_timeout,
                        verify=False,  # Disable SSL verification for custom AI endpoints
                        stream=use_streaming,  # Enable streaming for DeepSeek V4/Reasoner
                    )

                    if response.status_code == 200:
                        success = True
                        break  # Success, exit retry loop

                    if response.status_code == 429:
                        # Rate limited, wait and retry
                        wait_time = (2**attempt) + random.uniform(0, 1)  # Exponential backoff with jitter
                        logger.warning(
                            "AI API rate limited for %s (attempt %s/%s), waiting %.1fs…",
                            account.name,
                            attempt + 1,
                            max_retries,
                            wait_time,
                        )
                        if attempt < max_retries - 1:
                            time.sleep(wait_time)
                            continue

                        logger.error(
                            "AI API rate limited after %s attempts for endpoint %s: %s",
                            max_retries,
                            endpoint,
                            response.text,
                        )
                        break

                    logger.warning(
                        "AI API returned status %s for endpoint %s: %s",
                        response.status_code,
                        endpoint,
                        response.text,
                    )
                    break  # Try next endpoint if available
                except requests.RequestException as req_err:
                    if attempt < max_retries - 1:
                        wait_time = (2**attempt) + random.uniform(0, 1)
                        logger.warning(
                            "AI API request failed for endpoint %s (attempt %s/%s), retrying in %.1fs: %s",
                            endpoint,
                            attempt + 1,
                            max_retries,
                            wait_time,
                            req_err,
                        )
                        time.sleep(wait_time)
                        continue

                    logger.warning(
                        "AI API request failed after %s attempts for endpoint %s: %s",
                        max_retries,
                        endpoint,
                        req_err,
                    )
                    break
            if success:
                break

        if not success or not response:
            logger.error("All API endpoints failed for account %s (%s)", account.name, account.model)
            system_logger.log_error(
                "AI_API_ALL_ENDPOINTS_FAILED",
                f"All API endpoints failed for {account.name}",
                {
                    "account": account.name,
                    "model": account.model,
                    "endpoints_tried": [str(ep) for ep in endpoints],
                    "max_retries": max_retries,
                },
            )
            return None

        # Handle streaming response for DeepSeek V4/Reasoner
        if use_streaming:
            try:
                full_content = ""
                reasoning_content = ""
                chunk_count = 0

                # Parse SSE stream
                for line in response.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')

                        # SSE format: "data: {...}"
                        if line_str.startswith('data: '):
                            json_str = line_str[6:]  # Remove "data: " prefix

                            # Check for [DONE] marker
                            if json_str.strip() == '[DONE]':
                                break

                            try:
                                data = json.loads(json_str)
                                chunk_count += 1

                                # Extract content from delta
                                if data.get('choices'):
                                    delta = data['choices'][0].get('delta', {})
                                    content = delta.get('content') or ''
                                    reasoning = delta.get('reasoning_content') or ''

                                    full_content += content
                                    reasoning_content += reasoning

                            except json.JSONDecodeError as e:
                                logger.warning(f"JSON decode error in streaming response: {e}")
                                continue

                # Construct complete response object (simulate non-streaming format)
                result = {
                    "choices": [{
                        "message": {
                            "content": full_content,
                            "reasoning_content": reasoning_content
                        },
                        "finish_reason": "stop"
                    }]
                }

                logger.info(f"Streaming response completed: {chunk_count} chunks, content: {len(full_content)} chars, reasoning: {len(reasoning_content)} chars")

            except Exception as stream_err:
                logger.error(f"Failed to parse streaming response: {stream_err}")
                return None
        else:
            # Non-streaming response (existing logic)
            result = response.json()

        # Extract text from OpenAI-compatible response format
        if "choices" in result and len(result["choices"]) > 0:
            choice = result["choices"][0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "")
            reasoning_text = _extract_text_from_message(message.get("reasoning"))

            # Extract reasoning content from multi-vendor protocols (defensive design)
            def _extract_reasoning_content_safe(api_result: dict) -> str:
                """
                Extract reasoning content from AI response (multi-vendor support)
                Supports: OpenAI (o1/o3/gpt-5), DeepSeek (R1), Qwen (QwQ), Claude (thinking), Gemini (thoughts), Grok (3-mini)
                Returns empty string on any error - never blocks main trading flow
                """
                try:
                    reasoning_parts = []

                    # Safe extraction: get choices and message with type checking
                    choices = api_result.get("choices")
                    if not choices or not isinstance(choices, list) or len(choices) == 0:
                        return ""

                    choice_item = choices[0]
                    if not isinstance(choice_item, dict):
                        return ""

                    msg = choice_item.get("message")
                    if not isinstance(msg, dict):
                        return ""

                    # Strategy 1: OpenAI/DeepSeek/Qwen/Grok standard format
                    # message.reasoning (OpenAI o1/o3/gpt-5)
                    # message.reasoning_content (DeepSeek V4/R1, Qwen QwQ, Grok 3-mini)
                    try:
                        reasoning_field = msg.get("reasoning")
                        if reasoning_field:
                            extracted = _extract_text_from_message(reasoning_field)
                            if extracted and extracted.strip():
                                reasoning_parts.append(extracted.strip())
                    except Exception:
                        pass

                    try:
                        reasoning_content_field = msg.get("reasoning_content")
                        if reasoning_content_field:
                            extracted = _extract_text_from_message(reasoning_content_field)
                            if extracted and extracted.strip():
                                reasoning_parts.append(extracted.strip())
                    except Exception:
                        pass

                    # Strategy 2: Claude format - thinking blocks in content array
                    # {"content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "..."}]}
                    try:
                        content_array = msg.get("content")
                        if isinstance(content_array, list):
                            for block in content_array:
                                if isinstance(block, dict) and block.get("type") == "thinking":
                                    thinking_text = block.get("thinking")
                                    if thinking_text and isinstance(thinking_text, str) and thinking_text.strip():
                                        reasoning_parts.append(thinking_text.strip())
                    except Exception:
                        pass

                    # Strategy 3: Gemini format - parts array with thought=true flag
                    # {"parts": [{"text": "...", "thought": true}, {"text": "..."}]}
                    try:
                        parts_array = msg.get("parts")
                        if isinstance(parts_array, list):
                            for part in parts_array:
                                if isinstance(part, dict) and part.get("thought") is True:
                                    thought_text = part.get("text")
                                    if thought_text and isinstance(thought_text, str) and thought_text.strip():
                                        reasoning_parts.append(thought_text.strip())
                    except Exception:
                        pass

                    # Strategy 4: Fallback - try other possible field names
                    try:
                        for field_name in ["chain_of_thought", "cot", "thinking", "thinking_log", "reasoning_log"]:
                            field_value = msg.get(field_name)
                            if field_value:
                                extracted = _extract_text_from_message(field_value)
                                if extracted and extracted.strip():
                                    reasoning_parts.append(extracted.strip())
                                    break  # Only take first match from fallback fields
                    except Exception:
                        pass

                    # Merge all reasoning segments
                    if reasoning_parts:
                        merged = "\n\n--- [Reasoning Section] ---\n\n".join(reasoning_parts)
                        logger.debug(f"Reasoning content extracted: {len(merged)} chars from API response")
                        return merged

                    return ""

                except Exception as e:
                    logger.warning(f"Failed to extract reasoning content from API response: {e}")
                    return ""

            # Extract reasoning content for later merging
            api_reasoning_content = _extract_reasoning_content_safe(result)

            # Check if response was truncated due to length limit
            if finish_reason == "length":
                logger.warning("AI response was truncated due to token limit. Consider increasing max_tokens.")
                # Try to get content from reasoning field if available (some models put partial content there)
                raw_content = message.get("reasoning") or message.get("content")
            else:
                raw_content = message.get("content")

            text_content = _extract_text_from_message(raw_content)

            if not text_content and reasoning_text:
                # Some providers keep reasoning separately even on normal completion
                text_content = reasoning_text
            elif not text_content and api_reasoning_content:
                # Fallback: DeepSeek Reasoner may put JSON in reasoning_content
                text_content = api_reasoning_content
                logger.info("Using reasoning_content as fallback for empty content (DeepSeek Reasoner)")

            if not text_content:
                logger.error(
                    "Empty content in AI response: %s",
                    {k: v for k, v in result.items() if k != "usage"},
                )
                return None

            # Try to extract JSON from the text
            # Sometimes AI might wrap JSON in markdown code blocks
            raw_decision_text = text_content.strip()
            cleaned_content = raw_decision_text
            if "```json" in cleaned_content:
                cleaned_content = cleaned_content.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned_content:
                cleaned_content = cleaned_content.split("```")[1].split("```")[0].strip()

            # Handle potential JSON parsing issues with escape sequences
            try:
                decision = json.loads(cleaned_content)
            except json.JSONDecodeError as parse_err:
                logger.warning("Initial JSON parse failed: %s", parse_err)
                logger.warning("Problematic content: %s...", cleaned_content[:200])

                cleaned = (
                    cleaned_content.replace("\n", " ")
                    .replace("\r", " ")
                    .replace("\t", " ")
                )
                cleaned = cleaned.replace("“", '"').replace("”", '"')
                cleaned = cleaned.replace("‘", "'").replace("’", "'")
                cleaned = cleaned.replace("–", "-").replace("—", "-").replace("‑", "-")

                try:
                    decision = json.loads(cleaned)
                    cleaned_content = cleaned
                    logger.info("Successfully parsed AI decision after cleanup")
                except json.JSONDecodeError:
                    logger.error("JSON parsing failed after cleanup, attempting manual extraction")
                    logger.error(f"Original AI response: {text_content[:1000]}...")
                    logger.error(f"Cleaned content: {cleaned[:1000]}...")
                    operation_match = re.search(r'"operation"\s*:\s*"([^"]+)"', text_content, re.IGNORECASE)
                    symbol_match = re.search(r'"symbol"\s*:\s*"([^"]+)"', text_content, re.IGNORECASE)
                    portion_match = re.search(r'"target_portion_of_balance"\s*:\s*([0-9.]+)', text_content)
                    reason_match = re.search(r'"reason"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', text_content, re.DOTALL)

                    if operation_match and symbol_match and portion_match:
                        decision = {
                            "operation": operation_match.group(1),
                            "symbol": symbol_match.group(1),
                            "target_portion_of_balance": float(portion_match.group(1)),
                            "reason": reason_match.group(1) if reason_match else "AI response parsing issue",
                        }
                        logger.info("Successfully recovered AI decision via manual extraction")
                        cleaned_content = json.dumps(decision)
                    else:
                        logger.error("Unable to extract required fields from AI response")
                        logger.error(f"Regex match results - operation: {operation_match.group(1) if operation_match else None}, symbol: {symbol_match.group(1) if symbol_match else None}, portion: {portion_match.group(1) if portion_match else None}, reason: {reason_match.group(1)[:100] if reason_match else None}...")
                        return None

            # Normalize into a list of decisions
            if isinstance(decision, dict) and isinstance(decision.get("decisions"), list):
                decision_entries = decision.get("decisions") or []
            elif isinstance(decision, list):
                decision_entries = decision
            elif isinstance(decision, dict):
                decision_entries = [decision]
            else:
                logger.error(f"AI response has unsupported structure: {type(decision)}")
                return None

            snapshot_source = cleaned_content if "cleaned_content" in locals() and cleaned_content else raw_decision_text

            structured_decisions: List[Dict[str, Any]] = []
            for idx, raw_entry in enumerate(decision_entries):
                if not isinstance(raw_entry, dict):
                    logger.warning(
                        "Skipping decision entry %s for account %s because it is %s instead of dict",
                        idx,
                        account.name,
                        type(raw_entry),
                    )
                    continue

                entry = dict(raw_entry)
                strategy_details = entry.get("trading_strategy")

                # Merge API reasoning content with trading_strategy
                # Priority: API reasoning (from reasoning models) > trading_strategy (from prompt) > fallback reasoning_text
                entry["_prompt_snapshot"] = prompt

                if api_reasoning_content:
                    # Reasoning model: merge trading_strategy and API reasoning content
                    base_strategy = strategy_details if isinstance(strategy_details, str) and strategy_details.strip() else ""
                    if base_strategy:
                        # Combine strategy description from JSON and real CoT from API (seamless merge)
                        entry["_reasoning_snapshot"] = f"{base_strategy}\n\n{api_reasoning_content}"
                    else:
                        # Only API reasoning content available
                        entry["_reasoning_snapshot"] = api_reasoning_content
                elif isinstance(strategy_details, str) and strategy_details.strip():
                    # Chat model: use trading_strategy from JSON
                    entry["_reasoning_snapshot"] = strategy_details.strip()
                else:
                    # Fallback: use reasoning_text extracted earlier
                    entry["_reasoning_snapshot"] = reasoning_text or ""

                entry["_raw_decision_text"] = snapshot_source
                structured_decisions.append(entry)

            if not structured_decisions:
                logger.error("AI response for %s contained no usable decision entries", account.name)
                return None

            logger.info(f"AI decisions for {account.name}: {structured_decisions}")
            return structured_decisions

        logger.error(f"Unexpected AI response format: {result}")
        return None
        
    except requests.RequestException as err:
        logger.error(f"AI API request failed: {err}")
        return None
    except json.JSONDecodeError as err:
        logger.error(f"Failed to parse AI response as JSON: {err}")
        # Try to log the content that failed to parse
        try:
            if 'text_content' in locals():
                logger.error(f"Content that failed to parse: {text_content[:500]}")
        except:
            pass
        return None
    except Exception as err:
        logger.error(f"Unexpected error calling AI: {err}", exc_info=True)
        return None


def save_ai_decision(
    db: Session,
    account: Account,
    decision: Dict,
    portfolio: Dict,
    executed: bool = False,
    order_id: Optional[int] = None,
    wallet_address: Optional[str] = None,
    # Decision tracking fields for analysis chain
    prompt_template_id: Optional[int] = None,
    signal_trigger_id: Optional[int] = None,
    hyperliquid_order_id: Optional[str] = None,
    tp_order_id: Optional[str] = None,
    sl_order_id: Optional[str] = None,
    # Exchange identifier for attribution analysis
    exchange: Optional[str] = None,
) -> None:
    """Save AI decision to the decision log"""
    try:
        operation = decision.get("operation", "").lower() if decision.get("operation") else ""
        symbol_raw = decision.get("symbol")
        symbol = symbol_raw.upper() if symbol_raw else None
        target_portion = float(decision.get("target_portion_of_balance", 0)) if decision.get("target_portion_of_balance") is not None else 0.0
        reason = decision.get("reason", "No reason provided")
        prompt_snapshot = decision.get("_prompt_snapshot")
        reasoning_snapshot = decision.get("_reasoning_snapshot")
        raw_decision_snapshot = decision.get("_raw_decision_text")
        decision_snapshot_structured = None
        try:
            decision_payload = {k: v for k, v in decision.items() if not k.startswith("_")}
            decision_snapshot_structured = json.dumps(decision_payload, indent=2, ensure_ascii=False)
        except Exception:
            decision_snapshot_structured = raw_decision_snapshot

        if (not reasoning_snapshot or not reasoning_snapshot.strip()) and isinstance(raw_decision_snapshot, str):
            candidate = raw_decision_snapshot.strip()
            extracted_reasoning: Optional[str] = None
            if candidate:
                # Try to strip JSON payload to keep narrative reasoning only
                json_start = candidate.find('{')
                json_end = candidate.rfind('}')
                if json_start != -1 and json_end != -1 and json_end > json_start:
                    prefix = candidate[:json_start].strip()
                    suffix = candidate[json_end + 1 :].strip()
                    parts = [part for part in (prefix, suffix) if part]
                    if parts:
                        extracted_reasoning = '\n\n'.join(parts)
                else:
                    extracted_reasoning = candidate if not candidate.startswith('{') else None

            if extracted_reasoning:
                reasoning_snapshot = extracted_reasoning

        # Calculate previous portion for the symbol
        prev_portion = 0.0
        if operation in ["sell", "hold"] and symbol:
            positions = portfolio.get("positions", {})
            if symbol in positions:
                symbol_value = positions[symbol]["current_value"]
                total_balance = portfolio["total_assets"]
                if total_balance > 0:
                    prev_portion = symbol_value / total_balance

        # Get Hyperliquid environment for decision tagging
        # IMPORTANT: Always use global trading mode for accurate logging
        from services.hyperliquid_environment import get_global_trading_mode
        hyperliquid_environment = get_global_trading_mode(db)

        # Create decision log entry
        decision_log = AIDecisionLog(
            account_id=account.id,
            reason=reason,
            operation=operation,
            symbol=symbol,
            prev_portion=Decimal(str(prev_portion)),
            target_portion=Decimal(str(target_portion)),
            total_balance=Decimal(str(portfolio["total_assets"])),
            executed="true" if executed else "false",
            order_id=order_id,
            prompt_snapshot=prompt_snapshot,
            reasoning_snapshot=reasoning_snapshot,
            decision_snapshot=decision_snapshot_structured or raw_decision_snapshot,
            hyperliquid_environment=hyperliquid_environment,
            wallet_address=wallet_address,
            # Decision tracking fields for analysis chain
            prompt_template_id=prompt_template_id,
            signal_trigger_id=signal_trigger_id,
            hyperliquid_order_id=hyperliquid_order_id,
            tp_order_id=tp_order_id,
            sl_order_id=sl_order_id,
            # Exchange identifier (NULL treated as "hyperliquid" for backward compatibility)
            exchange=exchange,
        )

        db.add(decision_log)
        db.commit()
        db.refresh(decision_log)

        if decision_log.decision_time:
            set_last_trigger(db, account.id, decision_log.decision_time)

        symbol_str = symbol if symbol else "N/A"
        logger.info(f"Saved AI decision log for account {account.name}: {operation} {symbol_str} "
                   f"prev_portion={prev_portion:.4f} target_portion={target_portion:.4f} executed={executed}")

        # Log to system logger
        system_logger.log_ai_decision(
            account_name=account.name,
            model=account.model,
            operation=operation,
            symbol=symbol,
            reason=reason,
            success=executed
        )

        # Broadcast AI decision update via WebSocket
        import asyncio
        from api.ws import broadcast_model_chat_update

        try:
            broadcast_data = {
                "id": decision_log.id,
                "account_id": account.id,
                "account_name": account.name,
                "model": account.model,
                "decision_time": decision_log.decision_time.isoformat() if hasattr(decision_log.decision_time, 'isoformat') else str(decision_log.decision_time),
                "operation": decision_log.operation.upper() if decision_log.operation else "HOLD",
                "symbol": decision_log.symbol,
                "reason": decision_log.reason,
                "prev_portion": float(decision_log.prev_portion),
                "target_portion": float(decision_log.target_portion),
                "total_balance": float(decision_log.total_balance),
                "executed": decision_log.executed == "true",
                "order_id": decision_log.order_id,
                "prompt_snapshot": decision_log.prompt_snapshot,
                "reasoning_snapshot": decision_log.reasoning_snapshot,
                "decision_snapshot": decision_log.decision_snapshot,
                "wallet_address": decision_log.wallet_address,
            }
            
            # Check if there's a running event loop
            try:
                loop = asyncio.get_running_loop()
                # Event loop is running, create task
                loop.create_task(broadcast_model_chat_update(broadcast_data))
            except RuntimeError:
                # No running event loop, run synchronously
                asyncio.run(broadcast_model_chat_update(broadcast_data))
        except Exception as broadcast_err:
            # Don't fail the save operation if broadcast fails
            logger.warning(f"Failed to broadcast AI decision update: {broadcast_err}")

        # Bot push notification for AI Trader decisions
        try:
            from api.bot_routes import get_notification_config_dict
            from services.bot_event_service import enqueue_system_event, push_event_to_all_channels
            notif_config = get_notification_config_dict(db)
            if notif_config.get("ai_trader", True) and executed and operation and operation.lower() != "hold":
                event_data = {
                    "trader_name": account.name,
                    "operation": operation.upper() if operation else "HOLD",
                    "symbol": symbol or "N/A",
                    "target_portion": f"{target_portion:.1%}" if target_portion else "0%",
                    "price": "market",
                    "reason": reason[:100] if reason else "",
                }
                results = enqueue_system_event(db, "ai_decision", event_data)
                if results:
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(push_event_to_all_channels(db, results))
                    except RuntimeError:
                        asyncio.run(push_event_to_all_channels(db, results))
        except Exception as notif_err:
            logger.warning(f"Failed to send bot notification: {notif_err}")

    except Exception as err:
        logger.error(f"Failed to save AI decision log: {err}")
        db.rollback()


def get_active_ai_accounts(db: Session) -> List[Account]:
    """Get all active AI accounts that are not using default API key"""
    accounts = db.query(Account).filter(
        Account.is_active == "true",
        Account.account_type == "AI",
        Account.auto_trading_enabled == "true",
        Account.is_deleted != True
    ).all()
    
    if not accounts:
        return []
    
    # Filter out default accounts
    valid_accounts = [acc for acc in accounts if not _is_default_api_key(acc.api_key)]
    
    if not valid_accounts:
        logger.debug("No valid AI accounts found (all using default keys)")
        return []
        
    return valid_accounts


def _parse_kline_indicator_variables(template_text: str) -> Dict[str, Dict[str, Any]]:
    """
    Parse K-line and indicator variables from prompt template.

    Extracts variables like:
    - {BTC_klines_15m}(200) - K-line data
    - {BTC_RSI14_15m} - Technical indicators
    - {BTC_market_data} - Market ticker data
    - {BTC_CVD_15m} - Market flow indicators (CVD, TAKER, OI, FUNDING, DEPTH)

    Returns grouped by (symbol, period) for optimization:
    {
        ('BTC', '15m'): {
            'klines': {'count': 200},
            'indicators': ['RSI14', 'MACD'],
            'flow_indicators': ['CVD', 'TAKER'],
            'market_data': True
        },
        ('BTC', None): {
            'market_data': True
        }
    }
    """
    # Pattern for K-line variables: {SYMBOL_klines_PERIOD}(COUNT)
    kline_pattern = r'\{([A-Z]+)_klines_(\w+)\}(?:\((\d+)\))?'

    # Pattern for indicator variables: {SYMBOL_INDICATOR_PERIOD}
    # Supports: RSI14, RSI7, MACD, STOCH, MA, EMA, BOLL, ATR14, VWAP, OBV
    indicator_pattern = r'\{([A-Z]+)_(RSI\d+|MACD|STOCH|MA\d*|EMA\d*|BOLL|ATR\d+|VWAP|OBV)_(\w+)\}'

    # Pattern for market flow variables: {SYMBOL_FLOW_PERIOD}
    # Supports: CVD, TAKER, OI, OI_DELTA, FUNDING, DEPTH, IMBALANCE, PRICE_CHANGE, VOLATILITY
    # Note: OI_DELTA must come before OI in the pattern to match correctly
    flow_pattern = r'\{([A-Z]+)_(CVD|TAKER|OI_DELTA|OI|FUNDING|DEPTH|IMBALANCE|PRICE_CHANGE|VOLATILITY)_(\w+)\}'

    # Pattern for market data: {SYMBOL_market_data}
    market_data_pattern = r'\{([A-Z]+)_market_data\}'

    grouped = {}

    def _ensure_key(key):
        if key not in grouped:
            grouped[key] = {
                'klines': None,
                'indicators': [],
                'flow_indicators': [],
                'market_data': False
            }

    # Parse K-line variables
    for match in re.finditer(kline_pattern, template_text):
        symbol = match.group(1)
        if symbol == "SYMBOL":
            continue  # Skip documentation placeholder
        period = match.group(2)
        count = int(match.group(3)) if match.group(3) else 500  # Default 500

        key = (symbol, period)
        _ensure_key(key)
        grouped[key]['klines'] = {'count': count}

        logger.debug(f"Found K-line variable: {symbol}_klines_{period}({count})")

    # Parse indicator variables
    for match in re.finditer(indicator_pattern, template_text):
        symbol = match.group(1)
        if symbol == "SYMBOL":
            continue  # Skip documentation placeholder
        indicator = match.group(2)
        period = match.group(3)

        key = (symbol, period)
        _ensure_key(key)

        # Handle compound indicators (MA, EMA expand to multiple)
        if indicator == 'MA':
            grouped[key]['indicators'].extend(['MA5', 'MA10', 'MA20'])
        elif indicator == 'EMA':
            grouped[key]['indicators'].extend(['EMA20', 'EMA50', 'EMA100'])
        else:
            grouped[key]['indicators'].append(indicator)

        logger.debug(f"Found indicator variable: {symbol}_{indicator}_{period}")

    # Parse market flow variables
    for match in re.finditer(flow_pattern, template_text):
        symbol = match.group(1)
        if symbol == "SYMBOL":
            continue  # Skip documentation placeholder
        flow_indicator = match.group(2)
        period = match.group(3)

        key = (symbol, period)
        _ensure_key(key)
        grouped[key]['flow_indicators'].append(flow_indicator)

        logger.debug(f"Found flow indicator variable: {symbol}_{flow_indicator}_{period}")
    
    # Parse market data variables
    for match in re.finditer(market_data_pattern, template_text):
        symbol = match.group(1)
        if symbol == "SYMBOL":
            continue  # Skip documentation placeholder

        key = (symbol, None)
        _ensure_key(key)
        grouped[key]['market_data'] = True

        logger.debug(f"Found market data variable: {symbol}_market_data")

    # Remove duplicates from indicators and flow_indicators lists
    for key in grouped:
        grouped[key]['indicators'] = list(set(grouped[key]['indicators']))
        grouped[key]['flow_indicators'] = list(set(grouped[key]['flow_indicators']))

    logger.info(f"Parsed {len(grouped)} groups of K-line/indicator/flow/market-data variables")
    return grouped


def _parse_factor_variables(template_text: str) -> List[tuple]:
    """
    Parse factor variables from prompt template.
    Preferred format: {SYMBOL_factor_PERIOD_NAME}
    Legacy format: {SYMBOL_factor_NAME} -> defaults to 5m

    Returns list of (symbol, period, factor_name, var_name) tuples.
    """
    results = []
    seen = set()

    preferred_pattern = r'\{([A-Z][A-Z0-9]*)_factor_(1m|5m|15m|1h|4h|1d)_([A-Za-z][A-Za-z0-9_]*)\}'
    for match in re.finditer(preferred_pattern, template_text):
        symbol = match.group(1)
        period = match.group(2)
        factor_name = match.group(3)
        if symbol == "SYMBOL":
            continue
        key = (symbol, period, factor_name)
        if key not in seen:
            seen.add(key)
            var_name = f"{symbol}_factor_{period}_{factor_name}"
            results.append((symbol, period, factor_name, var_name))

    legacy_pattern = r'\{([A-Z][A-Z0-9]*)_factor_([A-Za-z][A-Za-z0-9_]*)\}'
    for match in re.finditer(legacy_pattern, template_text):
        symbol = match.group(1)
        factor_name = match.group(2)
        if symbol == "SYMBOL":
            continue
        key = (symbol, "5m", factor_name)
        if key not in seen:
            seen.add(key)
            var_name = f"{symbol}_factor_{factor_name}"
            results.append((symbol, "5m", factor_name, var_name))

    return results


def _build_factor_context(
    factor_vars: List[tuple], environment: str, exchange: str
) -> Dict[str, str]:
    """
    Build factor context dict for prompt template variables.
    Each variable resolves to a text block with value + effectiveness.
    """
    from database.connection import SessionLocal
    from program_trader.data_provider import compute_factor_snapshot
    from services.market_data import get_kline_data

    context = {}
    db = SessionLocal()
    try:
        # Sync rule: Prompt factor variables must stay aligned with Program
        # live get_factor() and Program backtest get_factor().
        for symbol, period, factor_name, var_name in factor_vars:
            try:
                market = "binance" if exchange == "binance" else "CRYPTO"
                snapshot = compute_factor_snapshot(
                    db=db,
                    symbol=symbol,
                    factor_name=factor_name,
                    period=period,
                    exchange=exchange,
                    klines_loader=lambda requested_period, count: get_kline_data(
                        symbol,
                        market=market,
                        period=requested_period,
                        count=count,
                        environment=environment,
                        persist=False,
                    ) or [],
                    include_effectiveness=True,
                )

                if snapshot.get("error"):
                    context[var_name] = snapshot["error"]
                    continue

                desc = snapshot.get("description") or ""
                parts = [
                    f"name={factor_name}(id={snapshot.get('id')})",
                    f"period={period}",
                    f"expr={snapshot.get('expression')}",
                ]
                if desc:
                    parts.append(f"desc={desc}")
                value = snapshot.get("value")
                parts.append(f"value={value:.4f}" if value is not None else "value=N/A")
                if snapshot.get("ic") is not None:
                    parts.append(f"IC={float(snapshot['ic']):.4f}")
                if snapshot.get("icir") is not None:
                    parts.append(f"ICIR={float(snapshot['icir']):.2f}")
                if snapshot.get("win_rate") is not None:
                    parts.append(f"WinRate={float(snapshot['win_rate']):.1f}%")
                if snapshot.get("decay_half_life_hours") is not None:
                    dh = int(snapshot["decay_half_life_hours"])
                    parts.append("Persistent" if dh == -1 else f"Decay={dh}h")

                context[var_name] = " | ".join(parts)
            except Exception as e:
                logger.warning(f"Failed to compute factor {factor_name} for {symbol}/{period}: {e}")
                context[var_name] = f"Error computing factor"

    finally:
        db.close()

    return context


def _format_single_indicator(indicator_name: str, indicator_data: Any) -> str:
    """
    Format a single technical indicator for prompt injection.

    Args:
        indicator_name: Name of the indicator (e.g., 'RSI14', 'MACD')
        indicator_data: Calculated indicator data

    Returns:
        Formatted string for prompt
    """
    if not indicator_data:
        return "N/A (Insufficient data for calculation)"

    try:
        if indicator_name.startswith('RSI'):
            # RSI format: value + interpretation + last 5 values
            values = indicator_data if isinstance(indicator_data, list) else []
            if not values:
                return "N/A"

            current = values[-1]
            last_5 = values[-5:] if len(values) >= 5 else values

            # Interpret RSI value
            if current > 70:
                interpretation = "Overbought"
            elif current < 30:
                interpretation = "Oversold"
            else:
                interpretation = "Neutral"

            result = [
                f"{indicator_name}: {current:.2f} ({interpretation})",
                f"{indicator_name} last 5: {', '.join(f'{v:.2f}' for v in last_5)}"
            ]
            return "\n".join(result)

        elif indicator_name == 'MACD':
            # MACD format: MACD line, Signal line, Histogram + interpretation
            macd_line = indicator_data.get('macd', [])
            signal_line = indicator_data.get('signal', [])
            histogram = indicator_data.get('histogram', [])

            if not macd_line or not signal_line or not histogram:
                return "N/A"

            current_macd = macd_line[-1]
            current_signal = signal_line[-1]
            current_hist = histogram[-1]
            last_5_hist = histogram[-5:] if len(histogram) >= 5 else histogram

            # Interpret MACD
            momentum = "Bullish momentum" if current_hist > 0 else "Bearish momentum"

            result = [
                f"MACD Line: {current_macd:.4f}",
                f"Signal Line: {current_signal:.4f}",
                f"Histogram: {current_hist:.4f} ({momentum})",
                f"Histogram last 5: {', '.join(f'{v:.4f}' for v in last_5_hist)}"
            ]
            return "\n".join(result)

        elif indicator_name.startswith('MA') or indicator_name.startswith('EMA'):
            # Moving average format: current value + last 5 values
            values = indicator_data if isinstance(indicator_data, list) else []
            if not values:
                return "N/A"

            current = values[-1]
            last_5 = values[-5:] if len(values) >= 5 else values

            result = [
                f"{indicator_name}: {current:.2f}",
                f"{indicator_name} last 5: {', '.join(f'{v:.2f}' for v in last_5)}"
            ]
            return "\n".join(result)

        elif indicator_name == 'BOLL':
            # Bollinger Bands format: Upper, Middle, Lower bands
            upper = indicator_data.get('upper', [])
            middle = indicator_data.get('middle', [])
            lower = indicator_data.get('lower', [])

            if not upper or not middle or not lower:
                return "N/A"

            result = [
                f"Upper Band: {upper[-1]:.2f}",
                f"Middle Band: {middle[-1]:.2f}",
                f"Lower Band: {lower[-1]:.2f}",
                f"Band Width: {(upper[-1] - lower[-1]):.2f}"
            ]
            return "\n".join(result)

        elif indicator_name.startswith('ATR'):
            # ATR format: current value + interpretation
            values = indicator_data if isinstance(indicator_data, list) else []
            if not values:
                return "N/A"

            current = values[-1]
            avg_atr = sum(values[-20:]) / min(len(values), 20) if values else 0

            volatility = "High volatility" if current > avg_atr * 1.2 else "Normal volatility"

            result = [
                f"{indicator_name}: {current:.2f} ({volatility})",
                f"20-period average: {avg_atr:.2f}"
            ]
            return "\n".join(result)

        elif indicator_name == 'STOCH':
            # Stochastic Oscillator format: %K and %D lines + interpretation
            k_line = indicator_data.get('k', [])
            d_line = indicator_data.get('d', [])

            if not k_line or not d_line:
                return "N/A"

            current_k = k_line[-1]
            current_d = d_line[-1]
            last_5_k = k_line[-5:] if len(k_line) >= 5 else k_line

            # Interpret Stochastic
            if current_k > 80:
                interpretation = "Overbought"
            elif current_k < 20:
                interpretation = "Oversold"
            else:
                interpretation = "Neutral"

            result = [
                f"%K Line: {current_k:.2f} ({interpretation})",
                f"%D Line: {current_d:.2f}",
                f"%K last 5: {', '.join(f'{v:.2f}' for v in last_5_k)}"
            ]
            return "\n".join(result)

        elif indicator_name == 'VWAP':
            # VWAP format: current value + comparison with price
            values = indicator_data if isinstance(indicator_data, list) else []
            if not values:
                return "N/A"

            current = values[-1]
            last_5 = values[-5:] if len(values) >= 5 else values

            result = [
                f"VWAP: {current:.2f}",
                f"VWAP last 5: {', '.join(f'{v:.2f}' for v in last_5)}",
                f"Note: Price above VWAP suggests bullish sentiment, below suggests bearish"
            ]
            return "\n".join(result)

        elif indicator_name == 'OBV':
            # OBV format: current value + trend
            values = indicator_data if isinstance(indicator_data, list) else []
            if not values:
                return "N/A"

            current = values[-1]
            last_5 = values[-5:] if len(values) >= 5 else values

            # Determine trend
            if len(values) >= 2:
                trend = "Rising" if current > values[-2] else "Falling"
            else:
                trend = "N/A"

            result = [
                f"OBV: {current:.0f} ({trend})",
                f"OBV last 5: {', '.join(f'{v:.0f}' for v in last_5)}"
            ]
            return "\n".join(result)

        else:
            return "N/A"

    except Exception as e:
        logger.error(f"Error formatting indicator {indicator_name}: {e}")
        return "N/A"


def _format_flow_indicator(indicator_name: str, indicator_data: Any, symbol: str = "", period: str = "", exchange: str = "") -> str:
    """
    Format a market flow indicator for prompt injection.

    Args:
        indicator_name: Name of the flow indicator (e.g., 'CVD', 'TAKER', 'OI')
        indicator_data: Calculated flow indicator data dict

    Returns:
        Formatted string for prompt (objective data only, no interpretations)
    """
    if not indicator_data:
        if symbol and period and exchange:
            return f"N/A ({symbol} {indicator_name} on {exchange}: insufficient data for {period} calculation. Symbol may need more time after being added to watchlist.)"
        return "N/A (Insufficient data for calculation)"

    try:
        period = indicator_data.get("period", "")

        if indicator_name == "CVD":
            current = indicator_data.get("current", 0)
            last_5 = indicator_data.get("last_5", [])
            cumulative = indicator_data.get("cumulative", 0)

            result = [
                f"CVD ({period}): {_format_usd(current)}",
                f"CVD last 5: {', '.join(_format_usd(v) for v in last_5)}",
                f"Cumulative: {_format_usd(cumulative)}"
            ]
            return "\n".join(result)

        elif indicator_name == "TAKER":
            import math
            buy = indicator_data.get("buy", 0)
            sell = indicator_data.get("sell", 0)
            ratio = indicator_data.get("ratio", 1.0)
            ratio_last_5 = indicator_data.get("ratio_last_5", [])
            volume_last_5 = indicator_data.get("volume_last_5", [])

            # Calculate log ratio: positive = buyers dominate, negative = sellers dominate
            log_ratio = math.log(ratio) if ratio > 0 else 0

            result = [
                f"Taker Buy: {_format_usd(buy)} | Taker Sell: {_format_usd(sell)}",
                f"Buy/Sell Ratio: {ratio:.2f}x (log: {log_ratio:+.2f})",
                f"Ratio last 5: {', '.join(f'{r:.2f}x' for r in ratio_last_5)}",
                f"Volume last 5: {', '.join(_format_usd(v) for v in volume_last_5)}"
            ]
            return "\n".join(result)

        elif indicator_name == "OI":
            current = indicator_data.get("current", 0)
            last_5 = indicator_data.get("last_5", [])
            is_stale = indicator_data.get("stale", False)
            age_minutes = indicator_data.get("age_minutes", 0)

            result = [f"Open Interest: {_format_usd(current)}"]
            if is_stale and age_minutes > 0:
                result[0] += f" (data from {age_minutes}min ago)"
            result.append(f"OI last 5: {', '.join(_format_usd(v) for v in last_5)}")
            return "\n".join(result)

        elif indicator_name == "OI_DELTA":
            current = indicator_data.get("current", 0)
            last_5 = indicator_data.get("last_5", [])
            is_stale = indicator_data.get("stale", False)
            expanded_window = indicator_data.get("expanded_window", 0)

            result = [f"OI Delta ({period}): {current:+.2f}%"]
            if is_stale and expanded_window > 0:
                result[0] += f" (expanded {expanded_window}x window)"
            result.append(f"OI Delta last 5: {', '.join(f'{c:+.2f}%' for c in last_5)}")
            return "\n".join(result)

        elif indicator_name == "FUNDING":
            # Values are in K-line display unit (raw × 1000000)
            # current_pct is the actual percentage
            current = indicator_data.get("current", 0)
            current_pct = indicator_data.get("current_pct", current / 10000)
            change = indicator_data.get("change", 0)
            change_pct = indicator_data.get("change_pct", change / 10000)
            last_5 = indicator_data.get("last_5", [])
            annualized = indicator_data.get("annualized", 0)

            # Format change with sign
            change_sign = "+" if change >= 0 else ""

            result = [
                f"Funding Rate: {current:.1f} ({current_pct:.4f}%)",
                f"Funding Change: {change_sign}{change:.1f} ({change_sign}{change_pct:.4f}%)",
                f"Annualized: {annualized:.2f}%",
                f"Funding last 5: {', '.join(f'{f:.1f}' for f in last_5)}"
            ]
            return "\n".join(result)

        elif indicator_name == "DEPTH":
            bid = indicator_data.get("bid", 0)
            ask = indicator_data.get("ask", 0)
            ratio = indicator_data.get("ratio", 1.0)
            ratio_last_5 = indicator_data.get("ratio_last_5", [])
            spread = indicator_data.get("spread")

            result = [
                f"Bid Depth: {_format_usd(bid)} | Ask Depth: {_format_usd(ask)}",
                f"Depth Ratio (Bid/Ask): {ratio:.2f}",
                f"Ratio last 5: {', '.join(f'{r:.2f}' for r in ratio_last_5)}"
            ]
            if spread is not None:
                result.append(f"Spread: {spread:.4f}")
            return "\n".join(result)

        elif indicator_name == "IMBALANCE":
            current = indicator_data.get("current", 0)
            last_5 = indicator_data.get("last_5", [])

            result = [
                f"Order Imbalance: {current:+.3f}",
                f"Imbalance last 5: {', '.join(f'{v:+.3f}' for v in last_5)}"
            ]
            return "\n".join(result)

        elif indicator_name == "PRICE_CHANGE":
            current = indicator_data.get("current", 0)
            start_price = indicator_data.get("start_price")
            end_price = indicator_data.get("end_price")
            last_5 = indicator_data.get("last_5", [])

            # Calculate USD change value
            if start_price and end_price:
                change_usd = end_price - start_price
                usd_str = _format_price_value(change_usd, reference_price=end_price, with_sign=True)
                result = [f"Price Change: {current:+.3f}% ({usd_str})"]
                result.append(f"Price: {_format_price_value(start_price)} -> {_format_price_value(end_price)}")
            else:
                result = [f"Price Change: {current:+.3f}%"]
            if last_5:
                result.append(f"Change last 5: {', '.join(f'{v:+.3f}%' for v in last_5)}")
            return "\n".join(result)

        elif indicator_name == "VOLATILITY":
            current = indicator_data.get("current", 0)
            high = indicator_data.get("high")
            low = indicator_data.get("low")
            last_5 = indicator_data.get("last_5", [])

            # Calculate USD range value
            if high and low:
                range_usd = high - low
                usd_str = _format_price_value(range_usd, reference_price=high, with_sign=False)
                result = [f"Volatility: {current:.3f}% ({usd_str})"]
                result.append(f"Range: {_format_price_value(low)} - {_format_price_value(high)}")
            else:
                result = [f"Volatility: {current:.3f}%"]
            if last_5:
                result.append(f"Volatility last 5: {', '.join(f'{v:.3f}%' for v in last_5)}")
            return "\n".join(result)

        else:
            return "N/A"

    except Exception as e:
        logger.error(f"Error formatting flow indicator {indicator_name}: {e}")
        return "N/A"


def _format_usd(value: float) -> str:
    """Format USD value with appropriate unit (K, M, B)"""
    if value is None:
        return "N/A"
    abs_val = abs(value)
    sign = "+" if value >= 0 else "-"
    if abs_val >= 1_000_000_000:
        return f"{sign}${abs_val/1_000_000_000:.2f}B"
    elif abs_val >= 1_000_000:
        return f"{sign}${abs_val/1_000_000:.2f}M"
    elif abs_val >= 1_000:
        return f"{sign}${abs_val/1_000:.2f}K"
    else:
        return f"{sign}${abs_val:.2f}"


def _format_price_value(value: float, reference_price: float = None, with_sign: bool = False) -> str:
    """
    Format price value with adaptive decimal places based on price magnitude.

    Args:
        value: The price value to format
        reference_price: Reference price to determine decimal places (uses value if None)
        with_sign: Whether to include +/- sign prefix

    Returns:
        Formatted price string like "$94,521.00" or "$+2,156.00"
    """
    if value is None:
        return "N/A"

    ref = reference_price if reference_price is not None else abs(value)
    abs_val = abs(value)

    # Determine decimal places based on reference price magnitude
    if ref >= 1000:
        decimals = 2
    elif ref >= 1:
        decimals = 4
    elif ref >= 0.01:
        decimals = 6
    else:
        decimals = 8

    # Format with thousand separators
    formatted = f"{abs_val:,.{decimals}f}"

    if with_sign:
        sign = "+" if value >= 0 else "-"
        return f"${sign}{formatted}"
    else:
        return f"${formatted}"


def _build_klines_and_indicators_context(
    variable_groups: Dict[str, Dict[str, Any]],
    db: Session,
    environment: str = "mainnet",
    exchange: str = "hyperliquid",
) -> Dict[str, str]:
    """
    Build K-line and indicator context for prompt filling.

    Uses parallel fetching for improved performance when multiple symbols/periods
    are requested. Each (symbol, period) combination is processed concurrently.

    Args:
        variable_groups: Parsed variable groups from _parse_kline_indicator_variables
        db: Database session
        environment: Trading environment (mainnet/testnet)
        exchange: Exchange to use for market data ("hyperliquid" or "binance")

    Returns:
        Dict mapping variable names to formatted strings
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    context = {}

    # If only one group, process directly without threading overhead
    if len(variable_groups) <= 1:
        for (symbol, period), requirements in variable_groups.items():
            result = _process_single_symbol_period(
                symbol,
                period,
                requirements,
                environment,
                exchange,
            )
            context.update(result)
        logger.info(f"Built context with {len(context)} variables for environment: {environment}")
        return context

    # Use thread pool for parallel fetching
    # Limit workers to avoid overwhelming the API
    max_workers = min(len(variable_groups), 4)

    start_time = time.time()
    logger.info(f"[PARALLEL] Starting parallel fetch for {len(variable_groups)} symbol/period groups with {max_workers} workers")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_key = {}
        for (symbol, period), requirements in variable_groups.items():
            future = executor.submit(
                _process_single_symbol_period,
                symbol, period, requirements, environment, exchange
            )
            future_to_key[future] = (symbol, period)

        # Collect results as they complete
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                result = future.result()
                context.update(result)
                logger.debug(f"[PARALLEL] Completed {key[0]} {key[1]}: {len(result)} variables")
            except Exception as e:
                logger.error(f"[PARALLEL] Error processing {key[0]} {key[1]}: {e}", exc_info=True)

    elapsed = time.time() - start_time
    logger.info(f"[PARALLEL] Built context with {len(context)} variables in {elapsed:.2f}s for environment: {environment}")
    return context


def _process_single_symbol_period(
    symbol: str,
    period: Optional[str],
    requirements: Dict[str, Any],
    environment: str,
    exchange: str = "hyperliquid",
) -> Dict[str, str]:
    """
    Process a single (symbol, period) combination and return context variables.

    This function is designed to be called in parallel for different symbol/period
    combinations. It handles K-line fetching, indicator calculation, and formatting.

    Args:
        symbol: Trading symbol (e.g., "BTC")
        period: Time period (e.g., "5m", "1h") or None for market data
        requirements: Dict with 'klines', 'indicators', 'flow_indicators', 'market_data' keys
        environment: Trading environment (mainnet/testnet)
        exchange: Exchange to use for market data ("hyperliquid" or "binance")

    Returns:
        Dict mapping variable names to formatted strings
    """
    from services.market_data import get_kline_data, get_ticker_data

    context = {}
    # Determine market parameter based on exchange
    market_param = "binance" if exchange == "binance" else "CRYPTO"

    try:
        # Handle market data (no period)
        if period is None and requirements.get('market_data'):
            logger.info(f"Processing market data for {symbol} in {environment} (exchange: {exchange})")
            try:
                ticker = get_ticker_data(symbol, market_param, environment)
                if ticker:
                    var_name = f"{symbol}_market_data"
                    context[var_name] = _format_market_data_block(symbol, ticker)
                    logger.debug(f"Added market data variable: {var_name}")
            except Exception as ticker_err:
                logger.warning(f"Failed to get ticker data for {symbol}: {ticker_err}")
            return context

        # Process K-lines and indicators (has period)
        logger.info(f"Processing {symbol} {period} for environment: {environment} (exchange: {exchange})")
        from services.technical_indicators import calculate_indicators
        from services.kline_ai_analysis_service import _format_klines_summary

        # Always fetch 500 candles for accurate indicator calculation
        # Skip persistence for prompt generation (real-time data only, no DB write overhead)
        kline_data = get_kline_data(
            symbol=symbol,
            market=market_param,
            period=period,
            count=500,
            environment=environment,
            persist=False
        )

        if not kline_data:
            logger.warning(f"No K-line data for {symbol} {period} in {environment}")
            return context

        # Process K-line variables
        if requirements.get('klines'):
            count = requirements['klines']['count']
            # Take last N candles for display
            display_klines = kline_data[-count:] if len(kline_data) >= count else kline_data
            formatted_klines = _format_klines_summary(display_klines)

            # Variable name: {BTC_klines_15m}
            var_name = f"{symbol}_klines_{period}"
            context[var_name] = formatted_klines
            logger.debug(f"Added K-line variable: {var_name} ({len(display_klines)} candles)")

        # Calculate and process indicators
        if requirements.get('indicators'):
            indicators_to_calc = requirements['indicators']
            calculated = calculate_indicators(kline_data, indicators_to_calc)

            # Track compound indicators (MA, EMA) for merged output
            ma_indicators = []
            ema_indicators = []

            for indicator_name in indicators_to_calc:
                indicator_data = calculated.get(indicator_name)
                formatted = _format_single_indicator(indicator_name, indicator_data)

                # Variable name: {BTC_RSI14_15m}
                var_name = f"{symbol}_{indicator_name}_{period}"
                context[var_name] = formatted
                logger.debug(f"Added indicator variable: {var_name}")

                # Track for compound output
                if indicator_name.startswith('MA') and indicator_name[2:].isdigit():
                    ma_indicators.append((indicator_name, formatted))
                elif indicator_name.startswith('EMA') and indicator_name[3:].isdigit():
                    ema_indicators.append((indicator_name, formatted))

            # Generate compound MA variable: {BTC_MA_15m}
            if ma_indicators:
                ma_lines = []
                for ind_name, ind_formatted in sorted(ma_indicators):
                    ma_lines.append(f"**{ind_name}**")
                    ma_lines.append(ind_formatted)
                    ma_lines.append("")
                compound_var = f"{symbol}_MA_{period}"
                context[compound_var] = "\n".join(ma_lines).strip()
                logger.debug(f"Added compound MA variable: {compound_var}")

            # Generate compound EMA variable: {BTC_EMA_15m}
            if ema_indicators:
                ema_lines = []
                for ind_name, ind_formatted in sorted(ema_indicators):
                    ema_lines.append(f"**{ind_name}**")
                    ema_lines.append(ind_formatted)
                    ema_lines.append("")
                compound_var = f"{symbol}_EMA_{period}"
                context[compound_var] = "\n".join(ema_lines).strip()
                logger.debug(f"Added compound EMA variable: {compound_var}")

        # Process market flow indicators
        # Note: flow indicators need db session, create a new one for thread safety
        if requirements.get('flow_indicators'):
            from services.market_flow_indicators import get_flow_indicators_for_prompt
            from database.connection import SessionLocal

            flow_indicators_to_calc = requirements['flow_indicators']
            with SessionLocal() as thread_db:
                flow_data = get_flow_indicators_for_prompt(
                    db=thread_db,
                    symbol=symbol,
                    period=period,
                    indicators=flow_indicators_to_calc,
                    exchange=exchange
                )

            for flow_name in flow_indicators_to_calc:
                flow_indicator_data = flow_data.get(flow_name)
                formatted = _format_flow_indicator(flow_name, flow_indicator_data, symbol=symbol, period=period, exchange=exchange)

                # Variable name: {BTC_CVD_15m}
                var_name = f"{symbol}_{flow_name}_{period}"
                context[var_name] = formatted
                logger.debug(f"Added flow indicator variable: {var_name}")

    except Exception as e:
        logger.error(f"Error processing {symbol} {period}: {e}", exc_info=True)

    return context
