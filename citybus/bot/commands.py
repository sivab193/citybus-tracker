"""
Telegram bot command implementations.

Includes user commands (/start, /search, /arrivals, /status, /stop,
/favorites, /fav, /unfav, /schedule) and admin commands
(/admin_stats, /admin_users, /admin_errors, /admin_broadcast, /debug).
"""

from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from citybus.config import settings
from citybus.services.stop_service import get_stop_service
from citybus.services.user_service import get_or_create_user, add_favorite, remove_favorite
from citybus.services.subscription_service import (
    create_subscription, stop_user_subscriptions, get_active_subscriptions,
)
from citybus.db.mongo import get_db
from citybus.db.redis import get_arrivals
from citybus.worker.gtfs_poller import (
    fetch_trip_updates, parse_arrivals_for_stop, format_arrival_message,
)
from citybus.bot.keyboards import stop_list_keyboard, route_list_keyboard, frequency_keyboard
from citybus.logging.logger import log_general

# Conversation states
SELECTING_STOP, SELECTING_ROUTE, SELECTING_FREQUENCY = range(3)

HELP_MESSAGE = (
    "👋 *Welcome to the CityBus Tracker!*\n\n"
    "I can help you track bus arrivals in real-time for CityBus of Greater Lafayette.\n\n"
    "*Commands:*\n"
    "• `/search <name>` — Search for a bus stop\n"
    "• `/arrivals <stop>` — Check arrivals at a stop\n"
    "• `/schedule <stop> [route] [time]` — Planned schedule\n"
    "• `/status` — Show your active tracking\n"
    "• `/stop` — Stop all notifications\n"
    "• `/favorites` — View favorite stops\n"
    "• `/fav <stop>` — Add a stop to favorites\n"
    "• `/unfav <stop>` — Remove a stop from favorites\n\n"
    "Try: `/search walmart` or `/arrivals BUS215`!"
)


async def _ensure_user(update: Update) -> dict:
    """Ensure the user exists in the database."""
    user = update.effective_user
    return await get_or_create_user(user.id, username=user.username)


# ── /start ──

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    await update.message.reply_text(HELP_MESSAGE, parse_mode="Markdown")


# ── /search ──

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _ensure_user(update)
    if not context.args:
        await update.message.reply_text("Usage: `/search <stop name>`", parse_mode="Markdown")
        return ConversationHandler.END

    query = " ".join(context.args)
    svc = get_stop_service()
    stops = svc.search_stops(query, limit=6)
    await log_general(command="/search", user_id=update.effective_user.id, params={"query": query})

    if not stops:
        await update.message.reply_text(f"No stops found for '{query}'.")
        return ConversationHandler.END

    await update.message.reply_text(
        f"🔍 Found {len(stops)} stops matching '*{query}*':\nSelect a stop to track:",
        reply_markup=stop_list_keyboard(stops),
        parse_mode="Markdown",
    )
    return SELECTING_STOP


# ── Stop selected (callback) ──

async def stop_selected_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    stop_id = data.split(":")[1]
    context.user_data["selected_stop"] = stop_id

    svc = get_stop_service()
    stop = svc.get_stop(stop_id)
    routes = svc.get_routes_for_stop(stop_id)

    # Show current arrivals preview
    preview = ""
    cached = None
    try:
        cached = await get_arrivals(stop_id)
    except Exception:
        pass

    if cached:
        preview = "\n\n*Next arrivals:*\n"
        for key, secs in sorted(cached.items(), key=lambda x: x[1])[:3]:
            r_id = key.replace("route_", "")
            route = svc.get_route(r_id)
            r_name = route.route_short_name if route else r_id
            preview += f"• {r_name}: {secs // 60} min\n"

    text = f"📍 *{stop.stop_name}* ({stop.stop_id}){preview}\n\nSelect a route to track:"
    await query.edit_message_text(
        text,
        reply_markup=route_list_keyboard(routes),
        parse_mode="Markdown",
    )
    return SELECTING_ROUTE


# ── Route selected (callback) ──

async def route_selected_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    route_id = data.split(":")[1]
    context.user_data["selected_route"] = route_id

    svc = get_stop_service()
    route_name = "All Routes"
    if route_id != "ALL":
        route = svc.get_route(route_id)
        route_name = f"Route {route.route_short_name}" if route else route_id

    await query.edit_message_text(
        f"⏰ Tracking *{route_name}*\n\nHow often should I send updates?",
        reply_markup=frequency_keyboard(),
        parse_mode="Markdown",
    )
    return SELECTING_FREQUENCY


# ── Frequency selected (callback) ──

