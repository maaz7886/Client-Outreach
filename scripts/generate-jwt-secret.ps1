# ============================================================
#  generate-jwt-secret.ps1
#  Generates a cryptographically random 64-character JWT secret.
#  Paste the output into .env as JWT_SECRET=<output>
# ============================================================

$bytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$secret = [Convert]::ToBase64String($bytes) -replace '[+/=]', ''
$secret = $secret.Substring(0, [Math]::Min(64, $secret.Length))

Write-Host ""
Write-Host "Generated JWT Secret (64 chars):" -ForegroundColor Cyan
Write-Host $secret -ForegroundColor Green
Write-Host ""
Write-Host "Add to .env:" -ForegroundColor Yellow
Write-Host "JWT_SECRET=$secret"
Write-Host ""

# Optionally copy to clipboard
try {
    $secret | Set-Clipboard
    Write-Host "(Copied to clipboard)" -ForegroundColor DarkGray
} catch {}
