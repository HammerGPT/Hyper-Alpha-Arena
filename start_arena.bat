@echo off
REM Alpha Arena Windows Startup Script
REM This script automatically detects the project directory and starts the backend service

echo === Alpha Arena Windows Startup Script ===
echo Starting backend service on port 8802...

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0
set BACKEND_DIR=%SCRIPT_DIR%backend

echo Project directory: %SCRIPT_DIR%
echo Backend directory: %BACKEND_DIR%

REM Check if backend directory exists
if not exist "%BACKEND_DIR%" (
    echo ERROR: Backend directory not found at %BACKEND_DIR%
    echo Please make sure you're running this script from the project root directory.
    pause
    exit /b 1
)

REM Change to backend directory
cd /d "%BACKEND_DIR%"

REM Check if virtual environment exists
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found.
    echo Please run the setup script first to create the virtual environment.
    echo.
    echo To create virtual environment:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -e .
    pause
    exit /b 1
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
start "Alpha Arena Backend" /min "%BACKEND_DIR%\.venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8802

REM Wait for service to start
echo Waiting for service to start...
timeout /t 5 /nobreak >nul

REM Check if service is running
powershell -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8802/api/health' -TimeoutSec 5 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Service failed to start. Please check the backend window for errors.
    echo You can also check the logs manually.
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
echo To stop the service: Close the "Alpha Arena Backend" window
echo or run: taskkill /f /im python.exe /fi "WINDOWTITLE eq Alpha Arena Backend*"
echo.

REM Open browser automatically
echo Opening browser...
start http://localhost:8802

echo Press any key to exit this window...
pause >nul