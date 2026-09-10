[CmdletBinding()]
param([int]$LogMinutes = 15)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $projectRoot "runtime\local-prod\.env"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputDir = Join-Path $projectRoot "runtime\local-prod\diagnostics\$stamp"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$compose = @("compose", "--env-file", $envFile, "-f", (Join-Path $projectRoot "compose.local-prod.yml"))

(& docker stats --no-stream --format "{{.Name}}`t{{.CPUPerc}}`t{{.MemUsage}}`t{{.PIDs}}") |
    Set-Content -LiteralPath (Join-Path $outputDir "container-stats.txt") -Encoding utf8
(& docker @compose ps) | Set-Content -LiteralPath (Join-Path $outputDir "compose-ps.txt") -Encoding utf8

# SIGQUIT is non-destructive for the JVM and prints a full thread dump to the container log.
& docker @compose exec -T media sh -c "kill -3 1"
Start-Sleep -Seconds 2
$applicationLog = Join-Path $outputDir "application.log"
(& docker @compose logs --no-color --since "${LogMinutes}m" media agent) |
    Set-Content -LiteralPath $applicationLog -Encoding utf8
(& docker @compose exec -T redis redis-cli INFO memory) |
    Set-Content -LiteralPath (Join-Path $outputDir "redis-memory.txt") -Encoding utf8
(& docker @compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SHOW ENGINE INNODB STATUS\G"') |
    Set-Content -LiteralPath (Join-Path $outputDir "mysql-innodb-status.txt") -Encoding utf8
(& docker @compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" videoplatform -e "SELECT status, COUNT(*) AS task_count FROM video_task GROUP BY status; SELECT status, COUNT(*) AS dispatch_count FROM workflow_dispatch_outbox GROUP BY status; SELECT status, COUNT(*) AS integration_count FROM integration_event_outbox GROUP BY status;"') |
    Set-Content -LiteralPath (Join-Path $outputDir "database-backlog.txt") -Encoding utf8

$mediaContainerId = (& docker @compose ps -q media).Trim()
if ($mediaContainerId) {
    $jfrSource = "${mediaContainerId}:/app/diagnostics/media.jfr"
    & docker cp $jfrSource (Join-Path $outputDir "media-active.jfr") 2>$null
}
Write-Host "Diagnostics captured under $outputDir"
if (Select-String -LiteralPath $applicationLog -Pattern "Found one Java-level deadlock", "Found [0-9]+ deadlocks" -Quiet) {
    throw "The JVM thread dump reports a Java-level deadlock. See $applicationLog"
}
