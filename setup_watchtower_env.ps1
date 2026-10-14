param(
    [string]$Root = $PSScriptRoot,
    [switch]$Gcs
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $Root).Path
$python = Get-Command python -ErrorAction Stop
& $python.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Watchtower requires Python 3.12 or newer" }
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Warning "Node.js 24 was not found; JavaScript behavior tests will be skipped locally (CI requires them)."
} elseif (-not ((& $node.Source --version) -match '^v(2[4-9]|[3-9][0-9])\.')) {
    Write-Warning "Node.js 24 or newer is recommended for the JavaScript behavior tests."
}
$venv = Join-Path $Root '.venv-watchtower'
& $python.Source -m venv $venv
if ($LASTEXITCODE -ne 0) { throw "Unable to create Watchtower virtual environment" }

$venvPython = Join-Path $venv 'Scripts\python.exe'
Push-Location $Root
try {
    $installTarget = if ($Gcs) { '.[gcs]' } else { '.' }
    & $venvPython -m pip install --disable-pip-version-check --constraint (Join-Path $Root 'constraints.txt') -e $installTarget
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
Write-Host "To refresh the pinned runtime dependency set, update constraints.txt deliberately and rerun this script."
