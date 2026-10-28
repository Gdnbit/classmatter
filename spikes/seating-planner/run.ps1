[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
node --test (Join-Path $PSScriptRoot 'solver.test.mjs') (Join-Path $PSScriptRoot 'browser.test.mjs')
if ($LASTEXITCODE -ne 0) { throw 'Synthetic seating tests failed' }
