"""
AI Attribution Analysis Service

Handles AI-assisted attribution analysis conversations using LLM.
Supports Function Calling for AI to query trading performance data.
Role: Strategy Diagnosis Doctor - analyze performance, identify issues, suggest improvements.
"""

import json
import logging
import re
import time
import requests
from typing import Dict, List, Optional, Any, Generator
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import text

from database.models import (
    AiAttributionConversation, AiAttributionMessage,
    Account, AIDecisionLog, PromptTemplate, SignalPool
)
from database.snapshot_connection import SnapshotSessionLocal
from database.snapshot_models import HyperliquidTrade
from services.ai_decision_service import build_chat_completion_endpoints, detect_api_format, _extract_text_from_message, get_max_tokens, build_llm_payload, build_llm_headers, extract_reasoning, convert_tools_to_anthropic, convert_messages_to_anthropic, strip_thinking_tags

logger = logging.getLogger(__name__)

# System prompt for AI Attribution Analysis
ATTRIBUTION_SYSTEM_PROMPT = """You are a professional Trading Strategy Diagnosis Doctor.

## YOUR ROLE
Analyze user's trading performance data, identify problem patterns, and provide actionable improvement suggestions.

## CRITICAL: EXCHANGE AND ENVIRONMENT CONFIRMATION
Before any analysis, you MUST confirm:

1. **Exchange**: Which exchange to analyze?
   - **hyperliquid**: Hyperliquid perpetual futures
   - **binance**: Binance USDT-M futures

2. **Environment** (for both exchanges):
   - **testnet**: Test network trades (exchange test funds)
   - **mainnet**: Real money trades
   - **paper**: Internal paper trading (simulated fills on mainnet data)

Ask the user: "Which exchange do you want to analyze - Hyperliquid or Binance? Also specify testnet, mainnet or paper."
Only proceed after getting a clear answer. Pass the exchange and environment parameters to ALL tool calls.

## ACCOUNT IDENTIFICATION
Users typically refer to accounts by NAME (e.g., "Deepseek", "Claude", "GPT"), not by ID.
When user mentions an account name:
1. FIRST call `list_ai_accounts` to get all accounts with their IDs and names
2. Match the user's description to find the correct account ID
3. Then proceed with analysis using that account ID

NEVER ask user for account ID directly. Instead, use `list_ai_accounts` and present options like:
"I found these AI accounts: Deepseek (ID: 1), Claude (ID: 2). Which one would you like to analyze?"

## GUIDED CONVERSATION
Before using analysis tools, confirm:
1. Which exchange? (hyperliquid or binance) - REQUIRED
2. Which environment? (testnet, mainnet or paper) - REQUIRED for both exchanges
3. Which account? (use `list_ai_accounts` to find by name)
4. Time period? (default: 30 days)

## WORKFLOW
1. Confirm exchange and environment with user
2. Use `list_ai_accounts` to identify account by name
3. Use `get_attribution_summary` to get overall performance metrics
4. Use `get_account_strategy` to understand current strategy configuration
5. Use `get_prompt_template` to see the AI prompt being used
6. Use `get_trade_decision_chain` to examine specific trade decisions
7. Identify patterns: which symbols or time periods perform poorly
8. Use `suggest_prompt_modification` to output structured improvement suggestions

## OUTPUT FORMAT
After analysis, output diagnosis cards using this format:

```diagnosis-card
{
  "type": "problem",
  "title": "High Loss Rate on DOGE",
  "severity": "high",
  "metrics": {"win_rate": "23%", "loss_count": 15, "symbol": "DOGE"},
  "description": "Your strategy loses 77% of trades on DOGE."
}
```

```prompt-suggestion
{
  "title": "Add DOGE Filter",
  "current": "Execute trades based on signal triggers",
  "suggested": "Avoid DOGE trades or reduce position size by 50%",
  "reason": "Historical data shows poor performance on DOGE"
}
```

## IMPORTANT RULES
- ALWAYS confirm exchange and environment before analysis
- NEVER ask for account ID - use `list_ai_accounts` to find by name
- Always use tools to get real data before making conclusions
- Be specific with numbers and percentages
- Provide actionable suggestions, not vague advice
- Connect diagnosis to prompt modifications when possible
"""

# Tools schema for Function Calling
ATTRIBUTION_TOOLS = []  # Will be defined below


