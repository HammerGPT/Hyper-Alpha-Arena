 # <img width="40" height="40" alt="logo_app" src="https://github.com/user-attachments/assets/911ba846-a08b-4e3e-b119-ec1e78347288" style="vertical-align: middle;" /> Hyper Alpha Arena

> An open-source AI-powered cryptocurrency trading platform for autonomous trading with Large Language Models. Deploy AI trading strategies with both paper trading simulation and real perpetual contract trading on Hyperliquid DEX.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![GitHub stars](https://img.shields.io/github/stars/HammerGPT/Hyper-Alpha-Arena)](https://github.com/HammerGPT/Hyper-Alpha-Arena/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/HammerGPT/Hyper-Alpha-Arena)](https://github.com/HammerGPT/Hyper-Alpha-Arena/network)

> **🚨 BREAKING CHANGE - Multi-Wallet Architecture (v0.6.0)**
>
> **For users upgrading from v0.5.x or earlier:** This version introduces a major architectural change. Each AI Trader can now configure separate wallets for Testnet and Mainnet environments.
>
> **⚠️ MIGRATION REQUIRED**: You must run the migration script to preserve your existing wallet configurations:
> ```bash
> cd backend
> python database/migrations/migrate_to_multi_wallet.py
> ```
>
> **What Changed:**
> - New `hyperliquid_wallets` table for independent testnet/mainnet wallet storage
> - Global trading mode switch (testnet/mainnet) applies to all AI Traders
> - Environment isolation for cache, API calls, and data queries
> - Enhanced wallet configuration UI with dual-environment display
>
> See [Upgrading from v0.5.x](#upgrading-from-v05x-multi-wallet-migration) section below for detailed instructions.

## Overview

Hyper Alpha Arena is a production-ready AI trading platform where Large Language Models (LLMs) autonomously execute cryptocurrency trading strategies. Inspired by [nof1 Alpha Arena](https://nof1.ai), this platform enables AI models like GPT-5, Claude, and Deepseek to make intelligent trading decisions based on real-time market data and execute trades automatically.

**Official Website:** https://www.akooi.com/

**Trading Modes:**
- **Hyperliquid Testnet (Paper Trading)**: Risk-free testing with real market mechanics, free test funds, and actual order book - a superior paper trading experience
- **Hyperliquid Mainnet**: Live trading on decentralized perpetual exchange with 1-50x leverage support (real capital at risk)

**Current Status**: v0.6.0 - Multi-Wallet Architecture with independent testnet/mainnet wallet management.


## Features

### Current Features (v0.6.0)

#### Core Trading Features
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

#### Hyperliquid Trading Features
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
- **Enhanced Monitoring**:
  - API rate limit tracking for Hyperliquid wallets
  - Detailed exchange action logging
  - Environment validation with clear error messages

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

---

### Upgrading from v0.5.x (Multi-Wallet Migration)

**⚠️ IMPORTANT**: v0.6.0 introduces a breaking change with the new Multi-Wallet Architecture. You must run the migration script to preserve your wallet configurations.

**What's New:**
- Each AI Trader can now configure separate Testnet and Mainnet wallets
- Global trading mode switch controls which environment all AI Traders use
- Enhanced environment isolation prevents data contamination between testnet/mainnet

**Migration Steps:**

1. **Backup Your Data** (Recommended):
```bash
cd Hyper-Alpha-Arena
docker-compose exec postgres pg_dump -U alpha_user alpha_arena > backup_$(date +%Y%m%d).sql
```

2. **Pull Latest Code**:
```bash
git pull origin main
```

3. **Rebuild Containers** (This will auto-create the new `hyperliquid_wallets` table):
```bash
docker-compose down
docker-compose up -d --build
```

4. **Run Migration Script** (Critical Step):
```bash
# Wait for containers to be healthy
docker-compose ps

# Run migration
docker-compose exec app python database/migrations/migrate_to_multi_wallet.py
```

**Expected Migration Output:**
```
============================================================
Starting migration to multi-wallet architecture
============================================================
Creating hyperliquid_wallets table...
✓ hyperliquid_wallets table created
Migrating Account private keys to hyperliquid_wallets...
Found X accounts with Hyperliquid configuration
  Account Y (Name): migrated wallet 0x...
Migration complete: X wallets migrated, 0 skipped
✓ Global trading_mode initialized to 'testnet'
============================================================
Migration completed successfully!
============================================================
```

5. **Verify Migration**:
- Open http://localhost:8802
- Navigate to **AI Traders** → Select a trader → **Hyperliquid Wallet**
- You should see your wallet configurations migrated to the new UI
- Check **System Logs** for any migration warnings

**Troubleshooting:**
- If migration reports "0 wallets migrated", your accounts may not have had Hyperliquid configured previously
- If you see "wallet already exists" messages, the migration has already been run
- Old wallet configurations remain in the `accounts` table for backup purposes
- Contact support if you encounter errors during migration

---

### Upgrading from Previous Versions (v0.4.x or earlier)

**For v0.4.x or earlier users upgrading to v0.6.0:**

Due to significant database schema changes (wallet address tracking and multi-wallet architecture), we recommend a clean installation for older versions:

**Clean Installation** (Deletes Historical Data):

```bash
# ⚠️ This will delete all historical data
docker-compose down -v
git pull origin main
docker-compose up -d --build
```

**Why clean installation for v0.4.x?**
- Multiple breaking schema changes between v0.4.x and v0.6.0
- Old trading records lack wallet addresses and environment tracking
- Migration from v0.4.x → v0.6.0 requires multiple sequential migration scripts
- Clean start ensures compatibility and avoids partial migration issues

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

**Note on Multi-Wallet Architecture:**
- Each AI Trader can have both testnet and mainnet wallets configured simultaneously
- The global trading mode determines which wallet is active
- You can switch modes instantly without reconfiguring wallets
- Only configure mainnet wallets after thorough testnet testing

**Step 4: Configure Market Watchlist**

1. Navigate to **Hyperliquid** page → **Market Watchlist** section
2. Select up to 10 symbols you want the AI to monitor (e.g., BTC, ETH, SOL)
3. The order you select determines the AI's evaluation priority
4. Save your selection
5. This watchlist applies to all AI Traders and affects:
   - Hyperliquid-specific AI prompts
   - Model decision scope
   - Live market data queries

**Step 5: Enable Auto Trading**

1. In your AI Trader configuration
2. Toggle **Auto Trading** to ON
3. Configure trading strategy:
   - Trigger Mode: Real-time (recommended for active trading)
   - Trigger Interval: 60-150 seconds
   - Price Threshold: 0.5-2.0%
4. Choose appropriate **Prompt Template**: "Hyperliquid Pro" includes leverage education
5. Monitor initial trades carefully in **System Logs**

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

**Multi-Wallet Architecture Benefits:**
- Each AI Trader has independent wallet configurations for testnet and mainnet
- No wallet address conflicts between different AI models
- Accurate per-model performance tracking across both environments
- Seamless environment switching without reconfiguration

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

### Phase 2.5: Multi-Wallet Architecture ✅ (Completed - v0.6.0)
- [✅] **Independent wallet management** - Each AI Trader can configure separate testnet/mainnet wallets
- [✅] **Global trading mode** - Centralized environment switch for all AI Traders
- [✅] **Environment isolation enhancement** - Composite cache keys `(account_id, environment)`
- [✅] **Wallet configuration UI redesign** - Dual-environment wallet panels with balance display
- [✅] **Trade page refactor** - Global trading console with multi-wallet selector
- [✅] **API rate limit tracking** - Monitor Hyperliquid request quota per wallet
- [✅] **Exchange action logging** - Detailed API call history for debugging
- [✅] **Migration tooling** - Automated script for upgrading from v0.5.x
- [✅] **Environment parameter propagation** - All API calls and cache operations environment-aware

### Phase 3: Enhancement & Optimization 🔄 (In Progress - v0.7.0)
- [🔄] Enhanced risk analytics dashboard with liquidation risk scoring
- [ ] Multiple trading pair support expansion (beyond current BTC, ETH, SOL focus)
- [ ] Advanced order types (stop-loss, take-profit, trailing stops)
- [ ] Multi-timeframe analysis for AI decision-making (1m, 5m, 15m, 1h charts)
- [ ] Backtesting framework with historical market data replay
- [ ] Performance comparison tools for A/B testing different AI models

### Phase 4: Trading Platform Expansion 📋 (Planned - v0.8.0)
- [ ] Binance spot and futures trading
- [ ] Bybit perpetual contracts
- [ ] OKX derivatives trading
- [ ] Exchange aggregation for best execution
- [ ] Cross-exchange arbitrage detection

### Phase 5: Advanced Features 🚀 (Long Term - v1.0.0+)
- [ ] AI agent marketplace and strategy sharing
- [ ] Multi-user support with role-based access control
- [ ] Mobile app for real-time trade monitoring and alerts
- [ ] Advanced portfolio analytics and reporting dashboard
- [ ] Social trading features with strategy copying

## Key Improvements Over Original Project

### 🔥 Major Enhancements in v0.6.0

**Multi-Wallet Architecture**:
   - Each AI Trader maintains independent testnet and mainnet wallet configurations
   - Global trading mode switch enables instant environment changes without reconfiguration
   - Enhanced environment isolation with composite cache keys preventing data contamination
   - Dual-environment UI panels showing both testnet and mainnet balances simultaneously
   - Automated migration tooling for seamless upgrades from previous versions

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

### For Developers

**Hot Reload Configuration**: The project uses selective volume mounting in `docker-compose.yml` to enable Python code hot reload while preserving built frontend static files.

If you add new directories or important Python files under `backend/`, you need to update the `volumes` section in `docker-compose.yml` to enable hot reload for those new files. For example:

```yaml
volumes:
  - ./backend/your_new_directory:/app/backend/your_new_directory
  - ./backend/your_new_file.py:/app/backend/your_new_file.py
```

**IMPORTANT**: Never mount the entire `./backend` directory or the `./backend/static` directory, as this will override the built frontend files and cause "Frontend not built yet" errors.

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

**🌐 Official Website**: [https://www.akooi.com/](https://www.akooi.com/)

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

## FAQ (Frequently Asked Questions)

### How do I get testnet funds for paper trading?

When using Hyperliquid Testnet mode for paper trading, you'll need test funds to execute trades. If you see this warning in logs:

```
⚠️ Account skipped - No balance to trade! Equity: $0.00
Please deposit funds to wallet 0xYourWalletAddress
```

Follow these steps to get free testnet funds:

**Step 1: Get Your Wallet Address**
1. Navigate to the **Hyperliquid** page in the web interface
2. Make sure you've switched to **Testnet** mode
3. Your wallet address will be displayed in the configuration panel (starts with `0x...`)
4. Copy this address

**Step 2: Request Testnet Funds**
1. Visit the Hyperliquid Testnet interface: https://app.hyperliquid-testnet.xyz/
2. Connect your wallet or import your private key
3. Request testnet USDC from the faucet:
   - Look for the "Faucet" or "Get Test Funds" button
   - Request the maximum amount available (usually 10,000 USDC)
   - The funds should arrive within 1-2 minutes

**Step 3: Verify Balance**
1. Return to your Hyper Alpha Arena interface
2. Refresh the **Hyperliquid** page
3. You should see your balance updated
4. Wait for the next strategy trigger (60-150 seconds depending on your interval)
5. Check **System Logs** - you should now see AI decision logs

**Alternative Methods:**
- Join the Hyperliquid Discord community and ask for testnet funds
- Use Hyperliquid testnet bridge if available
- Contact Hyperliquid support for faucet issues

**Note**: Testnet funds have no real value and are reset periodically. This is a completely safe environment for testing your AI trading strategies.

### Why is my AI strategy not executing any trades?

Check these common issues in order:

1. **Zero Balance**: Check System Logs for warnings about "No balance to trade" - see FAQ above for getting testnet funds
2. **Strategy Not Enabled**: Verify "Start Trading" is toggled ON in AI Trader settings
3. **Trigger Interval**: Default is 150 seconds (2.5 minutes) - wait at least this long after enabling
4. **Price Threshold**: Default 1.0% - market needs to move enough to trigger
5. **Auto Trading Disabled**: Check that "Auto Trading" is enabled for your account
6. **API Key Issues**: Verify your AI model API key is valid and has sufficient credits

### What's the difference between Testnet and Mainnet?

- **Testnet (Paper Trading)**:
  - Uses test funds with no real value
  - Risk-free testing environment
  - Real market mechanics and order matching
  - Free unlimited test funds from faucet
  - Perfect for testing strategies before going live

- **Mainnet (Live Trading)**:
  - Uses real cryptocurrency (USDC)
  - Real money at risk - can result in losses
  - Live trading on Hyperliquid DEX
  - Requires real funds deposited to your wallet
  - Only use after thorough testing on testnet

**⚠️ Always test on testnet for at least 1 week before considering mainnet trading!**

---

Star this repository to follow development progress.
