# ============================================================
#  start-backend.ps1
#  Manual startup script — run this after a reboot if the
#  Task Scheduler job hasn't fired yet, or for a first start.
#
#  Usage (from repo root):
#    .\scripts\start-backend.ps1
# ============================================================

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Fail { param($msg) Write-Host "    ERR $msg" -ForegroundColor Red }

# ── 1. Docker Desktop ─────────────────────────────────────────────────────────
Write-Step "Checking Docker Desktop..."
$tries = 0
do {
    $info = docker info 2>&1
    if ($LASTEXITCODE -eq 0) { break }
    $tries++
    if ($tries -ge 12) {
        Write-Fail "Docker Desktop did not start after 60s. Start it manually."
        exit 1
    }
    Write-Host "    Waiting for Docker Desktop... ($tries/12)" -ForegroundColor Yellow
    Start-Sleep 5
} while ($true)
Write-Ok "Docker Desktop is running."

# ── 2. Docker Compose ─────────────────────────────────────────────────────────
Write-Step "Starting Docker Compose services (db, redis, api, worker, beat)..."
docker compose up -d db redis api worker beat
if ($LASTEXITCODE -ne 0) {
    Write-Fail "docker compose up failed. Check docker compose logs."
    exit 1
}

# Wait for api to become healthy
Write-Step "Waiting for services to become healthy..."
$tries = 0
do {
    $apiState = docker compose ps api --format "{{.Health}}" 2>&1
    if ($apiState -eq "healthy") { break }
    $tries++
    if ($tries -ge 24) {
        Write-Fail "API did not become healthy after 120s."
        docker compose logs api --tail 30
        exit 1
    }
    Write-Host "    Waiting for api... state='$apiState' ($tries/24)" -ForegroundColor Yellow
    Start-Sleep 5
} while ($true)
Write-Ok "All services are up."

# ── 3. Cloudflare Tunnel ──────────────────────────────────────────────────────
Write-Step "Checking cloudflared service..."
$cfSvc = Get-Service cloudflared -ErrorAction SilentlyContinue
if (-not $cfSvc) {
    Write-Fail "cloudflared service not installed. Run scripts\setup-cloudflare-tunnel.ps1 first."
} elseif ($cfSvc.Status -ne "Running") {
    Write-Host "    Starting cloudflared service..." -ForegroundColor Yellow
    Start-Service cloudflared
    Start-Sleep 3
    Write-Ok "cloudflared started."
} else {
    Write-Ok "cloudflared is already running."
}

# ── 4. Health check ───────────────────────────────────────────────────────────
Write-Step "Health check: http://localhost:8000/health"
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 10
    Write-Ok "FastAPI responded: $($resp.Content)"
} catch {
    Write-Fail "FastAPI health check failed: $_"
}

Write-Host ""
Write-Host "Backend is running. Run .\scripts\verify.ps1 for a full connectivity test." -ForegroundColor Green
