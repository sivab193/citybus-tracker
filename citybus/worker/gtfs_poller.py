"""
GTFS Realtime poller — fetches feeds from CityBus every WORKER_POLL_INTERVAL seconds.
"""

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests
from google.transit import gtfs_realtime_pb2

from citybus.config import settings


@dataclass
class Arrival:
    route_id: str
    trip_id: str
    stop_id: str
    arrival_time: Optional[datetime]
    delay_seconds: int
    minutes_until: int
    trip_headsign: str = ""


@dataclass
class VehiclePosition:
    vehicle_id: str
    route_id: str
    trip_id: str
    latitude: float
    longitude: float
    bearing: Optional[float]
    speed: Optional[float]
    timestamp: Optional[datetime]


@dataclass
class ServiceAlert:
    alert_id: str
    header_text: str
    description_text: str
    cause: str
    effect: str
    active_periods: list
    informed_entities: list


def fetch_trip_updates() -> gtfs_realtime_pb2.FeedMessage:
    url = settings.get_config("GTFS_RT_TRIP_UPDATES_URL", "https://bus.gocitybus.com/GTFSRT/GTFS_TripUpdates.pb")
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)
    return feed


def fetch_vehicle_positions() -> gtfs_realtime_pb2.FeedMessage:
    url = settings.get_config("GTFS_RT_VEHICLE_POSITIONS_URL", "https://bus.gocitybus.com/GTFSRT/GTFS_VehiclePositions.pb")
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)
    return feed


def fetch_service_alerts() -> gtfs_realtime_pb2.FeedMessage:
    url = settings.get_config("GTFS_RT_SERVICE_ALERTS_URL", "https://bus.gocitybus.com/GTFSRT/GTFS_ServiceAlerts.pb")
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)
    return feed


def parse_arrivals_for_stop(feed: gtfs_realtime_pb2.FeedMessage, stop_id: str, route_id: str = None) -> list[Arrival]:
    """Parse a trip-updates feed and extract arrivals for a specific stop."""
    arrivals = []
    now = int(time.time())
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        r_id = tu.trip.route_id
        t_id = tu.trip.trip_id
        if route_id and r_id != route_id:
            continue
        for stu in tu.stop_time_update:
            if stu.stop_id != stop_id:
                continue
            ts = None
            delay = 0
            if stu.HasField("arrival"):
                ts = stu.arrival.time if stu.arrival.HasField("time") else None
                delay = stu.arrival.delay if stu.arrival.HasField("delay") else 0
            elif stu.HasField("departure"):
                ts = stu.departure.time if stu.departure.HasField("time") else None
                delay = stu.departure.delay if stu.departure.HasField("delay") else 0
            if ts is None:
                continue
            mins = (ts - now) // 60
            if mins < 0 or mins > 120:
                continue
            arrivals.append(Arrival(
                route_id=r_id, trip_id=t_id, stop_id=stop_id,
                arrival_time=datetime.fromtimestamp(ts),
                delay_seconds=delay, minutes_until=mins,
            ))
    arrivals.sort(key=lambda a: a.minutes_until)
    return arrivals


def parse_all_arrivals(feed: gtfs_realtime_pb2.FeedMessage) -> dict[str, dict[str, int]]:
    """Parse ALL arrivals from a feed.

    Returns:
        dict of stop_id -> {route_id: seconds_until_arrival, ...}
        (only the soonest arrival per route per stop)
    """
    result: dict[str, dict[str, int]] = {}
    now = int(time.time())
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        r_id = tu.trip.route_id
        for stu in tu.stop_time_update:
            ts = None
            if stu.HasField("arrival") and stu.arrival.HasField("time"):
                ts = stu.arrival.time
            elif stu.HasField("departure") and stu.departure.HasField("time"):
                ts = stu.departure.time
            if ts is None:
                continue
            secs = ts - now
            if secs < 0 or secs > 7200:
                continue
            sid = stu.stop_id
            if sid not in result:
                result[sid] = {}
            # Keep only soonest per route
            key = f"route_{r_id}"
            if key not in result[sid] or secs < result[sid][key]:
                result[sid][key] = secs
    return result


