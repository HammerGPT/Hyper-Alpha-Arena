#!/bin/bash
# Alpha Arena Startup Script with System Logging

cd /home/Hyper-Alpha-Arena/backend

echo "=== Alpha Arena Startup Script ==="
echo "Starting backend service on port 8802..."

# Check if screen session exists
if screen -list | grep -q "alpha-arena"; then
    echo "Stopping existing alpha-arena session..."
    screen -S alpha-arena -X quit
    sleep 2
fi

# Start new screen session with virtual environment
screen -dmS alpha-arena bash -c "cd /home/wwwroot/open-alpha-arena/backend && .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8802"

# Wait for service to start
echo "Waiting for service to start..."
sleep 5

# Check if service is running
if curl -s http://127.0.0.1:8802/api/health > /dev/null 2>&1; then
    echo "✅ Service started successfully!"
    echo "   - Backend API: http://localhost:8802"
    echo "   - Health Check: http://localhost:8802/api/health"
    echo "   - System Logs API: http://localhost:8802/api/system-logs"
    echo ""
    echo "📊 System Log Features:"
    echo "   - View logs: GET /api/system-logs"
    echo "   - Get stats: GET /api/system-logs/stats"
    echo "   - Clear logs: DELETE /api/system-logs"
    echo ""
    echo "🔍 View live logs: screen -r alpha-arena"
    echo "⏹️  Stop service: screen -S alpha-arena -X quit"
else
    echo "❌ Service failed to start. Check logs:"
    echo "   screen -r alpha-arena"
fi

echo ""
echo "Database changes applied:"
echo "✅ Added prompt_snapshot column to ai_decision_logs"
echo "✅ Added reasoning_snapshot column to ai_decision_logs"
echo "✅ Added decision_snapshot column to ai_decision_logs"
