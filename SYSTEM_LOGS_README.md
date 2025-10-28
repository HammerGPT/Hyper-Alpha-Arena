# System Logs Feature

## Overview

The new system logs feature provides real-time monitoring and debugging capabilities, allowing you to view:
1. **AI Decision Logs** - Decision process and results of each AI Trader
2. **System Error Logs** - API call failures, parsing errors, etc.
3. **Price Update Logs** - Market data changes (optional)

## Completed Changes

### 1. Database Changes

Added three snapshot fields to the `ai_decision_logs` table:

```sql
ALTER TABLE ai_decision_logs ADD COLUMN prompt_snapshot TEXT;
ALTER TABLE ai_decision_logs ADD COLUMN reasoning_snapshot TEXT;
ALTER TABLE ai_decision_logs ADD COLUMN decision_snapshot TEXT;
```

**Purpose:**
- `prompt_snapshot`: Stores the complete prompt sent to AI (including portfolio, market prices, news)
- `reasoning_snapshot`: Stores AI's reasoning process (Claude's thinking process)
- `decision_snapshot`: Stores structured decision JSON

### 2. Backend New Features

#### New Files:

**`backend/services/system_logger.py`**
- `SystemLogCollector` class: Stores recent 500 logs in memory
- Automatic log categorization: `price_update`, `ai_decision`, `system_error`
- Log levels: `INFO`, `WARNING`, `ERROR`
- Supports real-time WebSocket push (to be implemented)

**`backend/api/system_log_routes.py`**
- `GET /api/system-logs/` - Get log list (with filtering support)
- `GET /api/system-logs/stats` - Get log statistics
- `GET /api/system-logs/categories` - Get available categories and levels
- `DELETE /api/system-logs/` - Clear all logs

#### Modified Files:

**`backend/main.py`**
- Import and register `system_log_router`
- Initialize `setup_system_logger()` on startup

**`backend/services/ai_decision_service.py`**
- Log errors on API call failures
- Log AI decisions when saving decisions
- Integrate `system_logger` calls

**Key Logging Points:**
```python
# API endpoint build failed
system_logger.log_error("API_ENDPOINT_BUILD_FAILED", ...)

# All API endpoints failed
system_logger.log_error("AI_API_ALL_ENDPOINTS_FAILED", ...)

# AI decision logging
system_logger.log_ai_decision(
    account_name=account.name,
    model=account.model,
    operation=operation,
    symbol=symbol,
    reason=reason,
    success=executed
)
```

### 3. Frontend New Features

#### New Files:

**`frontend/app/components/layout/SystemLogs.tsx`**
- System logs viewing page
- Real-time statistics cards (total logs, errors, warnings, AI decisions)
- Log filters (by category, by level)
- Auto-refresh (every 3 seconds)
- Expandable log details

#### Modified Files:

**`frontend/app/components/layout/Sidebar.tsx`**
- Added FileText icon import
- Added "System Logs" button above Settings button
- Desktop and mobile support

**`frontend/app/main.tsx`**
- Import `SystemLogs` component
- Add `system-logs` page route
- Update `PAGE_TITLES` mapping

## Usage

### Starting the Service

```bash
# Method 1: Using startup script (recommended)
cd /home/wwwroot/open-alpha-arena
./start_arena.sh

# Method 2: Manual start (using project virtual environment)
cd /home/wwwroot/open-alpha-arena/backend
screen -dmS alpha-arena bash -c "cd /home/wwwroot/open-alpha-arena/backend && .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8802"

# Method 3: Foreground run (for debugging)
cd /home/wwwroot/open-alpha-arena/backend
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8802
```

**⚠️ Important Notes:**
- Must use project's virtual environment `.venv/bin/python`
- Do not use system Python or other virtual environments
- Startup script automatically configures correct Python path

### Accessing System Logs

1. **Frontend UI:**
   - Open http://localhost:8802 (or your domain)
   - Click the **📄 document icon** (FileText) in the left sidebar (above Settings button)
   - Enter the system logs page

   **⚠️ Note:** If you don't see the log button, rebuild the frontend:
   ```bash
   cd /home/wwwroot/open-alpha-arena/frontend
   npm run build
   rm -rf /home/wwwroot/open-alpha-arena/backend/static/*
   cp -r dist/* /home/wwwroot/open-alpha-arena/backend/static/
   cd /home/wwwroot/open-alpha-arena
   ./start_arena.sh
   ```

