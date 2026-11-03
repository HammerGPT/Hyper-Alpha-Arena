"""
AI Prompt Generation Service - Handles AI-powered trading prompt generation

Supports Function Calling for AI to query variables reference, validate prompts, and preview.
Aligned with ai_program_service.py architecture for consistency.
"""
import json
import logging
import os
import random
import re
import time
from typing import Dict, List, Optional, Any, Generator

import requests
from sqlalchemy.orm import Session

from database.models import Account, AiPromptConversation, AiPromptMessage
from services.ai_decision_service import (
    build_chat_completion_endpoints,
    detect_api_format,
    _extract_text_from_message,
    get_max_tokens,
    build_llm_payload,
    build_llm_headers,
    extract_reasoning,
    convert_tools_to_anthropic,
    convert_messages_to_anthropic,
    strip_thinking_tags,
)
from services.ai_stream_service import format_sse_event
from services.ai_shared_tools import (
    SHARED_SIGNAL_TOOLS,
    execute_get_signal_pools,
    execute_run_signal_backtest
)
from services.ai_prompt_shared_tools import (
    PROMPT_CONTEXT_TOOLS,
    execute_get_prompt_context,
    execute_get_trader_details,
    execute_get_decision_list,
    execute_get_decision_details,
    execute_query_market_data
)

logger = logging.getLogger(__name__)

# Retry configuration for API calls
API_MAX_RETRIES = 5
API_BASE_DELAY = 1.0  # seconds
API_MAX_DELAY = 16.0  # seconds
RETRYABLE_STATUS_CODES = {502, 503, 504, 429}


def _should_retry_api(status_code: Optional[int], error: Optional[str]) -> bool:
    """Check if API error is retryable."""
    if status_code and status_code in RETRYABLE_STATUS_CODES:
        return True
    if error and any(x in error.lower() for x in ['timeout', 'connection', 'reset', 'eof']):
        return True
    return False


def _get_retry_delay(attempt: int) -> float:
    """Calculate retry delay with exponential backoff and jitter."""
    delay = min(API_BASE_DELAY * (2 ** attempt), API_MAX_DELAY)
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter


# Path to system prompt file
SYSTEM_PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "prompt_generation_system_prompt.md"
)

# Path to variables reference file
VARIABLES_REFERENCE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "PROMPT_VARIABLES_REFERENCE.md"
)


def load_system_prompt() -> str:
    """Load the system prompt from markdown file"""
    try:
        with open(SYSTEM_PROMPT_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load system prompt: {e}")
        return "You are a trading strategy prompt generation assistant."


def load_variables_reference() -> str:
    """Load the variables reference document"""
    try:
        with open(VARIABLES_REFERENCE_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load variables reference: {e}")
        return "Variables reference not available."


def extract_prompt_from_response(content: str) -> Optional[str]:
    """Extract prompt content from AI response.

    Parsing priority:
    1. Exact ```prompt code block
    2. Fallback: Generic code block (``` without language)
    3. Fallback: Detect prompt structure markers (=== sections)

    Returns extracted prompt text or None.
    """
    # === Priority 1: Exact ```prompt code block ===
    pattern = r'```prompt\s*\n(.*?)\n```'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()

    # === Priority 2: Generic code block without language specifier ===
    # Match ``` followed by newline (not ```json, ```python, etc.)
    generic_pattern = r'```\s*\n(.*?)\n```'
    matches = re.findall(generic_pattern, content, re.DOTALL)
    for match_content in matches:
        # Check if it looks like a prompt (has section markers)
        if _looks_like_prompt(match_content):
            logger.info("Fallback: extracted prompt from generic code block")
            return match_content.strip()

    # === Priority 3: Detect prompt structure in plain text ===
    # Look for content with prompt section markers
    if _looks_like_prompt(content):
        # Try to extract the prompt portion
        # Find first section marker and last section content
        section_pattern = r'(===\s*[A-Z][A-Z\s]+===)'
        sections = re.findall(section_pattern, content)
        if len(sections) >= 2:
            # Find the span of prompt content
            first_section = re.search(section_pattern, content)
            if first_section:
                # Extract from first section to end, but trim trailing non-prompt text
                prompt_start = first_section.start()
                prompt_content = content[prompt_start:]
                # Trim common AI closing remarks
                closing_patterns = [
                    r'\n\n\*\*Explanation',
                    r'\n\nThis prompt',
                    r'\n\nI hope this',
                    r'\n\nLet me know',
                    r'\n\nFeel free',
                    r'\n\n---\n',
                ]
                for cp in closing_patterns:
                    closing_match = re.search(cp, prompt_content, re.IGNORECASE)
                    if closing_match:
                        prompt_content = prompt_content[:closing_match.start()]
                        break
                if prompt_content.strip():
                    logger.info("Fallback: extracted prompt from plain text with section markers")
                    return prompt_content.strip()

    return None


def _looks_like_prompt(text: str) -> bool:
    """Check if text looks like a trading prompt.

    Heuristics:
    - Has section markers (=== SECTION NAME ===)
    - Has variable placeholders ({variable_name})
    """
    # Must have at least one section marker
    has_section = bool(re.search(r'===\s*[A-Z][A-Z\s]+===', text))
    # Should have variable placeholders
    has_variables = bool(re.search(r'\{[a-zA-Z_]+\}', text))
    return has_section and has_variables


# ============================================================================
# Tool Definitions (OpenAI format)
# ============================================================================

PROMPT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_variables_reference",
            "description": "Get the complete list of available variables that can be used in trading prompts. Returns documentation for market data, K-line, technical indicators, flow indicators, position/account variables, etc.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "validate_variables",
            "description": "Validate that all variables used in a prompt text are valid and available. Returns list of valid and invalid variables found.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt_text": {
                        "type": "string",
                        "description": "The prompt text to validate for variable usage"
                    }
                },
                "required": ["prompt_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "preview_prompt",
            "description": "Preview the prompt with real market data to verify variables work correctly. Returns rendered text and variable status. Note: Account-related variables (equity, positions, trades, trigger_context) will show placeholder values since the prompt is not yet bound to an AI Trader. Market data and technical indicators will show real values.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt_text": {
                        "type": "string",
                        "description": "The prompt text to preview"
                    },
                    "asset": {
                        "type": "string",
                        "description": "Primary asset symbol for market data (default: BTC)",
                        "default": "BTC"
                    }
                },
                "required": ["prompt_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_apply_prompt",
            "description": "Suggest applying the generated prompt to a specific AI Trader. Call this when you have a complete, validated prompt ready for the user to apply.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt_text": {
                        "type": "string",
                        "description": "The complete prompt text to apply"
                    },
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of what this prompt does (1-2 sentences)"
                    }
                },
                "required": ["prompt_text", "summary"]
            }
        }
    },
    # Factor query tool (reused from hyper_ai_tools)
    {
        "type": "function",
        "function": {
            "name": "query_factors",
            "description": "Query factor library and effectiveness data. Without symbol: returns factor list with names (for use in prompt variables like {SYMBOL_factor_PERIOD_NAME}). With symbol: returns factor values and effectiveness ranking. Response includes IC, ICIR, win_rate, decay_half_life_hours.",
            "parameters": {
                "type": "object",
                "properties": {
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange (required)"},
                    "symbol": {"type": "string", "description": "Trading symbol (e.g., BTC). If omitted, returns factor library list."},
                    "factor_name": {"type": "string", "description": "Specific factor name for detailed info"},
                    "forward_period": {"type": "string", "enum": ["1h", "4h", "12h", "24h"], "description": "Forward period for effectiveness (default: 4h)"}
                },
                "required": ["exchange"]
            }
        }
    },
] + PROMPT_CONTEXT_TOOLS + SHARED_SIGNAL_TOOLS  # Add context tools and shared signal pool tools


