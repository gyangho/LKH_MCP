# Read-only Native upgrade diagnostics. Does NOT stop services, migrate or overwrite data.
param([string]$StateDir = "$env:ProgramData\LKH-MCP")
$ErrorActionPreference = 'Stop'
if (-not [System.IO.Path]::IsPathRooted($StateDir)) { throw 'State directory must be absolute' }
$r = [ordered]@{ StateDir=$StateDir; ConfigPresent=$false; DatabasePresent=$false
    AgentPresent=$false; ServicePresent=$false; ReadyForUpgrade=$false }
$r.ConfigPresent = Test-Path -LiteralPath (Join-Path $StateDir 'config\bootstrap.json') -PathType Leaf
$r.DatabasePresent = Test-Path -LiteralPath (Join-Path $StateDir 'data\mcp.sqlite3') -PathType Leaf
$r.AgentPresent = Test-Path -LiteralPath (Join-Path $StateDir 'config\agent.json') -PathType Leaf
$r.ServicePresent = [bool](Get-Service -Name 'LKH-MCP-Server' -ErrorAction SilentlyContinue)
# File existence does not establish integrity. Separate verified backup and restore required.
$r.ReadyForUpgrade = $false
$r | ConvertTo-Json -Depth 3