def parse_vehicle_positions(feed: gtfs_realtime_pb2.FeedMessage, route_id: str = None) -> list[VehiclePosition]:
    """Parse vehicle positions feed."""
    positions = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle
        v_route = v.trip.route_id if v.HasField("trip") else ""
        v_trip = v.trip.trip_id if v.HasField("trip") else ""
        if route_id and v_route != route_id:
            continue
        if not v.HasField("position"):
            continue
        pos = v.position
        v_id = v.vehicle.id if v.HasField("vehicle") else entity.id
        positions.append(VehiclePosition(
            vehicle_id=v_id, route_id=v_route, trip_id=v_trip,
            latitude=pos.latitude, longitude=pos.longitude,
            bearing=pos.bearing if pos.HasField("bearing") else None,
            speed=pos.speed if pos.HasField("speed") else None,
            timestamp=datetime.fromtimestamp(v.timestamp) if v.timestamp else None,
        ))
    return positions


def parse_service_alerts(feed: gtfs_realtime_pb2.FeedMessage) -> list[ServiceAlert]:
    """Parse service alerts feed."""
    cause_map = {0:"UNKNOWN",1:"OTHER",2:"TECHNICAL_PROBLEM",3:"STRIKE",4:"DEMONSTRATION",
                 5:"ACCIDENT",6:"HOLIDAY",7:"WEATHER",8:"MAINTENANCE",9:"CONSTRUCTION",
                 10:"POLICE_ACTIVITY",11:"MEDICAL_EMERGENCY"}
    effect_map = {0:"UNKNOWN",1:"NO_SERVICE",2:"REDUCED_SERVICE",3:"SIGNIFICANT_DELAYS",
                  4:"DETOUR",5:"ADDITIONAL_SERVICE",6:"MODIFIED_SERVICE",7:"OTHER",8:"STOP_MOVED"}
    alerts = []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        a = entity.alert
        header = a.header_text.translation[0].text if a.header_text and a.header_text.translation else ""
        desc = a.description_text.translation[0].text if a.description_text and a.description_text.translation else ""
        periods = []
        for p in a.active_period:
            periods.append({
                "start": datetime.fromtimestamp(p.start).isoformat() if p.start else None,
                "end": datetime.fromtimestamp(p.end).isoformat() if p.end else None,
            })
        informed = []
        for ie in a.informed_entity:
            e = {}
            if ie.route_id: e["route_id"] = ie.route_id
            if ie.stop_id: e["stop_id"] = ie.stop_id
            if e: informed.append(e)
        alerts.append(ServiceAlert(
            alert_id=entity.id, header_text=header, description_text=desc,
            cause=cause_map.get(a.cause, "UNKNOWN"), effect=effect_map.get(a.effect, "UNKNOWN"),
            active_periods=periods, informed_entities=informed,
        ))
    return alerts


def format_arrival_message(arrival: Arrival, route_name: str = "") -> str:
    """Format an arrival as a user-friendly message."""
    abs_time = arrival.arrival_time.strftime("%I:%M%p").lstrip("0") if arrival.arrival_time else ""
    if arrival.minutes_until == 0:
        t = f"Now ({abs_time})"
    else:
        t = f"{arrival.minutes_until}mins ({abs_time})"
    r = route_name or arrival.route_id
    dest = f" → {arrival.trip_headsign}" if arrival.trip_headsign else ""
    if arrival.delay_seconds > 60:
        return f"🚌 Route {r}{dest}: {t} (delayed {arrival.delay_seconds // 60}min)"
    elif arrival.delay_seconds < -60:
        return f"🚌 Route {r}{dest}: {t} ({abs(arrival.delay_seconds) // 60}min early)"
    return f"🚌 Route {r}{dest}: {t}"