# Pre-convert tools for Anthropic format
PROMPT_TOOLS_ANTHROPIC = convert_tools_to_anthropic(PROMPT_TOOLS)


# ============================================================================
# Valid Variables List (for validation)
# ============================================================================

# Base variable patterns that are always valid
VALID_VARIABLE_PATTERNS = [
    # Account/Position variables
    r"total_equity", r"available_balance", r"margin_usage_percent", r"maintenance_margin",
    r"positions_detail", r"recent_trades_summary", r"open_orders_detail",
    # Context variables
    r"runtime_minutes", r"current_time_utc", r"trading_environment", r"selected_symbols_detail",
    r"trigger_context", r"news_section", r"output_format",
    r"adanos_sentiment(?:_\d+d)?",
    # Market regime
    r"market_regime_description", r"trigger_market_regime",
    r"market_regime(?:_(?:1m|5m|15m|1h|4h|1d))?",
    # Symbol-specific patterns (BTC, ETH, SOL, etc.)
    r"[A-Z]+_market_data",
    r"[A-Z][A-Z0-9]*_adanos_sentiment(?:_\d+d)?",
    r"[A-Z]+_klines_(?:1m|3m|5m|15m|30m|1h|2h|4h|8h|12h|1d|3d|1w|1M)",
    r"[A-Z]+_market_regime(?:_(?:1m|5m|15m|1h|4h|1d))?",
    # Technical indicators
    r"[A-Z]+_(?:MA|EMA|RSI14|RSI7|MACD|BOLL|ATR14|VWAP|OBV|STOCH)_(?:1m|3m|5m|15m|30m|1h|2h|4h|8h|12h|1d)",
    # Flow indicators
    r"[A-Z]+_(?:CVD|OI|OI_DELTA|TAKER|FUNDING|DEPTH|IMBALANCE|PRICE_CHANGE|VOLATILITY)_(?:1m|3m|5m|15m|30m|1h|2h|4h|8h|12h|1d)",
    # Factor variables: preferred {SYMBOL_factor_PERIOD_NAME}, legacy {SYMBOL_factor_NAME}
    r"[A-Z][A-Z0-9]*_factor_(?:1m|5m|15m|1h|4h|1d)_[A-Za-z][A-Za-z0-9_]*",
    r"[A-Z][A-Z0-9]*_factor_[A-Za-z][A-Za-z0-9_]*",
]


def _validate_variable(var_name: str) -> bool:
    """Check if a variable name matches any valid pattern."""
    for pattern in VALID_VARIABLE_PATTERNS:
        if re.fullmatch(pattern, var_name):
            return True
    return False


