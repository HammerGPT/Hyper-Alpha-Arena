# Hyperliquid Integration - Database Upgrade Guide

## Overview

This guide walks through the database upgrade process for integrating Hyperliquid perpetual contract trading into Hyper Alpha Arena.

## Prerequisites

- Python 3.11+ with virtual environment activated
- Existing Hyper Alpha Arena installation
- Backup of important data (Trader API keys)

## Upgrade Steps

### Step 1: Activate Virtual Environment

```bash
cd /home/wwwroot/open-alpha-arena/backend
source .venv/bin/activate
```

### Step 2: Install New Dependencies

```bash
pip install cryptography eth-account
```

Verify installation:
```bash
python -c "from cryptography.fernet import Fernet; print('cryptography OK')"
python -c "from eth_account import Account; print('eth-account OK')"
```

### Step 3: Verify Encryption Key

Check that `.env` file exists with encryption key:
```bash
cat .env | grep HYPERLIQUID_ENCRYPTION_KEY
```

Expected output:
```
HYPERLIQUID_ENCRYPTION_KEY=_Vb-0WhmCmh2_NPbbZfSUk8ZGnWK3oBfcbGt0HeYHG0=
```

### Step 4: Run Database Upgrade Script

```bash
python database/upgrade_for_hyperliquid.py
```

**What this script does:**
1. Exports existing Trader configurations (API keys, models, base URLs)
2. Backs up old database to `trading.db.backup.YYYYMMDD_HHMMSS`
3. Creates fresh database with all Hyperliquid tables and fields
4. Restores Trader configurations
5. Initializes default trading configs

**Expected output:**
```
======================================================================
Hyper Alpha Arena - Database Upgrade for Hyperliquid
======================================================================

Step 1: Exporting trader configurations...
Exported 2 trader configurations

Step 2: Backing up database...
✓ Database backed up to: trading.db.backup.20251103_120000

Step 3: Creating fresh database with Hyperliquid support...
✓ Created fresh database with Hyperliquid support

Step 4: Restoring trader configurations...
✓ Restored 2 trader configurations
✓ Initialized trading configurations

Step 5: Verifying new database...
  ✓ users
  ✓ accounts
  ✓ orders
  ✓ positions
  ✓ hyperliquid_account_snapshots
  ✓ hyperliquid_positions

  Hyperliquid fields in accounts table:
    ✓ hyperliquid_enabled
    ✓ hyperliquid_environment
    ✓ hyperliquid_testnet_private_key
    ✓ hyperliquid_mainnet_private_key
    ✓ max_leverage
    ✓ default_leverage

======================================================================
✓ Database upgrade completed successfully!
======================================================================

Backup location: trading.db.backup.20251103_120000
Restored 2 trader configurations

Next steps:
1. Generate encryption key: python utils/encryption.py
2. Add to .env: HYPERLIQUID_ENCRYPTION_KEY=<key>
3. Configure Hyperliquid accounts via API
```

### Step 5: Verify Database Structure

```bash
sqlite3 trading.db ".schema accounts" | grep hyperliquid
```

Expected output:
```
hyperliquid_enabled VARCHAR(10) DEFAULT 'false',
hyperliquid_environment VARCHAR(20),
hyperliquid_testnet_private_key VARCHAR(500),
hyperliquid_mainnet_private_key VARCHAR(500),
max_leverage INTEGER DEFAULT 3,
default_leverage INTEGER DEFAULT 1,
```

### Step 6: Restart Backend Service

If running as systemd service:
```bash
systemctl restart open-alpha-arena-backend
```

Or if running manually:
```bash
# Stop existing process
pkill -f "python main.py"

# Start new process
python main.py
```

Or using uvicorn directly:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 7: Verify API Health

Test Hyperliquid API health:
```bash
curl http://localhost:8000/api/hyperliquid/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "hyperliquid",
  "encryption_configured": true,
  "endpoints": {
    "setup": "/api/hyperliquid/accounts/{id}/setup",
    "balance": "/api/hyperliquid/accounts/{id}/balance",
    "positions": "/api/hyperliquid/accounts/{id}/positions",
    "test": "/api/hyperliquid/accounts/{id}/test-connection"
  }
}
```

## Post-Upgrade Configuration

### Configure Hyperliquid for an Account

**1. Get Account ID**
```bash
curl http://localhost:8000/api/accounts
```

