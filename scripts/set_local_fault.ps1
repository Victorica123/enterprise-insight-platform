[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("mysql", "redis", "minio", "agent")]
    [string]$Target,
    [Parameter(Mandatory = $true)]
    [ValidateSet("latency", "down", "reset")]
    [string]$Mode,
    [int]$LatencyMs = 1500,
    [int]$JitterMs = 250
)

$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:18474/proxies/$Target"

if ($Mode -eq "reset") {
    try { Invoke-RestMethod -Method Delete -Uri "$base/toxics/latency" | Out-Null } catch { }
    Invoke-RestMethod -Method Post -Uri $base -ContentType "application/json" -Body '{"enabled":true}' | Out-Null
    Write-Host "$Target fault reset."
    exit 0
}

if ($Mode -eq "down") {
    Invoke-RestMethod -Method Post -Uri $base -ContentType "application/json" -Body '{"enabled":false}' | Out-Null
    Write-Host "$Target proxy disabled. Run with -Mode reset to recover it."
    exit 0
}

Invoke-RestMethod -Method Post -Uri $base -ContentType "application/json" -Body '{"enabled":true}' | Out-Null
try { Invoke-RestMethod -Method Delete -Uri "$base/toxics/latency" | Out-Null } catch { }
$payload = @{
    name = "latency"
    type = "latency"
    stream = "downstream"
    toxicity = 1.0
    attributes = @{ latency = $LatencyMs; jitter = $JitterMs }
} | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post -Uri "$base/toxics" -ContentType "application/json" -Body $payload | Out-Null
Write-Host "$Target downstream latency set to ${LatencyMs}ms (+/- ${JitterMs}ms)."
