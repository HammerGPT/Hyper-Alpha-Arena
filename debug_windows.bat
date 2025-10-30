@echo off
REM Alpha Arena Windows Debug Script
REM This script helps diagnose startup issues

echo === Alpha Arena Windows Debug Script ===
echo.

REM Get project directory
set SCRIPT_DIR=%~dp0
set BACKEND_DIR=%SCRIPT_DIR%backend

echo Project directory: %SCRIPT_DIR%
echo Backend directory: %BACKEND_DIR%
echo.

REM Check backend directory
if not exist "%BACKEND_DIR%" (
    echo ERROR: Backend directory not found!
    pause
    exit /b 1
)

cd /d "%BACKEND_DIR%"

echo === Checking Python Virtual Environment ===
if exist ".venv\Scripts\python.exe" (
    echo Virtual environment found: .venv\Scripts\python.exe
    ".venv\Scripts\python.exe" --version
) else (
    echo ERROR: Virtual environment not found at .venv\Scripts\python.exe
    echo Please create it first: python -m venv .venv
    pause
    exit /b 1
)
echo.

echo === Checking Dependencies ===
".venv\Scripts\python.exe" -c "import uvicorn; print('uvicorn:', uvicorn.__version__)"
if errorlevel 1 (
    echo ERROR: uvicorn not found. Installing...
    ".venv\Scripts\pip.exe" install -e .
)
echo.

echo === Checking Port 8802 ===
netstat -an | findstr :8802
if errorlevel 1 (
    echo Port 8802 is available
) else (
    echo WARNING: Port 8802 is already in use
)
echo.

echo === Testing Manual Startup ===
echo Starting backend manually (this will show any error messages)...
echo Press Ctrl+C to stop the server when you see it running
echo.
pause

".venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8802