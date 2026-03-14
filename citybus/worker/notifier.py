"""
Notification scheduler — processes active subscriptions and sends Telegram updates.
"""

from datetime import datetime, timezone
import requests

from citybus.db.redis import get_arrivals
from citybus.services.subscription_service import (
    get_all_active_subscriptions,
    record_notification,
    cleanup_inactive,
)
from citybus.services.stop_service import get_stop_service
from citybus.logging.logger import get_logger, log_error

logger = get_logger()


async def process_notifications(bot_token: str):
    """Check all active subscriptions and send updates where due.

    This is called by the worker loop. It uses the Telegram Bot API
    directly (HTTP) rather than python-telegram-bot to avoid coupling
    the worker to the bot's event loop.
    """
    subs = await get_all_active_subscriptions()
    if not subs:
        return 0

    sent = 0
    svc = get_stop_service()
    now = datetime.now(timezone.utc)

    for sub in subs:
        try:
            # Check if it's time to send
            last = sub.get("last_sent")
            freq = sub["frequency"]
            if last:
                elapsed = (now - last).total_seconds()
                if elapsed < freq:
                    continue

            stop_id = sub["stop_id"]
            route_id = sub["route_id"]

            # Get arrivals from Redis cache
            cached = await get_arrivals(stop_id)
            if not cached:
                continue

            # Build message
            stop = svc.get_stop(stop_id)
            stop_name = stop.stop_name if stop else stop_id

            lines = [f"🚏 *{stop_name}*\n"]
            route_key = f"route_{route_id}" if route_id != "ALL" else None

            if route_key and route_key in cached:
                secs = cached[route_key]
                route = svc.get_route(route_id)
                r_name = route.route_short_name if route else route_id
                mins = secs // 60
                lines.append(f"🚌 Route {r_name}: {mins} min{'s' if mins != 1 else ''}")
            else:
                # Show all routes
                for key, secs in sorted(cached.items(), key=lambda x: x[1]):
                    r_id = key.replace("route_", "")
                    route = svc.get_route(r_id)
                    r_name = route.route_short_name if route else r_id
                    mins = secs // 60
                    lines.append(f"🚌 Route {r_name}: {mins} min{'s' if mins != 1 else ''}")

            if len(lines) <= 1:
                continue

            # Add timestamp
            t = datetime.now().strftime("%I:%M %p").lstrip("0")
            lines.append(f"\n_Updated at {t}_")

            text = "\n".join(lines)

            # Send via Telegram HTTP API
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            resp = requests.post(url, json={
                "chat_id": sub["user_id"],
                "text": text,
                "parse_mode": "Markdown",
            }, timeout=10)

            if resp.status_code == 200:
                await record_notification(sub["_id"])
                sent += 1
            else:
                logger.warning(f"Telegram send failed for sub {sub['_id']}: {resp.status_code}")

        except Exception as e:
            await log_error(
                service="worker.notifier",
                error_type=type(e).__name__,
                message=str(e),
                context={"subscription_id": sub.get("_id")},
            )

    # Cleanup stale subscriptions
    cleaned = await cleanup_inactive()
    if cleaned:
        logger.info(f"Cleaned up {cleaned} inactive subscriptions")

    return sent