**2. Setup Hyperliquid (Testnet)**
```bash
curl -X POST http://localhost:8000/api/hyperliquid/accounts/1/setup \
  -H "Content-Type: application/json" \
  -d '{
    "environment": "testnet",
    "private_key": "0x1234567890abcdef...",
    "max_leverage": 5,
    "default_leverage": 2
  }'
```

**3. Test Connection**
```bash
curl http://localhost:8000/api/hyperliquid/accounts/1/test-connection
```

**4. Check Balance**
```bash
curl http://localhost:8000/api/hyperliquid/accounts/1/balance
```

**5. Enable Auto Trading**

Ensure account has `auto_trading_enabled` set to `"true"` in the database or via API.

## Verification Checklist

- [ ] Virtual environment activated
- [ ] New dependencies installed (cryptography, eth-account)
- [ ] Encryption key exists in `.env`
- [ ] Database upgrade script executed successfully
- [ ] Database backup created
- [ ] New tables exist (hyperliquid_account_snapshots, hyperliquid_positions)
- [ ] New fields exist in accounts table
- [ ] Backend service restarted
- [ ] Hyperliquid API health check passes
- [ ] Test connection to Hyperliquid testnet successful

## Rollback Procedure (If Needed)

If upgrade fails or needs to be reverted:

```bash
cd /home/wwwroot/open-alpha-arena/backend

# Stop backend service
systemctl stop open-alpha-arena-backend

# Restore old database
mv trading.db trading.db.failed
mv trading.db.backup.YYYYMMDD_HHMMSS trading.db

# Restart service with old database
systemctl start open-alpha-arena-backend
```

## Troubleshooting

### Issue: Encryption key not found

**Symptom:**
```
KeyError: 'HYPERLIQUID_ENCRYPTION_KEY'
```

**Solution:**
```bash
python utils/encryption.py
# Copy the generated key to .env file
echo "HYPERLIQUID_ENCRYPTION_KEY=<generated-key>" >> .env
```

### Issue: Module not found (cryptography or eth-account)

**Symptom:**
```
ModuleNotFoundError: No module named 'cryptography'
```

**Solution:**
```bash
source .venv/bin/activate
pip install cryptography eth-account
```

### Issue: Database upgrade script fails

**Symptom:**
```
ERROR: Failed to export trader configurations
```

**Solution:**
- Check that database file exists: `ls -la trading.db`
- Ensure write permissions: `chmod 644 trading.db`
- Check disk space: `df -h`

### Issue: CCXT cannot connect to Hyperliquid

**Symptom:**
```
Failed to initialize Hyperliquid exchange
```

**Solution:**
- Verify private key format (must start with 0x)
- Check network connectivity to Hyperliquid API
- Test with curl:
  ```bash
  curl https://api.hyperliquid-testnet.xyz/info
  ```

## Next Steps

After successful upgrade:

1. **Configure Hyperliquid Accounts**: Set up testnet accounts via API
2. **Test Trading**: Place manual test orders to verify functionality
3. **Enable Auto Trading**: Turn on auto trading for Hyperliquid accounts
4. **Monitor Logs**: Watch logs for any Hyperliquid-related errors
5. **Frontend Development**: Add UI for Hyperliquid configuration

## Support

If you encounter issues not covered in this guide:

1. Check logs: `tail -f /var/log/open-alpha-arena/backend.log`
2. Review database structure: `sqlite3 trading.db .schema`
3. Verify API endpoints: Check all routes return expected responses

## Files Modified

- `backend/database/models.py` - Added Hyperliquid fields and tables
- `backend/services/hyperliquid_trading_client.py` - New trading client
- `backend/services/hyperliquid_environment.py` - Environment management
- `backend/utils/encryption.py` - Encryption utilities
- `backend/api/hyperliquid_routes.py` - API endpoints
- `backend/services/trading_commands.py` - AI-driven trading execution
- `backend/config/prompt_templates.py` - AI prompt templates
- `backend/services/ai_decision_service.py` - AI context building
- `backend/services/scheduler.py` - Scheduled trading tasks
- `backend/services/startup.py` - Service initialization
- `backend/.env` - Environment configuration
- `backend/pyproject.toml` - Dependencies

## Security Notes

- **Private keys are encrypted** using Fernet symmetric encryption
- **Encryption key must be kept secure** - if lost, private keys cannot be decrypted
- **Testnet environment recommended** for initial testing
- **Environment validation** prevents accidental mainnet operations
- **Backup database** before any configuration changes

---

**Version:** 1.0
**Date:** 2025-11-03
**Author:** Hyper Alpha Arena Development Team
