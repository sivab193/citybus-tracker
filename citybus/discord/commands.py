import re
import discord
from discord import app_commands
from discord.ext import commands

from citybus.services.user_service import (
    get_or_create_user, check_registered_username_exists, set_registered_username,
    add_favorite, remove_favorite
)
from citybus.services.subscription_service import get_active_subscriptions, stop_user_subscriptions
from citybus.services.stop_service import get_stop_service
from citybus.worker.gtfs_poller import fetch_trip_updates, parse_arrivals_for_stop, format_arrival_message
from citybus.db.redis import get_arrivals
from citybus.bot.commands import get_next_bus_info
from datetime import datetime
from citybus.discord.views import SearchFlowView, TrackFlowView

class CityBusCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _ensure_discord_user(self, interaction: discord.Interaction) -> dict | None:
        """Ensure the user exists and has a registered username."""
        user = interaction.user
        db_user = await get_or_create_user(user.id, username=user.name, platform="discord")
        if not db_user.get("registered_username"):
            await interaction.response.send_message("⚠️ You must register a unique username first. Please use `/register`.", ephemeral=True)
            return None
        return db_user

    @app_commands.command(name="register", description="Register a unique username")
    async def register(self, interaction: discord.Interaction, username: str):
        username_input = username.strip().lower()
        if not re.match(r"^[a-z0-9]{3,15}$", username_input):
            await interaction.response.send_message("❌ Username must be 3-15 characters and contain only letters and numbers.", ephemeral=True)
            return

        if await check_registered_username_exists(username_input):
            await interaction.response.send_message(f"❌ Username '{username_input}' is already taken.", ephemeral=True)
            return

        await get_or_create_user(interaction.user.id, username=interaction.user.name, platform="discord")
        await set_registered_username(interaction.user.id, username_input)
        await interaction.response.send_message(f"✅ Registration complete! Welcome to CityBus Tracker, {username_input}!", ephemeral=True)

    @app_commands.command(name="status", description="Show active subscriptions")
    async def status(self, interaction: discord.Interaction):
        user = await self._ensure_discord_user(interaction)
        if not user:
            return

        subs = await get_active_subscriptions(interaction.user.id)
        if not subs:
            await interaction.response.send_message("You have no active subscriptions.\nUse `/search` to start.", ephemeral=True)
            return

        svc = get_stop_service()
        lines = ["📊 **Active Subscriptions:**\n"]
        for s in subs:
            stop = svc.get_stop(s["stop_id"])
            route = svc.get_route(s["route_id"]) if s["route_id"] != "ALL" else None
            freq = f"{s['frequency']}s" if s['frequency'] < 60 else f"{s['frequency'] // 60}m"
            lines.append(
                f"• {stop.stop_name if stop else s['stop_id']} "
                f"| {route.route_short_name if route else 'All'} "
                f"| every {freq} | sent: {s['sent_count']}"
            )
        lines.append("\nUse `/stop` to stop all.")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="stop", description="Stop all notifications")
    async def stop(self, interaction: discord.Interaction):
        user = await self._ensure_discord_user(interaction)
        if not user:
            return
        count = await stop_user_subscriptions(interaction.user.id)
        if count == 0:
            await interaction.response.send_message("No active subscriptions to stop.", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ Stopped {count} subscription(s).", ephemeral=True)

    @app_commands.command(name="favorites", description="View your favorite stops")
    async def favorites(self, interaction: discord.Interaction):
        user = await self._ensure_discord_user(interaction)
        if not user:
            return

        favs = user.get("favorites", [])
        if not favs:
            await interaction.response.send_message("No favorites yet. Use `/fav <stop_id>` to add one.", ephemeral=True)
            return

        svc = get_stop_service()
        lines = ["⭐ **Favorites:**\n"]
        for sid in favs:
            stop = svc.get_stop(sid)
            lines.append(f"• {stop.stop_name if stop else sid} (`{sid}`)")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="fav", description="Add a favorite stop")
    async def fav(self, interaction: discord.Interaction, stop_id: str):
        user = await self._ensure_discord_user(interaction)
        if not user:
            return

        sid = stop_id.upper()
        ok = await add_favorite(interaction.user.id, sid)
        msg = f"⭐ Added `{sid}` to favorites." if ok else f"`{sid}` already in favorites."
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="unfav", description="Remove a favorite stop")
    async def unfav(self, interaction: discord.Interaction, stop_id: str):
        user = await self._ensure_discord_user(interaction)
        if not user:
            return

        sid = stop_id.upper()
        ok = await remove_favorite(interaction.user.id, sid)
        msg = f"Removed `{sid}` from favorites." if ok else f"`{sid}` not in favorites."
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="arrivals", description="Live bus arrivals")
    async def arrivals(self, interaction: discord.Interaction, stop: str):
        user = await self._ensure_discord_user(interaction)
        if not user:
            return

        svc = get_stop_service()
        search_term = stop.strip()
        stop_obj = svc.get_stop(search_term.upper())
        if not stop_obj:
            results = svc.search_stops(search_term, limit=1)
            if results:
                stop_obj = results[0]
            else:
                await interaction.response.send_message(f"Stop '{search_term}' not found.", ephemeral=True)
                return

        await interaction.response.defer(ephemeral=False)

        # Try Redis first
        cached = await get_arrivals(stop_obj.stop_id)
        if cached:
            lines = [f"📍 **{stop_obj.stop_name}**\n"]
            for key, secs in sorted(cached.items(), key=lambda x: x[1])[:5]:
                r_id = key.replace("route_", "")
                route = svc.get_route(r_id)
                r_name = route.route_short_name if route else r_id
                lines.append(f"🚌 Route {r_name}: {secs // 60} min")
            lines.append(f"\n_Updated from cache_")
            await interaction.followup.send("\n".join(lines))
            return

        # Fallback: live fetch
        try:
            from citybus.worker.gtfs_poller import fetch_trip_updates, parse_arrivals_for_stop, format_arrival_message
            # Using to_thread for the sync requests call in fetch_trip_updates
            import asyncio
            feed = await asyncio.to_thread(fetch_trip_updates)
            arrivals_list = parse_arrivals_for_stop(feed, stop_obj.stop_id)
            if not arrivals_list:
                await interaction.followup.send(f"📍 **{stop_obj.stop_name}**\n\nNo upcoming arrivals.")
                return

            lines = [f"📍 **{stop_obj.stop_name}**\n"]
            for arr in arrivals_list[:5]:
                route = svc.get_route(arr.route_id)
                r_name = route.route_short_name if route else arr.route_id
                lines.append(format_arrival_message(arr, r_name))
            lines.append(f"\n_Updated at {datetime.now().strftime('%H:%M')}_")
            await interaction.followup.send("\n".join(lines))
        except Exception as e:
            await interaction.followup.send(f"Failed to fetch arrivals: {e}")

    @app_commands.command(name="search", description="Search for a bus stop")
    async def search(self, interaction: discord.Interaction, query: str):
        user = await self._ensure_discord_user(interaction)
        if not user:
            return

        svc = get_stop_service()
        stops = svc.search_stops(query, limit=25)

        if not stops:
            await interaction.response.send_message(f"No stops found for '{query}'.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"🔍 Found {len(stops)} stops matching '**{query}**':\nSelect a stop to track:",
            view=SearchFlowView(stops),
            ephemeral=True
        )

    @app_commands.command(name="track", description="Quick start notifications for a stop")
    async def track(self, interaction: discord.Interaction, stop: str):
        user = await self._ensure_discord_user(interaction)
        if not user:
            return

        query = stop.strip().lower()
        stop_id = None

        # Check if favorite
        if query.startswith("f") and query[1:].isdigit():
            idx = int(query[1:]) - 1
            favs = user.get("favorites", [])
            if 0 <= idx < len(favs):
                stop_id = favs[idx]
            else:
                await interaction.response.send_message(f"Favorite f{idx+1} not found. Check `/favorites`.", ephemeral=True)
                return
        else:
            stop_id = query.upper()

        svc = get_stop_service()
        stop_obj = svc.get_stop(stop_id)
        if not stop_obj:
            await interaction.response.send_message(f"Stop '{stop_id}' not found. Use `/search` first.", ephemeral=True)
            return

        # Next bus validation
        next_bus_msg, can_track = await get_next_bus_info(stop_id)
        if not can_track:
            await interaction.response.send_message(f"🛑 **No buses departing in the next 2 hours.**\n\n{next_bus_msg}", ephemeral=True)
            return

        routes = svc.get_routes_for_stop(stop_id)
        text = f"📍 **{stop_obj.stop_name}** ({stop_obj.stop_id})\n\nSelect a route to track:"

        await interaction.response.send_message(text, view=TrackFlowView(stop_id, routes), ephemeral=True)

    @app_commands.command(name="schedule", description="Planned schedule for a stop")
    async def schedule(self, interaction: discord.Interaction, stop: str, route: str = None, duration: str = None):
        user = await self._ensure_discord_user(interaction)
        if not user:
            return

        query = stop.strip()
        svc = get_stop_service()
        stop_obj = svc.get_stop(query.upper())
        if not stop_obj:
            results = svc.search_stops(query, limit=1)
            stop_obj = results[0] if results else None
        if not stop_obj:
            await interaction.response.send_message(f"Stop '{query}' not found.", ephemeral=True)
            return

        duration_min = None
        if duration:
            dur_str = duration.lower()
            try:
                if "h" in dur_str:
                    duration_min = float(dur_str.split("h")[0]) * 60
                elif "m" in dur_str:
                    duration_min = float(dur_str.split("m")[0])
                else:
                    duration_min = float(dur_str)
            except ValueError:
                pass

        route_filter = route.upper() if route else None

        now = datetime.now(tz=__import__('zoneinfo').ZoneInfo("America/Indiana/Indianapolis"))
        day_name = now.strftime("%A").lower()
        current_secs = now.hour * 3600 + now.minute * 60 + now.second
        dur_secs = int(duration_min * 60) if duration_min else None

        scheduled = svc.get_scheduled_arrivals(stop_obj.stop_id, day_name, current_secs, dur_secs)
        if route_filter:
            scheduled = [s for s in scheduled if s["route_id"] == route_filter]

        if not scheduled:
            await interaction.response.send_message(f"📅 **{stop_obj.stop_name}**\nNo buses scheduled.", ephemeral=True)
            return

        msg_lines = [f"📅 **{stop_obj.stop_name}**\n"]
        if route_filter:
            msg_lines.append(f"Route: {route_filter}\n")
        msg_lines.append(f"{'Next ' + str(int(duration_min)) + ' mins' if duration_min else day_name.capitalize()}:\n\n")

        for s in scheduled[:15]:
            t = s["time_seconds"]
            h, m = t // 3600, (t % 3600) // 60
            if h >= 24:
                h -= 24
            ampm = "AM" if h < 12 else "PM"
            h_d = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
            route_obj = svc.get_route(s["route_id"])
            r_name = route_obj.route_short_name if route_obj else s["route_id"]
            icon = "⏮️" if t < current_secs else "✅"
            msg_lines.append(f"{icon} **{h_d}:{m:02d}{ampm}** — {r_name} to {s['headsign']}\n")

        if len(scheduled) > 15:
            msg_lines.append(f"\n...and {len(scheduled) - 15} more.")

        await interaction.response.send_message("".join(msg_lines), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(CityBusCog(bot))
