# 提示词变量参考

本文档列出了所有可在提示词模板中使用的变量。

---

## 必需变量

| 变量 | 描述 |
|------|------|
| `{output_format}` | **必须包含** - JSON输出格式和格式要求。确保AI返回有效、可解析的JSON。 |
| `{trigger_context}` | **推荐** - 触发上下文信息。告诉AI是什么触发了这次决策（信号或定时），并在信号池触发时提供信号详情。 |

### 触发上下文格式

当由**信号池**触发时：
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

当由**钱包信号**触发时（Hyper Insight 钱包追踪）：
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

钱包信号字段说明：
- `event_type`：position_change, equity_change, funding, transfer, liquidation
- `event_level`：normal, significant, critical
- `tier`（在 summary 前缀中）："Real-time"（付费 WS 实时成交）或 "Polling"（快照对比）
- `action`：open, close, add, reduce, flip, update（仅 position_change）
- `direction`：long, short, flat（仅 position_change）
- 共享仓位字段：`start_position`、`end_position`、`old_value`、`new_value`、`notional_value`
- 可用仓位上下文字段：`entry_price`、`leverage`、`unrealized_pnl`、`liquidation_price`
- 仅实时聚合字段：`average_price`、`closed_pnl`、`fills_count`、`fills`

当由**定时间隔**触发时：
```
=== TRIGGER CONTEXT ===
trigger_type: scheduled
trigger_interval: 150 seconds
```

**为什么要包含这个？** AI在知道以下信息时可以做出更明智的决策：
- 是什么触发了分析（信号 vs 定时检查）
- 哪些具体信号被触发及其值
- 导致触发的市场条件

---

## 基础变量（所有模板）

| 变量 | 描述 | 示例 |
|------|------|------|
| `{trading_environment}` | 当前交易模式描述 | "Platform: Hyperliquid Perpetual Contracts \| Environment: MAINNET" |
| `{available_cash}` | 可用资金（格式化USD） | "$10,000.00" |
| `{total_account_value}` | 账户总价值（格式化USD） | "$12,500.00" |
| `{market_prices}` | 所有交易对当前价格（可读格式） | "BTC: $50,000.00\nETH: $3,000.00" |
| `{news_section}` | 最新加密货币新闻摘要 | "Bitcoin ETF inflows reach..." |
| `{max_leverage}` | 最大允许杠杆 | "10" |

---

## 会话变量（专业模板）

| 变量 | 描述 | 示例 |
|------|------|------|
| `{runtime_minutes}` | 交易开始后的分钟数 | "120" |
| `{current_time_utc}` | 当前UTC时间戳 | "2025-01-15T08:30:00Z" |
| `{total_return_percent}` | 总收益率百分比 | "+5.25" |

---

## 投资组合变量（专业模板）

| 变量 | 描述 | 示例 |
|------|------|------|
| `{holdings_detail}` | 详细持仓信息，包含数量、成本、价值 | "BTC: 0.5 units @ $48,000 avg (current value: $25,000)" |
| `{sampling_data}` | 所有交易对的日内价格序列 | 多行价格历史数据 |
| `{margin_info}` | 保证金模式信息（仅Hyperliquid） | "Margin Mode: Cross margin" |

---

## Hyperliquid变量（实盘交易）

| 变量 | 描述 | 示例 |
|------|------|------|
| `{environment}` | 交易环境 | "mainnet" 或 "testnet" |
| `{total_equity}` | USDC总权益 | "$10,500.00" |
| `{available_balance}` | 可用于交易的余额 | "$8,000.00" |
| `{used_margin}` | 当前使用的保证金 | "$2,500.00" |
| `{margin_usage_percent}` | 保证金使用率百分比 | "23.8" |
| `{maintenance_margin}` | 维持保证金要求 | "$500.00" |
| `{positions_detail}` | 详细持仓信息，包含杠杆、爆仓价、盈亏 | 完整持仓明细 |
| `{recent_trades_summary}` | 最近平仓交易历史 | 最近5笔平仓记录 |
| `{default_leverage}` | 默认杠杆设置 | "3" |
| `{real_trading_warning}` | 风险警告信息 | "REAL MONEY TRADING - All decisions execute on live markets" |
| `{operational_constraints}` | 交易约束和风险规则 | 仓位大小限制、保证金规则 |
| `{leverage_constraints}` | 杠杆相关约束 | "Leverage range: 1x to 10x" |

