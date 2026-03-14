"""
FastAPI application factory and error-logging middleware.
"""

import time
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from citybus.db.mongo import init_db
from citybus.logging.logger import log_error
from citybus.api.routes import router as public_router
from citybus.api.admin_routes import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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

    # Root health
    @app.get("/", tags=["Health"])
    async def root():
        from citybus.services.stop_service import get_stop_service
        svc = get_stop_service()
        return {
            "service": "CityBus GTFS API",
            "version": "2.0.0",
            "status": "healthy",
            "data": {"stops": len(svc.stops), "routes": len(svc.routes)},
            "docs": "/docs",
        }

    return app
