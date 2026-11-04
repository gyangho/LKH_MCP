# I1 preview: build a headless native Windows server bundle (NOT an SCM service).
# Runs only on a Windows build host. Does not register services, modify ports or DB.
param([string]$Python = ".\.venv\Scripts\python.exe", [switch]$SkipVersionBump)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command $Python -ErrorAction Stop).Source
$buildLock = $null
if (-not $SkipVersionBump) {
    New-Item -ItemType Directory -Path (Join-Path $root 'dist') -Force | Out-Null
    $buildLock = [IO.File]::Open((Join-Path $root 'dist\.native-build.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
}
Push-Location $root
try {
    if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") {
        throw "Windows is required to build the native server bundle"
    }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python interpreter not found: $Python" }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js/npm 22+ required" }
    if (-not $SkipVersionBump) {
        & $Python scripts/bump-native-version.py
        if ($LASTEXITCODE -ne 0) { throw "Native version update failed" }
    }
    $skills = "vendor\mattpocock-skills\.lkh-pinned-revision"
    if (-not (Test-Path -LiteralPath $skills -PathType Leaf)) {
        throw "Server engineering skills missing; run scripts/install-matt-skills.ps1 first"
    }
    if ((Get-Content -LiteralPath $skills -Raw).Trim() -ne "4ae2317ddb22b046e26455e4f9c9b3aaaf62212d") {
        throw "Mismatched engineering skills revision"
    }
    Push-Location frontend
    try {
        & npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
    } finally { Pop-Location }
    if (-not (Test-Path "frontend\dist\index.html")) { throw "Missing frontend/dist/index.html" }
    & $Python -m pip install -r requirements/runtime.txt -r requirements/build.txt -r requirements/windows.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
    & $Python scripts/generate_icon.py
    if ($LASTEXITCODE -ne 0) { throw "Approved Pixel Pig icon generation failed" }
    & $Python -m PyInstaller --noconfirm --clean --onedir --console `
        --name LKH-MCP-Server --paths src `
        --version-file "scripts/windows-version.txt" --icon "assets/lkh-mcp.ico" `
        --collect-submodules mcp.server --collect-submodules oracledb `
        --hidden-import win32com.client --hidden-import win32crypt `
        --add-data "frontend/dist;web/dist" `
        --add-data "vendor/ui-ux-pro-max-skill;vendor/ui-ux-pro-max-skill" `
        --add-data "vendor/mattpocock-skills;vendor/mattpocock-skills" `
        src/native_server.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
    $exe = "dist\LKH-MCP-Server\LKH-MCP-Server.exe"
    if (-not (Test-Path $exe)) { throw "Native server executable missing" }
    & $exe --check
    if ($LASTEXITCODE -ne 0) { throw "Native bundle preflight failed" }
    Write-Host "I1 preview built and asset-checked: $exe"
    Write-Host "NOT validated: SCM Service, dual-port isolation, Oracle, installer-downloaded public skills."
    Write-Host "Default preview bind: 127.0.0.1:8000 (does not replace Docker)."
} finally { Pop-Location; if ($null -ne $buildLock) { $buildLock.Dispose() } }
