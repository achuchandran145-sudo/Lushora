$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Write-Host '=== LUSHORA setup ===' -ForegroundColor Magenta
function Find-Python {
  foreach ($cmd in @('py','python')) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
      try { & $cmd --version 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { return $cmd } } catch {}
    }
  }
  return $null
}
$Python = Find-Python
if (-not $Python) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host 'Python not found. Installing Python 3.12 with winget...' -ForegroundColor Yellow
    winget install --id Python.Python.3.12 --exact --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
    $Python = Find-Python
  }
  if (-not $Python) { throw 'Python 3.12+ is required. Install from https://www.python.org/downloads/ and rerun.' }
}
$Node = Get-Command node -ErrorAction SilentlyContinue
$Npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $Node -or -not $Npm) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host 'Node.js not found. Installing Node.js LTS with winget...' -ForegroundColor Yellow
    winget install --id OpenJS.NodeJS.LTS --exact --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
  }
}
if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw 'Node.js LTS is required. Install from https://nodejs.org/ then rerun this launcher.'
}
Set-Location $Root
if (-not (Test-Path 'backend\.venv')) { & $Python -m venv 'backend\.venv' }
$PyExe = Join-Path $Root 'backend\.venv\Scripts\python.exe'
& $PyExe -m pip install --upgrade pip
& $PyExe -m pip install -r 'backend\requirements.txt'
Set-Location (Join-Path $Root 'frontend')
if (-not (Test-Path 'node_modules')) { npm install }
Write-Host 'Setup complete.' -ForegroundColor Green
