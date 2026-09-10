[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$Faults,
    [switch]$RequireRealAi,
    [switch]$SkipSoak,
    [switch]$SkipMemoryProbe,
    [int]$MemoryIterations = 2000
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not (Get-Command k6 -ErrorAction SilentlyContinue)) {
    throw "k6 is required. Install it first, then rerun this script."
}

& (Join-Path $PSScriptRoot "start_local_prod.ps1") -Build:$Build -Faults:$Faults `
    -Observability -RequireRealAi:$RequireRealAi

$deadline = (Get-Date).AddMinutes(5)
do {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:18081/actuator/health" -TimeoutSec 3
        if ($health.status -eq "UP") { break }
    } catch { }
    Start-Sleep -Seconds 3
} while ((Get-Date) -lt $deadline)
if (-not $health -or $health.status -ne "UP") { throw "Media Service did not become healthy in five minutes." }

$env:E2E_BASE_URL = "http://127.0.0.1:18080"
& python (Join-Path $projectRoot "scripts\local_oidc.py")
if ($LASTEXITCODE -ne 0) { throw "Dedicated OIDC test identity preparation failed." }
Get-Content (Join-Path $projectRoot "runtime\local-prod\load.env") | ForEach-Object {
    $name, $value = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
}
& k6 run (Join-Path $projectRoot "quality\load\k6\e2e-smoke.js")
if ($LASTEXITCODE -ne 0) { throw "End-to-end smoke failed." }

if (-not $SkipSoak) {
    & k6 run (Join-Path $projectRoot "quality\load\k6\platform-soak.js")
    if ($LASTEXITCODE -ne 0) { throw "Platform soak thresholds failed." }
}

if (-not $SkipMemoryProbe) {
    $envFile = Join-Path $projectRoot "runtime\local-prod\.env"
    $compose = @("compose", "--env-file", $envFile, "-f", (Join-Path $projectRoot "compose.local-prod.yml"))
    if ($Faults) { $compose += @("-f", (Join-Path $projectRoot "compose.local-prod.faults.yml")) }
    $probe = Join-Path $projectRoot "quality\memory\agent_tracemalloc_probe.py"
    & docker @compose cp $probe "agent:/tmp/agent_tracemalloc_probe.py"
    if ($LASTEXITCODE -ne 0) { throw "Unable to copy the Agent memory probe into the container." }
    & docker @compose exec -T -e AGENT_SOURCE_DIR=/app agent `
        python /tmp/agent_tracemalloc_probe.py --iterations $MemoryIterations --max-growth-mb 24
    if ($LASTEXITCODE -ne 0) { throw "Agent tracemalloc growth threshold failed." }
}

& (Join-Path $PSScriptRoot "capture_local_diagnostics.ps1")
Write-Host "Reliability run completed. Review runtime/local-prod/results and diagnostics."
