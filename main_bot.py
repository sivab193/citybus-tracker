"""
CityBus Telegram Bot — entry point.

  python main_bot.py
"""

from telegram.ext import Application

from citybus.config import settings
from citybus.services.stop_service import get_stop_service
from citybus.bot.handlers import register_handlers, set_bot_commands
from citybus.logging.logger import get_logger

logger = get_logger()


async def post_init(app: Application):
    """Runs after bot starts — register commands."""
    await set_bot_commands(app)
    logger.info("Bot commands registered for autocomplete")

    print("Loading GTFS static data from MongoDB...")
    from citybus.db.mongo import init_db
    await init_db()
    
    from citybus.config import settings
    await settings.get_dynamic_config()
    
    # ── Acquire Distributed Lock ──
    from citybus.db.redis import acquire_service_lock, renew_service_lock
    import asyncio
    import sys
    
    if not await acquire_service_lock("bot", timeout=30):
        print("❌ CRITICAL: Another citybus-bot instance is already running!")
        logger.error("Failed to acquire Redis lock for 'bot'. Terminating.")
        sys.exit(1)
        
    # Start heartbeat lock renewal in background
    asyncio.create_task(renew_service_lock("bot", timeout=30))
    print("✅ Acquired Redis exclusive instance lock for Bot")

    svc = get_stop_service()
    await svc.load_from_db(city_id="lafayette")
    print(f"Loaded {len(svc.stops)} stops and {len(svc.routes)} routes")


def main():
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not set in .env")
        print("  1. Create a bot with @BotFather")
        print("  2. Add TELEGRAM_BOT_TOKEN to your .env file")
        return



    print("Starting CityBus Telegram bot...")
    app = Application.builder().token(token).post_init(post_init).build()
    register_handlers(app)

    from telegram import Update
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
