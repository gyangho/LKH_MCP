# Prepare pinned Markdown skill documents on the MCP server only.
# No plugin is installed in Codex/Claude/ChatGPT, and no service is restarted.
param([string]$Destination = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$revision = "4ae2317ddb22b046e26455e4f9c9b3aaaf62212d"
$target = if ($Destination) { $Destination } else { Join-Path $root "vendor/mattpocock-skills" }
$marker = Join-Path $target ".lkh-pinned-revision"
if (Test-Path -LiteralPath $target) {
    if ((Test-Path -LiteralPath $marker -PathType Leaf) -and
        ((Get-Content -LiteralPath $marker -Raw).Trim() -eq $revision) -and
        (Test-Path -LiteralPath (Join-Path $target "LICENSE")) -and
        (Test-Path -LiteralPath (Join-Path $target ".claude-plugin/plugin.json"))) {
        Write-Host "Pinned server skills already installed: $revision"
        exit 0
    }
    throw "Target exists but is not the pinned installation; inspect it manually: $target"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git executable required on the MCP build/server host" }
& git clone --no-checkout --filter=blob:none https://github.com/mattpocock/skills.git $target
if ($LASTEXITCODE -ne 0) { throw "Git clone failed; inspect incomplete target" }
& git -C $target checkout --detach $revision
if ($LASTEXITCODE -ne 0) { throw "Pinned checkout failed; inspect incomplete target" }
$head = (& git -C $target rev-parse HEAD).Trim()
if ($head -ne $revision) { throw "Unexpected upstream commit" }
if (-not (Test-Path -LiteralPath (Join-Path $target "LICENSE")) -or
    -not (Test-Path -LiteralPath (Join-Path $target ".claude-plugin/plugin.json"))) {
    throw "Upstream license or manifest missing"
}
Set-Content -LiteralPath $marker -Value $revision -Encoding ascii
Write-Host "Server skill documents staged: $revision; client plugin installation not required"
