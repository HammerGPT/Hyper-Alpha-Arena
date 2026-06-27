# Prompt Variables Reference

This document lists all available variables you can use in your prompt templates.

---

## Required Variables

| Variable | Description |
|----------|-------------|
| `{output_format}` | **MUST INCLUDE** - JSON output schema and format requirements. Ensures AI returns valid, parseable JSON. |
| `{trigger_context}` | **RECOMMENDED** - Trigger context information. Tells AI what triggered this decision (signal or scheduled) and provides signal details when triggered by signal pool. |

### Trigger Context Format

When triggered by **signal pool**:
```
=== TRIGGER CONTEXT ===
trigger_type: signal
signal_pool_name: OI Surge Monitor
pool_logic: OR
trigger_symbol: BTC
triggered_signals:
  - name: OI Delta Signal
    metric: oi_delta_percent
    condition: > 2.0
    current_value: 3.5
```

When triggered by **wallet signal** (Hyper Insight wallet tracking):
```
=== TRIGGER CONTEXT ===
trigger_type: wallet_signal
signal_pool_name: BTC Whale Tracker
trigger_symbol: ETH
address: 0x84d5c9e6a6944356a01ffc9728610227bd1a670e
event_type: position_change
event_level: significant
summary: Real-time: opened ETH $50,000
action: open
direction: long
notional_value: 50000.0
start_position: 0.0
end_position: 20.0
entry_price: 2500.5
leverage: 10
unrealized_pnl: 420.0
liquidation_price: 2100.0
average_price: 2500.5
closed_pnl: 0.0
fills_count: 5
```

Wallet signal fields:
- `event_type`: position_change, equity_change, funding, transfer, liquidation
- `event_level`: normal, significant, critical
- `tier` (in summary prefix): "Real-time" (paid WS fills) or "Polling" (snapshot diff)
- `action`: open, close, add, reduce, flip, update (position_change only)
- `direction`: long, short, flat (position_change only)
- Shared position fields: `start_position`, `end_position`, `old_value`, `new_value`, `notional_value`
- Position context when available: `entry_price`, `leverage`, `unrealized_pnl`, `liquidation_price`
- Realtime-only fields: `average_price`, `closed_pnl`, `fills_count`, `fills`

When triggered by **scheduled interval**:
```
=== TRIGGER CONTEXT ===
trigger_type: scheduled
trigger_interval: 150 seconds
```

**Why include this?** The AI can make more informed decisions when it knows:
- What triggered the analysis (signal vs scheduled check)
- Which specific signals fired and their values
- The market conditions that caused the trigger

---

## Basic Variables (All Templates)

| Variable | Description | Example |
|----------|-------------|---------|
| `{trading_environment}` | Current trading mode description | "Platform: Hyperliquid Perpetual Contracts \| Environment: MAINNET" |
| `{available_cash}` | Available cash (formatted USD) | "$10,000.00" |
| `{total_account_value}` | Total account value (formatted USD) | "$12,500.00" |
| `{market_prices}` | Current prices for all symbols (readable format) | "BTC: $50,000.00\nETH: $3,000.00" |
| `{news_section}` | Latest crypto news summary | "Bitcoin ETF inflows reach..." |
| `{max_leverage}` | Maximum allowed leverage | "10" |

---

## Session Variables (Pro Template)

| Variable | Description | Example |
|----------|-------------|---------|
| `{runtime_minutes}` | Minutes since trading started | "120" |
| `{current_time_utc}` | Current UTC timestamp | "2025-01-15T08:30:00Z" |
| `{total_return_percent}` | Total return percentage | "+5.25" |

---

## Portfolio Variables (Pro Template)

| Variable | Description | Example |
|----------|-------------|---------|
| `{holdings_detail}` | Detailed holdings with quantity, cost, value | "BTC: 0.5 units @ $48,000 avg (current value: $25,000)" |
| `{sampling_data}` | Intraday price series for all symbols | Multi-line price history data |
| `{margin_info}` | Margin mode information (Hyperliquid only) | "Margin Mode: Cross margin" |

---

## Hyperliquid Variables (Real Trading)

