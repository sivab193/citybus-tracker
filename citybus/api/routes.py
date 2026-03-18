"""
Public API routes — stops, routes, arrivals, search, auth.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from citybus.api.auth import require_api_key
from citybus.services.stop_service import get_stop_service
from citybus.db.mongo import get_db
from citybus.db.redis import get_arrivals
from citybus.worker.gtfs_poller import (
    fetch_trip_updates, parse_arrivals_for_stop,
)

router = APIRouter(prefix="/api/v1", tags=["Public"])


# ── Auth ──

class SignupRequest(BaseModel):
    owner: str


class SignupResponse(BaseModel):
    owner: str
    api_key: str
    rate_limit: str
    message: str


@router.post("/auth/signup", response_model=SignupResponse, tags=["Auth"])
async def signup(body: SignupRequest):
    """Get an API key by providing an owner name/email."""
    db = get_db()
    key = f"cb_{uuid.uuid4().hex}"
    doc = {
        "_id": key,
        "owner": body.owner,
        "created_at": datetime.now(timezone.utc),
        "rate_limit": "100/minute",
        "is_active": True,
        "requests_today": 0,
        "last_request_date": "",
    }
    try:
        await db.api_keys.insert_one(doc)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to create API key")
    return SignupResponse(
        owner=body.owner,
        api_key=key,
        rate_limit="100/minute",
        message="Save your API key! Include it as 'X-API-Key' header in all requests.",
    )


# ── Stops ──

@router.get("/stops/{stop_id}", tags=["Stops"])
async def get_stop(stop_id: str, _=Depends(require_api_key)):
    svc = get_stop_service()
    stop = svc.get_stop(stop_id)
    if not stop:
        raise HTTPException(status_code=404, detail=f"Stop '{stop_id}' not found")
    routes = svc.get_routes_for_stop(stop_id)
    return {
        "data": stop.model_dump(),
        "routes": [r.model_dump() for r in routes],
    }


@router.get("/search", tags=["Search"])
async def search_stops(
    query: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    _=Depends(require_api_key),
):
    svc = get_stop_service()
    results = svc.search_stops(query, limit=limit)
    return {
        "data": [s.model_dump() for s in results],
        "meta": {"query": query, "total": len(results)},
    }


@router.get("/routes/{route_id}", tags=["Routes"])
async def get_route(route_id: str, _=Depends(require_api_key)):
    svc = get_stop_service()
    route = svc.get_route(route_id)
    if not route:
        raise HTTPException(status_code=404, detail=f"Route '{route_id}' not found")
    stop_ids = svc.route_stops.get(route.route_id, set())
    stops = [svc.get_stop(sid).model_dump() for sid in stop_ids if svc.get_stop(sid)]
    return {"data": route.model_dump(), "stops": stops}


# ── Realtime ──

@router.get("/arrivals/{stop_id}", tags=["Realtime"])
async def get_arrivals_endpoint(
    stop_id: str,
    route_id: Optional[str] = Query(None),
    _=Depends(require_api_key),
):
    """Get arrivals — tries Redis cache first, falls back to live fetch."""
    svc = get_stop_service()
    stop = svc.get_stop(stop_id)
    if not stop:
        raise HTTPException(status_code=404, detail=f"Stop '{stop_id}' not found")

    # Try Redis cache
    cached = await get_arrivals(stop_id)
    if cached:
        data = []
        for key, secs in sorted(cached.items(), key=lambda x: x[1]):
            r_id = key.replace("route_", "")
            if route_id and r_id != route_id:
                continue
            route = svc.get_route(r_id)
            data.append({
                "route_id": r_id,
                "route_name": route.route_short_name if route else r_id,
                "seconds_until": secs,
                "minutes_until": secs // 60,
            })
        return {
            "data": data,
            "source": "cache",
            "stop": stop.model_dump(),
            "updated_at": datetime.now().isoformat(),
        }

    # Fallback: live fetch
    try:
        feed = await asyncio.to_thread(fetch_trip_updates)
        arrivals = parse_arrivals_for_stop(feed, stop_id, route_id)
        data = []
        for a in arrivals:
            route = svc.get_route(a.route_id)
            data.append({
                "route_id": a.route_id,
                "route_name": route.route_short_name if route else a.route_id,
                "arrival_time": a.arrival_time.isoformat() if a.arrival_time else None,
                "delay_seconds": a.delay_seconds,
                "minutes_until": a.minutes_until,
            })
        return {
            "data": data,
            "source": "live",
            "stop": stop.model_dump(),
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch realtime data: {e}")


# ── Metadata ──

@router.get("/meta/dashboard-stats", tags=["Metadata"])
async def dashboard_stats():
    """Public stats for the dashboard UI — real aggregated data."""
    db = get_db()
    svc = get_stop_service()

    total_users = await db.users.count_documents({})
    active_subs = await db.subscriptions.count_documents({"status": "active"})
    total_api_keys = await db.api_keys.count_documents({})

    stats_doc = await db.stats.find_one({"_id": "global"})
    total_requests = stats_doc.get("total_requests", 0) if stats_doc else 0

    total_stops = len(svc.stops)
    total_routes = len(svc.routes)

    # Top favorited stops (aggregate across all users)
    top_favorites = []
    try:
        pipeline = [
            {"$unwind": "$favorites"},
            {"$group": {"_id": "$favorites", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
        cursor = db.users.aggregate(pipeline)
        fav_results = await cursor.to_list(length=5)
        for item in fav_results:
            stop = svc.get_stop(item["_id"])
            top_favorites.append({
                "stop_id": item["_id"],
                "stop_name": stop.stop_name if stop else item["_id"],
                "fav_count": item["count"],
            })
    except Exception:
        pass

    # Most tracked stops (from subscriptions)
    top_tracked = []
    try:
        pipeline = [
            {"$group": {"_id": "$stop_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
        cursor = db.subscriptions.aggregate(pipeline)
        tracked_results = await cursor.to_list(length=5)
        for item in tracked_results:
            stop = svc.get_stop(item["_id"])
            top_tracked.append({
                "stop_id": item["_id"],
                "stop_name": stop.stop_name if stop else item["_id"],
                "track_count": item["count"],
            })
    except Exception:
        pass

    return {
        "registered_users": total_users,
        "total_stops": total_stops,
        "total_routes": total_routes,
        "api_requests_served": total_requests,
        "active_subscriptions": active_subs,
        "api_keys_issued": total_api_keys,
        "top_favorites": top_favorites,
        "top_tracked": top_tracked,
    }


# ── Health ──

@router.get("/health", tags=["Health"])
async def health():
    svc = get_stop_service()
    return {
        "status": "healthy",
        "stops": len(svc.stops),
        "routes": len(svc.routes),
    }
