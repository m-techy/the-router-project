@echo off
setlocal
where docker >nul 2>nul
if errorlevel 1 (
  echo.
  echo Docker was not found.
  echo Install Docker Desktop, start it, then run start.bat again.
  echo https://www.docker.com/products/docker-desktop/
  echo.
  pause
  exit /b 1
)

echo Starting The Router...
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
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 60;$i++){try{$r=Invoke-WebRequest -UseBasicParsing http://localhost:4010/health -TimeoutSec 2;if($r.StatusCode -eq 200){$ok=$true;break}}catch{};Start-Sleep -Seconds 1}; if(-not $ok){exit 1}"
if errorlevel 1 (
  echo.
  echo The Router container started, but the web UI did not become healthy.
  echo Run: docker compose logs router
  echo.
  pause
  exit /b 1
)

echo The Router is ready.
echo Dashboard: http://localhost:4010
echo OpenAI API: http://localhost:4010/v1
start "" http://localhost:4010
echo.
echo To stop later: docker compose down
endlocal
