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
# Load variables from .env file if present
$envFile = Join-Path $PSScriptRoot ".env"
$fileEnv = @{}
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line -split "=", 2
            $key = $parts[0].Trim()
            $value = $parts[1].Trim()
            # Remove surrounding single or double quotes if present
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $fileEnv[$key] = $value
        }
    }
}

function Get-EnvConfig($key, $defaultVal) {
    if ([System.Environment]::GetEnvironmentVariable($key)) {
        return [System.Environment]::GetEnvironmentVariable($key)
    }
    if ($fileEnv.ContainsKey($key) -and $fileEnv[$key]) {
        return $fileEnv[$key]
    }
    return $defaultVal
}

$NasUser = Get-EnvConfig "SYNOLOGY_USER" $null
$NasHost = Get-EnvConfig "SYNOLOGY_HOST" $null
$RemoteDir = Get-EnvConfig "SYNOLOGY_PATH" "/volume1/docker/5-stacker-lol"
$ContainerName = Get-EnvConfig "SYNOLOGY_CONTAINER" "5-stacker-lol"

if (-not $NasUser -or -not $NasHost) {
    Write-Error "Missing required Synology connection settings in .env! Please add SYNOLOGY_USER and SYNOLOGY_HOST to your .env file."
    exit 1
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  5-Stacker Discord Bot - Synology NAS Deployment" -ForegroundColor Cyan
Write-Host "  Target: ${NasUser}@${NasHost}:${RemoteDir}" -ForegroundColor DarkGray
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Quick check for unpushed commits
$unpushed = git log "@{u}.." --oneline 2>$null
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

