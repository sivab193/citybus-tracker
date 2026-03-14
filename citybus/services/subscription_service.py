"""
Subscription management service.

Enforces limits from the spec:
  - Max 3 active subscriptions per user
  - Auto-stop after 100 notifications
  - Auto-stop after 30 minutes inactivity
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from citybus.config import settings
from citybus.db.mongo import get_db


async def create_subscription(
    user_id: int,
    stop_id: str,
    route_id: str,
    frequency: int,
) -> dict:
    """Create a new subscription.

    Args:
        frequency: update interval in seconds (must be in ALLOWED_FREQUENCIES)

    Returns:
        The subscription document.

    Raises:
        ValueError if limits exceeded or frequency not allowed.
    """
    if frequency not in settings.ALLOWED_FREQUENCIES:
        raise ValueError(
            f"Frequency must be one of {settings.ALLOWED_FREQUENCIES} seconds"
        )

    db = get_db()

    # Check active subscription count
    active_count = await db.subscriptions.count_documents(
        {"user_id": user_id, "status": "active"}
    )
    if active_count >= settings.MAX_ACTIVE_SUBSCRIPTIONS:
        raise ValueError(
            f"Max {settings.MAX_ACTIVE_SUBSCRIPTIONS} active subscriptions allowed. "
            "Stop one first with /stop."
        )

    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "stop_id": stop_id,
        "route_id": route_id,
        "frequency": frequency,
        "created_at": datetime.now(timezone.utc),
        "last_sent": None,
        "status": "active",
        "sent_count": 0,
    }
    await db.subscriptions.insert_one(doc)

    # Update user's active count
    await db.users.update_one(
        {"_id": user_id},
        {"$inc": {"active_subscriptions": 1}},
    )
    return doc


async def stop_subscription(sub_id: str) -> bool:
    """Stop a subscription by ID."""
    db = get_db()
    sub = await db.subscriptions.find_one({"_id": sub_id, "status": "active"})
    if not sub:
        return False

    await db.subscriptions.update_one(
        {"_id": sub_id},
        {"$set": {"status": "stopped"}},
    )
    await db.users.update_one(
        {"_id": sub["user_id"]},
        {"$inc": {"active_subscriptions": -1}},
    )
    return True


async def stop_user_subscriptions(user_id: int) -> int:
    """Stop all active subscriptions for a user. Returns count stopped."""
    db = get_db()
    result = await db.subscriptions.update_many(
        {"user_id": user_id, "status": "active"},
        {"$set": {"status": "stopped"}},
    )
    if result.modified_count > 0:
        await db.users.update_one(
            {"_id": user_id},
            {"$set": {"active_subscriptions": 0}},
        )
    return result.modified_count


async def get_active_subscriptions(user_id: int) -> list[dict]:
    """Get all active subscriptions for a user."""
    db = get_db()
    cursor = db.subscriptions.find({"user_id": user_id, "status": "active"})
    return await cursor.to_list(length=settings.MAX_ACTIVE_SUBSCRIPTIONS)


async def get_all_active_subscriptions() -> list[dict]:
    """Get ALL active subscriptions (used by the worker)."""
    db = get_db()
    cursor = db.subscriptions.find({"status": "active"})
    return await cursor.to_list(length=1000)


async def record_notification(sub_id: str) -> Optional[dict]:
    """Record that a notification was sent. Returns None if sub should stop."""
    db = get_db()
    now = datetime.now(timezone.utc)

    result = await db.subscriptions.find_one_and_update(
        {"_id": sub_id, "status": "active"},
        {
            "$set": {"last_sent": now},
            "$inc": {"sent_count": 1},
        },
        return_document=True,
    )
    if not result:
        return None

    # Auto-stop after max notifications
    if result["sent_count"] >= settings.MAX_NOTIFICATIONS_PER_SUB:
        await stop_subscription(sub_id)
        return None

    return result


async def cleanup_inactive():
    """Stop subscriptions inactive for INACTIVITY_TIMEOUT_MINUTES."""
    db = get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.INACTIVITY_TIMEOUT_MINUTES)

    # Find active subs where last_sent is older than cutoff (or never sent and created long ago)
    inactive = await db.subscriptions.find(
        {
            "status": "active",
            "$or": [
                {"last_sent": {"$lt": cutoff}},
                {"last_sent": None, "created_at": {"$lt": cutoff}},
            ],
        }
    ).to_list(length=1000)

    for sub in inactive:
        await stop_subscription(sub["_id"])

    return len(inactive)