def _define_tools():
    """Define Function Calling tools for attribution analysis"""
    global ATTRIBUTION_TOOLS
    ATTRIBUTION_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "list_ai_accounts",
                "description": "List all AI trading accounts with their IDs, names, and models. Use this FIRST when user mentions an account by name (e.g., 'Deepseek', 'Claude') to find the account ID.",
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
                "name": "get_attribution_summary",
                "description": "Get trading performance summary including win rate, PnL, trade counts by operation/symbol.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "integer", "description": "Account ID to analyze. Use 0 for all accounts."},
                        "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange to analyze trades from. REQUIRED."},
                        "environment": {"type": "string", "enum": ["testnet", "mainnet", "paper"], "description": "Trading environment. REQUIRED for both exchanges."},
                        "days": {"type": "integer", "description": "Number of days to analyze (7, 30, 90)", "default": 30}
                    },
                    "required": ["account_id", "exchange"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_account_strategy",
                "description": "Get account's trading strategy configuration including signal pool and prompt binding.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "integer", "description": "Account ID to query"}
                    },
                    "required": ["account_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_prompt_template",
                "description": "Get the prompt template content used by an account.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "integer", "description": "Account ID to get prompt for"}
                    },
                    "required": ["account_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_signal_pool_config",
                "description": "Get signal pool configuration including signals and trigger conditions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pool_id": {"type": "integer", "description": "Signal pool ID to query"}
                    },
                    "required": ["pool_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_trade_decision_chain",
                "description": "Get detailed decision chain for specific trades including AI reasoning and execution results.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "integer", "description": "Account ID"},
                        "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange to query trades from. REQUIRED."},
                        "environment": {"type": "string", "enum": ["testnet", "mainnet", "paper"], "description": "Trading environment. REQUIRED for both exchanges."},
                        "limit": {"type": "integer", "description": "Number of recent trades to fetch", "default": 10},
                        "filter_type": {"type": "string", "enum": ["all", "wins", "losses"], "description": "Filter by trade outcome"}
                    },
                    "required": ["account_id", "exchange"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "suggest_prompt_modification",
                "description": "Generate a structured prompt modification suggestion card based on diagnosis.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Short title for the suggestion"},
                        "current_behavior": {"type": "string", "description": "Current prompt behavior causing issues"},
                        "suggested_change": {"type": "string", "description": "Specific prompt modification to apply"},
                        "reason": {"type": "string", "description": "Why this change will improve performance"}
                    },
                    "required": ["title", "current_behavior", "suggested_change", "reason"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_factor_attribution",
                "description": "Analyze trading performance grouped by factor signal triggers. Shows which factors led to profitable vs losing trades.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "integer", "description": "Account ID (0 for all)"},
                        "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange. REQUIRED."},
                        "environment": {"type": "string", "enum": ["testnet", "mainnet", "paper"], "description": "Environment. REQUIRED."},
                        "days": {"type": "integer", "description": "Analysis period in days", "default": 30}
                    },
                    "required": ["account_id", "exchange"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_factors",
                "description": "Query factor library and effectiveness data. Returns factor values, IC, ICIR, win rate, decay, and IC trend (ic_7d/ic_trend). ic_trend > 1 = factor strengthening recently, < 1 = weakening.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange (required)"},
                        "symbol": {"type": "string", "description": "Symbol for effectiveness ranking"},
                        "forward_period": {"type": "string", "enum": ["1h", "4h", "12h", "24h"], "description": "Forward period (default: 4h)"}
                    },
                    "required": ["exchange"]
                }
            }
        }
    ]


# Initialize tools
_define_tools()


def _execute_tool(db: Session, tool_name: str, args: Dict) -> str:
    """Execute a tool and return JSON result string"""
    try:
        if tool_name == "list_ai_accounts":
            return _tool_list_ai_accounts(db)
        elif tool_name == "get_attribution_summary":
            return _tool_get_attribution_summary(db, args)
        elif tool_name == "get_account_strategy":
            return _tool_get_account_strategy(db, args)
        elif tool_name == "get_prompt_template":
            return _tool_get_prompt_template(db, args)
        elif tool_name == "get_signal_pool_config":
            return _tool_get_signal_pool_config(db, args)
        elif tool_name == "get_trade_decision_chain":
            return _tool_get_trade_decision_chain(db, args)
        elif tool_name == "suggest_prompt_modification":
            return _tool_suggest_prompt_modification(args)
        elif tool_name == "get_factor_attribution":
            return _tool_get_factor_attribution(db, args)
        elif tool_name == "query_factors":
            from services.hyper_ai_tools import execute_query_factors
            return execute_query_factors(db, args.get("exchange", "hyperliquid"), args.get("symbol"), forward_period=args.get("forward_period", "4h"))
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as e:
        logger.error(f"Tool execution error: {tool_name}: {e}")
        return json.dumps({"error": str(e)})


