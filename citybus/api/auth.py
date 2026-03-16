"""
API authentication — API key validation and admin key check.
"""

from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader

from citybus.db.mongo import get_db
from citybus.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="Token obtained from /api/v1/auth/signup")
admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False, description="Admin secret key")

async def require_api_key(api_key: str = Security(api_key_header)) -> dict:
    """Validate the API key from X-API-Key header. Returns the key document."""
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include 'X-API-Key' header. Sign up at POST /api/v1/auth/signup",
        )
    db = get_db()
    doc = await db.api_keys.find_one({"_id": api_key, "is_active": True})
    if not doc:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    # Increment usage
    from datetime import date, datetime, timezone
    today = date.today().isoformat()
    await db.api_keys.update_one(
        {"_id": api_key, "last_request_date": {"$ne": today}},
        {"$set": {"requests_today": 0, "last_request_date": today}},
    )
    await db.api_keys.update_one(
        {"_id": api_key},
        {"$inc": {"requests_today": 1}, "$set": {"last_used": datetime.now(timezone.utc)}},
    )
    return doc


async def require_admin_key(admin_key: str = Security(admin_key_header)):
    """Validate admin key from X-Admin-Key header."""
    admin_config_key = settings.get_config("ADMIN_API_KEY", "change_me_in_production")
    if not admin_key or admin_key != admin_config_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return True

