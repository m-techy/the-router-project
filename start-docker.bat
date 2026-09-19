@echo off
setlocal
cd /d "%~dp0"

where docker >nul 2>nul
if errorlevel 1 (
  echo.
  echo Docker was not found.
  echo Install Docker Desktop, start it, then run start-docker.bat again.
  echo https://www.docker.com/products/docker-desktop/
  echo.
  pause
  exit /b 1
)

echo Starting The Router with Docker...
docker compose up -d --build
if errorlevel 1 (
  echo.
  echo Docker could not start The Router.
  echo Run: docker compose logs router
  echo.
  pause
  exit /b 1
)

echo Waiting for http://localhost:4010 ...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 60;$i++){try{$r=Invoke-WebRequest -UseBasicParsing http://localhost:4010/health -TimeoutSec 2;if($r.StatusCode -eq 200){$ok=$true;break}}catch{};Start-Sleep -Milliseconds 700}; if($ok){Start-Process 'http://localhost:4010'} else {exit 1}"
if errorlevel 1 (
  echo.
  echo The container started, but the router did not become healthy.
  echo Run: docker compose logs router
  echo.
  pause
  exit /b 1
)

echo.
echo The Router is ready in Docker mode.
echo Dashboard: http://localhost:4010
echo API:       http://localhost:4010/v1
echo Stop:      docker compose down
echo Native:    use start.bat instead
echo.
endlocal
