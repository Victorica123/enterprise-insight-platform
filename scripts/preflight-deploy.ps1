param(
    [string]$EnvFile = ".env",
    [string]$ComposeFile = "docker-compose.prod.yml"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

function Resolve-ProjectPath([string]$Path) {
    if ([IO.Path]::IsPathRooted($Path)) {
        return $Path
    }
    return Join-Path $projectRoot $Path
}

function Read-DotEnv([string]$Path) {
    $values = @{}
    foreach ($rawLine in (Get-Content -LiteralPath $Path)) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $separator = $line.IndexOf("=")
        $key = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim().Trim('"').Trim("'")
        $values[$key] = $value
    }
    return $values
}

function Add-Result([string]$Level, [string]$Name, [string]$Detail) {
    $script:results.Add([pscustomobject]@{
        level = $Level
        name = $Name
        detail = $Detail
    })
    Write-Host "[$Level] $Name - $Detail"
}

function Require-Value([hashtable]$Values, [string]$Name) {
    if (-not $Values.ContainsKey($Name) -or [string]::IsNullOrWhiteSpace($Values[$Name])) {
        Add-Result "FAIL" $Name "missing or empty"
        return $false
    }
    if ($Values[$Name] -match "CHANGE_ME|example\.com") {
        Add-Result "FAIL" $Name "still contains a template value"
        return $false
    }
    Add-Result "PASS" $Name "configured"
    return $true
}

function Check-SecretLength([hashtable]$Values, [string]$Name, [int]$Minimum) {
    if (-not $Values.ContainsKey($Name) -or [string]::IsNullOrWhiteSpace($Values[$Name]) -or
            $Values[$Name] -match "CHANGE_ME|example\.com") {
        return
    }
    if ($Values[$Name].Length -ge $Minimum) {
        Add-Result "PASS" $Name "length is at least $Minimum"
    } else {
        Add-Result "FAIL" $Name "must be at least $Minimum characters"
    }
}

$results = [System.Collections.Generic.List[object]]::new()
$envPath = Resolve-ProjectPath $EnvFile
$composePath = Resolve-ProjectPath $ComposeFile

if (-not (Test-Path -LiteralPath $envPath)) {
    Add-Result "FAIL" "environment file" "not found: $envPath; copy .env.example to .env first"
    exit 1
}
if (-not (Test-Path -LiteralPath $composePath)) {
    Add-Result "FAIL" "compose file" "not found: $composePath"
    exit 1
}

$values = Read-DotEnv $envPath
$required = @(
    "PUBLIC_APP_DOMAIN",
    "PUBLIC_FILES_DOMAIN",
    "PUBLIC_APP_URL",
    "SERVER_PORT",
    "APP_JWT_SECRET",
    "MYSQL_DATABASE",
    "MYSQL_USERNAME",
    "MYSQL_PASSWORD",
    "MYSQL_ROOT_PASSWORD",
    "APP_STORAGE_S3_PUBLIC_ENDPOINT",
    "APP_STORAGE_S3_ENDPOINT",
    "APP_STORAGE_TYPE",
    "APP_STORAGE_S3_ACCESS_KEY",
    "APP_STORAGE_S3_SECRET_KEY",
    "MINIO_API_CORS_ALLOW_ORIGIN",
    "APP_REDIS_ENABLED",
    "APP_MQ_ENABLED",
    "ROCKETMQ_NAMESERVER",
    "GRAFANA_ADMIN_PASSWORD"
)
foreach ($name in $required) {
    [void](Require-Value $values $name)
}

Check-SecretLength $values "APP_JWT_SECRET" 32
Check-SecretLength $values "MYSQL_PASSWORD" 12
Check-SecretLength $values "MYSQL_ROOT_PASSWORD" 12
Check-SecretLength $values "APP_STORAGE_S3_SECRET_KEY" 12
Check-SecretLength $values "GRAFANA_ADMIN_PASSWORD" 12

