from pyrogram import Client, filters
from bot import is_authorized, user_state
from core.session import session_manager
from core.logger import bot_logger

@Client.on_message(filters.command("login") & filters.private)
async def login_cmd(client, message):
    if not await is_authorized(message.from_user.id):
        return await message.reply("🚫 **Unauthorized Access.**")

    if await session_manager.get_client():
        return await message.reply("✅ **Already logged in.** Use /logout to reset.")

    user_state[message.from_user.id] = {"action": "ask_phone"}
    await message.reply(
        "📱 **Premium Login Wizard**\n\n"
        "Please send your phone number in this exact format:\n"
        "`+91XXXXXXXXXX`"
    )

async def login_wizard(client, message, state):
    uid = message.from_user.id
    action = state.get("action")

    if action == "ask_phone":
        phone = message.text.strip()
        if not phone.startswith("+") or len(phone) < 10:
            return await message.reply("❌ **Invalid Format.** Use `+91XXXXXXXXXX`:")

        await message.reply("⏳ **Requesting OTP from Telegram...**")
        if await session_manager.login_start(phone):
            user_state[uid].update({"action": "ask_otp", "phone": phone})
            await message.reply("📩 **OTP Sent.** Please enter the code you received:")
        else:
            await message.reply("❌ **Failed to send OTP.** Check the number and try again.")

    elif action == "ask_otp":
        code = message.text.strip()
        try: await message.delete()
        except: pass

        res = await session_manager.login_complete(code)
        if res == "2FA":
            user_state[uid].update({"action": "ask_password", "otp": code})
            await message.reply("🔐 **Two-Step Verification Enabled.** Please enter your password:")
        elif res is True:
            await message.reply("🎉 **Login Successful!** Userbot session is now permanent.")
            user_state.pop(uid, None)
        else:
            await message.reply("❌ **Invalid OTP.** Please try again:")

    elif action == "ask_password":
        password = message.text.strip()
        try: await message.delete()
        except: pass

        if await session_manager.login_complete(state["otp"], password) is True:
            await message.reply("🎉 **Login Successful!** Userbot session is now permanent.")
            user_state.pop(uid, None)
        else:
            await message.reply("❌ **Invalid Password.** Please try again:")
