# Installer-owned lifecycle gate. Does not delete user data or source repositories.
param(
    [Parameter(Mandatory=$true)][ValidateSet('begin','activate','ready','fail')][string]$Action,
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+$')][string]$Version
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$install = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
if (-not [IO.Path]::IsPathRooted($InstallDir) -or $install.Length -lt 4) { throw 'Invalid installation directory' }
$state = Join-Path $env:ProgramData 'LKH-MCP'
$config = Join-Path $state 'config'
$marker = Join-Path $config 'installation.json'
$script:LifecycleStep = 'validate-state-paths'
$script:FailureRecorded = $false
function WriteLifecycleResult([bool]$ok, $record = $null) {
    # Safe metadata only. Never include exception messages, credentials, command lines or stack traces.
    try {
        $logDir = Join-Path $state 'logs'
        if ((Test-Path -LiteralPath $logDir) -and ((Get-Item -LiteralPath $logDir -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { return }
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        $statusFile = Join-Path $logDir ("installer-" + $Action + ".json")
        if ((Test-Path -LiteralPath $statusFile) -and ((Get-Item -LiteralPath $statusFile -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { return }
        $result = [ordered]@{ ok=$ok; action=$Action; step=$script:LifecycleStep; version=$Version; at=[DateTime]::UtcNow.ToString('o') }
        if ($null -ne $record) {
            $exception = $record.Exception
            if ($null -ne $exception.InnerException) { $exception = $exception.InnerException }
            $result['reason'] = $exception.GetType().FullName
            $result['hresult'] = $exception.HResult
            $safeId = [regex]::Replace([string]$record.FullyQualifiedErrorId, '[^A-Za-z0-9_.,:-]', '')
            $result['error_id'] = $safeId.Substring(0, [Math]::Min(200, $safeId.Length))
            $result['line'] = $record.InvocationInfo.ScriptLineNumber
            if ($exception -is [ComponentModel.Win32Exception]) { $result['win32_error'] = $exception.NativeErrorCode }
            if ($exception -is [ArgumentException]) { $result['parameter'] = $exception.ParamName }
        }
        [IO.File]::WriteAllText($statusFile, ($result | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
        & icacls.exe $statusFile /inheritance:r /grant:r '*S-1-5-32-544:F' '*S-1-5-18:F' '*S-1-5-19:R' '*S-1-5-32-545:R' | Out-Null
    } catch { }
}
trap {
    if (-not $script:FailureRecorded) { WriteLifecycleResult $false $_ }
    exit 1
}
foreach ($path in @($state,$config,$marker)) {
    if ((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Refusing redirected installation state'
    }
}
$script:LifecycleStep = 'validate-service-ownership'
$expectedService = Join-Path $install 'LKH-MCP-Service\LKH-MCP-Service.exe'
$service = Get-CimInstance Win32_Service -Filter "Name='LKH-MCP-Server'" -ErrorAction Stop
if ($null -ne $service) {
    $command = $service.PathName.Trim()
    if ($command -match '^"([^"]+\.exe)"(?:\s|$)') { $actual = $Matches[1] }
    elseif ($command -match '^(.+?\.exe)(?:\s|$)') { $actual = $Matches[1] }
    else { throw 'Unknown service executable' }
    if ([IO.Path]::GetFullPath($actual) -ine $expectedService) { throw 'Service belongs to another installation' }
}
$script:LifecycleStep = 'validate-task-ownership'
$ownedTasks = @()
foreach ($name in @('LKH-Codex-Agent','LKH-MCP-Tray')) {
    $task = Get-ScheduledTask -TaskPath '\' -TaskName $name -ErrorAction SilentlyContinue
    if ($null -eq $task) { continue }
    $relative = if ($name -eq 'LKH-Codex-Agent') { 'agent\LKH-Codex-Agent.exe' } else { 'LKH-MCP-Tray\LKH-MCP-Tray.exe' }
    if (@($task.Actions).Count -ne 1 -or [IO.Path]::GetFullPath($task.Actions[0].Execute) -ine (Join-Path $install $relative)) {
        throw 'Task belongs to another installation'
    }
    $ownedTasks += $task
}
function SavePhase([string]$phase) {
    $script:LifecycleStep = 'write-state-' + $phase
    New-Item -ItemType Directory -Path $config -Force | Out-Null
    $id = [guid]::NewGuid().ToString('N')
    $temporary = Join-Path $config ('installation-' + $id + '.tmp')
    $backup = Join-Path $config ('installation-' + $id + '.bak')
    $payload = @{ phase=$phase; version=$Version; updated_at=[DateTime]::UtcNow.ToString('o') } | ConvertTo-Json
    try {
        [IO.File]::WriteAllText($temporary, $payload, [Text.UTF8Encoding]::new($false))
        $script:LifecycleStep = 'publish-state-' + $phase
        # Use a real backup path: PowerShell/.NET string binding must not turn null into an empty path.
        if (Test-Path -LiteralPath $marker) { [IO.File]::Replace($temporary,$marker,$backup) }
        else { [IO.File]::Move($temporary,$marker) }
        $script:LifecycleStep = 'state-permissions-' + $phase
        & icacls.exe $marker /inheritance:r /grant:r '*S-1-5-32-544:F' '*S-1-5-18:F' '*S-1-5-19:R' '*S-1-5-32-545:R' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Installation marker ACL failed' }
    } finally {
        # Both are unique, fixed-scope state files created by this invocation. No recursive deletion.
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue }
    }
}
function StopOwned {
    $script:LifecycleStep = 'stop-owned-components'
    foreach ($task in $ownedTasks) {
        Disable-ScheduledTask -InputObject $task | Out-Null
        if ($task.State -eq 'Running') { Stop-ScheduledTask -InputObject $task }
    }
    if ($null -ne $service) {
        Set-Service -Name 'LKH-MCP-Server' -StartupType Disabled
        $running = Get-Service -Name 'LKH-MCP-Server'
        if ($running.Status -ne 'Stopped') {
            Stop-Service -Name 'LKH-MCP-Server'
            $running.WaitForStatus('Stopped',[TimeSpan]::FromSeconds(40))
        }
    }
    # Shortcuts can launch a tray outside its scheduled task.
    $fixedPaths = @((Join-Path $install 'agent\LKH-Codex-Agent.exe'), (Join-Path $install 'LKH-MCP-Tray\LKH-MCP-Tray.exe'), (Join-Path $install 'LKH-MCP-Server\LKH-MCP-Server.exe'))
    foreach ($process in @(Get-CimInstance Win32_Process -ErrorAction Stop)) {
        if ($process.ExecutablePath -and $process.ExecutablePath -in $fixedPaths) {
            $owned = Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
            if ($null -ne $owned -and $owned.Path -in $fixedPaths) {
                $owned.Kill()
                if (-not $owned.WaitForExit(15000)) { throw 'Installed process did not stop' }
            }
        }
    }
}
function AdminPort {
    $port = 8001
    $network = Join-Path $config 'network.ini'
    if (Test-Path -LiteralPath $network) {
        $entries = @(Get-Content -LiteralPath $network | Where-Object { $_ -match '^admin_port\s*=' })
        if ($entries.Count -ne 1 -or $entries[0] -notmatch '^admin_port\s*=\s*([0-9]{1,5})\s*$') { throw 'Invalid administrator port' }
        $port = [int]$Matches[1]
        if ($port -lt 1 -or $port -gt 65535) { throw 'Invalid administrator port' }
    }
    return $port
}
if ($Action -eq 'begin') {
    $script:LifecycleStep = 'confirm-idle'
    # Do not interrupt a valid running job, including an installation-owned standalone server.
    $expectedServer = Join-Path $install 'LKH-MCP-Server\LKH-MCP-Server.exe'
    $standalone = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object { $_.ExecutablePath -and $_.ExecutablePath -ieq $expectedServer })
    if (($null -ne $service -and $service.State -ne 'Stopped') -or $standalone.Count -gt 0) {
        $port = AdminPort
        $verdict = Invoke-RestMethod -Uri "http://127.0.0.1:$port/admin/host/tray-state" -TimeoutSec 3
        if ($verdict.state -notin @('online','offline') -or $verdict.busy -isnot [bool] -or $verdict.busy) {
            throw 'Active or unknown Agent work; installation blocked'
        }
    }
    try {
        SavePhase 'installing'
        StopOwned
    } catch {
        WriteLifecycleResult $false $_
        $script:FailureRecorded = $true
        try { SavePhase 'failed'; StopOwned } catch { }
        throw 'Installation preparation failed; startup remains blocked'
    }
} elseif ($Action -eq 'activate') {
    SavePhase 'starting'
    $script:LifecycleStep = 'verify-service-manual'
    if ($null -eq $service) { throw 'Registered service not found' }
    if ($service.StartMode -ne 'Manual') {
        $script:LifecycleStep = 'set-service-manual'
        Set-Service -Name 'LKH-MCP-Server' -StartupType Manual
    }
} elseif ($Action -eq 'ready') {
    try {
        $script:LifecycleStep = 'confirm-server-health'
        $port = AdminPort
        $deadline = (Get-Date).AddSeconds(30)
        $confirmed = $false
        do {
            try {
                $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/admin/healthz" -TimeoutSec 2
                $currentService = Get-CimInstance Win32_Service -Filter "Name='LKH-MCP-Server'"
                [uint32]$healthPid = 0
                $validPid = [uint32]::TryParse([string]$health.pid, [ref]$healthPid)
                if ($health.status -eq 'ok' -and $health.application -eq 'LKH-MCP' -and $health.version -eq $Version -and
                    $currentService.State -eq 'Running' -and $validPid -and $healthPid -gt 0) {
                    $child = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $healthPid)
                    $expectedServer = Join-Path $install 'LKH-MCP-Server\LKH-MCP-Server.exe'
                    if ($null -ne $child -and $child.ExecutablePath -and
                        [IO.Path]::GetFullPath($child.ExecutablePath) -ieq $expectedServer -and
                        $child.ParentProcessId -eq $currentService.ProcessId) { $confirmed = $true }
                }
            } catch { }
            if (-not $confirmed) { Start-Sleep -Milliseconds 500 }
        } while (-not $confirmed -and (Get-Date) -lt $deadline)
        if (-not $confirmed) { throw 'Server startup not confirmed' }
        $script:LifecycleStep = 'set-service-automatic'
        Set-Service -Name 'LKH-MCP-Server' -StartupType Automatic
        SavePhase 'ready'
        $script:LifecycleStep = 'enable-installed-tasks'
        foreach ($task in $ownedTasks) { Enable-ScheduledTask -InputObject $task | Out-Null }
    } catch {
        WriteLifecycleResult $false $_
        $script:FailureRecorded = $true
        SavePhase 'failed'
        StopOwned
        throw 'Installation completion failed; service and tasks disabled'
    }
} else {
    SavePhase 'failed'
    StopOwned
}
WriteLifecycleResult $true
Write-Output "Native installation phase completed: $Action"
