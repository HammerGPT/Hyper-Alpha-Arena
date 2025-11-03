# Hyperliquid Integration & Enhanced Paper Trading - Strategic Plan

**Project**: Hyper Alpha Arena
**Objective**: Implement realistic paper trading + full Hyperliquid live trading integration
**Approach**: Balanced (5-7 weeks with comprehensive testing)
**Created**: 2025-11-02

---

## STRATEGIC OVERVIEW

### Goals
1. **Enhanced Paper Trading**: Realistic simulations without API credentials
2. **Live Trading Infrastructure**: Full Hyperliquid integration (testnet → mainnet)
3. **Risk Management**: Comprehensive safety measures for live trading
4. **User Safety**: Clear separation between paper and live modes

### User Preferences (From Planning Session)
- ✅ **Priority**: Enhanced paper trading first, then live trading
- ✅ **Exchange**: Hyperliquid only (simpler, faster delivery)
- ✅ **Paper Trading**: Real market data via public endpoints (no credentials)
- ✅ **Timeline**: 5-7 weeks balanced approach with full testing
- ✅ **Risk Tolerance**: Conservative - extensive testnet validation before mainnet

---

## PHASE BREAKDOWN

### ✅ PHASE 1: Enhanced Paper Trading (COMPLETED - Week 1)
**Duration**: 2-3 days
**Status**: 100% Complete, Ready for Testing
**Risk Level**: Low ✅

#### Deliverables
- [x] Paper trading simulation engine with realistic slippage (0.01-0.1%)
- [x] Execution latency simulation (50-200ms)
- [x] Partial fill simulation (10% chance for large orders)
- [x] Order rejection scenarios (2% base rate + liquidity limits)
- [x] Database schema updates (slippage + rejection_reason fields)
- [x] Backend API integration (return slippage in responses)
- [x] Frontend display (slippage on trades + PAPER TRADING badge)
- [x] Database initialization script

#### Success Criteria
- [x] Orders execute with realistic slippage
- [x] Large orders occasionally get partial fills
- [x] Orders >$100k rejected with clear reason
- [x] No API credentials required
- [ ] **PENDING**: 50+ test trades executed successfully

---

### 🔄 PHASE 2: Database Schema for Live Trading (Week 1-2)
**Duration**: 2 days
**Status**: Planned, Not Started
**Risk Level**: Low ✅

#### Objectives
Prepare database to support both paper and live trading modes.

#### Tasks
- [ ] Add Account table fields:
  - `trading_mode VARCHAR(10) DEFAULT 'PAPER'` (PAPER/LIVE)
  - `exchange VARCHAR(20) DEFAULT 'HYPERLIQUID'`
  - `exchange_api_key VARCHAR(500)` (encrypted)
  - `exchange_api_secret VARCHAR(500)` (encrypted)
  - `wallet_address VARCHAR(100)` (for Hyperliquid wallet auth)
  - `testnet_enabled VARCHAR(10) DEFAULT 'true'`

- [ ] Add Order table fields:
  - `exchange_order_id VARCHAR(100)` (exchange-assigned ID)
  - `exchange VARCHAR(20)` (which exchange)
  - `actual_fill_price DECIMAL(18,6)` (actual execution price)

- [ ] Create ExchangeConfig table:
  ```sql
  CREATE TABLE exchange_configs (
      id INTEGER PRIMARY KEY,
      exchange VARCHAR(20) NOT NULL,
      environment VARCHAR(10) NOT NULL,  -- TESTNET/MAINNET
      api_endpoint VARCHAR(200) NOT NULL,
      ws_endpoint VARCHAR(200),
      commission_rate FLOAT NOT NULL,
      min_commission FLOAT NOT NULL,
      max_leverage INT,
      UNIQUE(exchange, environment)
  );
  ```

- [ ] Create `/backend/config/exchanges.py`:
  - Hyperliquid testnet/mainnet endpoints
  - Commission rates (0.025% maker/taker)
  - Symbol format patterns (BTC/USDC:USDC)

