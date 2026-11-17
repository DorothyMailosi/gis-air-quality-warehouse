<#
.SYNOPSIS
  Scheduled update: fetch any new CAMS months for every enabled country,
  load them, and rebuild the dbt analytics models.

.DESCRIPTION
  Safe to run repeatedly: months already loaded are skipped (--incremental),
  downloaded files are reused, and fact inserts are idempotent.
  Credentials come from the repository's .env file (see .env.example).
#>
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$env:PYTHONPATH = Join-Path $repo "src"
& $python -m gaia_pipeline run --all --incremental
exit $LASTEXITCODE
