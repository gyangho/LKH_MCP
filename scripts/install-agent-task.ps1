# Register a SINGLE fixed Windows Scheduled Task (admin installer phase).
# Never register arbitrary user-provided executable commands.
param(
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][string]$AgentUser
)
$ErrorActionPreference = "Stop"
$exe = Join-Path $InstallDir "agent\LKH-Codex-Agent.exe"
$config = Join-Path $env:ProgramData "LKH-MCP\config\agent.json"
if (-not (Test-Path -LiteralPath $exe)) { throw "Installed Agent EXE missing" }
if (-not (Test-Path -LiteralPath $config)) {
    Write-Warning "Agent config missing; task will be registered but disabled until configured."
}
# Require explicit Windows identity supplied by installer; do not pass a password.
if ($AgentUser -notmatch '^[A-Za-z0-9_.\\@-]{1,128}$') { throw "Invalid account name" }
$action = New-ScheduledTaskAction -Execute $exe -Argument ('--config "' + $config + '"') -WorkingDirectory (Split-Path $exe)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $AgentUser
$principal = New-ScheduledTaskPrincipal -UserId $AgentUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "LKH-Codex-Agent" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
if (-not (Test-Path -LiteralPath $config)) {
    Disable-ScheduledTask -TaskName "LKH-Codex-Agent" | Out-Null
}
# Permit ONLY the selected account to read the DPAPI blob; do not grant Users.
$credential = Join-Path $env:ProgramData "LKH-MCP\\config\\agent-credential.bin"
if (-not (Test-Path -LiteralPath $credential)) { throw "Device enrollment credential not provisioned" }
$account = New-Object System.Security.Principal.NTAccount($AgentUser)
$sid = $account.Translate([System.Security.Principal.SecurityIdentifier]).Value
& icacls.exe $credential /grant:r "*${sid}:(R)" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Device credential ACL grant failed" }
Write-Host "Task registered for $AgentUser. Agent account must be logged in and authorized."
