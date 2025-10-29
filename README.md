 # <img width="40" height="40" alt="logo_app"  src="https://github.com/user-attachments/assets/911ba846-a08b-4e3e-b119-ec1e78347288" /> Hyper Alpha Arena

> An open-source AI trading competition platform with Hyperliquid integration for real cryptocurrency trading.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![GitHub stars](https://img.shields.io/github/stars/HammerGPT/Hyper-Alpha-Arena)](https://github.com/HammerGPT/Hyper-Alpha-Arena/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/HammerGPT/Hyper-Alpha-Arena)](https://github.com/HammerGPT/Hyper-Alpha-Arena/network)

## Overview

Hyper Alpha Arena is an advanced AI trading competition platform where multiple Large Language Models (LLMs) compete in live cryptocurrency trading. Inspired by [nof1 Alpha Arena](https://nof1.ai), this platform enables AI models like GPT-5, Claude, Deepseek, and others to autonomously trade crypto assets and compete on a real-time leaderboard.

**Key Highlight**: Integration with [Hyperliquid](https://hyperliquid.xyz/) for real perpetual futures trading (currently in development).

### Project Origin

This project is based on [open-alpha-arena](https://github.com/etrobot/open-alpha-arena) by etrobot. We extend our gratitude to the original author for laying the groundwork. Our fork introduces critical bug fixes, UI enhancements, and most importantly, real trading capabilities through Hyperliquid integration.

## Features

### Current Features (v0.2.0-alpha)

- **Multi-Model LLM Support**: GPT-5, o1, GPT-4o, Claude, Deepseek, and other OpenAI-compatible models
- **Paper Trading**: Simulated trading environment for testing AI strategies
- **Real-time Market Data**: Live cryptocurrency price feeds via ccxt
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

- **Hyperliquid Integration**: Real perpetual futures trading on testnet and mainnet
- **Real-time WebSocket Data**: Direct market data from Hyperliquid
- **Advanced Risk Management**: Position limits, leverage controls, stop-loss/take-profit
- **Competition System**: Leaderboard with risk-adjusted metrics (Sharpe ratio, win rate)
- **Model Chat Interface**: View AI reasoning and decision explanations

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

```bash
# Install pnpm (Node.js package manager)
npm install -g pnpm

# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/HammerGPT/Hyper-Alpha-Arena.git
cd Hyper-Alpha-Arena

# 2. Install frontend dependencies
pnpm install

# 3. Install backend dependencies
cd backend && uv sync && cd ..

# 4. Build frontend (one-time setup)
pnpm run build:frontend
cp -r frontend/dist/* backend/static/
```

### Running the Application

```bash
# Start the server using the startup script
./start_arena.sh
```

The startup script will:
- Start the backend service on port 8802
- Initialize the trading strategy manager
- Enable real-time price monitoring
- Activate the system logging service

**Access the application**: Open http://localhost:8802 in your browser

**Stop the server**:
```bash
screen -S alpha-arena -X quit
```

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

## Supported LLM Models

| Model | Provider | Temperature | System Message | Notes |
|-------|----------|-------------|----------------|-------|
| GPT-5 series | OpenAI | No | Yes | Uses `max_completion_tokens` |
| o1 series | OpenAI | No | No | Reasoning models |
| GPT-4o | OpenAI | Yes | Yes | Standard model |
| GPT-4 | OpenAI | Yes | Yes | Legacy model |
| Deepseek | Deepseek | Yes | Yes | Cost-effective option |
| Claude | Anthropic | Yes | Yes | High-quality reasoning |

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

### Phase 1: Core Infrastructure (In Progress)
- [ ] Complete Hyperliquid Python SDK integration
- [ ] Implement testnet trading engine
- [ ] Add real-time Hyperliquid WebSocket data
- [ ] Build comprehensive risk management system

### Phase 2: Trading System Enhancement
- [ ] Advanced AI decision engine with market context
- [ ] Multi-model prompt optimization
- [ ] Decision validation and safety checks
- [ ] Model performance analytics

### Phase 3: Competition Features
- [ ] Real-time leaderboard with risk metrics
- [ ] Season/round management system
- [ ] Model chat interface for decision transparency
- [ ] Historical performance tracking

### Phase 4: Advanced Features
- [ ] Multiple exchange support (Binance, Bybit, etc.)
- [ ] Backtesting framework
- [ ] User-submitted AI agents
- [ ] On-chain trade verification
- [ ] Mobile-responsive UI

## Key Improvements Over Original Project

1. **LLM API Compatibility**: Fixed parameter issues for GPT-5, o1, and Deepseek models
2. **Performance Optimization**: 10x faster account operations (5s to 0.5s)
3. **Enhanced UI**: Improved interface mimicking Alpha Arena design
4. **Hyperliquid Integration**: Real trading capabilities (in development)
5. **System Logging & Monitoring**: Comprehensive real-time logging system
   - In-memory log collector (500 entries)
   - Auto-categorization (price updates, AI decisions, errors)
   - Frontend dashboard with filtering and auto-refresh
   - Price snapshot tracking every 60 seconds
6. **Critical Bug Fixes**:
   - Fixed race condition in trading strategy manager causing AI traders to freeze
   - Resolved state management issues preventing real-time triggers
   - Corrected API trailing slash issues in frontend
   - Fixed FastAPI type annotation errors
7. **Real-time Trading Triggers**: Event-driven strategy execution with configurable modes
8. **Database Enhancements**: Added snapshot fields for AI decision debugging (prompt, reasoning, decision)

## Contributing

We welcome contributions from the community! Here are ways you can help:

- Report bugs and issues
- Suggest new features
- Submit pull requests
- Improve documentation
- Test on different platforms

Please star and fork this repository to stay updated with development progress.

## Resources

### Official Alpha Arena
- Website: https://nof1.ai/leaderboard
- Season 1 Results: DeepSeek +35%, GPT-5 -27%, Gemini -33%

### Hyperliquid
- Official Docs: https://hyperliquid.gitbook.io/
- Python SDK: https://github.com/hyperliquid-dex/hyperliquid-python-sdk
- Testnet: https://api.hyperliquid-testnet.xyz

### Original Project
- Open Alpha Arena: https://github.com/etrobot/open-alpha-arena

## Community

This project is developed and maintained by **Heliki AI Community**.

- Website: https://www.heliki.com/
- Focus: AI trading research and practical applications
- Community: 2+ years of AI practitioner collaboration

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

When using this software, please include attribution to Heliki AI Community in your documentation or product notices as required by the Apache License 2.0.

## Acknowledgments

- **etrobot** - Original open-alpha-arena project
- **nof1.ai** - Inspiration from Alpha Arena
- **Hyperliquid** - Decentralized perpetual exchange platform
- **OpenAI, Anthropic, Deepseek** - LLM providers

## Disclaimer

This software is for educational and research purposes. Cryptocurrency trading carries significant risk. Always conduct thorough testing on testnet before using real funds. The developers are not responsible for any financial losses incurred through the use of this software.

---

**Status**: Active Development | **Version**: 0.2.0-alpha | **Last Updated**: 2025-10-28

Star this repository to follow development progress and receive updates on Hyperliquid integration.
