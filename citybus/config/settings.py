"""
Centralized settings — all configuration from .env with validated defaults.
"""

import os
from dotenv import load_dotenv

load_dotenv()


# --- Telegram Bot ---
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# --- Location & Agency ---
CITY_ID: str = os.environ.get("CITY_ID", "default")
AGENCY_TZ: str = os.environ.get("AGENCY_TZ", "UTC")

# --- API ---
API_PORT: int = int(os.environ.get("API_PORT", "8000"))

# --- MongoDB ---
MONGO_URI: str = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME: str = os.environ.get("MONGO_DB_NAME", "citybus")

# --- Redis ---
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_ARRIVAL_TTL: int = int(os.environ.get("REDIS_ARRIVAL_TTL", "30"))

# --- Dynamic Configurations ---
# These are the DEFAULT values. The actual values will be fetched
# dynamically from the `config` collection in MongoDB.
DEFAULT_CONFIG = {
    "GTFS_RT_TRIP_UPDATES_URL": os.environ.get("GTFS_RT_URL", "https://bus.gocitybus.com/GTFSRT/GTFS_TripUpdates.pb"),
    "GTFS_RT_VEHICLE_POSITIONS_URL": os.environ.get("GTFS_RT_VEHICLE_URL", "https://bus.gocitybus.com/GTFSRT/GTFS_VehiclePositions.pb"),
    "GTFS_RT_SERVICE_ALERTS_URL": os.environ.get("GTFS_RT_ALERTS_URL", "https://bus.gocitybus.com/GTFSRT/GTFS_ServiceAlerts.pb"),
    "API_RATE_LIMIT": os.environ.get("API_RATE_LIMIT", "100/minute"),
    "ADMIN_API_KEY": os.environ.get("ADMIN_API_KEY", "change_me_in_production"),
    "ADMIN_IDS": [int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()],
    "WORKER_POLL_INTERVAL": int(os.environ.get("WORKER_POLL_INTERVAL", "10")),
    "MAX_ACTIVE_SUBSCRIPTIONS": 3,
    "MAX_NOTIFICATIONS_PER_SUB": 100,
    "INACTIVITY_TIMEOUT_MINUTES": 30,
    "ALLOWED_FREQUENCIES": [10, 20, 30, 60, 120, 300, 600],
    "LOG_GENERAL_TTL_DAYS": 7,
    "LOG_ERROR_TTL_DAYS": 30,
}

_dynamic_cache = {}

async def get_dynamic_config():
    """Fetch the dynamic configuration from MongoDB."""
    from citybus.db.mongo import get_db
    db = get_db()
    
    # We store all configs in a single document with _id="global"
    doc = await db.config.find_one({"_id": "global"})
    
    if not doc:
        # Seed it with defaults if it doesn't exist
        doc = {"_id": "global", **DEFAULT_CONFIG}
        try:
            await db.config.insert_one(doc)
        except Exception:
            pass
            
    global _dynamic_cache
    _dynamic_cache = doc
    return doc

def get_config(key, default=None):
    """Synchronous getter that uses the last cached config."""
    if not _dynamic_cache:
        return DEFAULT_CONFIG.get(key, default)
    return _dynamic_cache.get(key, DEFAULT_CONFIG.get(key, default))