---

## 订单执行变量（高级）

这些变量控制订单在Hyperliquid上的执行方式。

| 变量 | 描述 | 可选值 | 默认值 |
|------|------|--------|--------|
| `time_in_force` | 订单有效期模式 | "Ioc", "Gtc", "Alo" | "Ioc" |
| `tp_execution` | 止盈执行模式 | "market", "limit" | "limit" |
| `sl_execution` | 止损执行模式 | "market", "limit" | "limit" |

### 订单有效期选项

| 值 | 描述 | 手续费影响 |
|----|------|-----------|
| `Ioc` | 立即成交或取消 - 立即成交或取消未成交部分 | 始终为taker费率 (0.0432%) |
| `Gtc` | 有效直到取消 - 挂单直到成交或取消 | 如果未立即成交可能成为maker (0.0144%) |
| `Alo` | 仅添加流动性（只挂单）- 只添加到订单簿，不吃单 | 始终为maker费率 (0.0144%)，但在快速行情中可能不成交 |

### 止盈/止损执行模式

| 值 | 描述 | 手续费影响 | 风险 |
|----|------|-----------|------|
| `market` | 触发时立即以市价执行 | Taker费率 (0.0432%) | 保证成交 |
| `limit` | 以0.05%偏移价格挂限价单，尝试成为maker | 可能获得maker费率 (0.0144%) | 在快速行情中可能不成交 |

**注意**：止盈limit模式下，系统会添加0.05%的价格偏移：
- 多头止盈（卖出）：`限价 = 触发价 * 1.0005`
- 空头止盈（买入）：`限价 = 触发价 * 0.9995`

这个偏移增加了成为maker订单的机会，同时仍能确保合理的成交概率。

---

## 交易对选择变量

| 变量 | 描述 | 示例 |
|------|------|------|
| `{selected_symbols_csv}` | 逗号分隔的交易对列表 | "BTC, ETH, SOL" |
| `{selected_symbols_detail}` | 详细交易对信息 | "BTC: Bitcoin\nETH: Ethereum" |
| `{selected_symbols_count}` | 选中的交易对数量 | "6" |

---

## K线和技术指标变量（高级）

这些变量根据您的模板动态生成。添加它们以获取技术分析数据。

### 语法

**重要**：`SYMBOL` 是占位符 - 您必须将其替换为实际的交易对名称（BTC、ETH、SOL等）。系统不会自动为您替换 `SYMBOL`。

| 模式 | 您必须写成 | 示例 |
|------|-----------|------|
| `SYMBOL_klines_PERIOD` | 将SYMBOL替换为实际交易对 | `{BTC_klines_15m}`, `{ETH_klines_1h}` |
| `SYMBOL_market_data` | 将SYMBOL替换为实际交易对 | `{BTC_market_data}`, `{SOL_market_data}` |
| `SYMBOL_INDICATOR_PERIOD` | 将SYMBOL替换为实际交易对 | `{BTC_RSI14_15m}`, `{ETH_MACD_1h}` |

**错误写法**（不会显示任何内容）：
```
{SYMBOL_market_data}
{SYMBOL_RSI14_15m}
```

**正确写法**（会显示实际数据）：
```
{BTC_market_data}
{BTC_RSI14_15m}
```

### 支持的周期

`1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1M`

### 支持的指标

