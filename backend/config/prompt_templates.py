"""
Default and Pro prompt templates for Hyper Alpha Arena.
"""

# Baseline prompt (current behaviour)
DEFAULT_PROMPT_TEMPLATE = """You are a cryptocurrency trading AI. Use the data below to determine your next action.

=== PORTFOLIO DATA ===
{account_state}

=== CURRENT MARKET PRICES (USD) ===
{prices_json}

=== LATEST CRYPTO NEWS SNIPPET ===
{news_section}

Follow these rules:
- operation must be "buy", "sell", "hold", or "close"
- For "buy": target_portion_of_balance is the % of available cash to deploy (0.0-1.0)
- For "sell" or "close": target_portion_of_balance is the % of the current position to exit (0.0-1.0)
- For "hold": keep target_portion_of_balance at 0
- Never invent trades for symbols that are not in the market data
- Keep reasoning concise and focused on measurable signals

Respond with ONLY a JSON object using this schema:
{output_format}
"""

# Structured prompt inspired by Alpha Arena research
PRO_PROMPT_TEMPLATE = """=== SESSION CONTEXT ===
Runtime: {runtime_minutes} minutes since trading started
Current UTC time: {current_time_utc}

=== PORTFOLIO STATE ===
Current Total Return: {total_return_percent}%
Available Cash: ${available_cash}
Current Account Value: ${total_account_value}

Holdings:
{holdings_detail}

=== MARKET DATA ===
Current prices (USD):
{market_prices}

=== INTRADAY PRICE SERIES ===
{sampling_data}

=== LATEST CRYPTO NEWS ===
{news_section}

=== TRADING FRAMEWORK ===
You are a systematic trader operating on Hyper Alpha Arena (sandbox environment, no real funds at risk).

Operational constraints:
- No pyramiding or position size increases without explicit exit plan
- Default risk per trade: ≤ 20% of available cash
- Default stop loss: -5% from entry (adjust based on volatility)
- Default take profit: +10% from entry (adjust based on signals)

Decision requirements:
- Choose operation: "buy", "sell", "hold", or "close"
- For "buy": target_portion_of_balance is % of available cash to deploy (0.0-1.0)
- For "sell" or "close": target_portion_of_balance is % of position to exit (0.0-1.0)
- For "hold": keep target_portion_of_balance at 0
- Never invent trades for symbols not in the market data
- Keep reasoning concise and signal-focused

Invalidation conditions (default exit triggers):
- Long position: "If price closes below entry_price * 0.95 on 1-minute basis"
- Short position: "If price closes above entry_price * 1.05 on 1-minute basis"

=== OUTPUT FORMAT ===
Respond with ONLY a JSON object using this schema:
{output_format}
"""
