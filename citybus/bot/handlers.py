"""
Bot handler setup — wires commands to the Telegram Application.
"""

from telegram import BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from citybus.bot.commands import (
    SELECTING_STOP, SELECTING_ROUTE, SELECTING_FREQUENCY,
    start_cmd, search_cmd, stop_selected_cb, route_selected_cb,
    frequency_selected_cb, arrivals_cmd, status_cmd, stop_cmd,
    favorites_cmd, fav_cmd, fav_receive, unfav_cmd, unfav_receive, schedule_cmd, schedule_receive,
    track_cmd, list_cmd, cancel_cmd, unknown_cmd,
    register_username_receive, WAITING_FOR_USERNAME,
    WAITING_FOR_SEARCH, search_receive,
    WAITING_FOR_ARRIVALS, arrivals_receive,
    WAITING_FOR_TRACK, track_receive,
    WAITING_FOR_FAV, fav_receive,
    WAITING_FOR_UNFAV, unfav_receive,
    WAITING_FOR_SCHEDULE, schedule_receive,
    admin_stats_cmd, admin_users_cmd, admin_errors_cmd,
    admin_broadcast_cmd, debug_cmd,
)


async def set_bot_commands(app: Application):
    """Register commands for Telegram autocomplete."""
    commands = [
        BotCommand("start", "Show welcome message"),
        BotCommand("search", "<name> Search for a bus stop"),
        BotCommand("arrivals", "<stop> Check arrivals at a stop"),
        BotCommand("schedule", "<stop> [route] [duration] View planned schedule"),
        BotCommand("track", "<stop|f1> Track a stop or favorite"),
        BotCommand("status", "Show active subscriptions"),
        BotCommand("stop", "Stop all notifications"),
        BotCommand("favorites", "View favorite stops"),
        BotCommand("fav", "<stop> Add a favorite stop"),
        BotCommand("unfav", "<stop> Remove a favorite stop"),
    ]
    await app.bot.set_my_commands(commands)


def register_handlers(app: Application):
    """Register all command and conversation handlers."""

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("search", search_cmd),
            CommandHandler("track", track_cmd),
            CommandHandler("arrivals", arrivals_cmd),
            CommandHandler("fav", fav_cmd),
            CommandHandler("unfav", unfav_cmd),
            CommandHandler("schedule", schedule_cmd),
        ],
        states={
            WAITING_FOR_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_receive)],
            WAITING_FOR_ARRIVALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, arrivals_receive)],
            WAITING_FOR_TRACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, track_receive)],
            WAITING_FOR_FAV: [MessageHandler(filters.TEXT & ~filters.COMMAND, fav_receive)],
            WAITING_FOR_UNFAV: [MessageHandler(filters.TEXT & ~filters.COMMAND, unfav_receive)],
            WAITING_FOR_SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_receive)],
            SELECTING_STOP: [CallbackQueryHandler(stop_selected_cb)],
            SELECTING_ROUTE: [CallbackQueryHandler(route_selected_cb)],
            SELECTING_FREQUENCY: [CallbackQueryHandler(frequency_selected_cb)],
        },
        fallbacks=[CommandHandler("cancel", cancel_cmd)],
        per_message=False,
    )

    registration_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start_cmd)],
        states={
            WAITING_FOR_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_username_receive)]
        },
        fallbacks=[CommandHandler("cancel", cancel_cmd)],
        per_message=False,
    )

    # User commands
    app.add_handler(registration_conv)
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("favorites", favorites_cmd))

    # Admin commands
    app.add_handler(CommandHandler("admin_stats", admin_stats_cmd))
    app.add_handler(CommandHandler("admin_users", admin_users_cmd))
    app.add_handler(CommandHandler("admin_errors", admin_errors_cmd))
    app.add_handler(CommandHandler("admin_broadcast", admin_broadcast_cmd))
    app.add_handler(CommandHandler("debug", debug_cmd))

    # Conversation handler (search/track)
    app.add_handler(conv_handler)

    # Unknown messages (must be last)
    app.add_handler(MessageHandler(filters.ALL, unknown_cmd))
