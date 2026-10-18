param(
    [switch]$RefreshEvidence
)

$ErrorActionPreference = 'Stop'
$SpikeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $SpikeRoot
try {
    uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Agent spike frozen dependency install failed' }
    Push-Location (Join-Path $SpikeRoot 'browser')
    try {
        pnpm install --frozen-lockfile --ignore-scripts
        if ($LASTEXITCODE -ne 0) { throw 'Browser spike dependency install failed' }
        pnpm test
        if ($LASTEXITCODE -ne 0) { throw 'Browser event client tests failed' }
    } finally { Pop-Location }
    uv run pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Agent spike Python tests failed' }
    if ($RefreshEvidence) {
        uv run python routing_eval.py
        uv export --frozen --no-dev --format cyclonedx1.5 --output-file evidence/sbom.cdx.json
        uv run python dependency_inventory.py
    } else {
        uv run python routing_eval.py --check
        uv run python dependency_inventory.py --check
    }
} finally {
    Pop-Location
}