| Variable | Description | Example |
|----------|-------------|---------|
| `{environment}` | Trading environment | "mainnet" or "testnet" |
| `{total_equity}` | Total equity in USDC | "$10,500.00" |
| `{available_balance}` | Available balance for trading | "$8,000.00" |
| `{used_margin}` | Margin currently in use | "$2,500.00" |
| `{margin_usage_percent}` | Margin usage percentage | "23.8" |
| `{maintenance_margin}` | Maintenance margin requirement | "$500.00" |
| `{positions_detail}` | Detailed open positions with leverage, liquidation price, PnL | Full position breakdown |
| `{recent_trades_summary}` | Recent closed trades history | Last 5 closed positions |
| `{default_leverage}` | Default leverage setting | "3" |
| `{real_trading_warning}` | Risk warning message | "REAL MONEY TRADING - All decisions execute on live markets" |
| `{operational_constraints}` | Trading constraints and risk rules | Position size limits, margin rules |
| `{leverage_constraints}` | Leverage-specific constraints | "Leverage range: 1x to 10x" |

---

## Order Execution Variables (Advanced)

These variables control how orders are executed on Hyperliquid.

| Variable | Description | Values | Default |
|----------|-------------|--------|---------|
| `time_in_force` | Order time-in-force mode | "Ioc", "Gtc", "Alo" | "Ioc" |
| `tp_execution` | Take profit execution mode | "market", "limit" | "limit" |
| `sl_execution` | Stop loss execution mode | "market", "limit" | "limit" |

### Time-in-Force Options

| Value | Description | Fee Impact |
|-------|-------------|------------|
| `Ioc` | Immediate or Cancel - fills immediately or cancels unfilled portion | Always taker fee (0.0432%) |
| `Gtc` | Good Til Canceled - remains on order book until filled or canceled | May become maker (0.0144%) if not immediately filled |
| `Alo` | Add Liquidity Only (Post-Only) - only adds to order book, never takes | Always maker fee (0.0144%), but may not fill in fast markets |

### TP/SL Execution Modes

| Value | Description | Fee Impact | Risk |
|-------|-------------|------------|------|
| `market` | Executes immediately at market price when triggered | Taker fee (0.0432%) | Guaranteed fill |
| `limit` | Places limit order with 0.05% offset to attempt maker status | May get maker fee (0.0144%) | May not fill in fast markets |

**Note**: For TP limit mode, the system adds a 0.05% price offset:
- Long position TP (sell): `limit_price = trigger_price * 1.0005`
- Short position TP (buy): `limit_price = trigger_price * 0.9995`

This offset increases the chance of becoming a maker order while still ensuring reasonable fill probability.

---

## Symbol Selection Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{selected_symbols_csv}` | Comma-separated symbol list | "BTC, ETH, SOL" |
| `{selected_symbols_detail}` | Detailed symbol information | "BTC: Bitcoin\nETH: Ethereum" |
| `{selected_symbols_count}` | Number of selected symbols | "6" |

---

## K-line and Technical Indicator Variables (Advanced)

These variables are dynamically generated based on your template. Add them to get technical analysis data.

### Syntax

**IMPORTANT**: `SYMBOL` is a placeholder - you must replace it with actual symbol names (BTC, ETH, SOL, etc.). The system will NOT auto-replace `SYMBOL` for you.

| Pattern | You Must Write | Example |
|---------|----------------|---------|
| `SYMBOL_klines_PERIOD` | Replace SYMBOL with actual symbol | `{BTC_klines_15m}`, `{ETH_klines_1h}` |
| `SYMBOL_market_data` | Replace SYMBOL with actual symbol | `{BTC_market_data}`, `{SOL_market_data}` |
| `SYMBOL_INDICATOR_PERIOD` | Replace SYMBOL with actual symbol | `{BTC_RSI14_15m}`, `{ETH_MACD_1h}` |

**Wrong** (will show nothing):
```
{SYMBOL_market_data}
{SYMBOL_RSI14_15m}
```

**Correct** (will show actual data):
```
{BTC_market_data}
{BTC_RSI14_15m}
```

### Supported Periods

`1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1M`

### Supported Indicators

