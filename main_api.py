"""
CityBus API Server — entry point.

  python main_api.py
"""

import uvicorn
from citybus.config import settings
from citybus.api.main import create_api
from citybus.services.stop_service import get_stop_service

app = create_api()

if __name__ == "__main__":
    print("Loading GTFS static data...")
    svc = get_stop_service()
    print(f"Loaded {len(svc.stops)} stops and {len(svc.routes)} routes")
    print(f"\nStarting CityBus API on port {settings.API_PORT}...")
    print(f"Docs: http://localhost:{settings.API_PORT}/docs")

    uvicorn.run("main_api:app", host="0.0.0.0", port=settings.API_PORT, reload=True)
