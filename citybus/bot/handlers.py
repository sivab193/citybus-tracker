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
    favorites_cmd, fav_cmd, unfav_cmd, schedule_cmd,
    cancel_cmd, unknown_cmd,
    admin_stats_cmd, admin_users_cmd, admin_errors_cmd,
    admin_broadcast_cmd, debug_cmd,
)


async def set_bot_commands(app: Application):
    """Register commands for Telegram autocomplete."""
    commands = [
        BotCommand("start", "Show welcome message"),
        BotCommand("search", "Search for a bus stop"),
        BotCommand("arrivals", "Check arrivals at a stop"),
        BotCommand("schedule", "View planned schedule"),
        BotCommand("status", "Show active subscriptions"),
        BotCommand("stop", "Stop all notifications"),
        BotCommand("favorites", "View favorite stops"),
        BotCommand("fav", "Add a favorite stop"),
        BotCommand("unfav", "Remove a favorite stop"),
    ]
    await app.bot.set_my_commands(commands)


def register_handlers(app: Application):
    """Register all command and conversation handlers."""

    # Conversation handler for search → stop → route → frequency flow
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("search", search_cmd),
        ],
        states={
            SELECTING_STOP: [CallbackQueryHandler(stop_selected_cb)],
            SELECTING_ROUTE: [CallbackQueryHandler(route_selected_cb)],
            SELECTING_FREQUENCY: [CallbackQueryHandler(frequency_selected_cb)],
        },
        fallbacks=[CommandHandler("cancel", cancel_cmd)],
    )

    # User commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("arrivals", arrivals_cmd))
    app.add_handler(CommandHandler("schedule", schedule_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("favorites", favorites_cmd))
    app.add_handler(CommandHandler("fav", fav_cmd))
    app.add_handler(CommandHandler("unfav", unfav_cmd))

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