| Indicator | Variable Example | Description |
|-----------|------------------|-------------|
| RSI (14) | `{BTC_RSI14_15m}` | Relative Strength Index (14-period) |
| RSI (7) | `{BTC_RSI7_15m}` | Relative Strength Index (7-period, faster) |
| MACD | `{BTC_MACD_15m}` | MACD line, signal line, histogram |
| Stochastic | `{BTC_STOCH_15m}` | Stochastic Oscillator (%K and %D) |
| MA | `{BTC_MA_15m}` | Moving Averages (MA5, MA10, MA20) |
| EMA | `{BTC_EMA_15m}` | Exponential MAs (EMA20, EMA50, EMA100) |
| Bollinger | `{BTC_BOLL_15m}` | Bollinger Bands (upper, middle, lower) |
| ATR | `{BTC_ATR14_15m}` | Average True Range (volatility) |
| VWAP | `{BTC_VWAP_15m}` | Volume Weighted Average Price |
| OBV | `{BTC_OBV_15m}` | On-Balance Volume |

### Example Usage

To add BTC technical analysis to your prompt:

```
=== TECHNICAL ANALYSIS ===
{BTC_market_data}
{BTC_klines_15m}
{BTC_RSI14_15m}
{BTC_MACD_15m}
```

---

## Market Flow Indicator Variables (Advanced)

Market flow indicators provide insights into order flow, volume delta, and market microstructure.

### Supported Flow Indicators

| Indicator | Variable Example | Description |
|-----------|------------------|-------------|
| CVD | `{BTC_CVD_15m}` | Cumulative Volume Delta (Taker Buy - Sell) |
| TAKER | `{BTC_TAKER_15m}` | Taker Buy/Sell Volume and Ratio |
| OI | `{BTC_OI_15m}` | Open Interest (absolute value) |
| OI_DELTA | `{BTC_OI_DELTA_15m}` | Open Interest Change % |
| FUNDING | `{BTC_FUNDING_15m}` | Funding Rate Change (bps) and Current Rate |
| DEPTH | `{BTC_DEPTH_15m}` | Order Book Depth Ratio (Bid/Ask) |
| IMBALANCE | `{BTC_IMBALANCE_15m}` | Order Book Imbalance (-1 to 1) |
| PRICE_CHANGE | `{BTC_PRICE_CHANGE_15m}` | Price Change % over time window. Formula: (current-prev)/prev*100 |
| VOLATILITY | `{BTC_VOLATILITY_15m}` | Price Volatility % over time window. Formula: (high-low)/low*100 |

### Supported Periods

