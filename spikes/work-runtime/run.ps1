[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
python -m unittest discover -s $PSScriptRoot -p 'test_*.py' -v
if ($LASTEXITCODE -ne 0) {
    throw "Synthetic work runtime tests failed with exit code $LASTEXITCODE"
}
