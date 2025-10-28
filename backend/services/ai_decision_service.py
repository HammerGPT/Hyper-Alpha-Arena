"""
AI Decision Service - Handles AI model API calls for trading decisions
"""
import logging
import random
import json
import time
from decimal import Decimal
from typing import Dict, Optional, List

import requests
from sqlalchemy.orm import Session

from database.models import Position, Account, AIDecisionLog
from services.asset_calculator import calc_positions_value
from services.news_feed import fetch_latest_news


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


def call_ai_for_decision(account: Account, portfolio: Dict, prices: Dict[str, float]) -> Optional[Dict]:
    """Call AI model API to get trading decision"""
    # Check if this is a default API key
    if _is_default_api_key(account.api_key):
        logger.info(f"Skipping AI trading for account {account.name} - using default API key")
        return None
    
    try:
        news_summary = fetch_latest_news()
        news_section = news_summary if news_summary else "No recent CoinJournal news available."

        prompt = f"""You are a cryptocurrency trading AI. Based on the following portfolio and market data, decide on a trading action.

Portfolio Data:
- Cash Available: ${portfolio['cash']:.2f}
- Frozen Cash: ${portfolio['frozen_cash']:.2f}
- Total Assets: ${portfolio['total_assets']:.2f}
- Current Positions: {json.dumps(portfolio['positions'], indent=2)}

Current Market Prices:
{json.dumps(prices, indent=2)}

Latest Crypto News (CoinJournal):
{news_section}

Analyze the market and portfolio, then respond with ONLY a JSON object in this exact format:
{{
  "operation": "buy" or "sell" or "hold",
  "symbol": "BTC" or "ETH" or "SOL" or "BNB" or "XRP" or "DOGE",
  "target_portion_of_balance": 0.2,
  "reason": "Brief explanation of your decision"
}}

Rules:
- operation must be "buy", "sell", or "hold"
- For "buy": symbol is what to buy, target_portion_of_balance is % of cash to use (0.0-1.0)
- For "sell": symbol is what to sell, target_portion_of_balance is % of position to sell (0.0-1.0)
- For "hold": no action taken
- Keep target_portion_of_balance between 0.1 and 0.3 for risk management
- Only choose symbols you have data for"""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {account.api_key}"
        }
        
        # Use OpenAI-compatible chat completions format
        # Detect model type for appropriate parameter handling
        model_lower = account.model.lower()

        # Reasoning models that don't support temperature parameter
        is_reasoning_model = any(x in model_lower for x in [
            'gpt-5', 'o1-preview', 'o1-mini', 'o1-', 'o3-', 'o4-'
        ])

        # o1 series specifically doesn't support system messages
        is_o1_series = any(x in model_lower for x in ['o1-preview', 'o1-mini', 'o1-'])

        # New models that use max_completion_tokens instead of max_tokens
        is_new_model = is_reasoning_model or any(x in model_lower for x in ['gpt-4o'])

        payload = {
            "model": account.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
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

        # For GPT-5 series, set reasoning_effort for trading decisions
        if 'gpt-5' in model_lower:
            # Use "low" for trading to balance speed and quality
            payload["reasoning_effort"] = "low"
        
        endpoints = build_chat_completion_endpoints(account.base_url, account.model)
        if not endpoints:
            logger.error(f"No valid API endpoint built for account {account.name}")
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
                        verify=False  # Disable SSL verification for custom AI endpoints
                    )
                    
                    if response.status_code == 200:
                        success = True
                        break  # Success, exit retry loop
                    elif response.status_code == 429:
                        # Rate limited, wait and retry
                        wait_time = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff with jitter
                        logger.warning(
                            f"AI API rate limited for {account.name} (attempt {attempt + 1}/{max_retries}), waiting {wait_time:.1f}s..."
                        )
                        if attempt < max_retries - 1:
                            time.sleep(wait_time)
                            continue
                        else:
                            logger.error(
                                f"AI API rate limited after {max_retries} attempts for endpoint {endpoint}: {response.text}"
                            )
                            break
                    else:
                        logger.warning(
                            f"AI API returned status {response.status_code} for endpoint {endpoint}: {response.text}"
                        )
                        break  # Try next endpoint if available
                except requests.RequestException as req_err:
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(
                            f"AI API request failed for endpoint {endpoint} (attempt {attempt + 1}/{max_retries}), "
                            f"retrying in {wait_time:.1f}s: {req_err}"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.warning(f"AI API request failed after {max_retries} attempts for endpoint {endpoint}: {req_err}")
                        break
            if success:
                break

        if not success or not response:
            logger.error(f"All API endpoints failed for account {account.name} ({account.model})")
            return None

        result = response.json()
        
        # Extract text from OpenAI-compatible response format
        if "choices" in result and len(result["choices"]) > 0:
            choice = result["choices"][0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "")
            
            # Check if response was truncated due to length limit
            if finish_reason == "length":
                logger.warning(f"AI response was truncated due to token limit. Consider increasing max_tokens.")
                # Try to get content from reasoning field if available (some models put partial content there)
                text_content = message.get("reasoning", "") or message.get("content", "")
            else:
                text_content = message.get("content", "")
            
            if not text_content:
                logger.error(f"Empty content in AI response: {result}")
                return None
                
            # Try to extract JSON from the text
            # Sometimes AI might wrap JSON in markdown code blocks
            text_content = text_content.strip()
            if "```json" in text_content:
                text_content = text_content.split("```json")[1].split("```")[0].strip()
            elif "```" in text_content:
                text_content = text_content.split("```")[1].split("```")[0].strip()
            
            # Handle potential JSON parsing issues with escape sequences
            try:
                decision = json.loads(text_content)
            except json.JSONDecodeError as parse_err:
                # Try to fix common JSON issues
                logger.warning(f"Initial JSON parse failed: {parse_err}")
                logger.warning(f"Problematic content: {text_content[:200]}...")
                
                # Try to clean up the text content
                cleaned_content = text_content
                
                # Replace problematic characters that might break JSON
                cleaned_content = cleaned_content.replace('\n', ' ')
                cleaned_content = cleaned_content.replace('\r', ' ')
                cleaned_content = cleaned_content.replace('\t', ' ')
                
                # Handle unescaped quotes in strings by escaping them
                import re
                # Try a simpler approach to fix common JSON issues
                # Replace smart quotes and em-dashes with regular equivalents
                cleaned_content = cleaned_content.replace('"', '"').replace('"', '"')
                cleaned_content = cleaned_content.replace(''', "'").replace(''', "'")
                cleaned_content = cleaned_content.replace('–', '-').replace('—', '-')
                cleaned_content = cleaned_content.replace('‑', '-')  # Non-breaking hyphen
                
                # Try parsing again
                try:
                    decision = json.loads(cleaned_content)
                    logger.info("Successfully parsed JSON after cleanup")
                except json.JSONDecodeError:
                    # If still failing, try to extract just the essential parts
                    logger.error("JSON parsing failed even after cleanup, attempting manual extraction")
                    try:
                        # Extract operation, symbol, and target_portion manually
                        operation_match = re.search(r'"operation":\s*"([^"]+)"', text_content)
                        symbol_match = re.search(r'"symbol":\s*"([^"]+)"', text_content)
                        portion_match = re.search(r'"target_portion_of_balance":\s*([0-9.]+)', text_content)
                        reason_match = re.search(r'"reason":\s*"([^"]*)', text_content)
                        
                        if operation_match and symbol_match and portion_match:
                            decision = {
                                "operation": operation_match.group(1),
                                "symbol": symbol_match.group(1),
                                "target_portion_of_balance": float(portion_match.group(1)),
                                "reason": reason_match.group(1) if reason_match else "AI response parsing issue"
                            }
                            logger.info("Successfully extracted AI decision manually")
                        else:
                            raise json.JSONDecodeError("Could not extract required fields", text_content, 0)
                    except Exception:
                        raise parse_err  # Re-raise original error
            
            # Validate that decision is a dict with required structure
            if not isinstance(decision, dict):
                logger.error(f"AI response is not a dict: {type(decision)}")
                return None
            
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
            order_id=order_id
        )
        
        db.add(decision_log)
        db.commit()
        db.refresh(decision_log)

        symbol_str = symbol if symbol else "N/A"
        logger.info(f"Saved AI decision log for account {account.name}: {operation} {symbol_str} "
                   f"prev_portion={prev_portion:.4f} target_portion={target_portion:.4f} executed={executed}")

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
                "order_id": decision_log.order_id
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