| 指标 | 变量示例 | 描述 |
|------|---------|------|
| RSI (14) | `{BTC_RSI14_15m}` | 相对强弱指数（14周期） |
| RSI (7) | `{BTC_RSI7_15m}` | 相对强弱指数（7周期，更快） |
| MACD | `{BTC_MACD_15m}` | MACD线、信号线、柱状图 |
| Stochastic | `{BTC_STOCH_15m}` | 随机指标（%K和%D） |
| MA | `{BTC_MA_15m}` | 移动平均线（MA5、MA10、MA20） |
| EMA | `{BTC_EMA_15m}` | 指数移动平均线（EMA20、EMA50、EMA100） |
| Bollinger | `{BTC_BOLL_15m}` | 布林带（上轨、中轨、下轨） |
| ATR | `{BTC_ATR14_15m}` | 平均真实波幅（波动率） |
| VWAP | `{BTC_VWAP_15m}` | 成交量加权平均价格 |
| OBV | `{BTC_OBV_15m}` | 能量潮指标 |

### 使用示例

在提示词中添加BTC技术分析：

```
=== TECHNICAL ANALYSIS ===
{BTC_market_data}
{BTC_klines_15m}
{BTC_RSI14_15m}
{BTC_MACD_15m}
```

---

## 市场流量指标变量（高级）

市场流量指标提供订单流、成交量差值和市场微观结构的洞察。

### 支持的流量指标

| 指标 | 变量示例 | 描述 |
|------|---------|------|
| CVD | `{BTC_CVD_15m}` | 累积成交量差值（主动买入 - 卖出） |
| TAKER | `{BTC_TAKER_15m}` | 主动买卖成交量和比率 |
| OI | `{BTC_OI_15m}` | 持仓量（绝对值） |
| OI_DELTA | `{BTC_OI_DELTA_15m}` | 持仓量变化百分比 |
| FUNDING | `{BTC_FUNDING_15m}` | 资金费率变化（基点）和当前费率 |
| DEPTH | `{BTC_DEPTH_15m}` | 订单簿深度比率（买/卖） |
| IMBALANCE | `{BTC_IMBALANCE_15m}` | 订单簿失衡度（-1到1） |
| PRICE_CHANGE | `{BTC_PRICE_CHANGE_15m}` | 价格变化百分比。公式：(当前价-前期价)/前期价*100 |
| VOLATILITY | `{BTC_VOLATILITY_15m}` | 价格波动率百分比。公式：(最高价-最低价)/最低价*100 |

### 支持的周期

