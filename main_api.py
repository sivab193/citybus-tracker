"""
CityBus API Server — entry point.

  python main_api.py
"""

import uvicorn
from citybus.config import settings
from citybus.api.main import create_api

app = create_api()

if __name__ == "__main__":
    print(f"\nStarting CityBus API on port {settings.API_PORT}...")
    print(f"Docs: http://localhost:{settings.API_PORT}/docs")

    # Uvicorn will automatically call the lifespan events when the app starts/stops
    uvicorn.run("main_api:app", host="0.0.0.0", port=settings.API_PORT, reload=True)
