$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$geoserverRoot = Join-Path $projectRoot '.runtime\geoserver'
$javaRoot = Join-Path $projectRoot '.runtime\java'
$url = 'http://127.0.0.1:8080/geoserver/web/'

try {
    $response = Invoke-WebRequest -Uri $url -SkipHttpErrorCheck -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
        Write-Output 'GeoServer is already running on 127.0.0.1:8080.'
        exit 0
    }
} catch {}

if (-not (Test-Path -LiteralPath (Join-Path $geoserverRoot 'start.jar'))) {
    throw 'GeoServer binary is missing from .runtime\geoserver.'
}
$java = Get-ChildItem -LiteralPath $javaRoot -Directory -ErrorAction Stop |
    ForEach-Object { Join-Path $_.FullName 'bin\java.exe' } |
    Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1
if (-not $java) { throw 'Java runtime is missing from .runtime\java.' }

$dataDir = Join-Path $geoserverRoot 'data_dir'
$stdout = Join-Path $geoserverRoot 'logs\native-stdout.log'
$stderr = Join-Path $geoserverRoot 'logs\native-stderr.log'
$arguments = @('-Xms256m', '-Xmx1024m', "-DGEOSERVER_DATA_DIR=`"$dataDir`"", '-Djava.awt.headless=true', '-jar', 'start.jar')
$process = Start-Process -FilePath $java -ArgumentList $arguments -WorkingDirectory $geoserverRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Seconds 3
    if ($process.HasExited) { throw "GeoServer exited during startup. Check $stderr" }
    try {
        $response = Invoke-WebRequest -Uri $url -SkipHttpErrorCheck -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            Write-Output 'GeoServer is running on 127.0.0.1:8080.'
            exit 0
        }
    } catch {}
}
throw "GeoServer did not become ready. Check $stderr"
