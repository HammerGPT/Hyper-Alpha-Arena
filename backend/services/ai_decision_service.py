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


def _build_sampling_data(samples: Optional[List], target_symbol: Optional[str]) -> str:
    """Build sampling pool data section for Alpha Arena style prompts (single symbol)"""
    if not samples or not target_symbol:
        return "No sampling data available."

    lines = [
        f"Multi-timeframe price data for {target_symbol} (18-second intervals, oldest to newest):",
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


def _build_multi_symbol_sampling_data(symbols: List[str], sampling_pool) -> str:
    """Build sampling pool data for multiple symbols (Alpha Arena style)"""
    if not symbols:
        return "No symbols selected for sampling data."

    sections = []

    for symbol in symbols:
        samples = sampling_pool.get_samples(symbol)
        if not samples:
            sections.append(f"{symbol}: No sampling data available")
            continue

        lines = [
            f"{symbol} (18-second intervals, oldest to newest):",
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
    '      "reason": "<string explaining primary signals>",\n'
    '      "trading_strategy": "<string covering thesis, risk controls, and exit plan>"\n'
    '    }\n'
    '  ]\n'
    '}'
)


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
    symbol_metadata: Optional[Dict[str, Any]] = None,
    symbol_order: Optional[List[str]] = None,
) -> Dict[str, Any]:
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

    environment = getattr(account, "hyperliquid_environment", "testnet") or "testnet"

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

    # Legacy format variables (for backward compatibility with existing templates)
    account_state = _build_account_state(portfolio)
    market_snapshot = _build_market_snapshot(prices, positions, ordered_symbols)
    session_context = _build_session_context(account)
    sampling_data = _build_sampling_data(samples, target_symbol)

    # New Alpha Arena style variables
    runtime_minutes = _calculate_runtime_minutes(account)
    current_time_utc = now.isoformat() + "Z"
    total_return_percent = _calculate_total_return_percent(account)
    available_cash = _format_currency(portfolio.get('cash'))
    total_account_value = _format_currency(portfolio.get('total_assets'))
    holdings_detail = _build_holdings_detail(positions)
    market_prices = _build_market_prices(prices, ordered_symbols, symbol_display_map)
    output_format = OUTPUT_FORMAT_JSON.replace(SYMBOL_PLACEHOLDER, output_symbol_choices or "SYMBOL")

    # Hyperliquid-specific context
    max_leverage = getattr(account, "max_leverage", 3)
    default_leverage = getattr(account, "default_leverage", 1)

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
                max_leverage = float(pos.get('max_leverage', 10))
                margin_used = float(pos.get('margin_used', 0))
                position_value = float(pos.get('position_value', 0))
                roe = float(pos.get('return_on_equity', 0))
                funding_total = float(pos.get('cum_funding_all_time', 0))

                # Format values
                pnl_str = f"+${unrealized_pnl:,.2f}" if unrealized_pnl >= 0 else f"-${abs(unrealized_pnl):,.2f}"
                roe_str = f"+{roe:.2f}%" if roe >= 0 else f"{roe:.2f}%"
                funding_str = f"+${funding_total:.4f}" if funding_total >= 0 else f"-${abs(funding_total):.4f}"

                pos_lines.append(
                    f"- {symbol}: {direction} {abs_size:.3f} units @ ${entry_px:,.2f} avg\n"
                    f"  Current value: ${position_value:,.2f} | Unrealized P&L: {pnl_str} ({roe_str} ROE)\n"
                    f"  Leverage: {leverage:.0f}x (max {max_leverage:.0f}x) | Margin used: ${margin_used:,.2f} | Funding accrual: {funding_str} total"
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

    return {
        # Legacy variables (for Default prompt and backward compatibility)
        "account_state": account_state,
        "market_snapshot": market_snapshot,
        "session_context": session_context,
        "sampling_data": sampling_data,
        "decision_task": DECISION_TASK_TEXT,
        "output_format": output_format,
        "prices_json": json.dumps(prices, indent=2, sort_keys=True),
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


def build_chat_completion_endpoints(base_url: str, model: Optional[str] = None) -> List[str]:
    """Build a list of possible chat completion endpoints for an OpenAI-compatible API.

    Supports Deepseek-specific behavior where both `/chat/completions` and `/v1/chat/completions`
    might be valid, depending on how the base URL is configured.
    Returns:
        List of decision dictionaries (one per symbol action) or None if generation failed.
    """
    if not base_url:
        return []

    normalized = base_url.strip().rstrip('/')
    if not normalized:
        return []

    endpoints: List[str] = []
    base_lower = normalized.lower()
    endpoints.append(f"{normalized}/chat/completions")

    is_deepseek = "deepseek.com" in base_lower

    if is_deepseek:
        # Deepseek 官方同时支持 https://api.deepseek.com/chat/completions 和 /v1/chat/completions。
        if base_lower.endswith('/v1'):
            without_v1 = normalized[:-3]
            endpoints.append(f"{without_v1}/chat/completions")
        else:
            endpoints.append(f"{normalized}/v1/chat/completions")

    # Use dict to preserve order while removing duplicates
    deduped = list(dict.fromkeys(endpoints))
    return deduped


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
    """
    # Check if this is a default API key
    if _is_default_api_key(account.api_key):
        logger.info(f"Skipping AI trading for account {account.name} - using default API key")
        return None

    try:
        news_summary = fetch_latest_news()
        news_section = news_summary if news_summary else "No recent CoinJournal news available."
    except Exception as err:  # pragma: no cover - defensive logging
        logger.warning("Failed to fetch latest news: %s", err)
        news_section = "No recent CoinJournal news available."

    template = prompt_repo.get_prompt_for_account(db, account.id)
    if not template:
        try:
            template = prompt_repo.ensure_default_prompt(db)
        except ValueError as exc:
            logger.error("Prompt template resolution failed: %s", exc)
            return None

    # Build context with multi-symbol support
    active_symbol_metadata = symbol_metadata or SUPPORTED_SYMBOLS
    symbol_order = symbols if symbols else list(active_symbol_metadata.keys())

    if symbols:
        # New multi-symbol approach
        from services.sampling_pool import sampling_pool
        sampling_data = _build_multi_symbol_sampling_data(symbols, sampling_pool)
        context = _build_prompt_context(
            account,
            portfolio,
            prices,
            news_section,
            None,
            None,
            hyperliquid_state,
            symbol_metadata=active_symbol_metadata,
            symbol_order=symbol_order,
        )
        context["sampling_data"] = sampling_data
    else:
        # Legacy single-symbol approach (backward compatibility)
        context = _build_prompt_context(
            account,
            portfolio,
            prices,
            news_section,
            samples,
            target_symbol,
            hyperliquid_state,
            symbol_metadata=active_symbol_metadata,
            symbol_order=symbol_order,
        )

    try:
        prompt = template.template_text.format_map(SafeDict(context))
    except Exception as exc:  # pragma: no cover - fallback rendering
        logger.error("Failed to render prompt template '%s': %s", template.key, exc)
        prompt = template.template_text

    logger.debug("Using prompt template '%s' for account %s", template.key, account.id)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {account.api_key}",
    }

    # Use OpenAI-compatible chat completions format
    # Detect model type for appropriate parameter handling
    model_lower = (account.model or "").lower()

    # Reasoning models that don't support temperature parameter
    is_reasoning_model = any(
        marker in model_lower for marker in ["gpt-5", "o1-preview", "o1-mini", "o1-", "o3-", "o4-"]
    )

    # New models that use max_completion_tokens instead of max_tokens
    is_new_model = is_reasoning_model or any(marker in model_lower for marker in ["gpt-4o"])

    payload = {
        "model": account.model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }

    # Reasoning models (GPT-5, o1, o3, o4) don't support custom temperature
    # Only add temperature parameter for non-reasoning models
    if not is_reasoning_model:
        payload["temperature"] = 0.7

    # Use max_completion_tokens for newer models
    # Use max_tokens for older models (GPT-3.5, GPT-4, GPT-4-turbo, Deepseek)
    # Modern models have large context windows, allocate generous token budgets
    if is_new_model:
        # Reasoning models (GPT-5/o1) need more tokens for internal reasoning
        payload["max_completion_tokens"] = 5000
    else:
        # Regular models (GPT-4, Deepseek, Claude, etc.)
        payload["max_tokens"] = 5000

    # For GPT-5 family set reasoning_effort to balance latency and quality
    if "gpt-5" in model_lower:
        payload["reasoning_effort"] = "low"

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

        # Retry logic for rate limiting
        max_retries = 3
        response = None
        success = False
        for endpoint in endpoints:
            for attempt in range(max_retries):
                try:
                    response = requests.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                        timeout=30,
                        verify=False,  # Disable SSL verification for custom AI endpoints
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

        result = response.json()

        # Extract text from OpenAI-compatible response format
        if "choices" in result and len(result["choices"]) > 0:
            choice = result["choices"][0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "")
            reasoning_text = _extract_text_from_message(message.get("reasoning"))

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

                entry["_prompt_snapshot"] = prompt
                if isinstance(strategy_details, str) and strategy_details.strip():
                    entry["_reasoning_snapshot"] = strategy_details.strip()
                else:
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
        hyperliquid_environment = getattr(account, "hyperliquid_environment", None)

        # Create decision log entry
        decision_log = AIDecisionLog(
            account_id=account.id,
            reason=reason,
            operation=operation,
            symbol=symbol if operation != "hold" else None,
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
            asyncio.create_task(broadcast_model_chat_update({
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
            }))
        except Exception as broadcast_err:
            # Don't fail the save operation if broadcast fails
            logger.warning(f"Failed to broadcast AI decision update: {broadcast_err}")

    except Exception as err:
        logger.error(f"Failed to save AI decision log: {err}")
        db.rollback()


def get_active_ai_accounts(db: Session) -> List[Account]:
    """Get all active AI accounts that are not using default API key"""
    accounts = db.query(Account).filter(
        Account.is_active == "true",
        Account.account_type == "AI",
        Account.auto_trading_enabled == "true"
    ).all()
    
    if not accounts:
        return []
    
    # Filter out default accounts
    valid_accounts = [acc for acc in accounts if not _is_default_api_key(acc.api_key)]
    
    if not valid_accounts:
        logger.debug("No valid AI accounts found (all using default keys)")
        return []
        
    return valid_accounts
