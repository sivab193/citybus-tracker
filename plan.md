1. **Add `discord.py` to `requirements.txt`**
   - Add `discord.py` to the core requirements.

2. **Add `DISCORD_BOT_TOKEN` to Settings and `.env.example`**
   - Update `citybus/config/settings.py` to fetch `DISCORD_BOT_TOKEN`.
   - Update `.env.example` to include `DISCORD_BOT_TOKEN`.

3. **Create `citybus/discord` directory and Discord Bot entry point `main_discord.py`**
   - Implement `main_discord.py` using `discord.py` with `discord.ext.commands`.
   - Setup basic discord bot initialization, similarly to `main_bot.py`.
   - Ensure the bot runs via `python main_discord.py` with `DISCORD_BOT_TOKEN`.
   - Include the database initialization and locking mechanisms (e.g. `await acquire_service_lock("discord_bot", timeout=30)`).

4. **Implement Discord Commands**
   - Create `citybus/discord/commands.py` containing Discord command equivalents (slash commands or normal prefix commands) for the Telegram ones: `/search`, `/arrivals`, `/track`, `/status`, `/stop`, `/schedule`, `/fav`, `/unfav`, etc.
   - Use `discord.app_commands` for slash commands for a more modern experience.
   - Ensure Discord user IDs are handled appropriately in user service (since user IDs can just be Discord's 64-bit integer IDs instead of Telegram's, they should be compatible or handled side-by-side).

5. **Update Worker for Discord Notifications**
   - Right now `citybus/worker/notifier.py` sends updates directly to Telegram via HTTP.
   - We need to modify the notifier to know if a subscription is for Telegram or Discord.
   - We can update the `create_subscription` to accept a `platform` parameter (default `'telegram'`), and also store the `platform` in the subscription document.
   - In `notifier.py`, read the `platform` of the subscription. If `telegram`, send via Telegram. If `discord`, send via Discord webhooks or a Discord HTTP API call.
   - Sending via Discord HTTP API without `discord.py` library instance is simple: `POST https://discord.com/api/v10/channels/{channel_id}/messages` with `Authorization: Bot {token}`. Here, `user_id` would actually need to be a DM channel ID, OR we need to create a DM channel first. A simpler alternative is to store the DM channel ID when the user interacts with the Discord bot.

6. **Refactoring `user_service.py` & `subscription_service.py`**
   - Add a `platform` field to subscriptions.
   - When a Discord user registers/starts tracking, save their platform as `discord`.

7. **Pre-commit and Test**
   - Run tests, ensure existing logic isn't broken.
