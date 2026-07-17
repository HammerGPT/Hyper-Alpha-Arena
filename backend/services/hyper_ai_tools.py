"""
Hyper AI Tools - Tools for Hyper AI main agent

Provides tools for:
- System overview and diagnostics
- Wallet status queries
- API reference documentation
- Market data (klines, regime, flow)
- Create/save operations (signal pool, prompt, program, AI trader)
- Sub-agent calls (Prompt AI, Program AI, Signal AI, Attribution AI)
"""

import json
import logging
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta

import requests
from sqlalchemy.orm import Session
from sqlalchemy import text, func

from database.models import SystemConfig
from services.hyper_ai_subagents import SUBAGENT_TOOLS, execute_subagent_tool
from repositories.strategy_repo import _UNSET as _STRATEGY_UNSET

logger = logging.getLogger(__name__)


# Tool definitions in OpenAI format
# IMPORTANT: When adding/removing/modifying tools, you MUST also update:
#   1. The JSON schema definition below (this list)
#   2. The execute_xxx() implementation function
#   3. The execute_hyper_ai_tool() dispatcher at the bottom of this file
#   4. The system prompt: backend/config/hyper_ai_system_prompt.md (Available Tools section)
HYPER_AI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_system_overview",
            "description": "Get high-level system status: wallets, AI traders, strategies, signal pools, positions.",
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
            "name": "get_wallet_status",
            "description": "Get wallet balance and position summary (read-only, no credentials exposed).",
            "parameters": {
                "type": "object",
                "properties": {
                    "exchange": {
                        "type": "string",
                        "enum": ["hyperliquid", "binance", "all"],
                        "description": "Filter by exchange (default: all)"
                    },
                    "environment": {
                        "type": "string",
                        "enum": ["testnet", "mainnet", "all"],
                        "description": "Filter by environment (default: all)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_api_reference",
            "description": "Get API reference docs for Prompt variables or Program MarketData/Decision APIs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_type": {
                        "type": "string",
                        "enum": ["prompt", "program"],
                        "description": "Document type: prompt (variables) or program (MarketData/Decision API)"
                    },
                    "api_type": {
                        "type": "string",
                        "enum": ["market", "decision", "all"],
                        "description": "For program only: which API docs (default: all)"
                    },
                    "lang": {
                        "type": "string",
                        "enum": ["en", "zh"],
                        "description": "Language (default: en)"
                    }
                },
                "required": ["doc_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_klines",
            "description": "Get K-line/candlestick data for a symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Trading symbol (e.g., BTC, ETH)"},
                    "period": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "4h", "1d"], "description": "K-line period (default: 1h)"},
                    "limit": {"type": "integer", "description": "Number of candles (default: 50, max: 200)"},
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange (default: hyperliquid)"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_regime",
            "description": "Get current market regime classification for a symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Trading symbol"},
                    "period": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "4h", "1d"], "description": "Time period (default: 1h)"},
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange (default: hyperliquid)"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_flow",
            "description": "Get market flow data (CVD, OI, Funding, etc.) for a symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Trading symbol"},
                    "period": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "4h", "1d"], "description": "Time period (default: 1h)"},
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange (default: hyperliquid)"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_logs",
            "description": "Get recent system logs enriched with error registry (severity, exchange relevance, suggestions). Logs marked 'other_exchange' are from an exchange the user doesn't use — deprioritize them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["error", "warning", "all"], "description": "Log level filter (default: error)"},
                    "limit": {"type": "integer", "description": "Max entries (default: 20, max: 50)"},
                    "trader_id": {"type": "integer", "description": "Filter by AI Trader ID"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_contact_config",
            "description": "Get support channel URLs (Twitter, Telegram, GitHub).",
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
            "name": "get_trading_environment",
            "description": "Get current global trading environment (testnet/mainnet). This affects which wallets and data sources are used system-wide.",
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
            "name": "get_watchlist",
            "description": "Get symbol watchlist configuration for all exchanges. Shows which symbols are being monitored for data collection and trading. Also indicates if user is still using default symbols.",
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
            "name": "update_watchlist",
            "description": "Update symbol watchlist for a specific exchange. IMPORTANT: Always call get_watchlist first to show current config and get user confirmation before updating.",
            "parameters": {
                "type": "object",
                "properties": {
                    "exchange": {
                        "type": "string",
                        "enum": ["hyperliquid", "binance"],
                        "description": "Exchange to update watchlist for"
                    },
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of symbols to monitor (e.g., ['BTC', 'ETH', 'SOL']). Max 10 symbols."
                    }
                },
                "required": ["exchange", "symbols"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "diagnose_trader_issues",
            "description": "Check why an AI Trader is not triggering and provide actionable suggestions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trader_id": {"type": "integer", "description": "AI Trader ID to diagnose"}
                },
                "required": ["trader_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_tracked_address",
            "description": "Get private Hyper Insight address detail for a tracked wallet. Returns factual data for recent activity analysis; recent fills are limited and do not represent the wallet's complete all-time trade history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Tracked wallet address to analyze"
                    }
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_tracked_wallets",
            "description": "Get the current Hyper Insight wallet sync status and the tracked wallet addresses currently synced into Hyper Alpha Arena. Use this to see whether Hyper Insight is connected and which wallets are currently available to wallet-tracking signal pools.",
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
            "name": "get_strategy_radar_universe",
            "description": "Get Strategy Radar's currently supported symbol/period/exchange/regime combinations. Call before searching Strategy Radar so unsupported symbols are not inferred.",
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
            "name": "search_strategy_radar",
            "description": "Search current Strategy Radar candidates for a supported symbol and period. Results are quality-filtered strategy ideas, not profitability rankings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Supported trading symbol from get_strategy_radar_universe, e.g. BTC"},
                    "period": {"type": "string", "enum": ["1h", "4h", "1d"], "description": "Radar period (default: 1h)"},
                    "regime": {"type": "string", "description": "Optional requested regime. Omit to use current Radar regime for the symbol/period."},
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Optional exchange filter"},
                    "strategy_type": {"type": "string", "description": "Optional strategy type filter"},
                    "sort_by": {"type": "string", "enum": ["relevance", "quality", "newest"], "description": "Optional sort mode. Default is relevance."},
                    "risk_level": {"type": "string", "enum": ["Low", "Medium", "High"], "description": "Optional risk filter."},
                    "timeframe": {"type": "string", "enum": ["1h", "4h", "1d", "multi"], "description": "Optional card timeframe filter."},
                    "limit": {"type": "integer", "description": "Max results (default: 5, max: 10)"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_signal_pool",
            "description": "Create a signal pool from complete signal configuration. Automatically creates signal definitions and combines them into a pool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_name": {"type": "string", "description": "Display name for the pool"},
                    "symbol": {"type": "string", "description": "Symbol to monitor (e.g., BTC, ETH)"},
                    "signals": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "metric": {"type": "string", "description": "Metric name. Standard: cvd, oi_delta_percent, order_imbalance, taker_volume, price_change, volatility. Factor: factor:<name> (e.g., factor:RSI21, factor:ADX14)."},
                                "operator": {"type": "string", "description": "Comparison operator (greater_than, less_than, etc.). NOT used for taker_volume."},
                                "threshold": {"type": "number", "description": "Threshold value. NOT used for taker_volume."},
                                "time_window": {"type": "string", "description": "Time window (e.g., 5m, 15m, 1h)"},
                                "direction": {"type": "string", "enum": ["buy", "sell", "any"], "description": "taker_volume ONLY: dominant side"},
                                "ratio_threshold": {"type": "number", "description": "taker_volume ONLY: buy/sell ratio multiplier (e.g., 1.5 = 50% more)"},
                                "volume_threshold": {"type": "number", "description": "taker_volume ONLY: minimum total volume in USD"}
                            }
                        },
                        "description": "Array of signal conditions. Standard signals use metric/operator/threshold/time_window. taker_volume uses metric/direction/ratio_threshold/volume_threshold/time_window instead."
                    },
                    "logic": {"type": "string", "enum": ["AND", "OR"], "description": "Logic operator (default: AND)"},
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange (default: hyperliquid)"},
                    "description": {"type": "string", "description": "Optional description for the pool"}
                },
                "required": ["pool_name", "symbol", "signals"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_prompt",
            "description": "Create or update a trading prompt template.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt_id": {"type": "integer", "description": "Prompt ID to update (omit for create)"},
                    "name": {"type": "string", "description": "Display name"},
                    "description": {"type": "string", "description": "Brief description"},
                    "template_text": {"type": "string", "description": "Main prompt content"}
                },
                "required": ["name", "template_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_program",
            "description": "Create or update a trading program.",
            "parameters": {
                "type": "object",
                "properties": {
                    "program_id": {"type": "integer", "description": "Program ID to update (omit for create)"},
                    "name": {"type": "string", "description": "Display name"},
                    "description": {"type": "string", "description": "Brief description"},
                    "code": {"type": "string", "description": "Python strategy code"}
                },
                "required": ["name", "code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_ai_trader",
            "description": "Create a new AI Trader with LLM config. Tests LLM connection before saving. Strategy binding and wallet setup are done separately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Display name for the trader"},
                    "model": {"type": "string", "description": "LLM model name (e.g., gpt-4o, deepseek-v4-flash, claude-3.5-sonnet)"},
                    "base_url": {"type": "string", "description": "LLM API base URL (e.g., https://api.openai.com/v1)"},
                    "api_key": {"type": "string", "description": "LLM API key"}
                },
                "required": ["name", "model", "base_url", "api_key"]
            }
        }
    },
    # --- Query Tools: list resources ---
    {
        "type": "function",
        "function": {
            "name": "list_traders",
            "description": "List all AI Traders with bindings, strategies, wallet and trading status. Pass trader_id to get one trader's full detail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trader_id": {"type": "integer", "description": "Optional: specific AI Trader ID for detail view"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_signal_pools",
            "description": "List all signal pools with IDs, symbols, exchange, and trigger conditions. Pass pool_id to get one pool's full detail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_id": {"type": "integer", "description": "Optional: specific signal pool ID for detail view"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_strategies",
            "description": "List all trading prompts and programs with IDs, names, and binding status. Pass strategy_id + strategy_type to get full content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "integer", "description": "Optional: specific strategy ID for detail view"},
                    "strategy_type": {"type": "string", "enum": ["prompt", "program"], "description": "Required when strategy_id is provided"}
                },
                "required": []
            }
        }
    },
    # --- Binding Tools: assemble components ---
    {
        "type": "function",
        "function": {
            "name": "bind_prompt_to_trader",
            "description": "Bind a prompt template to an AI Trader (one-to-one, replaces existing binding).",
            "parameters": {
                "type": "object",
                "properties": {
                    "trader_id": {"type": "integer", "description": "AI Trader ID"},
                    "prompt_id": {"type": "integer", "description": "Prompt template ID to bind"}
                },
                "required": ["trader_id", "prompt_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bind_program_to_trader",
            "description": "Create a program binding for an AI Trader with trigger config (many-to-many). IMPORTANT: exchange must match signal_pool exchange.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trader_id": {"type": "integer", "description": "AI Trader ID"},
                    "program_id": {"type": "integer", "description": "Trading program ID"},
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange to trade on (REQUIRED). Must match signal_pool exchange."},
                    "signal_pool_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Signal pool IDs for triggering. Their exchange must match the binding exchange."
                    },
                    "trigger_interval": {"type": "integer", "description": "Scheduled trigger interval in seconds (default: 300)"},
                    "is_active": {"type": "boolean", "description": "Whether binding is active (default: true)"}
                },
                "required": ["trader_id", "program_id", "exchange"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_trader_strategy",
            "description": "Update trigger configuration for a Prompt-based AI Trader (signal pools, scheduled trigger, interval, exchange).",
            "parameters": {
                "type": "object",
                "properties": {
                    "trader_id": {"type": "integer", "description": "AI Trader ID"},
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Target exchange. MUST match the trader's wallet exchange."},
                    "signal_pool_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Signal pool IDs to bind. Omit this field entirely to leave the trader's current signal pool bindings unchanged (e.g. when only updating trigger_interval or exchange). Pass an empty array [] to explicitly unbind all signal pools."
                    },
                    "scheduled_trigger_enabled": {"type": "boolean", "description": "Enable scheduled trigger"},
                    "trigger_interval": {"type": "integer", "description": "Trigger interval in seconds"}
                },
                "required": ["trader_id"]
            }
        }
    },
    # --- Update Tools ---
    {
        "type": "function",
        "function": {
            "name": "update_ai_trader",
            "description": "Update AI Trader settings (name, LLM config). Tests LLM connection if model/base_url/api_key changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trader_id": {"type": "integer", "description": "AI Trader ID"},
                    "name": {"type": "string", "description": "New display name"},
                    "model": {"type": "string", "description": "New LLM model name"},
                    "base_url": {"type": "string", "description": "New LLM API base URL"},
                    "api_key": {"type": "string", "description": "New LLM API key"}
                },
                "required": ["trader_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_program_binding",
            "description": "Update a program binding's configuration (signal pools, trigger interval, activation, params).",
            "parameters": {
                "type": "object",
                "properties": {
                    "binding_id": {"type": "integer", "description": "Program binding ID"},
                    "signal_pool_ids": {"type": "array", "items": {"type": "integer"}, "description": "New signal pool IDs"},
                    "trigger_interval": {"type": "integer", "description": "New trigger interval in seconds"},
                    "scheduled_trigger_enabled": {"type": "boolean", "description": "Enable/disable scheduled trigger"},
                    "is_active": {"type": "boolean", "description": "Activate or deactivate the binding"},
                    "params_override": {"type": "object", "description": "Parameter overrides for the program"}
                },
                "required": ["binding_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_signal_pool",
            "description": "Update signal pool settings (name, enabled, logic, signal_ids). Signal IDs must belong to the same exchange as the pool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_id": {"type": "integer", "description": "Signal pool ID"},
                    "pool_name": {"type": "string", "description": "New display name"},
                    "enabled": {"type": "boolean", "description": "Enable or disable the pool"},
                    "logic": {"type": "string", "enum": ["AND", "OR"], "description": "Logic operator"},
                    "signal_ids": {"type": "array", "items": {"type": "integer"}, "description": "Replace signal definitions in this pool. All signals must match the pool's exchange."}
                },
                "required": ["pool_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_prompt_binding",
            "description": "Update which prompt template is bound to an AI Trader. Replaces the current binding.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trader_id": {"type": "integer", "description": "AI Trader ID"},
                    "prompt_id": {"type": "integer", "description": "New prompt template ID to bind"}
                },
                "required": ["trader_id", "prompt_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save or update long-term memory with intelligent deduplication. The system automatically compares against existing memories and decides to ADD, UPDATE (merge/replace), or SKIP. To update an existing memory, just call this with the corrected content — the old version will be replaced automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["preference", "decision", "lesson", "insight", "context"],
                        "description": "Memory category: preference (trading style/risk), decision (config changes), lesson (from wins/losses), insight (market patterns), context (general)"
                    },
                    "content": {
                        "type": "string",
                        "description": "Concise, self-contained memory content. Should be understandable without conversation context."
                    },
                    "importance": {
                        "type": "number",
                        "description": "Importance score 0.0-1.0. Default 0.5. Use 0.7+ for key lessons/preferences, 0.3 for minor context."
                    }
                },
                "required": ["category", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_trader",
            "description": "Soft-delete an AI Trader. Checks for bindings and open positions first. Returns dependency list if blocked.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trader_id": {"type": "integer", "description": "AI Trader ID to delete"}
                },
                "required": ["trader_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_prompt_template",
            "description": "Soft-delete a Prompt Template. Checks for active bindings first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt_id": {"type": "integer", "description": "Prompt Template ID to delete"}
                },
                "required": ["prompt_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_signal_definition",
            "description": "Soft-delete a Signal Definition. Checks for signal pool references first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "signal_id": {"type": "integer", "description": "Signal Definition ID to delete"}
                },
                "required": ["signal_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_signal_pool",
            "description": "Soft-delete a Signal Pool. Checks for strategy and program binding references first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_id": {"type": "integer", "description": "Signal Pool ID to delete"}
                },
                "required": ["pool_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_trading_program",
            "description": "Soft-delete a Trading Program. Checks for active bindings first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "program_id": {"type": "integer", "description": "Trading Program ID to delete"}
                },
                "required": ["program_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_prompt_binding",
            "description": "Soft-delete a Prompt Binding (unbind prompt from trader).",
            "parameters": {
                "type": "object",
                "properties": {
                    "binding_id": {"type": "integer", "description": "Prompt Binding ID to delete"}
                },
                "required": ["binding_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_program_binding",
            "description": "Soft-delete a Program Binding. Must be deactivated (is_active=false) first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "binding_id": {"type": "integer", "description": "Program Binding ID to delete"}
                },
                "required": ["binding_id"]
            }
        }
    },
    # --- Factor System Tools ---
    {
        "type": "function",
        "function": {
            "name": "query_factors",
            "description": "Query factor library and effectiveness data. Without symbol: returns factor list. With symbol: returns factor values and effectiveness ranking. Fields: decay_half_life_hours (spatial dimension): positive=half-life in hours (IC decays across forward periods), -1=persistent (IC holds across periods). ic_7d: average IC over recent 7 days. ic_trend (temporal dimension): ic_7d / ic_30d ratio, >1 = factor strengthening recently, <1 = weakening, helps detect if factor is losing effectiveness over time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange (required)"},
                    "symbol": {"type": "string", "description": "Trading symbol (e.g., BTC). If omitted, returns factor library list."},
                    "factor_name": {"type": "string", "description": "Specific factor name for detailed info + history"},
                    "forward_period": {"type": "string", "enum": ["1h", "4h", "12h", "24h"], "description": "Forward period for effectiveness (default: 4h)"},
                    "days": {"type": "integer", "description": "Number of days of history to return when querying a specific factor (default: 30, max: 365). Use larger values for long-term trend analysis."}
                },
                "required": ["exchange"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_factor",
            "description": "Evaluate a custom factor expression against real market data. Returns syntax validation, latest value, and IC/ICIR/win_rate for each forward period.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Factor expression (e.g., 'EMA(close, 7) / EMA(close, 21) - 1')"},
                    "symbol": {"type": "string", "description": "Trading symbol (e.g., BTC)"},
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange (required)"}
                },
                "required": ["expression", "symbol", "exchange"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_factor",
            "description": "Save a custom factor expression to the factor library.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Factor name (unique, descriptive)"},
                    "expression": {"type": "string", "description": "Factor expression"},
                    "description": {"type": "string", "description": "Brief description of what the factor measures"}
                },
                "required": ["name", "expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_factor",
            "description": "Edit an existing custom factor. Only custom factors can be edited, not built-in ones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "factor_id": {"type": "integer", "description": "Custom factor ID (required)"},
                    "name": {"type": "string", "description": "New name (optional)"},
                    "expression": {"type": "string", "description": "New expression (optional)"},
                    "description": {"type": "string", "description": "New description (optional)"}
                },
                "required": ["factor_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compute_factor",
            "description": "Run computation for a specific factor across all watchlist symbols on an exchange. Updates factor values and effectiveness metrics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "factor_name": {"type": "string", "description": "Factor name to compute"},
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange (required)"}
                },
                "required": ["factor_name", "exchange"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_factor_functions",
            "description": "Get the full list of supported factor expression functions, grouped by category. Call this BEFORE designing or modifying factor expressions, so you know exactly which functions are available and their signatures.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category (optional). Leave empty for all categories."
                    }
                },
                "required": []
            }
        }
    }
]

