param(
    [string]$Profile = "",
    [int]$Port = 8081,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "logs"
$JarPath = Join-Path $Root "target\video-platform-0.0.1-SNAPSHOT.jar"
$OutLog = Join-Path $LogDir "video-platform.out.log"
$ErrLog = Join-Path $LogDir "video-platform.err.log"
$BuildLog = Join-Path $LogDir "video-platform.build.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Stop-PortOwner {
    param([int]$ListenPort)

    $lines = netstat -ano | Select-String ":$ListenPort\s+.*LISTENING"
    foreach ($line in $lines) {
        $parts = ($line.ToString() -split "\s+") | Where-Object { $_ }
        $processId = [int]$parts[-1]
        if ($processId -gt 0) {
            Write-Host "Stopping existing process on port $ListenPort, PID=$processId"
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Wait-Health {
    param([int]$ListenPort)

    $healthUrl = "http://localhost:$ListenPort/actuator/health"
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Write-Host "Video service is ready: http://localhost:$ListenPort"
                return
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    throw "Video service did not become healthy within 60 seconds. Check logs/video-platform.err.log and logs/video-platform.out.log."
}

Set-Location -LiteralPath $Root
Stop-PortOwner -ListenPort $Port

if (-not $SkipBuild) {
    Write-Host "Building jar..."
    & mvn clean package -DskipTests *> $BuildLog
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed. Check $BuildLog"
    }
}

if (-not (Test-Path -LiteralPath $JarPath)) {
    throw "Jar not found: $JarPath"
}

Remove-Item -LiteralPath $OutLog, $ErrLog -Force -ErrorAction SilentlyContinue

$javaArgs = "-jar `"$JarPath`""
if ($Profile -and $Profile.Trim()) {
    $javaArgs += " --spring.profiles.active=$Profile"
}

Write-Host "Starting video service..."
$process = Start-Process -FilePath "java" `
    -ArgumentList $javaArgs `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Started PID=$($process.Id)"
Wait-Health -ListenPort $Port
