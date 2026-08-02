# ============================================================
#  setup-cloudflare-tunnel.ps1
#  Run this ONCE from an Administrator PowerShell session to:
#   1. Install cloudflared
#   2. Authenticate with Cloudflare
#   3. Create a named tunnel
#   4. Install the tunnel as a Windows service
#   5. Register a Task Scheduler job for Docker Compose startup
# ============================================================
#
#  USAGE:
#    1. Open PowerShell as Administrator
#    2. cd D:\college-outreach-system
#    3. .\scripts\setup-cloudflare-tunnel.ps1 -TunnelName "college-outreach" -Hostname "api.yourdomain.com"
#
# ============================================================

param(
    [Parameter(Mandatory=$true)]
    [string]$TunnelName,          # e.g. "college-outreach"

    [Parameter(Mandatory=$true)]
    [string]$Hostname,            # e.g. "api.yourdomain.com"

    [string]$ProjectRoot = "D:\college-outreach-system",
    [int]$DockerStartupDelaySeconds = 60
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "    WARN: $msg" -ForegroundColor Yellow }

# ── Step 1: Install cloudflared ──────────────────────────────────────────────
Write-Step "Installing cloudflared via winget..."
$installed = Get-Command cloudflared -ErrorAction SilentlyContinue
if ($installed) {
    Write-Ok "cloudflared is already installed: $(cloudflared --version)"
} else {
    winget install --id Cloudflare.cloudflared -e --silent
    # Refresh PATH for this session
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH", "User")
    Write-Ok "cloudflared installed: $(cloudflared --version)"
}

# ── Step 2: Authenticate ──────────────────────────────────────────────────────
Write-Step "Authenticating with Cloudflare (browser will open)..."
$certPath = "$env:USERPROFILE\.cloudflared\cert.pem"
if (Test-Path $certPath) {
    Write-Ok "Already authenticated (cert.pem exists). Skipping."
} else {
    cloudflared tunnel login
    if (-not (Test-Path $certPath)) {
        throw "Authentication failed — cert.pem not found at $certPath"
    }
    Write-Ok "Authenticated. cert.pem saved."
}

# ── Step 3: Create the named tunnel ──────────────────────────────────────────
Write-Step "Creating tunnel: $TunnelName..."
$existing = cloudflared tunnel list 2>&1 | Select-String $TunnelName
if ($existing) {
    Write-Ok "Tunnel '$TunnelName' already exists. Skipping creation."
} else {
    cloudflared tunnel create $TunnelName
    Write-Ok "Tunnel '$TunnelName' created."
}

# Get the tunnel UUID
$tunnelInfo = cloudflared tunnel info $TunnelName 2>&1
$uuidLine = $tunnelInfo | Select-String -Pattern "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
if (-not $uuidLine) {
    throw "Could not parse tunnel UUID from: $tunnelInfo"
}
$uuid = $uuidLine.Matches[0].Value
Write-Ok "Tunnel UUID: $uuid"

# ── Step 4: Write config.yml to ~/.cloudflared ───────────────────────────────
Write-Step "Writing config.yml to $env:USERPROFILE\.cloudflared\config.yml..."
$configContent = @"
tunnel: $uuid
credentials-file: $env:USERPROFILE\.cloudflared\$uuid.json

metrics: localhost:2000

ingress:
  - hostname: $Hostname
    service: http://localhost:8000
    originRequest:
      connectTimeout: 10s
      keepAliveConnections: 10

  - service: http_status:404
"@

$cfDir = "$env:USERPROFILE\.cloudflared"
New-Item -ItemType Directory -Force -Path $cfDir | Out-Null
$configContent | Out-File -FilePath "$cfDir\config.yml" -Encoding utf8 -Force
Write-Ok "Config written to $cfDir\config.yml"

# ── Step 5: Route DNS ─────────────────────────────────────────────────────────
Write-Step "Creating DNS CNAME: $Hostname → $uuid.cfargotunnel.com..."
cloudflared tunnel route dns $TunnelName $Hostname
Write-Ok "DNS route created. Verify in Cloudflare dashboard that the record is Proxied (orange cloud)."

# ── Step 6: Install tunnel as Windows service ─────────────────────────────────
Write-Step "Installing cloudflared as a Windows service..."
$svc = Get-Service cloudflared -ErrorAction SilentlyContinue
if ($svc) {
    Write-Ok "Service already installed. Restarting to apply new config..."
    Restart-Service cloudflared
} else {
    cloudflared service install
    Start-Service cloudflared
    Write-Ok "Service installed and started."
}

