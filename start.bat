@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"

if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)

if not defined PY (
  echo.
  echo Python 3.11 or newer was not found.
  echo Install Python from https://www.python.org/downloads/
  echo During setup, enable "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo.
  echo The Router requires Python 3.11 or newer.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating lightweight local environment...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)

set "VPY=%CD%\.venv\Scripts\python.exe"

for /f %%H in ('powershell -NoProfile -Command "(Get-FileHash pyproject.toml -Algorithm SHA256).Hash"') do set "DEPS_HASH=%%H"
set "DEPS_MARKER=.venv\.router-deps-!DEPS_HASH!"

if not exist "!DEPS_MARKER!" (
  echo Installing or updating The Router dependencies...
  "%VPY%" -m pip install --disable-pip-version-check -e .
  if errorlevel 1 goto :fail
  del /q ".venv\.router-deps-*" >nul 2>nul
  type nul > "!DEPS_MARKER!"
) else (
  echo Dependencies already ready.
)

if not exist "data" mkdir data

echo.
echo Starting The Router in lightweight native mode...
echo Dashboard: http://localhost:4010
echo API:       http://localhost:4010/v1
echo Stop:      Ctrl+C
echo Docker:    use start-docker.bat instead
echo.

start "" powershell -NoProfile -WindowStyle Hidden -Command "$ok=$false; for($i=0;$i -lt 60;$i++){try{$r=Invoke-WebRequest -UseBasicParsing http://localhost:4010/health -TimeoutSec 2;if($r.StatusCode -eq 200){$ok=$true;break}}catch{};Start-Sleep -Milliseconds 700}; if($ok){Start-Process 'http://localhost:4010'}"

"%VPY%" -m uvicorn app.main:app --host 127.0.0.1 --port 4010
exit /b %errorlevel%

:fail
echo.
echo The Router could not start.
echo Check the output above for the failing command.
echo.
pause
exit /b 1
