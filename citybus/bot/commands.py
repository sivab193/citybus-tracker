"""
Telegram bot command implementations.

Includes user commands (/start, /search, /arrivals, /status, /stop,
/favorites, /fav, /unfav, /schedule) and admin commands
(/admin_stats, /admin_users, /admin_errors, /admin_broadcast, /debug).
"""

import asyncio
import re
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from citybus.config import settings
from citybus.services.stop_service import get_stop_service
from citybus.services.user_service import (
    get_or_create_user, add_favorite, remove_favorite,
    check_registered_username_exists, set_registered_username
)
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
WAITING_FOR_USERNAME = 99
WAITING_FOR_SEARCH = 100
WAITING_FOR_ARRIVALS = 101
WAITING_FOR_TRACK = 102
WAITING_FOR_FAV = 103
WAITING_FOR_UNFAV = 104
WAITING_FOR_SCHEDULE = 105
WAITING_FOR_LIST = 106

def get_help_message(username: str) -> str:
    return (
        f"👋 *Hi {username}! Welcome to CityBus Tracker.*\n\n"
        "Here are the most important commands:\n"
        "• `/search <name>` — Find a bus stop\n"
        "• `/arrivals <stop>` — Live bus arrivals\n"
        "• `/track <stop|f1>` — Quick start notifications\n"
        "• `/status` — View your active tracking\n"
        "• `/stop` — Stop all notifications\n\n"
        "Tap a command to start!"
    )


async def _ensure_user(update: Update) -> dict | None:
    """Ensure the user exists and has a registered username."""
    user = update.effective_user
    db_user = await get_or_create_user(user.id, username=user.username)
    if not db_user.get("registered_username"):
        if update.message:
            await update.message.reply_text("⚠️ You must register a unique username first. Please type /start to begin.")
        elif update.callback_query:
            await update.callback_query.answer("Please type /start to register a username first.", show_alert=True)
        return None
    return db_user


# ── /start & Registration ──

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(user.id, username=user.username)
    
    if not db_user.get("registered_username"):
        await update.message.reply_text(
            "👋 *Welcome to the CityBus Tracker!*\n\n"
            "To get started, please reply with a unique alphanumeric username (3-15 characters).",
            parse_mode="Markdown"
        )
        return WAITING_FOR_USERNAME

    await update.message.reply_text(get_help_message(db_user["registered_username"]), parse_mode="Markdown")
    return ConversationHandler.END


async def register_username_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username_input = update.message.text.strip().lower()
    
    if not re.match(r"^[a-z0-9]{3,15}$", username_input):
        await update.message.reply_text("Username must be 3-15 characters and contain only letters and numbers. Please try again:")
        return WAITING_FOR_USERNAME
        
    if await check_registered_username_exists(username_input):
        await update.message.reply_text(f"❌ Username '{username_input}' is already taken. Please choose another one:")
        return WAITING_FOR_USERNAME
        
    await set_registered_username(user.id, username_input)
    await update.message.reply_text(
        f"✅ Registration complete!\n\n" + get_help_message(username_input),
        parse_mode="Markdown"
    )
    return ConversationHandler.END


# ── /search ──

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await _ensure_user(update)
    if not user:
        return ConversationHandler.END
    if not context.args:
        await update.message.reply_text("Please type the name of the stop you want to search for:")
        return WAITING_FOR_SEARCH

    return await _execute_search(update, context, " ".join(context.args))

async def search_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _execute_search(update, context, update.message.text.strip())

async def _execute_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> int:
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

    # --- Next Bus Validation ---
    next_bus_msg, can_track = await get_next_bus_info(stop_id)
    if not can_track:
        await query.edit_message_text(f"🛑 *No buses departing in the next 2 hours.*\n\n{next_bus_msg}", parse_mode="Markdown")
        return ConversationHandler.END

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
    user = await _ensure_user(update)
    if not user:
        return ConversationHandler.END
    if not context.args:
        await update.message.reply_text("Please type the stop ID to check arrivals (e.g. BUS215):")
        return WAITING_FOR_ARRIVALS

    await _execute_arrivals(update, context, context.args[0])
    return ConversationHandler.END

async def arrivals_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _execute_arrivals(update, context, update.message.text.strip())
    return ConversationHandler.END

