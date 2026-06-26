import asyncio
from pyrogram import Client, errors
from config.config import Config
from database.db import db
from core.logger import userbot_logger

class SessionManager:
    def __init__(self):
        self.client = None
        self._phone_number = None
        self._phone_code_hash = None

    async def get_client(self):
        if self.client and self.client.is_connected:
            return self.client

        session_string = await db.get_userbot_session()
        if session_string:
            try:
                self.client = Client(
                    "userbot_session",
                    api_id=Config.API_ID,
                    api_hash=Config.API_HASH,
                    session_string=session_string,
                    in_memory=True
                )
                await self.client.start()
                me = await self.client.get_me()
                userbot_logger.info(f"✔ Userbot session restored: @{me.username}")
                return self.client
            except Exception as e:
                userbot_logger.error(f"✘ Session restoration failed: {e}")
                self.client = None
        return None

    async def login_start(self, phone):
        self._phone_number = phone
        self.client = Client(
            "userbot_temp",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            in_memory=True
        )
        await self.client.connect()
        try:
            sent_code = await self.client.send_code(phone)
            self._phone_code_hash = sent_code.phone_code_hash
            return True
        except Exception as e:
            userbot_logger.error(f"Login error: {e}")
            await self.client.disconnect()
            return False

    async def login_complete(self, code, password=None):
        try:
            await self.client.sign_in(self._phone_number, self._phone_code_hash, code)
        except errors.SessionPasswordNeeded:
            if not password:
                return "2FA"
            await self.client.check_password(password)

        session_string = await self.client.export_session_string()
        await db.save_userbot_session(session_string)
        me = await self.client.get_me()
        userbot_logger.info(f"✔ Login successful: @{me.username}")
        return True

    async def logout(self):
        if self.client:
            try:
                await self.client.log_out()
            except: pass
            self.client = None
        await db.delete_userbot_session()
        return True

session_manager = SessionManager()
