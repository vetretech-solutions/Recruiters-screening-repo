@echo off
REM Use venv outside Documents (avoids Windows file-lock errors in backend\.venv)
set VENV=C:\venvs\ai-recruitment
if not exist "%VENV%\Scripts\python.exe" (
  echo Creating venv at %VENV% ...
  python -m venv "%VENV%"
  "%VENV%\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
)
cd /d "%~dp0"
"%VENV%\Scripts\python.exe" main.py
