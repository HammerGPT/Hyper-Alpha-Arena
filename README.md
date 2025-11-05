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

**Current Status**: v0.4.0 - Both paper trading and Hyperliquid real trading fully operational.

### Project Origin

This project is based on [open-alpha-arena](https://github.com/etrobot/open-alpha-arena) by etrobot. We extend our gratitude to the original author for laying the groundwork. Our fork introduces critical bug fixes, UI enhancements, improved AI decision engine, and market data integration from multiple sources including Hyperliquid.

## Features

### Current Features (v0.4.0)

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

#### Hyperliquid Real Trading Features (NEW in v0.4.0)
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

1. Open http://localhost:8802
2. Navigate to AI Traders section
3. Create your first AI trader:
   - Name: e.g., "GPT-5 Trader"
   - Model: Select from dropdown (gpt-5-mini, claude-sonnet-4.5, etc.)
   - API Key: Your OpenAI/Anthropic/Deepseek API key
   - Base URL: Leave default or use custom endpoint
4. Configure trading strategy:
   - Trigger Mode: Real-time (recommended for active trading)
   - Enable Strategy: Toggle to activate
5. Monitor logs in System Logs section to verify setup

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

### Phase 1: Paper Trading Infrastructure ✅ (Completed)
- [✅] Hyperliquid market data integration (read-only via ccxt)
- [✅] Real-time price feeds from multiple exchanges
- [✅] AI decision engine with multi-model support (GPT-5, Claude, Deepseek)
- [✅] Simulated order matching and execution engine
- [✅] Comprehensive logging and monitoring system with 60s refresh intervals
- [✅] Manual AI trade trigger API with force operation support
- [✅] Prompt template management system with Hyperliquid-specific templates

### Phase 2: Hyperliquid Real Trading ✅ (Completed - v0.4.0)
- [✅] Hyperliquid testnet trading with real order execution
- [✅] Hyperliquid mainnet trading support with environment isolation
- [✅] Private key encryption and secure storage (Fernet)
- [✅] Perpetual contract trading (long/short) with 1-50x leverage
- [✅] Real-time position tracking and P&L calculation
- [✅] AI-driven leverage-aware trading with risk management
- [✅] Margin usage monitoring and liquidation warnings
- [✅] Environment validation to prevent cross-environment operations
- [✅] Position and account snapshot history in database
- [✅] Automated trading scheduler for Hyperliquid accounts

### Phase 3: Frontend UI Development 🔄 (In Progress)
- [ ] Hyperliquid account configuration interface
- [ ] Real-time balance and margin usage display
- [ ] Position management table with P&L visualization
- [ ] Manual order placement form with liquidation calculator
- [ ] Environment switcher with safety confirmations
- [ ] AI decision logs enhanced with leverage parameters

### Phase 4: Trading Enhancement (Medium Term)
- [ ] Advanced order types (stop-loss, take-profit, trailing stops)
- [ ] Multiple exchange support (Binance, Bybit, OKX) for spot trading
- [ ] Historical data backtesting framework
- [ ] Advanced portfolio management and rebalancing
- [ ] Trading strategy optimization and A/B testing
- [ ] Risk analytics dashboard

### Phase 5: Advanced Features (Long Term)
- [ ] User-submitted AI agents marketplace
- [ ] On-chain trade verification and transparency
- [ ] Advanced analytics dashboard with custom metrics
- [ ] Public API for third-party integrations and webhooks
- [ ] Multi-user support with role-based access control
- [ ] Mobile app for trade monitoring

## Key Improvements Over Original Project

### Core Trading Enhancements
1. **Hyperliquid Real Trading Integration** (NEW in v0.4.0):
   - Complete perpetual contract trading system with CCXT integration
   - Testnet and mainnet support with strict environment isolation
   - 1-50x leverage support with AI-driven leverage selection
   - Real-time position tracking and P&L calculation
   - Private key encryption (Fernet) for secure storage
   - Margin usage monitoring with automatic trading pause at 80% usage
   - Liquidation price warnings and risk management
   - Position and account snapshot history in database

2. **LLM API Compatibility**:
   - Fixed parameter issues for GPT-5, o1, and Deepseek models
   - Proper max_completion_tokens handling for modern LLMs
   - Temperature restriction support for reasoning models

3. **Prompt Template Management System**:
   - Hyperliquid-specific templates with leverage education
   - Visual template editor with real-time multi-symbol preview
   - Account-specific prompt binding with automatic fallback
   - Default, Pro, and Hyperliquid templates optimized for different risk profiles
   - Template versioning and one-click restore functionality

### Performance & Reliability
4. **Performance Optimization**:
   - 10x faster account operations (5s to 0.5s)
   - 95% reduction in API call frequency (from 3s to 60s intervals)
   - Improved caching and state management

5. **System Logging & Monitoring**:
   - In-memory log collector (500 entries with automatic rotation)
   - Auto-categorization (price updates, AI decisions, Hyperliquid orders, errors)
   - Frontend dashboard with filtering and 60-second auto-refresh
   - Price snapshot tracking with database persistence
   - Hyperliquid order execution logs with environment tags

6. **Critical Bug Fixes**:
   - Fixed race condition in trading strategy manager
   - Resolved state management issues preventing real-time triggers
   - Corrected API trailing slash issues
   - Fixed FastAPI type annotation errors for Python 3.8+ compatibility
   - Improved JSON parsing with better error handling and regex fallback

### Feature Additions
7. **Real-time Trading Triggers**:
   - Event-driven strategy execution with three configurable modes
   - Real-time: Execute on every market update
   - Interval: Execute at fixed time intervals (5 minutes default)
   - Tick batch: Execute after N price updates

8. **Database Enhancements**:
   - Added Hyperliquid-specific tables (account snapshots, position history)
   - Extended Account table with 6 Hyperliquid configuration fields
   - Extended Order table with 6 perpetual contract fields
   - AI decision logs with prompt snapshots, reasoning chain, and leverage parameters

9. **Enhanced UI**:
   - Improved interface inspired by Alpha Arena
   - Modern design patterns with Radix UI and Tailwind CSS
   - Real-time WebSocket updates for portfolio and positions

10. **Market Data Integration**:
    - Real-time price feeds from multiple exchanges via ccxt
    - Multi-symbol sampling pool for intraday data
    - Price cache with automatic expiry management

11. **Manual Trade Trigger API**:
    - New endpoint for programmatic AI trading control
    - Force operation support for testing and debugging

### Security & Safety
12. **Security Features**:
    - Private key encryption using Fernet (cryptography library)
    - Environment validation on every Hyperliquid API call
    - Separate storage for testnet and mainnet private keys
    - Automatic trading pause when margin usage exceeds 80%
    - Position checks before environment switching

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

## Community

This project is developed and maintained by **Heliki AI Community**.

- Website: https://www.heliki.com/
- Focus: AI-powered trading tools and practical applications
- Community: 2+ years of AI trading research and development

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