$appDomain = $values["PUBLIC_APP_DOMAIN"]
$filesDomain = $values["PUBLIC_FILES_DOMAIN"]
if ($appDomain -and $appDomain -notmatch "^[a-zA-Z0-9.-]+$") {
    Add-Result "FAIL" "PUBLIC_APP_DOMAIN format" "use a hostname only, without https:// or a path"
}
if ($filesDomain -and $filesDomain -notmatch "^[a-zA-Z0-9.-]+$") {
    Add-Result "FAIL" "PUBLIC_FILES_DOMAIN format" "use a hostname only, without https:// or a path"
}
if ($appDomain -and $values["PUBLIC_APP_URL"] -eq "https://$appDomain") {
    Add-Result "PASS" "app URL mapping" "PUBLIC_APP_URL matches PUBLIC_APP_DOMAIN"
} else {
    Add-Result "FAIL" "app URL mapping" "expected PUBLIC_APP_URL=https://PUBLIC_APP_DOMAIN"
}
if ($filesDomain -and $values["APP_STORAGE_S3_PUBLIC_ENDPOINT"] -eq "https://$filesDomain") {
    Add-Result "PASS" "storage URL mapping" "public S3 endpoint matches PUBLIC_FILES_DOMAIN"
} else {
    Add-Result "FAIL" "storage URL mapping" "expected APP_STORAGE_S3_PUBLIC_ENDPOINT=https://PUBLIC_FILES_DOMAIN"
}
if ($appDomain -and $values["MINIO_API_CORS_ALLOW_ORIGIN"] -eq "https://$appDomain") {
    Add-Result "PASS" "MinIO CORS" "origin matches the app domain"
} else {
    Add-Result "FAIL" "MinIO CORS" "expected MINIO_API_CORS_ALLOW_ORIGIN=https://PUBLIC_APP_DOMAIN"
}

$fixedValues = @{
    SERVER_PORT = "8081"
    APP_STORAGE_TYPE = "s3"
    APP_STORAGE_S3_ENDPOINT = "http://minio:9000"
    APP_REDIS_ENABLED = "true"
    APP_MQ_ENABLED = "true"
    ROCKETMQ_NAMESERVER = "rocketmq-namesrv:9876"
}
foreach ($entry in $fixedValues.GetEnumerator()) {
    if ($values[$entry.Key] -eq $entry.Value) {
        Add-Result "PASS" $entry.Key "production value is correct"
    } else {
        Add-Result "FAIL" $entry.Key "expected $($entry.Value) for this Compose deployment"
    }
}

if ($values["APP_TRANSCRIPT_ENABLED"] -eq "true") {
    if ([string]::IsNullOrWhiteSpace($values["WHISPER_API_KEY"])) {
        Add-Result "FAIL" "Whisper API" "transcription is enabled but WHISPER_API_KEY is empty"
    } else {
        Add-Result "PASS" "Whisper API" "enabled and key is present"
    }
} else {
    Add-Result "WARN" "Whisper API" "disabled; first deployment will use mock transcription"
}
if ($values["APP_SUMMARY_ENABLED"] -eq "true") {
    if ([string]::IsNullOrWhiteSpace($values["LLM_API_KEY"])) {
        Add-Result "FAIL" "LLM API" "summary is enabled but LLM_API_KEY is empty"
    } else {
        Add-Result "PASS" "LLM API" "enabled and key is present"
    }
} else {
    Add-Result "WARN" "LLM API" "disabled; first deployment will use mock summary"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Add-Result "FAIL" "Docker CLI" "docker command not found"
} else {
    Add-Result "PASS" "Docker CLI" "installed"
    try {
        $serverVersion = (& docker info --format '{{.ServerVersion}}' 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and $serverVersion) {
            Add-Result "PASS" "Docker daemon" "running, server version $serverVersion"
        } else {
            Add-Result "FAIL" "Docker daemon" "not reachable"
        }
    } catch {
        Add-Result "FAIL" "Docker daemon" "not reachable"
    }

    $oldEnvFile = [Environment]::GetEnvironmentVariable("ENV_FILE")
    try {
        $env:ENV_FILE = $envPath
        & docker compose --env-file $envPath -f $composePath config --quiet
        if ($LASTEXITCODE -eq 0) {
            Add-Result "PASS" "Compose configuration" "valid"
        } else {
            Add-Result "FAIL" "Compose configuration" "docker compose config failed"
        }
    } finally {
        if ($null -eq $oldEnvFile) {
            Remove-Item Env:ENV_FILE -ErrorAction SilentlyContinue
        } else {
            $env:ENV_FILE = $oldEnvFile
        }
    }
}

if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    foreach ($port in 80, 443) {
        $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($listener) {
            Add-Result "WARN" "port $port" "already in use; stop the existing web server or reuse it intentionally"
        } else {
            Add-Result "PASS" "port $port" "available"
        }
    }
}

$failures = @($results | Where-Object { $_.level -eq "FAIL" }).Count
$warnings = @($results | Where-Object { $_.level -eq "WARN" }).Count
Write-Host ""
Write-Host "Preflight summary: failures=$failures warnings=$warnings"
if ($failures -gt 0) {
    Write-Host "Fix every FAIL item before running the production stack."
    exit 1
}
Write-Host "Preflight passed. You can run: docker compose -f docker-compose.prod.yml up -d --build"