def _extract_variables_from_text(text: str) -> List[str]:
    """Extract all {variable} placeholders from text."""
    # Match {variable_name} but not {{escaped}}
    pattern = r'\{([^{}]+)\}'
    matches = re.findall(pattern, text)
    # Filter out things that look like JSON or format strings
    variables = []
    for m in matches:
        # Skip if it looks like JSON key or has special chars
        if ':' in m or '"' in m or "'" in m:
            continue
        # Skip if it's a number (like array index)
        if m.isdigit():
            continue
        # Handle klines with count: {BTC_klines_1h}(100) -> BTC_klines_1h
        clean_var = m.split('}')[0].split('(')[0].strip()
        if clean_var:
            variables.append(clean_var)
    return list(set(variables))


# Account-related variables that need AI Trader binding (will show placeholders)
ACCOUNT_VARIABLES = {
    "total_equity", "available_balance", "margin_usage_percent", "maintenance_margin",
    "positions_detail", "recent_trades_summary", "open_orders_detail",
    "runtime_minutes", "trading_environment", "trigger_context", "trigger_market_regime",
}


def _execute_preview_prompt(args: Dict[str, Any], request_id: str) -> str:
    """Execute preview_prompt tool - render prompt with real market data."""
    from services.ai_decision_service import _build_prompt_context, SafeDict
    from services.market_data import get_ticker_data
    from datetime import datetime, timezone

    prompt_text = args.get("prompt_text", "")
    asset = args.get("asset", "BTC").upper()

    # Extract variables from prompt
    variables = _extract_variables_from_text(prompt_text)

    resolved_vars = []
    placeholder_vars = []
    failed_vars = []

    # Build minimal context for preview (no account data)
    context = {}

    # System variables
    context["current_time_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    context["output_format"] = '{"action": "hold|buy|sell|close", "symbol": "BTC", ...}'
    context["selected_symbols_detail"] = f"Primary: {asset}"
    context["news_section"] = "[News preview not available in prompt generation mode]"
    context["market_regime_description"] = "[Market regime definitions - available at runtime]"

    # Account placeholders
    context["total_equity"] = "[PLACEHOLDER: Will show actual equity when bound to AI Trader]"
    context["available_balance"] = "[PLACEHOLDER: Will show actual balance when bound to AI Trader]"
    context["margin_usage_percent"] = "[PLACEHOLDER: Will show actual margin usage when bound to AI Trader]"
    context["maintenance_margin"] = "[PLACEHOLDER: Will show actual maintenance margin when bound to AI Trader]"
    context["positions_detail"] = "[PLACEHOLDER: Will show actual positions when bound to AI Trader]"
    context["recent_trades_summary"] = "[PLACEHOLDER: Will show actual trades when bound to AI Trader]"
    context["open_orders_detail"] = "[PLACEHOLDER: Will show actual orders when bound to AI Trader]"
    context["runtime_minutes"] = "[PLACEHOLDER: Will show actual runtime when AI Trader is running]"
    context["trading_environment"] = "[PLACEHOLDER: testnet or mainnet when bound to AI Trader]"
    context["trigger_context"] = "[PLACEHOLDER: Will show signal/scheduled trigger info at runtime]"
    context["trigger_market_regime"] = "[PLACEHOLDER: Will show regime snapshot at trigger time]"

    # Try to get real market data
    try:
        from services.hyperliquid_symbol_service import get_available_symbol_map
        from services.sampling_pool import sampling_pool

        symbol_map = get_available_symbol_map()
        symbols_to_fetch = [asset]

        # Check if other symbols are referenced
        for var in variables:
            match = re.match(r'^([A-Z]+)_', var)
            if match:
                sym = match.group(1)
                if sym not in symbols_to_fetch and sym in symbol_map:
                    symbols_to_fetch.append(sym)

        realtime_tickers = {}

        # Fetch market data for each symbol
        for sym in symbols_to_fetch[:5]:  # Limit to 5 symbols
            try:
                ticker = get_ticker_data(sym, "CRYPTO", environment="mainnet")
                realtime_tickers[sym] = ticker
                price = float(ticker.get("price", 0) or 0)
                context[f"{sym}_market_data"] = f"Symbol: {sym}, Price: ${price:,.2f}"

                # Get sampling data if available
                sample = sampling_pool.get(sym)
                if sample:
                    context[f"{sym}_market_data"] = (
                        f"Symbol: {sym}\n"
                        f"Price: ${sample.get('price', price):,.2f}\n"
                        f"24h Change: {sample.get('change_24h', 'N/A')}%\n"
                        f"Volume: ${sample.get('volume_24h', 'N/A'):,.0f}" if isinstance(sample.get('volume_24h'), (int, float)) else f"Volume: {sample.get('volume_24h', 'N/A')}"
                    )
            except Exception as e:
                logger.warning(f"[Preview {request_id}] Failed to get price for {sym}: {e}")
                context[f"{sym}_market_data"] = f"[Failed to fetch {sym} market data: {e}]"
    except Exception as e:
        logger.warning(f"[Preview {request_id}] Market data fetch error: {e}")

    # Build context with indicators using _build_prompt_context
    try:
        # Create minimal account-like object for context building
        class MinimalAccount:
            id = 0
            name = "Preview"

        minimal_portfolio = {'cash': 0, 'positions': {}, 'total_assets': 0}
        prices = {
            sym: float(ticker.get("price", 0) or 0)
            for sym, ticker in locals().get("realtime_tickers", {}).items()
            if float(ticker.get("price", 0) or 0) > 0
        }

        full_context = _build_prompt_context(
            MinimalAccount(),
            minimal_portfolio,
            prices,
            context.get("news_section", ""),
            None, None, None,
            db=None,
            symbol_metadata={asset: {"name": asset}},
            symbol_order=[asset],
            environment="mainnet",
            template_text=prompt_text,
        )
        # Merge indicator data into context
        for key, value in full_context.items():
            if key not in context or context[key].startswith("[PLACEHOLDER"):
                context[key] = value
    except Exception as e:
        logger.warning(f"[Preview {request_id}] Context building error: {e}")

    # Render the prompt
    try:
        rendered = prompt_text.format_map(SafeDict(context))
    except Exception as e:
        rendered = f"[Render error: {e}]"

    # Categorize variables
    for var in variables:
        if var in ACCOUNT_VARIABLES:
            placeholder_vars.append(var)
        elif f"{{{var}}}" in rendered or f"[PLACEHOLDER" in context.get(var, "") or "N/A" in str(context.get(var, "")):
            # Check if variable was not resolved
            if var not in context or context.get(var, "").startswith("["):
                failed_vars.append(var)
            else:
                placeholder_vars.append(var)
        else:
            resolved_vars.append(var)

    # Build result
    result = {
        "success": True,
        "rendered_preview": rendered[:2000] + ("..." if len(rendered) > 2000 else ""),
        "preview_length": len(rendered),
        "variables_status": {
            "total": len(variables),
            "resolved": len(resolved_vars),
            "placeholder": len(placeholder_vars),
            "failed": len(failed_vars),
            "resolved_list": sorted(resolved_vars)[:20],
            "placeholder_list": sorted(placeholder_vars),
            "failed_list": sorted(failed_vars),
        },
        "note": "Account-related variables show placeholders. Apply to AI Trader for full preview with real account data."
    }

    if failed_vars:
        result["warning"] = f"Found {len(failed_vars)} variable(s) that could not be resolved: {', '.join(failed_vars)}"

    return json.dumps(result, indent=2, ensure_ascii=False)


# ============================================================================
# Tool Execution Functions
# ============================================================================

def execute_tool(tool_name: str, args: Dict[str, Any], request_id: str, db: Session = None, prompt_id: int = None) -> str:
    """Execute a tool and return the result as a string."""
    logger.info(f"[AI Prompt Gen {request_id}] Executing tool: {tool_name}")

    try:
        if tool_name == "get_variables_reference":
            return load_variables_reference()

        elif tool_name == "validate_variables":
            prompt_text = args.get("prompt_text", "")
            variables = _extract_variables_from_text(prompt_text)

            valid_vars = []
            invalid_vars = []
            for var in variables:
                if _validate_variable(var):
                    valid_vars.append(var)
                else:
                    invalid_vars.append(var)

            result = {
                "total_found": len(variables),
                "valid_count": len(valid_vars),
                "invalid_count": len(invalid_vars),
                "valid_variables": sorted(valid_vars),
                "invalid_variables": sorted(invalid_vars),
            }
            if invalid_vars:
                result["warning"] = f"Found {len(invalid_vars)} invalid variable(s). Please check spelling or refer to variables reference."
            else:
                result["status"] = "All variables are valid."
            return json.dumps(result, indent=2)

        elif tool_name == "preview_prompt":
            return _execute_preview_prompt(args, request_id)

        elif tool_name == "suggest_apply_prompt":
            prompt_text = args.get("prompt_text", "")
            summary = args.get("summary", "")
            # This is a special tool - return structured data for frontend
            return json.dumps({
                "action": "suggest_apply",
                "prompt_text": prompt_text,
                "summary": summary,
                "message": "Prompt is ready to apply. User can click 'Apply' to use this prompt."
            })

        elif tool_name == "get_signal_pools":
            if db is None:
                return json.dumps({"error": "Database session not available"})
            exchange = args.get("exchange", "all")
            return execute_get_signal_pools(db, exchange)

        elif tool_name == "run_signal_backtest":
            if db is None:
                return json.dumps({"error": "Database session not available"})
            pool_id = args.get("pool_id")
            if pool_id is None:
                return json.dumps({"error": "pool_id is required"})
            symbol = args.get("symbol", "BTC")
            hours = args.get("hours", 24)
            return execute_run_signal_backtest(db, pool_id, symbol, hours)

        # New prompt context tools
        elif tool_name == "get_prompt_context":
            if db is None:
                return json.dumps({"error": "Database session not available"})
            # Use passed prompt_id if args doesn't specify one
            pid = args.get("prompt_id") or prompt_id
            return execute_get_prompt_context(db, pid)

        elif tool_name == "get_trader_details":
            if db is None:
                return json.dumps({"error": "Database session not available"})
            trader_id = args.get("trader_id")
            if trader_id is None:
                return json.dumps({"error": "trader_id is required"})
            return execute_get_trader_details(db, trader_id)

        elif tool_name == "get_decision_list":
            if db is None:
                return json.dumps({"error": "Database session not available"})
            trader_id = args.get("trader_id")
            if trader_id is None:
                return json.dumps({"error": "trader_id is required"})
            limit = args.get("limit", 10)
            return execute_get_decision_list(db, trader_id, limit)

        elif tool_name == "get_decision_details":
            if db is None:
                return json.dumps({"error": "Database session not available"})
            decision_ids = args.get("decision_ids")
            if not decision_ids:
                return json.dumps({"error": "decision_ids is required"})
            fields = args.get("fields")
            return execute_get_decision_details(db, decision_ids, fields)

        elif tool_name == "query_market_data":
            if db is None:
                return json.dumps({"error": "Database session not available"})
            symbol = args.get("symbol")
            if not symbol:
                return json.dumps({"error": "symbol is required"})
            period = args.get("period", "1h")
            exchange = args.get("exchange", "hyperliquid")
            return execute_query_market_data(db, symbol, period, exchange)

        elif tool_name == "query_factors":
            if db is None:
                return json.dumps({"error": "Database session not available"})
            from services.hyper_ai_tools import execute_query_factors
            exchange = args.get("exchange", "hyperliquid")
            symbol = args.get("symbol")
            factor_name = args.get("factor_name")
            forward_period = args.get("forward_period", "4h")
            return execute_query_factors(db, exchange, symbol, factor_name, forward_period)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        logger.error(f"[AI Prompt Gen {request_id}] Tool execution error: {e}")
        return json.dumps({"error": str(e)})


# ============================================================================
# Main SSE Generation Function
# ============================================================================

def generate_prompt_with_ai_stream(
    db: Session,
    account: Optional[Account] = None,
    user_message: str = "",
    conversation_id: Optional[int] = None,
    user_id: int = 1,
    prompt_id: Optional[int] = None,
    llm_config: Optional[Dict[str, Any]] = None,
) -> Generator[str, None, None]:
    """
    Generate trading strategy prompt using AI with SSE streaming.

    Yields SSE events:
    - tool_round: {type: "tool_round", round: N, max: M}
    - tool_call: {type: "tool_call", name: "...", args: {...}}
    - tool_result: {type: "tool_result", name: "...", result: "..."}
    - content: {type: "content", content: "..."}
    - suggest_apply: {type: "suggest_apply", prompt_text: "...", summary: "..."}
    - done: {type: "done", conversation_id: N, message_id: N, prompt_result: "..."}
    - error: {type: "error", content: "..."}
    - retry: {type: "retry", attempt: N, max_retries: M}
    """
    start_time = time.time()
    request_id = f"prompt_gen_{int(start_time)}"

    # Get LLM config: either from llm_config param or from account object
    if llm_config:
        # Use provided llm_config (e.g., from Hyper AI sub-agent call)
        api_config = {
            "base_url": llm_config.get("base_url"),
            "api_key": llm_config.get("api_key"),
            "model": llm_config.get("model"),
            "api_format": llm_config.get("api_format", "openai")
        }
        account_name = "Hyper AI"
    elif account:
        # Original logic: use account object
        api_config = {
            "base_url": account.base_url,
            "api_key": account.api_key,
            "model": account.model,
            "api_format": detect_api_format(account.base_url)[1] or "openai"
        }
        account_name = account.name
    else:
        yield format_sse_event("error", {"content": "No LLM configuration provided"})
        return

    logger.info(f"[AI Prompt Gen {request_id}] Starting: account={account_name}, "
                f"conversation_id={conversation_id}, user_message_length={len(user_message)}")

    try:
        # Load system prompt
        system_prompt = load_system_prompt()

        # Inject current context if prompt_id is provided
        if prompt_id:
            context_info = execute_get_prompt_context(db, prompt_id)
            try:
                context_data = json.loads(context_info)
                if context_data.get("success"):
                    context_section = "\n\n## CURRENT CONTEXT\n"
                    context_section += f"You are editing prompt ID: {prompt_id}\n"
                    if context_data.get("prompt"):
                        p = context_data["prompt"]
                        context_section += f"- Prompt Name: {p.get('name', 'Unnamed')}\n"
                        if p.get("content"):
                            # Truncate if too long
                            content = p["content"]
                            if len(content) > 500:
                                content = content[:500] + "..."
                            context_section += f"- Current Content:\n```\n{content}\n```\n"
                    if context_data.get("bound_traders"):
                        traders = context_data["bound_traders"]
                        context_section += f"\nThis prompt is bound to {len(traders)} AI Trader(s):\n"
                        for t in traders[:5]:  # Limit to 5
                            context_section += f"- {t.get('name')} (ID: {t.get('id')}, Exchange: {t.get('exchange')})\n"
                    else:
                        context_section += "\nThis prompt is not bound to any AI Trader yet.\n"
                    system_prompt += context_section
            except Exception as e:
                logger.warning(f"[AI Prompt Gen {request_id}] Failed to inject context: {e}")

        # Get or create conversation
        conversation = None
        if conversation_id:
            conversation = db.query(AiPromptConversation).filter(
                AiPromptConversation.id == conversation_id,
                AiPromptConversation.user_id == user_id
            ).first()

        if not conversation:
            title = user_message[:50] + "..." if len(user_message) > 50 else user_message
            conversation = AiPromptConversation(
                user_id=user_id,
                prompt_id=prompt_id,
                title=title
            )
            db.add(conversation)
            db.flush()
            logger.info(f"[AI Prompt Gen {request_id}] Created conversation: id={conversation.id}, prompt_id={prompt_id}")

        # Save user message
        user_msg = AiPromptMessage(
            conversation_id=conversation.id,
            role="user",
            content=user_message
        )
        db.add(user_msg)
        db.flush()

        # Build message history with compression support
        from services.ai_context_compression_service import (
            compress_messages, update_compression_points,
            restore_tool_calls_to_messages,
            get_last_compression_point, filter_messages_by_compression,
        )

        messages = [{"role": "system", "content": system_prompt}]

        # Check compression points - inject summary for compressed messages
        cp = get_last_compression_point(conversation)
        if cp and cp.get("summary"):
            messages.append({
                "role": "system",
                "content": f"[Previous conversation summary]\n{cp['summary']}"
            })

        # Load history, filter by compression point
        history = db.query(AiPromptMessage).filter(
            AiPromptMessage.conversation_id == conversation.id,
            AiPromptMessage.id != user_msg.id
        ).order_by(AiPromptMessage.created_at).limit(100).all()

        history = filter_messages_by_compression(history, cp)

        last_message_id = history[-1].id if history else None

        # Restore tool_calls into proper LLM message format
        history_dicts = [
            {
                "role": m.role,
                "content": m.content,
                "tool_calls_log": m.tool_calls_log,
                "reasoning_snapshot": m.reasoning_snapshot,
            }
            for m in history
        ]
        restored = restore_tool_calls_to_messages(history_dicts, api_config.get("api_format", "openai"), model=api_config.get("model", ""))
        messages.extend(restored)

        messages.append({"role": "user", "content": user_message})

        # Apply compression if needed (api_config already set above)
        result = compress_messages(messages, api_config, db=db)
        messages = result["messages"]

        # Update compression_points if compression occurred
        if result["compressed"] and result["summary"] and last_message_id:
            update_compression_points(
                conversation, last_message_id,
                result["summary"], result["compressed_at"], db
            )

        # Detect API format and build endpoints
        endpoint, api_format = detect_api_format(api_config["base_url"])
        if not endpoint:
            yield format_sse_event("error", {"content": "Invalid API configuration"})
            return

        if api_format == 'anthropic':
            endpoints = [endpoint]
        else:
            endpoints = build_chat_completion_endpoints(api_config["base_url"], api_config["model"])
            if not endpoints:
                yield format_sse_event("error", {"content": "Invalid API configuration"})
                return
        # Use unified headers builder (see build_llm_headers in ai_decision_service)
        headers = build_llm_headers(api_format, api_config["api_key"], api_config["base_url"])

        # Tool calling loop
        max_rounds = 10
        tool_round = 0
        tool_calls_log = []
        final_content = ""
        reasoning_snapshot = ""
        prompt_result = None
        suggest_apply_data = None

        # Create assistant message upfront with is_complete=False
        assistant_msg = AiPromptMessage(
            conversation_id=conversation.id,
            role="assistant",
            content="",
            is_complete=False
        )
        db.add(assistant_msg)
        db.flush()

        while tool_round < max_rounds:
            tool_round += 1
            is_last = tool_round == max_rounds

            yield format_sse_event("tool_round", {"round": tool_round, "max": max_rounds})

            # Use unified payload builder (see build_llm_payload in ai_decision_service)
            if api_format == 'anthropic':
                sys_prompt, anthropic_messages = convert_messages_to_anthropic(messages)
                tools_for_round = PROMPT_TOOLS_ANTHROPIC if not is_last else None
                payload = build_llm_payload(
                    model=api_config["model"],
                    messages=[{"role": "system", "content": sys_prompt}] + anthropic_messages,
                    api_format=api_format,
                    tools=tools_for_round,
                )
            else:
                tools_for_round = PROMPT_TOOLS if not is_last else None
                payload = build_llm_payload(
                    model=api_config["model"],
                    messages=messages,
                    api_format=api_format,
                    tools=tools_for_round,
                    tool_choice="auto" if not is_last else None,
                )

            # API call with retry logic
            response = None
            last_error = None
            last_status_code = None
            last_response_text = None  # Store full response text for error logging

            for retry_attempt in range(API_MAX_RETRIES):
                response = None
                # Don't reset last_error - preserve error from previous attempts

                for ep in endpoints:
                    try:
                        logger.info(f"[AI Prompt Gen {request_id}] Round {tool_round}, trying: {ep}")
                        response = requests.post(ep, json=payload, headers=headers, timeout=120)
                        last_status_code = response.status_code
                        last_response_text = response.text[:2000] if response.text else None

                        if response.status_code == 200:
                            break
                        else:
                            last_error = f"HTTP {response.status_code}"
                            logger.warning(f"[AI Prompt Gen {request_id}] Endpoint failed: {response.status_code} - {response.text[:500]}")

                    except requests.exceptions.Timeout as e:
                        last_error = f"Timeout after 120s: {str(e)}"
                        logger.warning(f"[AI Prompt Gen {request_id}] Timeout on {ep}: {e}")
                    except requests.exceptions.ConnectionError as e:
                        last_error = f"Connection error: {str(e)}"
                        logger.warning(f"[AI Prompt Gen {request_id}] Connection error on {ep}: {e}")
                    except Exception as e:
                        last_error = f"{type(e).__name__}: {str(e)}"
                        logger.warning(f"[AI Prompt Gen {request_id}] Error: {type(e).__name__}: {e}")

                if response and response.status_code == 200:
                    break

                if not _should_retry_api(last_status_code, last_error):
                    break

                if retry_attempt < API_MAX_RETRIES - 1:
                    delay = _get_retry_delay(retry_attempt)
                    logger.warning(f"[AI Prompt Gen {request_id}] Retrying in {delay:.1f}s")
                    yield format_sse_event("retry", {"attempt": retry_attempt + 2, "max_retries": API_MAX_RETRIES})
                    time.sleep(delay)

            if not response or response.status_code != 200:
                error_parts = []
                if last_error:
                    error_parts.append(f"error={last_error}")
                if last_status_code:
                    error_parts.append(f"status={last_status_code}")
                if last_response_text:
                    error_parts.append(f"response={last_response_text[:500]}")
                error_detail = "; ".join(error_parts) if error_parts else "No response from API"
                logger.error(f"[AI Prompt Gen {request_id}] API failed at round {tool_round}: {error_detail}")

                if tool_calls_log:
                    assistant_msg.content = final_content
                    assistant_msg.tool_calls_log = json.dumps(tool_calls_log)
                    assistant_msg.is_complete = False
                    assistant_msg.interrupt_reason = f"Round {tool_round}: {error_detail}"
                    db.commit()
                    yield format_sse_event("interrupted", {"message_id": assistant_msg.id, "error": error_detail})
                else:
                    db.delete(assistant_msg)
                    db.commit()
                    yield format_sse_event("error", {"content": f"API request failed: {error_detail}"})
                return

            resp_json = response.json()

            # Parse response based on API format
            if api_format == 'anthropic':
                content_blocks = resp_json.get("content", [])
                tool_uses = []
                content = ""
                reasoning_content = ""

                for block in content_blocks:
                    if block.get("type") == "text":
                        content += block.get("text", "")
                    elif block.get("type") == "tool_use":
                        tool_uses.append(block)
                    elif block.get("type") == "thinking":
                        t = block.get("thinking", "")
                        if t:
                            reasoning_content += t

                if reasoning_content:
                    reasoning_snapshot += f"\n[Round {tool_round}]\n{reasoning_content}"
                    yield format_sse_event("reasoning", {"content": reasoning_content[:500]})

                # Strip <thinking> text tags from content
                content, tag_thinking = strip_thinking_tags(content)
                if tag_thinking and not reasoning_content:
                    reasoning_content = tag_thinking
                    reasoning_snapshot += f"\n[Round {tool_round}]\n{tag_thinking}"

                if tool_uses:
                    # Process tool calls
                    messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_use_blocks": content_blocks
                    })

                    for tool_use in tool_uses:
                        tool_name = tool_use.get("name", "")
                        tool_id = tool_use.get("id", "")
                        tool_args = tool_use.get("input", {})

                        yield format_sse_event("tool_call", {"name": tool_name, "args": tool_args})

                        result = execute_tool(tool_name, tool_args, request_id, db, prompt_id)
                        tool_calls_log.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result": result[:500] if len(result) > 500 else result
                        })

                        # Check for suggest_apply
                        if tool_name == "suggest_apply_prompt":
                            try:
                                suggest_apply_data = json.loads(result)
                                yield format_sse_event("suggest_apply", {"prompt_text": suggest_apply_data.get("prompt_text", ""), "summary": suggest_apply_data.get("summary", "")})
                            except:
                                pass

                        yield format_sse_event("tool_result", {"name": tool_name, "result": result[:200] + "..." if len(result) > 200 else result})

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": result
                        })

                    continue  # Next round

                # No tool calls - final response
                final_content = content
                break

            else:
                # OpenAI format
                choice = resp_json.get("choices", [{}])[0]
                message = choice.get("message", {})
                content = _extract_text_from_message(message.get("content", ""))
                tool_calls = message.get("tool_calls", [])
                # DeepSeek Reasoner returns reasoning_content which MUST be included in next request
                # Unified fallback: also handles Qwen thinking field via extract_reasoning()
                reasoning_content = message.get("reasoning_content", "") or extract_reasoning(message)

                # Strip <thinking> text tags from content
                content, tag_thinking = strip_thinking_tags(content)
                if tag_thinking and not reasoning_content:
                    reasoning_content = tag_thinking

                if tool_calls:
                    # Process tool calls - MUST include reasoning_content for DeepSeek Reasoner
                    assistant_msg_dict = {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls
                    }
                    if reasoning_content:
                        assistant_msg_dict["reasoning_content"] = reasoning_content
                        reasoning_snapshot += f"\n[Round {tool_round}]\n{reasoning_content}"
                        # Stream reasoning to frontend
                        yield format_sse_event("reasoning", {"content": reasoning_content[:500]})
                    messages.append(assistant_msg_dict)

                    for tc in tool_calls:
                        func = tc.get("function", {})
                        tool_name = func.get("name", "")
                        tool_id = tc.get("id", "")
                        try:
                            tool_args = json.loads(func.get("arguments", "{}"))
                        except:
                            tool_args = {}

                        yield format_sse_event("tool_call", {"name": tool_name, "args": tool_args})

                        result = execute_tool(tool_name, tool_args, request_id, db, prompt_id)
                        tool_calls_log.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result": result[:500] if len(result) > 500 else result
                        })

                        # Check for suggest_apply
                        if tool_name == "suggest_apply_prompt":
                            try:
                                suggest_apply_data = json.loads(result)
                                yield format_sse_event("suggest_apply", {"prompt_text": suggest_apply_data.get("prompt_text", ""), "summary": suggest_apply_data.get("summary", "")})
                            except:
                                pass

                        yield format_sse_event("tool_result", {"name": tool_name, "result": result[:200] + "..." if len(result) > 200 else result})

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": result
                        })

                    continue  # Next round

                # No tool calls - final response
                final_content = content
                break

        # Extract prompt from final content
        prompt_result = extract_prompt_from_response(final_content)

        # Update and save assistant message
        assistant_msg.content = final_content
        assistant_msg.prompt_result = prompt_result
        assistant_msg.tool_calls_log = json.dumps(tool_calls_log) if tool_calls_log else None
        assistant_msg.reasoning_snapshot = reasoning_snapshot if reasoning_snapshot else None
        assistant_msg.is_complete = True
        db.commit()

        # Send final content and done event
        yield format_sse_event("content", {"content": final_content})
        done_data = {
            "conversation_id": conversation.id,
            "message_id": assistant_msg.id,
            "prompt_result": prompt_result,
            "tool_calls_log": tool_calls_log if tool_calls_log else None,
            "reasoning_snapshot": reasoning_snapshot if reasoning_snapshot else None,
            "compression_points": json.loads(conversation.compression_points) if conversation.compression_points else None,
        }
        yield format_sse_event("done", done_data)

        total_elapsed = time.time() - start_time
        logger.info(f"[AI Prompt Gen {request_id}] Completed in {total_elapsed:.2f}s")

    except Exception as e:
        logger.error(f"[AI Prompt Gen {request_id}] Unexpected error: {e}", exc_info=True)
        db.rollback()
        yield format_sse_event("error", {"content": f"Internal error: {type(e).__name__}"})


