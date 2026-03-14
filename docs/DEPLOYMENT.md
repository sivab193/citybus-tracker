# Deployment Guide

## Prerequisites

- Python 3.11+
- MongoDB Atlas account (or local MongoDB)
- Redis Cloud account (or local Redis)
- Google Cloud account (for cloud deployment)

## Local Development

```bash
# 1. Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your values

# 2. Start services (separate terminals)
python main_api.py          # API server
python main_bot.py          # Telegram bot
python main_worker.py       # Background worker

# 3. Test MCP with LM Studio
# In LM Studio: Add tool server → Command: python -m citybus.mcp.server
# Working directory: /path/to/citybus-bot
```

## Cloud Deployment

### One-Time GCP Setup

```bash
./scripts/setup_gcp.sh
```

### API → Cloud Run

```bash
./scripts/deploy_cloudrun.sh [project-id] [region]
```

### Worker + Bot → Compute Engine

```bash
./scripts/deploy_worker_vm.sh <server_ip> [ssh_user]
```

This creates two systemd services:
- `citybus-worker` — GTFS poller + notification sender
- `citybus-bot` — Telegram bot

### Monitoring

```bash
# Worker logs
ssh user@server 'sudo journalctl -u citybus-worker -f'

# Bot logs
ssh user@server 'sudo journalctl -u citybus-bot -f'

# Cloud Run logs
gcloud logging read "resource.type=cloud_run_revision" --limit 50
```

## External Services

### MongoDB Atlas

1. Create cluster at [cloud.mongodb.com](https://cloud.mongodb.com)
2. Create database user
3. Whitelist IPs (or use 0.0.0.0/0 for dev)
4. Copy connection string to `MONGO_URI` in `.env`

### Redis Cloud

1. Create database at [redis.com](https://redis.com/try-free)
2. Copy endpoint to `REDIS_URL` in `.env` as `redis://default:password@host:port`

## Adding New GTFS Feeds

1. Download GTFS zip from transit agency
2. Extract to `data/` directory (stops.txt, routes.txt, trips.txt, stop_times.txt, calendar.txt)
3. Restart the services — GTFS is loaded at startup
