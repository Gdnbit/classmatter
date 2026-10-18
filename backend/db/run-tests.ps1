[CmdletBinding()]
param([string]$PostgresRoot = '')
$ErrorActionPreference = 'Stop'
$backendRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $backendRoot
if ([string]::IsNullOrWhiteSpace($PostgresRoot)) {
    $PostgresRoot = Join-Path (Split-Path -Parent $repoRoot) 'class-os-local-runtime/postgresql-18.6/pgsql'
}
if (-not (Test-Path -LiteralPath $PostgresRoot -PathType Container)) {
    throw 'PostgreSQL binaries required: pass -PostgresRoot; no shared DSN is accepted'
}
Push-Location (Join-Path $repoRoot 'apps/web')
try {
    pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw 'Browser test dependency sync failed' }
    pnpm typecheck
    if ($LASTEXITCODE -ne 0) { throw 'Web typecheck failed' }
    pnpm build
    if ($LASTEXITCODE -ne 0) { throw 'Integrated browser test Web build failed' }
}
finally { Pop-Location }
Push-Location $backendRoot
try {
    uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Database test dependency sync failed' }
    uv run --frozen pytest tests -q -m db --pg-root $PostgresRoot
    if ($LASTEXITCODE -ne 0) { throw 'Database integration tests failed' }
}
finally { Pop-Location }
