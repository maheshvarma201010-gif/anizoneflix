import asyncio
from pyrogram import Client, filters
from config.config import Config
from core.session import userbot_manager
from core.peer_manager import peer_manager
from core.permission_checker import permission_checker
from core.forward_engine import forward_engine
from core.startup_checker import StartupChecker
from utils.validators import parse_telegram_link, is_valid_telegram_id
from core.logger import logger

@Client.on_message(filters.command("forward") & filters.user(Config.ADMIN_IDS))
async def forward_command_handler(bot, message):
    user_id = message.from_user.id

    # 1. Check Userbot Login
    client = await userbot_manager.get_client(user_id)
    if not client:
        return await message.reply_text("❌ **Not Logged In.** Please use `/login` first.")

    # 2. Collect Inputs
    try:
        # First Link
        prompt1 = await message.chat.ask("🔗 **Step 1: First Message Link**\n\nPlease send the link of the first message to forward.")
        if prompt1.text == "/cancel": return await message.reply_text("Cancelled.")
        source_chat, start_id = parse_telegram_link(prompt1.text.strip())

        if not source_chat or not start_id:
            return await message.reply_text("❌ **Invalid Link format.**")

        # Last Link
        prompt2 = await message.chat.ask("🔗 **Step 2: Last Message Link**\n\nPlease send the link of the last message in the range.")
        if prompt2.text == "/cancel": return await message.reply_text("Cancelled.")
        _, end_id = parse_telegram_link(prompt2.text.strip())

        if not end_id:
            return await message.reply_text("❌ **Invalid Link format.**")

        if end_id < start_id:
            return await message.reply_text("❌ **End ID must be greater than Start ID.**")

        # Target Channel
        prompt3 = await message.chat.ask("🎯 **Step 3: Target Channel**\n\nPlease send the Username or ID of the target channel.")
        if prompt3.text == "/cancel": return await message.reply_text("Cancelled.")
        target_chat_raw = prompt3.text.strip()

        if not is_valid_telegram_id(target_chat_raw):
            return await message.reply_text("❌ **Invalid Username or ID.**")

    except Exception as e:
        logger.error(f"Input collection error: {e}")
        return await message.reply_text("❌ **An error occurred during input collection.**")

    # 3. Resolve & Verify
    status_msg = await message.reply_text("⏳ **Verifying permissions and resolving peers...**")

    try:
        # Resolve target
        target_chat = await peer_manager.resolve_peer(client, target_chat_raw)
        source_chat = await peer_manager.resolve_peer(client, source_chat)

        # Verify Bot is Admin in target
        is_bot_admin = await permission_checker.is_admin(bot, target_chat)
        if not is_bot_admin:
            return await status_msg.edit_text("❌ **Bot is not an administrator in the target channel.**")

        # Verify User is Admin in target (using userbot client)
        is_user_admin = await permission_checker.is_admin(client, target_chat)
        if not is_user_admin:
            return await status_msg.edit_text("❌ **Your user account is not an administrator in the target channel.**")

        # 4. Hidden Test Message
        success, info = await StartupChecker.test_target_channel(bot, target_chat)
        if not success:
            return await status_msg.edit_text(f"❌ **Permission Test Failed:** {info}")

        # 5. Start Forwarding
        await status_msg.edit_text("✅ **Verification Complete. Starting Forwarding Engine...**")
        await forward_engine.start_forward(client, bot, user_id, source_chat, target_chat, start_id, end_id)

    except Exception as e:
        logger.error(f"Forwarding setup error: {e}")
        await status_msg.edit_text(f"❌ **Critical Error during setup:** `{e}`")
