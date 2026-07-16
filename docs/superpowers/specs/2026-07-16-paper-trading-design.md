# 纸交易通道（Paper Trading）设计文档

- 日期：2026-07-16
- 状态：已与用户逐段确认
- 范围：AI 交易员 + 程序化交易员

## 1. 背景与目标

Hyper Alpha Arena 目前支持 Hyperliquid（testnet/mainnet）与 Binance Futures 的真实下单。本设计新增一条**纯纸交易通道**：

- 行情、订单簿、资金费率全部来自交易员所选交易所的**主网公开数据**（只读，不需要任何钱包/API 密钥）
- 订单执行完全由系统内部的持久化纸交易引擎完成，**考虑真实滑点与手续费**
- 决策链路、归因分析、数据看板与实盘共用同一套口径，纸交易结果可直接与实盘对比

### 非目标（本期不做）

- 手动交易页面的纸交易下单
- 逐仓（isolated）保证金模式模拟（系统现状以全仓 cross 为主）
- 交易所 WebSocket 实时订阅（用高频轮询 + K 线补洞替代）

## 2. 已确认的设计决策

| # | 决策点 | 结论 |
|---|--------|------|
| 1 | 行情数据源 | 跟随交易员所选交易所（Hyperliquid / Binance）的主网公开 API |
| 2 | 覆盖范围 | AI 交易员 + 程序化交易员 |
| 3 | 数据建模 | paper 作为新**环境**值（testnet / mainnet / paper），交易所维度保留 |
| 4 | 滑点 | 主网 L2 订单簿逐档撮合（walk the book）+ 固定百分比回退 |
| 5 | 费用 | 真实 maker/taker 费率表（HL taker 0.045%/maker 0.015%；Binance taker 0.05%/maker 0.02%，可按账户覆盖）+ 模拟 funding 结算 |
| 6 | 挂单/TP/SL 触发 | 独立高频轮询（3-5 秒）+ 1 分钟 K 线高低点补洞 |
| 7 | 强平 | 全仓（cross）清算模拟 |
| 8 | 资金 | 初始资金可配置（默认 $10,000）；重置开新周期、历史保留 |
| 9 | UI | 策略配置加"执行模式"开关（实盘/纸交易）；纸交易账户卡片；不受全局 Testnet/Mainnet 切换影响 |
| 10 | 看板 | 资产曲线 / Arena / 排行同台展示，带 PAPER 标识 |
| 11 | 架构 | 方案 A：PaperTradingClient 适配器 + 持久化引擎（与真实 client 同接口） |

## 3. 总体架构

### 3.1 新增模块 `backend/paper_trading/`

| 组件 | 职责 |
|------|------|
| `client.py` — PaperTradingClient | 与 `HyperliquidTradingClient` / `BinanceTradingClient` 同接口的适配器：`get_account_state`、`get_positions`、`place_order_with_tpsl`、`close_position`、`cancel_order`、`get_open_orders` 等，返回结构与真实 client 逐字段对齐 |
| `engine.py` — PaperEngine | 核心撮合与记账：开/平/加仓、反向净额、保证金校验、已实现盈亏，全部持久化 |
| `monitor.py` — PaperMonitor | 后台服务：高频轮询有持仓/挂单的币种价格（默认 3 秒，可配置），触发 TP/SL、GTC 限价成交、清算检查；周期性 funding 结算；每 60 秒写权益快照 |
| `slippage.py` | 实时拉主网 L2 订单簿逐档撮合计算成交均价，失败回退固定百分比 |
| `fees.py` | maker/taker 费率表（按数据源交易所取默认，可账户级覆盖）+ funding 结算计算 |

### 3.2 数据流（AI 交易员，程序化交易员同理）

1. 信号池/定时触发交易员 —— 现有逻辑不变
2. 交易管线检查 `AccountStrategyConfig.execution_mode`：`"paper"` → 使用 `PaperTradingClient`，跳过钱包校验与 Binance 配额检查，environment 记为 `"paper"`
3. `get_account_state` / `get_positions` 从纸交易表读取，未实现盈亏用主网实时价计算——AI 看到的上下文口径与实盘一致
4. LLM 决策、决策校验、仓位计算 —— 现有逻辑不变
5. `place_order_with_tpsl` → PaperEngine：拉主网订单簿撮合 → 扣手续费 → 更新持仓/余额 → 注册独立 TP/SL 挂单 → 返回与真实 client 相同结构的结果（`{status: 'filled', order_id: 'P-xxx', average_price, fee, ...}`）
6. 管线照常写 `AIDecisionLog`（hyperliquid_environment="paper"）与成交记录（`HyperliquidTrade`，environment="paper"）
7. PaperMonitor 持续运行：TP/SL 触发写成交记录并回填决策 `realized_pnl`；每 60 秒写权益快照

