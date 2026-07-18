param(
    [ValidateSet("local", "mq")]
    [string]$Mode = "local",
    [ValidateRange(0, 60000)]
    [int]$MockDelayMs = 2000
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$env:APP_REDIS_ENABLED = "false"
$env:APP_MQ_ENABLED = if ($Mode -eq "mq") { "true" } else { "false" }
$env:APP_MQ_CONSUMER_THREADS = "4"
$env:APP_TRANSCRIPT_ENABLED = "false"
$env:APP_SUMMARY_ENABLED = "false"
$env:APP_TRANSCRIPT_MOCK_DELAY_MS = [string]$MockDelayMs
$env:APP_MAX_ACTIVE_TASKS_PER_USER = "0"
$env:APP_WORKFLOW_STALE_TASK_TIMEOUT = "10s"
$env:APP_WORKFLOW_REAPER_INTERVAL_MS = "5000"
$env:APP_WORKFLOW_REAPER_INITIAL_DELAY_MS = "5000"
$env:SPRING_DOCKER_COMPOSE_ENABLED = "false"
$env:MANAGEMENT_HEALTH_REDIS_ENABLED = "false"

if ($Mode -eq "mq") {
    Write-Host "Starting RocketMQ for the local async lab..." -ForegroundColor Cyan
	$previousErrorPreference = $ErrorActionPreference
	$ErrorActionPreference = "SilentlyContinue"
    docker info *> $null
	$dockerExitCode = $LASTEXITCODE
	$ErrorActionPreference = $previousErrorPreference
	if ($dockerExitCode -ne 0) {
        throw "Docker Desktop is not running. Start Docker Desktop, then retry -Mode mq."
    }
    docker compose --profile mq up -d rocketmq-namesrv rocketmq-broker
    if ($LASTEXITCODE -ne 0) {
        throw "RocketMQ containers failed to start. Run 'docker compose --profile mq logs rocketmq-broker'."
    }
}

Write-Host "Async lab mode: $Mode; mock delay: ${MockDelayMs}ms; quota: disabled" -ForegroundColor Green
Write-Host "Open http://localhost:8081, login, then use the Async Lab panel. Press Ctrl+C to stop." -ForegroundColor Green
mvn spring-boot:run "-Dspring-boot.run.profiles=h2"
