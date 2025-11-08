 # <img width="40" height="40" alt="logo_app" src="https://github.com/user-attachments/assets/911ba846-a08b-4e3e-b119-ec1e78347288" style="vertical-align: middle;" /> Hyper Alpha Arena

> An open-source AI-powered cryptocurrency trading platform for autonomous trading with Large Language Models. Deploy AI trading strategies with both paper trading simulation and real perpetual contract trading on Hyperliquid DEX.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![GitHub stars](https://img.shields.io/github/stars/HammerGPT/Hyper-Alpha-Arena)](https://github.com/HammerGPT/Hyper-Alpha-Arena/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/HammerGPT/Hyper-Alpha-Arena)](https://github.com/HammerGPT/Hyper-Alpha-Arena/network)

## Overview

Hyper Alpha Arena is a production-ready AI trading platform where Large Language Models (LLMs) autonomously execute cryptocurrency trading strategies. Inspired by [nof1 Alpha Arena](https://nof1.ai), this platform enables AI models like GPT-5, Claude, and Deepseek to make intelligent trading decisions based on real-time market data and execute trades automatically.

**Trading Modes:**
- **Paper Trading**: Risk-free simulation with real market data for strategy development and testing
- **Hyperliquid Perpetual Contracts**: Real trading on decentralized perpetual exchange with 1-50x leverage support
  - Testnet: Safe testing environment with test funds
  - Mainnet: Production trading with real capital (use with caution)

**Current Status**: v0.5.0 - Major update with complete Hyperliquid DEX integration for real perpetual contract trading.


## Features

### Current Features (v0.5.0)

#### Paper Trading Features
- **Multi-Model LLM Support**: OpenAI API compatible models (GPT-5, Claude, Deepseek, etc.)
- **Prompt Template Management**:
  - Customizable AI trading prompts with visual editor
  - Account-specific prompt binding system with Hyperliquid-specific templates
  - Default, Pro, and Hyperliquid templates with leverage education
  - Automatic fallback to default template for unbound accounts
- **Paper Trading Engine**: Simulated order matching and position management for risk-free strategy testing
- **Real-time Market Data**: Live cryptocurrency price feeds from multiple exchanges via ccxt
- **AI Trader Management**: Create and manage multiple AI trading agents with independent configurations

#### Hyperliquid Real Trading Features (🔥 NEW in v0.5.0)
- **Perpetual Contract Trading**: Real order execution on Hyperliquid DEX
  - Market and limit orders with 1-50x leverage support
  - Long and short positions with automatic liquidation price calculation
  - Cross-margin mode with real-time margin usage monitoring
- **Risk Management**: Built-in safety mechanisms
  - Maximum leverage limits (configurable per account, 1-50x)
  - Margin usage alerts (auto-pause trading at 80% usage)
  - Liquidation price display and warnings
- **AI-Driven Trading**: LLM-powered perpetual contract trading
  - Leverage-aware AI prompts with risk management education
  - Automatic leverage selection based on market confidence
  - Full integration with existing AI decision engine

## Screenshots

### Main Dashboard(Hyperliquid Mainnet)
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
docker compose up -d        # For newer Docker Desktop (recommended)
# OR
docker-compose up -d       # For older Docker versions or standalone docker-compose
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

### Upgrading from Previous Versions

**For v0.4.x or earlier users upgrading to v0.5.0+:**

Due to significant database schema changes (wallet address tracking for multi-model support), we recommend two approaches:

#### Option 1: Clean Installation (Recommended for Most Users)

```bash
# ⚠️ This will delete all historical data
docker-compose down -v
git pull origin main
docker-compose up -d
```

**Why clean installation?**
- Old trading records don't have wallet addresses and won't appear in wallet-specific views
- Simpler and faster than running migration scripts
- Guaranteed compatibility with the new version

#### Option 2: Preserve Historical Data (Advanced Users)

If you must keep historical data, run migration scripts manually:

```bash
cd backend
source .venv/bin/activate

# Run all migrations
python database/migrations/add_wallet_address_to_ai_decision_logs.py
python database/migrations/add_wallet_address_to_hyperliquid_trades.py
python database/migrations/add_wallet_address_to_hyperliquid_tables.py
python database/migrations/add_wallet_address_to_snapshot_tables.py

# Restart containers
docker-compose restart
```

**Important Limitations:**
- Historical records without wallet addresses will not display in wallet-specific views (Hyperliquid page, asset charts)
- The data remains in the database but is filtered out by the new UI
- Only new trades after migration will have wallet address tracking

### First-Time Setup

#### For Paper Trading (Risk-Free Testing)

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

#### For Hyperliquid Real Trading (⚠️ Use with Caution)

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

**Step 2: Configure in Hyper Alpha Arena**

1. Open http://localhost:8802
2. Navigate to **Hyperliquid** page in the sidebar
3. Click **Environment Switcher** to select Testnet or Mainnet
4. In the **Configuration Panel**:
   - Enter your Hyperliquid private key (will be encrypted and stored securely)
   - Set maximum leverage (1-50x, recommended: 5x for beginners)
   - Click **Save Configuration**
5. Your balance and positions will load automatically

**Step 3: Configure Market Watchlist (Hyperliquid Trading)**

1. Navigate to **AI Trader Management → Market Watchlist**
2. Select up to 10 symbols you want the AI to monitor (the order you pick determines the model’s evaluation order)
3. Save your selection — Hyperliquid prompts, model decisions, and live data will only cover these symbols
4. You can adjust the list anytime; paper-trading mode continues using its default fixed symbols

**Step 4: Configure AI Trader for Hyperliquid**

1. Navigate to **AI Traders** section
2. Create or edit an AI trader
3. In the configuration:
   - Enable **Hyperliquid Trading**: Toggle ON
   - Select **Environment**: Testnet or Mainnet
   - Choose **Prompt Template**: Select "Hyperliquid Pro" (includes leverage education)
   - Configure trading strategy triggers
4. The AI will now trade perpetual contracts on Hyperliquid

**Step 5: Monitor Your Trading**

1. **Dashboard**: View real-time P&L, positions, and margin usage
2. **System Logs**: Monitor AI decisions and order executions
3. **Hyperliquid Page**: Check detailed position information and liquidation prices
4. **Safety**: System auto-pauses trading if margin usage exceeds 80%

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

**Important Note for Hyperliquid Trading**: Currently, we recommend using **one AI model per Hyperliquid wallet address** to maintain accurate performance statistics. Multi-model support for the same wallet address will be available in a future update.

The platform automatically handles model-specific configurations and parameter differences.



## Roadmap

### Phase 1: Foundation & Paper Trading ✅ (Completed - v0.3.0)
- [✅] Multi-model LLM support (GPT-5, Claude, Deepseek)
- [✅] Paper trading engine with order matching
- [✅] Real-time market data integration via CCXT
- [✅] AI decision engine with prompt templates
- [✅] System logging and monitoring
- [✅] Basic UI with portfolio tracking

### Phase 2: Hyperliquid Integration ✅ (Completed - v0.5.0)
- [✅] **Hyperliquid testnet trading** - Safe testing with test funds
- [✅] **Hyperliquid mainnet trading** - Real perpetual contract execution
- [✅] **Private key encryption** - Fernet-based secure storage
- [✅] **Environment isolation** - Strict testnet/mainnet separation
- [✅] **Perpetual contracts** - Long/short with 1-50x leverage
- [✅] **AI-driven leverage trading** - Intelligent risk management
- [✅] **Real-time position tracking** - Live P&L and margin monitoring
- [✅] **Liquidation warnings** - Auto-pause at 80% margin usage
- [✅] **Complete frontend UI** - Hyperliquid page with all trading features
- [✅] **Position management** - Balance cards, order forms, position tables
- [✅] **Asset curve visualization** - Performance charts for real trading
- [✅] **Prompt template system** - Hyperliquid-specific AI prompts
- [✅] **Database snapshots** - Historical position and balance tracking

### Phase 3: Enhancement & Optimization 🔄 (In Progress - v0.6.0)
- [🔄] Multi-model account management and performance tracking
- [ ] Multiple trading pair support (currently BTC-focused)
- [ ] Enhanced prompt template UI with visual editor
- [ ] Advanced order types (stop-loss, take-profit, trailing stops)
- [ ] Multi-timeframe analysis for AI decision-making
- [ ] Enhanced risk analytics dashboard

### Phase 4: Trading Platform Expansion 📋 (Planned - v0.7.0)
- [ ] Binance spot and futures trading
- [ ] Bybit perpetual contracts
- [ ] OKX derivatives trading
- [ ] Exchange aggregation for best execution

### Phase 5: Advanced Features 🚀 (Long Term - v1.0.0+)
- [ ] AI agent marketplace and strategy sharing
- [ ] Multi-user support with role-based access
- [ ] Backtesting framework with historical data
- [ ] Mobile app for trade monitoring
- [ ] Advanced portfolio analytics and reporting

## Key Improvements Over Original Project

### 🔥 Major Enhancements in v0.5.0

 **Complete Hyperliquid DEX Integration**:
   - Full perpetual contract trading on testnet and mainnet
   - 1-50x leverage support with AI-driven selection
   - Real-time position tracking and P&L calculation
   - Fernet encryption for private key security
   - Environment isolation to prevent accidental cross-environment trades
   - Margin monitoring with auto-pause at 80% usage
   - Complete frontend UI with balance cards, order forms, and position tables

## Troubleshooting

### Common Issues

**Problem**: Port 8802 already in use
**Solution**:
```bash
docker-compose down
docker-compose up -d
```

**Problem**: Cannot connect to Docker daemon
**Solution**: Make sure Docker Desktop is running

**Problem**: Database connection errors
**Solution**: Wait for PostgreSQL container to be healthy (check with `docker-compose ps`)

**Problem**: Want to reset all data
**Solution**:
```bash
docker-compose down -v  # This will delete all data!
docker-compose up -d
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

### Alpha Arena (Inspiration)
- Website: https://nof1.ai/leaderboard
- Research: AI trading model performance analysis

### Hyperliquid
- Official Docs: https://hyperliquid.gitbook.io/
- Python SDK: https://github.com/hyperliquid-dex/hyperliquid-python-sdk
- Testnet: https://api.hyperliquid-testnet.xyz

### Original Project
- Open Alpha Arena: https://github.com/etrobot/open-alpha-arena

## Community & Support

### Join Our AI Trading Community

**学习更多AI量化交易技术，请加入知识星球🔽**
<div align="center">
  <img src="https://github.com/user-attachments/assets/82f748a0-2d2f-412d-9eb8-f46f543688d5" alt="Heliki AI Community" width="400"/>
</div>

**🌐 Official Website**: [https://www.heliki.com/](https://www.heliki.com/)

**🐦 Contact me on Twitter/X**: [@GptHammer3309](https://x.com/GptHammer3309)
- Latest updates on Hyper Alpha Arena development
- AI trading insights and strategy discussions
- Technical support and Q&A


## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

When using this software, please include attribution to Heliki AI Community in your documentation or product notices as required by the Apache License 2.0.

## Acknowledgments

- **etrobot** - Original open-alpha-arena project
- **nof1.ai** - Inspiration from Alpha Arena
- **Hyperliquid** - Decentralized perpetual exchange platform
- **OpenAI, Anthropic, Deepseek** - LLM providers

---


Star this repository to follow development progress. Frontend UI for Hyperliquid coming soon.
