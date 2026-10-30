# I1 preview: build a headless native Windows server bundle (NOT an SCM service).
# Runs only on a Windows build host. Does not register services, modify ports or DB.
param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") {
        throw "Windows is required to build the native server bundle"
    }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python interpreter not found: $Python" }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js/npm 22+ required" }
    $vendor = "vendor\ui-ux-pro-max-skill\src\ui-ux-pro-max\scripts\search.py"
    if (-not (Test-Path -LiteralPath $vendor -PathType Leaf)) {
        throw "Vendor submodule not initialized; use git submodule update --init --recursive"
    }
    Push-Location frontend
    try {
        & npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
    } finally { Pop-Location }
    if (-not (Test-Path "frontend\dist\index.html")) { throw "Missing frontend/dist/index.html" }
    & $Python -m pip install -r requirements.txt -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
    & $Python scripts/generate_icon.py
    if ($LASTEXITCODE -ne 0) { throw "Approved Pixel Pig icon generation failed" }
    & $Python -m PyInstaller --noconfirm --clean --onedir --console `
        --name LKH-MCP-Server --paths src `
        --version-file "scripts/windows-version.txt" --icon "assets/lkh-mcp.ico" `
        --collect-submodules mcp.server --collect-submodules oracledb `
        --add-data "frontend/dist;web/dist" `
        --add-data "vendor/ui-ux-pro-max-skill;vendor/ui-ux-pro-max-skill" `
        src/native_server.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
    $exe = "dist\LKH-MCP-Server\LKH-MCP-Server.exe"
    if (-not (Test-Path $exe)) { throw "Native server executable missing" }
    & $exe --check
    if ($LASTEXITCODE -ne 0) { throw "Native bundle preflight failed" }
    Write-Host "I1 preview built and asset-checked: $exe"
    Write-Host "NOT validated: SCM Service, dual-port isolation, Oracle 11g, UIUX external Python."
    Write-Host "Default preview bind: 127.0.0.1:18080 (does not replace Docker)."
} finally { Pop-Location }
