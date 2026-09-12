import asyncio
import logging
import re
from pyrogram import Client, filters
from database.db import db
from utils.task_helpers import (
    parse_file_entries,
    filter_highest_mb_file,
    extract_download_link,
    format_lgroup_command
)

logger = logging.getLogger("MZ_TASK_RUNNER")

class TaskQueueManager:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.active_prefixes = set()
        self.is_running = False
        self.user_client = None
        self.user_client_session = None
        self._client_lock = asyncio.Lock()

    def start(self):
        if not self.is_running:
            self.is_running = True
            asyncio.create_task(self._process_queue())

    def stop(self):
        self.is_running = False

    async def get_user_client(self):
        async with self._client_lock:
            session_str = await db.get_setting("session_string")
            if not session_str:
                return None
            if self.user_client and self.user_client_session == session_str:
                return self.user_client
            if self.user_client:
                try:
                    await self.user_client.stop()
                except Exception:
                    pass
                self.user_client = None
            try:
                from config.config import Config
                self.user_client = Client(
                    "shared_userbot_session",
                    api_id=Config.API_ID,
                    api_hash=Config.API_HASH,
                    session_string=session_str,
                    in_memory=True
                )
                await self.user_client.start()
                self.user_client_session = session_str
                return self.user_client
            except Exception as e:
                logger.error(f"Failed to start shared userbot client: {e}")
                self.user_client = None
                return None

    async def add_task(self, task_data):
        await self.queue.put(task_data)
        self.start()

    async def _process_queue(self):
        while self.is_running:
            try:
                task_data = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                prefix = await self._acquire_prefix()
                logger.info(f"Acquired prefix '{prefix}' for task '{task_data.get('name')}'")
                asyncio.create_task(self._run_single_task(task_data, prefix))
            except Exception as e:
                logger.error(f"Error starting queued task: {e}")
            finally:
                self.queue.task_done()

    async def _acquire_prefix(self):
        while True:
            lgroup = await db.get_setting("setlgroup")
            if not lgroup:
                cmds = ["/l"]
            else:
                if isinstance(lgroup, dict):
                    cmds = lgroup.get("commands", ["/l"])
                elif isinstance(lgroup, list):
                    cmds = lgroup
                else:
                    cmds = [str(lgroup)]

            if not cmds:
                cmds = ["/l"]

            for c in cmds:
                if c not in self.active_prefixes:
                    self.active_prefixes.add(c)
                    return c

            await asyncio.sleep(2)

    def release_prefix(self, prefix):
        self.active_prefixes.discard(prefix)

    async def _run_single_task(self, task_data, prefix):
        task_name = task_data["name"]
        page_link = task_data.get("page_link")
        group_name = task_data.get("group_name")

        logger.info(f"Starting Task: name='{task_name}', prefix='{prefix}'")

        try:
            target_group = await db.get_setting("setgroup")
            moviebot = await db.get_setting("setmoviebot")
            linkbot = await db.get_setting("setlink")
            lgroup_setting = await db.get_setting("setlgroup")

            lgroup_target = None
            if isinstance(lgroup_setting, dict):
                lgroup_target = lgroup_setting.get("target")

            user_client = await self.get_user_client()

            await execute_task_flow(
                user_client=user_client,
                task_name=task_name,
                page_link=page_link,
                group_name=group_name,
                prefix=prefix,
                target_group=target_group,
                moviebot=moviebot,
                linkbot=linkbot,
                lgroup_target=lgroup_target
            )
        except Exception as err:
            logger.error(f"Task '{task_name}' execution error: {err}")
        finally:
            self.release_prefix(prefix)
            logger.info(f"Released prefix '{prefix}' for task '{task_name}'")

async def scan_all_pages_and_get_entries(user_client, chat_id, message_id):
    """
    Collects file entries from current message and navigates Next pages until the end.
    """
    all_entries = []
    visited_pages = set()

    current_msg_id = message_id

    while True:
        try:
            msg = await user_client.get_messages(chat_id, current_msg_id)
            if not msg or not (msg.text or msg.caption):
                break

            txt = msg.text or msg.caption
            entities = msg.entities or msg.caption_entities
            page_entries = parse_file_entries(txt, entities)
            all_entries.extend(page_entries)

            if current_msg_id in visited_pages:
                break
            visited_pages.add(current_msg_id)

            next_btn = None
            if msg.reply_markup and msg.reply_markup.inline_keyboard:
                for row in msg.reply_markup.inline_keyboard:
                    for btn in row:
                        btn_label = btn.text.strip().lower()
                        if "next" in btn_label or "▶" in btn_label or "⏩" in btn_label:
                            next_btn = btn
                            break
                    if next_btn:
                        break

            if not next_btn:
                break

            # Click Next inline button
            await msg.click(next_btn.text)
            await asyncio.sleep(2.5)

            # Re-fetch updated message
            msg = await user_client.get_messages(chat_id, current_msg_id)

        except Exception as e:
            logger.error(f"Error scanning pagination pages: {e}")
            break

    return all_entries

