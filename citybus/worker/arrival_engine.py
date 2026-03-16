"""
Arrival engine — writes parsed GTFS-RT data to Redis cache.
"""

import asyncio

from citybus.db.redis import set_arrivals, set_vehicle
from citybus.worker.gtfs_poller import parse_all_arrivals, parse_vehicle_positions, fetch_trip_updates, fetch_vehicle_positions
from citybus.logging.logger import get_logger

logger = get_logger()


async def update_arrival_cache():
    """Fetch the latest GTFS-RT feed and populate Redis."""
    try:
        feed = await asyncio.to_thread(fetch_trip_updates)
        all_arrivals = parse_all_arrivals(feed)

        for stop_id, data in all_arrivals.items():
            await set_arrivals(stop_id, data)

        logger.info(f"Cached arrivals for {len(all_arrivals)} stops")
        return len(all_arrivals)
    except Exception as e:
        logger.error(f"Failed to update arrival cache: {e}")
        return 0


async def update_vehicle_cache():
    """Fetch vehicle positions and populate Redis."""
    try:
        feed = await asyncio.to_thread(fetch_vehicle_positions)
        positions = parse_vehicle_positions(feed)

        for v in positions:
            await set_vehicle(v.vehicle_id, {
                "vehicle_id": v.vehicle_id,
                "route_id": v.route_id,
                "trip_id": v.trip_id,
                "latitude": v.latitude,
                "longitude": v.longitude,
                "bearing": v.bearing,
                "speed": v.speed,
                "timestamp": v.timestamp.isoformat() if v.timestamp else None,
            })

        logger.info(f"Cached {len(positions)} vehicle positions")
        return len(positions)
    except Exception as e:
        logger.error(f"Failed to update vehicle cache: {e}")
        return 0
