"""
User management service.
"""

from datetime import datetime, timezone
from typing import Optional

from citybus.db.mongo import get_db


async def get_or_create_user(telegram_id: int, username: str = None) -> dict:
    """Get a user by Telegram ID, creating them if they don't exist."""
    db = get_db()
    doc = await db.users.find_one({"_id": telegram_id})
    if doc:
        # Update username if changed
        if username and doc.get("username") != username:
            await db.users.update_one(
                {"_id": telegram_id},
                {"$set": {"username": username}},
            )
            doc["username"] = username
        return doc

    new_user = {
        "_id": telegram_id,
        "username": username,
        "created_at": datetime.now(timezone.utc),
        "favorites": [],
        "active_subscriptions": 0,
        "role": "user",
    }
    await db.users.insert_one(new_user)
    return new_user


async def get_user(telegram_id: int) -> Optional[dict]:
    """Get a user by Telegram ID."""
    db = get_db()
    return await db.users.find_one({"_id": telegram_id})


async def list_users(limit: int = 50, offset: int = 0) -> list[dict]:
    """List all users with pagination."""
    db = get_db()
    cursor = db.users.find().sort("created_at", -1).skip(offset).limit(limit)
    return await cursor.to_list(length=limit)


async def count_users() -> int:
    """Count total registered users."""
    db = get_db()
    return await db.users.count_documents({})


async def update_user_role(telegram_id: int, role: str) -> bool:
    """Update a user's role."""
    db = get_db()
    result = await db.users.update_one(
        {"_id": telegram_id},
        {"$set": {"role": role}},
    )
    return result.modified_count > 0


async def add_favorite(telegram_id: int, stop_id: str) -> bool:
    """Add a stop to user's favorites."""
    db = get_db()
    result = await db.users.update_one(
        {"_id": telegram_id},
        {"$addToSet": {"favorites": stop_id}},
    )
    return result.modified_count > 0


async def remove_favorite(telegram_id: int, stop_id: str) -> bool:
    """Remove a stop from user's favorites."""
    db = get_db()
    result = await db.users.update_one(
        {"_id": telegram_id},
        {"$pull": {"favorites": stop_id}},
    )
    return result.modified_count > 0


async def ban_user(telegram_id: int) -> bool:
    """Ban a user by setting role to 'banned'."""
    db = get_db()
    result = await db.users.update_one(
        {"_id": telegram_id},
        {"$set": {"role": "banned"}},
    )
    return result.modified_count > 0


async def unban_user(telegram_id: int) -> bool:
    """Unban a user by resetting role to 'user'."""
    db = get_db()
    result = await db.users.update_one(
        {"_id": telegram_id, "role": "banned"},
        {"$set": {"role": "user"}},
    )
    return result.modified_count > 0
