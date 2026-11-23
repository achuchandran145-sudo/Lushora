$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Write-Host '=== LUSHORA setup ===' -ForegroundColor Magenta
$script:PythonArgs = @()
function Find-Python {
  # Prefer versions with stable wheel support for the pinned backend dependencies.
  foreach ($version in @('3.13','3.12')) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
      try { & py "-$version" --version 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { $script:PythonArgs = @("-$version"); return "py" } } catch {}
    }
  }
  foreach ($cmd in @('python','python3')) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
      try {
        $versionText = & $cmd --version 2>$null
        if ($versionText -match 'Python 3\.(12|13)\.') { return $cmd }
      } catch {}
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
  if (-not $Python) { throw 'Python 3.12 or 3.13 is recommended for this MVP. Install from https://www.python.org/downloads/ and rerun.' }
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
if (-not (Test-Path 'backend\.venv')) { & $Python @script:PythonArgs -m venv 'backend\.venv' }
$PyExe = Join-Path $Root 'backend\.venv\Scripts\python.exe'
& $PyExe -m pip install --upgrade pip
& $PyExe -m pip install -r 'backend\requirements.txt'
Set-Location (Join-Path $Root 'frontend')
if (-not (Test-Path 'node_modules')) { npm install }
Write-Host 'Setup complete.' -ForegroundColor Green
