param(
    [ValidateSet("brief", "files", "verify")]
    [string]$Mode = "brief"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

function Assert-LastExitCode {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

function Show-ImportantFiles {
    rg --files `
        -g "!apps/web/node_modules/**" `
        -g "!apps/web/dist/**" `
        -g "!services/agent-service/app/__pycache__/**" `
        -g "!services/agent-service/data/**" `
        -g "!*.tsbuildinfo"
}

function Show-Brief {
    Get-Content -Path "docs/archive/agent-docs/archive/context-brief.md"
    ""
    "## Current Important Files"
    Show-ImportantFiles
}

function Run-Verify {
    python -m compileall services\agent-service\app
    Assert-LastExitCode "Python compile"
    Push-Location services\agent-service
    python -m pytest -q
    Assert-LastExitCode "Python tests"
    python -c "from app.rag import answer_question; from app.database import get_embedding_stats, rebuild_chunk_embeddings; from app.main import get_system_status; modes=['keyword','embedding','hybrid']; [print(mode, answer_question('smoke test','local',mode).trace[2].status) for mode in modes]; print(get_embedding_stats()); print(rebuild_chunk_embeddings()); print(get_system_status()); print('smoke_ok')"
    Assert-LastExitCode "Backend smoke test"
    Pop-Location
    python quality\agent-evals\evaluate_v2.py
    Assert-LastExitCode "V2 offline evaluation"
    python quality\agent-evals\evaluate_v3.py
    Assert-LastExitCode "V3 controlled-tool evaluation"
    python quality\agent-evals\evaluate_v4.py
    Assert-LastExitCode "V4 GraphRAG evaluation"
    python quality\agent-evals\evaluate_v5.py
    Assert-LastExitCode "V5 observability evaluation"
    python quality\agent-evals\evaluate_v6.py
    Assert-LastExitCode "V6 golden-set evaluation"
    Push-Location apps\web
    npm run build
    Assert-LastExitCode "Frontend production build"
    Pop-Location
}

switch ($Mode) {
    "brief" { Show-Brief }
    "files" { Show-ImportantFiles }
    "verify" { Run-Verify }
}
