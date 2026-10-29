# Build no-console LKH-MCP Windows EXE, versioned from version.py
param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (!(Test-Path $Python)) { throw "Python interpreter not found" }
$ver = (Select-String -Path src/version.py -Pattern 'VERSION = "([^"]+)"').Matches.Groups[1].Value
& $Python -m pip install -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency install failed" }
& $Python scripts/generate_icon.py
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }
& $Python -m PyInstaller --noconfirm --clean --onedir --noconsole --name LKH-MCP --version-file "scripts/windows-version.txt" --icon "assets/lkh-mcp.ico" --collect-submodules mcp.server --hidden-import pystray._win32 --add-data "assets;assets" --collect-submodules oracledb --add-data "web;web" --add-data "vendor\ui-ux-pro-max-skill;vendor\ui-ux-pro-max-skill" src/server_launcher.py
if ($LASTEXITCODE -ne 0) { throw "Build failed" }
$destination = "dist\LKH-MCP-v$ver"
if (Test-Path $destination) { Remove-Item -Recurse -Force $destination }
Copy-Item "dist\LKH-MCP" $destination -Recurse
Copy-Item ".env.example" "$destination\.env.example"
Write-Host "EXE built at $destination\LKH-MCP.exe"
