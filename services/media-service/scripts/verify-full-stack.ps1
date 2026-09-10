param(
    [string]$BaseUrl = "http://localhost:8081",
    [string]$MysqlContainer = "video-platform-mysql",
    [string]$RedisContainer = "video-platform-redis",
    [string]$MysqlPassword = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($MysqlPassword)) {
    throw "Pass -MysqlPassword explicitly; do not rely on a committed database password."
}

function Invoke-JsonPost($Uri, $Body, $Token = $null) {
    $headers = @{}
    if ($Token) {
        $headers.Authorization = "Bearer $Token"
    }
    Invoke-RestMethod -Method Post -Uri $Uri -Headers $headers -ContentType "application/json" `
        -Body ($Body | ConvertTo-Json -Compress)
}

$suffix = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$username = "verify_full_$suffix"
$password = "demo123456"

Write-Host "1. Registering test user $username"
$auth = Invoke-JsonPost "$BaseUrl/api/auth/register" @{ username = $username; password = $password }
$token = $auth.data.token
if (-not $token) {
    throw "Register did not return a JWT token"
}

Write-Host "2. Checking Redis and MySQL containers"
$redisPing = docker exec $RedisContainer redis-cli -p 6379 PING
if ($redisPing -ne "PONG") {
    throw "Redis PING failed: $redisPing"
}
$mysqlPing = docker exec $MysqlContainer mysql -uroot "--password=$MysqlPassword" -N -e "SELECT 1;"
if (($mysqlPing | Select-Object -First 1) -ne "1") {
    throw "MySQL SELECT 1 failed: $mysqlPing"
}

Write-Host "3. Uploading a two-chunk video through Redis chunk APIs"
$full = Join-Path $env:TEMP "vp-full-$suffix.mp4"
$chunk0 = Join-Path $env:TEMP "vp-full-$suffix.part0"
$chunk1 = Join-Path $env:TEMP "vp-full-$suffix.part1"
[byte[]]$mp4Header = @(0, 0, 0, 24, 0x66, 0x74, 0x79, 0x70, 0x69, 0x73, 0x6f, 0x6d)
[byte[]]$bytes = $mp4Header + [Text.Encoding]::UTF8.GetBytes("HELLOWORLD-MYSQL-REDIS-MQ-$suffix")
[IO.File]::WriteAllBytes($full, $bytes)
[IO.File]::WriteAllBytes($chunk0, $bytes[0..9])
[IO.File]::WriteAllBytes($chunk1, $bytes[10..($bytes.Length - 1)])
$md5 = (Get-FileHash -Algorithm MD5 -LiteralPath $full).Hash.ToLowerInvariant()

$init = Invoke-JsonPost "$BaseUrl/api/media/upload/init" @{
    fileName = "full-$suffix.mp4"
    fileSize = $bytes.Length
    totalChunks = 2
    chunkSize = 10
    fileMd5 = $md5
} $token
$uploadId = $init.data.uploadId
if (-not $uploadId) {
    throw "Init upload did not return uploadId"
}

& curl.exe -sS -f -X POST "$BaseUrl/api/media/upload/chunk?uploadId=$uploadId&chunkIndex=0" `
    -H "Authorization: Bearer $token" -F "file=@$chunk0;type=video/mp4" | Out-Null
$statusAfterOne = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/media/upload/status?uploadId=$uploadId" `
    -Headers @{ Authorization = "Bearer $token" }
if (-not ($statusAfterOne.data.uploadedChunks -contains 0)) {
    throw "Redis upload status did not report chunk 0"
}

& curl.exe -sS -f -X POST "$BaseUrl/api/media/upload/chunk?uploadId=$uploadId&chunkIndex=1" `
    -H "Authorization: Bearer $token" -F "file=@$chunk1;type=video/mp4" | Out-Null
$merge = Invoke-JsonPost "$BaseUrl/api/media/upload/merge" @{ uploadId = $uploadId } $token
$taskId = $merge.data.taskId
if (-not $taskId) {
    throw "Merge did not return taskId"
}

Write-Host "4. Waiting for RocketMQ workflow completion"
$task = $null
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    $taskResp = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/workflow/tasks/$taskId" `
        -Headers @{ Authorization = "Bearer $token" }
    $task = $taskResp.data
    if ($task.status -eq "COMPLETED" -or $task.status -eq "FAILED") {
        break
    }
}
if ($task.status -ne "COMPLETED") {
    throw "Task did not complete. taskId=$taskId status=$($task.status) error=$($task.errorMessage)"
}

Write-Host "5. Checking persisted MySQL row"
$dbRow = docker exec $MysqlContainer mysql -uroot "--password=$MysqlPassword" -N -e `
    "SELECT status, owner, file_name FROM videoplatform.video_task WHERE task_id='$taskId';"
if (-not ($dbRow -match "COMPLETED\s+$username\s+full-$suffix\.mp4")) {
    throw "MySQL row check failed: $dbRow"
}

$leftoverKeys = docker exec $RedisContainer redis-cli -p 6379 --raw KEYS "upload:*$uploadId*"

[pscustomobject]@{
    ok = $true
    username = $username
    uploadId = $uploadId
    taskId = $taskId
    apiTaskStatus = $task.status
    hasTranscript = [bool]$task.transcript
    hasSummary = [bool]$task.summary
    mysqlRow = $dbRow
    redisUploadKeysAfterMerge = @($leftoverKeys | Where-Object { $_ }).Count
} | ConvertTo-Json -Compress
