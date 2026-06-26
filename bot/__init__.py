import asyncio
import logging
import traceback
import os
import glob
import importlib
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from config.config import Config
from database.db import db

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ANIZONEFLIX_BOT")

bot = Client(
    "anizoneflix_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    in_memory=True
)

# Shared State
user_state = {}
search_results = {}

async def is_authorized(user_id):
    try:
        if user_id in Config.ADMIN_IDS:
            return True
        return await db.is_admin(user_id)
    except Exception as e:
        logger.error(f"Authorization Check Error: {e}")
        return False

async def set_commands(client):
    user_commands = [BotCommand("start", "🚀 Start the Experience")]
    await client.set_bot_commands(user_commands, scope=BotCommandScopeDefault())

    admin_commands = [
        BotCommand("start", "🚀 Admin Dashboard"),
        BotCommand("forward", "🔄 Premium Forwarder"),
        BotCommand("forwardstop", "🛑 Stop Forwarding"),
        BotCommand("login", "🔑 Userbot Login"),
        BotCommand("logout", "🚪 Userbot Logout"),
        BotCommand("search", "🔍 Industrial-Grade Search"),
        BotCommand("add_post", "⚡ Rapid One-Shot Post"),
        BotCommand("edit", "🏛 Manage Content Groups"),
        BotCommand("redirect", "🔗 Trace Redirects"),
        BotCommand("help", "📖 Documentation")
    ]

    for admin_id in Config.ADMIN_IDS:
        try: await client.set_bot_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except: pass

    logger.info("Bot command scopes synchronized.")

def register_handlers(bot: Client):
    # Dynamic Plugin Loader
    plugins = glob.glob("plugins/*.py")
    for plugin_path in plugins:
        plugin_name = plugin_path.replace("/", ".").replace(".py", "")
        try:
            importlib.import_module(plugin_name)
            logger.info(f"✔ Plugin Loaded: {plugin_name}")
        except Exception as e:
            logger.error(f"✘ Failed to load plugin {plugin_name}: {e}")

    # Global Router for Interactive Wizards
    @bot.on_message(filters.private & filters.text & ~filters.command(["start", "help", "login", "logout", "forward", "forwardstop", "search", "add_post", "edit"]))
    async def global_router(client, message):
        uid = message.from_user.id
        state = user_state.get(uid)
        if not state: return
        action = state.get("action")

        # Route based on prefix
        if action.startswith("ask_") and "phone" in action or "otp" in action or "pass" in action:
            from plugins.login import login_wizard
            return await login_wizard(client, message, state)
        elif action.startswith("fwd_"):
            from plugins.forward import forward_wizard
            return await forward_wizard(client, message, state)
        # Add other dynamic routes as needed

    logger.info("Intelligence Suite Initialized.")
