param(
    [string]$BaseUrl = "http://localhost:8081"
)

$ErrorActionPreference = "Stop"

function Invoke-JsonPost {
    param(
        [string]$Path,
        [hashtable]$Body,
        [hashtable]$Headers = @{}
    )

    Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl$Path" `
        -ContentType "application/json" `
        -Headers $Headers `
        -Body ($Body | ConvertTo-Json)
}

$health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/actuator/health"
if ($health.status -ne "UP") {
    throw "Health check failed: $($health | ConvertTo-Json -Compress)"
}

$suffix = [guid]::NewGuid().ToString("N").Substring(0, 8)
$username = "smoke_$suffix"
$password = "Pass12345"
$credentials = @{ username = $username; password = $password }

$register = Invoke-JsonPost -Path "/api/auth/register" -Body $credentials
if (-not $register.success) {
    throw "Register failed: $($register | ConvertTo-Json -Compress)"
}

$login = Invoke-JsonPost -Path "/api/auth/login" -Body $credentials
if (-not $login.success -or -not $login.data.token) {
    throw "Login failed: $($login | ConvertTo-Json -Compress)"
}

$headers = @{ Authorization = "Bearer $($login.data.token)" }

$videoPath = Join-Path $env:TEMP "video-platform-smoke.mp4"
[System.IO.File]::WriteAllBytes($videoPath, [byte[]](
    0, 0, 0, 24, 102, 116, 121, 112, 105, 115, 111, 109, 0, 0, 2, 0,
    105, 115, 111, 109, 105, 115, 111, 50, 97, 118, 99, 49, 109, 112, 52, 49
))

$upload = & curl.exe -s -X POST "$BaseUrl/api/media/upload/file" `
    -H "Authorization: Bearer $($login.data.token)" `
    -F "file=@$videoPath;type=video/mp4;filename=smoke.mp4"

$uploadJson = $upload | ConvertFrom-Json
if (-not $uploadJson.success -or -not $uploadJson.data.taskId) {
    throw "Upload failed: $upload"
}

$tasks = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/workflow/tasks" -Headers $headers
if (-not $tasks.success) {
    throw "Task list failed: $($tasks | ConvertTo-Json -Compress)"
}

$createdTask = @($tasks.data) | Where-Object { $_.taskId -eq $uploadJson.data.taskId } | Select-Object -First 1
if (-not $createdTask) {
    throw "Uploaded task was not returned by task list. taskId=$($uploadJson.data.taskId)"
}

$videoBytes = [System.IO.File]::ReadAllBytes($videoPath)
$init = Invoke-JsonPost -Path "/api/media/upload/init" -Headers $headers -Body @{
    fileName = "chunk-smoke.mp4"
    fileSize = $videoBytes.Length
    totalChunks = 1
    chunkSize = $videoBytes.Length
    fileMd5 = ""
}
if (-not $init.success -or -not $init.data.uploadId) {
    throw "Chunk init failed: $($init | ConvertTo-Json -Compress)"
}

$chunkUpload = & curl.exe -s -X POST "$BaseUrl/api/media/upload/chunk?uploadId=$($init.data.uploadId)&chunkIndex=0" `
    -H "Authorization: Bearer $($login.data.token)" `
    -F "file=@$videoPath;type=application/octet-stream;filename=0.part"

$chunkUploadJson = $chunkUpload | ConvertFrom-Json
if (-not $chunkUploadJson.success -or $chunkUploadJson.data.uploadedChunks -ne 1) {
    throw "Chunk upload failed: $chunkUpload"
}

$merge = Invoke-JsonPost -Path "/api/media/upload/merge" -Headers $headers -Body @{
    uploadId = $init.data.uploadId
}
if (-not $merge.success -or -not $merge.data.taskId) {
    throw "Chunk merge failed: $($merge | ConvertTo-Json -Compress)"
}

$tasksAfterMerge = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/workflow/tasks" -Headers $headers
$mergedTask = @($tasksAfterMerge.data) | Where-Object { $_.taskId -eq $merge.data.taskId } | Select-Object -First 1
if (-not $mergedTask) {
    throw "Merged task was not returned by task list. taskId=$($merge.data.taskId)"
}

# ---- Multi-chunk scenario: split the payload into 2 parts to exercise chunk assembly/ordering ----
$half = [int]($videoBytes.Length / 2)
$part0 = Join-Path $env:TEMP "video-platform-smoke-0.part"
$part1 = Join-Path $env:TEMP "video-platform-smoke-1.part"
[System.IO.File]::WriteAllBytes($part0, $videoBytes[0..($half - 1)])
[System.IO.File]::WriteAllBytes($part1, $videoBytes[$half..($videoBytes.Length - 1)])

$multiInit = Invoke-JsonPost -Path "/api/media/upload/init" -Headers $headers -Body @{
    fileName = "multi-chunk-smoke.mp4"
    fileSize = $videoBytes.Length
    totalChunks = 2
    chunkSize = $half
    fileMd5 = ""
}
if (-not $multiInit.success -or -not $multiInit.data.uploadId) {
    throw "Multi-chunk init failed: $($multiInit | ConvertTo-Json -Compress)"
}

foreach ($idx in 0, 1) {
    $partPath = if ($idx -eq 0) { $part0 } else { $part1 }
    $partResp = & curl.exe -s -X POST "$BaseUrl/api/media/upload/chunk?uploadId=$($multiInit.data.uploadId)&chunkIndex=$idx" `
        -H "Authorization: Bearer $($login.data.token)" `
        -F "file=@$partPath;type=application/octet-stream;filename=$idx.part"
    $partJson = $partResp | ConvertFrom-Json
    if (-not $partJson.success -or $partJson.data.uploadedChunks -ne ($idx + 1)) {
        throw "Multi-chunk upload failed at index ${idx}: $partResp"
    }
}

$multiMerge = Invoke-JsonPost -Path "/api/media/upload/merge" -Headers $headers -Body @{
    uploadId = $multiInit.data.uploadId
}
if (-not $multiMerge.success -or -not $multiMerge.data.taskId) {
    throw "Multi-chunk merge failed: $($multiMerge | ConvertTo-Json -Compress)"
}

Write-Host "Smoke test passed"
Write-Host "User: $username"
Write-Host "Single upload task: $($uploadJson.data.taskId)"
Write-Host "Chunk upload task (1 chunk): $($merge.data.taskId)"
Write-Host "Chunk upload task (2 chunks): $($multiMerge.data.taskId)"
Write-Host "Status: $($createdTask.status)"
