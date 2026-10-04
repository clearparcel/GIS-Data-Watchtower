param(
    [string]$Root = $PSScriptRoot
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $Root).Path
$python = Get-Command python -ErrorAction Stop
$venv = Join-Path $Root '.venv-watchtower'
& $python.Source -m venv $venv
if ($LASTEXITCODE -ne 0) { throw "Unable to create Watchtower virtual environment" }
$venvPython = Join-Path $venv 'Scripts\python.exe'
$requirements = Join-Path $Root 'requirements-watchtower.txt'
& $venvPython -m pip install --disable-pip-version-check -r $requirements
if ($LASTEXITCODE -ne 0) { throw "Watchtower dependency installation failed with exit code $LASTEXITCODE" }
$sitePackages = (& $venvPython -c "import site; print(site.getsitepackages()[0])").Trim()
if (-not $sitePackages) { throw "Unable to resolve Watchtower virtual-environment site-packages" }
Set-Content -Path (Join-Path $sitePackages 'clearparcel_tools_watchtower.pth') -Value $Root -Encoding ASCII
Push-Location $Root
try {
    & $venvPython -m clearparcel.datawatch --config (Join-Path $Root 'config\example_sources.json') status --json | Out-Null
    if ($LASTEXITCODE -ge 2) { throw "Watchtower isolated environment validation failed with exit code $LASTEXITCODE" }
    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "Watchtower dependency check failed" }
} finally {
    Pop-Location
}
Write-Host "Watchtower virtual environment ready: $venv"
