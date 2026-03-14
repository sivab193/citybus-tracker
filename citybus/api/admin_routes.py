"""
Admin API routes — user management, error logs, stats, config.
Protected by X-Admin-Key header.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException

from citybus.api.auth import require_admin_key
from citybus.services.user_service import (
    list_users, count_users, get_user, ban_user, unban_user,
)
from citybus.db.mongo import get_db

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Users ──

@router.get("/users", dependencies=[Depends(require_admin_key)])
async def admin_list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List all registered Telegram users."""
    users = await list_users(limit=limit, offset=offset)
    total = await count_users()
    return {"data": users, "meta": {"total": total, "limit": limit, "offset": offset}}


@router.get("/users/{user_id}", dependencies=[Depends(require_admin_key)])
async def admin_get_user(user_id: int):
    """Get details for a specific user."""
    user = await get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Also get their subscriptions
    db = get_db()
    subs = await db.subscriptions.find({"user_id": user_id}).to_list(length=100)
    return {"user": user, "subscriptions": subs}


@router.post("/users/{user_id}/ban", dependencies=[Depends(require_admin_key)])
async def admin_ban_user(user_id: int):
    """Ban a user."""
    ok = await ban_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"User {user_id} banned"}


@router.post("/users/{user_id}/unban", dependencies=[Depends(require_admin_key)])
async def admin_unban_user(user_id: int):
    """Unban a user."""
    ok = await unban_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found or not banned")
    return {"message": f"User {user_id} unbanned"}


# ── Stats ──

@router.get("/stats", dependencies=[Depends(require_admin_key)])
async def admin_stats():
    """Get system-wide statistics."""
    db = get_db()
    total_users = await db.users.count_documents({})
    active_subs = await db.subscriptions.count_documents({"status": "active"})
    total_api_keys = await db.api_keys.count_documents({})

    # Errors today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    errors_today = await db.logs_errors.count_documents({"timestamp": {"$gte": today_start}})

    return {
        "users": total_users,
        "active_subscriptions": active_subs,
        "api_keys": total_api_keys,
        "errors_today": errors_today,
    }


# ── Logs ──

@router.get("/logs", dependencies=[Depends(require_admin_key)])
async def admin_logs(
    limit: int = Query(50, ge=1, le=200),
    service: Optional[str] = Query(None),
):
    """View general logs."""
    db = get_db()
    query = {}
    if service:
        query["worker"] = service
    cursor = db.logs_general.find(query).sort("timestamp", -1).limit(limit)
    logs = await cursor.to_list(length=limit)
    # Convert ObjectId to string for serialization
    for log in logs:
        log["_id"] = str(log["_id"])
    return {"data": logs}


@router.get("/errors", dependencies=[Depends(require_admin_key)])
async def admin_errors(
    limit: int = Query(50, ge=1, le=200),
    service: Optional[str] = Query(None),
):
    """View error logs."""
    db = get_db()
    query = {}
    if service:
        query["service"] = service
    cursor = db.logs_errors.find(query).sort("timestamp", -1).limit(limit)
    logs = await cursor.to_list(length=limit)
    for log in logs:
        log["_id"] = str(log["_id"])
    return {"data": logs}