async def _execute_arrivals(update: Update, context: ContextTypes.DEFAULT_TYPE, search_term: str):
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


# ── /track ──

async def track_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await _ensure_user(update)
    if not user:
        return ConversationHandler.END
    if not context.args:
        await update.message.reply_text("Please type the stop ID or favorite (e.g. f1) to track:")
        return WAITING_FOR_TRACK

    return await _execute_track(update, context, user, context.args[0])

async def track_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await _ensure_user(update)
    return await _execute_track(update, context, user, update.message.text.strip())

async def _execute_track(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict, raw_query: str) -> int:
    query = raw_query.lower()
    stop_id = None
    
    # Check if favorite (e.g. f1, f2)
    if query.startswith("f") and query[1:].isdigit():
        idx = int(query[1:]) - 1
        favs = user.get("favorites", [])
        if 0 <= idx < len(favs):
            stop_id = favs[idx]
        else:
            await update.message.reply_text(f"Favorite f{idx+1} not found. Check `/favorites`.", parse_mode="Markdown")
            return ConversationHandler.END
    else:
        stop_id = query.upper()
        
    svc = get_stop_service()
    stop = svc.get_stop(stop_id)
    if not stop:
        await update.message.reply_text(f"Stop '{stop_id}' not found. Use `/search` first.", parse_mode="Markdown")
        return ConversationHandler.END
        
    # --- Next Bus Validation ---
    next_bus_msg, can_track = await get_next_bus_info(stop_id)
    if not can_track:
        await update.message.reply_text(f"🛑 *No buses departing in the next 2 hours.*\n\n{next_bus_msg}", parse_mode="Markdown")
        return ConversationHandler.END

    # Start tracking flow
    context.user_data["selected_stop"] = stop_id
    routes = svc.get_routes_for_stop(stop_id)
    text = f"📍 *{stop.stop_name}* ({stop.stop_id})\n\nSelect a route to track:"
    await update.message.reply_text(
        text,
        reply_markup=route_list_keyboard(routes),
        parse_mode="Markdown",
    )
    return SELECTING_ROUTE


# ── /status ──

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _ensure_user(update)
    if not user:
        return
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
    if not user:
        return
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
    user = await _ensure_user(update)
    if not user:
        return ConversationHandler.END
    if not context.args:
        await update.message.reply_text("Please type the stop ID to add to favorites:")
        return WAITING_FOR_FAV
    
    await _execute_fav(update, context, context.args[0])
    return ConversationHandler.END

async def fav_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _execute_fav(update, context, update.message.text.strip())
    return ConversationHandler.END

async def _execute_fav(update: Update, context: ContextTypes.DEFAULT_TYPE, stop_id: str):
    sid = stop_id.upper()
    ok = await add_favorite(update.effective_user.id, sid)
    await update.message.reply_text(f"⭐ Added `{sid}` to favorites." if ok else f"`{sid}` already in favorites.", parse_mode="Markdown")


async def unfav_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _ensure_user(update)
    if not user:
        return ConversationHandler.END
    if not context.args:
        await update.message.reply_text("Please type the stop ID to remove from favorites:")
        return WAITING_FOR_UNFAV
        
    await _execute_unfav(update, context, context.args[0])
    return ConversationHandler.END

async def unfav_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _execute_unfav(update, context, update.message.text.strip())
    return ConversationHandler.END

async def _execute_unfav(update: Update, context: ContextTypes.DEFAULT_TYPE, stop_id: str):
    sid = stop_id.upper()
    ok = await remove_favorite(update.effective_user.id, sid)
    await update.message.reply_text(f"Removed `{sid}` from favorites." if ok else f"`{sid}` not in favorites.", parse_mode="Markdown")


# ── /schedule ──

async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _ensure_user(update)
    if not user:
        return ConversationHandler.END
    if not context.args:
        await update.message.reply_text("Please type the stop ID for the schedule:")
        return WAITING_FOR_SCHEDULE

    await _execute_schedule(update, context, list(context.args))
    return ConversationHandler.END

async def schedule_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.strip().split()
    await _execute_schedule(update, context, args)
    return ConversationHandler.END

