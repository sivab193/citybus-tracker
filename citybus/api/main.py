"""
FastAPI application factory and error-logging middleware.
"""

import time
import traceback
from contextlib import asynccontextmanager

import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from citybus.db.mongo import init_db
from citybus.logging.logger import log_error

# Global set to hold strong references to background tasks
# to prevent garbage collection mid-execution.
_background_tasks = set()
from citybus.api.routes import router as public_router
from citybus.api.admin_routes import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    
    # Load GTFS static data into memory for the API
    from citybus.config import settings
    from citybus.services.stop_service import get_stop_service
    svc = get_stop_service()
    await svc.load_from_db(city_id=settings.get_config("CITY_ID", "default"))
    
    yield


def create_api() -> FastAPI:
    """Build and configure the FastAPI application."""

    app = FastAPI(
        title="CityBus GTFS API",
        description=(
            "Public API for CityBus of Greater Lafayette, Indiana. "
            "Access static GTFS data, real-time arrivals, vehicle positions, "
            "and service alerts."
        ),
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def global_request_tracker(request: Request, call_next):
        """Increments a persistent request counter in MongoDB for actual API usage."""
        from citybus.db.mongo import get_db
        path = request.url.path
        
        response = await call_next(request)

        # Only count functional API requests
        # Filter: starts with /api/ AND is NOT the dashboard stats endpoint
        if path.startswith("/api/") and not path.endswith("/meta/dashboard-stats"):
            async def update_stats():
                db = get_db()
                if db is not None:
                    try:
                        await db.stats.update_one(
                            {"_id": "global"},
                            {"$inc": {"total_requests": 1}},
                            upsert=True
                        )
                    except Exception:
                        pass

            # Using asyncio.create_task to run the DB update concurrently.
            # We retain a strong reference to avoid the task being garbage
            # collected mid-execution by the event loop.
            task = asyncio.create_task(update_stats())
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)

        return response

    # Error-logging middleware
    @app.middleware("http")
    async def error_logging_middleware(request: Request, call_next):
        start = time.time()
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            await log_error(
                service="api",
                error_type=type(exc).__name__,
                message=str(exc),
                stack_trace=traceback.format_exc(),
                context={"path": str(request.url), "method": request.method},
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )

    # Routers
    app.include_router(public_router)
    app.include_router(admin_router)

    # Static files mounting
    import os
    static_path = os.path.join(os.path.dirname(__file__), "static")
    if not os.path.exists(static_path):
        os.makedirs(static_path)
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    # Root: Serve Dashboard
    @app.get("/", include_in_schema=False)
    async def dashboard():
        """Serve the high-fidelity dashboard."""
        return FileResponse(os.path.join(static_path, "index.html"))

    # Health check (moved to /health specifically if not already there, 
    # but the user might still want the old JSON root at /status or similar)
    @app.get("/health", tags=["Health"])
    async def health():
        from citybus.services.stop_service import get_stop_service
        svc = get_stop_service()
        return {
            "service": "CityBus GTFS API",
            "version": "2.0.0",
            "status": "healthy",
            "data": {"stops": len(svc.stops), "routes": len(svc.routes)},
        }

    return app
