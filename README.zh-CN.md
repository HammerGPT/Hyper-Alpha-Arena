# <img width="40" height="40" alt="logo_app" src="https://github.com/user-attachments/assets/911ba846-a08b-4e3e-b119-ec1e78347288" style="vertical-align: middle;" /> Hyper Alpha Arena

[English](./README.md) | **简体中文**

> **托管登录服务已关闭：** 本项目原有的托管登录、注册和会员服务已停止提供。自部署实例如需登录或多人访问，需要自行接入身份认证、用户管理和权限控制；依赖原托管会员校验的功能，也需要接入自己的权益校验服务。

> **多交易所 AI 交易平台，内置量化因子智能与市场资金流信号监控**。同时支持 **Hyperliquid** 和 **币安合约**。AI 能自主发现、验证并交易量化因子——机构量化团队使用的核心工具，现在零门槛可用。精准监控大资金订单流、持仓量变化、资金费率异常，市场结构变化时自动触发交易。两种交易模式：AI Trader 适合需要理解市场的策略，Program Trader 适合固定规则策略。AI 全程辅助配置，零基础也能上手。
>
> **合约交易者的效率神器**。86 个内置因子、自定义表达式引擎、AI 驱动的因子挖掘与网络研究。Docker 一键部署开箱即用，持续快速迭代更新。Hyperliquid 支持测试网模拟和主网实盘，币安合约直接 API 对接。

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Hyperliquid](https://img.shields.io/badge/Hyperliquid-Supported-00D395?style=flat&logo=data:image/svg%2bxml;base64,PHN2ZyB3aWR0aD0iMTQ0IiBoZWlnaHQ9IjE0NCIgdmlld0JveD0iMCAwIDE0NCAxNDQiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CiAgPHBhdGggZD0iTTE0NCA3MS42OTkxQzE0NCAxMTkuMzA2IDExNC44NjYgMTM0LjU4MiA5OS41MTU2IDEyMC45OEM4Ni44ODA0IDEwOS44ODkgODMuMTIxMSA4Ni40NTIxIDY0LjExNiA4NC4wNDU2QzM5Ljk5NDIgODEuMDExMyAzNy45MDU3IDExMy4xMzMgMjIuMDMzNCAxMTMuMTMzQzMuNTUwNCAxMTMuMTMzIDAgODYuMjQyOCAwIDcyLjQzMTVDMCA1OC4zMDYzIDMuOTY4MDkgMzkuMDU0MiAxOS43MzYgMzkuMDU0MkMzOC4xMTQ2IDM5LjA1NDIgMzkuMTU4OCA2Ni41NzIyIDYyLjEzMiA2NS4xMDczQzg1LjAwMDcgNjMuNTM3OSA4NS40MTg0IDM0Ljg2ODkgMTAwLjI0NyAyMi42MjcxQzExMy4xOTUgMTIuMDU5MyAxNDQgMjMuNDY0MSAxNDQgNzEuNjk5MVoiIGZpbGw9IndoaXRlIi8+Cjwvc3ZnPgo=)](https://hyperliquid.xyz)
[![Binance](https://img.shields.io/badge/Binance-Supported-F0B90B?style=flat&logo=data:image/svg%2bxml;base64,PHN2ZyB3aWR0aD0iMTQ0IiBoZWlnaHQ9IjE0NCIgdmlld0JveD0iMTI2IDEyNiA3NzIgNzcyIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPgogIDxwYXRoIGQ9Ik02NDMuNTQxMzMzIDU2Ni42MTMzMzNsNzcuMjY5MzM0IDc3LjIyNjY2Ny0yMDkuMTUyIDIwOS4xNTItMjA5LjEwOTMzNC0yMDkuMTUyIDc3LjI2OTMzNC03Ny4yMjY2NjcgMTMxLjg0IDEzMi41MjI2NjcgMTMxLjg0LTEzMi41NjUzMzN6IG0xMzEuODgyNjY3LTEzMS45MjUzMzNMODUzLjMzMzMzMyA1MTJsLTc3LjIyNjY2NiA3Ny4yMjY2NjdMNjk4LjgzNzMzMyA1MTJsNzYuNTg2NjY3LTc3LjIyNjY2N3ogbS0yNjMuNzIyNjY3IDBsNzcuMjI2NjY3IDc2LjU4NjY2Ny03Ny4yNjkzMzMgNzcuMjY5MzMzTDQzNC40MzIgNTEybDc3LjIyNjY2Ny03Ny4yMjY2Njd6IG0tMjYzLjc2NTMzMyAwTDMyNC41NjUzMzMgNTEybC03Ni41ODY2NjYgNzYuNTg2NjY3TDE3MC42NjY2NjcgNTExLjk1NzMzM2w3Ny4yMjY2NjYtNzcuMjI2NjY2eiBtMjYzLjc2NTMzMy0yNjMuNzY1MzMzbDIwOS4xNTIgMjA4LjQ2OTMzMy03Ny4zMTIgNzcuMjI2NjY3LTEzMS44NC0xMzEuODQtMTMxLjg0IDEzMi41MjI2NjYtNzcuMzEyLTc3LjIyNjY2NiAyMDkuMTUyLTIwOS4xNTJ6IiBmaWxsPSJ3aGl0ZSIvPgo8L3N2Zz4K)](https://binance.com)
[![Twitter](https://img.shields.io/badge/Twitter-@GptHammer3309-1DA1F2?style=flat&logo=twitter&logoColor=white)](https://x.com/GptHammer3309)
[![Discord](https://img.shields.io/badge/Discord-Community-5865F2?style=flat&logo=discord&logoColor=white)](https://discord.gg/9Pr5Uz2JvV)
[![English](https://img.shields.io/badge/Lang-English-blue)](https://www.akooi.com/docs/)
[![中文](https://img.shields.io/badge/语言-中文-red)](https://www.akooi.com/docs/zh/)

## 这是什么

Hyper Alpha Arena 是一个 AI 交易平台——让 GPT、Claude、Deepseek 这些大模型帮你盯盘、分析、下单，全自动。灵感来自 [nof1 Alpha Arena](https://nof1.ai)。

**官网：** https://www.akooi.com/

## 适合谁用

| 你是谁 | 能得到什么 |
|--------|-----------|
| **普通交易者** | 不会写代码也能用，AI 助手陪你聊天就能配好策略 |
| **量化玩家** | 86 个内置因子配合 IC/ICIR 有效性评分，69 函数自定义表达式引擎，AI 驱动因子挖掘——先在测试网验证，再上真金白银 |
| **Hyperliquid 用户** | 测试网免费练手，主网 1-50 倍杠杆实盘 |
| **币安用户** | API Key 一键绑定，U本位合约全功能支持 |
| **AI 发烧友** | 让 GPT、Claude、Deepseek 同台 PK，看谁更能赚 |

**支持的交易所：**
- **Hyperliquid 测试网**：零风险练手，真实行情真实订单簿，免费测试金，无需 KYC
- **Hyperliquid 主网**：去中心化永续合约，1-50 倍杠杆，钱包签名交易
- **币安合约**：全球最大加密衍生品交易所，U本位永续合约，API Key 认证

## 核心功能

### 两种交易模式

| 模式 | 适用场景 | 工作方式 |
|------|---------|----------|
| **AI Trader** | 需要理解市场的策略（舆情、新闻、综合判断） | 自然语言描述策略，AI 实时分析并决策 |
| **Program Trader** | 固定规则策略（技术指标、价格条件） | Python 代码定义规则，历史数据回测验证，毫秒级执行 |

**因子智能 (Factor Intelligence)** - AI 自主挖掘 Alpha。86 个内置因子覆盖动量、趋势、波动率、成交量、微观结构五大类——每个因子都有机构级评估指标（IC、ICIR、胜率、衰减半衰期）。69 函数自定义表达式引擎支持创建你自己的因子。Hyper AI 可以搜索网络上最新的量化研究、从学术论文中提取因子思路，然后用你的实盘数据验证——衡量预测能力，围绕真正有效的因子构建策略。因子可用作信号触发条件、注入 AI Trader 提示词、或在 Program Trader 中编程调用。

**市场流动信号监控** - 不用 24/7 盯盘，大资金异动时自动触发。监控订单流失衡、持仓量激增、资金费率极端，只在市场结构性变化时触发交易。因子库中的任意因子也可作为触发条件，配合真实百分位分布（P5–P95）精准设置阈值。

**AI 全程辅助配置** - 不会写策略提示词？不会设置信号条件？对话式 AI 生成器帮你从零开始配置，无需编程基础。

**交易归因分析** - 不知道策略哪里出问题？按币种、触发类型、时间段、因子四个维度拆解盈亏。"按因子"维度直接展示哪些因子信号真正赚了钱。AI 诊断策略弱点并给出优化建议。

**多账户实时对比** - 不知道哪个策略更有效？多个 AI Trader 资产曲线实时对比，交易标记显示在各自曲线上，一目了然。

**多交易所支持** - Hyperliquid（去中心化、钱包签名）和币安合约（中心化、API Key）任你选。Hyperliquid 测试网/主网无缝切换，1-50x 杠杆原生支持，保证金监控和清算价预警内置。

**多模型 LLM 支持** - 兼容 OpenAI API 格式模型（GPT-5、Claude、Deepseek 等）。多钱包架构，测试网/主网独立配置。

**程序化交易 (Program Trader)** - 用 Python 代码定义交易规则。历史数据回测验证策略盈利能力，上线前充分测试。AI 助手通过对话帮你编写和优化代码。

### 聪明钱钱包信号接入

可连接 Hyper Insight，将巨鲸与聪明钱地址的跟踪动作同步到 Hyper Alpha Arena，作为钱包信号池使用。Hyper Insight 当前已收录约 **70,000** 个跟踪地址，这些钱包信号可用于触发 **AI Trader**、**Program Trader** 和 Bot 通知。

### AI 多智能体架构

Hyper Alpha Arena 的核心差异化在于多智能体 AI 系统。不是单一聊天机器人，而是五个专业 AI 智能体协同覆盖完整交易工作流：

| 智能体 | 职责 |
|--------|------|
| **Hyper AI** | 中央协调器，具备工具调用能力——查询行情、分析持仓、挖掘验证量化因子、搜索网络量化研究、调度其他智能体 |
| **Signal AI** | 通过对话设计市场流动信号条件（CVD、OI、资金费率触发） |
| **Prompt AI** | 编写和优化 AI Trader 策略提示词，实时变量预览 |
| **Program AI** | 编写、调试和回测 Program Trader 的 Python 交易策略 |
| **Attribution AI** | 诊断策略表现——定位弱点并给出优化建议 |

每个智能体都深度理解自己的领域，并能调用相关工具。Hyper AI 可以实时查询行情 API、检查持仓、获取 K 线数据——将自然对话转化为可执行的交易情报。

**📱 移动端接入** — Hyper AI 同时支持 Telegram 和 Discord。同样的 AI，同样的工具，还能主动推送交易提醒到你的手机。

| 平台 | 状态 |
|------|------|
| Telegram | ✅ |
| Discord | ✅ |
| WhatsApp | 🔜 |

### Skill 技能系统 — 零门槛上手

Hyper AI 内置 Skill 技能系统：模块化的分步工作流引导，带你完成复杂操作。输入 `/命令` 或直接描述需求，AI 自动加载对应技能。

| 命令 | 技能 | 功能 |
|------|------|------|
| `/prompt` | 提示词策略搭建 | 从零开始引导创建 AI 决策交易策略 |
| `/program` | 程序策略搭建 | 引导构建 Python 程序化交易策略 |
| `/market` | 市场分析 | 多数据源综合市场分析 |
| `/review` | 绩效回顾 | 分析交易表现并给出优化建议 |
| `/diagnose` | Trader 诊断 | 系统化排查 Trader 不触发的原因 |
| `/resource` | 资源管理 | 重组策略、重新绑定信号池、管理 Trader |
| `/health` | 系统健康检查 | 全面系统状态报告与可操作建议 |
| `/factor` | 因子挖掘 | AI 引导因子发现——调研市场、生成假设、IC/ICIR 验证、保存到因子库 |
| `/memory` | 记忆管理 | 查看、更新或修正 AI 记住的用户偏好 |

每个技能都采用检查点式工作流——AI 在关键步骤暂停确认后再继续。不需要提前学习平台概念或阅读文档。

## 界面预览

### Hyper AI
![Hyper AI](screenshots/hyper_AI.png)
*全站 AI 管家，统一承接分析、配置与交易协作*

### Multi-Trader Arena
![Multi-Trader Arena](screenshots/dashboard_arena.png)
*多 Trader 数字交易大厅，统一观察运行状态与市场动态*

### 信号检测
![信号检测](screenshots/signal_new.png)
*带可视化回测语境的信号检测与触发工作流*

## 快速开始

### 环境要求

- **Docker Desktop**（[下载地址](https://www.docker.com/products/docker-desktop)）
  - Windows：Docker Desktop for Windows
  - macOS：Docker Desktop for Mac
  - Linux：Docker Engine（[安装指南](https://docs.docker.com/engine/install/)）

### 安装步骤

```bash
# 克隆仓库
git clone https://github.com/HammerGPT/Hyper-Alpha-Arena.git
cd Hyper-Alpha-Arena

# 启动应用（根据你的 Docker 版本选择命令）
docker compose up -d --build        # 新版 Docker Desktop（推荐）
# 或
docker-compose up -d --build       # 旧版 Docker 或独立安装的 docker-compose
```

启动完成后访问 **http://localhost:8802** 或 **http://127.0.0.1:8802**

### 常用命令

```bash
# 查看日志
docker compose logs -f        # 或 docker-compose logs -f

# 停止应用
docker compose down          # 或 docker-compose down

# 重启应用
docker compose restart       # 或 docker-compose restart

# 更新到最新版本
git pull origin main
docker compose up -d --build # 或 docker-compose up -d --build
```

**注意事项**：
- 所有数据（数据库、配置、交易记录）都保存在 Docker 卷中
- 停止/重启容器不会丢失数据
- 只有 `docker-compose down -v` 会删除数据（除非想重置，否则别加 `-v`）

## 首次配置

### 自部署用户体系

现有认证代码仍包含对已停用托管服务的依赖。接入自己的用户体系，需要适配 `auth-config.json`、OAuth 回调、令牌刷新与退出、会员接口请求，以及后端会话校验和权限控制。仅修改地址或环境变量，并不能提供完整用户体系或用户间的数据隔离。

在完善后端访问控制前，个人部署应限制在本机或可信私有网络内。交易所钱包/API 凭据与应用自身的用户认证是两回事。

详细配置指南请参考官方文档，包括：
- Hyperliquid 钱包配置（测试网 & 主网）
- 币安 API Key 设置
- AI Trader 创建与 LLM API 设置
- 交易环境与杠杆设置
- 信号触发交易配置

**📖 完整指南：[快速开始](https://www.akooi.com/docs/zh/guide/getting-started.html)**

## 支持的模型

Hyper Alpha Arena 支持所有兼容 OpenAI API 的大语言模型。**推荐使用 Deepseek**，性价比高，交易场景表现出色。

支持的模型包括：
- **Deepseek**（推荐）：交易决策性价比之王
- **OpenAI**：GPT-5 系列、o1 系列、GPT-4o、GPT-4
- **Anthropic**：Claude（通过兼容端点）
- **自定义 API**：任何 OpenAI 兼容的端点

平台会自动处理不同模型的配置差异。

## 常见问题

**问题**：端口 8802 被占用
**解决**：
```bash
docker-compose down
docker-compose up -d --build
```

**问题**：Windows 上访问 `localhost:8802` 页面无法加载 / WebSocket 报错
**解决**：改用 `http://127.0.0.1:8802`。Windows 可能将 `localhost` 解析为 IPv6（`::1`），而 Docker 默认不绑定 IPv6。

**问题**：无法连接 Docker 守护进程
**解决**：确保 Docker Desktop 正在运行

**问题**：数据库连接错误
**解决**：等待 PostgreSQL 容器启动完成（用 `docker-compose ps` 检查状态）

**问题**：想要重置所有数据
**解决**：
```bash
docker-compose down -v  # 这会删除所有数据！
docker-compose up -d --build
```

## 参与贡献

欢迎社区贡献！你可以：

- 报告 Bug 和问题
- 提出新功能建议
- 提交 Pull Request
- 完善文档
- 在不同平台测试

请 Star 和 Fork 本仓库，关注开发进展。

## 相关资源

### Hyperliquid
- 官方文档：https://hyperliquid.gitbook.io/
- Python SDK：https://github.com/hyperliquid-dex/hyperliquid-python-sdk
- 测试网：https://app.hyperliquid-testnet.xyz

### 币安合约
- API 文档：https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info
- 测试网：https://testnet.binancefuture.com

### 原始项目
- Open Alpha Arena：https://github.com/etrobot/open-alpha-arena

## 社区与支持

**🌐 官网**：[https://www.akooi.com/](https://www.akooi.com/)

**🐦 推特**：[@GptHammer3309](https://x.com/GptHammer3309)
- 产品更新动态
- AI 交易策略讨论

**💬 Discord**：[加入社区](https://discord.gg/9Pr5Uz2JvV)
- 技术支持与讨论
- Bug 反馈和功能建议

**📝 GitHub Issues**：Bug 追踪和功能请求请使用 [GitHub Issues](https://github.com/HammerGPT/Hyper-Alpha-Arena/issues)。

## 许可证

本项目采用 Apache License 2.0 许可证。详见 [LICENSE](LICENSE) 文件。

## 致谢

- **etrobot** - open-alpha-arena 原始项目
- **nof1.ai** - Alpha Arena 灵感来源
- **Hyperliquid** - 去中心化永续合约交易平台
- **OpenAI、Anthropic、Deepseek** - LLM 提供商

---

Star 本仓库，关注开发进展。