async def frequency_selected_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    frequency = int(data.split(":")[1])
    stop_id = context.user_data.get("selected_stop")
    route_id = context.user_data.get("selected_route", "ALL")
    user_id = query.from_user.id

    try:
        sub = await create_subscription(user_id, stop_id, route_id, frequency)
    except ValueError as e:
        await query.edit_message_text(f"❌ {e}")
        return ConversationHandler.END

    svc = get_stop_service()
    stop = svc.get_stop(stop_id)
    route = svc.get_route(route_id) if route_id != "ALL" else None

    freq_label = f"{frequency}s" if frequency < 60 else f"{frequency // 60} min"
    await query.edit_message_text(
        f"✅ *Tracking started!*\n\n"
        f"📍 Stop: {stop.stop_name if stop else stop_id}\n"
        f"🚌 Route: {route.route_short_name if route else 'All Routes'}\n"
        f"⏰ Updates every {freq_label}\n\n"
        "The worker will send updates automatically.\n"
        "Use `/stop` to stop tracking.",
        parse_mode="Markdown",
    )
    await log_general(command="track", user_id=user_id, params={"stop": stop_id, "route": route_id, "freq": frequency})
    return ConversationHandler.END


# ── /arrivals ──

async def arrivals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    if not context.args:
        await update.message.reply_text("Usage: `/arrivals <stop_id>`", parse_mode="Markdown")
        return

    search_term = context.args[0]
    svc = get_stop_service()
    stop = svc.get_stop(search_term.upper())
    if not stop:
        results = svc.search_stops(search_term, limit=1)
        if results:
            stop = results[0]
        else:
            await update.message.reply_text(f"Stop '{search_term}' not found.")
            return

    # Try Redis first
    cached = await get_arrivals(stop.stop_id)
    if cached:
        lines = [f"📍 *{stop.stop_name}*\n"]
        for key, secs in sorted(cached.items(), key=lambda x: x[1])[:5]:
            r_id = key.replace("route_", "")
            route = svc.get_route(r_id)
            r_name = route.route_short_name if route else r_id
            lines.append(f"🚌 Route {r_name}: {secs // 60} min")
        lines.append(f"\n_Updated from cache_")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # Fallback: live fetch
    try:
        feed = fetch_trip_updates()
        arrivals = parse_arrivals_for_stop(feed, stop.stop_id)
        if not arrivals:
            await update.message.reply_text(f"📍 *{stop.stop_name}*\n\nNo upcoming arrivals.", parse_mode="Markdown")
            return
        lines = [f"📍 *{stop.stop_name}*\n"]
        for arr in arrivals[:5]:
            route = svc.get_route(arr.route_id)
            r_name = route.route_short_name if route else arr.route_id
            lines.append(format_arrival_message(arr, r_name))
        lines.append(f"\n_Updated at {datetime.now().strftime('%H:%M')}_")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Failed to fetch arrivals: {e}")


# ── /status ──

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    subs = await get_active_subscriptions(update.effective_user.id)
    if not subs:
        await update.message.reply_text("You have no active subscriptions.\nUse `/search <stop>` to start.", parse_mode="Markdown")
        return

    svc = get_stop_service()
    lines = ["📊 *Active Subscriptions:*\n"]
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
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /stop ──

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = await stop_user_subscriptions(update.effective_user.id)
    if count == 0:
        await update.message.reply_text("No active subscriptions to stop.")
    else:
        await update.message.reply_text(f"✅ Stopped {count} subscription(s).")


# ── /favorites, /fav, /unfav ──

async def favorites_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _ensure_user(update)
    favs = user.get("favorites", [])
    if not favs:
        await update.message.reply_text("No favorites yet. Use `/fav <stop_id>` to add one.", parse_mode="Markdown")
        return
    svc = get_stop_service()
    lines = ["⭐ *Favorites:*\n"]
    for sid in favs:
        stop = svc.get_stop(sid)
        lines.append(f"• {stop.stop_name if stop else sid} (`{sid}`)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def fav_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/fav <stop_id>`", parse_mode="Markdown")
        return
    sid = context.args[0].upper()
    ok = await add_favorite(update.effective_user.id, sid)
    await update.message.reply_text(f"⭐ Added `{sid}` to favorites." if ok else f"`{sid}` already in favorites.", parse_mode="Markdown")


