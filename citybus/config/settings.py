"""
Centralized settings — all configuration from .env with validated defaults.
"""

import os
from dotenv import load_dotenv

load_dotenv()


# --- Telegram Bot ---
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS: list[int] = [
    int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()
]

# --- MongoDB ---
MONGO_URI: str = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME: str = os.environ.get("MONGO_DB_NAME", "citybus")

# --- Redis ---
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_ARRIVAL_TTL: int = int(os.environ.get("REDIS_ARRIVAL_TTL", "30"))

# --- GTFS ---
GTFS_RT_TRIP_UPDATES_URL: str = os.environ.get(
    "GTFS_RT_URL", "https://bus.gocitybus.com/GTFSRT/GTFS_TripUpdates.pb"
)
GTFS_RT_VEHICLE_POSITIONS_URL: str = os.environ.get(
    "GTFS_RT_VEHICLE_URL", "https://bus.gocitybus.com/GTFSRT/GTFS_VehiclePositions.pb"
)
GTFS_RT_SERVICE_ALERTS_URL: str = os.environ.get(
    "GTFS_RT_ALERTS_URL", "https://bus.gocitybus.com/GTFSRT/GTFS_ServiceAlerts.pb"
)
GTFS_DIR: str = os.environ.get(
    "GTFS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
)

# --- API ---
API_PORT: int = int(os.environ.get("API_PORT", "8000"))
API_RATE_LIMIT: str = os.environ.get("API_RATE_LIMIT", "100/minute")
API_BASE_URL: str = os.environ.get("API_BASE_URL", f"http://localhost:{API_PORT}")
ADMIN_API_KEY: str = os.environ.get("ADMIN_API_KEY", "change_me_in_production")

# --- Worker ---
WORKER_POLL_INTERVAL: int = int(os.environ.get("WORKER_POLL_INTERVAL", "10"))

# --- Heartbeat ---
ENABLE_HEARTBEAT: bool = os.environ.get("ENABLE_HEARTBEAT", "false").lower() == "true"
HEARTBEAT_URL: str = os.environ.get("HEARTBEAT_URL", "http://localhost:1903/heartbeat")
HEARTBEAT_INTERVAL: int = int(os.environ.get("HEARTBEAT_INTERVAL", "60"))

# --- Subscription Limits ---
MAX_ACTIVE_SUBSCRIPTIONS: int = 3
MAX_NOTIFICATIONS_PER_SUB: int = 100
INACTIVITY_TIMEOUT_MINUTES: int = 30
ALLOWED_FREQUENCIES: list[int] = [10, 20, 30, 60, 120, 300, 600]  # seconds

# --- Logging ---
LOG_GENERAL_TTL_DAYS: int = 7
LOG_ERROR_TTL_DAYS: int = 30
