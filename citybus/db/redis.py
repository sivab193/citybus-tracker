"""
Redis connection manager for realtime caching.

Key patterns:
  arrivals:{stop_id}         — JSON dict of route_id -> seconds_until_arrival
  vehicle:{vehicle_id}       — JSON vehicle position
  subscriptions:{stop_id}:{route_id} — set of subscription IDs
  ratelimit:{api_key}        — rate limiter counter
"""

import json
from typing import Optional

import redis.asyncio as aioredis
from citybus.config import settings

_pool: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    """Return the async Redis client, creating the pool on first call."""
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
        )
    return _pool


async def close_redis():
    """Gracefully close the Redis pool."""
    global _pool
    if _pool:
        await _pool.aclose()
        _pool = None


# ── Arrival helpers ──

async def set_arrivals(stop_id: str, data: dict, ttl: int = None):
    """Cache arrival data for a stop.

    Args:
        stop_id: GTFS stop ID
        data: dict of route_id -> seconds_until_arrival
        ttl: TTL in seconds (defaults to settings.REDIS_ARRIVAL_TTL)
    """
    r = get_redis()
    ttl = ttl or settings.REDIS_ARRIVAL_TTL
    await r.set(f"arrivals:{stop_id}", json.dumps(data), ex=ttl)


async def get_arrivals(stop_id: str) -> Optional[dict]:
    """Get cached arrival data for a stop. Returns None on cache miss."""
    r = get_redis()
    raw = await r.get(f"arrivals:{stop_id}")
    if raw:
        return json.loads(raw)
    return None


async def set_vehicle(vehicle_id: str, data: dict, ttl: int = 30):
    """Cache a vehicle position."""
    r = get_redis()
    await r.set(f"vehicle:{vehicle_id}", json.dumps(data), ex=ttl)


async def get_vehicle(vehicle_id: str) -> Optional[dict]:
    """Get cached vehicle position."""
    r = get_redis()
    raw = await r.get(f"vehicle:{vehicle_id}")
    if raw:
        return json.loads(raw)
    return None
