param(
  [string]$InstallDir = $(if ($env:ROUTER_INSTALL_DIR) { $env:ROUTER_INSTALL_DIR } else { Join-Path $HOME ".the-router" }),
  [string]$Branch = $(if ($env:ROUTER_INSTALL_BRANCH) { $env:ROUTER_INSTALL_BRANCH } else { "main" })
)

$ErrorActionPreference = "Stop"
$RepoUrl = if ($env:ROUTER_REPO_URL) { $env:ROUTER_REPO_URL } else { "https://github.com/m-techy/the-router-project.git" }

function Require-Command([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "The Router installer needs '$Name'."
  }
}

Require-Command "git"

$versionScript = "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if (Get-Command py -ErrorAction SilentlyContinue) {
  & py -3 -c $versionScript
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  & python -c $versionScript
} else {
  throw "The Router needs Python 3.11 or newer."
}
if ($LASTEXITCODE -ne 0) {
  throw "The Router needs Python 3.11 or newer."
}

if (Test-Path (Join-Path $InstallDir ".git")) {
  Write-Host "Updating The Router in $InstallDir"
  git -C $InstallDir fetch --prune origin $Branch
  git -C $InstallDir checkout $Branch
  git -C $InstallDir pull --ff-only origin $Branch
} elseif (Test-Path $InstallDir) {
  throw "Install path exists but is not a Router git checkout: $InstallDir"
} else {
  Write-Host "Installing The Router into $InstallDir"
  git clone --depth 1 --branch $Branch $RepoUrl $InstallDir
}

Write-Host ""
Write-Host "The Router is installed at: $InstallDir"
Write-Host "Dashboard: http://localhost:4010"
Write-Host ""

if ($env:ROUTER_INSTALL_NO_START -eq "1") {
  Write-Host "Start later with: $InstallDir\start.bat"
  exit 0
}

& (Join-Path $InstallDir "start.bat")
exit $LASTEXITCODE
