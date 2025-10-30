@echo off
REM Alpha Arena Windows Startup Script with Auto-Install and Frontend Build

REM Check for stop parameter
if "%1"=="stop" (
    echo === Stopping Alpha Arena ===

    REM Kill by port (more precise)
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8802') do (
        echo Stopping service on port 8802 (PID: %%a)...
        taskkill /f /pid %%a >nul 2>&1
        if not errorlevel 1 (
            echo Service stopped successfully
        )
    )

    exit /b 0
)

echo === Alpha Arena Windows Startup Script ===

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0
set BACKEND_DIR=%SCRIPT_DIR%backend
set FRONTEND_DIR=%SCRIPT_DIR%frontend

echo Project directory: %SCRIPT_DIR%
echo Backend directory: %BACKEND_DIR%
echo Frontend directory: %FRONTEND_DIR%

REM Check if directories exist
if not exist "%BACKEND_DIR%" (
    echo ERROR: Backend directory not found at %BACKEND_DIR%
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%" (
    echo ERROR: Frontend directory not found at %FRONTEND_DIR%
    pause
    exit /b 1
)

REM Function to check and install pnpm
:install_pnpm
where pnpm >nul 2>&1
if errorlevel 1 (
    echo Installing pnpm...
    where npm >nul 2>&1
    if not errorlevel 1 (
        npm install -g pnpm
    ) else (
        echo ERROR: npm not found. Please install Node.js first.
        pause
        exit /b 1
    )

    where pnpm >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Failed to install pnpm
        pause
        exit /b 1
    )
    echo pnpm installed successfully
) else (
    echo pnpm already installed
)

REM Function to build frontend
:build_frontend
echo Building frontend...
cd /d "%FRONTEND_DIR%"

REM Always install/update frontend dependencies
echo Installing frontend dependencies...
pnpm install
if errorlevel 1 (
    echo ERROR: Failed to install frontend dependencies
    pause
    exit /b 1
)

REM Build frontend
pnpm build
if errorlevel 1 (
    echo ERROR: Frontend build failed
    pause
    exit /b 1
)

REM Copy to backend static directory
echo Copying frontend build to backend/static...
if exist "%BACKEND_DIR%\static" rmdir /s /q "%BACKEND_DIR%\static"
mkdir "%BACKEND_DIR%\static"
xcopy /e /i /y "dist\*" "%BACKEND_DIR%\static\"

echo Frontend built and deployed successfully

REM Change to backend directory
cd /d "%BACKEND_DIR%"

REM Call install_pnpm and build_frontend
call :install_pnpm
call :build_frontend

echo Starting backend service on port 8802...

REM Check if virtual environment exists, create if not
if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )

    echo Installing Python dependencies...
    ".venv\Scripts\pip.exe" install -e .
    if errorlevel 1 (
        echo ERROR: Failed to install Python dependencies
        pause
        exit /b 1
    )
    echo Python environment setup completed
)

REM Check if uvicorn is available in virtual environment
".venv\Scripts\python.exe" -c "import uvicorn" 2>nul
if errorlevel 1 (
    echo ERROR: uvicorn not found in virtual environment.
    echo Installing required dependencies...
    ".venv\Scripts\pip.exe" install -e .
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies.
        pause
        exit /b 1
    )
)

REM Kill any existing process on port 8802
echo Checking for existing processes on port 8802...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8802') do (
    echo Killing process %%a on port 8802...
    taskkill /f /pid %%a >nul 2>&1
)

REM Start the backend service in a new window
echo Starting backend service...
start "Alpha Arena Backend" "%BACKEND_DIR%\.venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8802

REM Wait for service to start
echo Waiting for service to start...
timeout /t 8 /nobreak >nul

REM Check if service is running with detailed error output
echo Checking service health...
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8802/api/health' -TimeoutSec 10; Write-Host 'Health check successful'; exit 0 } catch { Write-Host 'Health check failed:' $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo.
    echo Service failed to start or health check failed.
    echo.
    echo Troubleshooting steps:
    echo 1. Check if the "Alpha Arena Backend" window opened and shows any errors
    echo 2. Try running manually: cd backend ^&^& .venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8802
    echo 3. Check if port 8802 is already in use: netstat -an ^| findstr :8802
    echo 4. Check if Python virtual environment is working: .venv\Scripts\python --version
    echo.
    pause
    exit /b 1
)

echo.
echo Service started successfully!
echo    - Backend API: http://localhost:8802
echo    - Health Check: http://localhost:8802/api/health
echo    - System Logs API: http://localhost:8802/api/system-logs
echo.
echo System Log Features:
echo    - View logs: GET /api/system-logs
echo    - Get stats: GET /api/system-logs/stats
echo    - Clear logs: DELETE /api/system-logs
echo.
echo Open http://localhost:8802 in your browser to access the application
echo.
echo To stop the service: start_arena.bat stop
echo.

REM Open browser automatically
echo Opening browser...
start http://localhost:8802

echo Press any key to exit this window...
pause >nul