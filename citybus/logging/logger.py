"""
Structured logging to MongoDB + stdout.
"""

import sys
import traceback
import logging
from datetime import datetime, timezone
from citybus.db.mongo import get_db

# Standard Python logger for stdout
_logger = logging.getLogger("citybus")
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)


def get_logger():
    """Return the stdlib logger for direct use."""
    return _logger


async def log_general(
    command: str = "",
    user_id: int = None,
    params: dict = None,
    response_time_ms: float = 0.0,
    status: str = "ok",
    worker: str = "",
):
    """Write a general log entry to MongoDB and stdout."""
    doc = {
        "timestamp": datetime.now(timezone.utc),
        "user_id": user_id,
        "command": command,
        "params": params or {},
        "response_time_ms": response_time_ms,
        "status": status,
        "worker": worker,
    }
    _logger.info(f"[{worker or 'app'}] {command} user={user_id} {status} {response_time_ms:.0f}ms")
    try:
        db = get_db()
        await db.logs_general.insert_one(doc)
    except Exception as e:
        _logger.warning(f"Failed to write general log to Mongo: {e}")


async def log_error(
    service: str = "",
    error_type: str = "",
    message: str = "",
    stack_trace: str = "",
    context: dict = None,
):
    """Write an error log entry to MongoDB and stderr."""
    if not stack_trace:
        stack_trace = traceback.format_exc()

    doc = {
        "timestamp": datetime.now(timezone.utc),
        "service": service,
        "error_type": error_type,
        "message": message,
        "stack_trace": stack_trace,
        "context": context or {},
    }
    _logger.error(f"[{service}] {error_type}: {message}")
    try:
        db = get_db()
        await db.logs_errors.insert_one(doc)
    except Exception as e:
        _logger.warning(f"Failed to write error log to Mongo: {e}")