# ============================================================================
# Legacy Synchronous Function (for backward compatibility)
# ============================================================================

def generate_prompt_with_ai(
    db: Session,
    account: Account,
    user_message: str,
    conversation_id: Optional[int] = None,
    user_id: int = 1,
    prompt_id: Optional[int] = None,
) -> Dict:
    """
    Legacy synchronous version - wraps the streaming version.
    Kept for backward compatibility with existing code.
    """
    result = {
        "success": False,
        "error": "Unknown error"
    }

    try:
        for event in generate_prompt_with_ai_stream(db, account, user_message, conversation_id, user_id, prompt_id):
            if event.startswith("data: "):
                data = json.loads(event[6:].strip())
                event_type = data.get("type")

                if event_type == "done":
                    result = {
                        "success": True,
                        "conversation_id": data.get("conversation_id"),
                        "message_id": data.get("message_id"),
                        "content": "",  # Will be set from content event
                        "prompt_result": data.get("prompt_result"),
                    }
                elif event_type == "content":
                    result["content"] = data.get("content", "")
                elif event_type == "error":
                    result = {
                        "success": False,
                        "error": data.get("content", "Unknown error")
                    }
    except Exception as e:
        result = {
            "success": False,
            "error": str(e)
        }

    return result


# ============================================================================
# Conversation History Functions
# ============================================================================

