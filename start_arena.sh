#!/bin/bash
# Alpha Arena Startup Script with Auto-Install and Frontend Build

# Check for stop parameter
if [ "$1" = "stop" ]; then
    echo "=== Stopping Alpha Arena ==="

    # Only kill by port 8802 (most precise)
    if command -v lsof &> /dev/null; then
        PID=$(lsof -t -i:8802 2>/dev/null)
        if [ ! -z "$PID" ]; then
            kill $PID
            echo "Service stopped successfully (PID: $PID)"
            # Clean up PID file if exists
            [ -f "arena.pid" ] && rm arena.pid
        else
            echo "No service running on port 8802"
            # Clean up stale PID file
            [ -f "arena.pid" ] && rm arena.pid
        fi
    else
        echo "lsof not available, cannot stop service"
    fi


    exit 0
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo "=== Alpha Arena Startup Script ==="
echo "Project directory: $SCRIPT_DIR"
echo "Backend directory: $BACKEND_DIR"
echo "Frontend directory: $FRONTEND_DIR"

# Check if directories exist
if [ ! -d "$BACKEND_DIR" ]; then
    echo "ERROR: Backend directory not found at $BACKEND_DIR"
    exit 1
fi

if [ ! -d "$FRONTEND_DIR" ]; then
    echo "ERROR: Frontend directory not found at $FRONTEND_DIR"
    exit 1
fi

# Function to check and install pnpm
install_pnpm() {
    if ! command -v pnpm &> /dev/null; then
        echo "Installing pnpm..."
        if command -v npm &> /dev/null; then
            npm install -g pnpm
        else
            echo "Installing pnpm via official installer..."
            curl -fsSL https://get.pnpm.io/install.sh | sh -
            export PATH="$HOME/.local/share/pnpm:$PATH"
        fi

        if ! command -v pnpm &> /dev/null; then
            echo "ERROR: Failed to install pnpm"
            exit 1
        fi
        echo "pnpm installed successfully"
    else
        echo "pnpm already installed"
    fi
}

# Function to build frontend
build_frontend() {
    echo "Building frontend..."
    cd "$FRONTEND_DIR"

    # Always install/update frontend dependencies
    echo "Installing frontend dependencies..."
    pnpm install

    # Build frontend
    pnpm build
    if [ $? -ne 0 ]; then
        echo "ERROR: Frontend build failed"
        exit 1
    fi

    # Copy to backend static directory
    echo "Copying frontend build to backend/static..."
    mkdir -p "$BACKEND_DIR/static"
    rm -rf "$BACKEND_DIR/static"/*
    cp -r dist/* "$BACKEND_DIR/static/"

    echo "Frontend built and deployed successfully"
    cd "$BACKEND_DIR"
}

# Install pnpm if needed
install_pnpm

# Build frontend
build_frontend

echo "=== Alpha Arena Startup Script ==="
echo "Starting backend service on port 8802..."

# Check if port 8802 is already in use
if command -v lsof &> /dev/null; then
    PID=$(lsof -t -i:8802 2>/dev/null)
    if [ ! -z "$PID" ]; then
        echo "Port 8802 is already in use by process $PID"
        echo "Please stop the existing service first: ./start_arena.sh stop"
        exit 1
    fi
fi

# Check if virtual environment exists, create if not
if [ ! -f ".venv/bin/python" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment"
        exit 1
    fi

    echo "Installing Python dependencies..."
    .venv/bin/pip install -e .
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install Python dependencies"
        exit 1
    fi
    echo "Python environment setup completed"
fi

# Check if uvicorn is available in virtual environment
if ! .venv/bin/python -c "import uvicorn" 2>/dev/null; then
    echo "ERROR: uvicorn not found in virtual environment."
    echo "Installing required dependencies..."
    .venv/bin/pip install -e .
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install dependencies."
        exit 1
    fi
fi

# Load environment variables from .env file
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Initialize PostgreSQL databases
echo "Initializing PostgreSQL databases..."
if command -v systemctl &> /dev/null; then
    # Check if PostgreSQL is installed and running (Linux with systemd)
    if systemctl list-units --type=service --all | grep -q postgresql; then
        if ! systemctl is-active --quiet postgresql; then
            echo "Starting PostgreSQL service..."
            sudo systemctl start postgresql
        fi
    elif ! command -v psql &> /dev/null; then
        echo "WARNING: PostgreSQL not found. Installing..."
        if command -v apt-get &> /dev/null; then
            # Debian/Ubuntu
            sudo apt-get update && sudo apt-get install -y postgresql postgresql-contrib
        elif command -v yum &> /dev/null; then
            # CentOS/RHEL
            sudo yum install -y postgresql-server postgresql-contrib
            sudo postgresql-setup initdb
        fi
        sudo systemctl enable postgresql
        sudo systemctl start postgresql
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    if ! command -v psql &> /dev/null; then
        if command -v brew &> /dev/null; then
            echo "WARNING: PostgreSQL not found. Installing via Homebrew..."
            brew install postgresql@14
            brew services start postgresql@14
        else
            echo "ERROR: Homebrew not found. Please install PostgreSQL manually:"
            echo "   Visit: https://postgresapp.com/ or run: brew install postgresql"
            exit 1
        fi
    else
        # Ensure PostgreSQL is running on macOS
        if ! pgrep -x postgres > /dev/null; then
            if command -v brew &> /dev/null; then
                brew services start postgresql@14 || brew services start postgresql
            else
                pg_ctl -D /usr/local/var/postgres start
            fi
        fi
    fi
fi

# Run database initialization script
echo "Setting up PostgreSQL databases and tables..."
.venv/bin/python database/init_postgresql.py
if [ $? -ne 0 ]; then
    echo "WARNING: Database initialization encountered issues, but will continue..."
    echo "   The application will attempt to create tables on first run."
fi

# Start service in background
nohup .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8802 > ../arena.log 2>&1 &
echo $! > ../arena.pid

# Wait for service to start with retry logic
echo "Waiting for service to start..."
for i in {1..60}; do
    if curl -s http://127.0.0.1:8802/api/health > /dev/null 2>&1; then
        break
    fi
    echo -n "."
    sleep 2
done
echo ""

# Check if service is running
if curl -s http://127.0.0.1:8802/api/health > /dev/null 2>&1; then
    echo "Service started successfully!"
    echo "   - Backend API: http://localhost:8802"
    echo "   - Health Check: http://localhost:8802/api/health"
    echo "   - System Logs API: http://localhost:8802/api/system-logs"
    echo ""
    echo "System Log Features:"
    echo "   - View logs: GET /api/system-logs"
    echo "   - Get stats: GET /api/system-logs/stats"
    echo "   - Clear logs: DELETE /api/system-logs"
    echo ""
    echo "View live logs: tail -f arena.log"
    echo "Stop service: ./start_arena.sh stop"
else
    echo "ERROR: Service failed to start. Check logs:"
    echo "   tail -f arena.log"
fi

echo ""
echo "Database changes applied:"
echo "  - Added prompt_snapshot column to ai_decision_logs"
echo "  - Added reasoning_snapshot column to ai_decision_logs"
echo "  - Added decision_snapshot column to ai_decision_logs"
