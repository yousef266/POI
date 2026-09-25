$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
docker compose --env-file .env.container down
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose could not stop the local services.' }
