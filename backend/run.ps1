[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency sync failed' }
    uv run --frozen python export_contracts.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Backend contract check failed' }
    uv run --frozen pytest -q -m 'not db'
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
}
finally { Pop-Location }
