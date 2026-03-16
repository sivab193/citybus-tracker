"""
Stop and route query service.

Wraps the GTFS loader for use by API, bot, and MCP.
Loads static GTFS data from MongoDB into memory for fast lookup.
"""

import math
from typing import Optional
from datetime import datetime
from zoneinfo import ZoneInfo

from rapidfuzz import fuzz, process

from citybus.config import settings
from citybus.db.mongo import get_db
from citybus.db.models import Stop, Route


class StopService:
    """Provides stop, route, and schedule queries from GTFS static data."""

    def __init__(self):
        self.stops: dict[str, Stop] = {}
        self._stops_upper: dict[str, str] = {}  # UPPER -> original key
        self.routes: dict[str, Route] = {}
        self._routes_upper: dict[str, str] = {}  # UPPER -> original key
        self.stop_routes: dict[str, set[str]] = {}
        self.route_stops: dict[str, set[str]] = {}
        self.calendar: dict[str, dict] = {}
        self.trips: dict[str, dict] = {}
        self.stop_times: dict[str, list[tuple]] = {}

    async def load_from_db(self, city_id: str = "default"):
        """Load all GTFS static data from MongoDB."""
        db = get_db()
        
        # Load Stops
        self.stops.clear()
        self._stops_upper.clear()
        async for doc in db.stops.find({"city_id": city_id}):
            doc["_id"] = doc["_id"]
            self.stops[doc["_id"]] = Stop(**doc)
            self._stops_upper[doc["_id"].upper()] = doc["_id"]
            
        # Load Routes
        self.routes.clear()
        self._routes_upper.clear()
        async for doc in db.routes.find({"city_id": city_id}):
            doc["_id"] = doc["_id"]
            self.routes[doc["_id"]] = Route(**doc)
            self._routes_upper[doc["_id"].upper()] = doc["_id"]
            
        # Load Calendar
        self.calendar.clear()
        async for doc in db.calendar.find({"city_id": city_id}):
            self.calendar[doc["_id"]] = {
                day: doc.get(day, 0)
                for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            } | {"start_date": doc.get("start_date", ""), "end_date": doc.get("end_date", "")}
            
        # Load Trips
        self.trips.clear()
        async for doc in db.trips.find({"city_id": city_id}):
            self.trips[doc["_id"]] = {
                "route_id": doc["route_id"],
                "service_id": doc["service_id"],
                "headsign": doc.get("trip_headsign", ""),
            }
            
        # Load Stop Times and build relationships
        self.stop_times.clear()
        self.stop_routes.clear()
        self.route_stops.clear()
        
        async for doc in db.stop_times.find({"city_id": city_id}):
            sid = doc["stop_id"]
            tid = doc["trip_id"]
            secs = doc["arrival_time_seconds"]
            self.stop_times.setdefault(sid, []).append((secs, tid))
            
        for sid in self.stop_times:
            self.stop_times[sid].sort(key=lambda x: x[0])
            for _, tid in self.stop_times[sid]:
                trip = self.trips.get(tid)
                if trip:
                    rid = trip["route_id"]
                    self.stop_routes.setdefault(sid, set()).add(rid)
                    self.route_stops.setdefault(rid, set()).add(sid)


    # ── Query methods ──

    def get_stop(self, stop_id: str) -> Optional[Stop]:
        """Case-insensitive stop lookup."""
        s = self.stops.get(stop_id)
        if s:
            return s
        # Fallback: case-insensitive
        canonical = self._stops_upper.get(stop_id.upper())
        return self.stops.get(canonical) if canonical else None

    def get_route(self, route_id: str) -> Optional[Route]:
        """Case-insensitive route lookup."""
        r = self.routes.get(route_id)
        if r:
            return r
        canonical = self._routes_upper.get(route_id.upper())
        return self.routes.get(canonical) if canonical else None

    def get_routes_for_stop(self, stop_id: str) -> list[Route]:
        # Resolve canonical ID
        canonical = self._stops_upper.get(stop_id.upper(), stop_id)
        route_ids = self.stop_routes.get(canonical, set())
        return [self.routes[rid] for rid in route_ids if rid in self.routes]

    def search_stops(self, query: str, limit: int = 5) -> list[Stop]:
        if not query:
            return []
        q = query.lower()
        
        # 1. Exact match by code or ID
        exact = [s for s in self.stops.values() if q in s.stop_id.lower() or (s.stop_code and q in s.stop_code.lower())]
        if exact:
            exact.sort(key=lambda s: len(s.stop_id))
            return exact[:limit]
            
        # 2. Fuzzy match by stop name
        names = {s.stop_id: s.stop_name for s in self.stops.values()}
        # process.extract on a dict returns a list of tuples: (matched_value, score, key)
        results = process.extract(query, names, scorer=fuzz.WRatio, limit=limit)
        
        # Filter for decent matches (score > 50) and map back using the key
        return [self.stops[r[2]] for r in results if r[1] > 50 and r[2] in self.stops]

    def get_scheduled_arrivals(self, stop_id: str, day_of_week: str, current_seconds: int, duration_seconds: int = None) -> list[dict]:
        if stop_id not in self.stop_times:
            return []
        arrivals = []
        tz_name = settings.get_config("AGENCY_TZ", "UTC")
        agency_tz = ZoneInfo(tz_name)
        for secs, tid in self.stop_times[stop_id]:
            if secs < current_seconds:
                continue
            if duration_seconds and secs > (current_seconds + duration_seconds):
                break
            trip = self.trips.get(tid)
            if not trip:
                continue
            svc = self.calendar.get(trip["service_id"])
            if not svc or svc.get(day_of_week) != 1:
                continue
            if "start_date" in svc and "end_date" in svc:
                today = datetime.now(agency_tz).strftime("%Y%m%d")
                if not (svc["start_date"] <= today <= svc["end_date"]):
                    continue
            arrivals.append({
                "time_seconds": secs,
                "route_id": trip["route_id"],
                "headsign": trip["headsign"],
            })
        return arrivals

    def nearby_stops(self, lat: float, lon: float, radius_km: float = 0.5, limit: int = 10) -> list[dict]:
        radius_km = min(radius_km, 5.0)
        def haversine(lat1, lon1, lat2, lon2):
            R = 6371
            dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        nearby = []
        for s in self.stops.values():
            d = haversine(lat, lon, s.stop_lat, s.stop_lon)
            if d <= radius_km:
                nearby.append({"stop": s, "distance_km": round(d, 3)})
        nearby.sort(key=lambda x: x["distance_km"])
        return nearby[:limit]


# ── Singleton ──

_service: Optional[StopService] = None

def get_stop_service() -> StopService:
    """Get the stop service singleton. Call `await load_from_db()` to populate."""
    global _service
    if _service is None:
        _service = StopService()
    return _service
