# <img width="40" height="40" alt="logo_app" src="https://github.com/user-attachments/assets/911ba846-a08b-4e3e-b119-ec1e78347288" style="vertical-align: middle;" /> Hyper Alpha Arena

> An open-source AI-powered cryptocurrency trading platform for autonomous trading with Large Language Models. Deploy AI trading strategies with both paper trading simulation and real perpetual contract trading on Hyperliquid DEX.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![GitHub stars](https://img.shields.io/github/stars/HammerGPT/Hyper-Alpha-Arena)](https://github.com/HammerGPT/Hyper-Alpha-Arena/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/HammerGPT/Hyper-Alpha-Arena)](https://github.com/HammerGPT/Hyper-Alpha-Arena/network)
[![Community](https://img.shields.io/badge/Telegram-Community-blue?logo=telegram)](https://t.me/+RqxjT7Gttm9hOGEx)

## 🔥 Start Trading Now - Up to 30% Fee Discount

Ready to put your AI trading strategies to work? Get started with these top exchanges:

### 🚀 **Hyperliquid** - Decentralized Perpetual Exchange
- **No KYC Required** | **Low Fees** | **High Performance**
- Direct integration with Hyper Alpha Arena
- [**Open Futures Trading →**](https://app.hyperliquid.xyz/trade)

### 💰 **Binance** - World's Largest Exchange
- **30% Fee Discount** | **High Liquidity** | **Advanced Tools**
- [**Register with 30% Discount →**](https://accounts.maxweb.red/register?ref=HYPERVIP)

### ⚡ **Aster DEX** - Binance-Compatible DEX
- **Lower Fees** | **Multi-chain Support** | **API Wallet Security**
- [**Register Now →**](https://www.asterdex.com/zh-CN/referral/2b5924)

---

## Overview

Hyper Alpha Arena is a production-ready AI trading platform where Large Language Models (LLMs) autonomously execute cryptocurrency trading strategies. Inspired by [nof1 Alpha Arena](https://nof1.ai), this platform enables AI models like GPT-5, Claude, and Deepseek to make intelligent trading decisions based on real-time market data and execute trades automatically.

**Official Website:** https://www.akooi.com/

**Trading Modes:**
- **Hyperliquid Testnet (Paper Trading)**: Risk-free testing with real market mechanics, free test funds, and actual order book - a superior paper trading experience
- **Hyperliquid Mainnet**: Live trading on decentralized perpetual exchange with 1-50x leverage support (real capital at risk)

## Features

### Core Trading Features
- **Multi-Model LLM Support**: OpenAI API compatible models (GPT-5, Claude, Deepseek, etc.)
- **Multi-Wallet Architecture**: Each AI Trader can configure separate wallets for Testnet and Mainnet
- **Global Trading Mode**: Centralized environment switch affecting all AI Traders simultaneously
- **Prompt Template Management**:
  - Customizable AI trading prompts with visual editor
  - Account-specific prompt binding system with Hyperliquid-specific templates
  - Default, Pro, and Hyperliquid templates with leverage education
  - Automatic fallback to default template for unbound accounts
- **Real-time Market Data**: Live cryptocurrency price feeds from multiple exchanges via ccxt
- **AI Trader Management**: Create and manage multiple AI trading agents with independent configurations

### Hyperliquid Trading Features
- **Perpetual Contract Trading**: Real order execution on Hyperliquid DEX
  - Market and limit orders with 1-50x leverage support
  - Long and short positions with automatic liquidation price calculation
  - Cross-margin mode with real-time margin usage monitoring
- **Environment Isolation**: Strict separation of Testnet and Mainnet
  - Separate wallet configurations per environment
  - Environment-aware caching with `(account_id, environment)` composite keys
  - API call isolation preventing cross-environment data contamination
- **Risk Management**: Built-in safety mechanisms
  - Maximum leverage limits (configurable per account, 1-50x)
  - Margin usage alerts (auto-pause trading at 80% usage)
  - Liquidation price display and warnings
- **AI-Driven Trading**: LLM-powered perpetual contract trading
  - Leverage-aware AI prompts with risk management education
  - Automatic leverage selection based on market confidence
  - Full integration with existing AI decision engine

## Screenshots

### Main Dashboard (Hyperliquid Mainnet)
<img width="3206" height="1928" alt="image" src="https://github.com/user-attachments/assets/afe0600b-c34c-401e-a47a-db81525a9ccf" />

<img width="3206" height="1932" alt="image" src="https://github.com/user-attachments/assets/48e70a94-013e-4873-9b44-f371e3a76581" />

### Model Chat Prompt
<img width="3206" height="1930" alt="image" src="https://github.com/user-attachments/assets/e200e702-c240-4ccd-896b-68038ffe475d" />

### AI Trader and Strategy Settings
<img width="3210" height="1932" alt="image" src="https://github.com/user-attachments/assets/383e447f-b5a1-4226-a24d-ee9e5a686d6f" />

### System Log
<img width="3208" height="1932" alt="image" src="https://github.com/user-attachments/assets/821ea000-ee78-4573-8c05-52579e8369b1" />

## Quick Start

### Prerequisites

- **Docker Desktop** ([Download](https://www.docker.com/products/docker-desktop))
  - Windows: Docker Desktop for Windows
  - macOS: Docker Desktop for Mac
  - Linux: Docker Engine ([Install Guide](https://docs.docker.com/engine/install/))

### Installation

```bash
# Clone the repository
git clone https://github.com/HammerGPT/Hyper-Alpha-Arena.git
cd Hyper-Alpha-Arena

# Start the application (choose one command based on your Docker version)
docker compose up -d --build        # For newer Docker Desktop (recommended)
# OR
docker-compose up -d --build       # For older Docker versions or standalone docker-compose
```

The application will be available at **http://localhost:8802**

### Managing the Application

```bash
# View logs
docker compose logs -f        # (or docker-compose logs -f)

# Stop the application
docker compose down          # (or docker-compose down)

# Restart the application
docker compose restart       # (or docker-compose restart)

# Update to latest version
git pull origin main
docker compose up -d --build # (or docker-compose up -d --build)
```

**Important Notes:**
- All data (databases, configurations, trading history) is persisted in Docker volumes
- Data will be preserved when you stop/restart containers
- Only `docker-compose down -v` will delete data (don't use `-v` flag unless you want to reset everything)

## First-Time Setup

### For Paper Trading (Risk-Free Testing)

1. Open http://localhost:8802
2. Navigate to **AI Traders** section
3. Create your first AI trader:
   - Name: e.g., "GPT-5 Trader"
   - Model: Select from dropdown (gpt-5-mini, claude-sonnet-4.5, etc.)
   - API Key: Your OpenAI/Anthropic/Deepseek API key
   - Base URL: Leave default or use custom endpoint
4. Configure trading strategy:
   - Trigger Mode: Real-time (recommended for active trading)
   - Enable Strategy: Toggle to activate
5. Monitor logs in **System Logs** section to verify setup

### For Hyperliquid Real Trading (⚠️ Use with Caution)

**Prerequisites:**
- A Hyperliquid account with API access
- Your private key (starts with 0x...)
- Test funds in testnet OR real funds in mainnet

**Step 1: Get Your Hyperliquid Private Key**

1. **Testnet (Recommended for Testing)**:
   - Visit: https://app.hyperliquid-testnet.xyz/
   - Create an account and export your private key
   - Request testnet funds from the faucet

2. **Mainnet (Real Money)**:
   - Visit: https://app.hyperliquid.xyz/
   - Create an account or use existing wallet
   - Export your private key from your wallet
   - ⚠️ **WARNING**: This is your real money wallet - keep private key secure!

**Step 2: Configure Wallets for AI Trader**

1. Open http://localhost:8802
2. Navigate to **AI Traders** section in the sidebar
3. Create or select an existing AI Trader
4. Scroll down to **Hyperliquid Wallets** section
5. You'll see two wallet configuration panels:
   - **Testnet Wallet**: For paper trading (risk-free)
   - **Mainnet Wallet**: For real trading (real funds)
6. For each wallet you want to configure:
   - Enter your Hyperliquid private key (will be encrypted and stored securely)
   - Set maximum leverage (1-50x, recommended: 3x for testing, 5x for mainnet)
   - Set default leverage (1-3x recommended)
   - Click **Save Wallet**
7. Your wallet address will be automatically parsed from the private key
8. Balance information will load automatically after configuration

**Step 3: Set Global Trading Mode**

1. Navigate to **Settings** (gear icon in sidebar) or **Hyperliquid** page
2. Find the **Global Trading Environment** section
3. Choose your mode:
   - **TESTNET**: All AI Traders will use their testnet wallets (recommended for initial testing)
   - **MAINNET**: All AI Traders will use their mainnet wallets (⚠️ REAL MONEY)
4. Confirm the switch (especially important when switching to mainnet)

**Step 4: Enable Auto Trading**

1. In your AI Trader configuration
2. Toggle **Auto Trading** to ON
3. Configure trading strategy:
   - Trigger Mode: Real-time (recommended for active trading)
   - Trigger Interval: 60-150 seconds
   - Price Threshold: 0.5-2.0%
4. Choose appropriate **Prompt Template**: "Hyperliquid Pro" includes leverage education
5. Monitor initial trades carefully in **System Logs**

**Safety Tips:**
- ✅ Always test on testnet first with at least 1 week of observation
- ✅ Start with low leverage (1x-3x) until you understand the system
- ✅ Monitor margin usage regularly - liquidations can happen fast
- ✅ Use stop-loss in your AI prompts to limit downside risk
- ❌ Never use maximum leverage (50x) - extremely high liquidation risk
- ❌ Don't leave trading unmonitored for extended periods

## Supported Models

Hyper Alpha Arena supports any OpenAI API compatible language model. **For best results, we recommend using Deepseek** for its cost-effectiveness and strong performance in trading scenarios.

Supported models include:
- **Deepseek** (Recommended): Excellent cost-performance ratio for trading decisions
- **OpenAI**: GPT-5 series, o1 series, GPT-4o, GPT-4
- **Anthropic**: Claude (via compatible endpoints)
- **Custom APIs**: Any OpenAI-compatible endpoint

The platform automatically handles model-specific configurations and parameter differences.

## Troubleshooting

### Common Issues

**Problem**: Port 8802 already in use
**Solution**:
```bash
docker-compose down
docker-compose up -d --build
```

**Problem**: Cannot connect to Docker daemon
**Solution**: Make sure Docker Desktop is running

**Problem**: Database connection errors
**Solution**: Wait for PostgreSQL container to be healthy (check with `docker-compose ps`)

**Problem**: Want to reset all data
**Solution**:
```bash
docker-compose down -v  # This will delete all data!
docker-compose up -d --build
```

## Contributing

We welcome contributions from the community! Here are ways you can help:

- Report bugs and issues
- Suggest new features
- Submit pull requests
- Improve documentation
- Test on different platforms

Please star and fork this repository to stay updated with development progress.

## Resources

### Hyperliquid
- Official Docs: https://hyperliquid.gitbook.io/
- Python SDK: https://github.com/hyperliquid-dex/hyperliquid-python-sdk
- Testnet: https://api.hyperliquid-testnet.xyz

### Original Project
- Open Alpha Arena: https://github.com/etrobot/open-alpha-arena

## Community & Support

**🌐 Official Website**: [https://www.akooi.com/](https://www.akooi.com/)

**🐦 Contact me on Twitter/X**: [@GptHammer3309](https://x.com/GptHammer3309)
- Latest updates on Hyper Alpha Arena development
- AI trading insights and strategy discussions
- Technical support and Q&A


Join our ([Telegram group](https://t.me/+RqxjT7Gttm9hOGEx)) for real-time discussions and faster triage .
- Report bugs (please include logs, screenshots, and steps if possible)
- Share strategy insights or product feedback
- Ping me about PRs/Issues so I can respond quickly

Friendly reminder: Telegram is for rapid communication, but final tracking and fixes still go through GitHub Issues/Pull Requests. Never post API keys or other sensitive data in the chat.

欢迎加入（[Telegram 群](https://t.me/+RqxjT7Gttm9hOGEx)）：
- 反馈 Bug（尽量附日志、截图、复现步骤）
- 讨论策略或产品体验
- PR / Issue 想要我关注可在群里提醒

注意：Telegram 主要用于快速沟通，正式记录请继续使用 GitHub Issues / Pull Requests；谨记不要分享密钥等敏感信息。

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **etrobot** - Original open-alpha-arena project
- **nof1.ai** - Inspiration from Alpha Arena
- **Hyperliquid** - Decentralized perpetual exchange platform
- **OpenAI, Anthropic, Deepseek** - LLM providers

---

Star this repository to follow development progress.