`1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `8h`, `12h`, `1d`

### Output Format Examples

**CVD (Cumulative Volume Delta)**
```
CVD (15m): +$2.34M
CVD last 5: -$0.50M, +$0.80M, +$1.20M, +$0.30M, +$0.54M
Cumulative: +$8.70M
```

**TAKER (Taker Volume)**
```
Taker Buy: +$5.20M | Taker Sell: +$2.86M
Buy/Sell Ratio: 1.82x (log: +0.60)
Log Ratio last 5: -0.05, +0.11, +0.37, +0.21, +0.60
```
Note: Log ratio = ln(buy/sell). Positive = buyers dominate, negative = sellers dominate.
- +0.69 = buyers 2x sellers
- 0 = balanced
- -0.69 = sellers 2x buyers

**OI (Open Interest)**
```
Open Interest: +$150.00M
OI last 5: +$148.50M, +$149.00M, +$149.30M, +$149.80M, +$150.00M
```

**OI_DELTA (Open Interest Change)**
```
OI Delta (15m): +1.20%
OI Delta last 5: -0.30%, +0.50%, +0.80%, +0.10%, +1.20%
```

**FUNDING (Funding Rate)**
```
Funding Rate: 12.5 bps (0.0125%)
Funding Change: +3.2 bps (0.0032%)
Annualized: 45.63%
Funding last 5: 10.0, 11.2, 12.0, 10.0, 12.5 bps
```
Note: 1 bps (basis point) = 0.01% = 0.0001. Signal triggers on rate CHANGE, not absolute value.

**DEPTH (Order Book Depth)**
```
Bid Depth: +$10.50M | Ask Depth: +$8.20M
Depth Ratio (Bid/Ask): 1.28
Ratio last 5: 1.12, 1.18, 1.25, 1.30, 1.28
Spread: 0.0100
```

**IMBALANCE (Order Book Imbalance)**
```
Order Imbalance: +0.125
Imbalance last 5: +0.050, +0.080, +0.100, +0.130, +0.125
```

**PRICE_CHANGE (Price Change Percentage)**
```
Price Change (15m): +2.35%
Price Change last 5: -0.50%, +0.80%, +1.20%, +0.30%, +2.35%
```

**VOLATILITY (Price Volatility)**
```
Volatility (15m): 1.85%
Volatility last 5: 0.60%, 0.90%, 1.20%, 1.50%, 1.85%
```

### Example Usage

To add market flow analysis to your prompt:

```
=== MARKET FLOW ANALYSIS ===
{BTC_CVD_15m}
{BTC_TAKER_15m}
{BTC_OI_1h}
{BTC_FUNDING_1h}
```

---

## Market Regime Classification Variables (Advanced)

Market Regime variables provide AI-ready classification of current market conditions, combining multiple flow indicators into actionable regime types.

### Available Variables

| Variable | Description |
|----------|-------------|
| `{market_regime_description}` | Indicator calculation methodology and regime type definitions (include once for AI context) |
| `{market_regime}` | All symbols summary (default 5m timeframe) |
| `{market_regime_1m}` | All symbols summary (1-minute timeframe) |
| `{market_regime_5m}` | All symbols summary (5-minute timeframe) |
| `{market_regime_15m}` | All symbols summary (15-minute timeframe) |
| `{market_regime_1h}` | All symbols summary (1-hour timeframe) |
| `{market_regime_4h}` | All symbols summary (4-hour timeframe) |
| `{market_regime_1d}` | All symbols summary (1-day timeframe) |
| `{BTC_market_regime}` | BTC regime only (default 5m) |
| `{BTC_market_regime_1m}` | BTC regime (1-minute) |
| `{BTC_market_regime_5m}` | BTC regime (5-minute) |
| `{BTC_market_regime_15m}` | BTC regime (15-minute) |
| `{BTC_market_regime_1h}` | BTC regime (1-hour) |
| `{BTC_market_regime_4h}` | BTC regime (4-hour) |
| `{BTC_market_regime_1d}` | BTC regime (1-day) |
| `{trigger_market_regime}` | **Trigger Snapshot**: The market regime captured at signal trigger time. Only available for signal triggers (N/A for scheduled triggers). Use this to ensure AI sees the same regime that caused the trigger, not the current real-time regime. |

Similar patterns available for ETH, SOL, and other supported symbols.

**Important**: `{trigger_market_regime}` differs from real-time regime variables:
- Real-time variables (`{BTC_market_regime_5m}`, etc.) are calculated at prompt generation time
- `{trigger_market_regime}` is the regime snapshot from when the signal pool triggered
- Use `{trigger_market_regime}` when you want AI decisions to be based on the exact market conditions that triggered the signal

### Regime Types

| Regime | Description |
|--------|-------------|
| `breakout` | Strong directional move with volume confirmation |
| `absorption` | Large orders absorbed without price impact (potential reversal) |
| `stop_hunt` | Wick beyond range then reversal (liquidity grab) |
| `exhaustion` | Extreme RSI with diverging CVD (trend weakening) |
| `trap` | Price breaks level but CVD/OI diverge (false breakout) |
| `continuation` | Trend continuation with aligned indicators |
| `noise` | No clear pattern, low conviction |

### Output Format

```
[BTC/5m] stop_hunt (bullish) conf=0.44 | cvd_ratio=0.286, oi_delta=0.01%, taker=1.80, rsi=50.7
```

- `[SYMBOL/TIMEFRAME]` - Symbol and timeframe context
- `regime (direction)` - Classified regime type and direction (bullish/bearish/neutral)
- `conf=X.XX` - Confidence score (0-1)
- Indicator values: cvd_ratio, oi_delta, taker ratio, RSI

### Indicator Definitions

- **cvd_ratio**: CVD / (Taker Buy + Taker Sell). Positive = net buying pressure
- **oi_delta**: Open Interest change percentage over the period
- **taker**: Taker Buy/Sell ratio. >1 = aggressive buying, <1 = aggressive selling
- **rsi**: RSI(14) momentum indicator. >70 overbought, <30 oversold

### Example Usage

```
=== MARKET REGIME ANALYSIS ===
{market_regime_description}