**关键原则**：纸交易与实盘共享同一条决策-执行-记录-归因链路，唯一分叉点是"client 是谁"。

## 4. 数据模型

### 4.1 新增表（主库）

**`paper_accounts`** — 每个交易员一个纸交易账户
- `id`、`account_id`（FK accounts.id，唯一）
- `data_exchange`（"hyperliquid" | "binance"，跟随策略配置）
- `initial_capital` DECIMAL，默认 10000
- `realized_pnl_total`、`total_fees`、`total_funding` DECIMAL
- `cycle` INT（周期号，重置 +1）、`cycle_started_at`
- 费率覆盖：`taker_fee_pct`、`maker_fee_pct`、`slippage_fallback_pct`（NULL = 交易所默认）
- 权益公式（与回测引擎、Hyperliquid Account Value 口径一致）：
  `equity = initial_capital + realized_pnl_total + unrealized_pnl(实时) - total_fees + total_funding`

**`paper_positions`** — 当前持仓
- `paper_account_id`、`symbol`、`side`（long/short）、`size`、`entry_price`（加仓加权平均）、`leverage`、`opened_at`、`cycle`

**`paper_orders`** — 挂单（GTC 限价单 + TP/SL 条件单）
- `order_no`（"P-{uuid}"，写入决策日志 order_id 字段用于归因关联）
- `order_type`（"limit" | "take_profit" | "stop_loss"）、`trigger_price`、`size`、`entry_price`（TP/SL 计算盈亏）、`reduce_only`、`time_in_force`、`status`（pending/filled/cancelled）、`cycle`
- TP/SL 为独立挂单（每笔开仓各带各的），与实盘及回测引擎行为一致

**`paper_funding_records`** — funding 结算流水
- `paper_account_id`、`symbol`、`funding_rate`、`position_notional`、`amount`（正=收入）、`settled_at`、`cycle`

### 4.2 复用现有表

- 成交记录 → `HyperliquidTrade`（快照库），`environment="paper"`——归因手续费查询（按 order_id 关联）零改动生效
- 权益快照 → `HyperliquidAccountSnapshot`（快照库），`environment="paper"`——资产曲线链路复用
- 决策日志 → `AIDecisionLog.hyperliquid_environment="paper"`、`ProgramExecutionLog.environment="paper"`；`exchange` 字段保留真实数据源（hyperliquid/binance）

### 4.3 现有表字段变更（仅一处）

- `account_strategy_configs` 新增 `execution_mode` VARCHAR(10)，"real" | "paper"，默认 "real"（迁移脚本走现有 migration_manager）

## 5. 撮合与记账规则

| 场景 | 规则 |
|------|------|
| 市价/IOC 单 | 拉主网 L2 订单簿逐档吃单计算加权均价；深度不足部分按最差档价加回退滑点；订单簿拉取失败整单按 `最新价 ± slippage_fallback_pct`（默认 0.05%） |
| GTC 限价单 | 立即可成交则按订单簿撮合且不劣于限价（taker 费率）；否则入 `paper_orders`，监控服务在价格穿越时成交（maker 费率） |
| TP（limit 执行） | 触发价成交，maker 费率 |
| SL / TP（market 执行） | 触发价 + 滑点成交，taker 费率 |
| 反向开仓 | 净额处理：先平旧仓（实现盈亏），剩余量反向开新仓——与 Hyperliquid 净额持仓一致 |
| 加仓 | 同方向加仓按加权平均更新 entry_price；新加部分的 TP/SL 独立挂单 |
| 保证金校验 | 所需保证金 = 名义价值 / 杠杆；可用余额不足拒单，错误返回结构与真实 client 一致 |
| 全仓清算 | 维持保证金 = 已用保证金 × 50%（与现有代码对 Hyperliquid 的估算口径一致）；`equity < 维持保证金` 时按市价+滑点强平全部持仓，成交记录标注 liquidation |
| Funding | Hyperliquid 每 1 小时 / Binance 每 8 小时，用系统已采集的实时资金费率：`金额 = 持仓名义价值 × 费率 × 方向`，计入 `total_funding` 并写流水 |

## 6. 管线集成

### 6.1 AI 交易员（`services/trading_commands.py`）

`place_ai_driven_hyperliquid_order` / `place_ai_driven_binance_order` 在获取 client 处加分支：

```python
if strategy.execution_mode == "paper":
    client = PaperTradingClient(account_id, data_exchange)
    environment = "paper"
    # 跳过钱包配置校验、跳过 Binance 每日配额检查
```

