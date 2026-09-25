$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker is not installed. Install Docker Desktop and start it, then rerun this script.'
}
docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker is installed but its engine is not running.'
}

if (-not (Test-Path -LiteralPath '.env.container')) {
    $dbPassword = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
    $gsPassword = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
    "POI_DB_PASSWORD=$dbPassword`nPOI_GS_PASSWORD=$gsPassword" | Set-Content -LiteralPath '.env.container' -Encoding utf8
    Write-Host 'Created local container credentials in .env.container (git-ignored).'
}

docker compose --env-file .env.container up -d db geoserver
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose could not start the local services.' }

$deadline = (Get-Date).AddMinutes(5)
do {
    try {
        $response = Invoke-WebRequest -Uri 'http://localhost:8080/geoserver/web/' -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            Write-Host 'PostGIS: localhost:5433; GeoServer: http://localhost:8080/geoserver'
            exit 0
        }
    } catch { Start-Sleep -Seconds 5 }
} while ((Get-Date) -lt $deadline)

throw 'GeoServer did not become ready within five minutes. Check: docker compose logs geoserver'