Current Market Regimes:
{market_regime_5m}

Hourly Context:
{BTC_market_regime_1h}
{ETH_market_regime_1h}
```

---

## News Intelligence Variables (Market News)

Real-time news sentiment and headlines from multiple crypto news sources, classified by AI.

### Per-Symbol News

| Variable | Description |
|----------|-------------|
| `{BTC_news_sentiment}` | Sentiment stats: bullish/bearish/neutral counts |
| `{BTC_news_headlines}` | Headlines with timestamps and sentiment tags |
| `{BTC_news_detail}` | Headlines + article summaries (original text or AI-compressed) |

Replace `BTC` with any symbol (ETH, SOL, etc.) to get news for that specific coin.

### Macro News (Economic & Geopolitical)

| Variable | Description |
|----------|-------------|
| `{macro_news}` | Macro headlines (Fed, CPI, GDP, tariffs, geopolitics) |
| `{macro_news_detail}` | Macro headlines + summaries |
| `{macro_news_sentiment}` | Macro sentiment stats |

### Crypto Industry News (General, Not Coin-Specific)

| Variable | Description |
|----------|-------------|
| `{crypto_news}` | General crypto industry headlines |
| `{crypto_news_detail}` | Crypto industry headlines + summaries |
| `{crypto_news_sentiment}` | Crypto industry sentiment stats |

### Time Window Suffixes

All news variables default to **24 hours**. Add a suffix to change:

| Suffix | Window | Example |
|--------|--------|---------|
| `_1h` | 1 hour | `{BTC_news_headlines_1h}` |
| `_4h` | 4 hours | `{macro_news_detail_4h}` |
| `_12h` | 12 hours | `{crypto_news_12h}` |
| `_24h` | 24 hours (default) | `{BTC_news_sentiment_24h}` |

### Output Format Examples

**Sentiment** (`{BTC_news_sentiment}`):
```
BTC news sentiment (24h): 19 bullish, 20 bearish, 7 neutral (total 46). Dominant: bearish.
```

**Headlines** (`{macro_news}`):
```
Macro news (24h, 51 articles):
[03-20 05:30] [bullish] Bank Executive Reinforces Bolivia's Cryptocurrency Pivot
[03-20 04:30] [neutral] From Trillion-Dollar Chips to Power Grid Stress: AI's Breakneck Week
[03-19 22:00] [bearish] JPMorgan sees S&P 500 vulnerable as Brent tops $110
...
```

**Detail** (`{BTC_news_detail}`):
```
BTC news (24h, 46 articles):
[03-20 02:03] [bullish] Coinbase, Apex Group tokenize Bitcoin Yield Fund on Base
  > Coinbase Asset Management's Anthony Bassili says the Bitcoin Yield Fund's tokenized share class checks "identity and eligibility at the token level" for compliance.
[03-20 01:56] [bearish] Bitcoin Trails Money Supply Growth as Energy Costs and Rates Bite
  > Bitcoin underperforms as high energy costs and restrictive monetary policy weigh on price recovery.
