param(
    [string]$BaseUrl = "http://localhost:8081",
    [string]$ComposeFile = "docker-compose.prod.yml",
    [string]$EnvFile = ".env",
    [switch]$SkipDocker,
    [int]$WaitSeconds = 90
)

$ErrorActionPreference = "Stop"

function Add-Step($Name, $Ok, $Detail) {
    $script:steps += [pscustomobject]@{
        name = $Name
        ok = [bool]$Ok
        detail = $Detail
    }
    if ($Ok) {
        Write-Host "[OK] $Name - $Detail"
    } else {
        Write-Host "[FAIL] $Name - $Detail"
    }
}

function Invoke-JsonPost($Uri, $Body, $Token = $null) {
    $headers = @{}
    if ($Token) {
        $headers.Authorization = "Bearer $Token"
    }
    Invoke-RestMethod -Method Post -Uri $Uri -Headers $headers -ContentType "application/json" `
        -Body ($Body | ConvertTo-Json -Compress)
}

function Read-DotEnv($Path) {
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $values
    }
    foreach ($rawLine in (Get-Content -LiteralPath $Path)) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $idx = $line.IndexOf("=")
        $key = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1).Trim().Trim('"').Trim("'")
        $values[$key] = $value
    }
    return $values
}

function Env-OrDefault($Values, $Name, $Default) {
    $envValue = [Environment]::GetEnvironmentVariable($Name)
    if ($envValue) {
        return $envValue
    }
    if ($Values.ContainsKey($Name) -and -not [string]::IsNullOrWhiteSpace($Values[$Name])) {
        return $Values[$Name]
    }
    return $Default
}

function Wait-Health($Uri, $TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $health = Invoke-RestMethod -Method Get -Uri $Uri -TimeoutSec 5
            if ($health.status -eq "UP") {
                return $health
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)
    throw "Health endpoint did not become UP within ${TimeoutSeconds}s"
}

$steps = @()
$envValues = Read-DotEnv $EnvFile
$mysqlDatabase = Env-OrDefault $envValues "MYSQL_DATABASE" "videoplatform"
$mysqlUsername = Env-OrDefault $envValues "MYSQL_USERNAME" "videoplatform"
$mysqlPassword = Env-OrDefault $envValues "MYSQL_PASSWORD" ""
$bucket = Env-OrDefault $envValues "APP_STORAGE_S3_BUCKET" "video-platform"
$suffix = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$username = "deploy_verify_$suffix"
$password = "demo123456"
$filePath = Join-Path $env:TEMP "vp-deploy-$suffix.mp4"
[IO.File]::WriteAllBytes($filePath, [Text.Encoding]::UTF8.GetBytes("HELLOWORLD-DEPLOY-$suffix"))

try {
    if (-not $SkipDocker) {
        $services = docker compose -f $ComposeFile ps --format json 2>$null | ForEach-Object {
            if ($_ -and $_.Trim()) { $_ | ConvertFrom-Json }
        }
        $runningNames = @($services | ForEach-Object { $_.Name })
        Add-Step "docker compose services" ($runningNames.Count -gt 0) ($runningNames -join ", ")

        $required = @(
            "video-platform-app",
            "video-platform-mysql",
            "video-platform-redis",
            "video-platform-namesrv",
            "video-platform-broker",
            "video-platform-minio",
            "video-platform-caddy"
        )
        foreach ($name in $required) {
            $service = $services | Where-Object { $_.Name -eq $name } | Select-Object -First 1
            Add-Step "container $name" ($null -ne $service -and $service.State -eq "running") `
                ($(if ($service) { "$($service.State) $($service.Status)" } else { "missing" }))
        }
    }

    $health = Wait-Health "$BaseUrl/actuator/health" $WaitSeconds
    Add-Step "app health" ($health.status -eq "UP") $health.status

    $auth = Invoke-JsonPost "$BaseUrl/api/auth/register" @{ username = $username; password = $password }
    $token = $auth.data.token
    Add-Step "register/login token" (-not [string]::IsNullOrWhiteSpace($token)) $username

    $single = & curl.exe -sS -X POST "$BaseUrl/api/media/upload/file" `
        -H "Authorization: Bearer $token" `
        -F "file=@$filePath;type=video/mp4;filename=single-$suffix.mp4"
    $singleJson = $single | ConvertFrom-Json
    Add-Step "single upload accepted" ($singleJson.success -and $singleJson.data.taskId) $singleJson.data.taskId

    $directInit = Invoke-JsonPost "$BaseUrl/api/media/upload/direct/init" @{
        fileName = "direct-$suffix.mp4"
        fileSize = (Get-Item -LiteralPath $filePath).Length
    } $token
    Add-Step "direct upload init" ($directInit.success -and $directInit.data.uploadUrl) `
        (($directInit.data.uploadUrl -split "\?")[0])

    & curl.exe -sS -f -X PUT $directInit.data.uploadUrl `
        -H "Content-Type: video/mp4" `
        --data-binary "@$filePath" | Out-Null
    Add-Step "minio presigned PUT" $true "uploaded bytes=$((Get-Item -LiteralPath $filePath).Length)"

    $directComplete = Invoke-JsonPost "$BaseUrl/api/media/upload/direct/complete" @{
        uploadToken = $directInit.data.uploadToken
    } $token
    $taskId = $directComplete.data.taskId
    Add-Step "direct upload complete" ($directComplete.success -and $taskId) $taskId

    $task = $null
    for ($i = 0; $i -lt 80; $i++) {
        Start-Sleep -Milliseconds 500
        $taskResp = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/workflow/tasks/$taskId" `
            -Headers @{ Authorization = "Bearer $token" }
        $task = $taskResp.data
        if ($task.status -eq "COMPLETED" -or $task.status -eq "FAILED") {
            break
        }
    }
    Add-Step "workflow completed" ($task.status -eq "COMPLETED") "taskId=$taskId status=$($task.status)"

    if (-not $SkipDocker) {
        $mysqlCheck = docker compose -f $ComposeFile exec -T mysql mysql -u"$mysqlUsername" `
            "-p$mysqlPassword" -N -e "SELECT COUNT(*) FROM $mysqlDatabase.video_task WHERE task_id='$taskId';"
        Add-Step "mysql task persisted" (($mysqlCheck | Select-Object -First 1) -eq "1") "rows=$mysqlCheck"

        $redisPing = docker compose -f $ComposeFile exec -T redis redis-cli PING
        Add-Step "redis ping" ($redisPing -eq "PONG") $redisPing

        $minioLs = docker compose -f $ComposeFile exec -T minio sh -c "ls /data/$bucket >/dev/null && echo OK"
        Add-Step "minio bucket exists" ($minioLs -eq "OK") $bucket
    }

    $ok = -not (@($steps | Where-Object { -not $_.ok }).Count)
    [pscustomobject]@{
        ok = $ok
        baseUrl = $BaseUrl
        username = $username
        directTaskId = $taskId
        finalStatus = $task.status
        steps = $steps
    } | ConvertTo-Json -Depth 6

    if (-not $ok) {
        exit 1
    }
} catch {
    Add-Step "verify-deploy exception" $false $_.Exception.Message
    [pscustomobject]@{
        ok = $false
        baseUrl = $BaseUrl
        username = $username
        steps = $steps
    } | ConvertTo-Json -Depth 6
    exit 1
} finally {
    Remove-Item -LiteralPath $filePath -ErrorAction SilentlyContinue
}