def get_conversation_history(
    db: Session,
    user_id: int,
    limit: int = 20
) -> List[Dict]:
    """Get user's conversation history."""
    conversations = db.query(AiPromptConversation).filter(
        AiPromptConversation.user_id == user_id
    ).order_by(
        AiPromptConversation.updated_at.desc()
    ).limit(limit).all()

    result = []
    for conv in conversations:
        msg_count = db.query(AiPromptMessage).filter(
            AiPromptMessage.conversation_id == conv.id
        ).count()

        result.append({
            "id": conv.id,
            "title": conv.title,
            "promptId": conv.prompt_id,
            "messageCount": msg_count,
            "createdAt": conv.created_at.isoformat() if conv.created_at else None,
            "updatedAt": conv.updated_at.isoformat() if conv.updated_at else None,
        })

    return result


def get_conversation_messages(
    db: Session,
    conversation_id: int,
    user_id: int
) -> Optional[List[Dict]]:
    """Get all messages in a conversation."""
    conversation = db.query(AiPromptConversation).filter(
        AiPromptConversation.id == conversation_id,
        AiPromptConversation.user_id == user_id
    ).first()

    if not conversation:
        return None

    messages = db.query(AiPromptMessage).filter(
        AiPromptMessage.conversation_id == conversation_id
    ).order_by(AiPromptMessage.created_at).all()

    result = []
    for msg in messages:
        msg_data = {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "promptResult": msg.prompt_result,
            "createdAt": msg.created_at.isoformat() if msg.created_at else None,
            "is_complete": msg.is_complete if msg.is_complete is not None else True,
        }
        # Include tool_calls_log if present
        if msg.tool_calls_log:
            try:
                msg_data["tool_calls_log"] = json.loads(msg.tool_calls_log)
            except:
                pass
        # Include reasoning_snapshot if present
        if msg.reasoning_snapshot:
            msg_data["reasoning_snapshot"] = msg.reasoning_snapshot
        result.append(msg_data)

    return result
