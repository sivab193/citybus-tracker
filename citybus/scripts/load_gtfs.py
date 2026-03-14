"""
Script to load GTFS static data from a .zip file into MongoDB.

Usage:
    python citybus/scripts/load_gtfs.py <path_to_zip> [city_id]
"""

import sys
import os
import zipfile
import csv
import asyncio
from pymongo import UpdateOne, InsertOne

from citybus.db.mongo import init_db, get_db

BATCH_SIZE = 5000


def _parse_time_to_seconds(t_str: str) -> int:
    """Convert GTFS HH:MM:SS to seconds past midnight. Handles >24h times."""
    try:
        parts = t_str.strip().split(":")
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2])
        return h * 3600 + m * 60 + s
    except Exception:
        return 0


async def load_gtfs_to_mongo(zip_path: str, city_id: str = "default"):
    print(f"Loading GTFS from {zip_path} for city '{city_id}'...")
    
    if not os.path.exists(zip_path):
        print(f"Error: File {zip_path} not found.")
        sys.exit(1)

    await init_db()
    db = get_db()
    
    with zipfile.ZipFile(zip_path, "r") as z:
        # Load Stops
        if "stops.txt" in z.namelist():
            print("Loading stops.txt...")
            stops = []
            with z.open("stops.txt") as f:
                reader = csv.DictReader(f.read().decode("utf-8-sig").splitlines())
                for row in reader:
                    stops.append(UpdateOne(
                        {"_id": row["stop_id"]},
                        {"$set": {
                            "stop_code": row.get("stop_code", ""),
                            "stop_name": row["stop_name"],
                            "stop_lat": float(row["stop_lat"]),
                            "stop_lon": float(row["stop_lon"]),
                            "city_id": city_id,
                        }},
                        upsert=True
                    ))
            if stops:
                await db.stops.bulk_write(stops)
                print(f" -> Inserted/Updated {len(stops)} stops")

        # Load Routes
        if "routes.txt" in z.namelist():
            print("Loading routes.txt...")
            routes = []
            with z.open("routes.txt") as f:
                reader = csv.DictReader(f.read().decode("utf-8-sig").splitlines())
                for row in reader:
                    routes.append(UpdateOne(
                        {"_id": row["route_id"]},
                        {"$set": {
                            "route_short_name": row.get("route_short_name", ""),
                            "route_long_name": row.get("route_long_name", ""),
                            "route_desc": row.get("route_desc"),
                            "route_color": row.get("route_color"),
                            "route_text_color": row.get("route_text_color"),
                            "city_id": city_id,
                        }},
                        upsert=True
                    ))
            if routes:
                await db.routes.bulk_write(routes)
                print(f" -> Inserted/Updated {len(routes)} routes")

        # Load Calendar
        if "calendar.txt" in z.namelist():
            print("Loading calendar.txt...")
            cals = []
            with z.open("calendar.txt") as f:
                reader = csv.DictReader(f.read().decode("utf-8-sig").splitlines())
                for row in reader:
                    cals.append(UpdateOne(
                        {"_id": row["service_id"]},
                        {"$set": {
                            "monday": int(row.get("monday", 0)),
                            "tuesday": int(row.get("tuesday", 0)),
                            "wednesday": int(row.get("wednesday", 0)),
                            "thursday": int(row.get("thursday", 0)),
                            "friday": int(row.get("friday", 0)),
                            "saturday": int(row.get("saturday", 0)),
                            "sunday": int(row.get("sunday", 0)),
                            "start_date": row.get("start_date", ""),
                            "end_date": row.get("end_date", ""),
                            "city_id": city_id,
                        }},
                        upsert=True
                    ))
            if cals:
                await db.calendar.bulk_write(cals)
                print(f" -> Inserted/Updated {len(cals)} calendar entries")

        # Load Trips
        if "trips.txt" in z.namelist():
            print("Loading trips.txt...")
            # We will completely drop and reload trips for this city since they can change entirely
            await db.trips.delete_many({"city_id": city_id})
            trips = []
            trip_count = 0
            with z.open("trips.txt") as f:
                reader = csv.DictReader(f.read().decode("utf-8-sig").splitlines())
                for row in reader:
                    tid = row["trip_id"]
                    t = {
                        "_id": tid,
                        "route_id": row.get("route_id", ""),
                        "service_id": row.get("service_id", ""),
                        "trip_headsign": row.get("trip_headsign"),
                        "direction_id": int(row["direction_id"]) if row.get("direction_id") else None,
                        "city_id": city_id,
                    }
                    trips.append(InsertOne(t))
                    if len(trips) >= BATCH_SIZE:
                        await db.trips.bulk_write(trips)
                        trip_count += len(trips)
                        trips = []
            if trips:
                await db.trips.bulk_write(trips)
                trip_count += len(trips)
            print(f" -> Inserted {trip_count} trips")

        # Load Stop Times
        if "stop_times.txt" in z.namelist():
            print("Loading stop_times.txt...")
            await db.stop_times.delete_many({"city_id": city_id})
            st_count = 0
            sts = []
            with z.open("stop_times.txt") as f:
                reader = csv.DictReader(f.read().decode("utf-8-sig").splitlines())
                for row in reader:
                    arr = row.get("arrival_time", "")
                    st = {
                        "trip_id": row.get("trip_id", ""),
                        "arrival_time": arr,
                        "departure_time": row.get("departure_time", ""),
                        "stop_id": row.get("stop_id", ""),
                        "stop_sequence": int(row.get("stop_sequence", 0)),
                        "arrival_time_seconds": _parse_time_to_seconds(arr),
                        "city_id": city_id,
                    }
                    sts.append(InsertOne(st))
                    if len(sts) >= BATCH_SIZE:
                        await db.stop_times.bulk_write(sts)
                        st_count += len(sts)
                        sts = []
            if sts:
                await db.stop_times.bulk_write(sts)
                st_count += len(sts)
            print(f" -> Inserted {st_count} stop times")

    # Create indexes for the new collections
    print("Creating indexes...")
    await db.trips.create_index("route_id")
    await db.trips.create_index("service_id")
    await db.stop_times.create_index("stop_id")
    await db.stop_times.create_index("trip_id")
    await db.stop_times.create_index([("stop_id", 1), ("arrival_time_seconds", 1)])
    
    print("✅ GTFS Data loaded successfully!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python load_gtfs.py <zip_file> [city_id]")
        sys.exit(1)
    
    zip_path = sys.argv[1]
    city = sys.argv[2] if len(sys.argv) > 2 else "default"
    
    asyncio.run(load_gtfs_to_mongo(zip_path, city))
