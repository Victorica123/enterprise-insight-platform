[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
& docker compose -f (Join-Path $projectRoot "compose.local.yml") down
if ($LASTEXITCODE -ne 0) { throw "Local compose shutdown failed." }
