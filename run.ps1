$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$localDependencies = Join-Path $projectRoot '.local-deps'
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($env:POI_PYTHON) {
    $pythonPath = $env:POI_PYTHON
} elseif ((Test-Path -LiteralPath $localDependencies) -and
          (Test-Path -LiteralPath $bundledPython)) {
    $pythonPath = $bundledPython
} elseif ($pythonCommand) {
    $pythonPath = $pythonCommand.Source
} elseif (Test-Path -LiteralPath $bundledPython) {
    $pythonPath = $bundledPython
} else {
    throw 'Python 3.11+ is required. Install Python or set POI_PYTHON.'
}
if (Test-Path -LiteralPath $localDependencies) {
    $env:PYTHONPATH = $localDependencies + [IO.Path]::PathSeparator + $env:PYTHONPATH
}
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath (Join-Path $projectRoot 'run.py') @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
