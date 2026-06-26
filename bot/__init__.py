import asyncio
import logging
import traceback
import os
import glob
import importlib
from pyrogram import Client, filters, ContinuePropagation, utils
from pyrogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from config.config import Config
from database.db import db

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ANIZONEFLIX_BOT")

# --- PYROGRAM PATCH ---
utils.MIN_CHANNEL_ID = -1009999999999

bot = Client(
    "anizoneflix_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    plugins=dict(root="plugins"),
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
        BotCommand("redirect", "🔗 Trace Redirects"),
        BotCommand("help", "📖 Documentation")
    ]

    for admin_id in Config.ADMIN_IDS:
        try: await client.set_bot_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except: pass

    logger.info("Bot command scopes synchronized.")

def register_handlers(bot: Client):
    @bot.on_message(filters.private & filters.text & ~filters.command(["start", "help", "login", "logout", "forward", "forwardstop", "search", "add_post", "edit"]))
    async def global_router(client, message):
        uid = message.from_user.id
        state = user_state.get(uid)
        if not state: return
        action = state.get("action")

        if action.startswith("ask_") and any(x in action for x in ["phone", "otp", "pass"]):
            from plugins.login import login_wizard
            return await login_wizard(client, message, state)

        elif action.startswith("fwd_"):
            from plugins.forward import forward_wizard
            return await forward_wizard(client, message, state)

        elif any(x in action for x in ["ask_edit_", "select_anime", "edit_", "ask_manual", "ask_category"]):
            from plugins.anime_admin import anime_wizard
            return await anime_wizard(client, message, state)

    logger.info("Intelligence Suite Initialized.")