- [ ] Create migration script (`002_add_live_trading_fields.py`)
- [ ] Test migration on fresh database
- [ ] Verify backward compatibility with existing paper trading

#### Success Criteria
- [ ] All accounts default to PAPER mode
- [ ] Schema supports both paper and live trading
- [ ] No disruption to existing paper trading functionality
- [ ] Migration reversible

---

### 🔄 PHASE 3: Hyperliquid Authentication (Week 2)
**Duration**: 2-3 days
**Status**: Planned, Not Started
**Risk Level**: Medium ⚠️

#### Objectives
Implement secure wallet-based authentication for Hyperliquid.

#### Tasks
- [ ] Install dependencies:
  - `uv add eth_account` (wallet signing)
  - `uv add cryptography` (Fernet encryption)

- [ ] Create `/backend/services/hyperliquid_auth.py`:
  - `HyperliquidAuth` class with wallet signing
  - `sign_request(payload)` method
  - Request signature generation

- [ ] Implement secure key storage:
  - Encryption key from environment variable (not in code/database)
  - `encrypt_private_key()` function
  - `decrypt_private_key()` function

- [ ] Update Account repository:
  - Add encryption/decryption methods
  - Validate wallet address format on creation
  - Never log/expose private keys

- [ ] Test on Hyperliquid testnet:
  - Generate test wallet
  - Sign test request
  - Verify signature acceptance

#### Success Criteria
- [ ] Can authenticate with Hyperliquid testnet using wallet signature
- [ ] Private keys encrypted at rest in database
- [ ] Encryption key never stored in code/database
- [ ] No private keys in logs

---

### 🔄 PHASE 4: Live Order Submission (Week 2-3)
**Duration**: 3-4 days
**Status**: Planned, Not Started
**Risk Level**: Medium ⚠️

#### Objectives
Submit real orders to Hyperliquid testnet.

#### Tasks
- [ ] Create `/backend/services/hyperliquid_trading.py`:
  - `HyperliquidTrading` class
  - `place_order(symbol, side, quantity, order_type, price)` method
  - `cancel_order(order_id)` method
  - `get_order_status(order_id)` method
  - Symbol format conversion (BTC → BTC/USDC:USDC)

- [ ] Update `/backend/services/order_matching.py`:
  - Add routing logic:
    ```python
    if account.trading_mode == 'LIVE':
        return _execute_order_live(db, order, account)
    else:
        return _execute_order_paper(db, order, account)
    ```
  - Keep paper trading logic unchanged
  - Store `exchange_order_id` from response

- [ ] Implement order status polling:
  - Background task to poll order status every 5s
  - Update Order.status when filled/rejected
  - Handle partial fills from exchange

- [ ] Error handling:
  - Catch exchange errors (insufficient funds, invalid symbol)
  - Retry logic with exponential backoff
  - Log all exchange interactions
  - User-friendly error messages

#### Success Criteria
- [ ] Can place MARKET and LIMIT orders on Hyperliquid testnet
- [ ] Exchange order IDs tracked in database
- [ ] Orders properly update from PENDING → FILLED
- [ ] Clear error messages for rejections
- [ ] No orders lost due to errors

---

### 🔄 PHASE 5: Account Synchronization (Week 3)
**Duration**: 2-3 days
**Status**: Planned, Not Started
**Risk Level**: Medium ⚠️

#### Objectives
Keep local database in sync with Hyperliquid account state.

#### Tasks
- [ ] Create `/backend/services/account_sync.py`:
  - `sync_balances(account_id)` - fetch from exchange
  - `sync_positions(account_id)` - fetch all open positions
  - `reconcile_discrepancies()` - handle differences

- [ ] Add to `hyperliquid_trading.py`:
  - `get_account_state()` - query account info
  - Parse balances (margin, unrealized PnL)
  - Parse positions (symbol, size, entry price)

