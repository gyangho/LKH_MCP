# Register only installer-owned fixed tasks. No arbitrary commands or task names.
# Intended for the explicitly approved Windows Installer (elevated).
param(
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][string]$AgentUser,
    [string]$ProjectAlias = "LKH_MCP",
    [string]$Repository = "gyangho/LKH_MCP",
    [string]$CheckoutPath = ""
)
$ErrorActionPreference = "Stop"

$agentExe = Join-Path $InstallDir "agent\LKH-Codex-Agent.exe"
$trayExe = Join-Path $InstallDir "LKH-MCP-Tray\LKH-MCP-Tray.exe"
$configurationDir = Join-Path $env:ProgramData "LKH-MCP\config"
$config = Join-Path $configurationDir "agent.json"
$credential = Join-Path $configurationDir "agent-credential.bin"

# Validate prerequisites before changing Task Scheduler.
foreach ($required in @($agentExe, $trayExe, $credential)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required installed artifact missing: $required"
    }
}
if ($AgentUser -cnotmatch '^[A-Za-z0-9_.\\@-]{1,128}$') { throw "Invalid Windows Agent account" }
if ($ProjectAlias -cnotmatch '^[A-Za-z0-9_-]{1,40}$') { throw "Invalid project alias" }
if ($Repository -cnotmatch '^[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100}$') { throw "Invalid owner/repository" }

$checkout = $CheckoutPath.Trim()
if ($checkout -ne "") {
    if ($checkout -cnotmatch '^[A-Za-z]:\\' -or -not (Test-Path -LiteralPath (Join-Path $checkout ".git"))) {
        throw "Project checkout must be an existing absolute Windows Git checkout"
    }
}
# Resolve Windows identity first to avoid registering an invalid task.
$account = New-Object System.Security.Principal.NTAccount($AgentUser)
$sid = $account.Translate([System.Security.Principal.SecurityIdentifier]).Value

if (-not (Test-Path -LiteralPath $config -PathType Leaf) -and $checkout -ne "") {
    $payload = @{
        server_url = "http://127.0.0.1:18081"
        agent_id = "win-" + ([guid]::NewGuid().ToString("N").Substring(0, 12))
        poll_interval_seconds = 10
        projects = @{ $ProjectAlias = @{ repository = $Repository; path = $checkout } }
    }
    $json = $payload | ConvertTo-Json -Depth 6
    [System.IO.File]::WriteAllText($config, $json, [System.Text.UTF8Encoding]::new($false))
}

if (Test-Path -LiteralPath $config -PathType Leaf) {
    try {
        $existing = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
        if (-not $existing.agent_id -or -not $existing.server_url -or -not $existing.projects) {
            throw "Invalid existing Agent configuration"
        }
    } catch {
        throw "Agent config is invalid; fix it before scheduling"
    }
}

# Agent can read its protected DPAPI blob/config, but not the SQLite DB.
$readAce = "*" + $sid + ":(R)"
& icacls.exe $credential /grant:r $readAce | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Device credential ACL grant failed" }
if (Test-Path -LiteralPath $config -PathType Leaf) {
    & icacls.exe $config /grant:r $readAce | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Agent configuration ACL grant failed" }
}

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $AgentUser
$principal = New-ScheduledTaskPrincipal -UserId $AgentUser -LogonType Interactive -RunLevel Limited
$agentAction = New-ScheduledTaskAction -Execute $agentExe -Argument ('--config "' + $config + '"') -WorkingDirectory (Split-Path $agentExe)
$agentSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "LKH-Codex-Agent" -Action $agentAction -Trigger $trigger -Principal $principal -Settings $agentSettings -Force | Out-Null
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
    Disable-ScheduledTask -TaskName "LKH-Codex-Agent" | Out-Null
}

# LocalService can only execute the fixed task, not change its action.
$com = New-Object -ComObject "Schedule.Service"
$com.Connect()
$registered = $com.GetFolder("\").GetTask("LKH-Codex-Agent")
$descriptor = $registered.GetSecurityDescriptor(4)
$registered.SetSecurityDescriptor($descriptor + "(A;;GRGX;;;LS)", 0)

# Tray runs in interactive user's session, independently of the SCM process.
$trayAction = New-ScheduledTaskAction -Execute $trayExe -WorkingDirectory (Split-Path $trayExe)
$traySettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "LKH-MCP-Tray" -Action $trayAction -Trigger $trigger -Principal $principal -Settings $traySettings -Force | Out-Null
Write-Host "Fixed Agent and Tray tasks configured for $AgentUser"