def _get_fees_for_decisions(decisions: List[AIDecisionLog]) -> Dict[int, float]:
    """Batch query HyperliquidTrade to get total fees for each decision."""
    if not decisions:
        return {}

    # Collect all order IDs (main, tp, sl)
    order_ids = set()
    decision_orders: Dict[int, List[str]] = {}

    for d in decisions:
        orders = []
        if d.hyperliquid_order_id:
            order_ids.add(d.hyperliquid_order_id)
            orders.append(d.hyperliquid_order_id)
        if d.tp_order_id:
            order_ids.add(d.tp_order_id)
            orders.append(d.tp_order_id)
        if d.sl_order_id:
            order_ids.add(d.sl_order_id)
            orders.append(d.sl_order_id)
        decision_orders[d.id] = orders

    if not order_ids:
        return {d.id: 0.0 for d in decisions}

    # Batch query fees from HyperliquidTrade
    fee_map: Dict[str, float] = {}
    try:
        snapshot_db = SnapshotSessionLocal()
        trades = snapshot_db.query(HyperliquidTrade).filter(
            HyperliquidTrade.order_id.in_(list(order_ids))
        ).all()
        for t in trades:
            if t.order_id:
                fee_map[str(t.order_id)] = float(t.fee or 0)
        snapshot_db.close()
    except Exception as e:
        logger.warning(f"Failed to fetch fees from HyperliquidTrade: {e}")

    # Calculate total fee for each decision
    result: Dict[int, float] = {}
    for d in decisions:
        total_fee = 0.0
        for oid in decision_orders.get(d.id, []):
            total_fee += fee_map.get(oid, 0.0)
        result[d.id] = total_fee

    return result


def _tool_get_attribution_summary(db: Session, args: Dict) -> str:
    """Get trading performance summary"""
    account_id = args.get("account_id", 0)
    exchange = args.get("exchange")
    environment = args.get("environment")
    days = args.get("days", 30)

    if not exchange:
        return json.dumps({"error": "exchange is required (hyperliquid or binance)"})

    if not environment:
        return json.dumps({"error": "environment is required (testnet or mainnet)"})

    start_date = datetime.now() - timedelta(days=days)

    # Build query with exchange and environment filter
    # Only include trades with non-zero PnL (exclude opening trades)
    query = db.query(AIDecisionLog).filter(
        AIDecisionLog.operation.in_(["buy", "sell", "close"]),
        AIDecisionLog.executed == "true",
        AIDecisionLog.realized_pnl.isnot(None),
        AIDecisionLog.realized_pnl != 0,  # Exclude opening trades (no settled PnL)
        AIDecisionLog.created_at >= start_date,
        AIDecisionLog.exchange == exchange,
        AIDecisionLog.hyperliquid_environment == environment
    )

    if account_id > 0:
        query = query.filter(AIDecisionLog.account_id == account_id)

    decisions = query.all()

    if not decisions:
        return json.dumps({"message": "No trading data found for the specified period"})

    # Get fees for all decisions
    fee_map = _get_fees_for_decisions(decisions)

    # Calculate metrics
    total_trades = len(decisions)
    wins = sum(1 for d in decisions if d.realized_pnl and float(d.realized_pnl) > 0)
    losses = sum(1 for d in decisions if d.realized_pnl and float(d.realized_pnl) < 0)
    total_pnl = sum(float(d.realized_pnl or 0) for d in decisions)
    total_fees = sum(fee_map.get(d.id, 0.0) for d in decisions)
    net_pnl = total_pnl - total_fees

    # By operation
    by_operation = {}
    for d in decisions:
        op = d.operation
        if op not in by_operation:
            by_operation[op] = {"count": 0, "wins": 0, "pnl": 0, "fees": 0}
        by_operation[op]["count"] += 1
        by_operation[op]["pnl"] += float(d.realized_pnl or 0)
        by_operation[op]["fees"] += fee_map.get(d.id, 0.0)
        if d.realized_pnl and float(d.realized_pnl) > 0:
            by_operation[op]["wins"] += 1

    # By symbol
    by_symbol = {}
    for d in decisions:
        sym = d.symbol or "UNKNOWN"
        if sym not in by_symbol:
            by_symbol[sym] = {"count": 0, "wins": 0, "pnl": 0, "fees": 0}
        by_symbol[sym]["count"] += 1
        by_symbol[sym]["pnl"] += float(d.realized_pnl or 0)
        by_symbol[sym]["fees"] += fee_map.get(d.id, 0.0)
        if d.realized_pnl and float(d.realized_pnl) > 0:
            by_symbol[sym]["wins"] += 1

    return json.dumps({
        "period_days": days,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": f"{(wins/total_trades*100):.1f}%" if total_trades > 0 else "N/A",
        "total_pnl": round(total_pnl, 2),
        "total_fees": round(total_fees, 2),
        "net_pnl": round(net_pnl, 2),
        "by_operation": by_operation,
        "by_symbol": by_symbol
    })