...
```

### Example Usage

Lightweight (minimal tokens):
```
=== MARKET NEWS ===
{BTC_news_sentiment}
{macro_news_sentiment}
```

Standard (recommended):
```
=== MARKET NEWS ===
{BTC_news_headlines}
{macro_news}
{crypto_news}
```

Deep analysis:
```
=== MARKET NEWS ===
{BTC_news_detail}
{ETH_news_detail_4h}
{macro_news_detail}
{crypto_news_detail}
```

---

## Adanos Market Sentiment Variables (Optional)

Adanos variables add external crypto market sentiment from Reddit discussion
when `ADANOS_API_KEY` is configured. If the key is missing, these variables
resolve to an unavailable message and the prompt continues rendering.

| Variable | Description |
|----------|-------------|
| `{adanos_sentiment}` | Sentiment summary for the selected symbols |
| `{adanos_sentiment_14d}` | Selected-symbol summary using a custom lookback in days |
| `{BTC_adanos_sentiment}` | BTC-specific Adanos sentiment summary |
| `{ETH_adanos_sentiment_30d}` | ETH-specific summary using a custom lookback |

Lookback suffixes use calendar days (`_1d` to `_365d`). The default is 7 days.

Example:
```
=== EXTERNAL SENTIMENT ===
{adanos_sentiment}
{BTC_adanos_sentiment}
```

---

## Legacy Variables (Backward Compatibility)

| Variable | Description | Recommended Alternative |
|----------|-------------|------------------------|
| `{account_state}` | Raw account state text | Use `{available_cash}` + `{total_account_value}` |
| `{prices_json}` | Prices in JSON format | Use `{market_prices}` |
| `{portfolio_json}` | Portfolio in JSON format | Use `{holdings_detail}` |
| `{session_context}` | Legacy session info | Use `{runtime_minutes}` + `{current_time_utc}` |

---

## Factor Variables (Advanced)

Factor variables inject real-time factor values and effectiveness metrics into your prompt.

### Format

`{SYMBOL_factor_PERIOD_NAME}` — e.g., `{BTC_factor_1h_RSI21}`, `{ETH_factor_5m_MOM10}`

Legacy syntax `{SYMBOL_factor_NAME}` still works and defaults to `5m`, but new templates should always specify the period explicitly.

Supported periods: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`.

### Output Content

Each variable resolves to a text block with factor metadata, period, real-time value, and effectiveness:

```
name=RSI21(id=5) | period=1h | expr=RSI(close, 21) | desc=RSI with 21-period lookback | value=0.0234 | IC=0.0512 | ICIR=1.35 | WinRate=52.0% | Persistent
```

- **name(id)**: Factor name and database ID
- **period**: K-line period used to compute the factor value
- **expr**: Factor expression formula
- **desc**: Human-readable description
- **value**: Real-time factor value computed from the latest 500 K-lines of the specified period
- **IC**: Information Coefficient (predictive power, daily average)
- **ICIR**: IC Information Ratio (IC stability, higher = more reliable)
- **WinRate**: Percentage of days factor correctly predicted direction
- **Decay**: `Persistent` (IC strengthens over time) or `Decay=Xh` (half-life in hours)

### Built-in Factor Names

| Name | Description |
|------|-------------|
| `RSI14` | RSI(close, 14) |
| `RSI21` | RSI(close, 21) |
| `MOM5` | Rate of change over 5 periods |
| `MOM10` | Rate of change over 10 periods |
| `SKEW20` | Return skewness over 20 periods |
| `KURT20` | Return kurtosis over 20 periods |
| `VOL_RATIO` | Volume ratio (current / 20-period avg) |
| `ILLIQ20` | Amihud illiquidity measure |
| `REALIZED_VOL10` | Realized volatility over 10 periods |
| `REALIZED_VOL30` | Realized volatility over 30 periods |
| `HIGH_LOW_RANGE` | (High - Low) / Close |

Custom factors created in the Factor Library also work. Use the `query_factors` tool (in Prompt AI or Hyper AI) to see all available factor names.

### Example Usage

```
Current factor readings for BTC:
- RSI21 (1h): {BTC_factor_1h_RSI21}
- Momentum (5m): {BTC_factor_5m_MOM10}
- Volatility (4h): {BTC_factor_4h_REALIZED_VOL10}

Use factor IC and ICIR to gauge signal reliability. Persistent factors are suitable for swing strategies; short-decay factors for scalping.
```

---

## Need Help?

If you're unsure how to use these variables or want a more sophisticated trading strategy, try the **AI Prompt Generation** feature (requires membership).

The AI assistant will:
- Generate optimized prompts based on your trading style
- Intelligently select appropriate variables and indicators
- Provide professional risk management suggestions
- Support multi-turn conversations to refine your strategy

Click "AI Write Prompt" button to get started.