# --- External Tools (require user-provided API keys) ---
EXTERNAL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for quant research, market news, factor ideas, or any external information. Use when user asks about recent events, research papers, trading strategies from the internet, or when you need external knowledge to design factors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (English recommended for better results)"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max number of results (default 5, max 10)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch the full content of a web page and convert it to clean Markdown text. Use AFTER web_search to retrieve detailed content from a specific URL found in search results. Supports HTML pages, blog posts, documentation, and GitHub files. For academic papers, fetch the abstract page rather than the PDF directly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch content from"
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum content length in characters (default 8000, max 15000)",
                        "default": 8000
                    }
                },
                "required": ["url"]
            }
        }
    }
]

# --- Skill System Tools ---
# These tools load workflow guidance into the AI's context (Level 2 & 3 loading).
# They do NOT perform any actions — they provide step-by-step instructions
# for the AI to follow when executing complex multi-step tasks.
# See backend/skills/*/SKILL.md for skill definitions.
SKILL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "Load a skill workflow guide into your context. This does NOT perform any action — it provides you with step-by-step instructions for a specific task type. Use this when a user's request matches one of your available skills.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill to load (e.g., 'prompt-strategy-setup', 'trader-diagnosis')"
                    }
                },
                "required": ["skill_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill_reference",
            "description": "Load a reference document from a skill's references/ directory. Use this when a loaded skill mentions additional reference materials you should consult.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill"
                    },
                    "reference_file": {
                        "type": "string",
                        "description": "Filename of the reference document (e.g., 'signal-design-guide.md')"
                    }
                },
                "required": ["skill_name", "reference_file"]
            }
        }
    }
]

# Combine base tools + external tools + skill tools + sub-agent tools
HYPER_AI_TOOLS = HYPER_AI_TOOLS + EXTERNAL_TOOLS + SKILL_TOOLS + SUBAGENT_TOOLS


# =============================================================================
# Tool Execution Functions
# =============================================================================

