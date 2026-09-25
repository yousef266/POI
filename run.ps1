$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) {
    $pythonPath = $pythonCommand.Source
} else {
    $pythonPath = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw 'Python 3.11+ is required. Install Python or run from a configured environment.'
    }
}
$localDependencies = Join-Path $projectRoot '.local-deps'
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
