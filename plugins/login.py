import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import (
    PhoneNumberInvalid,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    SessionPasswordNeeded,
    PasswordHashInvalid
)
from config.config import Config
from database.session_storage import session_storage
from core.session import userbot_manager
from utils.validators import validate_phone
from core.logger import logger

@Client.on_message(filters.command("login") & filters.user(Config.ADMIN_IDS))
async def login_handler(bot, message):
    user_id = message.from_user.id

    # 1. Ask for Phone Number
    prompt = await message.chat.ask(
        "📱 **Step 1: Authentication**\n\n"
        "Please send your phone number in this exact format:\n"
        "`+91XXXXXXXXXX` (with country code)"
    )
    phone_number = prompt.text.strip().replace(" ", "")

    if not validate_phone(phone_number):
        return await message.reply_text("❌ **Invalid Format.** Please use `+91XXXXXXXXXX` and try again.")

    await message.reply_text("⏳ **Sending OTP...**")

    # Initialize a temporary client
    temp_client = Client(
        name=f"temp_{user_id}",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        in_memory=True
    )

    try:
        await temp_client.connect()
        code_info = await temp_client.send_code(phone_number)
    except PhoneNumberInvalid:
        return await message.reply_text("❌ **Invalid Phone Number.**")
    except Exception as e:
        logger.error(f"Login error: {e}")
        return await message.reply_text(f"❌ **Error:** `{e}`")

    # 2. Ask for OTP
    otp_prompt = await message.chat.ask(
        "📩 **Step 2: Verification**\n\n"
        f"OTP has been sent to `{phone_number}`.\n"
        "Please send the code here."
    )
    otp_code = otp_prompt.text.strip().replace(" ", "")

    try:
        await temp_client.sign_in(phone_number, code_info.phone_code_hash, otp_code)
    except SessionPasswordNeeded:
        # 3. Handle 2FA
        pass_prompt = await message.chat.ask(
            "🔒 **Step 3: Two-Step Verification**\n\n"
            "This account has 2FA enabled. Please send your password."
        )
        password = pass_prompt.text.strip()
        try:
            await temp_client.check_password(password)
        except PasswordHashInvalid:
            return await message.reply_text("❌ **Incorrect Password.**")
    except PhoneCodeInvalid:
        return await message.reply_text("❌ **Invalid OTP Code.**")
    except PhoneCodeExpired:
        return await message.reply_text("❌ **OTP Expired.**")
    except Exception as e:
        return await message.reply_text(f"❌ **Login Failed:** `{e}`")

    # 4. Success & Save
    session_string = await temp_client.export_session_string()
    await session_storage.save_session(user_id, session_string)

    # Start the actual userbot client via manager
    await userbot_manager.start_session(user_id, session_string)

    await temp_client.disconnect()

    await message.reply_text(
        "✅ **Authentication Successful!**\n\n"
        "Your account is now linked and the session is saved permanently. "
        "You can now use `/forward` to clone content."
    )
    logger.info(f"User {user_id} logged in successfully.")
