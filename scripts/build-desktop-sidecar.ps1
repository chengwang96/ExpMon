param(
  [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $Python) {
  $VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
  $Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
}

Push-Location $Root
try {
  & $Python -m pip install -r requirements.txt "pyinstaller>=6.10"
  if ($LASTEXITCODE -ne 0) { throw "Failed to install Python desktop build dependencies" }

  & $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name expmon-collector `
    --distpath build\collector `
    --workpath build\pyinstaller `
    --specpath build\pyinstaller `
    --collect-submodules tensorboard.backend.event_processing `
    --exclude-module tkinter `
    scripts\local_collector.py
  if ($LASTEXITCODE -ne 0) { throw "Failed to build ExpMon collector sidecar" }
} finally {
  Pop-Location
}
