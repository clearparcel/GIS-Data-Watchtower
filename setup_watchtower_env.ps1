param(
    [string]$Root = $PSScriptRoot,
    [switch]$Gcs
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $Root).Path
$python = Get-Command python -ErrorAction Stop
$venv = Join-Path $Root '.venv-watchtower'
& $python.Source -m venv $venv
if ($LASTEXITCODE -ne 0) { throw "Unable to create Watchtower virtual environment" }

$venvPython = Join-Path $venv 'Scripts\python.exe'
Push-Location $Root
try {
    $installTarget = if ($Gcs) { '.[gcs]' } else { '.' }
    & $venvPython -m pip install --disable-pip-version-check -e $installTarget
    if ($LASTEXITCODE -ne 0) { throw "Watchtower package installation failed with exit code $LASTEXITCODE" }

    & $venvPython -m clearparcel.datawatch --config (Join-Path $Root 'config\example_sources.json') status --json | Out-Null
    if ($LASTEXITCODE -ge 2) { throw "Watchtower isolated environment validation failed with exit code $LASTEXITCODE" }

    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "Watchtower dependency check failed" }
} finally {
    Pop-Location
}
Write-Host "Watchtower virtual environment ready: $venv"
if ($Gcs) { Write-Host "Google Cloud Storage support installed." }
