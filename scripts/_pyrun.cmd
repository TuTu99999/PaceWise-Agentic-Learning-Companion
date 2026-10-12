@echo off
REM Cross-platform Python launcher for AI log hooks (Windows cmd.exe).
REM Prefers the repository virtual environment, then tries py -3 -> python ->
REM python3. Each fallback is executed only after a real interpreter probe.
REM Exits 0 silently if no Python is found - hooks must never block the AI tool.

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" %*
  exit /b %ERRORLEVEL%
)

py -3 -c "import sys" >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 %*
  exit /b %ERRORLEVEL%
)

python -c "import sys" >nul 2>nul
if %ERRORLEVEL%==0 (
  python %*
  exit /b %ERRORLEVEL%
)

python3 -c "import sys" >nul 2>nul
if %ERRORLEVEL%==0 (
  python3 %*
  exit /b %ERRORLEVEL%
)

exit /b 0
