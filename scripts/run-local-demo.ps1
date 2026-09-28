$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

& "$PSScriptRoot/start-local.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Local services did not start.' }

docker compose --env-file .env.container --profile run run --rm --build agent run `
  --bbox 24.70 46.66 24.73 46.69 `
  --category pharmacy `
  --sources demo,demo_alt `
  --use internal `
  --out output/demo `
  --publish `
  --allow-demo-publish `
  --database poi `
  --layer poi_pharmacy `
  --workspace poi
if ($LASTEXITCODE -ne 0) { throw 'The agent demo failed.' }