def execute_get_system_overview(db: Session) -> str:
    """Get high-level system status summary."""
    from database.models import (
        Account, HyperliquidWallet, BinanceWallet, PromptTemplate,
        TradingProgram, SignalPool, AccountPromptBinding, AccountProgramBinding,
        HyperliquidPosition
    )

    try:
        result = {
            "wallets": {"hyperliquid": {}, "binance": {}},
            "ai_traders": {"total": 0, "active": 0, "using_prompt": 0, "using_program": 0},
            "strategies": {"prompts": 0, "programs": 0},
            "signal_pools": {"hyperliquid": 0, "binance": 0},
            "open_positions": {}
        }

        # Count wallets by exchange and environment
        hl_wallets = db.query(
            HyperliquidWallet.environment, func.count(HyperliquidWallet.id)
        ).filter(HyperliquidWallet.is_active == "true").group_by(HyperliquidWallet.environment).all()
        for env, count in hl_wallets:
            result["wallets"]["hyperliquid"][env] = count

        bn_wallets = db.query(
            BinanceWallet.environment, func.count(BinanceWallet.id)
        ).filter(BinanceWallet.is_active == "true").group_by(BinanceWallet.environment).all()
        for env, count in bn_wallets:
            result["wallets"]["binance"][env] = count

        # Count AI Traders
        total_traders = db.query(Account).filter(Account.is_active == "true", Account.is_deleted != True).count()
        active_traders = db.query(Account).filter(
            Account.is_active == "true",
            Account.auto_trading_enabled == "true",
            Account.is_deleted != True
        ).count()
        result["ai_traders"]["total"] = total_traders
        result["ai_traders"]["active"] = active_traders

        # Count by strategy type
        prompt_bindings = db.query(AccountPromptBinding).filter(AccountPromptBinding.is_deleted != True).count()
        program_bindings = db.query(AccountProgramBinding).filter(
            AccountProgramBinding.is_active == True,
            AccountProgramBinding.is_deleted != True
        ).count()
        result["ai_traders"]["using_prompt"] = prompt_bindings
        result["ai_traders"]["using_program"] = program_bindings

        # Count strategies
        user_prompts = db.query(PromptTemplate).filter(
            PromptTemplate.is_system == "false",
            PromptTemplate.is_deleted == "false"
        ).count()
        programs = db.query(TradingProgram).filter(TradingProgram.is_deleted != True).count()
        result["strategies"]["prompts"] = user_prompts
        result["strategies"]["programs"] = programs

        # Count signal pools by exchange
        pools = db.query(
            SignalPool.exchange, func.count(SignalPool.id)
        ).filter(SignalPool.enabled == True, SignalPool.is_deleted != True).group_by(SignalPool.exchange).all()
        for exchange, count in pools:
            result["signal_pools"][exchange or "hyperliquid"] = count

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"[get_system_overview] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_wallet_status(db: Session, exchange: str = "all", environment: str = "all") -> str:
    """Get wallet balance and position summary using real-time API (same as frontend)."""
    from database.models import HyperliquidWallet, BinanceWallet, Account
    from services.hyperliquid_environment import get_hyperliquid_client
    from services.binance_trading_client import BinanceTradingClient
    from utils.encryption import decrypt_private_key

    try:
        wallets = []

        # Query Hyperliquid wallets - use real-time API
        if exchange in ["all", "hyperliquid"]:
            hl_query = db.query(HyperliquidWallet, Account).join(
                Account, HyperliquidWallet.account_id == Account.id
            ).filter(HyperliquidWallet.is_active == "true")

            if environment != "all":
                hl_query = hl_query.filter(HyperliquidWallet.environment == environment)

            for wallet, account in hl_query.all():
                try:
                    # Use get_hyperliquid_client to support API Wallet mode
                    client = get_hyperliquid_client(db, account.id, override_environment=wallet.environment)
                    account_state = client.get_account_state(db)

                    wallet_info = {
                        "exchange": "hyperliquid",
                        "environment": wallet.environment,
                        "wallet_address": wallet.wallet_address[:10] + "..." + wallet.wallet_address[-6:],
                        "trader_id": account.id,
                        "trader_name": account.name,
                        "balance": {
                            "total_equity": float(account_state.get("total_equity", 0)),
                            "available_balance": float(account_state.get("available_balance", 0)),
                            "used_margin": float(account_state.get("used_margin", 0))
                        },
                        "positions": [],
                        "last_updated": "real-time"
                    }

                    # Get positions from API response
                    for pos in account_state.get("positions", []):
                        szi = float(pos.get("szi", 0) or 0)
                        if szi != 0:
                            wallet_info["positions"].append({
                                "symbol": pos.get("coin", ""),
                                "size": abs(szi),
                                "side": "long" if szi > 0 else "short",
                                "unrealized_pnl": float(pos.get("unrealized_pnl", 0) or 0)
                            })

                    wallets.append(wallet_info)
                except Exception as e:
                    logger.warning(f"[get_wallet_status] Failed to get Hyperliquid data for {account.name}: {e}")
                    wallets.append({
                        "exchange": "hyperliquid",
                        "environment": wallet.environment,
                        "wallet_address": wallet.wallet_address[:10] + "..." + wallet.wallet_address[-6:],
                        "trader_id": account.id,
                        "trader_name": account.name,
                        "balance": {"total_equity": 0, "available_balance": 0, "used_margin": 0},
                        "positions": [],
                        "error": str(e)
                    })

        # Query Binance wallets - use real-time API
        if exchange in ["all", "binance"]:
            bn_query = db.query(BinanceWallet, Account).join(
                Account, BinanceWallet.account_id == Account.id
            ).filter(BinanceWallet.is_active == "true")

            if environment != "all":
                bn_query = bn_query.filter(BinanceWallet.environment == environment)

            for wallet, account in bn_query.all():
                try:
                    # Decrypt API keys
                    api_key = decrypt_private_key(wallet.api_key_encrypted)
                    secret_key = decrypt_private_key(wallet.secret_key_encrypted)
                    client = BinanceTradingClient(api_key, secret_key, wallet.environment)
                    balance = client.get_balance()

                    wallet_info = {
                        "exchange": "binance",
                        "environment": wallet.environment,
                        "trader_id": account.id,
                        "trader_name": account.name,
                        "balance": {
                            "total_equity": float(balance.get("total_equity", 0)),
                            "available_balance": float(balance.get("available_balance", 0)),
                            "unrealized_pnl": float(balance.get("unrealized_pnl", 0))
                        },
                        "positions": [],
                        "last_updated": "real-time"
                    }
                    wallets.append(wallet_info)
                except Exception as e:
                    logger.warning(f"[get_wallet_status] Failed to get Binance data for {account.name}: {e}")
                    wallets.append({
                        "exchange": "binance",
                        "environment": wallet.environment,
                        "trader_id": account.id,
                        "trader_name": account.name,
                        "balance": {"total_equity": 0, "available_balance": 0, "unrealized_pnl": 0},
                        "positions": [],
                        "error": str(e)
                    })

        return json.dumps({"wallets": wallets}, indent=2)

    except Exception as e:
        logger.error(f"[get_wallet_status] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_api_reference(doc_type: str, api_type: str = "all", lang: str = "en") -> str:
    """Get API reference documentation."""
    try:
        if doc_type == "prompt":
            # Read prompt variables reference document
            filename = "PROMPT_VARIABLES_REFERENCE_ZH.md" if lang == "zh" else "PROMPT_VARIABLES_REFERENCE.md"
            doc_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", filename)

            try:
                with open(doc_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return json.dumps({"doc_type": "prompt", "lang": lang, "content": content})
            except FileNotFoundError:
                return json.dumps({"error": f"Document not found: {filename}"})

        elif doc_type == "program":
            # Return MarketData/Decision API docs from ai_program_service
            from services.ai_program_service import MARKET_API_DOCS, DECISION_API_DOCS

            if api_type == "market":
                content = MARKET_API_DOCS
            elif api_type == "decision":
                content = DECISION_API_DOCS
            else:
                content = MARKET_API_DOCS + "\n\n" + DECISION_API_DOCS

            return json.dumps({"doc_type": "program", "api_type": api_type, "content": content})

        else:
            return json.dumps({"error": f"Invalid doc_type: {doc_type}"})

    except Exception as e:
        logger.error(f"[get_api_reference] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_klines(db: Session, symbol: str, period: str = "1h", limit: int = 50, exchange: str = "hyperliquid") -> str:
    """Get K-line data for a symbol."""
    from database.models import CryptoKline

    try:
        limit = min(max(limit, 1), 200)

        klines = db.query(CryptoKline).filter(
            CryptoKline.exchange == exchange,
            CryptoKline.symbol == symbol.upper(),
            CryptoKline.period == period,
            CryptoKline.environment == "mainnet"
        ).order_by(CryptoKline.timestamp.desc()).limit(limit).all()

        candles = []
        for k in reversed(klines):
            candles.append({
                "time": datetime.utcfromtimestamp(k.timestamp).strftime("%Y-%m-%d %H:%M UTC"),
                "open": float(k.open_price) if k.open_price else 0,
                "high": float(k.high_price) if k.high_price else 0,
                "low": float(k.low_price) if k.low_price else 0,
                "close": float(k.close_price) if k.close_price else 0,
                "volume": float(k.volume) if k.volume else 0
            })

        return json.dumps({
            "symbol": symbol.upper(),
            "period": period,
            "exchange": exchange,
            "candles": candles,
            "count": len(candles)
        }, indent=2)

    except Exception as e:
        logger.error(f"[get_klines] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_market_regime(db: Session, symbol: str, period: str = "1h", exchange: str = "hyperliquid") -> str:
    """Get market regime classification for a symbol."""
    try:
        from program_trader.data_provider import DataProvider

        data_provider = DataProvider(db=db, account_id=0, environment="mainnet", exchange=exchange)
        regime = data_provider.get_regime(symbol.upper(), period)

        if regime:
            return json.dumps({
                "symbol": symbol.upper(),
                "period": period,
                "exchange": exchange,
                "regime": regime.regime,
                "confidence": regime.conf
            }, indent=2)
        else:
            return json.dumps({
                "symbol": symbol.upper(),
                "period": period,
                "exchange": exchange,
                "regime": "unknown",
                "confidence": 0,
                "note": "Unable to determine market regime"
            })

    except Exception as e:
        logger.error(f"[get_market_regime] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_market_flow(db: Session, symbol: str, period: str = "1h", exchange: str = "hyperliquid") -> str:
    """Get market flow data for a symbol."""
    try:
        from program_trader.data_provider import DataProvider

        data_provider = DataProvider(db=db, account_id=0, environment="mainnet", exchange=exchange)

        flow = {}
        for metric in ["CVD", "OI", "OI_DELTA", "TAKER", "FUNDING"]:
            result = data_provider.get_flow(symbol.upper(), metric, period)
            if result:
                flow[metric] = result

        return json.dumps({
            "symbol": symbol.upper(),
            "period": period,
            "exchange": exchange,
            "flow": flow
        }, indent=2)

    except Exception as e:
        logger.error(f"[get_market_flow] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_system_logs(db: Session, level: str = "error", limit: int = 20, trader_id: int = None) -> str:
    """Get recent system logs enriched with error registry metadata."""
    from services.system_logger import system_logger
    from services.error_registry import classify_error, get_severity_summary

    try:
        limit = min(max(limit, 1), 50)

        # Map level to min_level for system_logger
        min_level = None
        if level == "error":
            min_level = "ERROR"
        elif level == "warning":
            min_level = "WARNING"

        raw_logs = system_logger.get_logs(limit=limit, min_level=min_level)

        # Determine user's exchange from their wallets
        user_exchange = None
        try:
            from database.models import Account, HyperliquidWallet
            account = db.query(Account).first()
            if account:
                has_hl = db.query(HyperliquidWallet).filter(
                    HyperliquidWallet.account_id == account.id
                ).first() is not None
                has_bn = False
                try:
                    from database.models import BinanceWallet
                    has_bn = db.query(BinanceWallet).filter(
                        BinanceWallet.account_id == account.id
                    ).first() is not None
                except Exception:
                    pass
                if has_hl and not has_bn:
                    user_exchange = "hyperliquid"
                elif has_bn and not has_hl:
                    user_exchange = "binance"
        except Exception:
            pass

        # Enrich logs with registry metadata
        logs = []
        for log in raw_logs:
            msg = log.get("message", "")
            entry = {
                "time": log.get("timestamp", ""),
                "level": log.get("level", "INFO"),
                "category": log.get("category", ""),
                "message": msg,
            }
            match = classify_error(msg)
            if match:
                entry["registry"] = match
                # Mark irrelevant exchange errors
                if user_exchange and match["exchange"] not in ("all", user_exchange):
                    entry["registry"]["relevance"] = "other_exchange"
            logs.append(entry)

        # Build severity summary
        severity_counts = {"CRITICAL": 0, "WARNING": 0, "INFO": 0, "NOISE": 0, "UNKNOWN": 0}
        for log in logs:
            reg = log.get("registry")
            sev = reg["severity"] if reg else "UNKNOWN"
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        result = {
            "logs": logs,
            "total": len(logs),
            "severity_summary": severity_counts,
        }
        if user_exchange:
            result["user_exchange"] = user_exchange

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"[get_system_logs] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_contact_config() -> str:
    """Get support channel URLs."""
    import requests

    try:
        # Try to fetch from external API
        resp = requests.get("https://www.akooi.com/api/config/contact", timeout=5)
        if resp.status_code == 200:
            return json.dumps(resp.json(), indent=2)
    except Exception as e:
        logger.warning(f"[get_contact_config] Failed to fetch from API: {e}")

    # Fallback to defaults
    return json.dumps({
        "twitter": {"url": "https://x.com/GptHammer3309", "enabled": True},
        "telegram": {"url": "https://t.me/+RqxjT7Gttm9hOGEx", "enabled": True},
        "github": {"url": "https://github.com/HammerGPT/Hyper-Alpha-Arena", "enabled": True}
    }, indent=2)


def execute_get_trading_environment(db: Session) -> str:
    """Get current global trading environment."""
    from services.hyperliquid_environment import get_global_trading_mode

    try:
        environment = get_global_trading_mode(db)
        return json.dumps({
            "current_environment": environment,
            "description": "testnet" if environment == "testnet" else "mainnet (real money)",
            "note": "Environment affects which wallets are used and which exchange endpoints are called. To switch, use the mode switcher in the top-right of the UI."
        }, indent=2)
    except Exception as e:
        logger.error(f"[get_trading_environment] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_watchlist(db: Session) -> str:
    """Get symbol watchlist for all exchanges."""
    from services import hyperliquid_symbol_service, binance_symbol_service

    try:
        # Get Hyperliquid watchlist
        hl_selected = hyperliquid_symbol_service.get_selected_symbols()
        hl_default = [s["symbol"] for s in hyperliquid_symbol_service.DEFAULT_SYMBOLS]
        hl_is_default = set(hl_selected) == set(hl_default)

        # Get Binance watchlist
        bn_selected = binance_symbol_service.get_selected_symbols()
        bn_default = [s["symbol"] for s in binance_symbol_service.DEFAULT_SYMBOLS]
        bn_is_default = set(bn_selected) == set(bn_default)

        result = {
            "hyperliquid": {
                "symbols": hl_selected,
                "is_default_config": hl_is_default,
                "default_symbols": hl_default,
                "max_symbols": hyperliquid_symbol_service.MAX_WATCHLIST_SYMBOLS
            },
            "binance": {
                "symbols": bn_selected,
                "is_default_config": bn_is_default,
                "default_symbols": bn_default,
                "max_symbols": binance_symbol_service.MAX_WATCHLIST_SYMBOLS
            },
            "note": "Watchlist determines which symbols the system collects data for (K-lines, OI, CVD, funding). If you want to trade a symbol, it must be in the watchlist first."
        }

        # Add warning if using defaults
        warnings = []
        if hl_is_default:
            warnings.append("Hyperliquid watchlist is using default config (only BTC). Consider adding symbols you want to trade.")
        if bn_is_default:
            warnings.append("Binance watchlist is using default config (only BTC). Consider adding symbols you want to trade.")
        if warnings:
            result["warnings"] = warnings

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"[get_watchlist] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_update_watchlist(db: Session, exchange: str, symbols: List[str]) -> str:
    """Update symbol watchlist for a specific exchange."""
    from services import hyperliquid_symbol_service, binance_symbol_service

    try:
        if exchange not in ["hyperliquid", "binance"]:
            return json.dumps({"error": "exchange must be 'hyperliquid' or 'binance'"})

        if not symbols or not isinstance(symbols, list):
            return json.dumps({"error": "symbols must be a non-empty list"})

        # Normalize symbols to uppercase
        symbols = [s.upper() for s in symbols]

        if exchange == "hyperliquid":
            updated = hyperliquid_symbol_service.update_selected_symbols(symbols)
        else:
            updated = binance_symbol_service.update_selected_symbols(symbols)

        return json.dumps({
            "success": True,
            "exchange": exchange,
            "updated_symbols": updated,
            "note": "Watchlist updated. Data collection will now include these symbols. It may take a few minutes for historical data to be backfilled."
        }, indent=2)

    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"[update_watchlist] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_diagnose_trader_issues(db: Session, trader_id: int) -> str:
    """Diagnose why an AI Trader is not triggering."""
    from database.models import (
        Account, HyperliquidWallet, BinanceWallet, AccountPromptBinding,
        AccountProgramBinding, AccountStrategyConfig, SignalPool,
        HyperliquidAccountSnapshot, BinanceAccountSnapshot, AIDecisionLog, ProgramExecutionLog
    )

    try:
        # Get account
        account = db.query(Account).filter(Account.id == trader_id, Account.is_deleted != True).first()
        if not account:
            return json.dumps({"error": f"AI Trader with id {trader_id} not found"})

        checks = []
        issues = []

        # Check 1: Trader enabled
        trader_enabled = account.is_active == "true"
        checks.append({"check": "trader_enabled", "passed": trader_enabled})
        if not trader_enabled:
            issues.append("AI Trader is disabled")

        # Check 2: Auto trading enabled
        auto_enabled = account.auto_trading_enabled == "true"
        checks.append({"check": "auto_trading_enabled", "passed": auto_enabled})
        if not auto_enabled:
            issues.append("Auto trading is disabled")

        # Check 3: Strategy bound
        prompt_binding = db.query(AccountPromptBinding).filter(
            AccountPromptBinding.account_id == trader_id,
            AccountPromptBinding.is_deleted != True
        ).first()
        program_binding = db.query(AccountProgramBinding).filter(
            AccountProgramBinding.account_id == trader_id,
            AccountProgramBinding.is_active == True,
            AccountProgramBinding.is_deleted != True
        ).first()

        strategy_bound = prompt_binding is not None or program_binding is not None
        strategy_type = "prompt" if prompt_binding else ("program" if program_binding else None)
        checks.append({"check": "strategy_bound", "passed": strategy_bound, "type": strategy_type})
        if not strategy_bound:
            issues.append("No strategy (prompt or program) bound to this trader")

        # Check 4: Wallet bound and has balance
        strategy_config = db.query(AccountStrategyConfig).filter(
            AccountStrategyConfig.account_id == trader_id
        ).first()

        exchange = strategy_config.exchange if strategy_config else "hyperliquid"
        wallet_bound = False
        wallet_balance = 0
        wallet_env = None

        if exchange == "hyperliquid":
            wallet = db.query(HyperliquidWallet).filter(
                HyperliquidWallet.account_id == trader_id,
                HyperliquidWallet.is_active == "true"
            ).first()
            if wallet:
                wallet_bound = True
                wallet_env = wallet.environment
                snapshot = db.query(HyperliquidAccountSnapshot).filter(
                    HyperliquidAccountSnapshot.account_id == trader_id,
                    HyperliquidAccountSnapshot.environment == wallet.environment
                ).order_by(HyperliquidAccountSnapshot.snapshot_time.desc()).first()
                if snapshot:
                    wallet_balance = float(snapshot.available_balance)
        else:
            wallet = db.query(BinanceWallet).filter(
                BinanceWallet.account_id == trader_id,
                BinanceWallet.is_active == "true"
            ).first()
            if wallet:
                wallet_bound = True
                wallet_env = wallet.environment
                snapshot = db.query(BinanceAccountSnapshot).filter(
                    BinanceAccountSnapshot.account_id == trader_id,
                    BinanceAccountSnapshot.environment == wallet.environment
                ).order_by(BinanceAccountSnapshot.snapshot_time.desc()).first()
                if snapshot:
                    wallet_balance = float(snapshot.available_balance)

        checks.append({
            "check": "wallet_bound",
            "passed": wallet_bound,
            "wallet": f"{exchange}/{wallet_env}" if wallet_bound else None
        })
        if not wallet_bound:
            issues.append(f"No {exchange} wallet bound. Go to Settings → Wallets to configure.")

        checks.append({
            "check": "wallet_balance",
            "passed": wallet_balance > 0,
            "balance": wallet_balance,
            "suggestion": "Deposit funds to wallet" if wallet_balance == 0 else None
        })
        if wallet_balance == 0 and wallet_bound:
            issues.append("Wallet balance is 0. Deposit funds to enable trading.")

        # Check 5: Signal pool or scheduled trigger
        if strategy_config:
            has_signal = bool(strategy_config.signal_pool_ids)
            has_scheduled = strategy_config.scheduled_trigger_enabled
            checks.append({
                "check": "trigger_configured",
                "passed": has_signal or has_scheduled,
                "signal_pools": strategy_config.signal_pool_ids,
                "scheduled_enabled": has_scheduled,
                "interval": strategy_config.trigger_interval
            })
            if not has_signal and not has_scheduled:
                issues.append("No trigger configured (neither signal pool nor scheduled)")

        # Check 6: Recent errors
        recent_errors = []
        ai_errors = db.query(AIDecisionLog).filter(
            AIDecisionLog.account_id == trader_id,
            AIDecisionLog.executed == "false"
        ).order_by(AIDecisionLog.decision_time.desc()).limit(3).all()

        for err in ai_errors:
            recent_errors.append({
                "time": err.decision_time.strftime("%Y-%m-%d %H:%M UTC") if err.decision_time else None,
                "type": "ai_decision",
                "message": err.reason[:100] if err.reason else "Unknown"
            })

        status = "healthy" if not issues else "issues_found"
        summary = issues[0] if issues else "All checks passed. Trader should be operational."

        return json.dumps({
            "trader_id": trader_id,
            "trader_name": account.name,
            "status": status,
            "checks": checks,
            "summary": summary,
            "recent_errors": recent_errors
        }, indent=2)

    except Exception as e:
        logger.error(f"[diagnose_trader_issues] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_save_signal_pool(
    db: Session,
    pool_name: str,
    symbol: str,
    signals: List[Dict[str, Any]],
    logic: str = "AND",
    exchange: str = "hyperliquid",
    description: str = None
) -> str:
    """Create a signal pool by calling the existing API handler."""
    from api.signal_routes import create_pool_from_config, SignalPoolConfigRequest

    try:
        # Defensive validation for taker_volume signals
        for i, sig in enumerate(signals):
            if sig.get("metric") == "taker_volume":
                missing = [f for f in ("direction", "ratio_threshold", "volume_threshold", "time_window")
                           if not sig.get(f) and sig.get(f) != 0]
                if missing or sig.get("operator"):
                    return json.dumps({
                        "error": f"Signal {i+1} (taker_volume) format error. "
                                 f"taker_volume requires: direction, ratio_threshold, volume_threshold, time_window. "
                                 f"Do NOT use operator/threshold for taker_volume.",
                        "correct_example": {
                            "metric": "taker_volume", "direction": "buy",
                            "ratio_threshold": 1.5, "volume_threshold": 100000, "time_window": "5m"
                        }
                    })

        # Build request object for the existing API handler
        request = SignalPoolConfigRequest(
            name=pool_name,
            symbol=symbol,
            signals=signals,
            logic=logic,
            exchange=exchange,
            description=description
        )

        # Call the existing API handler directly
        result = create_pool_from_config(request, db)

        return json.dumps({
            "success": True,
            "pool_id": result["pool"]["id"],
            "pool_name": result["pool"]["pool_name"],
            "symbol": symbol.upper(),
            "signals_created": len(result["signals"]),
            "signals": signals,
            "logic": logic,
            "exchange": exchange,
            "view_url": f"/#signal-management?view={result['pool']['id']}",
            "note": "Signal pool created. Bind it to an AI Trader to start receiving triggers."
        })

    except Exception as e:
        db.rollback()
        logger.error(f"[save_signal_pool] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_save_prompt(
    db: Session,
    name: str,
    template_text: str,
    prompt_id: int = None,
    description: str = None
) -> str:
    """Create or update a trading prompt template."""
    from database.models import PromptTemplate
    import re

    try:
        # Extract variables from template
        variables = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', template_text)
        variables = list(set(variables))

        if prompt_id:
            # Update existing prompt
            prompt = db.query(PromptTemplate).filter(
                PromptTemplate.id == prompt_id,
                PromptTemplate.is_deleted == "false"
            ).first()
            if not prompt:
                return json.dumps({"error": f"Prompt {prompt_id} not found"})

            prompt.name = name
            prompt.template_text = template_text
            if description:
                prompt.description = description
            prompt.updated_by = "hyper_ai"
            db.commit()
            action = "updated"
        else:
            # Create new prompt
            # Generate unique key
            import uuid
            key = f"hyper_ai_{uuid.uuid4().hex[:8]}"

            # Get default system template
            default_system = db.query(PromptTemplate).filter(
                PromptTemplate.is_system == "true"
            ).first()
            system_text = default_system.system_template_text if default_system else ""

            prompt = PromptTemplate(
                key=key,
                name=name,
                description=description or "",
                template_text=template_text,
                system_template_text=system_text,
                is_system="false",
                is_deleted="false",
                created_by="hyper_ai"
            )
            db.add(prompt)
            db.commit()
            db.refresh(prompt)
            action = "created"

        return json.dumps({
            "success": True,
            "prompt_id": prompt.id,
            "name": name,
            "action": action,
            "variables_detected": variables[:20],
            "template_text": template_text,
            "view_url": f"/#prompt-management?view={prompt.id}",
            "note": "Prompt saved. Changes apply to bound AI Traders on next trigger."
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[save_prompt] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_save_program(
    db: Session,
    name: str,
    code: str,
    program_id: int = None,
    description: str = None
) -> str:
    """Create or update a trading program by calling existing API handlers."""
    from routes.program_routes import (
        create_program, update_program, ProgramCreate, ProgramUpdate
    )
    from fastapi import HTTPException

    try:
        if program_id:
            # Update existing program
            data = ProgramUpdate(name=name, code=code, description=description)
            result = update_program(program_id, data, db)
            action = "updated"
        else:
            # Create new program
            data = ProgramCreate(name=name, code=code, description=description)
            result = create_program(data, db)
            action = "created"

        return json.dumps({
            "success": True,
            "program_id": result.id,
            "name": result.name,
            "action": action,
            "code": code,
            "view_url": f"/#program-trader?view={result.id}",
            "validation": {"syntax_valid": True, "security_check": "passed"},
            "note": "Program saved. Use test_run_code to verify logic before binding."
        }, indent=2)

    except HTTPException as e:
        db.rollback()
        logger.error(f"[save_program] HTTPException: {e.detail}")
        return json.dumps({"success": False, "error": e.detail})
    except Exception as e:
        db.rollback()
        logger.error(f"[save_program] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_create_ai_trader(
    db: Session,
    name: str,
    model: str,
    base_url: str,
    api_key: str
) -> str:
    """Create a new AI Trader with LLM config only. Strategy and wallet binding done separately."""
    from database.models import Account

    try:
        # Step 1: Test LLM connection first
        from api.account_routes import test_llm_connection
        import asyncio

        # Create event loop if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        test_result = loop.run_until_complete(test_llm_connection({
            "model": model,
            "base_url": base_url,
            "api_key": api_key
        }))

        if not test_result.get("success"):
            return json.dumps({
                "success": False,
                "error": "LLM connection test failed",
                "details": test_result.get("message", "Unknown error"),
                "note": "Please check your LLM credentials and try again."
            })

        # Step 2: Create Account with LLM config only
        account = Account(
            user_id=1,
            name=name,
            account_type="AI",
            is_active="true",
            auto_trading_enabled="false",  # Disabled until strategy/wallet configured
            model=model,
            base_url=base_url,
            api_key=api_key
        )
        db.add(account)
        db.commit()

        return json.dumps({
            "success": True,
            "trader_id": account.id,
            "trader_name": name,
            "llm_config": {
                "model": model,
                "base_url": base_url,
                "connection_tested": True
            },
            "view_url": f"/#trader-management?view={account.id}",
            "next_steps": [
                "1. Bind a wallet to this trader",
                "2. Create/select a trading strategy",
                "3. Enable auto-trading when ready"
            ],
            "note": "AI Trader created with LLM config. Complete wallet and strategy setup to start trading."
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[create_ai_trader] Error: {e}")
        return json.dumps({"error": str(e)})


# =============================================================================
# Query Tools: list resources
# =============================================================================

def execute_list_traders(db: Session, trader_id: int = None) -> str:
    """List all AI Traders with bindings, wallet status, and trading status.
    Pass trader_id to get a single trader's detail."""
    from database.models import (
        Account, HyperliquidWallet, BinanceWallet,
        AccountProgramBinding, AccountPromptBinding,
        TradingProgram, PromptTemplate
    )

    try:
        query = db.query(Account).filter(
            Account.is_active == "true",
            Account.account_type == "AI",
            Account.is_deleted != True
        )
        if trader_id:
            query = query.filter(Account.id == trader_id)
        accounts = query.all()
        if trader_id and not accounts:
            return json.dumps({"error": f"AI Trader {trader_id} not found"})

        traders = []
        for acc in accounts:
            # Wallet info
            hl_wallets = db.query(HyperliquidWallet).filter(
                HyperliquidWallet.account_id == acc.id
            ).all()
            bn_wallets = db.query(BinanceWallet).filter(
                BinanceWallet.account_id == acc.id
            ).all()

            wallet_info = []
            for w in hl_wallets:
                wallet_info.append({
                    "exchange": "hyperliquid",
                    "environment": w.environment
                })
            for w in bn_wallets:
                wallet_info.append({
                    "exchange": "binance",
                    "environment": w.environment
                })

            # Prompt binding
            prompt_binding = None
            pb = db.query(AccountPromptBinding).filter(
                AccountPromptBinding.account_id == acc.id,
                AccountPromptBinding.is_deleted != True
            ).first()
            if pb:
                tpl = db.get(PromptTemplate, pb.prompt_template_id)
                prompt_binding = {
                    "prompt_id": pb.prompt_template_id,
                    "prompt_name": tpl.name if tpl else "Unknown"
                }

            # Program bindings
            prog_bindings = db.query(AccountProgramBinding).filter(
                AccountProgramBinding.account_id == acc.id,
                AccountProgramBinding.is_deleted != True
            ).all()
            program_bindings = []
            for pgb in prog_bindings:
                prog = db.get(TradingProgram, pgb.program_id)
                pool_ids = json.loads(pgb.signal_pool_ids) if pgb.signal_pool_ids else []
                program_bindings.append({
                    "binding_id": pgb.id,
                    "program_id": pgb.program_id,
                    "program_name": prog.name if prog else "Unknown",
                    "exchange": pgb.exchange or "hyperliquid",
                    "signal_pool_ids": pool_ids,
                    "trigger_interval": pgb.trigger_interval,
                    "is_active": pgb.is_active
                })

            traders.append({
                "trader_id": acc.id,
                "name": acc.name,
                "model": acc.model,
                "auto_trading_enabled": acc.auto_trading_enabled == "true",
                "wallets": wallet_info,
                "prompt_binding": prompt_binding,
                "program_bindings": program_bindings
            })

        return json.dumps({"traders": traders, "count": len(traders)}, indent=2)

    except Exception as e:
        logger.error(f"[list_traders] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_list_signal_pools(db: Session, pool_id: int = None) -> str:
    """List all signal pools. Pass pool_id for single pool detail."""
    from database.models import SignalPool, SignalDefinition

    try:
        query = db.query(SignalPool).filter(SignalPool.is_deleted != True)
        if pool_id:
            query = query.filter(SignalPool.id == pool_id)
        pools = query.all()
        if pool_id and not pools:
            return json.dumps({"error": f"Signal pool {pool_id} not found"})

        result = []
        for pool in pools:
            # Parse signal_ids
            signal_ids = []
            if pool.signal_ids:
                try:
                    raw = pool.signal_ids
                    signal_ids = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    signal_ids = []

            # Parse symbols
            symbols = []
            if pool.symbols:
                try:
                    raw = pool.symbols
                    symbols = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    symbols = []

            source_type = pool.source_type or "market_signals"
            source_config = {}
            if getattr(pool, "source_config", None):
                try:
                    raw = pool.source_config
                    source_config = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    source_config = {}

            # Get signal details from trigger_condition
            signals = []
            for sid in signal_ids:
                sig = db.query(SignalDefinition).filter(
                    SignalDefinition.id == sid,
                    SignalDefinition.is_deleted != True
                ).first()
                if sig:
                    cond = {}
                    if sig.trigger_condition:
                        try:
                            raw = sig.trigger_condition
                            cond = json.loads(raw) if isinstance(raw, str) else raw
                        except Exception:
                            cond = {"raw": sig.trigger_condition}
                    signals.append({
                        "signal_id": sig.id,
                        "signal_name": sig.signal_name,
                        "trigger_condition": cond,
                        "enabled": sig.enabled
                    })

            result.append({
                "pool_id": pool.id,
                "name": pool.pool_name,
                "symbols": symbols,
                "exchange": pool.exchange or "hyperliquid",
                "source_type": source_type,
                "logic": pool.logic or "OR",
                "enabled": pool.enabled,
                "signals": signals,
                "source_config": source_config if source_type == "wallet_tracking" else {},
            })

        return json.dumps({"signal_pools": result, "count": len(result)}, indent=2)

    except Exception as e:
        logger.error(f"[list_signal_pools] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_analyze_tracked_address(db: Session, address: str) -> str:
    """Fetch protected Hyper Insight address detail for Hyper AI analysis."""
    from services.hyper_insight_wallet_service import hyper_insight_wallet_service

    normalized = (address or "").strip().lower()
    if not normalized:
        return json.dumps({"error": "address is required"})

    snapshot = hyper_insight_wallet_service.get_status_snapshot()
    synced_addresses = [str(item).strip().lower() for item in (snapshot.get("synced_addresses") or []) if str(item).strip()]
    synced_set = set(synced_addresses)

    access_token = _get_hyper_insight_access_token(db)
    if not access_token:
        return json.dumps({
            "error": "Please log in to Hyper Alpha Arena before using Hyper Insight analysis.",
            "next_steps": [
                "Log in to Hyper Alpha Arena with your linked account first.",
                "After login, open Signals > Wallet Tracking and make sure your tracked wallets have synced before asking for wallet analysis."
            ]
        }, ensure_ascii=False)

    if snapshot.get("status") != "connected":
        return json.dumps({
            "error": "Wallet Tracking is not connected yet in Hyper Alpha Arena.",
            "next_steps": [
                "Open Hyper Alpha Arena and use the left sidebar to enter Signals > Wallet Tracking.",
                "Enable sync and wait until the connection status becomes connected before requesting wallet analysis."
            ]
        }, ensure_ascii=False)

    if normalized not in synced_set:
        return json.dumps({
            "error": "This wallet is not currently in your synced wallet list.",
            "next_steps": [
                "Track the wallet on https://hyper.akooi.com/ if it is not already tracked there.",
                "Then return to Hyper Alpha Arena > Signals > Wallet Tracking and wait until the wallet appears in the synced wallet list."
            ]
        }, ensure_ascii=False)

    base_url = os.getenv("HYPER_INSIGHT_API_BASE_URL", "https://hyper.akooi.com").rstrip("/")
    url = f"{base_url}/api/s2s/addresses/{normalized}"
    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 404:
            return json.dumps({
                "error": "This wallet is temporarily unavailable for detailed analysis right now.",
                "next_steps": [
                    "Wallet Tracking is already connected and the wallet is already in your synced list.",
                    "This means the current failure is system-side rather than a wallet tracking problem. Please retry later."
                ]
            }, ensure_ascii=False)
        if response.status_code == 401:
            return json.dumps({
                "error": "Your Hyper Insight session in Hyper Alpha Arena is no longer valid.",
                "next_steps": [
                    "Refresh Hyper Alpha Arena, open Signals > Wallet Tracking, and enable sync again.",
                    "After the tracked wallet list is visible again, retry the wallet analysis request."
                ]
            }, ensure_ascii=False)
        if response.status_code == 403:
            return json.dumps({
                "error": "Tracked wallet analysis is temporarily unavailable right now.",
                "next_steps": [
                    "Wallet Tracking is connected and the wallet is already in your synced list.",
                    "This means the current failure is system-side rather than a wallet tracking problem. Please retry later."
                ]
            }, ensure_ascii=False)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            payload.setdefault(
                "analysis_limit_note",
                "Recent fills are limited to the latest window and do not represent the address's complete all-time trade history.",
            )
        return json.dumps(payload, indent=2, ensure_ascii=False)
    except requests.RequestException as exc:
        logger.error("[analyze_tracked_address] Error fetching %s: %s", normalized, exc)
        return json.dumps({
            "error": "Failed to fetch Hyper Insight address detail right now.",
            "next_steps": [
                "If Wallet Tracking is connected and the wallet is already in your synced list, then the current failure is system-side.",
                "Please retry later."
            ]
        }, ensure_ascii=False)


def execute_list_strategies(db: Session, strategy_id: int = None, strategy_type: str = None) -> str:
    """List all prompts and programs with binding status.
    Pass strategy_id + strategy_type to get full content of a specific strategy."""
    from database.models import (
        PromptTemplate, TradingProgram,
        AccountProgramBinding, AccountPromptBinding, Account
    )

    try:
        # Single strategy detail mode
        if strategy_id and strategy_type:
            if strategy_type == "prompt":
                tpl = db.query(PromptTemplate).filter(
                    PromptTemplate.id == strategy_id,
                    PromptTemplate.is_deleted == "false"
                ).first()
                if not tpl:
                    return json.dumps({"error": f"Prompt {strategy_id} not found"})
                bindings = db.query(AccountPromptBinding).filter(
                    AccountPromptBinding.prompt_template_id == tpl.id,
                    AccountPromptBinding.is_deleted != True
                ).all()
                bound_traders = []
                for b in bindings:
                    acc = db.get(Account, b.account_id)
                    if acc:
                        bound_traders.append({"trader_id": acc.id, "trader_name": acc.name})
                return json.dumps({
                    "prompt_id": tpl.id,
                    "name": tpl.name,
                    "description": getattr(tpl, "description", None),
                    "template_text": tpl.template_text,
                    "bound_traders": bound_traders
                }, indent=2)
            elif strategy_type == "program":
                prog = db.query(TradingProgram).filter(
                    TradingProgram.id == strategy_id,
                    TradingProgram.is_deleted != True
                ).first()
                if not prog:
                    return json.dumps({"error": f"Program {strategy_id} not found"})
                bindings = db.query(AccountProgramBinding).filter(
                    AccountProgramBinding.program_id == prog.id,
                    AccountProgramBinding.is_deleted != True
                ).all()
                bound_traders = []
                for b in bindings:
                    acc = db.get(Account, b.account_id)
                    if acc:
                        bound_traders.append({
                            "trader_id": acc.id, "trader_name": acc.name,
                            "is_active": b.is_active
                        })
                return json.dumps({
                    "program_id": prog.id,
                    "name": prog.name,
                    "description": prog.description,
                    "code": prog.code,
                    "bound_traders": bound_traders
                }, indent=2)

        # List all mode (original behavior)
        # Prompts
        templates = db.query(PromptTemplate).filter(
            PromptTemplate.is_deleted == "false"
        ).all()
        prompts = []
        for tpl in templates:
            bindings = db.query(AccountPromptBinding).filter(
                AccountPromptBinding.prompt_template_id == tpl.id,
                AccountPromptBinding.is_deleted != True
            ).all()
            bound_traders = []
            for b in bindings:
                acc = db.get(Account, b.account_id)
                if acc:
                    bound_traders.append({"trader_id": acc.id, "trader_name": acc.name})
            prompts.append({
                "prompt_id": tpl.id,
                "name": tpl.name,
                "description": getattr(tpl, "description", None),
                "bound_traders": bound_traders
            })

        # Programs
        programs_db = db.query(TradingProgram).filter(TradingProgram.is_deleted != True).all()
        programs = []
        for prog in programs_db:
            bindings = db.query(AccountProgramBinding).filter(
                AccountProgramBinding.program_id == prog.id,
                AccountProgramBinding.is_deleted != True
            ).all()
            bound_traders = []
            for b in bindings:
                acc = db.get(Account, b.account_id)
                if acc:
                    bound_traders.append({
                        "trader_id": acc.id,
                        "trader_name": acc.name,
                        "is_active": b.is_active
                    })
            programs.append({
                "program_id": prog.id,
                "name": prog.name,
                "description": prog.description,
                "bound_traders": bound_traders
            })

        return json.dumps({
            "prompts": prompts,
            "programs": programs,
            "prompt_count": len(prompts),
            "program_count": len(programs)
        }, indent=2)

    except Exception as e:
        logger.error(f"[list_strategies] Error: {e}")
        return json.dumps({"error": str(e)})


# =============================================================================
# Binding Tools: assemble components
# =============================================================================

def execute_bind_prompt_to_trader(db: Session, trader_id: int, prompt_id: int) -> str:
    """Bind a prompt template to an AI Trader. Reuses prompt_repo.upsert_binding."""
    from database.models import Account, PromptTemplate
    from repositories import prompt_repo

    try:
        account = db.query(Account).filter(Account.id == trader_id, Account.is_deleted != True).first()
        if not account:
            return json.dumps({"error": f"AI Trader {trader_id} not found"})

        template = db.get(PromptTemplate, prompt_id)
        if not template:
            return json.dumps({"error": f"Prompt template {prompt_id} not found"})

        binding = prompt_repo.upsert_binding(
            db,
            account_id=trader_id,
            prompt_template_id=prompt_id,
            updated_by="hyper_ai"
        )

        return json.dumps({
            "success": True,
            "binding_id": binding.id,
            "trader_id": trader_id,
            "trader_name": account.name,
            "prompt_id": prompt_id,
            "prompt_name": template.name
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[bind_prompt_to_trader] Error: {e}")
        return json.dumps({"error": str(e)})


def _validate_signal_pool_exchange_consistency(
    db: Session, binding_exchange: str, signal_pool_ids: list
) -> dict:
    """
    Validate that signal pool exchanges match the binding's target exchange.
    Returns {"valid": True} or {"valid": False, "error": "...", "details": {...}}
    """
    from database.models import SignalPool

    if not signal_pool_ids:
        return {"valid": True}

    # Get signal pool exchanges
    pools = db.query(SignalPool).filter(
        SignalPool.id.in_(signal_pool_ids),
        SignalPool.is_deleted != True
    ).all()

    # Check for mismatches
    mismatched = []
    for pool in pools:
        pool_exchange = pool.exchange or "hyperliquid"
        if pool_exchange != binding_exchange:
            mismatched.append({
                "pool_id": pool.id,
                "pool_name": pool.pool_name,
                "pool_exchange": pool_exchange,
                "binding_exchange": binding_exchange
            })

    if mismatched:
        return {
            "valid": False,
            "error": f"Exchange mismatch: Signal pool(s) exchange does not match binding's target exchange '{binding_exchange}'.",
            "mismatched_pools": mismatched,
            "suggestion": f"Use signal pools with exchange='{binding_exchange}', or change the binding exchange to match the signal pools."
        }

    return {"valid": True}


def execute_bind_program_to_trader(
    db: Session, trader_id: int, program_id: int,
    exchange: str = "hyperliquid",
    signal_pool_ids: list = None, trigger_interval: int = 300,
    is_active: bool = True
) -> str:
    """Create a program binding for an AI Trader. Reuses AccountProgramBinding model."""
    from database.models import Account, TradingProgram, AccountProgramBinding

    try:
        account = db.query(Account).filter(Account.id == trader_id, Account.is_deleted != True).first()
        if not account:
            return json.dumps({"error": f"AI Trader {trader_id} not found"})

        program = db.get(TradingProgram, program_id)
        if not program:
            return json.dumps({"error": f"Program {program_id} not found"})

        # Validate signal pool exchange consistency with binding exchange
        if signal_pool_ids:
            validation = _validate_signal_pool_exchange_consistency(db, exchange, signal_pool_ids)
            if not validation.get("valid"):
                return json.dumps(validation)

        # Check duplicate
        existing = db.query(AccountProgramBinding).filter(
            AccountProgramBinding.account_id == trader_id,
            AccountProgramBinding.program_id == program_id,
            AccountProgramBinding.is_deleted != True
        ).first()
        if existing:
            return json.dumps({
                "error": f"Binding already exists (binding_id={existing.id})",
                "binding_id": existing.id
            })

        binding = AccountProgramBinding(
            account_id=trader_id,
            program_id=program_id,
            signal_pool_ids=json.dumps(signal_pool_ids) if signal_pool_ids else None,
            trigger_interval=trigger_interval,
            is_active=is_active,
            exchange=exchange
        )
        db.add(binding)
        db.commit()
        db.refresh(binding)

        return json.dumps({
            "success": True,
            "binding_id": binding.id,
            "trader_id": trader_id,
            "trader_name": account.name,
            "program_id": program_id,
            "program_name": program.name,
            "signal_pool_ids": signal_pool_ids or [],
            "trigger_interval": trigger_interval,
            "is_active": is_active
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[bind_program_to_trader] Error: {e}")
        return json.dumps({"error": str(e)})


def build_update_trader_strategy_kwargs(arguments: dict) -> dict:
    """Build the kwargs for execute_update_trader_strategy from raw tool-call arguments.

    `signal_pool_ids` is only included in the returned dict when the key is
    actually present in `arguments`. An LLM that omits the key (e.g. a call
    that only changes trigger_interval) must leave the trader's existing
    signal pool bindings untouched - relying on execute_update_trader_strategy's
    _STRATEGY_UNSET default - rather than being coerced to None via a bare
    `arguments.get("signal_pool_ids")`, which previously caused an omitted key
    to be indistinguishable from an explicit unbind-all request. An explicit
    `[]` or list of ids from the LLM still passes through unchanged, since
    that is the documented bind/unbind signal.
    """
    kwargs = {
        "trader_id": arguments.get("trader_id"),
        "scheduled_trigger_enabled": arguments.get("scheduled_trigger_enabled"),
        "trigger_interval": arguments.get("trigger_interval"),
        "exchange": arguments.get("exchange"),
    }
    if "signal_pool_ids" in arguments:
        kwargs["signal_pool_ids"] = arguments.get("signal_pool_ids")
    return kwargs


def execute_update_trader_strategy(
    db: Session, trader_id: int,
    signal_pool_ids=_STRATEGY_UNSET,
    scheduled_trigger_enabled: Optional[bool] = None,
    trigger_interval: int = None,
    exchange: Optional[str] = None
) -> str:
    """Update trigger config for a Prompt-based AI Trader. Reuses upsert_strategy.

    Fields left as None (not supplied by the caller) are preserved by upsert_strategy
    rather than reset to a default - e.g. omitting `exchange` will NOT flip the trader
    back to hyperliquid, and this tool never touches `enabled` at all.

    `signal_pool_ids` defaults to the shared _UNSET sentinel (aliased here as
    _STRATEGY_UNSET) rather than None: the dispatcher only forwards this kwarg
    when the LLM actually included "signal_pool_ids" in its tool-call arguments,
    so an update that only changes e.g. trigger_interval leaves the trader's
    signal pool bindings untouched instead of silently unbinding them.
    """
    from database.models import Account
    from repositories.strategy_repo import upsert_strategy, parse_signal_pool_ids

    try:
        account = db.query(Account).filter(Account.id == trader_id, Account.is_deleted != True).first()
        if not account:
            return json.dumps({"error": f"AI Trader {trader_id} not found"})

        strategy = upsert_strategy(
            db,
            account_id=trader_id,
            signal_pool_ids=signal_pool_ids,
            scheduled_trigger_enabled=scheduled_trigger_enabled,
            trigger_interval=trigger_interval,
            exchange=exchange
        )

        return json.dumps({
            "success": True,
            "trader_id": trader_id,
            "trader_name": account.name,
            "exchange": strategy.exchange,
            # Reflect the strategy's actual, persisted pool bindings rather than
            # echoing the raw argument - it may be the _UNSET sentinel (omitted
            # by the caller, meaning "preserved") which isn't JSON-serializable.
            "signal_pool_ids": parse_signal_pool_ids(strategy),
            "scheduled_trigger_enabled": strategy.scheduled_trigger_enabled,
            "trigger_interval": trigger_interval
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[update_trader_strategy] Error: {e}")
        return json.dumps({"error": str(e)})


# =============================================================================
# Update Tools
# =============================================================================

def execute_update_ai_trader(
    db: Session, trader_id: int,
    name: str = None, model: str = None,
    base_url: str = None, api_key: str = None
) -> str:
    """Update AI Trader settings. Tests LLM connection if credentials change."""
    from database.models import Account

    try:
        account = db.query(Account).filter(
            Account.id == trader_id, Account.is_active == "true",
            Account.is_deleted != True
        ).first()
        if not account:
            return json.dumps({"error": f"AI Trader {trader_id} not found"})

        # Test LLM connection if any credential field changes
        new_model = model or account.model
        new_base_url = base_url or account.base_url
        new_api_key = api_key or account.api_key
        need_test = any([model, base_url, api_key])

        if need_test and new_model and new_base_url and new_api_key:
            from api.account_routes import test_llm_connection
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            test_result = loop.run_until_complete(test_llm_connection({
                "model": new_model,
                "base_url": new_base_url,
                "api_key": new_api_key
            }))
            if not test_result.get("success"):
                return json.dumps({
                    "success": False,
                    "error": "LLM connection test failed",
                    "details": test_result.get("message", "Unknown error")
                })

        updated = []
        if name:
            account.name = name
            updated.append("name")
        if model:
            account.model = model
            updated.append("model")
        if base_url:
            account.base_url = base_url
            updated.append("base_url")
        if api_key:
            account.api_key = api_key
            updated.append("api_key")

        db.commit()
        return json.dumps({
            "success": True, "trader_id": trader_id,
            "trader_name": account.name,
            "updated_fields": updated,
            "llm_tested": need_test
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[update_ai_trader] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_update_program_binding(
    db: Session, binding_id: int,
    signal_pool_ids: list = None, trigger_interval: int = None,
    scheduled_trigger_enabled: bool = None, is_active: bool = None,
    params_override: dict = None
) -> str:
    """Update a program binding's configuration."""
    from database.models import AccountProgramBinding, Account

    try:
        binding = db.query(AccountProgramBinding).filter(
            AccountProgramBinding.id == binding_id,
            AccountProgramBinding.is_deleted != True
        ).first()
        if not binding:
            return json.dumps({"error": f"Program binding {binding_id} not found"})

        updated = []
        if signal_pool_ids is not None:
            binding.signal_pool_ids = json.dumps(signal_pool_ids)
            updated.append("signal_pool_ids")
        if trigger_interval is not None:
            binding.trigger_interval = trigger_interval
            updated.append("trigger_interval")
        if scheduled_trigger_enabled is not None:
            binding.scheduled_trigger_enabled = scheduled_trigger_enabled
            updated.append("scheduled_trigger_enabled")
        if is_active is not None:
            binding.is_active = is_active
            updated.append("is_active")
        if params_override is not None:
            binding.params_override = json.dumps(params_override)
            updated.append("params_override")

        db.commit()
        account = db.get(Account, binding.account_id)
        return json.dumps({
            "success": True, "binding_id": binding_id,
            "trader_name": account.name if account else "unknown",
            "updated_fields": updated
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[update_program_binding] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_update_signal_pool(
    db: Session, pool_id: int,
    pool_name: str = None, enabled: bool = None, logic: str = None,
    signal_ids: list = None
) -> str:
    """Update signal pool settings."""
    from database.models import SignalPool, SignalDefinition

    try:
        pool = db.query(SignalPool).filter(SignalPool.id == pool_id, SignalPool.is_deleted != True).first()
        if not pool:
            return json.dumps({"error": f"Signal pool {pool_id} not found"})

        updated = []

        # Validate signal_ids exchange match
        if signal_ids is not None:
            pool_exchange = pool.exchange or "hyperliquid"
            mismatched = []
            for sid in signal_ids:
                sig = db.query(SignalDefinition).filter(SignalDefinition.id == sid, SignalDefinition.is_deleted != True).first()
                if not sig:
                    return json.dumps({"error": f"Signal definition {sid} not found"})
                sig_exchange = sig.exchange or "hyperliquid"
                if sig_exchange != pool_exchange:
                    mismatched.append(f"Signal {sid} ({sig_exchange})")
            if mismatched:
                return json.dumps({
                    "error": f"Exchange mismatch: pool is {pool_exchange}, but {', '.join(mismatched)}"
                })
            pool.signal_ids = json.dumps(signal_ids)
            updated.append("signal_ids")

        if pool_name is not None:
            pool.pool_name = pool_name
            updated.append("pool_name")
        if enabled is not None:
            pool.enabled = enabled
            updated.append("enabled")
        if logic is not None:
            pool.logic = logic
            updated.append("logic")

        db.commit()
        return json.dumps({
            "success": True, "pool_id": pool_id,
            "pool_name": pool.pool_name,
            "updated_fields": updated
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[update_signal_pool] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_update_prompt_binding(db: Session, trader_id: int, prompt_id: int) -> str:
    """Update which prompt is bound to a trader. Reuses upsert_binding."""
    from database.models import Account, PromptTemplate
    from repositories import prompt_repo

    try:
        account = db.query(Account).filter(Account.id == trader_id, Account.is_deleted != True).first()
        if not account:
            return json.dumps({"error": f"AI Trader {trader_id} not found"})

        template = db.get(PromptTemplate, prompt_id)
        if not template:
            return json.dumps({"error": f"Prompt template {prompt_id} not found"})

        binding = prompt_repo.upsert_binding(
            db, account_id=trader_id,
            prompt_template_id=prompt_id, updated_by="hyper_ai"
        )
        return json.dumps({
            "success": True, "binding_id": binding.id,
            "trader_id": trader_id, "trader_name": account.name,
            "prompt_id": prompt_id, "prompt_name": template.name
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[update_prompt_binding] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_save_memory(
    db: Session, category: str, content: str,
    importance: float = 0.5, api_config: Optional[Dict[str, Any]] = None
) -> str:
    """Save a memory with LLM-powered dedup (same logic as compression).

    When api_config is provided, uses batch_dedup_memories to intelligently
    ADD/UPDATE/DELETE memories. Falls back to simple add if no api_config.
    """
    from services.hyper_ai_memory_service import (
        add_memory, MEMORY_CATEGORIES, enforce_memory_limit,
        batch_dedup_memories
    )

    try:
        if category not in MEMORY_CATEGORIES:
            return json.dumps({"error": f"Invalid category. Must be one of: {MEMORY_CATEGORIES}"})

        content = content.strip()
        if len(content) < 10:
            return json.dumps({"error": "Content must be at least 10 characters"})

        importance = max(0.0, min(1.0, importance))

        new_memory = [{"category": category, "content": content, "importance": importance}]

        if api_config and api_config.get("api_key"):
            count = batch_dedup_memories(db, new_memory, api_config, source="ai_tool")
            action = "deduped" if count > 0 else "skipped (redundant)"
        else:
            add_memory(db, category, content, source="ai_tool", importance=importance)
            enforce_memory_limit(db)
            action = "added"

        return json.dumps({
            "success": True,
            "action": action,
            "note": "Memory processed with intelligent dedup. It will be included in future conversations."
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[save_memory] Error: {e}")
        return json.dumps({"error": str(e)})


# =============================================================================
# Factor System Tool Handlers
# =============================================================================

def execute_query_factors(
    db: Session, exchange: str, symbol: str = None,
    factor_name: str = None, forward_period: str = "4h",
    days: int = 30
) -> str:
    """Query factor library, values, and effectiveness."""
    from services.factor_registry import FACTOR_REGISTRY, CATEGORY_LABELS
    from database.models import CustomFactor

    try:
        # If specific factor requested, return detailed info + history
        if factor_name and symbol:
            row = db.execute(text("""
                SELECT factor_name, factor_category, ic_mean, ic_std, icir,
                    win_rate, sample_count, calc_date, decay_half_life
                FROM factor_effectiveness
                WHERE factor_name = :fn AND symbol = :sym AND period = '1h'
                    AND forward_period = :fp AND exchange = :ex
                ORDER BY calc_date DESC LIMIT 1
            """), {"fn": factor_name, "sym": symbol, "fp": forward_period, "ex": exchange}).fetchone()

            val_row = db.execute(text("""
                SELECT value, timestamp FROM factor_values
                WHERE factor_name = :fn AND symbol = :sym AND period = '1h' AND exchange = :ex
                ORDER BY timestamp DESC LIMIT 1
            """), {"fn": factor_name, "sym": symbol, "ex": exchange}).fetchone()

            from datetime import date as _d, timedelta as _td
            history_cutoff = _d.today() - _td(days=min(days, 365))
            history = db.execute(text("""
                SELECT calc_date, ic_mean, icir, win_rate, sample_count
                FROM factor_effectiveness
                WHERE factor_name = :fn AND symbol = :sym AND period = '1h'
                    AND forward_period = :fp AND exchange = :ex
                    AND calc_date >= :cutoff
                ORDER BY calc_date
            """), {"fn": factor_name, "sym": symbol, "fp": forward_period,
                   "ex": exchange, "cutoff": history_cutoff}).fetchall()

            return json.dumps({
                "factor_name": factor_name,
                "symbol": symbol, "exchange": exchange, "forward_period": forward_period,
                "latest_value": float(val_row[0]) if val_row else None,
                "effectiveness": {
                    "ic_mean": float(row[2]), "ic_std": float(row[3]),
                    "icir": float(row[4]), "win_rate": float(row[5]),
                    "sample_count": row[6], "calc_date": str(row[7]),
                    "decay_half_life_hours": int(row[8]) if row[8] is not None else None,
                } if row else None,
                "history": [
                    {"date": str(r[0]), "ic_mean": float(r[1]), "icir": float(r[2]),
                     "win_rate": float(r[3]), "sample_count": r[4]}
                    for r in history
                ]
            }, indent=2)

        # If symbol provided, return values + effectiveness ranking
        if symbol:
            eff_rows = db.execute(text("""
                SELECT DISTINCT ON (factor_name)
                    factor_name, factor_category, ic_mean, icir, win_rate, sample_count,
                    decay_half_life
                FROM factor_effectiveness
                WHERE symbol = :sym AND period = '1h' AND forward_period = :fp AND exchange = :ex
                ORDER BY factor_name, calc_date DESC
            """), {"sym": symbol, "fp": forward_period, "ex": exchange}).fetchall()

            # IC 7-day trend
            from datetime import date as _date, timedelta as _td
            cutoff_7d = _date.today() - _td(days=7)
            ic_7d_rows = db.execute(text("""
                SELECT factor_name, AVG(ic_mean) as ic_7d
                FROM factor_effectiveness
                WHERE symbol = :sym AND period = '1h' AND forward_period = :fp
                    AND exchange = :ex AND calc_date >= :cutoff
                GROUP BY factor_name
            """), {"sym": symbol, "fp": forward_period, "ex": exchange, "cutoff": cutoff_7d}).fetchall()
            ic_7d_map = {r[0]: round(float(r[1]), 6) if r[1] is not None else None for r in ic_7d_rows}

            items = []
            for r in eff_rows:
                fname = r[0]
                ic_30d = float(r[2])
                ic_7d = ic_7d_map.get(fname)
                ic_trend = None
                if ic_7d is not None and abs(ic_30d) > 1e-6:
                    ic_trend = round(ic_7d / ic_30d, 2)
                items.append({
                    "factor_name": fname, "category": r[1], "ic_mean": ic_30d,
                    "icir": float(r[3]), "win_rate": float(r[4]), "sample_count": r[5],
                    "decay_half_life_hours": int(r[6]) if r[6] is not None else None,
                    "ic_7d": ic_7d, "ic_trend": ic_trend,
                })
            items.sort(key=lambda x: abs(x.get("icir") or 0), reverse=True)

            return json.dumps({
                "symbol": symbol, "exchange": exchange, "forward_period": forward_period,
                "factor_count": len(items),
                "top_factors": items[:15],
                "note": f"Showing top 15 by |ICIR| out of {len(items)} factors"
            }, indent=2)

        # No symbol: return factor library
        custom_rows = db.query(CustomFactor).filter(CustomFactor.is_active == True).all()
        factors = [
            {"name": f["name"], "category": f["category"], "source": "builtin",
             "display_name": f.get("display_name", f["name"])}
            for f in FACTOR_REGISTRY
        ] + [
            {"name": cf.name, "category": "custom", "source": cf.source or "custom",
             "expression": cf.expression, "custom_id": cf.id}
            for cf in custom_rows
        ]
        return json.dumps({
            "exchange": exchange,
            "total_factors": len(factors),
            "builtin_count": len(FACTOR_REGISTRY),
            "custom_count": len(custom_rows),
            "factors": factors
        }, indent=2)

    except Exception as e:
        logger.error(f"[query_factors] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_evaluate_factor(
    db: Session, expression: str, symbol: str, exchange: str
) -> str:
    """Evaluate a factor expression against real market data (full local history)."""
    from services.factor_expression_engine import factor_expression_engine
    from services.factor_data_provider import ensure_kline_coverage
    import pandas as pd

    try:
        ok, err = factor_expression_engine.validate(expression)
        if not ok:
            return json.dumps({"error": err})

        klines = ensure_kline_coverage(db, exchange, symbol, "1h")
        if not klines or len(klines) < 50:
            return json.dumps({"error": f"Insufficient K-line data for {symbol} on {exchange}"})

        results, err = factor_expression_engine.evaluate_ic(expression, klines)
        if results is None:
            return json.dumps({"error": err})

        series, _ = factor_expression_engine.execute(expression, klines)
        latest_value = None
        if series is not None and len(series) > 0:
            last = series.iloc[-1]
            latest_value = float(last) if not pd.isna(last) else None

        return json.dumps({
            "expression": expression, "symbol": symbol, "exchange": exchange,
            "latest_value": latest_value,
            "effectiveness": results
        }, indent=2)

    except Exception as e:
        logger.error(f"[evaluate_factor] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_save_factor(db: Session, name: str, expression: str, description: str = "") -> str:
    """Save a custom factor expression to the library."""
    import re
    from database.models import CustomFactor
    from services.factor_expression_engine import factor_expression_engine

    try:
        # Validate factor name format
        if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', name):
            return json.dumps({"error": "Factor name must start with a letter and contain only English letters, digits, and underscores (e.g., RSI_fast, momentum_v2)"})

        ok, err = factor_expression_engine.validate(expression)
        if not ok:
            return json.dumps({"error": f"Invalid expression: {err}"})

        existing = db.query(CustomFactor).filter(CustomFactor.name == name).first()
        if existing:
            return json.dumps({"error": f"Factor name '{name}' already exists"})

        factor = CustomFactor(
            name=name, expression=expression,
            description=description, category="custom", source="ai"
        )
        db.add(factor)
        db.commit()
        db.refresh(factor)

        return json.dumps({
            "success": True,
            "factor_id": factor.id,
            "name": factor.name,
            "expression": factor.expression,
            "action": "created",
            "view_url": "/#factor-library",
            "note": f"Factor '{name}' saved. Use compute_factor to run full evaluation across all symbols."
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[save_factor] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_edit_factor(
    db: Session, factor_id: int,
    name: str = None, expression: str = None, description: str = None
) -> str:
    """Edit an existing custom factor."""
    from database.models import CustomFactor
    from services.factor_expression_engine import factor_expression_engine

    try:
        factor = db.query(CustomFactor).filter(CustomFactor.id == factor_id).first()
        if not factor:
            return json.dumps({"error": f"Custom factor with id={factor_id} not found"})

        if expression:
            ok, err = factor_expression_engine.validate(expression)
            if not ok:
                return json.dumps({"error": f"Invalid expression: {err}"})
            factor.expression = expression

        if name:
            dup = db.query(CustomFactor).filter(
                CustomFactor.name == name, CustomFactor.id != factor_id
            ).first()
            if dup:
                return json.dumps({"error": f"Factor name '{name}' already exists"})
            factor.name = name

        if description is not None:
            factor.description = description

        db.commit()
        db.refresh(factor)

        return json.dumps({
            "success": True,
            "factor_id": factor.id,
            "name": factor.name,
            "expression": factor.expression,
            "action": "updated",
            "view_url": "/#factor-library",
            "note": f"Factor '{factor.name}' updated."
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[edit_factor] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_compute_factor(db: Session, factor_name: str, exchange: str) -> str:
    """Compute a single factor across all watchlist symbols using sliding window IC.
    Delegates to FactorEffectivenessService.compute_single_factor() — no duplicated logic.
    """
    from services.factor_effectiveness_service import FactorEffectivenessService

    try:
        eff_svc = FactorEffectivenessService()
        result = eff_svc.compute_single_factor(db, exchange, factor_name)
        return json.dumps(result, indent=2)
    except Exception as e:
        db.rollback()
        logger.error(f"[compute_factor] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_factor_functions(category: str = None) -> str:
    """Return factor expression functions from the registry, optionally filtered by category."""
    from services.factor_expression_engine import factor_expression_engine

    grouped = factor_expression_engine.get_registry_grouped()
    if category:
        filtered = {k: v for k, v in grouped.items() if k == category}
        if not filtered:
            cats = list(grouped.keys())
            return json.dumps({"error": f"Unknown category '{category}'. Available: {cats}"})
        grouped = filtered

    # Compact format for token efficiency
    lines = []
    for cat_key, cat_data in grouped.items():
        lines.append(f"\n## {cat_data['label']}")
        for fn in cat_data["functions"]:
            lines.append(f"- `{fn['signature']}` — {fn['description']}")
            lines.append(f"  Example: `{fn['example']}`")

    return json.dumps({
        "total_functions": sum(len(c["functions"]) for c in grouped.values()),
        "categories": list(grouped.keys()),
        "reference": "\n".join(lines),
    })


def execute_web_search(db: Session, query: str, max_results: int = 5) -> str:
    """Search the web using Tavily API. Returns error with setup guide if key not configured."""
    from services.hyper_ai_tool_registry import get_tool_api_key

    api_key = get_tool_api_key(db, "tavily")
    if not api_key:
        return json.dumps({
            "error": "Web search is not configured. The user needs to set up their Tavily API key.",
            "setup_guide": "Go to Hyper AI page → right panel → Tools section → click Tavily Web Search → enter API key.",
            "get_url": "https://tavily.com"
        })

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        max_results = min(max(1, max_results), 10)
        response = client.search(query, max_results=max_results)

        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:500],
            })

        return json.dumps({
            "query": query,
            "results": results,
            "result_count": len(results),
        })

    except Exception as e:
        err = str(e)
        if "401" in err or "Unauthorized" in err:
            return json.dumps({"error": "Tavily API key is invalid or expired. Please update it in Tools settings."})
        logger.error(f"[web_search] Error: {e}")
        return json.dumps({"error": f"Search failed: {err}"})


def execute_fetch_url(url: str, max_length: int = 8000) -> str:
    """Fetch URL content using Jina Reader API with trafilatura fallback."""
    import requests as req

    max_length = min(max(1000, max_length), 15000)

    if not url or not url.startswith(("http://", "https://")):
        return json.dumps({"error": "Invalid URL. Must start with http:// or https://"})

    content = None
    source = None

    # Strategy 1: Jina Reader API (renders JS, returns clean Markdown)
    try:
        jina_url = f"https://r.jina.ai/{url}"
        headers = {
            "Accept": "text/plain",
            "X-No-Cache": "true",
        }
        resp = req.get(jina_url, headers=headers, timeout=30)
        if resp.status_code == 200 and len(resp.text.strip()) > 100:
            content = resp.text.strip()
            source = "jina_reader"
    except Exception as e:
        logger.warning(f"[fetch_url] Jina Reader failed for {url}: {e}")

    # Strategy 2: Trafilatura local extraction (fallback)
    if not content:
        try:
            import trafilatura
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                extracted = trafilatura.extract(
                    downloaded,
                    output_format="txt",
                    include_links=True,
                    include_tables=True,
                )
                if extracted and len(extracted.strip()) > 50:
                    content = extracted.strip()
                    source = "trafilatura"
        except Exception as e:
            logger.warning(f"[fetch_url] Trafilatura failed for {url}: {e}")

    # Strategy 3: Raw requests fallback (minimal extraction)
    if not content:
        try:
            resp = req.get(url, timeout=20, headers={
                "User-Agent": "Mozilla/5.0 (compatible; HyperAI/1.0)"
            })
            if resp.status_code == 200:
                text = resp.text
                # Basic HTML tag stripping for raw fallback
                import re
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                if len(text) > 50:
                    content = text
                    source = "raw_requests"
        except Exception as e:
            logger.warning(f"[fetch_url] Raw fetch failed for {url}: {e}")

    if not content:
        return json.dumps({"error": f"Failed to fetch content from {url}. The page may be inaccessible or require authentication."})

    # Truncate to max_length
    truncated = len(content) > max_length
    if truncated:
        content = content[:max_length] + "\n\n[Content truncated...]"

    return json.dumps({
        "url": url,
        "content": content,
        "content_length": len(content),
        "truncated": truncated,
        "source": source,
    })


def execute_get_tracked_wallets(db: Session) -> str:
    """Return the current Hyper Insight sync state and synced tracked wallets."""
    from services.hyper_insight_wallet_service import hyper_insight_wallet_service

    snapshot = hyper_insight_wallet_service.get_status_snapshot()
    synced_addresses = snapshot.get("synced_addresses") or []
    result = {
        "connected": snapshot.get("status") == "connected",
        "status": snapshot.get("status"),
        "tier": snapshot.get("tier"),
        "tracked_wallet_count": len(synced_addresses),
        "tracked_wallets": synced_addresses,
        "last_connected_at": snapshot.get("last_connected_at"),
        "last_event_at": snapshot.get("last_event_at"),
        "last_error": snapshot.get("last_error"),
        "usage_note": "This list reflects the wallets currently synced from Hyper Insight into Hyper Alpha Arena. It is the correct source for what Hyper AI can currently inspect in this Arena session.",
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


_STRATEGY_RADAR_UNIVERSE_CACHE: dict[str, Any] = {"expires_at": None, "payload": None}


def _get_hyper_insight_access_token(db: Session) -> str:
    token_row = db.query(SystemConfig).filter(SystemConfig.key == "hyper_insight_wallet_access_token").first()
    return ((token_row.value if token_row else "") or "").strip()


def _strategy_radar_headers(db: Session) -> dict[str, str] | None:
    access_token = _get_hyper_insight_access_token(db)
    if not access_token:
        return None
    return {"Authorization": f"Bearer {access_token}"}


def _strategy_radar_base_url() -> str:
    return os.getenv("HYPER_INSIGHT_API_BASE_URL", "https://hyper.akooi.com").rstrip("/")


def _fetch_strategy_radar_universe(db: Session, *, force_refresh: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    cached_until = _STRATEGY_RADAR_UNIVERSE_CACHE.get("expires_at")
    cached_payload = _STRATEGY_RADAR_UNIVERSE_CACHE.get("payload")
    if (
        not force_refresh
        and cached_payload is not None
        and isinstance(cached_until, datetime)
        and cached_until > now
    ):
        return cached_payload

    headers = _strategy_radar_headers(db)
    if headers is None:
        return {
            "ok": False,
            "error": "Please log in to Hyper Alpha Arena before using Strategy Radar with Hyper AI.",
            "reason": "missing_login_token",
            "next_steps": [
                "Log in to Hyper Alpha Arena with your linked account first.",
                "After login, ask Hyper AI to search Strategy Radar again.",
            ],
        }

    url = f"{_strategy_radar_base_url()}/api/s2s/strategy-radar/universe"
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code == 401:
        return {
            "ok": False,
            "error": "Your Hyper Insight login in Hyper Alpha Arena is no longer valid.",
            "reason": "upstream_401",
            "next_steps": [
                "Log in to Hyper Alpha Arena again.",
                "After login, ask Hyper AI to search Strategy Radar again.",
            ],
        }
    if response.status_code in {403, 503}:
        return {
            "ok": False,
            "error": "Strategy Radar lookup is temporarily unavailable right now.",
            "reason": f"upstream_{response.status_code}",
        }
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        payload["ok"] = True
        _STRATEGY_RADAR_UNIVERSE_CACHE["payload"] = payload
        _STRATEGY_RADAR_UNIVERSE_CACHE["expires_at"] = now + timedelta(minutes=10)
        return payload
    return {"ok": False, "error": "Strategy Radar returned an invalid universe response."}


def execute_get_strategy_radar_universe(db: Session) -> str:
    """Return Strategy Radar's currently queryable symbol/period/regime combinations."""
    try:
        payload = _fetch_strategy_radar_universe(db)
        return json.dumps(payload, indent=2, ensure_ascii=False)
    except requests.RequestException as exc:
        logger.error("[strategy_radar_universe] Error: %s", exc)
        return json.dumps({
            "ok": False,
            "error": "Failed to fetch Strategy Radar supported symbols right now.",
        }, ensure_ascii=False)


def _universe_supports(universe: dict, *, symbol: str, period: str, exchange: str | None) -> tuple[bool, dict | None]:
    for item in universe.get("symbols") or []:
        if str(item.get("symbol", "")).upper() != symbol:
            continue
        for period_item in item.get("periods") or []:
            if period_item.get("period") != period:
                continue
            if exchange and period_item.get("exchange") != exchange:
                continue
            return True, period_item
        return False, None
    return False, None


def execute_search_strategy_radar(
    db: Session,
    *,
    symbol: str,
    period: str = "1h",
    regime: str | None = None,
    exchange: str | None = None,
    strategy_type: str | None = None,
    sort_by: str | None = None,
    risk_level: str | None = None,
    timeframe: str | None = None,
    limit: int = 5,
) -> str:
    """Search protected Strategy Radar S2S endpoints for current strategy candidates."""
    safe_symbol = (symbol or "").strip().upper()
    safe_period = period if period in {"1h", "4h", "1d"} else "1h"
    safe_exchange = exchange if exchange in {"hyperliquid", "binance"} else None
    safe_sort_by = sort_by if sort_by in {"relevance", "quality", "newest"} else None
    safe_risk_level = risk_level if risk_level in {"Low", "Medium", "High"} else None
    safe_timeframe = timeframe if timeframe in {"1h", "4h", "1d", "multi"} else None
    safe_limit = max(1, min(int(limit or 5), 10))

    if not safe_symbol:
        return json.dumps({"ok": False, "error": "symbol is required"}, ensure_ascii=False)

    universe = _fetch_strategy_radar_universe(db)
    if not universe.get("ok"):
        return json.dumps(universe, ensure_ascii=False)

    supported, period_item = _universe_supports(
        universe,
        symbol=safe_symbol,
        period=safe_period,
        exchange=safe_exchange,
    )
    if not supported:
        return json.dumps({
            "ok": False,
            "reason": "unsupported_symbol_period",
            "symbol": safe_symbol,
            "period": safe_period,
            "exchange": safe_exchange,
            "supported_symbols": [
                item.get("symbol") for item in (universe.get("symbols") or []) if item.get("symbol")
            ],
            "usage_note": "Only combinations returned by get_strategy_radar_universe are supported.",
        }, ensure_ascii=False)

    headers = _strategy_radar_headers(db)
    if headers is None:
        return json.dumps({
            "ok": False,
            "error": "Please log in to Hyper Alpha Arena before using Strategy Radar with Hyper AI.",
            "next_steps": [
                "Log in to Hyper Alpha Arena with your linked account first.",
                "After login, ask Hyper AI to search Strategy Radar again.",
            ],
        }, ensure_ascii=False)

    params = {
        "symbol": safe_symbol,
        "period": safe_period,
        "limit": safe_limit,
    }
    if regime:
        params["regime"] = regime
    if safe_exchange:
        params["exchange"] = safe_exchange
    if strategy_type:
        params["strategy_type"] = strategy_type
    if safe_sort_by:
        params["sort_by"] = safe_sort_by
    if safe_risk_level:
        params["risk_level"] = safe_risk_level
    if safe_timeframe:
        params["timeframe"] = safe_timeframe

    try:
        response = requests.get(
            f"{_strategy_radar_base_url()}/api/s2s/strategy-radar/search",
            headers=headers,
            params=params,
            timeout=12,
        )
        if response.status_code == 401:
            return json.dumps({
                "ok": False,
                "error": "Your Hyper Insight login in Hyper Alpha Arena is no longer valid.",
                "reason": "upstream_401",
                "next_steps": [
                    "Log in to Hyper Alpha Arena again.",
                    "After login, ask Hyper AI to search Strategy Radar again.",
                ],
            }, ensure_ascii=False)
        if response.status_code in {403, 503}:
            return json.dumps({
                "ok": False,
                "error": "Strategy Radar lookup is temporarily unavailable right now.",
                "reason": f"upstream_{response.status_code}",
            }, ensure_ascii=False)
        if response.status_code == 429:
            return json.dumps({
                "ok": False,
                "error": "Strategy Radar is rate limited right now. Please retry later.",
            }, ensure_ascii=False)
        response.raise_for_status()
        payload = response.json()
        return json.dumps(payload, indent=2, ensure_ascii=False)
    except requests.RequestException as exc:
        logger.error("[search_strategy_radar] Error: %s", exc)
        return json.dumps({
            "ok": False,
            "error": "Failed to fetch Strategy Radar candidates right now.",
        }, ensure_ascii=False)


def execute_hyper_ai_tool(
    db: Session, tool_name: str, arguments: Dict[str, Any],
    user_id: int = 1, api_config: Optional[Dict[str, Any]] = None
) -> str:
    """Execute a Hyper AI tool by name."""
    try:
        if tool_name == "get_system_overview":
            return execute_get_system_overview(db)

        elif tool_name == "get_wallet_status":
            return execute_get_wallet_status(
                db,
                exchange=arguments.get("exchange", "all"),
                environment=arguments.get("environment", "all")
            )

        elif tool_name == "get_api_reference":
            return execute_get_api_reference(
                doc_type=arguments.get("doc_type", "prompt"),
                api_type=arguments.get("api_type", "all"),
                lang=arguments.get("lang", "en")
            )

        elif tool_name == "get_klines":
            return execute_get_klines(
                db,
                symbol=arguments.get("symbol", "BTC"),
                period=arguments.get("period", "1h"),
                limit=arguments.get("limit", 50),
                exchange=arguments.get("exchange", "hyperliquid")
            )

        elif tool_name == "get_market_regime":
            return execute_get_market_regime(
                db,
                symbol=arguments.get("symbol", "BTC"),
                period=arguments.get("period", "1h"),
                exchange=arguments.get("exchange", "hyperliquid")
            )

        elif tool_name == "get_market_flow":
            return execute_get_market_flow(
                db,
                symbol=arguments.get("symbol", "BTC"),
                period=arguments.get("period", "1h"),
                exchange=arguments.get("exchange", "hyperliquid")
            )

        elif tool_name == "get_system_logs":
            return execute_get_system_logs(
                db,
                level=arguments.get("level", "error"),
                limit=arguments.get("limit", 20),
                trader_id=arguments.get("trader_id")
            )

        elif tool_name == "get_contact_config":
            return execute_get_contact_config()

        elif tool_name == "get_trading_environment":
            return execute_get_trading_environment(db)

        elif tool_name == "get_watchlist":
            return execute_get_watchlist(db)

        elif tool_name == "update_watchlist":
            return execute_update_watchlist(
                db,
                exchange=arguments.get("exchange"),
                symbols=arguments.get("symbols", [])
            )

        elif tool_name == "diagnose_trader_issues":
            return execute_diagnose_trader_issues(db, trader_id=arguments.get("trader_id"))

        elif tool_name == "analyze_tracked_address":
            return execute_analyze_tracked_address(
                db,
                address=arguments.get("address", ""),
            )

        elif tool_name == "get_tracked_wallets":
            return execute_get_tracked_wallets(db)

        elif tool_name == "get_strategy_radar_universe":
            return execute_get_strategy_radar_universe(db)

        elif tool_name == "search_strategy_radar":
            return execute_search_strategy_radar(
                db,
                symbol=arguments.get("symbol", ""),
                period=arguments.get("period", "1h"),
                regime=arguments.get("regime"),
                exchange=arguments.get("exchange"),
                strategy_type=arguments.get("strategy_type"),
                sort_by=arguments.get("sort_by"),
                risk_level=arguments.get("risk_level"),
                timeframe=arguments.get("timeframe"),
                limit=arguments.get("limit", 5),
            )

        elif tool_name == "save_signal_pool":
            return execute_save_signal_pool(
                db,
                pool_name=arguments.get("pool_name"),
                symbol=arguments.get("symbol", "BTC"),
                signals=arguments.get("signals", []),
                logic=arguments.get("logic", "AND"),
                exchange=arguments.get("exchange", "hyperliquid"),
                description=arguments.get("description")
            )

        elif tool_name == "save_prompt":
            return execute_save_prompt(
                db,
                name=arguments.get("name"),
                template_text=arguments.get("template_text"),
                prompt_id=arguments.get("prompt_id"),
                description=arguments.get("description")
            )

        elif tool_name == "save_program":
            return execute_save_program(
                db,
                name=arguments.get("name"),
                code=arguments.get("code"),
                program_id=arguments.get("program_id"),
                description=arguments.get("description")
            )

        elif tool_name == "create_ai_trader":
            return execute_create_ai_trader(
                db,
                name=arguments.get("name"),
                model=arguments.get("model"),
                base_url=arguments.get("base_url"),
                api_key=arguments.get("api_key")
            )

        # --- Query tools: list resources ---
        elif tool_name == "list_traders":
            return execute_list_traders(db, trader_id=arguments.get("trader_id"))

        elif tool_name == "list_signal_pools":
            return execute_list_signal_pools(db, pool_id=arguments.get("pool_id"))

        elif tool_name == "list_strategies":
            return execute_list_strategies(
                db,
                strategy_id=arguments.get("strategy_id"),
                strategy_type=arguments.get("strategy_type")
            )

        # --- Binding tools: assemble components ---
        elif tool_name == "bind_prompt_to_trader":
            return execute_bind_prompt_to_trader(
                db,
                trader_id=arguments.get("trader_id"),
                prompt_id=arguments.get("prompt_id")
            )

        elif tool_name == "bind_program_to_trader":
            return execute_bind_program_to_trader(
                db,
                trader_id=arguments.get("trader_id"),
                program_id=arguments.get("program_id"),
                exchange=arguments.get("exchange", "hyperliquid"),
                signal_pool_ids=arguments.get("signal_pool_ids"),
                trigger_interval=arguments.get("trigger_interval", 300),
                is_active=arguments.get("is_active", True)
            )

        elif tool_name == "update_trader_strategy":
            return execute_update_trader_strategy(
                db, **build_update_trader_strategy_kwargs(arguments)
            )

        # --- Update tools ---
        elif tool_name == "update_ai_trader":
            return execute_update_ai_trader(
                db, trader_id=arguments.get("trader_id"),
                name=arguments.get("name"), model=arguments.get("model"),
                base_url=arguments.get("base_url"), api_key=arguments.get("api_key")
            )

        elif tool_name == "update_program_binding":
            return execute_update_program_binding(
                db, binding_id=arguments.get("binding_id"),
                signal_pool_ids=arguments.get("signal_pool_ids"),
                trigger_interval=arguments.get("trigger_interval"),
                scheduled_trigger_enabled=arguments.get("scheduled_trigger_enabled"),
                is_active=arguments.get("is_active"),
                params_override=arguments.get("params_override")
            )

        elif tool_name == "update_signal_pool":
            return execute_update_signal_pool(
                db, pool_id=arguments.get("pool_id"),
                pool_name=arguments.get("pool_name"),
                enabled=arguments.get("enabled"),
                logic=arguments.get("logic"),
                signal_ids=arguments.get("signal_ids")
            )

        elif tool_name == "update_prompt_binding":
            return execute_update_prompt_binding(
                db, trader_id=arguments.get("trader_id"),
                prompt_id=arguments.get("prompt_id")
            )

        # --- Skill tools: load workflow guidance (no side effects) ---
        elif tool_name == "load_skill":
            from services.hyper_ai_skill_engine import load_skill
            return json.dumps(load_skill(skill_name=arguments.get("skill_name", "")))

        elif tool_name == "load_skill_reference":
            from services.hyper_ai_skill_engine import load_skill_reference
            return json.dumps(load_skill_reference(
                skill_name=arguments.get("skill_name", ""),
                reference_file=arguments.get("reference_file", "")
            ))

        elif tool_name == "save_memory":
            return execute_save_memory(
                db,
                category=arguments.get("category", "context"),
                content=arguments.get("content", ""),
                importance=arguments.get("importance", 0.5),
                api_config=api_config
            )

        # --- Factor tools ---
        elif tool_name == "query_factors":
            return execute_query_factors(
                db, exchange=arguments.get("exchange", "hyperliquid"),
                symbol=arguments.get("symbol"),
                factor_name=arguments.get("factor_name"),
                forward_period=arguments.get("forward_period", "4h"),
                days=arguments.get("days", 30)
            )

        elif tool_name == "evaluate_factor":
            return execute_evaluate_factor(
                db, expression=arguments.get("expression", ""),
                symbol=arguments.get("symbol", "BTC"),
                exchange=arguments.get("exchange", "hyperliquid")
            )

        elif tool_name == "save_factor":
            return execute_save_factor(
                db, name=arguments.get("name", ""),
                expression=arguments.get("expression", ""),
                description=arguments.get("description", "")
            )

        elif tool_name == "edit_factor":
            return execute_edit_factor(
                db, factor_id=arguments.get("factor_id"),
                name=arguments.get("name"),
                expression=arguments.get("expression"),
                description=arguments.get("description")
            )

        elif tool_name == "compute_factor":
            return execute_compute_factor(
                db, factor_name=arguments.get("factor_name", ""),
                exchange=arguments.get("exchange", "hyperliquid")
            )

        elif tool_name == "get_factor_functions":
            return execute_get_factor_functions(
                category=arguments.get("category")
            )

        # --- External tools ---
        elif tool_name == "web_search":
            return execute_web_search(
                db, query=arguments.get("query", ""),
                max_results=arguments.get("max_results", 5)
            )

        elif tool_name == "fetch_url":
            return execute_fetch_url(
                url=arguments.get("url", ""),
                max_length=arguments.get("max_length", 8000)
            )

        # --- Delete tools ---
        elif tool_name == "delete_trader":
            from services.entity_deletion_service import delete_trader
            return json.dumps(delete_trader(db, trader_id=arguments.get("trader_id")), indent=2)

        elif tool_name == "delete_prompt_template":
            from services.entity_deletion_service import delete_prompt_template
            return json.dumps(delete_prompt_template(db, prompt_id=arguments.get("prompt_id")), indent=2)

        elif tool_name == "delete_signal_definition":
            from services.entity_deletion_service import delete_signal_definition
            return json.dumps(delete_signal_definition(db, signal_id=arguments.get("signal_id")), indent=2)

        elif tool_name == "delete_signal_pool":
            from services.entity_deletion_service import delete_signal_pool
            return json.dumps(delete_signal_pool(db, pool_id=arguments.get("pool_id")), indent=2)

        elif tool_name == "delete_trading_program":
            from services.entity_deletion_service import delete_trading_program
            return json.dumps(delete_trading_program(db, program_id=arguments.get("program_id")), indent=2)

        elif tool_name == "delete_prompt_binding":
            from services.entity_deletion_service import delete_prompt_binding
            return json.dumps(delete_prompt_binding(db, binding_id=arguments.get("binding_id")), indent=2)

        elif tool_name == "delete_program_binding":
            from services.entity_deletion_service import delete_program_binding
            return json.dumps(delete_program_binding(db, binding_id=arguments.get("binding_id")), indent=2)

        # Sub-agent tools are handled directly in hyper_ai_service.py main loop
        # via _execute_tool_with_progress() which uses yield from for progress events.
        # This branch should not be reached but kept as safety fallback.
        elif tool_name in ("call_prompt_ai", "call_program_ai", "call_signal_ai", "call_attribution_ai"):
            logger.warning(f"[execute_hyper_ai_tool] Sub-agent {tool_name} reached fallback path")
            return execute_subagent_tool(db, tool_name, arguments, user_id=user_id)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        logger.error(f"[execute_hyper_ai_tool] Error executing {tool_name}: {e}")
        return json.dumps({"error": str(e), "_error_class": type(e).__name__})
