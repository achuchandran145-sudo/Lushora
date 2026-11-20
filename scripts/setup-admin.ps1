$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Email = 'admin@lushora.local'
Write-Host "LUSHORA Admin setup" -ForegroundColor Magenta
Write-Host "Admin email: $Email"
$SecurePassword = Read-Host "Enter the admin password you chose" -AsSecureString
$Ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
try { $Password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Ptr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Ptr) }
if ($Password.Length -lt 12) { throw "Password must be at least 12 characters." }
$env:LUSHORA_ADMIN_EMAIL = $Email
$env:LUSHORA_ADMIN_PASSWORD = $Password
Push-Location (Join-Path $Root 'backend')
try {
  if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Backend virtual environment is missing. Run RUN_LUSHORA.bat first.' }
  & .\.venv\Scripts\python.exe .\create_admin.py
  if ($LASTEXITCODE -ne 0) { throw 'Admin setup failed.' }
} finally {
  Remove-Item Env:LUSHORA_ADMIN_PASSWORD -ErrorAction SilentlyContinue
  Remove-Item Env:LUSHORA_ADMIN_EMAIL -ErrorAction SilentlyContinue
  Pop-Location
}
Write-Host "Admin setup complete. Sign in at http://localhost:5173/admin/login" -ForegroundColor Green
