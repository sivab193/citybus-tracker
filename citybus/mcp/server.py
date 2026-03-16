"""
CityBus MCP Server — exposes transit tools for AI assistants
via the Model Context Protocol.

Usage:
  python -m citybus.mcp.server        # stdio mode (for LM Studio)

LM Studio config:
  Command: python -m citybus.mcp.server
  Working directory: /path/to/citybus-bot
"""

import asyncio
from datetime import datetime
from typing import Optional

from mcp.server.fastmcp import FastMCP

from citybus.services.stop_service import get_stop_service
from citybus.worker.gtfs_poller import (
    fetch_trip_updates, parse_arrivals_for_stop, format_arrival_message,
)

mcp = FastMCP(
    "CityBus Transit",
    instructions=(
        "CityBus Transit data for Greater Lafayette, Indiana. "
        "Use these tools to look up bus stops, routes, schedules, "
        "real-time arrivals, vehicle locations, and service alerts."
    ),
    host="0.0.0.0",
    port=8001,
)


async def _ensure_loaded():
    svc = get_stop_service()
    if not svc.stops:
        await svc.load_from_db()
    return svc


@mcp.tool()
async def search_stops(query: str, limit: int = 5) -> list[dict]:
    """
    Fuzzy search for bus stops by name or code.

    Args:
        query: Search term (e.g. "Walmart", "University", "BUS215")
        limit: Max results (default 5, max 20)
    """
    limit = min(limit, 20)
    svc = await _ensure_loaded()
    results = svc.search_stops(query, limit=limit)
    stops = []
    for s in results:
        routes = svc.get_routes_for_stop(s.stop_id)
        stops.append({
            "stop_id": s.stop_id,
            "stop_code": s.stop_code,
            "stop_name": s.stop_name,
            "latitude": s.stop_lat,
            "longitude": s.stop_lon,
            "routes": [{"route_id": r.route_id, "name": r.route_short_name} for r in routes],
        })
    return stops


@mcp.tool()
async def get_stop(stop_id: str) -> dict:
    """
    Get detailed information for a specific bus stop.

    Args:
        stop_id: The GTFS stop ID (e.g. "BUS215")
    """
    svc = await _ensure_loaded()
    stop = svc.get_stop(stop_id)
    if not stop:
        return {"error": f"Stop '{stop_id}' not found"}
    routes = svc.get_routes_for_stop(stop_id)
    return {
        "stop_id": stop.stop_id,
        "stop_name": stop.stop_name,
        "latitude": stop.stop_lat,
        "longitude": stop.stop_lon,
        "routes": [
            {"route_id": r.route_id, "short_name": r.route_short_name, "long_name": r.route_long_name}
            for r in routes
        ],
    }


@mcp.tool()
async def get_routes() -> list[dict]:
    """List all available CityBus routes."""
    svc = await _ensure_loaded()
    return [
        {"route_id": r.route_id, "short_name": r.route_short_name, "long_name": r.route_long_name}
        for r in svc.routes.values()
    ]


@mcp.tool()
async def get_arrivals(stop_id: str, route_id: Optional[str] = None) -> dict:
    """
    Get real-time arrival predictions for a stop.

    Args:
        stop_id: The GTFS stop ID
        route_id: Optional route ID to filter by
    """
    svc = await _ensure_loaded()
    stop = svc.get_stop(stop_id)
    if not stop:
        return {"error": f"Stop '{stop_id}' not found"}

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
                "message": format_arrival_message(a, route.route_short_name if route else ""),
            })
        return {
            "stop_id": stop_id,
            "stop_name": stop.stop_name,
            "arrivals": data,
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": f"Failed to fetch arrivals: {e}"}


if __name__ == "__main__":
    import sys
    transport = "sse" if "--sse" in sys.argv else "stdio"
    mcp.run(transport=transport)
