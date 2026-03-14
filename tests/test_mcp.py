"""
Tests for the CityBus MCP Server (new architecture).
Tests call the MCP tool functions directly with mocked services.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from citybus.db.models import Stop, Route


def _stop(sid="BUS215", name="CityBus Center", lat=40.42, lon=-86.92):
    return Stop(stop_id=sid, stop_code=sid, stop_name=name, stop_lat=lat, stop_lon=lon)


def _route(rid="21", short="21", long="Purdue West"):
    return Route(route_id=rid, route_short_name=short, route_long_name=long, route_color="0000FF")


def _mock_svc(stops=None, routes=None, stop_routes=None, route_stops=None):
    svc = MagicMock()
    svc.load_from_db = AsyncMock()
    stops = stops or {}
    routes = routes or {}
    svc.stops = stops
    svc.routes = routes
    svc.route_stops = route_stops or {}
    svc.get_stop.side_effect = lambda sid: stops.get(sid)
    svc.get_route.side_effect = lambda rid: routes.get(rid)
    svc.get_routes_for_stop.side_effect = lambda sid: [
        routes[rid] for rid in (stop_routes or {}).get(sid, set()) if rid in routes
    ]
    svc.search_stops.side_effect = lambda q, limit=5: list(stops.values())[:limit]
    return svc


class TestSearchStops:
    @pytest.mark.anyio
    @patch("citybus.mcp.server.get_stop_service")
    async def test_returns_results(self, mock_svc):
        from citybus.mcp.server import search_stops
        mock_svc.return_value = _mock_svc(
            stops={"BUS215": _stop()}, routes={"21": _route()},
            stop_routes={"BUS215": {"21"}},
        )
        results = await search_stops("CityBus", limit=5)
        assert len(results) == 1
        assert results[0]["stop_id"] == "BUS215"

    @pytest.mark.anyio
    @patch("citybus.mcp.server.get_stop_service")
    async def test_empty(self, mock_svc):
        from citybus.mcp.server import search_stops
        mock_svc.return_value = _mock_svc()
        assert await search_stops("nonexistent") == []

    @pytest.mark.anyio
    @patch("citybus.mcp.server.get_stop_service")
    async def test_limit_caps_at_20(self, mock_svc):
        from citybus.mcp.server import search_stops
        svc = _mock_svc()
        mock_svc.return_value = svc
        await search_stops("test", limit=100)
        svc.search_stops.assert_called_once_with("test", limit=20)


class TestGetStop:
    @pytest.mark.anyio
    @patch("citybus.mcp.server.get_stop_service")
    async def test_found(self, mock_svc):
        from citybus.mcp.server import get_stop
        mock_svc.return_value = _mock_svc(
            stops={"BUS215": _stop()}, routes={"21": _route()},
            stop_routes={"BUS215": {"21"}},
        )
        result = await get_stop("BUS215")
        assert result["stop_name"] == "CityBus Center"

    @pytest.mark.anyio
    @patch("citybus.mcp.server.get_stop_service")
    async def test_not_found(self, mock_svc):
        from citybus.mcp.server import get_stop
        mock_svc.return_value = _mock_svc()
        assert "error" in await get_stop("NOPE")


class TestGetRoutes:
    @pytest.mark.anyio
    @patch("citybus.mcp.server.get_stop_service")
    async def test_returns_all(self, mock_svc):
        from citybus.mcp.server import get_routes
        mock_svc.return_value = _mock_svc(routes={
            "21": _route("21"), "4B": _route("4B", "4B", "Salisbury"),
        })
        results = await get_routes()
        assert len(results) == 2


class TestGetArrivals:
    @pytest.mark.anyio
    @patch("citybus.mcp.server.fetch_trip_updates")
    @patch("citybus.mcp.server.get_stop_service")
    async def test_stop_not_found(self, mock_svc, mock_fetch):
        from citybus.mcp.server import get_arrivals
        mock_svc.return_value = _mock_svc()
        result = await get_arrivals("NOPE")
        assert "error" in result
