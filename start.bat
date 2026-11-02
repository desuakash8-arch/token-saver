@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m token_saver warmup
if errorlevel 1 goto failed
echo.
echo Open http://127.0.0.1:8000 in your browser. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -m token_saver serve
goto end
:failed
echo Setup failed. Check Python 3.11+ and your internet connection, then run start.bat again.
pause
:end
endlocal
