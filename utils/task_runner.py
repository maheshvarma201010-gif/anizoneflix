import asyncio
import logging
import re
import traceback
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ButtonStyle
from pyrogram.errors import FloodWait
from config.config import Config
from database.db import db

logger = logging.getLogger("MZ_TASK_RUNNER")
logger.setLevel(logging.INFO)

def detect_quality(text: str) -> str:
    if not text:
        return "720p" # default fallback if not found
    text_lower = text.lower()
    match = re.search(r'\b(1080|720|480)p?\b', text_lower)
    if match:
        q = match.group(1)
        return f"{q}p"
    return "720p"

def extract_download_url(text: str) -> str:
    if not text:
        return None

    # First try matching specific download labels like "Download :" or "Dᴏᴡɴʟᴏᴀᴅ :"
    match = re.search(r'(?:Download|Dᴏᴡɴʟᴏᴀᴅ)\s*:\s*(https?://[^\s]+)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Fallback: Find all HTTP/HTTPS links
    urls = re.findall(r'https?://[^\s]+', text)
    for url in urls:
        # Ignore watch online links
        if "watch" in url.lower():
            continue
        if "download" in url.lower() or "cdn" in url.lower() or "stream" in url.lower():
            return url.strip()

    # If urls exist and no "watch" link, return the first one
    for url in urls:
        if "watch" not in url.lower():
            return url.strip()

    return None

class TaskRunner:
    def __init__(self):
        self.userbot = None
        self.running_tasks = set()

    async def get_userbot(self):
        session_str = await db.get_setting("userbot_session")
        if not session_str:
            logger.warning("Userbot session not configured.")
            return None

        if self.userbot and self.userbot.is_connected:
            return self.userbot

        try:
            self.userbot = Client(
                "userbot_session_client",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                session_string=session_str,
                in_memory=True
            )
            await self.userbot.start()
            logger.info("Userbot Client started successfully.")
            return self.userbot
        except Exception as e:
            logger.error(f"Failed to start Userbot client: {e}")
            self.userbot = None
            return None

    async def stop_userbot(self):
        if self.userbot and self.userbot.is_connected:
            try:
                await self.userbot.stop()
                logger.info("Userbot Client stopped.")
            except Exception as e:
                logger.error(f"Error stopping userbot: {e}")

    async def run_task(self, task_id: str):
        if task_id in self.running_tasks:
            logger.info(f"Task {task_id} is already running.")
            return

        self.running_tasks.add(task_id)
        try:
            task = await db.get_task(task_id)
            if not task:
                logger.error(f"Task {task_id} not found in DB.")
                return

            ub = await self.get_userbot()
            if not ub:
                logger.error(f"Cannot run task {task_id}: Userbot is not available.")
                return

            logger.info(f"Starting processing for task {task_id}: {task.get('name')}")
            await self._process_collected_files(ub, task_id)
        except Exception as e:
            logger.error(f"Error in task {task_id}: {e}")
            logger.error(traceback.format_exc())
        finally:
            self.running_tasks.discard(task_id)

    async def _process_collected_files(self, ub: Client, task_id: str):
        task = await db.get_task(task_id)
        if not task:
            return

        collected_files = task.get("collected_files", [])
        dl_bot = task.get("dl_bot_username")
        output_group = task.get("output_group_link")
        prefix_cmd = task.get("prefix_cmd")
        admin_name = task.get("name")

        extracted_links = []

        for item in collected_files:
            chat_id = item.get("chat_id")
            msg_id = item.get("message_id")
            orig_filename = item.get("file_name", "")
            orig_caption = item.get("caption", "")

            quality = detect_quality(f"{orig_filename} {orig_caption}")

            # Send collected file to Download Link Bot from Userbot using file_id
            file_id = item.get("file_id")
            try:
                if file_id:
                    await ub.send_cached_media(
                        chat_id=dl_bot,
                        file_id=file_id,
                        caption=orig_caption
                    )
                else:
                    await ub.forward_messages(
                        chat_id=dl_bot,
                        from_chat_id=chat_id,
                        message_ids=msg_id
                    )
            except FloodWait as fw:
                await asyncio.sleep(fw.value)
                if file_id:
                    await ub.send_cached_media(
                        chat_id=dl_bot,
                        file_id=file_id,
                        caption=orig_caption
                    )
                else:
                    await ub.forward_messages(
                        chat_id=dl_bot,
                        from_chat_id=chat_id,
                        message_ids=msg_id
                    )
            except Exception as e:
                logger.error(f"Error sending file to {dl_bot}: {e}")
                continue

            # Wait for DL Bot response
            dl_url = None
            for _ in range(30): # wait up to 30 seconds
                await asyncio.sleep(1)
                async for response in ub.get_chat_history(dl_bot, limit=5):
                    if response.from_user and response.from_user.is_bot:
                        resp_text = response.text or response.caption or ""
                        url = extract_download_url(resp_text)
                        if url:
                            dl_url = url
                            break
                if dl_url:
                    break

            if dl_url:
                extracted_links.append({
                    "quality": quality,
                    "download_url": dl_url,
                    "original_filename": orig_filename
                })
                logger.info(f"Extracted DL link for task {task_id} ({quality}): {dl_url}")

        # Update DB task state
        await db.update_task(task_id, {
            "extracted_dl_links": extracted_links,
            "step": "WAITING_GENERATED_LINKS",
            "status": "WAITING_GENERATED_LINKS"
        })

        # Send formatted prefix command messages to output group
        for link_info in extracted_links:
            q = link_info["quality"]
            dl_link = link_info["download_url"]
            cmd_msg = f"{prefix_cmd} {dl_link} -e -n {admin_name} {q}.mkv"

            try:
                await ub.send_message(output_group, cmd_msg)
            except FloodWait as fw:
                await asyncio.sleep(fw.value)
                await ub.send_message(output_group, cmd_msg)
            except Exception as e:
                logger.error(f"Error sending prefix command to {output_group}: {e}")

        # Continue to monitor Link Generator Bot for generated deep links
        await self._monitor_link_generator_bot(ub, task_id)

    async def _monitor_link_generator_bot(self, ub: Client, task_id: str):
        task = await db.get_task(task_id)
        if not task:
            return

        lg_bot = task.get("link_gen_bot_username")
        output_group = task.get("output_group_link")
        admin_name = task.get("name")
        generated_links = {} # quality -> telegram deep link

        for _ in range(60): # Wait up to 60 seconds
            if len(generated_links) >= 3:
                break
            await asyncio.sleep(2)
            async for response in ub.get_chat_history(lg_bot, limit=10):
                if response.from_user and response.from_user.is_bot:
                    resp_text = response.text or response.caption or ""
                    # Check for deep link URL
                    match = re.search(r'https?://(?:t\.me|telegram\.me)/[^\s]+', resp_text)
                    if match:
                        deep_link = match.group(0).strip()
                        # Detect quality from response text
                        quality = detect_quality(resp_text)
                        if quality not in generated_links:
                            generated_links[quality] = deep_link
                            logger.info(f"Task {task_id} generated link for {quality}: {deep_link}")

        # Update DB task state
        await db.update_task(task_id, {
            "generated_links": generated_links,
            "step": "WAITING_FINAL_FILES",
            "status": "WAITING_FINAL_FILES"
        })

        # Build and send final quality buttons to Output Group using Standard Bot Client
        from bot import bot as main_bot

        buttons = []
        for q in ["480p", "720p", "1080p"]:
            link = generated_links.get(q, "https://t.me")
            buttons.append([InlineKeyboardButton(f"{q}", url=link)])

        markup = InlineKeyboardMarkup(buttons)
        text = f"🎬 **{admin_name}**\n\nSelect Quality to Download:"

        try:
            await main_bot.send_message(output_group, text, reply_markup=markup)
        except FloodWait as fw:
            await asyncio.sleep(fw.value)
            await main_bot.send_message(output_group, text, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error sending final quality buttons to {output_group}: {e}")

        # Continue to monitor incoming files from configured /monitor bots
        await self._monitor_incoming_files(ub, task_id)

    async def _monitor_incoming_files(self, ub: Client, task_id: str):
        task = await db.get_task(task_id)
        if not task:
            return

        admin_name = task.get("name")
        monitored_bots = await db.get_setting("monitorbots", [])
        if not monitored_bots:
            logger.warning(f"No monitor bots configured for task {task_id}.")
            return

        received_qualities = set()
        received_files = []

        for _ in range(120): # Monitor for up to 120 seconds
            if len(received_qualities) >= 3:
                break
            await asyncio.sleep(3)

            for bot_username in monitored_bots:
                try:
                    async for msg in ub.get_chat_history(bot_username, limit=10):
                        # Filter out non-bot / unrelated messages
                        if not (msg.from_user and msg.from_user.is_bot):
                            continue
                        # Strictly filter media files (documents, videos, audio)
                        media_obj = msg.document or msg.video or msg.audio
                        if not media_obj:
                            continue

                        file_name = getattr(media_obj, "file_name", "") or getattr(media_obj, "title", "") or ""
                        caption = msg.caption or ""
                        full_text = f"{file_name} {caption}".strip()

                        # Match task Name
                        if admin_name.lower() not in full_text.lower():
                            continue

                        # Detect Quality
                        quality = detect_quality(full_text)
                        if quality in ["480p", "720p", "1080p"] and quality not in received_qualities:
                            received_qualities.add(quality)
                            received_files.append({
                                "quality": quality,
                                "file_name": file_name,
                                "chat_id": bot_username,
                                "message_id": msg.id
                            })
                            logger.info(f"Task {task_id} matched file for {quality}: {file_name}")

                except Exception as e:
                    logger.error(f"Error checking chat history for {bot_username}: {e}")

        # Forward matched files to Output Group
        output_group = task.get("output_group_link")
        for item in received_files:
            try:
                await ub.forward_messages(
                    chat_id=output_group,
                    from_chat_id=item["chat_id"],
                    message_ids=item["message_id"]
                )
            except FloodWait as fw:
                await asyncio.sleep(fw.value)
                await ub.forward_messages(
                    chat_id=output_group,
                    from_chat_id=item["chat_id"],
                    message_ids=item["message_id"]
                )
            except Exception as fe:
                logger.error(f"Error forwarding matching file to {output_group}: {fe}")

        # Complete task state
        await db.update_task(task_id, {
            "received_final_files": received_files,
            "step": "COMPLETED",
            "status": "COMPLETED"
        })
        logger.info(f"Task {task_id} completed successfully ({len(received_qualities)} qualities matched and forwarded). Marked COMPLETED.")

task_runner = TaskRunner()