- 行情/提示词上下文固定用 mainnet 数据
- 其余逻辑（决策、校验、sizing、IOC→GTC 回退、日志写入）全部复用

### 6.2 程序化交易员（`services/program_execution_service.py`）

两处 client 创建点（约 L340-372、L860-901）加相同分支。

### 6.3 全局 Testnet/Mainnet 切换

对 paper 账户无效——paper 账户始终用主网行情，不参与全局环境切换。

### 6.4 盈亏回填

- 平仓类决策：PaperEngine 平仓瞬间算出已实现盈亏，直接写回决策日志 `realized_pnl` / `pnl_updated_at`，无需等用户刷新
- TP/SL 触发：监控服务成交时按 `order_no` 反查决策日志（`tp_order_id` / `sl_order_id`），回填盈亏与触发时间
- 现有"刷新盈亏"端点（arena_routes `update_pnl_data`）加 paper 分支：查纸交易成交表而非交易所 fills API

## 7. 归因分析集成

- `analytics_routes.build_base_query` 按 `hyperliquid_environment` 过滤——"paper" 值天然流转，后端查询零改动
- 手续费关联（`get_fees_for_decisions` 按 order_id 查 `HyperliquidTrade`）零改动
- Attribution AI（`ai_attribution_service.py`）：系统提示词环境枚举加 "paper"，工具参数说明同步更新
- 前端归因页环境筛选器加 **Paper** 选项（全部/Mainnet/Testnet/Paper）

## 8. 看板 / Arena 集成

- PaperMonitor 每 60 秒为所有 paper 账户写 `HyperliquidAccountSnapshot`（environment="paper"）
- `asset_curve_calculator` 加 paper 分支：按 execution_mode 判断账户后查 paper 快照构建曲线
- Arena / 排行 / 交易员卡片：数据来源不变，前端加 PAPER 徽章

## 9. 前端 UI 变更

| 位置 | 变更 |
|------|------|
| 策略配置面板 | "交易所"下拉之下新增"执行模式"选择：实盘交易 / 纸交易；选纸交易显示提示"使用主网实时行情模拟撮合，无需配置钱包"，并显示初始资金输入框 |
| 交易员卡片 Exchange Wallets 面板 | 新增"纸交易账户"卡片：模拟权益、可用余额、当前周期收益率、初始资金（可编辑）、重置按钮（确认弹窗，注明"开启新周期，历史记录保留"） |
| 归因分析页 | 环境筛选器加 Paper 选项；纸交易记录行带 PAPER 徽章 |
| 数据看板 / Arena / 排行 | 交易员名称旁 PAPER 徽章（蓝色系，与 Testnet/Mainnet 徽章风格一致）；资产曲线图例同样标识 |
| i18n | 中英文翻译同步 |

## 10. 错误处理与边界情况

| 场景 | 处理 |
|------|------|
| 订单簿拉取失败 | 回退 `最新价 ± slippage_fallback_pct`；价格也拿不到 → 拒单，错误结构与真实 client 一致，决策日志 executed=false |
| 服务重启 | 状态全部持久化；PaperMonitor 启动时重建监控列表，用 1 分钟 K 线补检停机窗口内的 TP/SL/限价/清算触发（优先用系统已采集的 K 线数据，缺口从交易所公开 API 补拉；按 K 线时间顺序结算，成交时间记 K 线时间） |
| 并发竞争（AI 下单 vs 监控触发） | 引擎写操作对 `paper_accounts` 行加锁（SELECT FOR UPDATE），同一账户操作串行化 |
| 币种移出监控列表但仍有持仓 | 持仓继续按实时价估值并触发 TP/SL，AI 不再开新仓（与实盘一致） |
| Funding 费率拉取失败 | 跳过本次结算并记日志，下周期重试 |
| 重置周期 | 单事务内：取消所有挂单、删除持仓、周期号 +1、记账字段归零；历史决策/成交/快照保留 |

## 11. 测试策略

1. **引擎单元测试**：开仓/平仓/部分平仓/加仓均价/反向净额/保证金拒单/TP/SL 独立触发/清算/funding 结算/订单簿逐档撮合（mock 订单簿）/回退滑点
2. **管线集成测试**：mock LLM 决策走完整 AI 管线（paper 模式），断言决策日志、成交记录、持仓状态；程序化交易员同理
3. **归因口径测试**：paper 环境筛选、手续费关联、盈亏汇总与引擎记账一致
4. **重启恢复测试**：构造停机窗口内触发 TP 的场景，验证 K 线补检正确结算
5. **手动端到端验证**：UI 开启纸交易 → 触发一次真实 LLM 决策 → 看板曲线/归因页确认数据
