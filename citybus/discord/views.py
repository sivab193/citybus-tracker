import discord
from citybus.services.stop_service import get_stop_service
from citybus.services.subscription_service import create_subscription
from citybus.db.redis import get_arrivals
from citybus.logging.logger import log_general


class FrequencySelect(discord.ui.Select):
    def __init__(self, stop_id: str, route_id: str):
        self.stop_id = stop_id
        self.route_id = route_id
        options = [
            discord.SelectOption(label="10 seconds", value="10"),
            discord.SelectOption(label="30 seconds", value="30"),
            discord.SelectOption(label="1 minute", value="60"),
            discord.SelectOption(label="2 minutes", value="120"),
            discord.SelectOption(label="5 minutes", value="300"),
            discord.SelectOption(label="10 minutes", value="600"),
        ]
        super().__init__(placeholder="Select frequency...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        freq = int(self.values[0])
        user_id = interaction.user.id

        try:
            # We must fetch or create a DM channel
            if interaction.user.dm_channel is None:
                await interaction.user.create_dm()

            chat_id = interaction.user.dm_channel.id

            await create_subscription(
                user_id=user_id,
                stop_id=self.stop_id,
                route_id=self.route_id,
                frequency=freq,
                platform="discord",
                chat_id=chat_id
            )
        except ValueError as e:
            await interaction.response.edit_message(content=f"❌ {e}", view=None)
            return

        svc = get_stop_service()
        stop = svc.get_stop(self.stop_id)
        route = svc.get_route(self.route_id) if self.route_id != "ALL" else None

        freq_label = f"{freq}s" if freq < 60 else f"{freq // 60} min"
        content = (
            f"✅ **Tracking started!**\n\n"
            f"📍 Stop: {stop.stop_name if stop else self.stop_id}\n"
            f"🚌 Route: {route.route_short_name if route else 'All Routes'}\n"
            f"⏰ Updates every {freq_label}\n\n"
            "The worker will send updates to your DMs automatically.\n"
            "Use `/stop` to stop tracking."
        )
        await interaction.response.edit_message(content=content, view=None)
        await log_general(command="track_discord", user_id=user_id, params={"stop": self.stop_id, "route": self.route_id, "freq": freq})


class RouteSelect(discord.ui.Select):
    def __init__(self, stop_id: str, routes: list):
        self.stop_id = stop_id
        options = [discord.SelectOption(label="All Routes", value="ALL")]
        for r in routes:
            r_name = f"Route {r.route_short_name}" if r.route_short_name else r.route_id
            options.append(discord.SelectOption(label=r_name, value=r.route_id))

        super().__init__(placeholder="Select a route to track...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        route_id = self.values[0]

        svc = get_stop_service()
        route_name = "All Routes"
        if route_id != "ALL":
            route = svc.get_route(route_id)
            route_name = f"Route {route.route_short_name}" if route else route_id

        view = discord.ui.View(timeout=60)
        view.add_item(FrequencySelect(self.stop_id, route_id))

        await interaction.response.edit_message(content=f"⏰ Tracking **{route_name}**\n\nHow often should I send updates?", view=view)


class StopSelect(discord.ui.Select):
    def __init__(self, stops: list):
        options = []
        for s in stops[:25]: # Discord select max 25 options
            options.append(discord.SelectOption(label=s.stop_name[:100], description=f"ID: {s.stop_id}", value=s.stop_id))

        super().__init__(placeholder="Select a stop...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        stop_id = self.values[0]

        svc = get_stop_service()
        stop = svc.get_stop(stop_id)
        routes = svc.get_routes_for_stop(stop_id)

        # Quick next bus check
        from citybus.bot.commands import get_next_bus_info # re-use
        next_bus_msg, can_track = await get_next_bus_info(stop_id)
        if not can_track:
            await interaction.response.edit_message(content=f"🛑 **No buses departing in the next 2 hours.**\n\n{next_bus_msg}", view=None)
            return

        preview = ""
        cached = await get_arrivals(stop_id)

        if cached:
            preview_lines = ["\n\n**Next arrivals:**\n"]
            for key, secs in sorted(cached.items(), key=lambda x: x[1])[:3]:
                r_id = key.replace("route_", "")
                route = svc.get_route(r_id)
                r_name = route.route_short_name if route else r_id
                preview_lines.append(f"• {r_name}: {secs // 60} min\n")
            preview = "".join(preview_lines)

        text = f"📍 **{stop.stop_name}** ({stop.stop_id}){preview}\n\nSelect a route to track:"

        view = discord.ui.View(timeout=60)
        view.add_item(RouteSelect(stop_id, routes))

        await interaction.response.edit_message(content=text, view=view)


class TrackFlowView(discord.ui.View):
    def __init__(self, stop_id: str, routes: list):
        super().__init__(timeout=60)
        self.add_item(RouteSelect(stop_id, routes))

class SearchFlowView(discord.ui.View):
    def __init__(self, stops: list):
        super().__init__(timeout=60)
        self.add_item(StopSelect(stops))
