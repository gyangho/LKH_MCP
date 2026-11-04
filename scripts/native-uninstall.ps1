# Elevated, fixed-scope removal hook for the Native Inno Setup uninstaller.
param(
    [ValidateSet('program','settings','all')][string]$Mode = 'settings',
    [ValidateSet('verify','remove')][string]$Stage = 'verify',
    [Parameter(Mandatory=$true)][string]$InstallDir
)
$ErrorActionPreference = 'Stop'
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Uninstaller must run elevated. Launch the installed uninstaller and approve Windows UAC.'
}
Set-StrictMode -Version Latest

function FullPath([string]$path) {
    if (-not [IO.Path]::IsPathRooted($path)) { throw 'Absolute path required' }
    return [IO.Path]::GetFullPath($path).TrimEnd('\')
}
function NoReparse([string]$path, [bool]$deep = $false) {
    if (-not (Test-Path -LiteralPath $path)) { return }
    $stack = New-Object 'System.Collections.Generic.Stack[string]'
    $stack.Push($path)
    while ($stack.Count) {
        $item = Get-Item -LiteralPath $stack.Pop() -Force -ErrorAction Stop
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Refusing junction or symbolic link in LKH owned path'
        }
        if ($deep -and $item.PSIsContainer) {
            foreach ($child in @(Get-ChildItem -LiteralPath $item.FullName -Force -ErrorAction Stop)) {
                $stack.Push($child.FullName)
            }
        }
    }
}
function OwnedTask([string]$name,[string]$exe) {
    $task = Get-ScheduledTask -TaskPath '\' -TaskName $name -ErrorAction SilentlyContinue
    if ($null -eq $task) { return $null }
    $actions = @($task.Actions)
    if ($actions.Count -ne 1 -or (FullPath $actions[0].Execute) -ine (FullPath $exe)) {
        throw "Task $name is not the installed LKH task; refusing removal"
    }
    return $task
}
function OwnedService([string]$exe) {
    $service = Get-CimInstance Win32_Service -Filter "Name='LKH-MCP-Server'" -ErrorAction Stop
    if ($null -eq $service) { return $null }
    $command = $service.PathName.Trim()
    if ($command -match '^"([^"]+\.exe)"(?:\s|$)') { $actual = $Matches[1] }
    elseif ($command -match '^(.+?\.exe)(?:\s|$)') { $actual = $Matches[1] }
    else { throw 'Unknown Windows service executable' }
    if ((FullPath $actual) -ine (FullPath $exe)) {
        throw 'Windows service name belongs to another executable'
    }
    return $service
}

