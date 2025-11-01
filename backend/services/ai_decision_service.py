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
    """Build sampling pool data section for Alpha Arena style prompts"""
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


def _build_market_snapshot(prices: Dict[str, float], positions: Dict[str, Dict[str, Any]]) -> str:
    lines: List[str] = []
    for symbol in SUPPORTED_SYMBOLS.keys():
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


OUTPUT_FORMAT_JSON = (
    '{\n'
    '  "operation": "buy" | "sell" | "hold" | "close",\n'
    '  "symbol": "<BTC|ETH|SOL|BNB|XRP|DOGE>",\n'
    '  "target_portion_of_balance": <float 0.0-1.0>,\n'
    '  "reason": "<150 characters maximum>",\n'
    '  "trading_strategy": "<2-3 sentences covering signals, risk, execution>"\n'
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
) -> Dict[str, Any]:
    positions = portfolio.get("positions", {})
    account_state = _build_account_state(portfolio)
    market_snapshot = _build_market_snapshot(prices, positions)
    session_context = _build_session_context(account)
    sampling_data = _build_sampling_data(samples, target_symbol)

    return {
        "account_state": account_state,
        "market_snapshot": market_snapshot,
        "session_context": session_context,
        "sampling_data": sampling_data,
        "decision_task": DECISION_TASK_TEXT,
        "output_format": OUTPUT_FORMAT_JSON,
        "prices_json": json.dumps(prices, indent=2, sort_keys=True),
        "portfolio_json": json.dumps(portfolio, indent=2, sort_keys=True),
        "portfolio_positions_json": json.dumps(positions, indent=2, sort_keys=True),
        "news_section": news_section,
        "account_name": account.name,
        "model_name": account.model or "",
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
) -> Optional[Dict]:
    """Call AI model API to get trading decision"""
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

    context = _build_prompt_context(account, portfolio, prices, news_section, samples, target_symbol)

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
        payload["max_completion_tokens"] = 3000
    else:
        # Regular models (GPT-4, Deepseek, Claude, etc.)
        payload["max_tokens"] = 3000

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
                    operation_match = re.search(r'"operation"\s*:\s*"([^"]+)"', text_content, re.IGNORECASE)
                    symbol_match = re.search(r'"symbol"\s*:\s*"([^"]+)"', text_content, re.IGNORECASE)
                    portion_match = re.search(r'"target_portion_of_balance"\s*:\s*([0-9.]+)', text_content)
                    reason_match = re.search(r'"reason"\s*:\s*"([^"]+)"', text_content)

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
                        return None

            # Validate that decision is a dict with required structure
            if not isinstance(decision, dict):
                logger.error(f"AI response is not a dict: {type(decision)}")
                return None

            # Attach debugging snapshots for downstream storage/logging
            strategy_details = decision.get("trading_strategy")

            decision["_prompt_snapshot"] = prompt
            if isinstance(strategy_details, str) and strategy_details.strip():
                decision["_reasoning_snapshot"] = strategy_details.strip()
            else:
                decision["_reasoning_snapshot"] = reasoning_text or ""
            # Use the most recent cleaned JSON payload; fall back to raw text if parsing succeeded via manual extraction
            snapshot_source = cleaned_content if 'cleaned_content' in locals() and cleaned_content else raw_decision_text
            decision["_raw_decision_text"] = snapshot_source

            logger.info(f"AI decision for {account.name}: {decision}")
            return decision

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


def save_ai_decision(db: Session, account: Account, decision: Dict, portfolio: Dict, executed: bool = False, order_id: Optional[int] = None) -> None:
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
            decision_snapshot=decision_snapshot_structured or raw_decision_snapshot
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
                "decision_snapshot": decision_log.decision_snapshot
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