def _tool_get_account_strategy(db: Session, args: Dict) -> str:
    """Get account strategy configuration"""
    from database.models import AccountStrategyConfig
    from repositories.strategy_repo import parse_signal_pool_ids

    account_id = args.get("account_id")
    if not account_id:
        return json.dumps({"error": "account_id is required"})

    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return json.dumps({"error": f"Account {account_id} not found"})

    # Get prompt binding for prompt template info
    prompt_binding = getattr(account, 'prompt_binding', None)
    prompt_info = None
    if prompt_binding and prompt_binding.prompt_template:
        prompt_info = {
            "id": prompt_binding.prompt_template.id,
            "name": prompt_binding.prompt_template.name
        }

    # Get signal pool binding from AccountStrategyConfig (correct source)
    strategy = db.query(AccountStrategyConfig).filter(
        AccountStrategyConfig.account_id == account_id
    ).first()

    signal_pool_ids = []
    signal_pool_names = []
    if strategy:
        signal_pool_ids = parse_signal_pool_ids(strategy)
        # Query pool names
        if signal_pool_ids:
            result = db.execute(
                text("SELECT id, pool_name FROM signal_pools WHERE id = ANY(:ids)"),
                {"ids": signal_pool_ids}
            ).fetchall()
            pool_name_map = {row[0]: row[1] for row in result}
            signal_pool_names = [pool_name_map.get(pid) for pid in signal_pool_ids if pool_name_map.get(pid)]

    return json.dumps({
        "account_id": account.id,
        "name": account.name,
        "model": account.model,
        "auto_trading_enabled": account.auto_trading_enabled,
        "hyperliquid_enabled": account.hyperliquid_enabled,
        "hyperliquid_environment": account.hyperliquid_environment,
        "max_leverage": account.max_leverage,
        "default_leverage": account.default_leverage,
        "prompt_template": prompt_info,
        "signal_pool_ids": signal_pool_ids if signal_pool_ids else None,
        "signal_pool_names": signal_pool_names if signal_pool_names else None,
        "note": "Account not bound to any signal pool" if not signal_pool_ids else None
    })


def _tool_get_prompt_template(db: Session, args: Dict) -> str:
    """Get prompt template content for an account"""
    account_id = args.get("account_id")
    if not account_id:
        return json.dumps({"error": "account_id is required"})

    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return json.dumps({"error": f"Account {account_id} not found"})

    if not account.prompt_binding or not account.prompt_binding.prompt_template:
        return json.dumps({"message": "No prompt template bound to this account"})

    template = account.prompt_binding.prompt_template
    return json.dumps({
        "id": template.id,
        "name": template.name,
        "content": template.template_text,  # Return full content without truncation
        "is_system": template.is_system
    })


def _tool_get_signal_pool_config(db: Session, args: Dict) -> str:
    """Get signal pool configuration with detailed signal trigger conditions"""
    pool_id = args.get("pool_id")
    if not pool_id:
        return json.dumps({"error": "pool_id is required"})

    pool = db.query(SignalPool).filter(SignalPool.id == pool_id).first()
    if not pool:
        return json.dumps({"error": f"Signal pool {pool_id} not found"})

    # Parse signal_ids JSON
    signal_ids = []
    if pool.signal_ids:
        try:
            signal_ids = json.loads(pool.signal_ids) if isinstance(pool.signal_ids, str) else pool.signal_ids
        except:
            pass

    # Parse symbols JSON
    symbols = []
    if pool.symbols:
        try:
            symbols = json.loads(pool.symbols) if isinstance(pool.symbols, str) else pool.symbols
        except:
            pass

    # Fetch detailed signal configurations
    signals_detail = []
    if signal_ids:
        result = db.execute(
            text("SELECT id, signal_name, description, trigger_condition FROM signal_definitions WHERE id = ANY(:ids)"),
            {"ids": signal_ids}
        ).fetchall()
        for row in result:
            trigger_condition = row[3]
            if isinstance(trigger_condition, str):
                try:
                    trigger_condition = json.loads(trigger_condition)
                except:
                    pass
            signals_detail.append({
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "trigger_condition": trigger_condition
            })

    return json.dumps({
        "id": pool.id,
        "name": pool.pool_name,
        "symbols": symbols,
        "logic": pool.logic,
        "enabled": pool.enabled,
        "signal_ids": signal_ids,
        "signals": signals_detail
    })


def _tool_get_trade_decision_chain(db: Session, args: Dict) -> str:
    """Get detailed trade decision chain"""
    account_id = args.get("account_id")
    exchange = args.get("exchange")
    environment = args.get("environment")
    limit = args.get("limit", 10)
    filter_type = args.get("filter_type", "all")

    if not account_id:
        return json.dumps({"error": "account_id is required"})

    if not exchange:
        return json.dumps({"error": "exchange is required (hyperliquid or binance)"})

    if not environment:
        return json.dumps({"error": "environment is required (testnet or mainnet)"})

    query = db.query(AIDecisionLog).filter(
        AIDecisionLog.account_id == account_id,
        AIDecisionLog.executed == "true",
        AIDecisionLog.realized_pnl.isnot(None),
        AIDecisionLog.exchange == exchange,
        AIDecisionLog.hyperliquid_environment == environment
    )

    if filter_type == "wins":
        query = query.filter(AIDecisionLog.realized_pnl > 0)
    elif filter_type == "losses":
        query = query.filter(AIDecisionLog.realized_pnl < 0)

    decisions = query.order_by(AIDecisionLog.created_at.desc()).limit(limit).all()

    # Get fees for all decisions
    fee_map = _get_fees_for_decisions(decisions)

    trades = []
    for d in decisions:
        pnl = float(d.realized_pnl) if d.realized_pnl else 0
        fee = fee_map.get(d.id, 0.0)

        # Parse prices from decision_snapshot
        entry_price = None
        tp_price = None
        sl_price = None
        if d.decision_snapshot:
            try:
                snapshot = json.loads(d.decision_snapshot) if isinstance(d.decision_snapshot, str) else d.decision_snapshot
                entry_price = snapshot.get("max_price") or snapshot.get("entry_price")
                tp_price = snapshot.get("take_profit_price") or snapshot.get("tp_price")
                sl_price = snapshot.get("stop_loss_price") or snapshot.get("sl_price")
            except:
                pass

        trades.append({
            "id": d.id,
            "symbol": d.symbol,
            "operation": d.operation,
            "entry_price": entry_price,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "realized_pnl": pnl,
            "fee": round(fee, 2),
            "net_pnl": round(pnl - fee, 2),
            "reason": (d.reason[:500] if d.reason else None),  # Truncate
            "created_at": d.created_at.isoformat() if d.created_at else None
        })

    return json.dumps({"trades": trades, "count": len(trades)})