`1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `8h`, `12h`, `1d`

### 输出格式示例

**CVD（累积成交量差值）**
```
CVD (15m): +$2.34M
CVD last 5: -$0.50M, +$0.80M, +$1.20M, +$0.30M, +$0.54M
Cumulative: +$8.70M
```

**TAKER（主动成交量）**
```
Taker Buy: +$5.20M | Taker Sell: +$2.86M
Buy/Sell Ratio: 1.82x (log: +0.60)
Log Ratio last 5: -0.05, +0.11, +0.37, +0.21, +0.60
```
注：Log ratio = ln(买/卖)。正值 = 买方主导，负值 = 卖方主导。
- +0.69 = 买方是卖方的2倍
- 0 = 平衡
- -0.69 = 卖方是买方的2倍

**OI（持仓量）**
```
Open Interest: +$150.00M
OI last 5: +$148.50M, +$149.00M, +$149.30M, +$149.80M, +$150.00M
```

**OI_DELTA（持仓量变化）**
```
OI Delta (15m): +1.20%
OI Delta last 5: -0.30%, +0.50%, +0.80%, +0.10%, +1.20%
```

**FUNDING（资金费率）**
```
Funding Rate: 12.5 bps (0.0125%)
Funding Change: +3.2 bps (0.0032%)
Annualized: 45.63%
Funding last 5: 10.0, 11.2, 12.0, 10.0, 12.5 bps
```
注：1 bps（基点）= 0.01% = 0.0001。信号基于费率变化触发，而非绝对值。

**DEPTH（订单簿深度）**
```
Bid Depth: +$10.50M | Ask Depth: +$8.20M
Depth Ratio (Bid/Ask): 1.28
Ratio last 5: 1.12, 1.18, 1.25, 1.30, 1.28
Spread: 0.0100
```

**IMBALANCE（订单簿失衡）**
```
Order Imbalance: +0.125
Imbalance last 5: +0.050, +0.080, +0.100, +0.130, +0.125
```

**PRICE_CHANGE（价格变化百分比）**
```
Price Change (15m): +2.35%
Price Change last 5: -0.50%, +0.80%, +1.20%, +0.30%, +2.35%
```

**VOLATILITY（价格波动率）**
```
Volatility (15m): 1.85%
Volatility last 5: 0.60%, 0.90%, 1.20%, 1.50%, 1.85%
```

### 使用示例

在提示词中添加市场流量分析：

```
=== MARKET FLOW ANALYSIS ===
{BTC_CVD_15m}
{BTC_TAKER_15m}
{BTC_OI_1h}
{BTC_FUNDING_1h}
```

---

## 市场状态分类变量（高级）

市场状态变量提供AI可用的当前市场条件分类，将多个流量指标组合成可操作的状态类型。

### 可用变量

| 变量 | 描述 |
|------|------|
| `{market_regime_description}` | 指标计算方法和状态类型定义（为AI上下文包含一次） |
| `{market_regime}` | 所有交易对摘要（默认5分钟周期） |
| `{market_regime_1m}` | 所有交易对摘要（1分钟周期） |
| `{market_regime_5m}` | 所有交易对摘要（5分钟周期） |
| `{market_regime_15m}` | 所有交易对摘要（15分钟周期） |
| `{market_regime_1h}` | 所有交易对摘要（1小时周期） |
| `{market_regime_4h}` | 所有交易对摘要（4小时周期） |
| `{market_regime_1d}` | 所有交易对摘要（日线周期） |
| `{BTC_market_regime}` | 仅BTC状态（默认5分钟） |
| `{BTC_market_regime_1m}` | BTC状态（1分钟） |
| `{BTC_market_regime_5m}` | BTC状态（5分钟） |
| `{BTC_market_regime_15m}` | BTC状态（15分钟） |
| `{BTC_market_regime_1h}` | BTC状态（1小时） |
| `{BTC_market_regime_4h}` | BTC状态（4小时） |
| `{BTC_market_regime_1d}` | BTC状态（日线） |
| `{trigger_market_regime}` | **触发快照**：信号触发时捕获的市场状态。仅在信号触发时可用（定时触发时为N/A）。使用此变量确保AI看到的是触发信号时的市场状态，而非当前实时状态。 |

ETH、SOL和其他支持的交易对也有类似模式。

**重要说明**：`{trigger_market_regime}` 与实时状态变量的区别：
- 实时变量（`{BTC_market_regime_5m}` 等）在提示词生成时计算
- `{trigger_market_regime}` 是信号池触发时的状态快照
- 当你希望AI决策基于触发信号时的确切市场条件时，使用 `{trigger_market_regime}`

### 状态类型

| 状态 | 描述 |
|------|------|
| `breakout` | 带成交量确认的强方向性突破 |
| `absorption` | 大单被吸收但价格未受影响（潜在反转） |
| `stop_hunt` | 突破区间后反转（流动性猎杀） |
| `exhaustion` | 极端RSI伴随CVD背离（趋势减弱） |
| `trap` | 价格突破但CVD/OI背离（假突破） |
| `continuation` | 指标一致的趋势延续 |
| `noise` | 无明确模式，低置信度 |

### 输出格式

```
[BTC/5m] stop_hunt (bullish) conf=0.44 | cvd_ratio=0.286, oi_delta=0.01%, taker=1.80, rsi=50.7
```

- `[SYMBOL/TIMEFRAME]` - 交易对和周期上下文
- `regime (direction)` - 分类的状态类型和方向（看涨/看跌/中性）
- `conf=X.XX` - 置信度分数（0-1）
- 指标值：cvd_ratio、oi_delta、taker比率、RSI

### 指标定义

- **cvd_ratio**: CVD / (主动买入 + 主动卖出)。正值 = 净买入压力
- **oi_delta**: 周期内持仓量变化百分比
- **taker**: 主动买卖比率。>1 = 激进买入，<1 = 激进卖出
- **rsi**: RSI(14)动量指标。>70超买，<30超卖

### 使用示例

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

## 新闻情报变量（市场新闻）

从多个加密新闻源实时采集、AI 分类的市场新闻数据。

### 单币种新闻

| 变量 | 描述 |
|------|------|
| `{BTC_news_sentiment}` | 情绪统计：看涨/看跌/中性数量 |
| `{BTC_news_headlines}` | 标题列表（含时间戳和情绪标签） |
| `{BTC_news_detail}` | 标题 + 新闻摘要（原文或 AI 压缩） |

将 `BTC` 替换为任意币种（ETH、SOL 等）即可获取对应新闻。

### 宏观新闻（经济与地缘政治）

| 变量 | 描述 |
|------|------|
| `{macro_news}` | 宏观新闻标题（美联储、CPI、GDP、关税、地缘政治） |
| `{macro_news_detail}` | 宏观新闻标题 + 摘要 |
| `{macro_news_sentiment}` | 宏观新闻情绪统计 |

### 加密行业新闻（通用，不绑定特定币种）

| 变量 | 描述 |
|------|------|
| `{crypto_news}` | 加密行业通用新闻标题 |
| `{crypto_news_detail}` | 加密行业新闻标题 + 摘要 |
| `{crypto_news_sentiment}` | 加密行业新闻情绪统计 |

### 时间窗口后缀

所有新闻变量默认 **24 小时**，添加后缀可调整：

| 后缀 | 窗口 | 示例 |
|------|------|------|
| `_1h` | 1 小时 | `{BTC_news_headlines_1h}` |
| `_4h` | 4 小时 | `{macro_news_detail_4h}` |
| `_12h` | 12 小时 | `{crypto_news_12h}` |
| `_24h` | 24 小时（默认） | `{BTC_news_sentiment_24h}` |

### 输出格式示例

**情绪统计** (`{BTC_news_sentiment}`):
```
BTC news sentiment (24h): 19 bullish, 20 bearish, 7 neutral (total 46). Dominant: bearish.
```

**标题列表** (`{macro_news}`):
```
Macro news (24h, 51 articles):
[03-20 05:30] [bullish] Bank Executive Reinforces Bolivia's Cryptocurrency Pivot
[03-20 04:30] [neutral] From Trillion-Dollar Chips to Power Grid Stress
[03-19 22:00] [bearish] JPMorgan sees S&P 500 vulnerable as Brent tops $110
...
```

**详细新闻** (`{BTC_news_detail}`):
```
BTC news (24h, 46 articles):
[03-20 02:03] [bullish] Coinbase, Apex Group tokenize Bitcoin Yield Fund on Base
  > Coinbase Asset Management's Anthony Bassili says the Bitcoin Yield Fund's tokenized share class checks "identity and eligibility at the token level" for compliance.
