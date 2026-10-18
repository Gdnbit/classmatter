[CmdletBinding()]
param(
    [switch]$SkipBenchmark
)

$ErrorActionPreference = 'Stop'
$spikeRoot = $PSScriptRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $spikeRoot)

Push-Location (Join-Path $spikeRoot 'python')
try {
    uv sync --frozen
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    uv run --frozen pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

Push-Location (Join-Path $spikeRoot 'typescript')
try {
    pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    pnpm test
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

if (-not $SkipBenchmark) {
    uv run --project (Join-Path $spikeRoot 'python') --frozen python (Join-Path $spikeRoot 'benchmark.py')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host 'Language spike completed.'