def _tool_suggest_prompt_modification(args: Dict) -> str:
    """Generate structured prompt modification suggestion"""
    return json.dumps({
        "_type": "prompt_suggestion",
        "title": args.get("title", "Untitled Suggestion"),
        "current_behavior": args.get("current_behavior", ""),
        "suggested_change": args.get("suggested_change", ""),
        "reason": args.get("reason", "")
    })


def _tool_list_ai_accounts(db: Session) -> str:
    """List all AI trading accounts with their IDs, names, and models"""
    accounts = db.query(Account).filter(Account.account_type == "AI").all()

    if not accounts:
        return json.dumps({"message": "No AI accounts found", "accounts": []})

    account_list = []
    for acc in accounts:
        account_list.append({
            "id": acc.id,
            "name": acc.name,
            "model": acc.model,
            "environment": acc.hyperliquid_environment,
            "auto_trading_enabled": acc.auto_trading_enabled
        })

    return json.dumps({"accounts": account_list, "count": len(account_list)})


def _tool_get_factor_attribution(db: Session, args: Dict) -> str:
    """Analyze trading performance grouped by factor signal triggers."""
    from database.models import SignalTriggerLog

    account_id = args.get("account_id", 0)
    exchange = args.get("exchange")
    environment = args.get("environment")
    days = args.get("days", 30)

    if not exchange:
        return json.dumps({"error": "exchange is required"})
    if not environment:
        return json.dumps({"error": "environment is required"})

    start_date = datetime.now() - timedelta(days=days)

    query = db.query(AIDecisionLog).filter(
        AIDecisionLog.operation.in_(["buy", "sell", "close"]),
        AIDecisionLog.executed == "true",
        AIDecisionLog.realized_pnl.isnot(None),
        AIDecisionLog.realized_pnl != 0,
        AIDecisionLog.created_at >= start_date,
        AIDecisionLog.exchange == exchange,
        AIDecisionLog.hyperliquid_environment == environment,
        AIDecisionLog.signal_trigger_id.isnot(None)
    )
    if account_id > 0:
        query = query.filter(AIDecisionLog.account_id == account_id)

    decisions = query.all()
    if not decisions:
        return json.dumps({"message": "No factor-triggered trades found"})

    fee_map = _get_fees_for_decisions(decisions)

    trigger_ids = set(d.signal_trigger_id for d in decisions)
    triggers = db.query(SignalTriggerLog).filter(
        SignalTriggerLog.id.in_(list(trigger_ids)),
        SignalTriggerLog.trigger_type.like("factor:%")
    ).all()
    trigger_map = {t.id: t for t in triggers}

    by_factor: Dict[str, Dict] = {}
    for d in decisions:
        trig = trigger_map.get(d.signal_trigger_id)
        if not trig:
            continue
        fname = trig.trigger_type.split(":", 1)[1] if ":" in trig.trigger_type else trig.trigger_type
        if fname not in by_factor:
            by_factor[fname] = {"count": 0, "wins": 0, "pnl": 0, "fees": 0}
        by_factor[fname]["count"] += 1
        pnl = float(d.realized_pnl or 0)
        by_factor[fname]["pnl"] += pnl
        by_factor[fname]["fees"] += fee_map.get(d.id, 0.0)
        if pnl > 0:
            by_factor[fname]["wins"] += 1

    items = []
    for fname, stats in by_factor.items():
        items.append({
            "factor_name": fname,
            "trade_count": stats["count"],
            "wins": stats["wins"],
            "win_rate": f"{stats['wins']/stats['count']*100:.1f}%" if stats["count"] > 0 else "N/A",
            "total_pnl": round(stats["pnl"], 2),
            "total_fees": round(stats["fees"], 2),
            "net_pnl": round(stats["pnl"] - stats["fees"], 2),
        })

    items.sort(key=lambda x: x["trade_count"], reverse=True)
    return json.dumps({"period_days": days, "factors": items})


