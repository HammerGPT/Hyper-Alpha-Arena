# Hyper Alpha Arena

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
- **Account Management**: Create and manage multiple AI trading accounts
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
<!-- Screenshot placeholder: Main dashboard showing leaderboard and performance metrics -->

### Account Configuration
<!-- Screenshot placeholder: Account settings page with model configuration -->

### Trading Controls
<!-- Screenshot placeholder: Trading toggle switch and auto-trading settings -->

## Installation

### Prerequisites

- **Operating System**: Linux, macOS, or Windows (WSL recommended)
- **Python**: 3.11 or higher
- **Node.js**: 18.x or higher
- **Package Managers**:
  - [pnpm](https://pnpm.io/installation): `npm install -g pnpm`
  - [uv](https://github.com/astral-sh/uv): Python package manager

### System Requirements

- RAM: Minimum 4GB, recommended 8GB
- Disk Space: At least 2GB free space
- Internet: Stable connection for market data and LLM API calls

### Step 1: Install Package Managers

```bash
# Install pnpm globally
npm install -g pnpm

# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

### Step 2: Clone the Repository

```bash
git clone https://github.com/HammerGPT/Hyper-Alpha-Arena.git
cd Hyper-Alpha-Arena
```

### Step 3: Install Dependencies

```bash
# Install frontend dependencies
pnpm install

# Install backend dependencies
cd backend
uv sync
cd ..
```

### Step 4: Build Frontend

```bash
# Build the React frontend
pnpm run build:frontend

# Copy build to backend static folder
rm -rf backend/static/*
cp -r frontend/dist/* backend/static/
```

### Step 5: Configure Environment Variables

Create a `.env` file in the `backend` directory:

```bash
cd backend
cat > .env << EOF
# Database
DATABASE_URL=sqlite:///./trading.db

# API Configuration (optional, can be set via UI)
# OPENAI_API_KEY=your_openai_api_key
# ANTHROPIC_API_KEY=your_anthropic_api_key
# DEEPSEEK_API_KEY=your_deepseek_api_key

# Server Configuration
HOST=0.0.0.0
PORT=8802
EOF
```

### Step 6: Start the Backend Service

```bash
# Start backend server
cd backend
uv run uvicorn main:app --host 0.0.0.0 --port 8802

# Or run in background with screen (Linux/macOS)
screen -dmS hyper-arena bash -c "uv run uvicorn main:app --host 0.0.0.0 --port 8802"
```

### Step 7: Verify Installation

```bash
# Check health endpoint
curl http://localhost:8802/api/health

# Expected response: {"status":"healthy"}
```

### Step 8: Access the Application

Open your browser and navigate to:
```
http://localhost:8802
```

## Usage

### 1. Create an AI Trading Account

1. Click the settings icon in the top-right corner
2. Click "Add Account"
3. Fill in the account details:
   - **Account Name**: e.g., "GPT-5 Trader"
   - **Model Name**: e.g., `gpt-5-mini`, `deepseek-chat`, `claude-3-5-sonnet`
   - **Base URL**: API endpoint (default: `https://api.openai.com/v1`)
   - **API Key**: Your LLM provider API key
   - **Initial Capital**: Starting balance (default: $10,000)
4. Click "Test Connection" to verify the API configuration
5. Click "Save" to create the account

### 2. Enable Auto Trading

1. In the account settings, find the trading account
2. Toggle the "Auto Trading" switch
3. The AI model will start making trading decisions at regular intervals
4. Monitor performance on the main dashboard

### 3. View Performance

- **Portfolio Value**: Real-time account balance
- **Positions**: Current open positions
- **Trade History**: Past trading decisions
- **Performance Metrics**: PnL, win rate, and other statistics

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
│   - Account Management                │
│   - Trading Dashboard                 │
│   - Performance Charts                │
└───────────────┬────────────────────────┘
                │ REST API + WebSocket
                ▼
┌────────────────────────────────────────┐
│   Backend (FastAPI + Python)          │
│   - Multi-model LLM Integration       │
│   - Trading Engine                    │
│   - Market Data Service (ccxt)        │
│   - Auto Trading Scheduler            │
│   - Risk Management                   │
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

## Development

### Running in Development Mode

```bash
# Start backend with auto-reload
cd backend
uv run uvicorn main:app --reload --port 8802

# Start frontend dev server (optional)
cd frontend
pnpm run dev
```

### Running Tests

```bash
cd backend
uv run pytest
```

## Key Improvements Over Original Project

1. **LLM API Compatibility**: Fixed parameter issues for GPT-5, o1, and Deepseek models
2. **Performance Optimization**: 10x faster account operations (5s to 0.5s)
3. **Enhanced UI**: Improved interface mimicking Alpha Arena design
4. **Hyperliquid Integration**: Real trading capabilities (in development)

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
