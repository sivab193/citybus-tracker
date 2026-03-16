import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User, Message, Chat
from telegram.ext import ContextTypes, ConversationHandler

from citybus.bot.commands import (
    start_cmd, register_username_receive, search_cmd, search_receive,
    list_cmd, stop_selected_cb,
    WAITING_FOR_USERNAME, WAITING_FOR_SEARCH
)


@pytest.fixture
def mock_update():
    """Create a mock Telegram Update object."""
    update = MagicMock(spec=Update)
    
    user = MagicMock(spec=User)
    user.id = 123456789
    user.username = "testuser"
    
    chat = MagicMock(spec=Chat)
    chat.id = 123456789
    
    message = AsyncMock(spec=Message)
    message.reply_text = AsyncMock()
    message.text = ""
    
    update.effective_user = user
    update.message = message
    update.effective_chat = chat
    return update


@pytest.fixture
def mock_context():
    """Create a mock ContextTypes.DEFAULT_TYPE."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.args = []
    return context


@pytest.mark.asyncio
@patch("citybus.bot.commands.get_or_create_user")
async def test_start_unregistered_prompts_username(mock_get_user, mock_update, mock_context):
    """Test that /start asks for a username if the user is unregistered."""
    mock_get_user.return_value = {"_id": 12345, "registered_username": None}
    
    state = await start_cmd(mock_update, mock_context)
    
    assert state == WAITING_FOR_USERNAME
    mock_update.message.reply_text.assert_called_once()
    assert "reply with a unique alphanumeric username" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
@patch("citybus.bot.commands.get_or_create_user")
async def test_start_registered_shows_help(mock_get_user, mock_update, mock_context):
    """Test that /start shows help if user is already registered."""
    mock_get_user.return_value = {"_id": 12345, "registered_username": "johndoe"}
    
    state = await start_cmd(mock_update, mock_context)
    
    assert state == ConversationHandler.END
    mock_update.message.reply_text.assert_called_once()
    assert "Hi johndoe" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
@patch("citybus.bot.commands.check_registered_username_exists")
@patch("citybus.bot.commands.set_registered_username")
async def test_register_username_invalid_format(mock_set, mock_check, mock_update, mock_context):
    """Test username containing invalid characters is rejected."""
    mock_update.message.text = "invalid_user!"  # contains underscore and exclamation
    
    state = await register_username_receive(mock_update, mock_context)
    
    assert state == WAITING_FOR_USERNAME
    mock_update.message.reply_text.assert_called_once()
    assert "must be 3-15 characters" in mock_update.message.reply_text.call_args[0][0]
    mock_check.assert_not_called()
    mock_set.assert_not_called()


@pytest.mark.asyncio
@patch("citybus.bot.commands.check_registered_username_exists")
@patch("citybus.bot.commands.set_registered_username")
async def test_register_username_success(mock_set, mock_check, mock_update, mock_context):
    """Test successful username registration."""
    mock_update.message.text = "ValidName123"
    mock_check.return_value = False  # username is not taken
    
    state = await register_username_receive(mock_update, mock_context)
    
    assert state == ConversationHandler.END
    mock_check.assert_called_once_with("validname123")
    mock_set.assert_called_once_with(123456789, "validname123")
    mock_update.message.reply_text.assert_called_once()
    assert "Registration complete" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
@patch("citybus.bot.commands.get_or_create_user")
async def test_search_no_args_prompts(mock_get_user, mock_update, mock_context):
    """Test that /search without args prompts the user interactively."""
    mock_get_user.return_value = {"_id": 12345, "registered_username": "johndoe"}
    
    # args is empty by default in mock_context
    state = await search_cmd(mock_update, mock_context)
    
    assert state == WAITING_FOR_SEARCH
    mock_update.message.reply_text.assert_called_once_with("Please type the name of the stop you want to search for:")


@pytest.mark.asyncio
@patch("citybus.bot.commands.get_stop_service")
@patch("citybus.bot.commands.log_general")
@patch("citybus.bot.commands.get_or_create_user")
async def test_search_with_args(mock_get_user, mock_log, mock_svc, mock_update, mock_context):
    """Test that /search with args executes immediately."""
    mock_get_user.return_value = {"_id": 12345, "registered_username": "johndoe"}
    mock_context.args = ["walmart"]
    
    # Mock Stop Service
    svc_instance = MagicMock()
    svc_instance.search_stops.return_value = [] # Return no stops for simplicity of assertion
    mock_svc.return_value = svc_instance
    
    state = await search_cmd(mock_update, mock_context)
    
    assert state == ConversationHandler.END
    svc_instance.search_stops.assert_called_once_with("walmart", limit=6)
    mock_update.message.reply_text.assert_called_once_with("No stops found for 'walmart'.")


@pytest.mark.asyncio
@patch("citybus.bot.commands._ensure_user")
@patch("citybus.bot.commands._is_admin")
async def test_list_cmd_user(mock_is_admin, mock_ensure, mock_update, mock_context):
    """Test /list for regular user."""
    mock_ensure.return_value = {"role": "user"}
    mock_is_admin.return_value = False
    
    await list_cmd(mock_update, mock_context)
    
    msg = mock_update.message.reply_text.call_args[0][0]
    assert "📖 *Available Commands:*" in msg
    assert "⚡ *Admin Commands:*" not in msg


@pytest.mark.asyncio
@patch("citybus.bot.commands._ensure_user")
@patch("citybus.bot.commands._is_admin")
async def test_list_cmd_admin(mock_is_admin, mock_ensure, mock_update, mock_context):
    """Test /list for admin."""
    mock_ensure.return_value = {"role": "admin"}
    mock_is_admin.return_value = True
    
    await list_cmd(mock_update, mock_context)
    
    msg = mock_update.message.reply_text.call_args[0][0]
    assert "📖 *Available Commands:*" in msg
    assert "⚡ *Admin Commands:*" in msg


@pytest.mark.asyncio
@patch("citybus.bot.commands.get_next_bus_info")
@patch("citybus.bot.commands.get_stop_service")
async def test_stop_selection_no_buses_blocks(mock_svc, mock_next_info, mock_update, mock_context):
    """Test that stop selection stops if no buses in 2 hours."""
    mock_next_info.return_value = ("Next bus at 8:00 AM", False) # False = tracking not allowed
    mock_update.callback_query = AsyncMock()
    mock_update.callback_query.data = "stop:BUS123"
    
    from citybus.bot.commands import stop_selected_cb
    state = await stop_selected_cb(mock_update, mock_context)
    
    assert state == ConversationHandler.END
    mock_update.callback_query.edit_message_text.assert_called_once()
    assert "No buses departing in the next 2 hours" in mock_update.callback_query.edit_message_text.call_args[0][0]
