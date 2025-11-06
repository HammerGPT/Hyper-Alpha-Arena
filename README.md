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

#### PostgreSQL Database Issues

**Problem**: "PostgreSQL not found" or "connection failed" during startup
**Solution**:

The application uses PostgreSQL for better concurrency handling. The startup script will attempt to install it automatically on Linux, but you may need to install it manually on some systems.

**Linux (Ubuntu/Debian)**:
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**Linux (CentOS/RHEL)**:
```bash
sudo yum install postgresql-server postgresql-contrib
sudo postgresql-setup initdb
sudo systemctl enable postgresql
sudo systemctl start postgresql
```

**macOS**:
```bash
# Using Homebrew
brew install postgresql@14
brew services start postgresql@14

# Or download PostgreSQL.app from https://postgresapp.com/
```

**Windows**:
```powershell
# Using winget
winget install PostgreSQL.PostgreSQL

# Or download installer from https://www.postgresql.org/download/windows/
```

After installation, restart the application with `./start_arena.sh` (Linux/macOS) or `.\start_arena.ps1` (Windows).

**Problem**: "fe_sendauth: no password supplied" or authentication errors
**Solution**:

This means PostgreSQL is installed but requires authentication configuration. The application will still work if databases are already created. If you see this error on first install:

1. Allow local connections without password (for development):
   ```bash
   # Edit PostgreSQL config (location varies by system)
   sudo nano /etc/postgresql/*/main/pg_hba.conf

   # Change this line:
   local   all             all                                     peer
   # To:
   local   all             all                                     trust

   # Restart PostgreSQL
   sudo systemctl restart postgresql
   ```

2. Or manually create the database:
   ```bash
   sudo -u postgres psql
   CREATE USER alpha_user WITH PASSWORD 'alpha_pass';
   CREATE DATABASE alpha_arena OWNER alpha_user;
   CREATE DATABASE alpha_snapshots OWNER alpha_user;
   \q
   ```

**Note**: If you see PostgreSQL warnings during startup but the service starts successfully, you can safely ignore them. The application will create tables automatically on first run.

#### Other Common Issues

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
