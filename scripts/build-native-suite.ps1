# I2-I6 unsigned build: separate Service / Tray / Agent / enrollment bundles.
# No service registration; no Docker or existing Windows data is modified.
param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    & .\scripts\build-native-server.ps1 -Python $Python
    if ($LASTEXITCODE -ne 0) { throw "Server build failed" }
    & $Python -m pip install -r requirements-native-build.txt
    if ($LASTEXITCODE -ne 0) { throw "Native Windows dependencies unavailable" }
    $base = @("--noconfirm", "--clean", "--onedir", "--paths", "src",
              "--hidden-import", "win32timezone")
    & $Python -m PyInstaller @base --console --name LKH-MCP-Service `
        --collect-submodules win32com src/native_service.py
    if ($LASTEXITCODE -ne 0) { throw "Service build failed" }
    & $Python -m PyInstaller @base --noconsole --name LKH-MCP-Tray `
        --icon "assets/lkh-mcp.ico" --hidden-import pystray._win32 `
        --add-data "assets;assets" src/native_tray.py
    if ($LASTEXITCODE -ne 0) { throw "Tray build failed" }
    & $Python -m PyInstaller @base --console --name LKH-Codex-Agent `
        --hidden-import win32crypt windows_agent/agent.py
    if ($LASTEXITCODE -ne 0) { throw "Agent build failed" }
    & $Python -m PyInstaller @base --console --name LKH-MCP-Enroll `
        --hidden-import win32crypt scripts/native-enroll.py
    if ($LASTEXITCODE -ne 0) { throw "Enrollment build failed" }
    & $Python -m PyInstaller @base --console --name LKH-MCP-Admin-Setup `
        scripts/native-admin-setup.py
    if ($LASTEXITCODE -ne 0) { throw "Admin bootstrap build failed" }
    foreach ($name in @("LKH-MCP-Admin-Setup", "LKH-MCP-Server", "LKH-MCP-Service", "LKH-MCP-Tray",
                         "LKH-Codex-Agent", "LKH-MCP-Enroll")) {
        if (-not (Test-Path "dist\$name\$name.exe")) {
            throw "Missing unsigned bundle: $name"
        }
    }
    Write-Host "Unsigned suite completed. Install/SCM/ACL/Oracle parity NOT verified."
} finally { Pop-Location }
