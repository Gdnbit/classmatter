param(
    [switch]$Live,
    [switch]$WriteEvidence,
    [string]$PostgresRoot = ''
)

$ErrorActionPreference = 'Stop'
$SpikeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $SpikeRoot)
Push-Location $SpikeRoot
try {
    uv sync --frozen
    uv run pytest -q
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        $PreviousPassword = $env:CLASS_OS_POSTGRES_PASSWORD
        try {
            $env:CLASS_OS_POSTGRES_PASSWORD = 'synthetic-config-validation-only'
            docker compose -f (Join-Path $SpikeRoot 'compose.yaml') config --quiet
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        } finally {
            if ($null -eq $PreviousPassword) {
                Remove-Item Env:CLASS_OS_POSTGRES_PASSWORD -ErrorAction SilentlyContinue
            } else {
                $env:CLASS_OS_POSTGRES_PASSWORD = $PreviousPassword
            }
        }
    } else {
        Write-Warning 'Docker CLI unavailable; Compose config validation skipped.'
    }
    if ($Live) {
        if ([string]::IsNullOrWhiteSpace($PostgresRoot)) {
            $PostgresRoot = Join-Path (Split-Path -Parent $RepoRoot) 'class-os-local-runtime/postgresql-18.6/pgsql'
        }
        # PostgreSQL Windows binaries do not reliably initialize under the
        # repository's non-ASCII path, so binaries and mutable data use an ASCII-only sibling.
        $RuntimeRoot = Join-Path (Split-Path -Parent $RepoRoot) 'class-os-local-runtime/self-host-spike'
        $args = @('run', 'python', 'portable_recovery.py', '--pg-root', $PostgresRoot, '--runtime-root', $RuntimeRoot)
        if ($WriteEvidence) {
            $args += @('--evidence', (Join-Path $SpikeRoot 'evidence/self-host-spike.latest.json'))
        }
        & uv @args
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
} finally {
    Pop-Location
}
