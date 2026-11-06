<#
.SYNOPSIS
    Deploys latest changes to the 5-stacker-lol bot running on Synology NAS.

.DESCRIPTION
    1. Checks for uncommitted changes locally.
    2. Pulls the latest commits on the NAS repository.
    3. Restarts the Docker container (or rebuilds if requirements.txt or Dockerfile changed).
    4. Displays recent container logs to verify clean startup.

.PARAMETER Rebuild
    Force a full Docker image rebuild (useful after modifying requirements.txt or Dockerfile).

.EXAMPLE
    .\deploy.ps1
    .\deploy.ps1 -Rebuild
#>

param (
    [switch]$Rebuild
)

# ================= Configuration =================
# Set these or override them via environment variables:
# $env:SYNOLOGY_USER = "your_admin_username"
# $env:SYNOLOGY_HOST = "192.168.1.100" (or QuickConnect / Tailscale hostname)
# $env:SYNOLOGY_PATH = "/volume1/docker/5-stacker-lol"

$NasUser = if ($env:SYNOLOGY_USER) { $env:SYNOLOGY_USER } else { "admin" }
$NasHost = if ($env:SYNOLOGY_HOST) { $env:SYNOLOGY_HOST } else { "synology.local" }
$RemoteDir = if ($env:SYNOLOGY_PATH) { $env:SYNOLOGY_PATH } else { "/volume1/docker/5-stacker-lol" }
$ContainerName = "5-stacker-lol"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  5-Stacker Discord Bot - Synology NAS Deployment" -ForegroundColor Cyan
Write-Host "  Target: ${NasUser}@${NasHost}:${RemoteDir}" -ForegroundColor DarkGray
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Quick check for unpushed commits
$unpushed = git log @{u}.. --oneline 2>$null
if ($unpushed) {
    Write-Warning "You have local commits that have NOT been pushed to remote:"
    $unpushed | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    $confirmation = Read-Host "Do you want to run 'git push' first? (y/n)"
    if ($confirmation -match '^[yY]') {
        Write-Host ">>> Pushing to remote..." -ForegroundColor Cyan
        git push
        if ($LASTEXITCODE -ne 0) {
            Write-Error "git push failed. Aborting deployment."
            exit 1
        }
    }
}

# 2. Execute git pull & container refresh on the NAS
$remoteCommands = @()
$remoteCommands += "cd '$RemoteDir'"
$remoteCommands += "git pull origin main"

if ($Rebuild) {
    Write-Host ">>> Pulling changes and rebuilding Docker image on NAS..." -ForegroundColor Yellow
    $remoteCommands += "docker compose up -d --build"
} else {
    Write-Host ">>> Pulling changes and restarting container on NAS..." -ForegroundColor Cyan
    # If Dockerfile or requirements.txt changed, rebuild automatically; otherwise restart
    $remoteCommands += "docker compose restart || docker compose up -d"
}

$combinedCommand = $remoteCommands -join " && "

ssh -o BatchMode=no "${NasUser}@${NasHost}" "$combinedCommand"
if ($LASTEXITCODE -ne 0) {
    Write-Error "SSH command execution failed on NAS. Check connection and permissions."
    exit 1
}

# 3. Stream recent container logs to verify startup
Write-Host "`n>>> Verifying container status and checking startup logs..." -ForegroundColor Green
Start-Sleep -Seconds 2
ssh "${NasUser}@${NasHost}" "docker logs --tail 25 $ContainerName"

Write-Host "`n Deployment complete!" -ForegroundColor Green

