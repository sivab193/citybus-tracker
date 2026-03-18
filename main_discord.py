"""
CityBus Discord Bot — entry point.

  python main_discord.py
"""

import discord
from discord.ext import commands
import asyncio
import sys

from citybus.config import settings
from citybus.services.stop_service import get_stop_service
from citybus.logging.logger import get_logger

logger = get_logger()

class CityBusDiscord(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        logger.info("Setting up Discord bot...")

        print("Loading GTFS static data from MongoDB...")
        from citybus.db.mongo import init_db
        await init_db()

        from citybus.config import settings
        await settings.get_dynamic_config()

        # ── Acquire Distributed Lock ──
        from citybus.db.redis import acquire_service_lock, renew_service_lock

        if not await acquire_service_lock("discord_bot", timeout=30):
            print("❌ CRITICAL: Another citybus discord bot instance is already running!")
            logger.error("Failed to acquire Redis lock for 'discord_bot'. Terminating.")
            sys.exit(1)

        # Start heartbeat lock renewal in background
        asyncio.create_task(renew_service_lock("discord_bot", timeout=30))
        print("✅ Acquired Redis exclusive instance lock for Discord Bot")

        svc = get_stop_service()
        await svc.load_from_db(city_id="lafayette")
        print(f"Loaded {len(svc.stops)} stops and {len(svc.routes)} routes")

        # Load cog
        await self.load_extension('citybus.discord.commands')

        # Sync tree
        await self.tree.sync()
        logger.info("Bot commands synced")


def main():
    token = settings.DISCORD_BOT_TOKEN
    if not token:
        print("Error: DISCORD_BOT_TOKEN not set in .env")
        return

    print("Starting CityBus Discord bot...")
    bot = CityBusDiscord()
    bot.run(token)


if __name__ == "__main__":
    main()