[03-20 01:56] [bearish] Bitcoin Trails Money Supply Growth as Energy Costs and Rates Bite
  > Bitcoin underperforms as high energy costs and restrictive monetary policy weigh on price recovery.
...
```

### 使用示例

轻量级（最少 Token）：
```
=== 市场新闻 ===
{BTC_news_sentiment}
{macro_news_sentiment}
```

标准（推荐）：
```
=== 市场新闻 ===
{BTC_news_headlines}
{macro_news}
{crypto_news}
```

深度分析：
```
=== 市场新闻 ===
{BTC_news_detail}
{ETH_news_detail_4h}
{macro_news_detail}
{crypto_news_detail}
```

---

## Adanos 市场情绪变量（可选）

配置 `ADANOS_API_KEY` 后，Adanos 变量会向提示词注入基于 Reddit 讨论的
外部加密市场情绪数据。如果没有配置 API key，变量会渲染为不可用提示，
不会阻塞提示词生成。

| 变量 | 描述 |
|------|------|
| `{adanos_sentiment}` | 当前选中币种的 Adanos 情绪摘要 |
| `{adanos_sentiment_14d}` | 使用自定义天数窗口的选中币种摘要 |
| `{BTC_adanos_sentiment}` | BTC 专属 Adanos 情绪摘要 |
| `{ETH_adanos_sentiment_30d}` | 使用自定义天数窗口的 ETH 摘要 |

时间窗口后缀使用日历天（`_1d` 到 `_365d`），默认 7 天。

示例：
```
=== 外部情绪 ===
{adanos_sentiment}
{BTC_adanos_sentiment}
```

---

## 遗留变量（向后兼容）

| 变量 | 描述 | 推荐替代 |
|------|------|---------|
| `{account_state}` | 原始账户状态文本 | 使用 `{available_cash}` + `{total_account_value}` |
| `{prices_json}` | JSON格式价格 | 使用 `{market_prices}` |
| `{portfolio_json}` | JSON格式投资组合 | 使用 `{holdings_detail}` |
| `{session_context}` | 遗留会话信息 | 使用 `{runtime_minutes}` + `{current_time_utc}` |

---

## 因子变量（高级）

因子变量将实时因子值和有效性指标注入提示词。

### 格式

`{SYMBOL_factor_PERIOD_NAME}` — 例如 `{BTC_factor_1h_RSI21}`、`{ETH_factor_5m_MOM10}`

旧语法 `{SYMBOL_factor_NAME}` 仍兼容，并默认按 `5m` 计算，但新模板应显式写出 period。

支持的周期：`1m`, `5m`, `15m`, `1h`, `4h`, `1d`。

### 输出内容

每个变量解析为包含因子元数据、时间周期、实时值和有效性的文本：

```
name=RSI21(id=5) | period=1h | expr=RSI(close, 21) | desc=RSI 21周期 | value=0.0234 | IC=0.0512 | ICIR=1.35 | WinRate=52.0% | Persistent
```

- **name(id)**: 因子名称和数据库ID
- **period**: 计算该因子值所使用的 K 线周期
- **expr**: 因子公式表达式
- **desc**: 因子描述
- **value**: 基于指定周期最近 500 根 K 线实时计算的因子值
- **IC**: 信息系数（预测能力，日均值）
- **ICIR**: IC信息比率（IC稳定性，越高越可靠）
- **WinRate**: 因子正确预测方向的天数百分比
- **Decay**: `Persistent`（IC随时间增强，趋势因子）或 `Decay=Xh`（半衰期，小时）

### 内置因子名称

| 名称 | 描述 |
|------|------|
| `RSI14` | RSI(close, 14) |
| `RSI21` | RSI(close, 21) |
| `MOM5` | 5周期动量 |
| `MOM10` | 10周期动量 |
| `VOL_RATIO` | 成交量比率 |
| `REALIZED_VOL10` | 10周期已实现波动率 |
| `HIGH_LOW_RANGE` | (最高 - 最低) / 收盘 |

自定义因子也可使用。使用 `query_factors` 工具查看所有可用因子名称。

### 使用示例

```
当前BTC因子读数：
- RSI21（1h）: {BTC_factor_1h_RSI21}
- 动量（5m）: {BTC_factor_5m_MOM10}
- 波动率（4h）: {BTC_factor_4h_REALIZED_VOL10}

根据因子IC和ICIR判断信号可靠性。持久型因子适合波段策略，短衰减因子适合短线。
```

---

## 需要帮助？

如果您不确定如何使用这些变量或想要更复杂的交易策略，请尝试**AI提示词生成**功能（需要会员）。

AI助手将：
- 根据您的交易风格生成优化的提示词
- 智能选择适当的变量和指标
- 提供专业的风险管理建议
- 支持多轮对话来完善您的策略

点击"AI编写提示词"按钮开始。