if ([string]::IsNullOrWhiteSpace($env:ProgramData)) { throw 'ProgramData not available' }
$install = FullPath $InstallDir
$state = FullPath (Join-Path $env:ProgramData 'LKH-MCP')
$backups = FullPath (Join-Path $env:ProgramData 'LKH-MCP-RemovalBackups')
$svcExe = Join-Path $install 'LKH-MCP-Service\LKH-MCP-Service.exe'
if ($state -ieq $install -or $state -ieq (FullPath $env:ProgramData)) {
    throw 'Unsafe install or state path'
}
NoReparse $install
NoReparse $state ($Mode -eq 'all')
NoReparse $backups
if ($Mode -eq 'settings') { NoReparse (Join-Path $state 'config') $true }
if ($Mode -eq 'all' -and (Test-Path -LiteralPath $state)) {
    foreach ($entry in @(Get-ChildItem -LiteralPath $state -Force -ErrorAction Stop)) {
        if ($entry.Name -notin @('config','data','logs','backups') -or -not $entry.PSIsContainer) {
            throw 'Unexpected state-root file or directory: manual review required'
        }
    }
}
$agent = OwnedTask 'LKH-Codex-Agent' (Join-Path $install 'agent\LKH-Codex-Agent.exe')
$tray = OwnedTask 'LKH-MCP-Tray' (Join-Path $install 'LKH-MCP-Tray\LKH-MCP-Tray.exe')
$service = OwnedService $svcExe
$db = Join-Path $state 'data\mcp.sqlite3'
$backupExe = Join-Path $install 'LKH-MCP-DB-Backup\LKH-MCP-DB-Backup.exe'
if ($Mode -eq 'all' -and (Test-Path -LiteralPath $db) -and
    -not (Test-Path -LiteralPath $backupExe -PathType Leaf)) {
    throw 'Verified SQLite backup helper is required for full removal'
}
if ($null -ne $service -and $service.State -ne 'Stopped') {
    try {
        $adminPort = 8001
        $networkFile = Join-Path $state 'config\network.ini'
        if (Test-Path -LiteralPath $networkFile -PathType Leaf) {
            $entries = @(Get-Content -LiteralPath $networkFile | Where-Object { $_ -match '^admin_port\s*=' })
            if ($entries.Count -ne 1 -or $entries[0] -notmatch '^admin_port\s*=\s*([0-9]{1,5})\s*$') {
                throw 'Invalid administrator port configuration'
            }
            $adminPort = [int]$Matches[1]
            if ($adminPort -lt 1 -or $adminPort -gt 65535) { throw 'Invalid administrator port' }
        }
        $verdict = Invoke-RestMethod -Uri "http://127.0.0.1:$adminPort/admin/host/tray-state" -TimeoutSec 3
    } catch {
        throw 'Running Native service could not confirm idle status'
    }
    if ($verdict.state -notin @('online','offline') -or $verdict.busy -isnot [bool] -or $verdict.busy) {
        throw 'Agent busy or idle status unknown; uninstall blocked'
    }
}
if ($Stage -eq 'verify') {
    Write-Output "Native uninstall validation passed: $Mode"
    exit 0
}
# Stop only validated installation-owned tasks; never enumerate arbitrary tasks.
foreach ($task in @($agent,$tray)) {
    if ($null -eq $task) { continue }
    if ($task.State -eq 'Running') {
        Stop-ScheduledTask -InputObject $task -ErrorAction Stop
        $deadline = (Get-Date).AddSeconds(15)
        do {
            Start-Sleep -Milliseconds 250
            $current = Get-ScheduledTask -TaskPath '\' -TaskName $task.TaskName -ErrorAction Stop
        } while ($current.State -eq 'Running' -and (Get-Date) -lt $deadline)
        if ($current.State -eq 'Running') { throw 'Scheduled task refused to stop' }
    }
}
# Post-install/menu shortcuts can launch a tray outside Task Scheduler.
# Stop only executable paths belonging to this exact installation.
foreach ($relative in @('LKH-MCP-Tray\LKH-MCP-Tray.exe', 'agent\LKH-Codex-Agent.exe')) {
    $expected = FullPath (Join-Path $install $relative)
    foreach ($process in @(Get-CimInstance Win32_Process -ErrorAction Stop)) {
        if ($process.ExecutablePath -and (FullPath $process.ExecutablePath) -ieq $expected) {
            $owned = Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
            if ($null -ne $owned) {
                # Revalidate after lookup to avoid stopping a reused PID.
                if ((FullPath $owned.Path) -ine $expected) { throw 'Process ownership changed' }
                $owned.Kill()
                if (-not $owned.WaitForExit(15000)) { throw "Installed process still running: $relative" }
            }
        }
    }
}
if ($null -ne $service) {
    $running = Get-Service -Name 'LKH-MCP-Server' -ErrorAction Stop
    if ($running.Status -ne 'Stopped') {
        Stop-Service -Name 'LKH-MCP-Server' -ErrorAction Stop
        $running.WaitForStatus('Stopped',[TimeSpan]::FromSeconds(30))
    }
    & $svcExe remove | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Service removal failed' }
}
foreach ($task in @($agent,$tray)) {
    if ($null -ne $task) {
        Unregister-ScheduledTask -TaskPath '\' -TaskName $task.TaskName -Confirm:$false -ErrorAction Stop
    }
}
# Downloaded skill versions are application code, removed in every uninstall mode.
$skillsRoot = FullPath (Join-Path $install 'skills')
if (-not $skillsRoot.StartsWith($install + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Downloaded skills directory is outside installation'
}
NoReparse $skillsRoot $true
if (Test-Path -LiteralPath $skillsRoot) {
    Remove-Item -LiteralPath $skillsRoot -Recurse -Force -ErrorAction Stop
}
if ($Mode -eq 'settings' -and (Test-Path -LiteralPath (Join-Path $state 'config'))) {
    # The SQLite device verifier remains, while its DPAPI key is removed.
    # Mark an explicit settings-reset to allow safe one-time re-enrollment on reinstall.
    if (Test-Path -LiteralPath $db -PathType Leaf) {
        $marker = Join-Path $state 'data\.enrollment-reset-by-uninstall'
        NoReparse $marker
        if (-not (Test-Path -LiteralPath $marker)) {
            [IO.File]::WriteAllText($marker, 'settings-reset', [Text.Encoding]::ASCII)
        }
    }
    Remove-Item -LiteralPath (Join-Path $state 'config') -Recurse -Force -ErrorAction Stop
}
if ($Mode -eq 'all' -and (Test-Path -LiteralPath $state)) {
    if (Test-Path -LiteralPath $db -PathType Leaf) {
        if (-not (Test-Path -LiteralPath $backups)) {
            New-Item -ItemType Directory -Path $backups -ErrorAction Stop | Out-Null
        }
        NoReparse $backups
        & icacls.exe $backups /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'External backup ACL could not be secured' }
        $id = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N')
        $dir = Join-Path $backups $id
        New-Item -ItemType Directory -Path $dir -ErrorAction Stop | Out-Null
        $destination = Join-Path $dir 'mcp.sqlite3'
        & $backupExe --source $db --destination $destination | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $destination -PathType Leaf)) {
            throw 'Verified SQLite recovery snapshot failed; original data not removed'
        }
        Write-Output "SQLite recovery snapshot retained: $dir"
    } elseif (Test-Path -LiteralPath (Join-Path $state 'data\mcp.sqlite3-wal')) {
        throw 'Orphan SQLite WAL; full removal blocked'
    }
    NoReparse $state $true
    Remove-Item -LiteralPath $state -Recurse -Force -ErrorAction Stop
}
Write-Output "Native uninstall cleanup completed: $Mode"
