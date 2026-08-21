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

  # Embedded/portable Python layouts keep runtime DLLs (ctypes' CFFI
  # runtime, expat for xml.etree, bzip2/lzma, OpenSSL, ...) outside the
  # standard DLL search path, so PyInstaller can miss them and the packaged
  # collector fails with "DLL load failed while importing <module>" (e.g.
  # _ctypes, pyexpat). Probe the common names and locations and bundle the
  # first match of each explicitly.
  $PythonDir = Split-Path $Python -Parent
  $ExtraDllNames = @(
    "ffi.dll", "ffi-8.dll", "ffi-7.dll", "libffi-8.dll",
    "expat.dll", "libexpat.dll",
    "libbz2.dll", "liblzma.dll",
    "libssl-3-x64.dll", "libcrypto-3-x64.dll"
  )
  $SearchDirs = @(
    (Join-Path $PythonDir "Library\bin"),
    (Join-Path $PythonDir "DLLs")
  )
  $AddBinaries = @()
  foreach ($Name in $ExtraDllNames) {
    foreach ($Dir in $SearchDirs) {
      $Candidate = Join-Path $Dir $Name
      if (Test-Path $Candidate) {
        $Argument = "--add-binary=$Candidate;."
        if ($AddBinaries -notcontains $Argument) {
          $AddBinaries += $Argument
          Write-Host "bundling runtime DLL: $Candidate"
        }
        break
      }
    }
  }

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
    @AddBinaries `
    scripts\local_collector.py
  if ($LASTEXITCODE -ne 0) { throw "Failed to build ExpMon collector sidecar" }
} finally {
  Pop-Location
}
