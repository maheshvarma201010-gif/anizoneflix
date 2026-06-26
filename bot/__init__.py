import os
import importlib
import logging
from pyrogram import Client
from config.config import Config
from database.db import db
from core.logger import setup_logger
from pyrogram.types import BotCommand
from pyromod import listen # Initialize pyromod for interactive prompts

# Setup Logging
logger = setup_logger("ANIZONEFLIX_BOT")

bot = Client(
    "anizoneflix_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    in_memory=True,
    plugins=dict(root="plugins") # Dynamic plugin loading from 'plugins/' folder
)

async def set_commands(client):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("login", "Login to User account"),
        BotCommand("logout", "Logout and clear session"),
        BotCommand("forward", "Start Auto Forwarding"),
        BotCommand("forwardstop", "Stop Forwarding"),
        BotCommand("ping", "System Latency Check"),
        BotCommand("help", "View full documentation")
    ]
    try:
        await client.set_bot_commands(commands)
        logger.info("Bot commands synchronized.")
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}")

def register_handlers(bot: Client):
    """
    With Pyrogram plugins, handlers are auto-loaded.
    This function maintains the interface for app.py lifespan.
    """
    logger.info("Modular Plugin Suite initialized.")
