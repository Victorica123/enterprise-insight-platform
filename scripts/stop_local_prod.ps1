[CmdletBinding()]
param(
    [switch]$Faults,
    [switch]$Purge
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $projectRoot "runtime\local-prod\.env"
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Local production-like environment file does not exist: $envFile"
}

$arguments = @("compose", "--env-file", $envFile, "-f", (Join-Path $projectRoot "compose.local-prod.yml"))
if ($Faults) {
    $arguments += @("-f", (Join-Path $projectRoot "compose.local-prod.faults.yml"))
}
$arguments += "down"
if ($Purge) { $arguments += "--volumes" }

& docker @arguments
if ($LASTEXITCODE -ne 0) { throw "Local production-like stack shutdown failed." }
if ($Purge) {
    Write-Warning "MySQL, Redis, MinIO and Grafana named volumes were removed. Files under runtime/local-prod remain."
}