async def unfav_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/unfav <stop_id>`", parse_mode="Markdown")
        return
    sid = context.args[0].upper()
    ok = await remove_favorite(update.effective_user.id, sid)
    await update.message.reply_text(f"Removed `{sid}` from favorites." if ok else f"`{sid}` not in favorites.", parse_mode="Markdown")


# ── /schedule ──

async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    if not context.args:
        await update.message.reply_text("Usage: `/schedule <stop> [route] [duration]`", parse_mode="Markdown")
        return

    args = list(context.args)
    duration_min = None
    route_filter = None

    # Check for duration at end
    if args[-1].lower().endswith(("hrs", "hr", "h", "mins", "min", "m")):
        dur_str = args.pop().lower()
        try:
            if "h" in dur_str:
                duration_min = float(dur_str.split("h")[0]) * 60
            elif "m" in dur_str:
                duration_min = float(dur_str.split("m")[0])
        except ValueError:
            pass

    # Check for route
    if len(args) > 1:
        possible = args[-1].upper()
        if len(possible) <= 6 and any(c.isdigit() for c in possible):
            route_filter = args.pop().upper()

    query = " ".join(args)
    if not query:
        await update.message.reply_text("Please provide a stop name.")
        return

    svc = get_stop_service()
    stop = svc.get_stop(query.upper())
    if not stop:
        results = svc.search_stops(query, limit=1)
        stop = results[0] if results else None
    if not stop:
        await update.message.reply_text(f"Stop '{query}' not found.")
        return

    now = datetime.now()
    day_name = now.strftime("%A").lower()
    current_secs = now.hour * 3600 + now.minute * 60 + now.second
    dur_secs = int(duration_min * 60) if duration_min else None

    scheduled = svc.get_scheduled_arrivals(stop.stop_id, day_name, current_secs, dur_secs)
    if route_filter:
        scheduled = [s for s in scheduled if s["route_id"] == route_filter]

    if not scheduled:
        await update.message.reply_text(f"📅 *{stop.stop_name}*\nNo buses scheduled.", parse_mode="Markdown")
        return

    msg = f"📅 *{stop.stop_name}*\n"
    if route_filter:
        msg += f"Route: {route_filter}\n"
    msg += f"{'Next ' + str(int(duration_min)) + ' mins' if duration_min else day_name.capitalize()}:\n\n"

    for s in scheduled[:15]:
        t = s["time_seconds"]
        h, m = t // 3600, (t % 3600) // 60
        if h >= 24:
            h -= 24
        ampm = "AM" if h < 12 else "PM"
        h_d = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
        route = svc.get_route(s["route_id"])
        r_name = route.route_short_name if route else s["route_id"]
        icon = "⏮️" if t < current_secs else "✅"
        msg += f"{icon} *{h_d}:{m:02d}{ampm}* — {r_name} to {s['headsign']}\n"

    if len(scheduled) > 15:
        msg += f"\n...and {len(scheduled) - 15} more."
    await update.message.reply_text(msg, parse_mode="Markdown")


# ── /cancel ──

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Cancelled.")
    else:
        await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# ── Unknown message handler ──

async def unknown_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_MESSAGE, parse_mode="Markdown")


# ════════════════════════════════════════════
# Admin Commands
# ════════════════════════════════════════════

def _is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


async def admin_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    db = get_db()
    users = await db.users.count_documents({})
    active = await db.subscriptions.count_documents({"status": "active"})
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    errors = await db.logs_errors.count_documents({"timestamp": {"$gte": today}})
    await update.message.reply_text(
        f"📊 *Admin Stats*\n\n"
        f"Users: {users}\n"
        f"Active Subscriptions: {active}\n"
        f"Errors Today: {errors}",
        parse_mode="Markdown",
    )


async def admin_users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    db = get_db()
    users = await db.users.find().sort("created_at", -1).to_list(length=20)
    if not users:
        await update.message.reply_text("No users registered.")
        return
    lines = ["👥 *Recent Users:*\n"]
    for u in users:
        lines.append(f"• `{u['_id']}` @{u.get('username', '?')} — {u.get('role', 'user')}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def admin_errors_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    db = get_db()
    errors = await db.logs_errors.find().sort("timestamp", -1).to_list(length=5)
    if not errors:
        await update.message.reply_text("No errors logged.")
        return
    lines = ["🔴 *Recent Errors:*\n"]
    for e in errors:
        ts = e["timestamp"].strftime("%m/%d %H:%M") if isinstance(e["timestamp"], datetime) else str(e["timestamp"])
        lines.append(f"• [{ts}] {e.get('service', '?')}: {e.get('message', '')[:80]}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def admin_broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/admin_broadcast <message>`", parse_mode="Markdown")
        return
    msg = " ".join(context.args)
    db = get_db()
    users = await db.users.find({}, {"_id": 1}).to_list(length=1000)
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u["_id"], text=f"📢 *Announcement*\n\n{msg}", parse_mode="Markdown")
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"Broadcast sent to {sent}/{len(users)} users.")


async def debug_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    svc = get_stop_service()
    await update.message.reply_text(
        f"🔧 *Debug Info*\n\n"
        f"Stops loaded: {len(svc.stops)}\n"
        f"Routes loaded: {len(svc.routes)}\n"
        f"Trips loaded: {len(svc.trips)}\n"
        f"Admin IDs: {settings.ADMIN_IDS}\n"
        f"Worker poll: {settings.WORKER_POLL_INTERVAL}s\n"
        f"Redis URL: {settings.REDIS_URL[:30]}...",
        parse_mode="Markdown",
    )
