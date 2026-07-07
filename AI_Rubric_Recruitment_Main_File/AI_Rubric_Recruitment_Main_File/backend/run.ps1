# Use venv outside Documents (avoids WinError 5 in backend\.venv)
$Venv = "C:\venvs\ai-recruitment"
$Backend = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path "$Venv\Scripts\python.exe")) {
  Write-Host "Creating venv at $Venv ..."
  python -m venv $Venv
  & "$Venv\Scripts\python.exe" -m pip install -r "$Backend\requirements.txt"
}

Set-Location $Backend
& "$Venv\Scripts\python.exe" main.py