# Confirm it's running
$svc = Get-Service cloudflared
if ($svc.Status -eq "Running") {
    Write-Ok "cloudflared service is Running. StartType: $($svc.StartType)"
} else {
    Write-Warn "Service status is $($svc.Status). Check Event Viewer for errors."
}

# ── Step 7: Docker Compose Task Scheduler job ────────────────────────────────
Write-Step "Registering Task Scheduler job: CollegeOutreach-DockerCompose..."
$taskName = "CollegeOutreach-DockerCompose"
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Ok "Task already exists. Skipping."
} else {
    $action = New-ScheduledTaskAction `
        -Execute "docker" `
        -Argument "compose up -d db redis api worker beat" `
        -WorkingDirectory $ProjectRoot

    $trigger = New-ScheduledTaskTrigger -AtLogon
    $trigger.Delay = "PT${DockerStartupDelaySeconds}S"

    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -RunLevel Highest

    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 2) `
        -StartWhenAvailable $true

    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "Starts college-outreach Docker Compose stack on login (${DockerStartupDelaySeconds}s after login to allow Docker Desktop to start)"

    Write-Ok "Task registered. Will run ${DockerStartupDelaySeconds}s after each login."
}

# ── Step 8: Watchdog task ─────────────────────────────────────────────────────
Write-Step "Registering watchdog task: CollegeOutreach-Watchdog..."
$watchdogName = "CollegeOutreach-Watchdog"
$watchdogScript = "$ProjectRoot\scripts\watchdog.ps1"
$existingWatchdog = Get-ScheduledTask -TaskName $watchdogName -ErrorAction SilentlyContinue
if ($existingWatchdog) {
    Write-Ok "Watchdog task already exists. Skipping."
} else {
    $wAction = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$watchdogScript`""

    $wTrigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 5) -Once -At (Get-Date)
    $wPrincipal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest
    $wSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

    Register-ScheduledTask `
        -TaskName $watchdogName `
        -Action $wAction `
        -Trigger $wTrigger `
        -Principal $wPrincipal `
        -Settings $wSettings `
        -Description "Restarts any stopped college-outreach Docker services and cloudflared every 5 minutes"

    Write-Ok "Watchdog task registered."
}

# ── Step 9: Windows Firewall ───────────────────────────────────────────────────
Write-Step "Adding Windows Firewall rule to block external access to port 8000..."
$fwRule = Get-NetFirewallRule -DisplayName "Block external port 8000" -ErrorAction SilentlyContinue
if ($fwRule) {
    Write-Ok "Firewall rule already exists."
} else {
    New-NetFirewallRule `
        -DisplayName "Block external port 8000" `
        -Direction Inbound `
        -LocalPort 8000 `
        -Protocol TCP `
        -Action Block `
        -RemoteAddress Internet | Out-Null
    Write-Ok "Firewall rule added. Port 8000 is blocked from external access."
}

# ── Summary ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " Setup complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host " Tunnel UUID  : $uuid"
Write-Host " Hostname     : https://$Hostname"
Write-Host " Config file  : $env:USERPROFILE\.cloudflared\config.yml"
Write-Host ""
Write-Host " Next steps:" -ForegroundColor Yellow
Write-Host "  1. Update .env:"
Write-Host "       PUBLIC_BASE_URL=https://$Hostname"
Write-Host "       PUBLIC_API_URL=https://$Hostname"
Write-Host "       CORS_ORIGINS=https://your-app.vercel.app,http://localhost:3000"
Write-Host ""
Write-Host "  2. In Vercel Dashboard → Settings → Environment Variables:"
Write-Host "       NEXT_PUBLIC_API_URL = https://$Hostname"
Write-Host "     Then redeploy your frontend."
Write-Host ""
Write-Host "  3. Rebuild Docker containers to pick up .env changes:"
Write-Host "       docker compose up -d --build"
Write-Host ""
Write-Host "  4. Run verification:"
Write-Host "       .\scripts\verify.ps1"
Write-Host ""
Write-Host " IMPORTANT: Rotate your Groq API key and Gmail App Password"
Write-Host "            — they were exposed in a previous session." -ForegroundColor Red
