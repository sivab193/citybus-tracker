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
- [Deployment Guide](docs/DEPLOYMENT.md)

| Component | Entry Point | Description |
|-----------|-------------|-------------|
| **Bot** | `main_bot.py` | Telegram interface — search, track, notify |
| **API** | `main_api.py` | FastAPI REST server — public + admin endpoints |
| **Worker** | `main_worker.py` | Polls GTFS-RT every 10s, caches in Redis, sends notifications |
| **MCP** | `citybus/mcp/server.py` | AI assistant tools via Model Context Protocol |

## Bot Commands

> **Note on Registration**: All users must register a unique alphanumeric username (3-15 characters) via the `/start` command before they can search or track stops.

| Command | Description |
|---------|-------------|
| `/search <name>` | Fuzzy-search stops |
| `/arrivals <stop>` | Check arrivals |
| `/schedule <stop> [route] [dur]` | Planned schedule |
| `/status` | Active subscriptions |
| `/stop` | Stop notifications |
| `/favorites` | View favorites |
| `/fav <stop>` / `/unfav <stop>` | Add/remove favorite |

**Admin** (Telegram IDs in `ADMIN_IDS` config):
`/admin_stats`, `/admin_users`, `/admin_errors`, `/admin_broadcast`, `/debug`

## 📝 API Documentation (Swagger UI)

CityBus provides a fully interactive REST API. You can explore all available endpoints, view schemas, and test requests directly from your browser using the built-in **Swagger UI**.

**Access the UI here:**  
👉 `http://localhost:8000/docs`

### Getting an API Token
To use the API (both in Swagger and your own apps), you need an API key.
You can generate one instantly via the `/signup` endpoint.

Run this command in your terminal:
```bash
curl -X POST http://localhost:8000/api/v1/auth/signup \
     -H "Content-Type: application/json" \
     -d '{"owner": "my-cool-app"}'
```

The response will contain your unique `api_key`:
```json
{
  "owner": "my-cool-app",
  "api_key": "cb_a1b2c3d4e5f6...",
  "rate_limit": "100/minute",
  "message": "Save your API key! Include it as 'X-API-Key' header in all requests."
}
```

### Using the Swagger UI
1. Open `http://localhost:8000/docs` in your browser.
2. Click the green **Authorize** button at the top right.
3. Paste the `api_key` you generated into the **X-API-Key** field and click Authorize.
4. You can now expand any endpoint (e.g., `/api/v1/search`) and click **"Try it out"** to test it right in the browser!

### Admins
Admin endpoints (`/admin/*`) require a master key. In the Swagger UI **Authorize** menu, paste your MongoDB `ADMIN_API_KEY` into the **X-Admin-Key** field to unlock these routes.

## Deployment (Docker Compose)

The simplest way to run CityBus Tracker is via the pre-built Docker image. You only need two files: `docker-compose.yml` and `.env`.

### 1. Download Configuration
Ensure you have the [docker-compose.yml](docker-compose.yml) and [.env.example](.env.example) (renamed to `.env`) in the same directory.

### 2. Configure Secrets
Edit your local `.env` file with your specific credentials:
- `TELEGRAM_BOT_TOKEN`, `MONGO_URI`, `REDIS_URL`.

### 3. Start the Containers
Run the following command. Docker will automatically pull the image and inject your `.env` secrets into the containers:

```bash
docker-compose up -d
```

### Lifecycle Commands

| Action | Command |
|--------|---------|
| **Start** | `docker-compose up -d` |
| **Stop** | `docker-compose down` |
| **Logs** | `docker-compose logs -f` |
| **Status** | `docker-compose ps` |

> [!IMPORTANT]
> **Why your secrets are safe**: The Docker image (e.g., `yourname/citybus:latest`) contains ONLY the code logic. It does **NOT** contain any credentials. When you run `docker-compose`, Docker reads your *local* `.env` file and passes those variables purely into the memory of the running container. Your private tokens never leave your server.

## Configuration Guide

The application uses a hybrid configuration model. **Foundational** settings are required to boot the app, while **Dynamic** settings can be updated at runtime without a restart by modifying the `config` collection in MongoDB.

### Foundational Settings (`.env`)

| Variable | Source | Required | Default | Description |
|----------|--------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | `.env` | **Yes** | — | Bot token from @BotFather |
| `MONGO_URI` | `.env` | **Yes** | `mongodb://localhost:27017` | MongoDB connection string |
| `REDIS_URL` | `.env` | **Yes** | `redis://redis:6379/0` | Redis connection string |
| `API_PORT` | `.env` | No | `8000` | Port for the REST API |

### Dynamic Settings (MongoDB `config` collection)

*These can also be set in `.env` as initial fallbacks.*

| Variable | Source | Default | Description |
|----------|--------|---------|-------------|
| `ADMIN_IDS` | **MongoDB** | — | CSV of Telegram IDs for bot admins |
| `ADMIN_API_KEY` | **MongoDB** | `change_me...` | Secret for admin REST endpoints |
| `WORKER_POLL_INTERVAL`| **MongoDB** | `10` | Frequency of GTFS-RT polling (seconds) |
| `GTFS_RT_URL` | **MongoDB** | *(CityBus URL)* | URL for Trip Updates proto |
| `API_RATE_LIMIT` | **MongoDB** | `100/minute` | Rate limit for REST API keys |
| `MAX_ACTIVE_SUBS` | **MongoDB** | `3` | Max alerts per user |

## License

MIT
