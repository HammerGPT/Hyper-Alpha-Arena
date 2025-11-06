# Alpha Arena Windows PowerShell Startup Script
param(
    [string]$Action = "start"
)

# Set error action preference
$ErrorActionPreference = "Stop"

# Check for stop parameter
if ($Action -eq "stop") {
    Write-Host "=== Stopping Alpha Arena ===" -ForegroundColor Yellow

    # Kill by port (more precise)
    $processes = Get-NetTCPConnection -LocalPort 8802 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
    if ($processes) {
        foreach ($processId in $processes) {
            Write-Host "Stopping service on port 8802 (PID: $processId)..." -ForegroundColor Yellow
            try {
                Stop-Process -Id $processId -Force
                Write-Host "Service stopped successfully" -ForegroundColor Green
            }
            catch {
                Write-Host "Failed to stop process $processId" -ForegroundColor Red
            }
        }
    }
    else {
        Write-Host "No processes found on port 8802" -ForegroundColor Green
    }

    exit 0
}

Write-Host "=== Alpha Arena Windows PowerShell Startup Script ===" -ForegroundColor Cyan

# Get the directory where this script is located
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$BACKEND_DIR = Join-Path $SCRIPT_DIR "backend"
$FRONTEND_DIR = Join-Path $SCRIPT_DIR "frontend"

Write-Host "Project directory: $SCRIPT_DIR" -ForegroundColor Gray
Write-Host "Backend directory: $BACKEND_DIR" -ForegroundColor Gray
Write-Host "Frontend directory: $FRONTEND_DIR" -ForegroundColor Gray

# Check if directories exist
if (-not (Test-Path $BACKEND_DIR)) {
    Write-Host "ERROR: Backend directory not found at $BACKEND_DIR" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

if (-not (Test-Path $FRONTEND_DIR)) {
    Write-Host "ERROR: Frontend directory not found at $FRONTEND_DIR" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Function to check and install pnpm
function Install-Pnpm {
    try {
        $null = Get-Command pnpm -ErrorAction Stop
        Write-Host "pnpm already installed" -ForegroundColor Green
    }
    catch {
        Write-Host "Installing pnpm..." -ForegroundColor Yellow
        try {
            $null = Get-Command npm -ErrorAction Stop
            npm install -g pnpm
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to install pnpm"
            }
            Write-Host "pnpm installed successfully" -ForegroundColor Green
        }
        catch {
            Write-Host "ERROR: npm not found. Please install Node.js first." -ForegroundColor Red
            Read-Host "Press Enter to exit"
            exit 1
        }
    }
}

# Function to build frontend
function Build-Frontend {
    Write-Host "Building frontend..." -ForegroundColor Yellow
    Set-Location $FRONTEND_DIR

    # Always install/update frontend dependencies
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    pnpm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to install frontend dependencies" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }

    # Build frontend
    pnpm build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Frontend build failed" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }

    # Copy to backend static directory
    Write-Host "Copying frontend build to backend/static..." -ForegroundColor Yellow
    $staticDir = Join-Path $BACKEND_DIR "static"
    if (Test-Path $staticDir) {
        Remove-Item $staticDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $staticDir -Force | Out-Null
    Copy-Item -Path "dist\*" -Destination $staticDir -Recurse -Force

    Write-Host "Frontend built and deployed successfully" -ForegroundColor Green

    # Return to script directory
    Set-Location $SCRIPT_DIR
}

# Install pnpm and build frontend
Install-Pnpm
Build-Frontend

# Change to backend directory
Set-Location $BACKEND_DIR

Write-Host "Starting backend service on port 8802..." -ForegroundColor Yellow

# Check if virtual environment exists, create if not
$venvPython = Join-Path $BACKEND_DIR ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create virtual environment" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }

    Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
    & ".venv\Scripts\pip.exe" install -e .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to install Python dependencies" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "Python environment setup completed" -ForegroundColor Green
}

# Check if uvicorn is available in virtual environment
try {
    & $venvPython -c "import uvicorn" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "uvicorn not found"
    }
}
catch {
    Write-Host "ERROR: uvicorn not found in virtual environment." -ForegroundColor Red
    Write-Host "Installing required dependencies..." -ForegroundColor Yellow
    & ".venv\Scripts\pip.exe" install -e .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to install dependencies." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Initialize PostgreSQL databases
Write-Host "Initializing PostgreSQL databases..." -ForegroundColor Yellow

# Check if PostgreSQL is installed
$pgInstalled = $false
try {
    $null = Get-Command psql -ErrorAction Stop
    $pgInstalled = $true
}
catch {
    Write-Host "⚠️  PostgreSQL not found on system PATH." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Please install PostgreSQL:" -ForegroundColor Yellow
    Write-Host "  1. Download from: https://www.postgresql.org/download/windows/" -ForegroundColor Cyan
    Write-Host "  2. Or use: winget install PostgreSQL.PostgreSQL" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "After installation, restart this script." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to continue anyway (database may not work)"
}

if ($pgInstalled) {
    # Check if PostgreSQL service is running
    $pgService = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue
    if ($pgService) {
        if ($pgService.Status -ne "Running") {
            Write-Host "Starting PostgreSQL service..." -ForegroundColor Yellow
            Start-Service $pgService.Name
        }
    }

    # Run database initialization script
    Write-Host "Setting up PostgreSQL databases and tables..." -ForegroundColor Yellow
    & $venvPython "database\init_postgresql.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠️  Database initialization encountered issues, but will continue..." -ForegroundColor Yellow
        Write-Host "   The application will attempt to create tables on first run." -ForegroundColor Gray
    }
}

