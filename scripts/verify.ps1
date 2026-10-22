[CmdletBinding()]
param(
    [ValidateSet('all', 'self', 'eval-meta', 'gate-graph', 'task-graph', 'development', 'backend', 'db', 'fixtures', 'security', 'language-spike', 'agent-spike', 'self-host-spike', 'signature-spike', 'docs', 'web', 'desktop')]
    [string]$Suite = 'all',
    [string]$PostgresRoot = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    Write-Host "==> $Label"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

if ($Suite -in @('all', 'self')) {
    Invoke-Checked -Label 'Manifest verifier self-check' -Command {
        python (Join-Path $PSScriptRoot 'verify_manifests.py') self --repo-root $repoRoot
    }
}

if ($Suite -in @('all', 'eval-meta')) {
    Invoke-Checked -Label 'Release eval metadata validation' -Command {
        python (Join-Path $PSScriptRoot 'verify_manifests.py') eval-meta --repo-root $repoRoot
    }
}

if ($Suite -in @('all', 'gate-graph')) {
    Invoke-Checked -Label 'Release gate reference graph validation' -Command {
        python (Join-Path $PSScriptRoot 'verify_manifests.py') gate-graph --repo-root $repoRoot
    }
}

if ($Suite -in @('all', 'task-graph')) {
    Invoke-Checked -Label 'Release task DAG, source-row hash, closure and run-state validation' -Command {
        python (Join-Path $PSScriptRoot 'verify_manifests.py') task-graph --repo-root $repoRoot
    }
}

if ($Suite -in @('all', 'development')) {
    Invoke-Checked -Label 'Synthetic development scope (not release authorization)' -Command {
        python (Join-Path $PSScriptRoot 'verify_synthetic_development.py') --repo-root $repoRoot --task T-RPLT-001
    }
}

if ($Suite -eq 'all') {
    Invoke-Checked -Label 'Manifest verifier mutation tests' -Command {
        python -m unittest discover -s (Join-Path $PSScriptRoot 'tests') -p 'test_*.py' -v
    }
}

if ($Suite -in @('all', 'backend')) {
    Invoke-Checked -Label 'Synthetic backend composition, contracts and real TCP lifecycle' -Command {
        & (Join-Path $repoRoot 'backend/run.ps1')
    }
}

if ($Suite -in @('all', 'fixtures')) {
    Invoke-Checked -Label 'Deterministic synthetic fixture drift and sensitive-pattern check' -Command {
        python (Join-Path $PSScriptRoot 'generate_synthetic_fixtures.py') check
    }
}

if ($Suite -in @('all', 'db')) {
    Invoke-Checked -Label 'Disposable PostgreSQL migrations and transactions (no shared DSN)' -Command {
        & (Join-Path $repoRoot 'backend/db/run-tests.ps1') -PostgresRoot $PostgresRoot
    }
}

if ($Suite -eq 'security') {
    Invoke-Checked -Label 'Release 1 security implementation evals (expected red before backend)' -Command {
        python (Join-Path $repoRoot 'evals/class-os-v1/runners/security.py') run
    }
}

if ($Suite -in @('all', 'language-spike')) {
    Invoke-Checked -Label 'ADR-006B language-boundary spike contract tests' -Command {
        & (Join-Path $repoRoot 'spikes/language/run.ps1') -SkipBenchmark
    }
}

if ($Suite -in @('all', 'agent-spike')) {
    Invoke-Checked -Label 'Agent read/draft boundary, fake adapter and routing evidence tests' -Command {
        & (Join-Path $repoRoot 'spikes/agent-read-draft/run.ps1')
    }
}

if ($Suite -in @('all', 'self-host-spike')) {
    Invoke-Checked -Label 'Self-host recovery harness and Compose contract tests' -Command {
        & (Join-Path $repoRoot 'spikes/self-host/run.ps1')
    }
}

if ($Suite -in @('all', 'signature-spike')) {
    Invoke-Checked -Label 'DSSE signature envelope and admission policy conformance tests' -Command {
        & (Join-Path $repoRoot 'spikes/signature-envelope/run.ps1')
    }
}

if ($Suite -in @('all', 'docs')) {
    Invoke-Checked -Label 'Git unstaged whitespace check' -Command {
        git -C $repoRoot diff --check
    }

    Invoke-Checked -Label 'Git staged whitespace check' -Command {
        git -C $repoRoot diff --cached --check
    }

    Invoke-Checked -Label 'Markdown local-link and UTF-8 check' -Command {
        & (Join-Path $PSScriptRoot 'verify-docs.ps1') -RepoRoot $repoRoot
    }
}

if ($Suite -in @('all', 'web')) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'apps/web/package.json'))) {
        throw 'apps/web/package.json is missing'
    }

    Invoke-Checked -Label 'Frontend typecheck and build' -Command {
        Push-Location (Join-Path $repoRoot 'apps/web')
        try {
            pnpm typecheck
            if ($LASTEXITCODE -ne 0) {
                exit $LASTEXITCODE
            }
            pnpm build
        }
        finally {
            Pop-Location
        }
    }
}

if ($Suite -eq 'desktop') {
    if (-not $IsWindows -or [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64') {
        throw 'Desktop delivery verification requires Windows x64 and PowerShell 7'
    }
    Push-Location (Join-Path $repoRoot 'apps/desktop')
    try {
        Invoke-Checked -Label 'Desktop resource boundary tests' -Command { pnpm test }
        Invoke-Checked -Label 'Standalone Windows Demo build' -Command { pnpm package }
        Invoke-Checked -Label 'Packaged Electron integration' -Command { node tests/smoke.cjs --packaged }
        Invoke-Checked -Label 'Targeted frontend acceptance regression' -Command { node tests/acceptance.cjs }
        Invoke-Checked -Label 'Development-only persistent desktop assets (no service/database start)' -Command { node scripts/runtime-build.cjs }
    }
    finally { Pop-Location }
}

Write-Host 'Verification completed.'