- [ ] Scheduler integration:
  - Periodic sync every 60 seconds (configurable)
  - Manual sync endpoint: `POST /api/accounts/{id}/sync`
  - Log all sync operations

- [ ] Conflict resolution:
  - Exchange is source of truth for LIVE accounts
  - Log discrepancies (don't auto-correct >5%)
  - Alert user if large discrepancies detected

#### Success Criteria
- [ ] Balances sync accurately from Hyperliquid
- [ ] Positions reflect exchange state within 60 seconds
- [ ] Manual sync completes in <2 seconds
- [ ] Discrepancy alerts trigger correctly
- [ ] No data loss during sync

---

### 🔄 PHASE 6: Risk Management (Week 3-4)
**Duration**: 2-3 days
**Status**: Planned, Not Started
**Risk Level**: High 🚨

#### Objectives
Prevent catastrophic losses in live trading.

#### Tasks
- [ ] Create `/backend/services/risk_manager.py`:
  - `validate_order(account, order, current_price)` - check all rules
  - `check_stop_loss(position, current_price)` - auto-close positions
  - `check_daily_loss_limit(account)` - track daily P&L
  - `emergency_stop()` - disable all live trading

- [ ] Implement risk rules (configurable per account):
  - Max position size: 20% of account value
  - Max leverage: 5x for crypto
  - Daily loss limit: -5% of initial capital
  - Stop-loss per position: -10% from entry
  - Max concurrent positions: 5

- [ ] Create RiskConfig table:
  ```sql
  CREATE TABLE risk_configs (
      id INTEGER PRIMARY KEY,
      account_id INTEGER UNIQUE NOT NULL,
      max_position_size_pct FLOAT DEFAULT 0.20,
      max_leverage FLOAT DEFAULT 5.0,
      daily_loss_limit_pct FLOAT DEFAULT -0.05,
      stop_loss_pct FLOAT DEFAULT -0.10,
      max_positions INT DEFAULT 5
  );
  ```

- [ ] Integration:
  - Call `risk_manager.validate_order()` before every live order
  - Background task checks stop-loss every 5 seconds
  - Emergency stop endpoint: `POST /api/emergency-stop`

#### Success Criteria
- [ ] Orders rejected if they violate position size limits
- [ ] Positions auto-close when stop-loss triggered
- [ ] Daily loss limit prevents further trading
- [ ] Emergency stop disables all accounts instantly
- [ ] Risk rules saved and persisted per account

---

### 🔄 PHASE 7: WebSocket Streaming (Week 4)
**Duration**: 3-4 days
**Status**: Planned, Not Started
**Risk Level**: Medium ⚠️

#### Objectives
Replace 1.5s polling with real-time price updates.

#### Tasks
- [ ] Create `/backend/services/hyperliquid_websocket.py`:
  - Connect to `wss://api.hyperliquid-testnet.xyz/ws`
  - Subscribe to "allMids" channel for all symbols
  - Parse price updates
  - Publish to market_events

- [ ] Update `/backend/services/market_stream.py`:
  - Add toggle: use WebSocket if available, else polling
  - Graceful degradation on WebSocket failures
  - Reconnection logic with exponential backoff

- [ ] Heartbeat monitoring:
  - Send ping every 30 seconds
  - Reconnect if no pong within 60 seconds
  - Log all WebSocket connection events

- [ ] Testing:
  - 24-hour stability test on testnet
  - Monitor memory leaks
  - Test reconnection after network interruption

#### Success Criteria
- [ ] Price updates arrive in <100ms (vs 1.5s polling)
- [ ] WebSocket stays connected for 24+ hours
- [ ] Automatic reconnection on failures
- [ ] No memory leaks after 24h run

---

### 🔄 PHASE 8: Frontend Integration (Week 4-5)
**Duration**: 2-3 days
**Status**: Planned, Not Started
**Risk Level**: Low ✅

#### Objectives
UI for switching between PAPER and LIVE modes.

#### Tasks
- [ ] Account configuration UI:
  - Trading mode selector: PAPER / LIVE radio buttons
  - Testnet toggle checkbox (default: enabled)
  - Exchange credential inputs (masked)
  - Wallet address input with validation

- [ ] Visual indicators:
  - Paper trading: Blue badge "PAPER TRADING" (already done)
  - Live trading: Red badge "🔴 LIVE TRADING"
  - Testnet: Yellow badge "TESTNET"
  - Mainnet: No badge (assume production)

- [ ] Order details enhancement:
  - Show exchange order ID for live orders
  - Show slippage on all orders (already done)
  - Show rejection reasons (already done)
  - Link to Hyperliquid explorer for live orders

- [ ] Safety features:
  - Confirmation dialog when enabling live trading
  - Daily verification prompt for live accounts
  - Manual sync button with loading state
  - Emergency stop button (prominent red button)

#### Success Criteria
- [ ] Clear visual distinction between paper and live
- [ ] Cannot enable live trading without wallet address
- [ ] Confirmation required before switching to live mode
- [ ] Emergency stop accessible from all pages

---

### 🔄 PHASE 9: Testing & Validation (Week 5-6)
**Duration**: 3-5 days
**Status**: Planned, Not Started
**Risk Level**: High 🚨

#### Objectives
Comprehensive testnet validation before mainnet.

#### Testing Plan
1. **Paper Trading Tests** (1 day):
   - [ ] 100+ paper trades with slippage verification
   - [ ] Test all rejection scenarios
   - [ ] Verify partial fills work correctly

2. **Testnet Live Trading Tests** (2 days):
   - [ ] Place 200+ orders on Hyperliquid testnet
   - [ ] Test MARKET and LIMIT order types
   - [ ] Test BUY, SELL, and position closing
   - [ ] Verify position sync accuracy
   - [ ] Verify balance sync accuracy

3. **Risk Management Tests** (1 day):
   - [ ] Trigger stop-loss automation
   - [ ] Trigger daily loss limit
   - [ ] Test position size limit rejection
   - [ ] Test emergency stop

4. **Stability Tests** (1-2 days):
   - [ ] 24-hour continuous operation
   - [ ] 100 concurrent AI accounts trading
   - [ ] WebSocket reconnection under network instability
   - [ ] Database performance under load

5. **Error Handling Tests** (1 day):
   - [ ] Simulate exchange API errors (500, 503)
   - [ ] Simulate network timeouts
   - [ ] Simulate invalid credentials
   - [ ] Test graceful degradation

#### Success Criteria
- [ ] 100% of paper trades execute with slippage
- [ ] 95%+ testnet order success rate
- [ ] Stop-loss triggers correctly in <10 seconds
- [ ] System stable for 24+ hours under load
- [ ] All error scenarios handled gracefully

---

### 🔄 PHASE 10: Production Readiness (Week 6-7)
**Duration**: 2-3 days
**Status**: Planned, Not Started
**Risk Level**: High 🚨

#### Objectives
Security audit, monitoring, documentation.

#### Tasks
1. **Security Audit**:
   - [ ] Code review by 2+ developers
   - [ ] Verify key encryption implementation
   - [ ] Test API key permission scopes
   - [ ] Review rate limiting implementation
   - [ ] Penetration testing (if budget allows)

2. **Monitoring Dashboards**:
   - [ ] Grafana dashboard for live trading metrics
   - [ ] Track: order success rate, API latency, WebSocket uptime
   - [ ] Alert thresholds: >5% order failures, >500ms latency

3. **Alerting System**:
   - [ ] Email alerts for critical errors
   - [ ] SMS alerts for emergency stops
   - [ ] Daily summary reports for live accounts

4. **Documentation**:
   - [ ] Update CLAUDE.md with live trading sections
   - [ ] Create `/docs/LIVE_TRADING_GUIDE.md`
   - [ ] Create `/docs/RISK_MANAGEMENT.md`
   - [ ] Document emergency procedures

5. **Backup & Recovery**:
   - [ ] Automated daily database backups
   - [ ] Test restore procedure
   - [ ] Document rollback steps

6. **Gradual Rollout**:
   - [ ] Start with 1-2 test accounts on mainnet
   - [ ] Monitor for 7 days
   - [ ] Gradually increase to 5, then 10, then all accounts
   - [ ] Cap initial position sizes at $100

#### Success Criteria
- [ ] Security audit completed with no critical issues
- [ ] Monitoring dashboard showing key metrics
- [ ] Email/SMS alerts tested and working
- [ ] Documentation complete and reviewed
- [ ] Successful 7-day mainnet test with small positions

---

## RISK MITIGATION

### Critical Safety Measures
1. **Default to Paper Trading**: All new accounts start in PAPER mode
2. **Testnet First**: Require 100+ successful testnet trades before mainnet
3. **Small Position Limits**: Initial mainnet cap at $100 per position
4. **Emergency Stop**: Prominent kill switch accessible to admins
5. **Daily Verification**: Require daily check-in for live accounts
6. **Audit Trail**: Immutable log of all live trades
7. **Insurance Review**: Consult legal/insurance before mainnet launch

### Rollback Plan
- Keep paper trading fully functional during all phases
- Database migrations are reversible
- Feature flags to disable live trading instantly
- Maintain separate testnet and mainnet environments

---

## SUCCESS METRICS

### Phase 1 (Paper Trading)
- ✅ Slippage displays on 100% of trades
- ✅ Partial fills occur for ~10% of large orders
- ✅ Rejections occur for ~2% of orders
- [ ] 50+ test trades executed successfully

### Phases 2-10 (Live Trading)
- [ ] 95%+ order success rate on testnet
- [ ] <100ms price update latency (WebSocket)
- [ ] Zero security vulnerabilities
- [ ] 24+ hours continuous operation without crashes
- [ ] Zero unauthorized trades
- [ ] 100% of stop-losses trigger correctly

---

## TIMELINE SUMMARY

| Week | Phases | Focus | Risk Level |
|------|--------|-------|------------|
| 1 | ✅ Phase 1-2 | Enhanced Paper + Schema | Low ✅ |
| 2 | Phase 3-4 | Hyperliquid Auth + Orders | Medium ⚠️ |
| 3 | Phase 5-6 | Account Sync + Risk Mgmt | Medium ⚠️ |
| 4 | Phase 7-8 | WebSocket + Frontend | Medium ⚠️ |
| 5-6 | Phase 9 | Testnet Testing | High 🚨 |
| 6-7 | Phase 10 | Production Prep | High 🚨 |

**Total Duration**: 5-7 weeks (balanced approach)
**Buffer**: +1 week for unexpected issues

---

## DECISION POINTS

### After Phase 1 (Current)
- **Test First**: Validate paper trading works correctly
- **Document**: Create user guide for paper trading features
- **Proceed**: Start Phase 2 if tests pass

### After Phase 4
- **Testnet Validation**: Ensure orders work on Hyperliquid testnet
- **Risk Assessment**: Review security measures before Phase 5

### After Phase 9
- **Go/No-Go Decision**: Proceed to mainnet or iterate on testnet
- **Legal Review**: Ensure compliance with regulations
- **Insurance Check**: Review liability coverage

---

## MAINTENANCE PLAN

### Daily Operations
- Monitor system logs for errors
- Check WebSocket connection status
- Review failed order reasons
- Track daily P&L for live accounts

### Weekly Operations
- Review risk limit triggers
- Analyze slippage statistics
- Database backup verification
- Performance metric review

### Monthly Operations
- Security audit
- Dependency updates
- Load testing
- Disaster recovery drill
