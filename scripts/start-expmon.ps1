param(
  [int]$CollectorPort = 5184,
  [int]$FrontendPort = 5173,
  [string]$Config = "",
  [string]$HostName = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (-not (Test-Path (Join-Path $Root "node_modules"))) {
  Push-Location $Root
  try {
    npm ci
  } finally {
    Pop-Location
  }
}

$collectorEnv = "`$env:EXPMON_COLLECTOR_PORT='$CollectorPort';"
if ($Config.Trim()) {
  $collectorEnv += " `$env:EXPMON_CONFIG='$Config';"
}

$collectorCommand = "$collectorEnv python scripts/local_collector.py"
$frontendCommand = "`$env:VITE_COLLECTOR_URL='http://127.0.0.1:$CollectorPort'; npm run dev -- --host $HostName --port $FrontendPort"

$collector = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-Command", $collectorCommand) -WorkingDirectory $Root -WindowStyle Hidden -PassThru
$frontend = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-Command", $frontendCommand) -WorkingDirectory $Root -WindowStyle Hidden -PassThru

Write-Host "ExpMon collector PID: $($collector.Id)"
Write-Host "ExpMon frontend PID:  $($frontend.Id)"
Write-Host "Open: http://$HostName`:$FrontendPort"
