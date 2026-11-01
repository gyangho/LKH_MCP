# Admin-only installer step for an isolated Windows native instance.
param([Parameter(Mandatory=$true)][string]$InstallDir)
$ErrorActionPreference = "Stop"
$state = Join-Path $env:ProgramData "LKH-MCP"
foreach ($folder in @("config","data","logs","backups")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $state $folder) | Out-Null
}
# Explicitly lock service data to Administrators, SYSTEM, LocalService.
# Agent profile is deliberately NOT allowed to modify the SQLite database.
foreach ($folder in @("data","logs","backups")) {
    $dir = Join-Path $state $folder
    & icacls.exe $dir /inheritance:r | Out-Null
    & icacls.exe $dir /grant:r "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-19:(OI)(CI)M" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not grant service data ACL" }
}
$conf = Join-Path $state "config"
& icacls.exe $conf /inheritance:r | Out-Null
& icacls.exe $conf /grant:r "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-19:(OI)(CI)M" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not secure config ACL" }
Write-Host "Service data directories prepared. Agent identity ACL is configured separately."
