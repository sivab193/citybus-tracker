"""
Inline keyboard builders for the Telegram bot.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def stop_list_keyboard(stops) -> InlineKeyboardMarkup:
    """Build keyboard for a list of stop search results."""
    keyboard = []
    for stop in stops:
        name = stop.stop_name
        if len(name) > 45:
            name = name[:42] + "..."
        keyboard.append([InlineKeyboardButton(name, callback_data=f"stop:{stop.stop_id}")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)


def route_list_keyboard(routes) -> InlineKeyboardMarkup:
    """Build keyboard for route selection."""
    keyboard = []
    for route in routes:
        name = f"{route.route_short_name}: {route.route_long_name}"
        if len(name) > 45:
            name = name[:42] + "..."
        keyboard.append([InlineKeyboardButton(name, callback_data=f"route:{route.route_id}")])
    keyboard.append([InlineKeyboardButton("📍 All Routes", callback_data="route:ALL")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)


def frequency_keyboard() -> InlineKeyboardMarkup:
    """Build keyboard for update frequency selection."""
    keyboard = [
        [
            InlineKeyboardButton("10s", callback_data="freq:10"),
            InlineKeyboardButton("20s", callback_data="freq:20"),
            InlineKeyboardButton("30s", callback_data="freq:30"),
        ],
        [
            InlineKeyboardButton("1 min", callback_data="freq:60"),
            InlineKeyboardButton("2 min", callback_data="freq:120"),
            InlineKeyboardButton("5 min", callback_data="freq:300"),
        ],
        [
            InlineKeyboardButton("10 min", callback_data="freq:600"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)
