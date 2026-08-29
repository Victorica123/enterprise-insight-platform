[CmdletBinding()]
param(
    [int]$Port = 8080,
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:LOCAL_WEB_PORT = [string]$Port
$arguments = @("compose", "-f", (Join-Path $projectRoot "compose.local.yml"), "up", "-d")
if ($Build) { $arguments += "--build" }

& docker @arguments
if ($LASTEXITCODE -ne 0) { throw "Local compose startup failed." }

Write-Host "Enterprise Insight Platform is starting at http://127.0.0.1:$Port"
Write-Host "Run: docker compose -f `"$projectRoot\compose.local.yml`" ps"
