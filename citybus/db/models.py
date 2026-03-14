"""
Pydantic models for all MongoDB collections.
"""

from datetime import datetime, timezone
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict
import uuid


# ── Users ──

class User(BaseModel):
    """Telegram User."""
    id: int = Field(alias="_id")  # Telegram user ID
    username: Optional[str] = None
    role: Literal["user", "admin"] = "user"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    favorites: list[str] = Field(default_factory=list)  # List of stop_ids
    is_banned: bool = False

    model_config = ConfigDict(populate_by_name=True)


# ── Subscriptions ──

class Subscription(BaseModel):
    """User tracking subscription."""
    id: str = Field(alias="_id", default_factory=lambda: f"sub_{uuid.uuid4().hex}")
    user_id: int
    stop_id: str
    route_id: str  # specific route_id or "ALL"
    frequency: int  # in seconds
    status: Literal["active", "stopped", "expired"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_sent: Optional[datetime] = None
    sent_count: int = 0
    
    model_config = ConfigDict(populate_by_name=True)


# ── API Keys ──

class ApiKey(BaseModel):
    """API key for public endpoints."""
    id: str = Field(alias="_id")  # e.g., 'cb_xxxxx'
    owner: str  # email or name
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rate_limit: str = "100/minute"
    is_active: bool = True
    requests_today: int = 0
    last_request_date: str = ""  # YYYY-MM-DD
    last_used: Optional[datetime] = None

    model_config = ConfigDict(populate_by_name=True)


# ── GTFS Static ──

class Stop(BaseModel):
    """GTFS Stop."""
    stop_id: str = Field(alias="_id")
    stop_code: Optional[str] = None
    stop_name: str
    stop_lat: float
    stop_lon: float
    city_id: str = "default"

    model_config = ConfigDict(populate_by_name=True)


class Route(BaseModel):
    """GTFS Route."""
    route_id: str = Field(alias="_id")
    route_short_name: str
    route_long_name: str
    route_desc: Optional[str] = None
    route_color: Optional[str] = None
    route_text_color: Optional[str] = None
    city_id: str = "default"

    model_config = ConfigDict(populate_by_name=True)


class Trip(BaseModel):
    """GTFS Trip."""
    trip_id: str = Field(alias="_id")
    route_id: str
    service_id: str
    trip_headsign: Optional[str] = None
    direction_id: Optional[int] = None
    city_id: str = "default"

    model_config = ConfigDict(populate_by_name=True)


class StopTime(BaseModel):
    """GTFS Stop Time."""
    # Using composite ID generated downstream for actual mongo insertion, or let mongo auto-generate _id.
    trip_id: str
    arrival_time: str
    departure_time: str
    stop_id: str
    stop_sequence: int
    arrival_time_seconds: int
    city_id: str = "default"

    model_config = ConfigDict(populate_by_name=True)


class Calendar(BaseModel):
    """GTFS Calendar."""
    service_id: str = Field(alias="_id")
    monday: int
    tuesday: int
    wednesday: int
    thursday: int
    friday: int
    saturday: int
    sunday: int
    start_date: str
    end_date: str
    city_id: str = "default"

    model_config = ConfigDict(populate_by_name=True)


# ── Logging ──

class GeneralLog(BaseModel):
    """General telemetry & command logs."""
    id: str = Field(alias="_id", default_factory=lambda: uuid.uuid4().hex)
    command: Optional[str] = None
    user_id: Optional[int] = None
    params: Optional[dict] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "ok"

    model_config = ConfigDict(populate_by_name=True)


class ErrorLog(BaseModel):
    """System error logs."""
    id: str = Field(alias="_id", default_factory=lambda: uuid.uuid4().hex)
    service: str  # e.g., "worker.notifier", "api.arrivals", "bot.search"
    error_type: str
    message: str
    stack_trace: Optional[str] = None
    context: Optional[dict] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal["new", "resolved", "ignored"] = "new"

    model_config = ConfigDict(populate_by_name=True)


# ── Admin Actions ──

class AdminAction(BaseModel):
    """Audit logs for admin actions."""
    id: str = Field(alias="_id", default_factory=lambda: uuid.uuid4().hex)
    admin_id: int
    action: str
    target: str
    details: Optional[dict] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True)