def extract_diagnosis_results(content: str) -> List[Dict]:
    """Extract diagnosis cards and prompt suggestions from AI response"""
    results = []

    # Extract diagnosis cards
    diagnosis_pattern = r"```diagnosis-card\s*([\s\S]*?)```"
    for match in re.findall(diagnosis_pattern, content):
        try:
            card = json.loads(match.strip())
            card["_type"] = "diagnosis"
            results.append(card)
        except:
            pass

    # Extract prompt suggestions
    suggestion_pattern = r"```prompt-suggestion\s*([\s\S]*?)```"
    for match in re.findall(suggestion_pattern, content):
        try:
            suggestion = json.loads(match.strip())
            suggestion["_type"] = "prompt_suggestion"
            results.append(suggestion)
        except:
            pass

    return results


def generate_attribution_analysis_stream(
    db: Session,
    account_id: Optional[int] = None,
    user_message: str = "",
    conversation_id: Optional[int] = None,
    user_id: int = 1,
    llm_config: Optional[Dict[str, Any]] = None
) -> Generator[str, None, None]:
    """Generate attribution analysis with SSE streaming"""
    start_time = time.time()
    request_id = f"attr_analysis_{int(start_time)}"

    logger.info(f"[AI Attribution {request_id}] Starting: account_id={account_id}")

    try:
        # Get LLM config: either from llm_config param or from account_id
        if llm_config:
            # Use provided llm_config (e.g., from Hyper AI sub-agent call)
            api_config = {
                "base_url": llm_config.get("base_url"),
                "api_key": llm_config.get("api_key"),
                "model": llm_config.get("model"),
                "api_format": llm_config.get("api_format", "openai")
            }
            account = None
        else:
            # Original logic: get from AI account
            account = db.query(Account).filter(
                Account.id == account_id,
                Account.account_type == "AI"
            ).first()

            if not account:
                yield f"event: error\ndata: {json.dumps({'message': 'AI account not found'})}\n\n"
                return

            api_config = {
                "base_url": account.base_url,
                "api_key": account.api_key,
                "model": account.model,
                "api_format": detect_api_format(account.base_url)[1] or "openai"
            }

        # Get or create conversation
        conversation = None
        if conversation_id:
            conversation = db.query(AiAttributionConversation).filter(
                AiAttributionConversation.id == conversation_id,
                AiAttributionConversation.user_id == user_id
            ).first()

        is_new_conversation = False
        if not conversation:
            title = user_message[:50] + "..." if len(user_message) > 50 else user_message
            conversation = AiAttributionConversation(user_id=user_id, title=title)
            db.add(conversation)
            db.flush()
            is_new_conversation = True

        if is_new_conversation:
            yield f"event: conversation_created\ndata: {json.dumps({'conversation_id': conversation.id})}\n\n"

        # Save user message
        user_msg = AiAttributionMessage(
            conversation_id=conversation.id,
            role="user",
            content=user_message
        )
        db.add(user_msg)
        db.flush()

        yield f"event: status\ndata: {json.dumps({'message': 'Analyzing...'})}\n\n"

        # Build message history with compression support
        from services.ai_context_compression_service import (
            compress_messages, update_compression_points,
            restore_tool_calls_to_messages,
            get_last_compression_point, filter_messages_by_compression,
        )

        messages = [{"role": "system", "content": ATTRIBUTION_SYSTEM_PROMPT}]

        # Check compression points - inject summary for compressed messages
        cp = get_last_compression_point(conversation)
        if cp and cp.get("summary"):
            messages.append({
                "role": "system",
                "content": f"[Previous conversation summary]\n{cp['summary']}"
            })

        # Load history, filter by compression point
        history = db.query(AiAttributionMessage).filter(
            AiAttributionMessage.conversation_id == conversation.id,
            AiAttributionMessage.id != user_msg.id
        ).order_by(AiAttributionMessage.created_at).limit(100).all()

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
        comp_result = compress_messages(messages, api_config, db=db)
        messages = comp_result["messages"]

        # Update compression_points if compression occurred
        if comp_result["compressed"] and comp_result["summary"] and last_message_id:
            update_compression_points(
                conversation, last_message_id,
                comp_result["summary"], comp_result["compressed_at"], db
            )

        # Call LLM with Function Calling
        api_format = api_config.get("api_format", "openai")
        if api_format == 'anthropic':
            ep, _ = detect_api_format(api_config["base_url"])
            endpoints = [ep] if ep else []
        else:
            endpoints = build_chat_completion_endpoints(api_config["base_url"], api_config["model"])
        if not endpoints:
            yield f"event: error\ndata: {json.dumps({'message': 'Invalid API configuration'})}\n\n"
            return

        # Use unified headers builder (see build_llm_headers in ai_decision_service)
        headers = build_llm_headers(api_format, api_config["api_key"], api_config["base_url"])

        # Function calling loop
        max_rounds = 15
        assistant_content = None

        # Collect reasoning and analysis log for storage
        all_reasoning_parts = []
        tool_calls_log = []

        for round_num in range(max_rounds):
            is_last = (round_num == max_rounds - 1)

            yield f"event: tool_round\ndata: {json.dumps({'round': round_num + 1, 'max_rounds': max_rounds})}\n\n"

            if is_last:
                messages.append({
                    "role": "user",
                    "content": "Now provide your final analysis with diagnosis cards and suggestions."
                })

            # Use unified payload builder (see build_llm_payload in ai_decision_service)
            if api_format == 'anthropic':
                sys_prompt, anthropic_messages = convert_messages_to_anthropic(messages)
                tools_for_round = convert_tools_to_anthropic(ATTRIBUTION_TOOLS) if not is_last else None
                request_payload = build_llm_payload(
                    model=api_config["model"],
                    messages=[{"role": "system", "content": sys_prompt}] + anthropic_messages,
                    api_format=api_format,
                    tools=tools_for_round,
                )
            else:
                request_payload = build_llm_payload(
                    model=api_config["model"],
                    messages=messages,
                    api_format=api_format,
                    tools=ATTRIBUTION_TOOLS if not is_last else None,
                    tool_choice="auto" if not is_last else None,
                )

            response = None
            last_error = None
            last_status_code = None
            last_response_text = None

            for endpoint in endpoints:
                try:
                    response = requests.post(endpoint, json=request_payload, headers=headers, timeout=120)
                    last_status_code = response.status_code
                    last_response_text = response.text[:2000] if response.text else None
                    if response.status_code == 200:
                        break
                    else:
                        last_error = f"HTTP {response.status_code}"
                        logger.warning(f"[AI Attribution] Endpoint failed: {response.status_code} - {response.text[:500]}")
                except requests.exceptions.Timeout as e:
                    last_error = f"Timeout after 120s: {str(e)}"
                    logger.warning(f"[AI Attribution] Endpoint timeout: {e}")
                except requests.exceptions.ConnectionError as e:
                    last_error = f"Connection error: {str(e)}"
                    logger.warning(f"[AI Attribution] Connection error: {e}")
                except Exception as e:
                    last_error = f"{type(e).__name__}: {str(e)}"
                    logger.warning(f"[AI Attribution] Endpoint error: {type(e).__name__}: {e}")

            if not response or response.status_code != 200:
                error_parts = []
                if last_error:
                    error_parts.append(f"error={last_error}")
                if last_status_code:
                    error_parts.append(f"status={last_status_code}")
                if last_response_text:
                    error_parts.append(f"response={last_response_text[:500]}")
                error_detail = "; ".join(error_parts) if error_parts else "No response from API"
                logger.error(f"[AI Attribution] API failed at round {round_num + 1}: {error_detail}")

                if tool_calls_log:
                    reasoning_snapshot = "\n\n---\n\n".join(all_reasoning_parts) if all_reasoning_parts else None
                    assistant_msg = AiAttributionMessage(
                        conversation_id=conversation.id,
                        role="assistant",
                        content=f"**[Interrupted at round {round_num + 1}]** {error_detail}",
                        reasoning_snapshot=reasoning_snapshot,
                        tool_calls_log=json.dumps(tool_calls_log),
                        is_complete=False,
                        interrupt_reason=f"Round {round_num + 1}: {error_detail}"
                    )
                    db.add(assistant_msg)
                    db.commit()
                    yield f"event: interrupted\ndata: {json.dumps({'message_id': assistant_msg.id, 'conversation_id': conversation.id, 'round': round_num + 1, 'error': error_detail})}\n\n"
                else:
                    yield f"event: error\ndata: {json.dumps({'message': f'API request failed: {error_detail}'})}\n\n"
                return

            resp_json = response.json()

            # Parse response based on API format
            if api_format == 'anthropic':
                content_blocks = resp_json.get("content", [])
                tool_uses = []
                content = ""
                reasoning = ""
                for block in content_blocks:
                    if block.get("type") == "text":
                        content += block.get("text", "")
                    elif block.get("type") == "tool_use":
                        tool_uses.append(block)
                    elif block.get("type") == "thinking":
                        t = block.get("thinking", "")
                        if t:
                            reasoning += t
                api_tool_calls = tool_uses if tool_uses else None
            else:
                message = resp_json["choices"][0]["message"]
                tool_calls = message.get("tool_calls", [])
                content = message.get("content", "")
                reasoning = message.get("reasoning_content", "") or extract_reasoning(message)
                api_tool_calls = tool_calls if tool_calls else None

            # Strip <thinking> text tags from content
            content, tag_thinking = strip_thinking_tags(content)
            if tag_thinking and not reasoning:
                reasoning = tag_thinking

            if reasoning:
                yield f"event: reasoning\ndata: {json.dumps({'content': reasoning[:200]})}\n\n"
                all_reasoning_parts.append(reasoning)

            if api_tool_calls:
                if api_format == 'anthropic':
                    messages.append({
                        "role": "assistant",
                        "content": content or "",
                        "tool_use_blocks": resp_json.get("content", [])
                    })
                    for tool_use in api_tool_calls:
                        func_name = tool_use.get("name", "")
                        tool_id = tool_use.get("id", "")
                        func_args = tool_use.get("input", {})
                        yield f"event: tool_call\ndata: {json.dumps({'name': func_name, 'arguments': func_args})}\n\n"
                        result = _execute_tool(db, func_name, func_args)
                        yield f"event: tool_result\ndata: {json.dumps({'name': func_name, 'result': json.loads(result)})}\n\n"
                        tool_calls_log.append({"tool": func_name, "args": func_args, "result": result})
                        messages.append({"role": "tool", "tool_call_id": tool_id, "content": result})
                else:
                    msg_dict = {"role": "assistant", "content": content or "", "tool_calls": api_tool_calls}
                    if reasoning:
                        msg_dict["reasoning_content"] = reasoning
                    messages.append(msg_dict)
                    for tc in api_tool_calls:
                        func_name = tc["function"]["name"]
                        try:
                            func_args = json.loads(tc["function"]["arguments"])
                        except:
                            func_args = {}
                        yield f"event: tool_call\ndata: {json.dumps({'name': func_name, 'arguments': func_args})}\n\n"
                        result = _execute_tool(db, func_name, func_args)
                        yield f"event: tool_result\ndata: {json.dumps({'name': func_name, 'result': json.loads(result)})}\n\n"
                        tool_calls_log.append({"tool": func_name, "args": func_args, "result": result})
                        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            else:
                # Final response - only use content, not reasoning
                assistant_content = _extract_text_from_message(content) if content else ""
                break

        if not assistant_content:
            assistant_content = "Analysis completed but no final response generated."

        # Extract diagnosis results
        diagnosis_results = extract_diagnosis_results(assistant_content)

        # Save assistant message with reasoning and tool calls log
        reasoning_snapshot = "\n\n---\n\n".join(all_reasoning_parts) if all_reasoning_parts else None
        tool_calls_log_json = json.dumps(tool_calls_log) if tool_calls_log else None

        assistant_msg = AiAttributionMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=assistant_content,
            diagnosis_result=json.dumps(diagnosis_results) if diagnosis_results else None,
            reasoning_snapshot=reasoning_snapshot,
            tool_calls_log=tool_calls_log_json,
            is_complete=True
        )
        db.add(assistant_msg)
        db.commit()

        # Send final response
        yield f"event: content\ndata: {json.dumps({'content': assistant_content})}\n\n"
        yield f"event: done\ndata: {json.dumps({'conversation_id': conversation.id, 'message_id': assistant_msg.id, 'content': assistant_content, 'diagnosis_results': diagnosis_results, 'tool_calls_log': json.loads(tool_calls_log_json) if tool_calls_log_json else None, 'reasoning_snapshot': reasoning_snapshot if reasoning_snapshot else None, 'compression_points': json.loads(conversation.compression_points) if conversation.compression_points else None})}\n\n"

    except Exception as e:
        logger.error(f"[AI Attribution {request_id}] Error: {e}", exc_info=True)
        db.rollback()
        yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"


