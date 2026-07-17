param(
    [string]$Agent = "unknown",
    [string]$Summary = "",
    [string]$Next = "",
    [string]$Tests = "",
    [string]$Risks = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$handoffPath = Join-Path $repoRoot "docs\AI_HANDOFF.md"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"

function Get-CommandOutput {
    param([string]$Command)
    try {
        $output = Invoke-Expression $Command 2>&1
        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
            return ($output | Out-String).Trim()
        }
        return ($output | Out-String).Trim()
    } catch {
        return $_.Exception.Message
    }
}

$gitBranch = Get-CommandOutput "git branch --show-current"
$gitStatus = Get-CommandOutput "git status --short"
if ([string]::IsNullOrWhiteSpace($gitStatus)) {
    $gitStatus = "(clean)"
}

$recentCommit = Get-CommandOutput "git log -1 --oneline"
$changedFiles = Get-CommandOutput "git diff --name-only"
if ([string]::IsNullOrWhiteSpace($changedFiles)) {
    $changedFiles = "(none)"
}

$existingNotes = ""
if (Test-Path -LiteralPath $handoffPath) {
    $content = Get-Content -LiteralPath $handoffPath -Raw -Encoding UTF8
    $marker = "## Handoff Log"
    $idx = $content.IndexOf($marker)
    if ($idx -ge 0) {
        $existingNotes = $content.Substring($idx + $marker.Length).Trim()
    }
}

$doc = @"
# AI Handoff

This is the shared handoff entrypoint for Codex, Claude, and future AI agents working on this repository.
Read this after `AGENTS.md` or `CLAUDE.md`, then open only the referenced docs needed for the current task.

## Current Product Goal

Help real users upload videos, wait for processing, receive transcript/summary results, play back videos when needed, and manage their history. Performance, MQ, Redis, observability, and deployment work should serve that user workflow.

## Canonical Context

- `docs/PROJECT_KNOWLEDGE.md` - navigation map and current product priorities.
- `CLAUDE.md` - most complete architecture notes as of 2026-07-02, including MD5 resume/dedup, Range playback, content-level single-flight, metrics, and load testing.
- `AGENTS.md` - Codex working rules. Keep it aligned with `CLAUDE.md` when architecture changes.
- `docs/TROUBLESHOOTING.md` - real engineering problem cards. Add new issues with `Symptom`, `Cause`, `Fix`, `Verify yourself`, and `Interview point`.
- `docs/LOADTEST.md` - MQ on/off A/B load-test method and measured results.
- `INTERVIEW_GUIDE.md` - interview-facing feature and architecture summary.

## Shared Rules

- Treat existing uncommitted changes as user-owned unless you made them.
- Preserve owner isolation on upload, playback, crawl, and workflow records.
- Keep tests independent from Redis, RocketMQ, Docker, FFmpeg, Whisper, and LLM APIs.
- Prefer small, verifiable progress over broad rewrites.
- When a task changes architecture, update both the code and this handoff entrypoint.
- For user-facing failure modes, prefer precise `4xx` errors for client-correctable problems and generic `5xx` for internal faults.

## Quick State

- Generated at: $timestamp
- Last agent: $Agent
- Branch: $gitBranch
- Last commit: $recentCommit
- Working tree:

```text
$gitStatus
```

- Changed files:

```text
$changedFiles
```

## Latest Session Summary

$Summary

## Verification

$Tests

## Known Risks / Watch Items

$Risks

## Recommended Next Step

$Next

## Handoff Log

"@

if (-not [string]::IsNullOrWhiteSpace($existingNotes)) {
    $doc += $existingNotes + "`r`n"
}

Set-Content -LiteralPath $handoffPath -Value $doc -Encoding UTF8
Write-Host "Updated $handoffPath"
