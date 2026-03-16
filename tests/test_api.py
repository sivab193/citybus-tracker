"""
Tests for the CityBus REST API (new architecture).
"""

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB_NAME", "citybus_test")

from citybus.api.main import create_api
from citybus.db.models import Stop, Route

app = create_api()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def admin_headers():
    from citybus.config import settings
    return {"X-Admin-Key": settings.get_config("ADMIN_API_KEY")}


def _stop(sid="BUS215", name="CityBus Center"):
    return Stop(stop_id=sid, stop_code=sid, stop_name=name, stop_lat=40.42, stop_lon=-86.92)


def _route(rid="21", short="21", long="Purdue West"):
    return Route(route_id=rid, route_short_name=short, route_long_name=long, route_color="0000FF")


# ── Health ──

class TestHealth:
    @patch("citybus.services.stop_service.get_stop_service")
    def test_root(self, mock_svc, client):
        svc = MagicMock()
        svc.stops = {"BUS215": _stop()}
        svc.routes = {"21": _route()}
        mock_svc.return_value = svc
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    @patch("citybus.api.routes.get_stop_service")
    def test_health_endpoint(self, mock_svc, client):
        svc = MagicMock()
        svc.stops = {"BUS215": _stop()}
        svc.routes = {"21": _route()}
        mock_svc.return_value = svc
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200


# ── Auth ──

class TestAuth:
    def test_missing_api_key(self, client):
        resp = client.get("/api/v1/stops/BUS215")
        assert resp.status_code == 401

    @patch("citybus.api.routes.get_db")
    def test_signup(self, mock_db, client):
        db = MagicMock()
        db.api_keys.insert_one = AsyncMock()
        mock_db.return_value = db
        resp = client.post("/api/v1/auth/signup", json={"owner": "test@example.com"})
        assert resp.status_code == 200
        assert "api_key" in resp.json()


# ── Stops (with auth mock) ──

class TestStops:
    @patch("citybus.api.auth.get_db")
    @patch("citybus.api.routes.get_stop_service")
    def test_get_stop_found(self, mock_svc, mock_auth_db, client):
        # Mock auth
        auth_db = MagicMock()
        auth_db.api_keys.find_one = AsyncMock(return_value={"_id": "cb_test", "is_active": True, "owner": "t"})
        auth_db.api_keys.update_one = AsyncMock()
        mock_auth_db.return_value = auth_db
        # Mock service
        svc = MagicMock()
        s = _stop()
        svc.get_stop.return_value = s
        svc.get_routes_for_stop.return_value = [_route()]
        mock_svc.return_value = svc
        resp = client.get("/api/v1/stops/BUS215", headers={"X-API-Key": "cb_test"})
        assert resp.status_code == 200

    @patch("citybus.api.auth.get_db")
    @patch("citybus.api.routes.get_stop_service")
    def test_get_stop_not_found(self, mock_svc, mock_auth_db, client):
        auth_db = MagicMock()
        auth_db.api_keys.find_one = AsyncMock(return_value={"_id": "cb_test", "is_active": True, "owner": "t"})
        auth_db.api_keys.update_one = AsyncMock()
        mock_auth_db.return_value = auth_db
        svc = MagicMock()
        svc.get_stop.return_value = None
        mock_svc.return_value = svc
        resp = client.get("/api/v1/stops/NOPE", headers={"X-API-Key": "cb_test"})
        assert resp.status_code == 404


# ── Admin ──

class TestAdmin:
    @patch("citybus.api.admin_routes.count_users", new_callable=AsyncMock, return_value=5)
    @patch("citybus.api.admin_routes.list_users", new_callable=AsyncMock, return_value=[])
    def test_list_users(self, mock_list, mock_count, client, admin_headers):
        resp = client.get("/admin/users", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] == 5

    def test_admin_no_key(self, client):
        resp = client.get("/admin/users")
        assert resp.status_code == 403

    @patch("citybus.api.admin_routes.get_db")
    def test_stats(self, mock_db, client, admin_headers):
        db = MagicMock()
        db.users.count_documents = AsyncMock(return_value=10)
        db.subscriptions.count_documents = AsyncMock(return_value=3)
        db.api_keys.count_documents = AsyncMock(return_value=2)
        db.logs_errors.count_documents = AsyncMock(return_value=1)
        mock_db.return_value = db
        resp = client.get("/admin/stats", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["users"] == 10
