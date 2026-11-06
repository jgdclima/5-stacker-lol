# Synology NAS Deployment Guide for 5-Stack Coordinator

This setup runs the bot in a lightweight Docker container on your Synology NAS using **Container Manager**. It uses live volume mounts for Python code so updates apply in ~1 second with no rebuild needed.

---

## Architecture Overview
- **Container**: `5-stacker-lol` (Python 3.11-slim)
- **Persistent Data**: `docker/5-stacker-lol/data/` (contains `league_stats.json` and logs)
- **Live Code Mounts**: `bot.py`, `data_manager.py`, `rating_engine.py`, etc., are mounted into the container as read-only volumes.
- **Pushing Patches**: Run `git push` locally, then execute `.\deploy.ps1`. The NAS runs `git pull` and restarts the container instantly.

---

## Initial Setup (One-Time)

### 1. Enable Container Manager & SSH on DSM
1. In DSM, open **Package Center** and install **Container Manager** (or **Docker** on older DSM).
2. Go to **Control Panel > Terminal & SNMP** -> Check **Enable SSH service** (default port 22).

### 2. Prepare Directory on the NAS
Log into your NAS via SSH (from PowerShell or Terminal):
```bash
ssh <your_admin_user>@<nas_ip_or_hostname>
```
Create the project folder under `/volume1/docker/`:
```bash
cd /volume1/docker
git clone https://github.com/jgdclima/5-stacker-lol.git
cd 5-stacker-lol
mkdir -p data
```

### 3. Copy Existing State & Secrets to the NAS
From your PC (PowerShell), transfer your existing `.env` file and historical `league_stats.json`:
```powershell
# Copy .env
scp .env <your_admin_user>@<nas_ip_or_hostname>:/volume1/docker/5-stacker-lol/.env

# Copy existing league stats (if you have active records)
scp data/league_stats.json <your_admin_user>@<nas_ip_or_hostname>:/volume1/docker/5-stacker-lol/data/league_stats.json
```

### 4. Build and Launch the Container
SSH into the NAS and start the bot:
```bash
cd /volume1/docker/5-stacker-lol
docker compose up -d --build
```
Verify that the bot is running:
```bash
docker logs -f 5-stacker-lol
```
(Press `Ctrl+C` to exit the log stream).

---

## Setting Up 1-Click Deployment (`.\deploy.ps1`)

To push updates effortlessly from your PC without typing passwords every time:

### 1. Set Up SSH Key-Based Authentication
On your PC (PowerShell):
```powershell
# Generate an SSH key if you don't already have one
ssh-keygen -t ed25519

# Copy your public key to the NAS (replace with your admin user and IP)
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh <your_admin_user>@<nas_ip_or_hostname> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```
Test that you can run `ssh <your_admin_user>@<nas_ip_or_hostname>` without entering a password.

### 2. Configure `deploy.ps1`
Edit the top of [`deploy.ps1`](file:///c:/Users/theot/Documents/dev/5-stacker-lol/deploy.ps1) (or set environment variables in Windows):
```powershell
$NasUser = "admin"
$NasHost = "192.168.1.100"       # Or your NAS hostname or Tailscale IP
$RemoteDir = "/volume1/docker/5-stacker-lol"
```

---

## Daily Patching Workflow

Whenever you change bot code:

1. **Test locally** (if desired):
   ```powershell
   python bot.py
   ```
2. **Commit and push** to GitHub:
   ```powershell
   git commit -am "My bot update"
   git push
   ```
3. **Deploy to NAS**:
   ```powershell
   .\deploy.ps1
   ```
   - It triggers `git pull` on the NAS.
   - It reloads the container with the mounted code in ~1 second.
   - It streams the startup logs directly in your console so you can confirm it initialized properly.

> [!TIP]
> If you add new pip packages to `requirements.txt` or modify `Dockerfile`, run:
> ```powershell
> .\deploy.ps1 -Rebuild
> ```
> This tells Docker on the NAS to rebuild the image before restarting.

