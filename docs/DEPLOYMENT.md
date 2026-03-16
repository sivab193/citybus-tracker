# Deployment Guide

Deploy CityBus Bot to a **GCP Compute Engine** VM with automatic SSL via Caddy and CI/CD via GitHub Actions.

## Prerequisites

- A GCP project with billing enabled
- A domain managed in Google Cloud DNS (this guide uses `cb.siv19.dev`)
- A MongoDB Atlas cluster (free tier works)
- The repo pushed to GitHub

---

## 1. Create the GCE VM

```bash
gcloud compute instances create citybus-prod \
  --zone=us-east4-a \
  --machine-type=e2-small \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=20GB \
  --tags=http-server,https-server

# Allow HTTP + HTTPS
gcloud compute firewall-rules create allow-http  --allow tcp:80  --target-tags http-server
gcloud compute firewall-rules create allow-https --allow tcp:443 --target-tags https-server
```

## 2. Install Docker & Caddy on the VM

SSH into the VM:
```bash
gcloud compute ssh citybus-prod --zone=us-east4-a
```

Then run:
```bash
# Docker (from Debian packages — most reliable on Debian 12)
sudo apt update
sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
docker-compose --version

# Caddy (reverse proxy + auto-SSL)
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

## 3. Point Your Domain

In **Google Cloud DNS**, add an A record:

| Type | Name | Value |
|------|------|-------|
| A | `cb.siv19.dev` | `<VM_EXTERNAL_IP>` |

Find your VM's external IP:
```bash
gcloud compute instances describe citybus-prod --zone=us-east4-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

## 4. Configure Caddy

On the VM, edit the Caddyfile:
```bash
sudo tee /etc/caddy/Caddyfile <<'EOF'
cb.siv19.dev {
    reverse_proxy localhost:8000
}
EOF

sudo systemctl reload caddy
```

Caddy automatically provisions a Let's Encrypt TLS certificate. Your site will be live at `https://cb.siv19.dev` once the app is running.

## 5. Clone & Configure the App

```bash
cd ~
git clone https://github.com/sivab193/citybus-bot.git citybus-tracker
cd citybus-tracker

# Create .env with your secrets
cat > .env <<'EOF'
TELEGRAM_BOT_TOKEN=your_token_here
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/citybus
REDIS_URL=redis://redis:6379/0
EOF
```

## 6. Start the Application

```bash
cd ~/citybus-tracker
docker-compose up -d --build
```

Check that everything is running:
```bash
docker-compose ps
docker-compose logs -f    # watch logs (Ctrl+C to exit)
```

### Lifecycle Commands

| Action | Command |
|--------|---------|
| **Start** | `docker-compose up -d` |
| **Stop** | `docker-compose down` |
| **Rebuild** | `docker-compose up -d --build` |
| **Logs** | `docker-compose logs -f` |
| **Status** | `docker-compose ps` |
| **Restart one service** | `docker-compose restart api` |

---

## 7. Set Up Auto-Deployment (GitHub Actions)

Every push to `main` will automatically deploy to your VM.

### Generate an SSH Key Pair

On your **local machine**:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/citybus_deploy -C "github-actions" -N ""
```

### Add the Public Key to the VM using `gcloud`

You can use the `gcloud` CLI to inject this key into your VM's authorized list without even logging in:

```bash
cat ~/.ssh/citybus_deploy.pub | gcloud compute ssh citybus-tracker \
  --zone=us-east5-a \
  --project=hidden-talon-484715-b0 \
  --command='mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys'
```

### Add GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions** → Add these:

| Secret Name | Value |
|-------------|-------|
| `GCE_HOST` | VM external IP address |
| `GCE_USER` | SSH username on the VM (e.g., `sivab`) |
| `SSH_PRIVATE_KEY` | Contents of `~/.ssh/citybus_deploy` (the **private** key file) |

### Test the Pipeline

Push any commit to `main`:
```bash
git add . && git commit -m "Enable CI/CD" && git push origin main
```

Go to **GitHub → Actions** tab to watch the deploy run.

**What the pipeline does:**
```
SSH into VM → cd ~/citybus-tracker → git pull → docker-compose down → docker-compose up -d --build
```

---

## 8. Production Hardening (Optional)

A `docker-compose.prod.yml` override is available that:
- Removes `--reload` from uvicorn (dev-only feature)
- Adds 2 uvicorn workers for better concurrency

To use it, update the GitHub Actions deploy script to:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot not responding | `docker-compose logs bot` — check for token errors |
| API returning 502 | `docker-compose logs api` then `curl localhost:8000/health` |
| SSL not working | `sudo systemctl status caddy` then `sudo journalctl -u caddy` |
| Manual redeploy | `cd ~/citybus-tracker && git pull && docker-compose up -d --build` |
