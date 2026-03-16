"""
Integration tests using a real MongoDB instance and sample GTFS data.
"""

import os
import pytest
from fastapi.testclient import TestClient
from citybus.api.main import create_api

# Ensure test DB is used
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB_NAME", "citybus_test")

app = create_api()

import httpx
import pytest_asyncio

from citybus.db.mongo import close_db

@pytest_asyncio.fixture
async def client():
    """Build an AsyncClient for the app with lifespan support."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture
async def api_key(client):
    """Signup to get an API key for tests."""
    resp = await client.post("/api/v1/auth/signup", json={"owner": "test-integration@example.com"})
    assert resp.status_code == 200
    return resp.json()["api_key"]

@pytest.mark.asyncio
async def test_integration_health(client):
    """Verify health endpoint works with real DB connection."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "stops" in data
    assert "routes" in data

@pytest.mark.asyncio
async def test_integration_stops_load(client, api_key):
    """Verify that stops loaded from GTFS are accessible via API."""
    resp = await client.get("/api/v1/search?query=Center", headers={"X-API-Key": api_key})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)
    if len(data) > 0:
        stop_id = data[0]["stop_id"]
        resp_stop = await client.get(f"/api/v1/stops/{stop_id}", headers={"X-API-Key": api_key})
        assert resp_stop.status_code == 200
        assert resp_stop.json()["data"]["stop_id"] == stop_id

@pytest.mark.asyncio
async def test_integration_route_by_id(client, api_key):
    """Verify that a specific route loaded from GTFS is accessible."""
    # First find a stop that has routes
    resp_search = await client.get("/api/v1/search?query=A", headers={"X-API-Key": api_key})
    assert resp_search.status_code == 200
    stops_data = resp_search.json()["data"]
    
    if not stops_data:
        pytest.skip("No stops found in sample data to test routes")
        
    stop_id = stops_data[0]["stop_id"]
    resp_stop = await client.get(f"/api/v1/stops/{stop_id}", headers={"X-API-Key": api_key})
    assert resp_stop.status_code == 200
    stop_detail = resp_stop.json()
    
    if not stop_detail.get("routes"):
        pytest.skip(f"Stop {stop_id} has no routes in sample data")
        
    route_id = stop_detail["routes"][0]["route_id"]
    
    # Now verify the route lookup
    resp = await client.get(f"/api/v1/routes/{route_id}", headers={"X-API-Key": api_key})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["route_id"] == route_id
    assert "stops" in resp.json()
