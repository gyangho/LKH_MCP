# Register a SINGLE fixed Windows Scheduled Task (admin installer phase).
# Never register arbitrary user-provided executable commands.
param(
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][string]$AgentUser,
    [string]$ProjectAlias = "LKH_MCP",
    [string]$Repository = "gyangho/LKH_MCP",
    [string]$CheckoutPath = ""
)
$ErrorActionPreference = "Stop"
$exe = Join-Path $InstallDir "agent\LKH-Codex-Agent.exe"
$config = Join-Path $env:ProgramData "LKH-MCP\config\agent.json"
# The installer wizard's initial Agent config must be created BEFORE the task
# is registered; creating it from ssPostInstall could leave the task disabled.
if (-not [string]::IsNullOrWhiteSpace($CheckoutPath) -and
    -not (Test-Path -LiteralPath $config)) {
    if ($ProjectAlias -cnotmatch '^[A-Za-z0-9_-]{1,40} { throw "Installed Agent EXE missing" }
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
if (Test-Path -LiteralPath $config) {
    & icacls.exe $config /grant:r "*${sid}:(R)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Agent configuration ACL grant failed" }
}
# Grant local Service account READ/EXECUTE on this exact task only.
# Never give it task modification or arbitrary command execution rights.
$com = New-Object -ComObject "Schedule.Service"
$com.Connect()
$registered = $com.GetFolder("\").GetTask("LKH-Codex-Agent")
$descriptor = $registered.GetSecurityDescriptor(4)
$registered.SetSecurityDescriptor($descriptor + "(A;;GRGX;;;LS)", 0)
# Per-user Tray auto-start is a separate scheduled task, not an HKCU entry
# owned by whatever administrator elevated the Installer.
$trayExe = Join-Path $InstallDir "LKH-MCP-Tray\\LKH-MCP-Tray.exe"
if (-not (Test-Path -LiteralPath $trayExe)) { throw "Installed Tray EXE missing" }
$trayAction = New-ScheduledTaskAction -Execute $trayExe -WorkingDirectory (Split-Path $trayExe)
$traySettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "LKH-MCP-Tray" -Action $trayAction -Trigger $trigger -Principal $principal -Settings $traySettings -Force | Out-Null
Write-Host "Agent and Tray tasks registered for $AgentUser."
) {
        throw "Invalid project alias"
    }
    if ($Repository -cnotmatch '^[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100} { throw "Installed Agent EXE missing" }
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
if (Test-Path -LiteralPath $config) {
    & icacls.exe $config /grant:r "*${sid}:(R)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Agent configuration ACL grant failed" }
}
# Grant local Service account READ/EXECUTE on this exact task only.
# Never give it task modification or arbitrary command execution rights.
$com = New-Object -ComObject "Schedule.Service"
$com.Connect()
$registered = $com.GetFolder("\").GetTask("LKH-Codex-Agent")
$descriptor = $registered.GetSecurityDescriptor(4)
$registered.SetSecurityDescriptor($descriptor + "(A;;GRGX;;;LS)", 0)
# Per-user Tray auto-start is a separate scheduled task, not an HKCU entry
# owned by whatever administrator elevated the Installer.
$trayExe = Join-Path $InstallDir "LKH-MCP-Tray\\LKH-MCP-Tray.exe"
if (-not (Test-Path -LiteralPath $trayExe)) { throw "Installed Tray EXE missing" }
$trayAction = New-ScheduledTaskAction -Execute $trayExe -WorkingDirectory (Split-Path $trayExe)
$traySettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "LKH-MCP-Tray" -Action $trayAction -Trigger $trigger -Principal $principal -Settings $traySettings -Force | Out-Null
Write-Host "Agent and Tray tasks registered for $AgentUser."
) {
        throw "Invalid owner/repository"
    }
    if ($CheckoutPath -cnotmatch '^[A-Za-z]:\\' -or
        -not (Test-Path -LiteralPath (Join-Path $CheckoutPath ".git"))) {
        throw "Project checkout path must be an existing local Git checkout"
    }
    $agentId = "win-" + ([guid]::NewGuid().ToString("N").Substring(0, 12))
    $payload = @{
        server_url = "http://127.0.0.1:18081"
        agent_id = $agentId
        poll_interval_seconds = 10
        projects = @{ $ProjectAlias = @{ repository = $Repository; path = $CheckoutPath } }
    }
    $json = $payload | ConvertTo-Json -Depth 6
    # Agent config is not a credential; its parent directory is ACL-locked in preflight.
    [System.IO.File]::WriteAllText($config, $json, [System.Text.UTF8Encoding]::new($false))
}
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
if (Test-Path -LiteralPath $config) {
    & icacls.exe $config /grant:r "*${sid}:(R)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Agent configuration ACL grant failed" }
}
# Grant local Service account READ/EXECUTE on this exact task only.
# Never give it task modification or arbitrary command execution rights.
$com = New-Object -ComObject "Schedule.Service"
$com.Connect()
$registered = $com.GetFolder("\").GetTask("LKH-Codex-Agent")
$descriptor = $registered.GetSecurityDescriptor(4)
$registered.SetSecurityDescriptor($descriptor + "(A;;GRGX;;;LS)", 0)
# Per-user Tray auto-start is a separate scheduled task, not an HKCU entry
# owned by whatever administrator elevated the Installer.
$trayExe = Join-Path $InstallDir "LKH-MCP-Tray\\LKH-MCP-Tray.exe"
if (-not (Test-Path -LiteralPath $trayExe)) { throw "Installed Tray EXE missing" }
$trayAction = New-ScheduledTaskAction -Execute $trayExe -WorkingDirectory (Split-Path $trayExe)
$traySettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "LKH-MCP-Tray" -Action $trayAction -Trigger $trigger -Principal $principal -Settings $traySettings -Force | Out-Null
Write-Host "Agent and Tray tasks registered for $AgentUser."
