import logging
import asyncio
import os
from pyrogram import Client, errors
from config.config import Config
from database.db import db

logger = logging.getLogger("ANIZONEFLIX_USERBOT")

class UserbotManager:
    def __init__(self):
        self.client = None
        self._is_logging_in = False
        self._phone_number = None
        self._phone_code_hash = None

    async def get_client(self):
        if self.client and self.client.is_connected:
            return self.client

        session_string = await db.get_userbot_session()
        if session_string:
            try:
                self.client = Client(
                    "anizoneflix_userbot",
                    api_id=Config.API_ID,
                    api_hash=Config.API_HASH,
                    session_string=session_string,
                    in_memory=True
                )
                await self.client.start()
                me = await self.client.get_me()
                logger.info(f"✔ Userbot session restored: @{me.username} ({me.id})")

                # System Integrity Check
                try:
                    # Test reachability
                    await self.client.get_chat("me")
                    logger.info("✔ Userbot integrity verified: Account reachable.")
                except Exception as e:
                    logger.error(f"✘ Userbot integrity check failed: {e}")

                return self.client
            except Exception as e:
                logger.error(f"Failed to restore userbot session: {e}")
                self.client = None
        return None

    async def start_login(self, phone_number):
        self._phone_number = phone_number
        self.client = Client(
            "anizoneflix_userbot_temp",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            in_memory=True
        )
        await self.client.connect()
        try:
            sent_code = await self.client.send_code(phone_number)
            self._phone_code_hash = sent_code.phone_code_hash
            return True
        except Exception as e:
            logger.error(f"Error sending login code: {e}")
            await self.client.disconnect()
            return False

    async def complete_login(self, code, password=None):
        try:
            await self.client.sign_in(self._phone_number, self._phone_code_hash, code)
        except errors.SessionPasswordNeeded:
            if not password:
                return "2FA_REQUIRED"
            await self.client.check_password(password)

        session_string = await self.client.export_session_string()
        await db.save_userbot_session(session_string)

        me = await self.client.get_me()
        logger.info(f"Userbot login successful: @{me.username}")
        return True

    async def logout(self):
        if self.client:
            try:
                if self.client.is_connected:
                    await self.client.log_out()
            except: pass
            self.client = None
        await db.delete_userbot_session()
        return True

    async def resolve_peer(self, peer_id):
        client = await self.get_client()
        if not client: return None
        try:
            return await client.get_chat(peer_id)
        except Exception as e:
            logger.error(f"Error resolving peer {peer_id}: {e}")
            return None

userbot_manager = UserbotManager()