2. **Direct API Access:**
   ```bash
   # Get all logs
   curl http://localhost:8802/api/system-logs/

   # Get AI decision logs
   curl "http://localhost:8802/api/system-logs/?category=ai_decision"

   # Get error logs
   curl "http://localhost:8802/api/system-logs/?level=ERROR"

   # Get statistics
   curl http://localhost:8802/api/system-logs/stats

   # Clear logs
   curl -X DELETE http://localhost:8802/api/system-logs/
   ```

### Viewing Claude Trader Decisions

1. Ensure Claude account has a valid API Key configured
2. Open system logs page
3. Select filter: "AI Decisions"
4. View Claude's decision records:
   - If you see decision logs → API call successful
   - If you see error logs → Check error details
   - If nothing appears → Check account configuration and trigger conditions

## Log Examples

### AI Decision Log
```json
{
  "timestamp": "2025-10-28T16:30:45.123Z",
  "level": "INFO",
  "category": "ai_decision",
  "message": "[Claude] BUY BTC: Bullish trend detected...",
  "details": {
    "account": "Claude",
    "model": "claude-sonnet-4.5",
    "operation": "buy",
    "symbol": "BTC",
    "reason": "Bullish trend detected with strong institutional support",
    "success": true
  }
}
```

### API Error Log
```json
{
  "timestamp": "2025-10-28T16:31:10.456Z",
  "level": "ERROR",
  "category": "system_error",
  "message": "[AI_API_ALL_ENDPOINTS_FAILED] All API endpoints failed for Claude",
  "details": {
    "account": "Claude",
    "model": "claude-sonnet-4.5",
    "endpoints_tried": ["http://free.lvis.lol/v1/chat/completions"],
    "max_retries": 3
  }
}
```

## Troubleshooting

### Claude Has No Decision Records

**1. Check if API Key is valid:**
```sql
SELECT id, name, model, base_url, LENGTH(api_key) as key_len
FROM accounts WHERE id = 4;
```

**2. View errors in system logs:**
- Open system logs page
- Filter by "System Errors" category
- Check if there are API call failure records

**3. Manually test the API:**
```bash
curl -X POST http://free.lvis.lol/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 100
  }'
```

**4. Check trigger strategy:**
```sql
SELECT * FROM account_strategy_configs WHERE account_id = 4;
```

### Incomplete Log Records

**Check if log collector is initialized:**
```bash
# View startup logs
screen -r alpha-arena

# Should see:
# INFO: System log collector initialized
```

### Frontend Cannot Access Logs

**Check if API routes are registered:**
```bash
curl http://localhost:8802/api/system-logs/stats

# Should return:
# {"total_logs": 0, "by_level": {...}, "by_category": {...}}
```

## Future Enhancements

### Features to Implement:
- [ ] WebSocket real-time log push
- [ ] Log export functionality (CSV/JSON)
- [ ] Log search and advanced filtering
- [ ] Price change threshold logging (only record significant fluctuations)
- [ ] Email/WeChat alert integration
- [ ] Performance metrics recording (API latency, token consumption)

### Suggested Enhancements:
```python
# backend/database/models.py
class AIDecisionLog:
    # New fields
    api_latency_ms = Column(Integer)        # API call latency
    parsing_errors = Column(Integer)        # Parsing retry count
    endpoint_used = Column(String(500))     # Successful API endpoint
    token_usage = Column(Integer)           # Token consumption
    error_message = Column(Text)            # Error message
```

## Technical Details

### Log Flow

```
AI Trader Triggered
    ↓
call_ai_for_decision()
    ↓
API Call
    ├─ Success → Parse decision → save_ai_decision() → system_logger.log_ai_decision()
    └─ Failure → system_logger.log_error()
         ↓
    Frontend real-time query ← Logs in memory (recent 500 entries)
```

### Performance Considerations

- Logs stored in memory (max 500 entries)
- No impact on database performance
- Thread locks ensure concurrency safety
- Auto-refresh interval 3 seconds (adjustable)

### Security Considerations

- API Keys will not appear in logs
- Sensitive information needs to be manually added to details
- Recommended to set log access permissions in production environment

## Summary

✅ **Completed:**
1. Database snapshot fields added
2. Backend log collection system
3. System logs REST API
4. Frontend log viewing interface
5. AI decision log integration
6. Error log integration

🔧 **Usage Workflow:**
1. Run `./start_arena.sh` to start the service
2. Access frontend, click the "document" icon to view logs
3. Filter AI decision logs to observe Claude's decisions
4. View system error logs to troubleshoot issues

📊 **Monitoring Focus:**
- Error log count (should be 0 or very few)
- AI decision logs (at least 1 per 5 minutes)
- API latency (future feature)

---

*Created: 2025-10-28*
*Author: Claude Code Assistant*