# Kill any existing process on port 8802
Write-Host "Checking for existing processes on port 8802..." -ForegroundColor Yellow
$processes = Get-NetTCPConnection -LocalPort 8802 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
if ($processes) {
    foreach ($processId in $processes) {
        Write-Host "Killing process $processId on port 8802..." -ForegroundColor Yellow
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

# Start the backend service in a new window
Write-Host "Starting backend service..." -ForegroundColor Yellow
$processArgs = @{
    FilePath = $venvPython
    ArgumentList = @("-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8802")
    WindowStyle = "Normal"
    PassThru = $true
}
$backendProcess = Start-Process @processArgs

# Wait for service to start with retry logic
Write-Host "Waiting for service to start..." -ForegroundColor Yellow
$retryCount = 0
$maxRetries = 60

do {
    $retryCount++
    Write-Host "Checking service health (attempt $retryCount/$maxRetries)..." -ForegroundColor Gray

    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8802/api/health" -TimeoutSec 5 -ErrorAction Stop
        Write-Host "Service health check passed!" -ForegroundColor Green
        break
    }
    catch {
        if ($retryCount -ge $maxRetries) {
            Write-Host "Health check failed after $maxRetries attempts." -ForegroundColor Red
            Write-Host ""
            Write-Host "Service failed to start or health check failed." -ForegroundColor Red
            Write-Host ""
            Write-Host "Troubleshooting steps:" -ForegroundColor Yellow
            Write-Host "1. Check if the backend window opened and shows any errors"
            Write-Host "2. Try running manually: cd backend && .venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8802"
            Write-Host "3. Check if port 8802 is already in use: Get-NetTCPConnection -LocalPort 8802"
            Write-Host "4. Check if Python virtual environment is working: .venv\Scripts\python --version"
            Write-Host ""
            Read-Host "Press Enter to exit"
            exit 1
        }

        Write-Host "." -NoNewline
        Start-Sleep -Seconds 2
    }
} while ($retryCount -lt $maxRetries)

Write-Host ""
Write-Host "Service started successfully!" -ForegroundColor Green
Write-Host "    - Backend API: http://localhost:8802" -ForegroundColor Cyan
Write-Host "    - Health Check: http://localhost:8802/api/health" -ForegroundColor Cyan
Write-Host "    - System Logs API: http://localhost:8802/api/system-logs" -ForegroundColor Cyan
Write-Host ""
Write-Host "System Log Features:" -ForegroundColor Yellow
Write-Host "    - View logs: GET /api/system-logs"
Write-Host "    - Get stats: GET /api/system-logs/stats"
Write-Host "    - Clear logs: DELETE /api/system-logs"
Write-Host ""
Write-Host "Open http://localhost:8802 in your browser to access the application" -ForegroundColor Green
Write-Host ""
Write-Host "To stop the service: .\start_arena.ps1 stop (run from project root)" -ForegroundColor Yellow
Write-Host ""

# Open browser automatically
Write-Host "Opening browser..." -ForegroundColor Yellow
Start-Process "http://localhost:8802"

Write-Host "Press any key to exit this window..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")