# ============================================================
#  verify.ps1
#  End-to-end connectivity verification for the full stack.
#  Run this after initial setup or after any config change.
#
#  Usage:
#    .\scripts\verify.ps1
#    .\scripts\verify.ps1 -TunnelHostname "api.yourdomain.com" -VercelOrigin "https://your-app.vercel.app"
# ============================================================

param(
    [string]$TunnelHostname = "",   # e.g. "api.yourdomain.com"
    [string]$VercelOrigin = ""      # e.g. "https://your-app.vercel.app"
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$pass = 0; $fail = 0; $warn = 0

function Check { param($label, [scriptblock]$test, [bool]$isWarn = $false)
    try {
        $result = & $test
        Write-Host "  [PASS] $label" -ForegroundColor Green
        if ($result) { Write-Host "         $result" -ForegroundColor DarkGray }
        $script:pass++
    } catch {
        if ($isWarn) {
            Write-Host "  [WARN] $label — $_" -ForegroundColor Yellow
            $script:warn++
        } else {
            Write-Host "  [FAIL] $label — $_" -ForegroundColor Red
            $script:fail++
        }
    }
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  College Outreach System — Verification" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

# ── Docker ─────────────────────────────────────────────────────────────────────
Write-Host "`n[Docker]" -ForegroundColor White

Check "Docker Desktop running" {
    $info = docker info 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker not running" }
    "Docker daemon OK"
}

$services = @("api", "db", "redis", "worker", "beat")
foreach ($svc in $services) {
    Check "Container '$svc' is running" {
        $state = docker compose -f "$ProjectRoot\docker-compose.yml" ps $svc --format "{{.State}}" 2>&1
        if ($state -ne "running") { throw "State: $state" }
        "State: running"
    }
}

# ── FastAPI local ──────────────────────────────────────────────────────────────
Write-Host "`n[FastAPI — localhost]" -ForegroundColor White

Check "GET http://localhost:8000/health" {
    $r = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 10
    if ($r.StatusCode -ne 200) { throw "HTTP $($r.StatusCode)" }
    $r.Content
}

Check "GET http://localhost:8000/docs (Swagger UI)" {
    $r = Invoke-WebRequest -Uri "http://localhost:8000/docs" -UseBasicParsing -TimeoutSec 10
    if ($r.StatusCode -ne 200) { throw "HTTP $($r.StatusCode)" }
    "HTTP 200"
} -isWarn $true

# ── Database ───────────────────────────────────────────────────────────────────
Write-Host "`n[Database]" -ForegroundColor White

Check "Alembic migration current" {
    $result = docker compose -f "$ProjectRoot\docker-compose.yml" exec -T api alembic current 2>&1
    if ($LASTEXITCODE -ne 0) { throw $result }
    ($result | Select-String "(head)").ToString().Trim()
}

# ── Redis ──────────────────────────────────────────────────────────────────────
Write-Host "`n[Redis]" -ForegroundColor White

Check "Redis PING" {
    $result = docker compose -f "$ProjectRoot\docker-compose.yml" exec -T redis redis-cli ping 2>&1
    if ($result.Trim() -ne "PONG") { throw "Got: $result" }
    "PONG"
}

# ── Celery ─────────────────────────────────────────────────────────────────────
Write-Host "`n[Celery]" -ForegroundColor White

Check "Celery worker inspect ping" {
    $result = docker compose -f "$ProjectRoot\docker-compose.yml" exec -T worker celery -A app.worker.celery_app inspect ping --timeout 10 2>&1
    if ($result -match "Error" -and $result -notmatch "pong") { throw $result }
    "Worker responded"
} -isWarn $true

Check "Beat container running" {
    $state = docker compose -f "$ProjectRoot\docker-compose.yml" ps beat --format "{{.State}}" 2>&1
    if ($state -ne "running") { throw "Beat state: $state" }
    "running"
}

# ── SMTP ────────────────────────────────────────────────────────────────────────
Write-Host "`n[SMTP]" -ForegroundColor White

Check "SMTP connection test" {
    $result = docker compose -f "$ProjectRoot\docker-compose.yml" exec -T api python -c @"
import os, smtplib
host = os.environ.get('SMTP_HOST','')
port = int(os.environ.get('SMTP_PORT', 587))
user = os.environ.get('SMTP_USERNAME','')
pwd  = os.environ.get('SMTP_PASSWORD','')
if not host or not user or not pwd:
    print('SMTP not configured — skipped')
else:
    s = smtplib.SMTP(host, port, timeout=10)
    s.starttls()
    s.login(user, pwd)
    s.quit()
    print('SMTP OK')
"@ 2>&1
    if ($result -match "Error" -or $result -match "Exception") { throw $result }
    $result.Trim()
} -isWarn $true

# ── Cloudflare Tunnel ──────────────────────────────────────────────────────────
Write-Host "`n[Cloudflare Tunnel]" -ForegroundColor White

Check "cloudflared service is Running" {
    $svc = Get-Service cloudflared -ErrorAction Stop
    if ($svc.Status -ne "Running") { throw "Status: $($svc.Status)" }
    "Status: Running, StartType: $($svc.StartType)"
}

Check "Tunnel metrics endpoint reachable" {
    $r = Invoke-WebRequest -Uri "http://localhost:2000/healthz" -UseBasicParsing -TimeoutSec 5
    if ($r.StatusCode -ne 200) { throw "HTTP $($r.StatusCode)" }
    $r.Content.Trim()
} -isWarn $true

if ($TunnelHostname) {
    Check "GET https://$TunnelHostname/health (via tunnel)" {
        $r = Invoke-WebRequest -Uri "https://$TunnelHostname/health" -UseBasicParsing -TimeoutSec 15
        if ($r.StatusCode -ne 200) { throw "HTTP $($r.StatusCode)" }
        $r.Content
    }
}

# ── CORS ────────────────────────────────────────────────────────────────────────
if ($VercelOrigin -and $TunnelHostname) {
    Write-Host "`n[CORS]" -ForegroundColor White

    Check "Preflight OPTIONS from Vercel origin returns correct header" {
        $headers = @{
            "Origin"                         = $VercelOrigin
            "Access-Control-Request-Method"  = "GET"
            "Access-Control-Request-Headers" = "Authorization"
        }
        $r = Invoke-WebRequest -Uri "https://$TunnelHostname/health" -Method Options -Headers $headers -UseBasicParsing -TimeoutSec 10
        $allowOrigin = $r.Headers["Access-Control-Allow-Origin"]
        if ($allowOrigin -ne $VercelOrigin -and $allowOrigin -ne "*") {
            throw "Access-Control-Allow-Origin was '$allowOrigin', expected '$VercelOrigin'"
        }
        "Access-Control-Allow-Origin: $allowOrigin"
    }
}

# ── Summary ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Results: $pass passed, $warn warnings, $fail failed" -ForegroundColor $(if ($fail -gt 0) { "Red" } elseif ($warn -gt 0) { "Yellow" } else { "Green" })
Write-Host "================================================" -ForegroundColor Cyan

if ($fail -gt 0) {
    Write-Host ""
    Write-Host "  Fix failures before deploying." -ForegroundColor Red
    exit 1
} elseif ($warn -gt 0) {
    Write-Host ""
    Write-Host "  Warnings are non-critical but worth investigating." -ForegroundColor Yellow
    exit 0
} else {
    Write-Host ""
    Write-Host "  All checks passed. System is ready." -ForegroundColor Green
    exit 0
}
