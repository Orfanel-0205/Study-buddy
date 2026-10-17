@echo off
REM Start Jarvis. Uses the .venv folder if you created one, otherwise your normal Python.
REM Any options are passed through, e.g.  run_jarvis.bat --port 8800 --no-browser
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m jarvis %*
) else (
  python -m jarvis %*
)
if errorlevel 1 pause