async def execute_task_flow(user_client, task_name, page_link, group_name, prefix, target_group, moviebot, linkbot, lgroup_target):
    if not user_client or not target_group:
        logger.info(f"Simulated flow completed for task '{task_name}' with prefix '{prefix}'")
        return

    try:
        # Step 1: Send exact task_name to target_group
        sent_msg = await user_client.send_message(target_group, task_name)
        await asyncio.sleep(3)

        response_msg = None
        async for reply in user_client.get_chat_history(target_group, limit=5):
            if reply.reply_to_message_id == sent_msg.id:
                response_msg = reply
                break
            if reply.text or reply.caption:
                response_msg = reply

        if not response_msg:
            logger.warning(f"No response received in group for task '{task_name}'")
            return

        # Detect quality buttons (e.g., "480P", "720P", "1080P")
        quality_buttons = []
        if response_msg.reply_markup and response_msg.reply_markup.inline_keyboard:
            for row in response_msg.reply_markup.inline_keyboard:
                for btn in row:
                    txt = btn.text.strip()
                    if any(q in txt.upper() for q in ["480P", "720P", "1080P", "360P", "2160P", "4K"]):
                        quality_buttons.append(btn)

        if not quality_buttons:
            quality_names = ["480P", "720P", "1080P"]
        else:
            quality_names = [b.text.strip() for b in quality_buttons]

        for qual in quality_names:
            qual_clean = qual.upper()

            # Click quality button if present
            if response_msg.reply_markup and response_msg.reply_markup.inline_keyboard:
                try:
                    await response_msg.click(qual)
                    await asyncio.sleep(3)
                except Exception as ce:
                    logger.warning(f"Could not click button {qual}: {ce}")

            # Re-fetch response message after clicking quality
            response_msg = await user_client.get_messages(target_group, response_msg.id)

            # Scan all pagination pages and aggregate entries
            all_entries = await scan_all_pages_and_get_entries(user_client, target_group, response_msg.id)

            # Select largest MB file size matching quality
            best_file = filter_highest_mb_file(all_entries, quality=qual_clean)
            if not best_file:
                logger.warning(f"No matching MB file found for quality {qual_clean}")
                continue

            # Click deep link
            deep_link = best_file.get("link")
            if deep_link:
                if "?start=" in deep_link and moviebot:
                    payload = deep_link.split("?start=")[1]
                    await user_client.send_message(moviebot, f"/start {payload}")
                elif moviebot:
                    await user_client.send_message(moviebot, f"/start {deep_link}")

            await asyncio.sleep(4)

            # Wait for incoming file from moviebot
            incoming_file_msg = None
            if moviebot:
                async for m in user_client.get_chat_history(moviebot, limit=5):
                    if m.media:
                        incoming_file_msg = m
                        break

            # Forward file to linkbot
            if incoming_file_msg and linkbot:
                await incoming_file_msg.forward(linkbot)
                await asyncio.sleep(4)

                # Extract download link from linkbot reply
                linkbot_reply = None
                async for lmsg in user_client.get_chat_history(linkbot, limit=5):
                    if lmsg.text or lmsg.caption:
                        linkbot_reply = lmsg
                        break

                if linkbot_reply:
                    dl_text = linkbot_reply.text or linkbot_reply.caption
                    entities = linkbot_reply.entities or linkbot_reply.caption_entities
                    dl_link = extract_download_link(dl_text, entities)

                    if lgroup_target and dl_link:
                        cmd_text = format_lgroup_command(prefix, dl_link, task_name, qual_clean)
                        await user_client.send_message(lgroup_target, cmd_text)

    except Exception as e:
        logger.error(f"Error during execute_task_flow for task '{task_name}': {e}")

task_queue_manager = TaskQueueManager()
