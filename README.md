# CityBus Bot

Real-time bus tracking for **CityBus of Greater Lafayette, Indiana** — Telegram bot, REST API, MCP server, and background worker.

## Quick Start

```bash
# Clone & install
git clone https://github.com/<you>/citybus-bot.git && cd citybus-bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env   # edit: set TELEGRAM_BOT_TOKEN, MONGO_URI, REDIS_URL

# Run (pick one or all)
python main_bot.py          # Telegram bot
python main_api.py          # REST API → http://localhost:8000/docs
python main_worker.py       # Background worker (GTFS-RT → Redis → notifications)
python -m citybus.mcp.server  # MCP server (for LM Studio / AI assistants)
```

## 📚 Documentation
- [Architecture & Design Details](docs/ARCHITECTURE.md)
- [Google Cloud VM Deployment Guide](docs/DEPLOYMENT.md)

| Component | Entry Point | Description |
|-----------|-------------|-------------|
| **Bot** | `main_bot.py` | Telegram interface — search, track, notify |
| **API** | `main_api.py` | FastAPI REST server — public + admin endpoints |
| **Worker** | `main_worker.py` | Polls GTFS-RT every 10s, caches in Redis, sends notifications |
| **MCP** | `citybus/mcp/server.py` | AI assistant tools via Model Context Protocol |

## Bot Commands

| Command | Description |
|---------|-------------|
| `/search <name>` | Fuzzy-search stops |
| `/arrivals <stop>` | Check arrivals |
| `/schedule <stop> [route] [dur]` | Planned schedule |
| `/status` | Active subscriptions |
| `/stop` | Stop notifications |
| `/favorites` | View favorites |
| `/fav <stop>` / `/unfav <stop>` | Add/remove favorite |

**Admin** (Telegram IDs in `ADMIN_IDS`):
`/admin_stats`, `/admin_users`, `/admin_errors`, `/admin_broadcast`, `/debug`

## REST API

Signup: `POST /api/v1/auth/signup` → get API key → pass as `X-API-Key` header.

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/stops/{id}` | Stop details |
| `GET /api/v1/search?query=` | Search stops |
| `GET /api/v1/routes/{id}` | Route details |
| `GET /api/v1/arrivals/{stop_id}` | Realtime arrivals |

**Admin** (pass `X-Admin-Key` header):
`GET /admin/users`, `GET /admin/stats`, `GET /admin/logs`, `GET /admin/errors`,
`POST /admin/users/{id}/ban`, `POST /admin/users/{id}/unban`

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for Cloud Run + Compute Engine instructions.

```bash
./scripts/setup_gcp.sh              # one-time GCP API setup
./scripts/deploy_cloudrun.sh        # API → Cloud Run
./scripts/deploy_worker_vm.sh <ip>  # Worker + Bot → Compute Engine VM
```

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Yes | — |
| `MONGO_URI` | Yes | `mongodb://localhost:27017` |
| `REDIS_URL` | Yes | `redis://localhost:6379/0` |
| `ADMIN_IDS` | No | — |
| `ADMIN_API_KEY` | No | `change_me_in_production` |
| `API_PORT` | No | `8000` |
| `WORKER_POLL_INTERVAL` | No | `10` |

## License

MIT
