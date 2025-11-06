 # <img width="40" height="40" alt="logo_app" src="https://github.com/user-attachments/assets/911ba846-a08b-4e3e-b119-ec1e78347288" style="vertical-align: middle;" /> Hyper Alpha Arena

> An open-source AI-powered cryptocurrency trading platform supporting both paper trading simulation and real perpetual contract trading on Hyperliquid DEX.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![GitHub stars](https://img.shields.io/github/stars/HammerGPT/Hyper-Alpha-Arena)](https://github.com/HammerGPT/Hyper-Alpha-Arena/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/HammerGPT/Hyper-Alpha-Arena)](https://github.com/HammerGPT/Hyper-Alpha-Arena/network)

## Overview

Hyper Alpha Arena is an advanced AI-powered cryptocurrency trading platform where Large Language Models (LLMs) autonomously execute trading strategies. Inspired by [nof1 Alpha Arena](https://nof1.ai), this platform enables AI models like GPT-5, Claude, Deepseek, and others to make intelligent trading decisions based on real-time market data.

**Trading Modes:**
- **Paper Trading**: Risk-free simulation with real market data for strategy development and testing
- **Hyperliquid Perpetual Contracts**: Real trading on decentralized perpetual exchange with 1-50x leverage support
  - Testnet: Safe testing environment with test funds
  - Mainnet: Production trading with real capital (use with caution)

**Current Status**: v0.5.0 - Major update with complete Hyperliquid DEX integration for real perpetual contract trading.

### Project Origin

This project is based on [open-alpha-arena](https://github.com/etrobot/open-alpha-arena) by etrobot. We extend our gratitude to the original author for laying the groundwork. Our fork introduces critical bug fixes, UI enhancements, improved AI decision engine, and market data integration from multiple sources including Hyperliquid.

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
- **Environment Isolation**: Complete separation between testnet and mainnet
  - Separate private key storage with Fernet encryption
  - Environment validation on every API call to prevent accidents
  - Safe environment switching with position checks
- **Position Management**: Real-time position tracking and P&L calculation
  - Unrealized P&L monitoring with liquidation warnings
  - Manual position closing via API
  - Position snapshot history in database
- **Risk Management**: Built-in safety mechanisms
  - Maximum leverage limits (configurable per account, 1-50x)
  - Margin usage alerts (auto-pause trading at 80% usage)
  - Liquidation price display and warnings
- **AI-Driven Trading**: LLM-powered perpetual contract trading
  - Leverage-aware AI prompts with risk management education
  - Automatic leverage selection based on market confidence
  - Full integration with existing AI decision engine

#### Common Features
- **Real-time Trading Triggers**: Event-driven AI trading with configurable strategies
  - Real-time trigger: Execute on every market update
  - Interval trigger: Execute at fixed time intervals (5 minutes default)
  - Tick batch trigger: Execute after N price updates
- **System Logs & Monitoring**: Comprehensive logging system
  - Real-time price update tracking (60-second snapshots)
  - AI decision logs with full reasoning context and leverage parameters
  - Hyperliquid order execution logs with environment tags
  - Error and warning detection with automatic categorization
  - Filterable log categories and severity levels
  - Auto-refresh dashboard with statistics
- **Auto Trading**: Automated trading scheduler for both paper and real trading
- **WebSocket Updates**: Real-time portfolio and position updates
- **Performance Dashboard**: Track AI model performance metrics across paper and real trading
- **API Compatibility**: Fixed parameter issues for modern LLM APIs (max_completion_tokens, temperature restrictions)

### Upcoming Features

- **Frontend UI for Hyperliquid**: Web interface for account configuration and position management
- **Advanced Order Types**: Stop-loss, take-profit, and trailing stop orders for Hyperliquid
- **Multiple Exchange Support**: Live trading on Binance, Bybit, and other major CEXs
- **Backtesting Framework**: Historical data simulation and strategy optimization
- **Trade Execution Analytics**: Slippage analysis and execution quality metrics
- **Portfolio Rebalancing**: Automated portfolio management across paper and real accounts

## Screenshots

### Main Dashboard
<img width="2198" height="1141" alt="image" src="https://github.com/user-attachments/assets/a5363a13-7977-4aa2-9441-da2376e3074f" />

### Model Chat Prompt
<img width="1843" height="1111" alt="image" src="https://github.com/user-attachments/assets/daafe0ab-a584-46ba-8805-d50aa4696ad3" />

### AI Trader and Strategy Settings
<img width="1849" height="1107" alt="image" src="https://github.com/user-attachments/assets/e59d59ae-0cf2-4665-9d59-7fc016e55d3b" />

<img width="1851" height="1111" alt="image" src="https://github.com/user-attachments/assets/ce275ccb-6800-4b92-9317-65271955999e" />


### System Log
<img width="1854" height="1120" alt="image" src="https://github.com/user-attachments/assets/59fe62ac-77a4-498b-a09a-ca8f8ec19620" />

## Quick Start

### Prerequisites

- **Node.js** 18+ ([Download](https://nodejs.org/))
- **Python** 3.11+ ([Download](https://python.org/))

### Installation

#### 🍎 macOS/Linux

```bash
git clone https://github.com/HammerGPT/Hyper-Alpha-Arena.git
cd Hyper-Alpha-Arena

# Make script executable and start the application
chmod +x start_arena.sh
./start_arena.sh
```

#### 🪟 Windows

```powershell
git clone https://github.com/HammerGPT/Hyper-Alpha-Arena.git
cd Hyper-Alpha-Arena

.\start_arena.ps1
```

**Note**: If you encounter PowerShell execution policy issues, run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Running the Application

The startup script automatically handles all setup and runs on port 8802:

#### 🍎 macOS/Linux
```bash
# Start the application
./start_arena.sh

# Stop the application
./start_arena.sh stop
```

#### 🪟 Windows
```powershell
# Start the application
.\start_arena.ps1

# Stop the application
.\start_arena.ps1 stop
```

The startup script will:
- Auto-create Python virtual environment and install dependencies
- Auto-install pnpm if not present (no sudo required)
- Build and deploy frontend automatically
- Start the backend service on port 8802
- Initialize the trading strategy manager
- Enable real-time price monitoring and auto-rebuild

**Access the application**: Open http://localhost:8802 in your browser

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

**Step 3: Configure AI Trader for Hyperliquid**

1. Navigate to **AI Traders** section
2. Create or edit an AI trader
3. In the configuration:
   - Enable **Hyperliquid Trading**: Toggle ON
   - Select **Environment**: Testnet or Mainnet
   - Choose **Prompt Template**: Select "Hyperliquid Pro" (includes leverage education)
   - Configure trading strategy triggers
4. The AI will now trade perpetual contracts on Hyperliquid

**Step 4: Monitor Your Trading**

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

Hyper Alpha Arena supports any OpenAI API compatible language model, including:

- **OpenAI**: GPT-5 series, o1 series, GPT-4o, GPT-4
- **Anthropic**: Claude (via compatible endpoints)
- **Deepseek**: Cost-effective alternative
- **Custom APIs**: Any OpenAI-compatible endpoint

The platform automatically handles model-specific configurations and parameter differences.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│   Frontend (React + TypeScript)                                │
│   - AI Trader Management                                        │
│   - Trading Dashboard (Paper + Hyperliquid)                     │
│   - Performance Charts & P&L Tracking                           │
│   - System Logs Viewer (Real-time)                             │
│   - Hyperliquid Configuration UI (Coming Soon)                  │
└────────────────────┬────────────────────────────────────────────┘
                     │ REST API + WebSocket
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│   Backend (FastAPI + Python)                                   │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │  Trading Engine                                         │  │
│   │  - Paper Trading: Simulated order matching             │  │
│   │  - Hyperliquid Trading: Real order execution (ccxt)    │  │
│   │  - AI Decision Service: Multi-model LLM integration    │  │
│   │  - Strategy Manager: Real-time/Interval/Tick triggers  │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │  Hyperliquid Integration (NEW)                          │  │
│   │  - Trading Client: CCXT-based API wrapper              │  │
│   │  - Environment Manager: Testnet/Mainnet isolation      │  │
│   │  - Encryption Service: Fernet private key protection   │  │
│   │  - Risk Management: Leverage limits & margin alerts    │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │  Market Data Service                                    │  │
│   │  - Price Stream: 1.5s polling interval (ccxt)          │  │
│   │  - Event Publisher: Real-time price updates            │  │
│   │  - Price Cache: In-memory caching with expiry          │  │
│   │  - Sampling Pool: Multi-symbol historical data         │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │  System Logger & Monitoring                             │  │
│   │  - Log Collector: 500-entry rotating buffer            │  │
│   │  - Price Snapshots: 60-second interval logging         │  │
│   │  - AI Decision Tracking: Full reasoning chain storage  │  │
│   │  - Hyperliquid Order Logs: Environment-tagged records  │  │
│   │  - Error Monitoring: Auto-categorization & alerts      │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │  Database (SQLite + SQLAlchemy)                         │  │
│   │  - accounts: Paper + Hyperliquid configs               │  │
│   │  - orders: Paper orders + Hyperliquid perpetuals       │  │
│   │  - positions: Paper + Hyperliquid position snapshots   │  │
│   │  - hyperliquid_account_snapshots: Real balance history │  │
│   │  - hyperliquid_positions: Position history with P&L    │  │
│   │  - ai_decision_logs: Prompt + reasoning + leverage     │  │
│   │  - strategy_configs: Real-time trigger configurations  │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │  Scheduler (APScheduler)                                │  │
│   │  - Paper AI Trading: 5-minute interval                 │  │
│   │  - Hyperliquid AI Trading: 5-minute interval           │  │
│   │  - Asset Curve Broadcast: 60-second WebSocket push     │  │
│   │  - Price Cache Cleanup: 2-minute maintenance           │  │
│   └─────────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│   External Services                                             │
│                                                                  │
│   ┌──────────────────────┐  ┌──────────────────────────────┐  │
│   │  LLM Providers       │  │  Hyperliquid DEX              │  │
│   │  - OpenAI (GPT-5)    │  │  - Testnet: Safe testing     │  │
│   │  - Anthropic (Claude)│  │  - Mainnet: Real trading     │  │
│   │  - Deepseek          │  │  - ccxt integration          │  │
│   │  - Custom APIs       │  │  - 1-50x leverage support    │  │
│   └──────────────────────┘  └──────────────────────────────┘  │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │  Cryptocurrency Exchanges (via ccxt)                    │  │
│   │  - Real-time price data for 6 major cryptocurrencies   │  │
│   │  - BTC, ETH, SOL, BNB, XRP, DOGE                        │  │
│   └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Tech Stack

### Backend
- **Framework**: FastAPI 0.116.1
- **Runtime**: Python 3.8+
- **Package Manager**: pip with virtual environment
- **Database**: SQLite with SQLAlchemy 2.0 ORM
- **Scheduler**: APScheduler 3.10+ for automated trading
- **Market Data**: ccxt 4.0+ for multi-exchange price feeds
- **Trading**: CCXT Hyperliquid integration for perpetual contracts
- **Security**: Cryptography (Fernet) for private key encryption
- **Wallet**: eth-account 0.10+ for Ethereum address derivation

### Frontend
- **Framework**: React 18.2.0
- **Build Tool**: Vite 4.5.14
- **Language**: TypeScript
- **UI Components**: Radix UI + Tailwind CSS
- **Charts**: lightweight-charts 5.0.9

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
- [🔄] Advanced order types (stop-loss, take-profit, trailing stops)
- [ ] Multi-timeframe analysis for AI decision-making
- [ ] Portfolio rebalancing across paper and real accounts
- [ ] Enhanced risk analytics dashboard
- [ ] Trade execution quality metrics
- [ ] Backtesting framework with historical data

### Phase 4: Multi-Exchange Expansion 📋 (Planned - v0.7.0)
- [ ] Binance spot and futures trading
- [ ] Bybit perpetual contracts
- [ ] OKX derivatives trading
- [ ] Exchange aggregation for best execution
- [ ] Cross-exchange arbitrage detection

### Phase 5: Advanced Features 🚀 (Long Term - v1.0.0+)
- [ ] AI agent marketplace and strategy sharing
- [ ] Multi-user support with role-based access
- [ ] Mobile app for trade monitoring
- [ ] Public API for third-party integrations
- [ ] On-chain trade verification
- [ ] Advanced portfolio analytics

## Key Improvements Over Original Project

### 🔥 Major Enhancements in v0.5.0

1. **Complete Hyperliquid DEX Integration**:
   - Full perpetual contract trading on testnet and mainnet
   - 1-50x leverage support with AI-driven selection
   - Real-time position tracking and P&L calculation
   - Fernet encryption for private key security
   - Environment isolation to prevent accidental cross-environment trades
   - Margin monitoring with auto-pause at 80% usage
   - Complete frontend UI with balance cards, order forms, and position tables

2. **Advanced AI Decision Engine**:
   - Multi-model LLM support (GPT-5, Claude, Deepseek, etc.)
   - Hyperliquid-specific prompt templates with leverage education
   - Intelligent leverage selection based on market confidence
   - Visual template editor with real-time preview
   - Account-specific prompt binding system

3. **Enhanced Performance & Reliability**:
   - 10x faster account operations (5s → 0.5s)
   - 95% reduction in API call frequency for better stability
   - Comprehensive system logging with auto-categorization
   - Real-time WebSocket updates for portfolio and positions
   - Price caching with automatic expiry management

4. **Professional Trading Features**:
   - Real-time/Interval/Tick-batch trading triggers
   - Multi-symbol sampling pool for historical data
   - Asset curve visualization for performance tracking
   - Automated trading scheduler for both paper and real trading
   - Manual trade trigger API for testing and debugging

5. **Security & Safety**:
   - Private key encryption using Fernet
   - Environment validation on every API call
   - Separate storage for testnet and mainnet keys
   - Liquidation warnings and risk alerts
   - Position snapshot history in database

## Troubleshooting

### Common Issues

**Problem**: Windows PowerShell execution policy error
**Solution**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Problem**: "此时不应有 ..." error on Windows
**Solution**: Ensure you're using PowerShell (not Command Prompt):
```powershell
.\start_arena.ps1
```

**Problem**: Port 8802 already in use
**Solution**:
- Linux/macOS: `./start_arena.sh stop`
- Windows: `.\start_arena.ps1 stop` (run from project root)

**Problem**: Virtual environment not found
**Solution**: Create the virtual environment manually:
```bash
# Linux/macOS
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e .

# Windows
cd backend && python -m venv .venv && .venv\Scripts\activate && pip install -e .
```

**Problem**: Frontend build fails
**Solution**: Clear cache and reinstall:
```bash
rm -rf node_modules package-lock.json  # Linux/macOS
rmdir /s node_modules && del package-lock.json  # Windows
pnpm install
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

This project is developed and maintained by **Heliki AI Community** - a group of AI enthusiasts and traders exploring the intersection of artificial intelligence and quantitative finance.

<div align="center">
  <img src="https://github.com/user-attachments/assets/9a5e5e8f-6c1f-4f9e-b8e5-7c3d5c3b8f4a" alt="Heliki AI Community" width="400"/>
</div>

**🌐 Official Website**: [https://www.heliki.com/](https://www.heliki.com/)

**🐦 Follow on Twitter/X**: [@GptHammer3309](https://x.com/GptHammer3309)
- Latest updates on Hyper Alpha Arena development
- AI trading insights and strategy discussions
- Community events and challenges
- Technical support and Q&A

**💡 What We Offer**:
- 2+ years of AI trading research and development
- Practical AI-powered trading tools and frameworks
- Active community discussions on LLM applications in finance
- Regular updates on quantitative trading strategies

**🎯 Get Involved**:
- ⭐ Star this repository to stay updated
- 🐛 Report bugs and issues on GitHub
- 💬 Join discussions and share your trading strategies
- 🤝 Contribute code, documentation, or ideas

### Premium AI Trading Resources

For advanced AI trading strategies, exclusive tools, and in-depth market analysis:
- **Premium Membership**: Access to proprietary AI models and trading signals
- **Private Discord**: Real-time discussions with experienced AI traders
- **Custom Strategies**: Personalized AI trading strategy development
- **Priority Support**: Direct technical support and consultation

Visit [Heliki.com](https://www.heliki.com/) for more information.

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

When using this software, please include attribution to Heliki AI Community in your documentation or product notices as required by the Apache License 2.0.

## Acknowledgments

- **etrobot** - Original open-alpha-arena project
- **nof1.ai** - Inspiration from Alpha Arena
- **Hyperliquid** - Decentralized perpetual exchange platform
- **OpenAI, Anthropic, Deepseek** - LLM providers

## Disclaimer

**IMPORTANT - READ CAREFULLY**

This software supports both paper trading (simulation) and real cryptocurrency trading via Hyperliquid perpetual contracts:

### Paper Trading Mode
- Simulation mode with no real funds at risk
- Safe for strategy development and testing
- Uses real market data for realistic simulation

### Hyperliquid Real Trading Mode (v0.4.0+)
- **REAL MONEY TRADING** - All trades execute on live markets
- **HIGH RISK** - Cryptocurrency trading with leverage carries extreme financial risk
- **YOUR RESPONSIBILITY** - You are solely responsible for all trading decisions and outcomes
- **NO LIABILITY** - Developers assume NO liability for trading losses, system failures, or data inaccuracies
- **TESTNET FIRST** - ALWAYS test thoroughly on Hyperliquid testnet before using mainnet
- **UNDERSTAND LEVERAGE** - Leverage (1-50x) amplifies both gains and losses; liquidation can result in total position loss
- **SECURITY** - Secure your private keys; compromised keys = loss of funds
- **NO GUARANTEES** - Past performance does not guarantee future results
- **REGULATORY COMPLIANCE** - Ensure compliance with your jurisdiction's laws

**By using Hyperliquid trading features, you acknowledge:**
- You understand the risks of leveraged cryptocurrency trading
- You have tested on testnet before using real funds
- You accept full responsibility for all outcomes
- You will not hold developers liable for any losses

**Recommended Safety Practices:**
1. Start with small position sizes on testnet
2. Never use maximum leverage without extensive testing
3. Monitor margin usage and set conservative limits
4. Keep majority of funds in cold storage
5. Use stop-loss orders (when implemented)
6. Never invest more than you can afford to lose

---

**Status**: Active Development | **Version**: 0.4.0-alpha | **Last Updated**: 2025-11-03

Star this repository to follow development progress. Frontend UI for Hyperliquid coming soon.
