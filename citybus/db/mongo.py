"""
MongoDB connection manager and collection setup.
"""

from typing import Optional
import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from citybus.config import settings

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


def get_db() -> AsyncIOMotorDatabase:
    """Return the MongoDB database, creating the client on first call."""
    global _client, _db
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        _db = _client[settings.MONGO_DB_NAME]
    return _db


async def init_db():
    """Create indexes for all collections."""
    db = get_db()

    # Users
    await db.users.create_index("username", sparse=True)

    # API keys (using _id for the key, which is natively indexed)

    # Subscriptions
    await db.subscriptions.create_index("user_id")
    await db.subscriptions.create_index([("user_id", 1), ("status", 1)])

    # GTFS static (for API lookups)
    await db.stops.create_index("stop_id", unique=True)
    await db.routes.create_index("route_id", unique=True)

    # Logging — TTL indexes
    await db.logs_general.create_index(
        "timestamp",
        expireAfterSeconds=settings.get_config("LOG_GENERAL_TTL_DAYS", 7) * 86400,
    )
    await db.logs_errors.create_index(
        "timestamp",
        expireAfterSeconds=settings.get_config("LOG_ERROR_TTL_DAYS", 30) * 86400,
    )

    # Admin actions
    await db.admin_actions.create_index("timestamp")


async def close_db():
    """Gracefully close the MongoDB client."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
