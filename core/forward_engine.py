import asyncio
import time
from pyrogram import errors
from core.logger import forwarder_logger

class ForwardEngine:
    def __init__(self, task_id, from_chat, to_chat, start_id, end_id):
        self.task_id = task_id
        self.from_chat = from_chat
        self.to_chat = to_chat
        self.start_id = min(int(start_id), int(end_id))
        self.end_id = max(int(start_id), int(end_id))
        self.current_id = self.start_id
        self.is_running = False

        self.stats = {
            "total": self.end_id - self.start_id + 1,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "start_time": None
        }

    async def run(self, client, status_callback=None):
        self.is_running = True
        self.stats["start_time"] = time.time()

        while self.is_running and self.current_id <= self.end_id:
            try:
                # Use copy_message to avoid forward tags
                await client.copy_message(
                    chat_id=self.to_chat,
                    from_chat_id=self.from_chat,
                    message_id=self.current_id
                )
                self.stats["success"] += 1
            except errors.FloodWait as e:
                forwarder_logger.warning(f"FloodWait: Sleeping for {e.value}s")
                await asyncio.sleep(e.value)
                continue
            except errors.MessageIdInvalid:
                self.stats["skipped"] += 1
            except Exception as e:
                forwarder_logger.error(f"Copy error at {self.current_id}: {e}")
                self.stats["failed"] += 1

            self.current_id += 1
            if status_callback and (self.stats["success"] + self.stats["failed"] + self.stats["skipped"]) % 5 == 0:
                await status_callback(self.stats, self.get_progress())

            await asyncio.sleep(1.0) # Rate limiting safety

        self.is_running = False
        return self.stats

    def get_progress(self):
        processed = self.stats["success"] + self.stats["failed"] + self.stats["skipped"]
        percentage = round((processed / self.stats["total"]) * 100, 2)
        elapsed = time.time() - self.stats["start_time"]
        eta = round((elapsed / (processed or 1)) * (self.stats["total"] - processed), 2)
        return {"processed": processed, "percentage": percentage, "eta": f"{eta}s"}

    def stop(self):
        self.is_running = False

active_tasks = {}
