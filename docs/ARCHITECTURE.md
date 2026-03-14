# Architecture

## System Diagram

```
Telegram Users
      │
      ▼
┌─────────────────────┐
│  Bot (main_bot.py)  │  Compute Engine
│  python-telegram-bot│
└─────────┬───────────┘
          │ uses
          ▼
┌─────────────────────┐     ┌──────────────┐
│  API (main_api.py)  │────▶│  MongoDB     │
│  FastAPI + Uvicorn  │     │  Atlas       │
│  Cloud Run          │     │              │
└─────────┬───────────┘     │  • users     │
          │                 │  • subs      │
          │                 │  • api_keys  │
          │                 │  • logs      │
          ▼                 │  • stops     │
┌─────────────────────┐     │  • routes    │
│Worker(main_worker.py│────▶│  • trips     │
│  Compute Engine     │     └──────────────┘
│                     │
│  • GTFS-RT poller   │     ┌──────────────┐
│  • Arrival engine   │────▶│  Redis Cloud │
│  • Notifier         │     │              │
└─────────────────────┘     │ arrivals:*   │
                            │ vehicle:*    │
┌─────────────────────┐     └──────────────┘
│MCP Server (stdio)   │
│  For LM Studio      │
│  AI assistant tools  │
└─────────────────────┘
```

## Project Structure

```
citybus-bot/
├── main_api.py                 # API entry point
├── main_bot.py                 # Bot entry point
├── main_worker.py              # Worker entry point
├── Dockerfile                  # Cloud Run container
├── requirements.txt
├── .env.example
│
├── citybus/
│   ├── config/settings.py      # All config from .env
│   │
│   ├── db/
│   │   ├── mongo.py            # MongoDB connection + indexes
│   │   ├── redis.py            # Redis connection + helpers
│   │   └── models.py           # Pydantic models
│   │
│   ├── services/
│   │   ├── user_service.py     # User CRUD, roles, favorites
│   │   ├── subscription_service.py  # Subscription lifecycle
│   │   └── stop_service.py     # GTFS static data queries
│   │
│   ├── api/
│   │   ├── main.py             # FastAPI app factory
│   │   ├── auth.py             # API key + admin auth
│   │   ├── routes.py           # Public endpoints
│   │   └── admin_routes.py     # Admin endpoints
│   │
│   ├── bot/
│   │   ├── commands.py         # User + admin commands
│   │   ├── handlers.py         # Handler registration
│   │   └── keyboards.py        # Inline keyboards
│   │
│   ├── worker/
│   │   ├── gtfs_poller.py      # GTFS-RT feed parsing
│   │   ├── arrival_engine.py   # Redis cache updates
│   │   └── notifier.py         # Subscription notifications
│   │
│   ├── mcp/server.py           # MCP tools for AI assistants
│   │
│   └── logging/logger.py       # Structured logging
│
├── scripts/
│   ├── deploy_cloudrun.sh
│   ├── deploy_worker_vm.sh
│   └── setup_gcp.sh
│
├── data/                       # GTFS static data files
│   ├── stops.txt
│   ├── routes.txt
│   └── ...
│
└── tests/
```

## Data Flow

1. **Worker** polls GTFS-RT feeds every 10 seconds
2. Parsed arrivals written to **Redis** (30s TTL)
3. **Bot** and **API** read from Redis for sub-100ms responses
4. **MongoDB** stores users, subscriptions, API keys, logs
5. **Notifier** checks active subscriptions, sends Telegram messages via HTTP API

## MongoDB Collections

| Collection | Purpose | TTL |
|-----------|---------|-----|
| `users` | Telegram users | — |
| `subscriptions` | Tracking subscriptions | — |
| `api_keys` | REST API authentication | — |
| `stops` | GTFS static stops | — |
| `routes` | GTFS static routes | — |
| `logs_general` | Command/usage logs | 7 days |
| `logs_errors` | Error tracking | 30 days |
| `admin_actions` | Audit trail | — |

## Redis Keys

| Pattern | Value | TTL |
|---------|-------|-----|
| `arrivals:{stop_id}` | JSON: `{route_21: 240, ...}` | 30s |
| `vehicle:{vehicle_id}` | JSON: position + metadata | 30s |