async def _execute_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]):
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

    now = datetime.now(tz=__import__('zoneinfo').ZoneInfo("America/Indiana/Indianapolis"))
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
    user = await _ensure_user(update)
    if not user:
        return
    await update.message.reply_text(get_help_message(user.get("registered_username", "")), parse_mode="Markdown")


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all available commands, including admin ones if applicable."""
    user = await _ensure_user(update)
    if not user:
        return
    
    is_admin = _is_admin(update.effective_user.id)
    
    commands = [
        "📖 *Available Commands:*\n",
        "• `/search <name>` — Find a bus stop",
        "• `/arrivals <stop>` — Live bus arrivals",
        "• `/track <stop|f1>` — Quick start notifications",
        "• `/status` — View your active tracking",
        "• `/stop` — Stop all notifications",
        "• `/favorites` — View favorites",
        "• `/fav <stop>` — Add favorite",
        "• `/unfav <stop>` — Remove favorite",
        "• `/schedule <stop>` — Planned schedule",
        "• `/cancel` — Cancel current menu flow",
        "• `/list` — This command list"
    ]
    
    if is_admin:
        commands.extend([
            "\n⚡ *Admin Commands:*",
            "• `/admin_stats` — System usage",
            "• `/admin_users` — Recent users",
            "• `/admin_errors` — Recent logs",
            "• `/admin_broadcast` — Send msg to everyone",
            "• `/debug` — Build & Config info"
        ])
    
    await update.message.reply_text("\n".join(commands), parse_mode="Markdown")


# ════════════════════════════════════════════
# Admin Commands
# ════════════════════════════════════════════

def _is_admin(user_id: int) -> bool:
    admin_ids = settings.get_config("ADMIN_IDS", [])
    return user_id in admin_ids


async def admin_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    db = get_db()
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    users, active, errors = await asyncio.gather(
        db.users.count_documents({}),
        db.subscriptions.count_documents({"status": "active"}),
        db.logs_errors.count_documents({"timestamp": {"$gte": today}})
    )
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
        f"Worker poll: {settings.get_config('WORKER_POLL_INTERVAL', 10)}s\n"
        f"Redis URL: {settings.REDIS_URL[:30]}...",
        parse_mode="Markdown",
    )


# ════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════

async def get_next_bus_info(stop_id: str) -> tuple[str, bool]:
    """
    Checks for upcoming buses at a stop.
    Returns (message, is_tracking_allowed).
    Tracking is only allowed if a bus is coming in the next 2 hours.
    Uses agency timezone (Eastern) for schedule lookups.
    """
    from zoneinfo import ZoneInfo
    AGENCY_TZ = ZoneInfo("America/Indiana/Indianapolis")

    svc = get_stop_service()
    now = datetime.now(AGENCY_TZ)
    day_name = now.strftime("%A").lower()
    current_secs = now.hour * 3600 + now.minute * 60 + now.second

    # 1. Check Real-time (Redis)
    cached = await get_arrivals(stop_id)
    if cached:
        min_secs = min(cached.values())
        if min_secs <= 7200: # 2 hours
            return f"Next bus in {min_secs // 60} mins.", True

    # 2. Check Schedule (Static) - 2 hours
    scheduled_2h = svc.get_scheduled_arrivals(stop_id, day_name, current_secs, 7200)
    if scheduled_2h:
        first = scheduled_2h[0]
        wait_mins = (first["time_seconds"] - current_secs) // 60
        return f"Next scheduled bus in {wait_mins} mins.", True

    # 3. No bus in 2 hours - Find the absolute next bus
    # Check remaining of today
    scheduled_today = svc.get_scheduled_arrivals(stop_id, day_name, current_secs)
    if scheduled_today:
        first = scheduled_today[0]
        t = first["time_seconds"]
        h, m = t // 3600, (t % 3600) // 60
        if h >= 24: h -= 24
        ampm = "AM" if h < 12 else "PM"
        h_d = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
        wait_hrs = (t - current_secs) / 3600
        return f"No buses now. The next bus is at {h_d}:{m:02d} {ampm} ({wait_hrs:.1f} hrs away).", False

    # Check tomorrow (simplified: just list it as "tomorrow")
    return "No buses found for the remainder of today. Please check back later.", False

