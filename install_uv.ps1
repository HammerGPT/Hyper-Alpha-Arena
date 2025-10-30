# Alpha Arena - UV Package Manager Installation Script for Windows
# This script downloads and installs UV package manager on Windows systems

Write-Host "=== Alpha Arena UV Installation Script ===" -ForegroundColor Green
Write-Host "Installing UV package manager for Python..." -ForegroundColor Yellow

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")

if (-not $isAdmin) {
    Write-Host "WARNING: Not running as Administrator. Installation may fail." -ForegroundColor Yellow
    Write-Host "Consider running PowerShell as Administrator for best results." -ForegroundColor Yellow
    Write-Host ""
}

# Check if UV is already installed
try {
    $uvVersion = & uv --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "UV is already installed: $uvVersion" -ForegroundColor Green
        Write-Host "Installation completed successfully!" -ForegroundColor Green
        exit 0
    }
} catch {
    # UV not found, continue with installation
}

Write-Host "Downloading UV installer..." -ForegroundColor Yellow

# Create temporary directory
$tempDir = Join-Path $env:TEMP "uv-installer"
if (Test-Path $tempDir) {
    Remove-Item $tempDir -Recurse -Force
}
New-Item -ItemType Directory -Path $tempDir | Out-Null

# Download UV installer
$installerUrl = "https://github.com/astral-sh/uv/releases/latest/download/uv-installer.ps1"
$installerPath = Join-Path $tempDir "uv-installer.ps1"

try {
    Write-Host "Downloading from: $installerUrl" -ForegroundColor Gray
    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
    Write-Host "Download completed successfully." -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to download UV installer." -ForegroundColor Red
    Write-Host "Error details: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Manual installation instructions:" -ForegroundColor Yellow
    Write-Host "1. Visit: https://github.com/astral-sh/uv" -ForegroundColor Gray
    Write-Host "2. Download the Windows installer" -ForegroundColor Gray
    Write-Host "3. Run the installer as Administrator" -ForegroundColor Gray
    exit 1
}

# Run the installer
Write-Host "Running UV installer..." -ForegroundColor Yellow
try {
    & PowerShell -ExecutionPolicy Bypass -File $installerPath
    if ($LASTEXITCODE -ne 0) {
        throw "Installer returned error code: $LASTEXITCODE"
    }
} catch {
    Write-Host "ERROR: UV installation failed." -ForegroundColor Red
    Write-Host "Error details: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting steps:" -ForegroundColor Yellow
    Write-Host "1. Run PowerShell as Administrator" -ForegroundColor Gray
    Write-Host "2. Check your internet connection" -ForegroundColor Gray
    Write-Host "3. Temporarily disable antivirus software" -ForegroundColor Gray
    Write-Host "4. Try manual installation from GitHub" -ForegroundColor Gray
    exit 1
}

# Clean up temporary files
Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue

# Refresh environment variables
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")

# Verify installation
Write-Host "Verifying UV installation..." -ForegroundColor Yellow
Start-Sleep -Seconds 2

try {
    $uvVersion = & uv --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "UV installed successfully: $uvVersion" -ForegroundColor Green
        Write-Host ""
        Write-Host "Next steps:" -ForegroundColor Yellow
        Write-Host "1. Close and reopen your terminal/PowerShell" -ForegroundColor Gray
        Write-Host "2. Navigate to your project directory" -ForegroundColor Gray
        Write-Host "3. Run: uv sync" -ForegroundColor Gray
        Write-Host "4. Run: start_arena.bat" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Installation completed successfully!" -ForegroundColor Green
    } else {
        throw "UV command not found after installation"
    }
} catch {
    Write-Host "WARNING: UV installation may not be complete." -ForegroundColor Yellow
    Write-Host "Please restart your terminal and try running 'uv --version'" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "If UV is still not found:" -ForegroundColor Yellow
    Write-Host "1. Restart your computer" -ForegroundColor Gray
    Write-Host "2. Check if UV was added to your PATH environment variable" -ForegroundColor Gray
    Write-Host "3. Try manual installation from: https://github.com/astral-sh/uv" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Press any key to continue..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")