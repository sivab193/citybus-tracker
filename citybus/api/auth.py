"""
API authentication — API key validation and admin key check.
"""

from fastapi import Request, HTTPException

from citybus.db.mongo import get_db
from citybus.config import settings


async def require_api_key(request: Request) -> dict:
    """Validate the API key from X-API-Key header. Returns the key document."""
    api_key = request.headers.get("X-API-Key")
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


async def require_admin_key(request: Request):
    """Validate admin key from X-Admin-Key header."""
    admin_key = request.headers.get("X-Admin-Key")
    if not admin_key or admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return True
