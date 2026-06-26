import asyncio
import time
from pyrogram.errors import FloodWait, MessageIdInvalid
from core.logger import logger
from utils.helpers import get_progress_bar, format_eta, format_time

class ForwardEngine:
    def __init__(self):
        self.active_tasks = {} # user_id -> task

    async def start_forward(self, client, bot, user_id, source_chat, target_chat, start_id, end_id):
        """
        Starts the forwarding process in a background task.
        """
        task = asyncio.create_task(self._forward_loop(client, bot, user_id, source_chat, target_chat, start_id, end_id))
        self.active_tasks[user_id] = task
        return task

    async def stop_forward(self, user_id):
        """
        Stops an active forwarding task.
        """
        task = self.active_tasks.pop(user_id, None)
        if task:
            task.cancel()
            return True
        return False

    async def _forward_loop(self, client, bot, user_id, source_chat, target_chat, start_id, end_id):
        stats = {
            "total": end_id - start_id + 1,
            "forwarded": 0,
            "skipped": 0,
            "failed": 0,
            "start_time": time.time()
        }

        status_msg = await bot.send_message(user_id, "🚀 **Starting Forwarding Engine...**")

        try:
            processed_media_groups = set()

            for msg_id in range(start_id, end_id + 1):
                if asyncio.current_task().cancelled():
                    break

                try:
                    msg = await client.get_messages(source_chat, msg_id)

                    if not msg or msg.empty:
                        stats["skipped"] += 1
                        continue

                    # Handle Media Groups (Albums)
                    if msg.media_group_id:
                        if msg.media_group_id in processed_media_groups:
                            # Already forwarded as part of the group
                            stats["forwarded"] += 1
                            continue

                        # Fetch the entire media group
                        media_group = await client.get_media_group(source_chat, msg_id)
                        await client.copy_media_group(target_chat, source_chat, msg_id)

                        # Mark all message IDs in this group as processed
                        for m in media_group:
                            processed_media_groups.add(m.media_group_id)

                        stats["forwarded"] += 1 # We count the group as a single logical forward if preferred, or by count.
                        # For the range loop, we'll increment for the others in the loop skip.
                    else:
                        # Single message
                        await client.copy_message(target_chat, source_chat, msg_id)
                        stats["forwarded"] += 1

                    if (stats["forwarded"] + stats["skipped"] + stats["failed"]) % 5 == 0:
                        await self._update_progress(bot, user_id, status_msg, stats)

                except FloodWait as e:
                    logger.warning(f"FloodWait: {e.value}s")
                    await asyncio.sleep(e.value)
                    continue
                except MessageIdInvalid:
                    stats["skipped"] += 1
                except Exception as e:
                    logger.error(f"Error forwarding {msg_id}: {e}")
                    stats["failed"] += 1

                await asyncio.sleep(0.5)

            await self._update_progress(bot, user_id, status_msg, stats, final=True)

        except asyncio.CancelledError:
            logger.info(f"Forwarding task for {user_id} cancelled.")
            await bot.send_message(user_id, f"🛑 **Forwarding Stopped Safely.**\n\n{self._get_stats_text(stats)}")
        except Exception as e:
            logger.error(f"Forwarding loop error for {user_id}: {e}")
            await bot.send_message(user_id, f"❌ **Forwarding Engine Crashed:** `{e}`")
        finally:
            self.active_tasks.pop(user_id, None)

    async def _update_progress(self, bot, user_id, status_msg, stats, final=False):
        text = self._get_stats_text(stats, final)
        try:
            await status_msg.edit_text(text)
        except Exception:
            pass

    def _get_stats_text(self, stats, final=False):
        processed = stats["forwarded"] + stats["skipped"] + stats["failed"]
        total = stats["total"]
        percentage = (processed / total) * 100 if total > 0 else 0
        elapsed = time.time() - stats["start_time"]
        eta = (elapsed / processed) * (total - processed) if processed > 0 else 0

        progress_bar = get_progress_bar(percentage)
        header = "✅ **Forwarding Completed!**" if final else "⏳ **Forwarding in Progress...**"

        text = (
            f"{header}\n\n"
            f"{progress_bar} `{percentage:.1f}%`\n\n"
            f"📂 **Total:** `{total}`\n"
            f"✅ **Forwarded:** `{stats['forwarded']}`\n"
            f"⏩ **Skipped:** `{stats['skipped']}`\n"
            f"❌ **Failed:** `{stats['failed']}`\n"
            f"🕒 **Time Elapsed:** `{format_time(elapsed)}`\n"
        )

        if not final:
            text += f"⏳ **ETA:** `{format_eta(eta)}`"
        else:
            text += f"🏁 **Completed in:** `{format_time(elapsed)}`"

        return text

forward_engine = ForwardEngine()
