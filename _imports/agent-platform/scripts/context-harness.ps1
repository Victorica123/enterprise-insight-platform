param(
    [ValidateSet("brief", "files", "verify")]
    [string]$Mode = "brief"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
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
        -g "!apps/api/app/__pycache__/**" `
        -g "!apps/api/data/**" `
        -g "!*.tsbuildinfo"
}

function Show-Brief {
    Get-Content -Path "docs/context-brief.md"
    ""
    "## Current Important Files"
    Show-ImportantFiles
}

function Run-Verify {
    python -m compileall apps\api\app
    Assert-LastExitCode "Python compile"
    Push-Location apps\api
    python -m unittest discover -s tests -v
    Assert-LastExitCode "Python tests"
    python -c "from app.rag import answer_question; from app.database import get_embedding_stats, rebuild_chunk_embeddings; from app.main import get_system_status; modes=['keyword','embedding','hybrid']; [print(mode, answer_question('smoke test','local',mode).trace[2].status) for mode in modes]; print(get_embedding_stats()); print(rebuild_chunk_embeddings()); print(get_system_status()); print('smoke_ok')"
    Assert-LastExitCode "Backend smoke test"
    Pop-Location
    python scripts\evaluate_v2.py
    Assert-LastExitCode "V2 offline evaluation"
    python scripts\evaluate_v3.py
    Assert-LastExitCode "V3 controlled-tool evaluation"
    python scripts\evaluate_v4.py
    Assert-LastExitCode "V4 GraphRAG evaluation"
    python scripts\evaluate_v5.py
    Assert-LastExitCode "V5 observability evaluation"
    python scripts\evaluate_v6.py
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
