"""
CityBus Background Worker — entry point.

Runs a continuous loop that:
  1. Fetches GTFS-RT feed every WORKER_POLL_INTERVAL seconds
  2. Updates Redis arrival cache
  3. Updates vehicle position cache
  4. Processes active subscriptions and sends Telegram notifications

  python main_worker.py
"""

import asyncio

from citybus.config import settings
from citybus.db.mongo import init_db
from citybus.services.stop_service import get_stop_service
from citybus.worker.arrival_engine import update_arrival_cache, update_vehicle_cache
from citybus.worker.notifier import process_notifications
from citybus.logging.logger import get_logger, log_error

logger = get_logger()


async def worker_loop():
    """Main worker loop."""
    logger.info("Initializing worker...")

    # Init MongoDB indexes
    await init_db()

    # Pre-load GTFS
    svc = get_stop_service()
    await svc.load_from_db()
    logger.info(f"Loaded {len(svc.stops)} stops and {len(svc.routes)} routes")

    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — notifications will be skipped")

    interval = settings.WORKER_POLL_INTERVAL
    logger.info(f"Worker started — polling every {interval}s")

    while True:
        try:
            # 1. Update arrival cache
            stops_cached = await update_arrival_cache()

            # 2. Update vehicle positions
            vehicles_cached = await update_vehicle_cache()

            # 3. Process notifications
            sent = 0
            if token:
                sent = await process_notifications(token)

            if sent > 0:
                logger.info(f"Sent {sent} notifications")

        except Exception as e:
            await log_error(
                service="worker",
                error_type=type(e).__name__,
                message=str(e),
            )

        await asyncio.sleep(interval)


def main():
    print("Starting CityBus background worker...")
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
