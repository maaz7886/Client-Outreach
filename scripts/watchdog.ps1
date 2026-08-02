# ============================================================
#  watchdog.ps1 — runs every 5 minutes via Task Scheduler
#  Restarts any stopped Docker services and cloudflared.
# ============================================================

$ProjectRoot = "D:\college-outreach-system"
$LogFile     = "$ProjectRoot\logs\watchdog.log"
$MaxLogLines = 500   # rotate after this many lines

function Log { param($msg) 
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

# Ensure log directory exists
New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null

# Rotate log if too large
if (Test-Path $LogFile) {
    $lines = Get-Content $LogFile
    if ($lines.Count -gt $MaxLogLines) {
        $lines | Select-Object -Last ($MaxLogLines / 2) | Set-Content $LogFile
    }
}

Log "--- watchdog check ---"

# ── Docker services ────────────────────────────────────────────────────────────
$services = @("api", "worker", "beat", "db", "redis")

# Check if Docker is running at all first
$dockerRunning = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Log "WARN: Docker Desktop is not running. Skipping container checks."
} else {
    foreach ($svc in $services) {
        $state = docker compose -f "$ProjectRoot\docker-compose.yml" ps $svc --format "{{.State}}" 2>&1
        if ($state -ne "running") {
            Log "RESTART: $svc was '$state' — restarting..."
            docker compose -f "$ProjectRoot\docker-compose.yml" restart $svc 2>&1 | Out-Null
            Log "INFO: $svc restart issued."
        } else {
            Log "OK: $svc is running."
        }
    }
}

# ── cloudflared service ───────────────────────────────────────────────────────
$cfSvc = Get-Service cloudflared -ErrorAction SilentlyContinue
if (-not $cfSvc) {
    Log "WARN: cloudflared service not found. Run setup-cloudflare-tunnel.ps1 first."
} elseif ($cfSvc.Status -ne "Running") {
    Log "RESTART: cloudflared was '$($cfSvc.Status)' — restarting..."
    Start-Service cloudflared
    Log "INFO: cloudflared restart issued."
} else {
    Log "OK: cloudflared is running."
}

Log "--- watchdog done ---"
