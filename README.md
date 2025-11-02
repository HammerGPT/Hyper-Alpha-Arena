 # <img width="40" height="40" alt="logo_app" src="https://github.com/user-attachments/assets/911ba846-a08b-4e3e-b119-ec1e78347288" style="vertical-align: middle;" /> Hyper Alpha Arena

> An open-source AI-powered paper trading platform with simulated cryptocurrency trading and Hyperliquid market data integration.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![GitHub stars](https://img.shields.io/github/stars/HammerGPT/Hyper-Alpha-Arena)](https://github.com/HammerGPT/Hyper-Alpha-Arena/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/HammerGPT/Hyper-Alpha-Arena)](https://github.com/HammerGPT/Hyper-Alpha-Arena/network)

## Overview

Hyper Alpha Arena is an advanced AI-powered paper trading platform where Large Language Models (LLMs) autonomously execute simulated cryptocurrency trading strategies. Inspired by [nof1 Alpha Arena](https://nof1.ai), this platform enables AI models like GPT-5, Claude, Deepseek, and others to make intelligent trading decisions based on real-time market data from Hyperliquid and other exchanges.

**Current Status**: Paper trading with real market data. Real exchange integration for live trading is under development.

### Project Origin

This project is based on [open-alpha-arena](https://github.com/etrobot/open-alpha-arena) by etrobot. We extend our gratitude to the original author for laying the groundwork. Our fork introduces critical bug fixes, UI enhancements, improved AI decision engine, and market data integration from multiple sources including Hyperliquid.

## Features

### Current Features (v0.3.0-alpha)

- **Multi-Model LLM Support**: OpenAI API compatible models
- **Prompt Template Management**: NEW FEATURE
  - Customizable AI trading prompts with visual editor
  - Account-specific prompt binding system
  - Default and Pro templates with restore functionality
  - Automatic fallback to default template for unbound accounts
- **Paper Trading Engine**: Simulated order matching and position management for risk-free strategy testing
- **Real-time Market Data**: Live cryptocurrency price feeds from Hyperliquid and other exchanges via ccxt
- **AI Trader Management**: Create and manage multiple AI trading agents
- **Real-time Trading Triggers**: Event-driven AI trading with configurable strategies
  - Real-time trigger: Execute on every market update
  - Interval trigger: Execute at fixed time intervals
  - Tick batch trigger: Execute after N price updates
- **System Logs & Monitoring**: Comprehensive logging system for debugging and monitoring
  - Real-time price update tracking (60-second snapshots)
  - AI decision logs with full reasoning context
  - Error and warning detection
  - Filterable log categories and severity levels
  - Auto-refresh dashboard with statistics
- **Auto Trading**: Automated trading scheduler with customizable intervals
- **WebSocket Updates**: Real-time portfolio and position updates
- **Performance Dashboard**: Track AI model performance metrics
- **API Compatibility**: Fixed parameter issues for modern LLM APIs (max_completion_tokens, temperature restrictions)

### Upcoming Features

- **Live Trading Integration**: Real order execution on Hyperliquid testnet and mainnet
- **Advanced Risk Management**: Position limits, leverage controls, stop-loss/take-profit automation
- **Multiple Exchange Support**: Live trading on Binance, Bybit, and other major exchanges
- **Backtesting Framework**: Historical data simulation and strategy optimization
- **Trade Execution Analytics**: Slippage analysis and execution quality metrics

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
┌────────────────────────────────────────┐
│   Frontend (React + TypeScript)       │
│   - AI Trader Management              │
│   - Trading Dashboard                 │
│   - Performance Charts                │
│   - System Logs Viewer                │
└───────────────┬────────────────────────┘
                │ REST API + WebSocket
                ▼
┌────────────────────────────────────────┐
│   Backend (FastAPI + Python)          │
│                                        │
│   ┌──────────────────────────────┐   │
│   │  Trading Engine              │   │
│   │  - Real-time Strategy Manager│   │
│   │  - Multi-model LLM Router    │   │
│   │  - Order Execution           │   │
│   └──────────────────────────────┘   │
│                                        │
│   ┌──────────────────────────────┐   │
│   │  Market Data Service         │   │
│   │  - Price Stream (1.5s polls) │   │
│   │  - Event Publisher           │   │
│   │  - Price Cache               │   │
│   └──────────────────────────────┘   │
│                                        │
│   ┌──────────────────────────────┐   │
│   │  System Logger               │   │
│   │  - Log Collector (500 cache) │   │
│   │  - Price Snapshots (60s)     │   │
│   │  - AI Decision Tracking      │   │
│   │  - Error Monitoring          │   │
│   └──────────────────────────────┘   │
│                                        │
│   ┌──────────────────────────────┐   │
│   │  Database (SQLite)           │   │
│   │  - AI Decision Logs          │   │
│   │  - Trading History           │   │
│   │  - Strategy Configs          │   │
│   └──────────────────────────────┘   │
└───────────────┬────────────────────────┘
                │
                ▼
┌────────────────────────────────────────┐
│   External Services                    │
│   - OpenAI / Anthropic / Deepseek     │
│   - Hyperliquid (coming soon)         │
│   - Cryptocurrency Exchanges (ccxt)   │
└────────────────────────────────────────┘
```

## Tech Stack

### Backend
- **Framework**: FastAPI 0.116.1
- **Runtime**: Python 3.11
- **Package Manager**: uv 0.9.5
- **Database**: SQLite (via SQLAlchemy)
- **Scheduler**: APScheduler
- **Market Data**: ccxt 4.5.11

### Frontend
- **Framework**: React 18.2.0
- **Build Tool**: Vite 4.5.14
- **Language**: TypeScript
- **UI Components**: Radix UI + Tailwind CSS
- **Charts**: lightweight-charts 5.0.9

## Roadmap

### Phase 1: Paper Trading Infrastructure (Completed)
- [✔️] Hyperliquid market data integration (read-only via ccxt)
- [✔️] Real-time price feeds from multiple exchanges
- [✔️] AI decision engine with multi-model support (GPT-5, Claude, Deepseek)
- [✔️] Simulated order matching and execution engine
- [✔️] Comprehensive logging and monitoring system with 60s refresh intervals
- [✔️] Manual AI trade trigger API with force operation support

### Phase 2: Live Trading Integration (Current Focus)
- [ ] Hyperliquid testnet trading with real order execution
- [ ] Account authentication and API key management for exchanges
- [ ] Real-time position synchronization with exchange APIs
- [ ] Advanced risk management with position limits and stop-loss
- [ ] Production-ready error handling and failover mechanisms

### Phase 3: Trading Enhancement (Medium Term)
- [ ] Multiple exchange support (Binance, Bybit, OKX, etc.)
- [ ] Historical data backtesting framework
- [ ] Advanced portfolio management and rebalancing
- [ ] Trading strategy optimization and A/B testing

### Phase 4: Advanced Features (Long Term)
- [ ] User-submitted AI agents marketplace
- [ ] On-chain trade verification and transparency
- [ ] Advanced analytics dashboard with custom metrics
- [ ] Public API for third-party integrations and webhooks

## Key Improvements Over Original Project

1. **LLM API Compatibility**: Fixed parameter issues for GPT-5, o1, and Deepseek models with proper max_completion_tokens handling
2. **Performance Optimization**: 10x faster account operations (5s to 0.5s) and reduced API call frequency (95% reduction from 3s to 60s intervals)
3. **Enhanced UI**: Improved interface inspired by Alpha Arena with modern design patterns
4. **Market Data Integration**: Real-time price feeds from Hyperliquid and multiple exchanges via ccxt
5. **System Logging & Monitoring**: Comprehensive real-time logging system
   - In-memory log collector (500 entries with automatic rotation)
   - Auto-categorization (price updates, AI decisions, errors, warnings)
   - Frontend dashboard with filtering and 60-second auto-refresh
   - Price snapshot tracking with database persistence
6. **Critical Bug Fixes**:
   - Fixed race condition in trading strategy manager causing AI traders to freeze
   - Resolved state management issues preventing real-time triggers
   - Corrected API trailing slash issues in frontend requests
   - Fixed FastAPI type annotation errors for Python 3.8+ compatibility
   - Improved JSON parsing with better error handling and regex fallback
7. **Real-time Trading Triggers**: Event-driven strategy execution with three configurable modes
   - Real-time: Execute on every market update
   - Interval: Execute at fixed time intervals
   - Tick batch: Execute after N price updates
8. **Database Enhancements**: Added snapshot fields for AI decision debugging (full prompt, reasoning chain, final decision)
9. **Prompt Template Management System**: Professional prompt engineering interface
   - Visual template editor with real-time multi-symbol preview
   - Account-specific prompt binding with automatic fallback to default
   - Default and Pro templates optimized for different risk profiles
   - Template versioning and one-click restore functionality
10. **Manual Trade Trigger API**: New endpoint for programmatic AI trading control with force operation support

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

This software is currently a paper trading simulation platform for educational and research purposes only. All trades are simulated and no real funds are at risk. When live trading features are implemented in future versions, cryptocurrency trading will carry significant financial risk. Users will be solely responsible for their trading decisions and any financial outcomes. The developers assume no liability for trading losses, system failures, or data inaccuracies. Always conduct thorough testing on exchange testnets before deploying any real capital.

---

**Status**: Active Development | **Version**: 0.3.1-alpha | **Last Updated**: 2025-10-31

Star this repository to follow development progress and receive updates on Hyperliquid integration.
