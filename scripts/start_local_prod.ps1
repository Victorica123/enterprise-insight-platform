[CmdletBinding()]
param(
    [int]$Port = 18080,
    [switch]$Build,
    [switch]$Faults,
    [switch]$Observability,
    [switch]$RequireRealAi
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeDir = Join-Path $projectRoot "runtime\local-prod"
$envFile = Join-Path $runtimeDir ".env"
$keyDir = Join-Path $runtimeDir "keys"

function New-HexSecret([int]$Bytes) {
    $buffer = [byte[]]::new($Bytes)
    [Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return [Convert]::ToHexString($buffer).ToLowerInvariant()
}

function Add-EnvSecretIfMissing([string]$Name, [int]$Bytes) {
    $existing = if (Test-Path -LiteralPath $envFile) { Get-Content -LiteralPath $envFile -Raw } else { "" }
    if ($existing -notmatch "(?m)^$([Regex]::Escape($Name))=") {
        [IO.File]::AppendAllLines($envFile, @("$Name=$(New-HexSecret $Bytes)"), [Text.UTF8Encoding]::new($false))
    }
}

function ConvertTo-Pem([string]$Label, [byte[]]$Bytes) {
    $body = [Convert]::ToBase64String($Bytes, [Base64FormattingOptions]::InsertLineBreaks)
    return "-----BEGIN $Label-----`n$body`n-----END $Label-----`n"
}

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $runtimeDir "agent") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $runtimeDir "media\storage") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $runtimeDir "diagnostics") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $runtimeDir "results") | Out-Null
New-Item -ItemType Directory -Force -Path $keyDir | Out-Null

if (-not (Test-Path -LiteralPath $envFile)) {
    $lines = @(
        "LOCAL_PROD_JWT_SECRET=$(New-HexSecret 48)",
        "LOCAL_PROD_MEDIA_SERVICE_TOKEN=$(New-HexSecret 32)",
        "LOCAL_PROD_MYSQL_ROOT_PASSWORD=$(New-HexSecret 24)",
        "LOCAL_PROD_MYSQL_PASSWORD=$(New-HexSecret 24)",
        "LOCAL_PROD_MINIO_ACCESS_KEY=localprod$(New-HexSecret 8)",
        "LOCAL_PROD_MINIO_SECRET_KEY=$(New-HexSecret 32)",
        "LOCAL_PROD_GRAFANA_PASSWORD=$(New-HexSecret 16)",
        "LOCAL_PROD_KEYCLOAK_ADMIN_PASSWORD=$(New-HexSecret 24)"
    )
    [IO.File]::WriteAllLines($envFile, $lines, [Text.UTF8Encoding]::new($false))
    Write-Host "Generated local-only secrets at $envFile"
}

# Existing local-prod environments receive newly introduced secrets without rotating prior values.
Add-EnvSecretIfMissing -Name "LOCAL_PROD_KEYCLOAK_ADMIN_PASSWORD" -Bytes 24

$privateKeyPath = Join-Path $keyDir "platform-private.pem"
$publicKeyPath = Join-Path $keyDir "platform-public.pem"
if (-not (Test-Path -LiteralPath $privateKeyPath) -or -not (Test-Path -LiteralPath $publicKeyPath)) {
    $rsa = [Security.Cryptography.RSA]::Create(2048)
    try {
        [IO.File]::WriteAllText(
            $privateKeyPath,
            (ConvertTo-Pem -Label "PRIVATE KEY" -Bytes $rsa.ExportPkcs8PrivateKey()),
            [Text.UTF8Encoding]::new($false)
        )
        [IO.File]::WriteAllText(
            $publicKeyPath,
            (ConvertTo-Pem -Label "PUBLIC KEY" -Bytes $rsa.ExportSubjectPublicKeyInfo()),
            [Text.UTF8Encoding]::new($false)
        )
    } finally {
        $rsa.Dispose()
    }
    Write-Host "Generated local-only RS256 signing keys in $keyDir"
}

if ($RequireRealAi) {
    & (Join-Path $PSScriptRoot "check_local_prod_ai.ps1") -EnvFile $envFile
    if ($LASTEXITCODE -ne 0) { throw "Real AI readiness validation failed." }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Engine with Compose v2 is required for the local production-like stack."
}

$env:LOCAL_PROD_WEB_PORT = [string]$Port
$arguments = @("compose", "--env-file", $envFile, "-f", (Join-Path $projectRoot "compose.local-prod.yml"))
if ($Faults) {
    $arguments += @("-f", (Join-Path $projectRoot "compose.local-prod.faults.yml"))
}
if ($Observability) {
    $arguments += @("--profile", "observability")
}
$arguments += @("up", "-d")
if ($Build) { $arguments += "--build" }

& docker @arguments
if ($LASTEXITCODE -ne 0) { throw "Local production-like stack startup failed." }

Write-Host "Production-like localhost stack is starting at http://127.0.0.1:$Port"
Write-Host "Media: http://127.0.0.1:18081  Agent: http://127.0.0.1:18000"
Write-Host "Identity: http://127.0.0.1:18082 (Keycloak; admin password is stored in the local runtime env file)"
Write-Host "AI mode: $(if ($RequireRealAi) { 'real-provider-required' } else { 'mock/local allowed' })"
if ($Observability) {
    Write-Host "Prometheus: http://127.0.0.1:19090  Grafana: http://127.0.0.1:13000"
}
