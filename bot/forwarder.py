import asyncio
import logging
import time
from pyrogram import errors
from bot.userbot import userbot_manager
from database.db import db

logger = logging.getLogger("ANIZONEFLIX_FORWARDER")

class ForwardingTask:
    def __init__(self, task_id, from_chat, to_chat, start_id, end_id):
        self.task_id = task_id
        self.from_chat = from_chat
        self.to_chat = to_chat
        self.start_id = min(int(start_id), int(end_id))
        self.end_id = max(int(start_id), int(end_id))
        self.current_id = self.start_id
        self.is_running = False
        self.stats = {"total": self.end_id - self.start_id + 1, "success": 0, "failed": 0, "start_time": None}

    async def run(self, client, status_callback=None):
        self.is_running = True
        self.stats["start_time"] = time.time()

        # Permission Test
        try:
            test_msg = await client.send_message(self.to_chat, "🔄 **Initialization Permission Test...**")
            await test_msg.delete()
        except Exception as e:
            logger.error(f"Permission test failed for {self.to_chat}: {e}")
            self.is_running = False
            return f"❌ **Missing Permissions:** {str(e)}"

        while self.is_running and self.current_id <= self.end_id:
            try:
                # Forwarding in small chunks to be safer with PeerID resolution and FloodWait
                # but since we want exact forwarding, we use forward_messages
                await client.forward_messages(
                    chat_id=self.to_chat,
                    from_chat_id=self.from_chat,
                    message_ids=self.current_id
                )
                self.stats["success"] += 1
            except errors.FloodWait as e:
                logger.warning(f"FloodWait: Sleeping for {e.value}s")
                await asyncio.sleep(e.value)
                continue # Retry same ID
            except errors.MessageIdInvalid:
                # Silently skip missing IDs
                pass
            except Exception as e:
                logger.error(f"Forward error at {self.current_id}: {e}")
                self.stats["failed"] += 1
                # Retry once after a small backoff for random RPC errors
                await asyncio.sleep(2)

            self.current_id += 1
            if status_callback and self.stats["success"] % 5 == 0:
                await status_callback(self.stats, self.current_id - self.start_id)

            # Small delay to prevent hitting limits too fast
            await asyncio.sleep(0.5)

        self.is_running = False
        duration = round(time.time() - self.stats["start_time"], 2)
        return (
            f"✅ **Forward Completed**\n\n"
            f"📊 **Statistics:**\n"
            f"• Total: `{self.stats['total']}`\n"
            f"• Success: `{self.stats['success']}`\n"
            f"• Failed: `{self.stats['failed']}`\n"
            f"• Time Taken: `{duration}s`"
        )

    def stop(self):
        self.is_running = False

active_tasks = {}
