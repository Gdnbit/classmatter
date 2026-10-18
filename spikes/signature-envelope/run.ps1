[CmdletBinding()]
param(
    [switch]$RefreshEvidence
)

$ErrorActionPreference = 'Stop'
$spikeRoot = $PSScriptRoot

Push-Location $spikeRoot
try {
    uv sync --frozen
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    uv run pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    if ($RefreshEvidence) {
        uv run python evidence.py write
    }
    else {
        uv run python evidence.py check
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    uv run python scope_allocation_evidence.py check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
