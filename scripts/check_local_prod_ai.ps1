[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$EnvFile
)

$ErrorActionPreference = "Stop"

function Read-DotEnv([string]$Path) {
    $values = @{}
    foreach ($rawLine in (Get-Content -LiteralPath $Path)) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { continue }
        $separator = $line.IndexOf("=")
        $values[$line.Substring(0, $separator).Trim()] = $line.Substring($separator + 1).Trim().Trim('"').Trim("'")
    }
    return $values
}

function Test-ConfiguredValue([hashtable]$Values, [string]$Name) {
    $value = if ($Values.ContainsKey($Name)) { [string]$Values[$Name] } else { "" }
    return -not [string]::IsNullOrWhiteSpace($value) -and $value -notmatch "CHANGE_ME|your-|example\.com"
}

function Add-Check([bool]$Passed, [string]$Name, [string]$Detail) {
    $level = if ($Passed) { "PASS" } else { "FAIL" }
    Write-Host "[$level] $Name - $Detail"
    if (-not $Passed) { $script:failures += 1 }
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    Write-Host "[FAIL] environment file - not found: $EnvFile"
    exit 1
}

$values = Read-DotEnv $EnvFile
$failures = 0

Add-Check (Test-ConfiguredValue $values "LOCAL_PROD_MODEL_EGRESS_ALLOWED_TENANTS") `
    "model data egress allowlist" "at least one approved tenant id must be configured"

$transcriptEnabled = $values["LOCAL_PROD_TRANSCRIPT_ENABLED"] -eq "true"
Add-Check $transcriptEnabled "real transcription" "LOCAL_PROD_TRANSCRIPT_ENABLED must be true"
Add-Check (Test-ConfiguredValue $values "LOCAL_PROD_WHISPER_API_BASE_URL") "transcription endpoint" "configured without printing credentials"
Add-Check (Test-ConfiguredValue $values "LOCAL_PROD_WHISPER_API_KEY") "transcription credential" "configured without printing credentials"
Add-Check (Test-ConfiguredValue $values "LOCAL_PROD_WHISPER_MODEL") "transcription model" "configured"

$summaryEnabled = $values["LOCAL_PROD_SUMMARY_ENABLED"] -eq "true"
Add-Check $summaryEnabled "real media summary" "LOCAL_PROD_SUMMARY_ENABLED must be true"
Add-Check (Test-ConfiguredValue $values "LOCAL_PROD_SUMMARY_API_BASE_URL") "summary endpoint" "configured without printing credentials"
Add-Check (Test-ConfiguredValue $values "LOCAL_PROD_SUMMARY_API_KEY") "summary credential" "configured without printing credentials"
Add-Check (Test-ConfiguredValue $values "LOCAL_PROD_SUMMARY_MODEL") "summary model" "configured"

$answerMode = $values["LOCAL_PROD_DEFAULT_ANSWER_MODE"]
Add-Check ($answerMode -in @("api", "auto")) "Agent answer mode" "must be api or auto"
$provider = $values["LOCAL_PROD_LLM_PROVIDER"]
Add-Check ($provider -in @("deepseek", "openai")) "Agent model provider" "must be deepseek or openai"
if ($provider -eq "openai") {
    Add-Check (Test-ConfiguredValue $values "LOCAL_PROD_OPENAI_BASE_URL") "Agent model endpoint" "configured without printing credentials"
    Add-Check (Test-ConfiguredValue $values "LOCAL_PROD_OPENAI_API_KEY") "Agent model credential" "configured without printing credentials"
    Add-Check (Test-ConfiguredValue $values "LOCAL_PROD_OPENAI_MODEL") "Agent model" "configured"
} elseif ($provider -eq "deepseek") {
    Add-Check (Test-ConfiguredValue $values "LOCAL_PROD_DEEPSEEK_BASE_URL") "Agent model endpoint" "configured without printing credentials"
    Add-Check (Test-ConfiguredValue $values "LOCAL_PROD_DEEPSEEK_API_KEY") "Agent model credential" "configured without printing credentials"
    Add-Check (Test-ConfiguredValue $values "LOCAL_PROD_DEEPSEEK_MODEL") "Agent model" "configured"
}

Write-Host "Real AI readiness summary: failures=$failures"
if ($failures -gt 0) { exit 1 }
Write-Host "Real AI configuration is complete. Run provider smoke tests before making a production claim."
