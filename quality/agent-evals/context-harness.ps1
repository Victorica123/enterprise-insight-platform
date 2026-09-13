param(
    [ValidateSet("brief", "files", "verify")]
    [string]$Mode = "brief"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Assert-LastExitCode {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

function Show-ImportantFiles {
    rg --files services/agent-service/app services/agent-service/tests apps/web/src `
        contracts scripts quality knowledge docs skills `
        -g "!docs/archive/**" -g "!knowledge/generated/SEMANTIC_INDEX.json" `
        -g "!**/__pycache__/**" -g "!*.tsbuildinfo"
    Assert-LastExitCode "File inventory"
}

function Show-Brief {
    Get-Content -LiteralPath "knowledge/INDEX.md" -Encoding UTF8
    Write-Output "Next: docs/START_HERE.md; current task plan; latest knowledge/QUALITY.md evidence."
    git status --short
    Assert-LastExitCode "Working tree status"
    git log -3 --oneline
    Assert-LastExitCode "Recent commits"
}

function Run-Verify {
    $Python = Join-Path $Root ".venv/Scripts/python.exe"
    if (-not (Test-Path -LiteralPath $Python)) {
        $Python = (Get-Command python -ErrorAction Stop).Source
    }
    $Overrides = @{
        LLM_ROUTER_ENABLED = "0"
        EMBEDDING_MODEL = ""
        RERANKER_MODEL = ""
        AGENT_DATABASE_URL = ""
        APP_ENV = "test"
    }
    $Previous = @{}
    foreach ($Name in $Overrides.Keys) {
        $Previous[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
        [Environment]::SetEnvironmentVariable($Name, $Overrides[$Name], "Process")
    }
    try {
        if (Get-Command uvx -ErrorAction SilentlyContinue) {
            uvx ruff@0.16.6 check --config ruff.toml services/agent-service scripts quality
        } else {
            & $Python -m ruff check --config ruff.toml services/agent-service scripts quality
        }
        Assert-LastExitCode "Python lint"
        Push-Location services/agent-service
        try {
            & $Python -X utf8 -m unittest discover -s tests -q
            Assert-LastExitCode "Agent tests"
        } finally { Pop-Location }
        foreach ($Gate in @("v6", "prd", "knowledge_lifecycle", "conversation", "v5")) {
            & $Python -X utf8 "quality/agent-evals/evaluate_$Gate.py"
            Assert-LastExitCode "Agent $Gate evaluation"
        }
        & $Python -X utf8 -m unittest discover -s scripts/tests -q
        Assert-LastExitCode "Maintenance tests"
        Push-Location apps/web
        try {
            npm run lint
            Assert-LastExitCode "Web lint"
            npm test
            Assert-LastExitCode "Web tests"
            npm run build
            Assert-LastExitCode "Web production build"
        } finally { Pop-Location }
        & $Python -X utf8 scripts/update_knowledge.py --check
        Assert-LastExitCode "Knowledge drift check"
        Write-Output "Service gates passed. Platform changes also require Media tests, localhost acceptance and backup/restore; see the maintenance workflow."
    } finally {
        foreach ($Name in $Overrides.Keys) {
            [Environment]::SetEnvironmentVariable($Name, $Previous[$Name], "Process")
        }
    }
}

Push-Location $Root
try {
    switch ($Mode) {
        "brief" { Show-Brief }
        "files" { Show-ImportantFiles }
        "verify" { Run-Verify }
    }
} finally { Pop-Location }