def get_attribution_conversations(db: Session, user_id: int = 1, limit: int = 20) -> List[Dict]:
    """Get list of attribution analysis conversations"""
    conversations = db.query(AiAttributionConversation).filter(
        AiAttributionConversation.user_id == user_id
    ).order_by(AiAttributionConversation.updated_at.desc()).limit(limit).all()

    return [{
        "id": c.id,
        "title": c.title,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None
    } for c in conversations]


def get_attribution_messages(db: Session, conversation_id: int, user_id: int = 1) -> List[Dict]:
    """Get messages for a specific conversation"""
    conversation = db.query(AiAttributionConversation).filter(
        AiAttributionConversation.id == conversation_id,
        AiAttributionConversation.user_id == user_id
    ).first()

    if not conversation:
        return []

    messages = db.query(AiAttributionMessage).filter(
        AiAttributionMessage.conversation_id == conversation_id
    ).order_by(AiAttributionMessage.created_at).all()

    result = []
    for m in messages:
        msg_dict = {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        if m.diagnosis_result:
            try:
                msg_dict["diagnosis_results"] = json.loads(m.diagnosis_result)
            except:
                pass
        # Include reasoning and tool calls log for history display
        if m.reasoning_snapshot:
            msg_dict["reasoning_snapshot"] = m.reasoning_snapshot
        if m.tool_calls_log:
            try:
                msg_dict["tool_calls_log"] = json.loads(m.tool_calls_log)
            except:
                pass
        if hasattr(m, 'is_complete'):
            msg_dict["is_complete"] = m.is_complete if m.is_complete is not None else True
        result.append(msg_dict)

    return result
