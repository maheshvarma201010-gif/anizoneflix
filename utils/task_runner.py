import asyncio
import logging
import re
import uuid
from pyrogram import Client, filters
from database.db import db
from utils.task_helpers import (
    parse_file_entries,
    filter_highest_mb_file,
    extract_download_link,
    format_lgroup_command,
    normalize_font_text
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
        self.tasks = {}  # task_id -> task dict

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
        task_id = task_data.get("id") or f"task_{str(uuid.uuid4())[:8]}"
        task_data["id"] = task_id
        task_entry = {
            "id": task_id,
            "name": task_data.get("name", "Unnamed Task"),
            "status": "queued",
            "prefix": None,
            "handle": None,
            "data": task_data
        }
        self.tasks[task_id] = task_entry
        await self.queue.put(task_id)
        self.start()
        return task_id

    def get_all_tasks(self):
        """
        Returns list of active/running or queued tasks.
        """
        return [
            {
                "id": t_id,
                "name": t_info["name"],
                "status": t_info["status"],
                "prefix": t_info["prefix"]
            }
            for t_id, t_info in list(self.tasks.items())
            if t_info["status"] in ["queued", "running"]
        ]

    def cancel_task(self, task_id):
        """
        Cancels a running or queued task by ID.
        """
        if task_id not in self.tasks:
            return False

        task_entry = self.tasks[task_id]
        status = task_entry.get("status")

        if status == "running":
            handle = task_entry.get("handle")
            prefix = task_entry.get("prefix")
            if handle and not handle.done():
                handle.cancel()
            if prefix:
                self.release_prefix(prefix)
            task_entry["status"] = "cancelled"
            logger.info(f"Cancelled running task '{task_id}'")
            return True
        elif status == "queued":
            task_entry["status"] = "cancelled"
            logger.info(f"Cancelled queued task '{task_id}'")
            return True

        return False

    async def _process_queue(self):
        while self.is_running:
            try:
                task_id = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if task_id not in self.tasks or self.tasks[task_id]["status"] == "cancelled":
                self.queue.task_done()
                continue

            task_entry = self.tasks[task_id]
            task_data = task_entry["data"]

            try:
                prefix = await self._acquire_prefix()
                if task_entry["status"] == "cancelled":
                    self.release_prefix(prefix)
                    self.queue.task_done()
                    continue

                task_entry["status"] = "running"
                task_entry["prefix"] = prefix
                logger.info(f"Acquired prefix '{prefix}' for task '{task_entry['name']}' ({task_id})")

                async_task = asyncio.create_task(self._run_single_task(task_id, task_data, prefix))
                task_entry["handle"] = async_task

            except Exception as e:
                logger.error(f"Error starting queued task '{task_id}': {e}")
                task_entry["status"] = "failed"
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
        if prefix:
            self.active_prefixes.discard(prefix)

    async def _run_single_task(self, task_id, task_data, prefix):
        task_name = task_data["name"]
        page_link = task_data.get("page_link")
        group_name = task_data.get("group_name")

        logger.info(f"Starting Task: name='{task_name}', prefix='{prefix}', id='{task_id}'")

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
            if task_id in self.tasks and self.tasks[task_id]["status"] == "running":
                self.tasks[task_id]["status"] = "completed"
        except asyncio.CancelledError:
            logger.info(f"Task '{task_name}' ({task_id}) was cancelled mid-execution.")
            if task_id in self.tasks:
                self.tasks[task_id]["status"] = "cancelled"
            raise
        except Exception as err:
            logger.error(f"Task '{task_name}' execution error: {err}")
            if task_id in self.tasks:
                self.tasks[task_id]["status"] = "failed"
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
                        btn_label = normalize_font_text(btn.text or "").strip().lower()
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
        await asyncio.sleep(2)

        # Step 2: Monitor target_group for result message matching title (up to 30 seconds)
        response_msg = None
        for _ in range(15):
            async for reply in user_client.get_chat_history(target_group, limit=10):
                txt = (reply.text or reply.caption or "")
                norm_txt = normalize_font_text(txt).lower()
                norm_name = normalize_font_text(task_name).lower()

                if reply.reply_to_message_id == sent_msg.id or norm_name in norm_txt or "requested files" in norm_txt or "ᴛɪᴛʟᴇ" in txt:
                    response_msg = reply
                    break
            if response_msg:
                break
            await asyncio.sleep(2)

        if not response_msg:
            logger.warning(f"No result message received in group for task '{task_name}'")
            return

        # Step 3: Click inline button in second row if available (e.g., category or file list button)
        if response_msg.reply_markup and response_msg.reply_markup.inline_keyboard:
            keyboard = response_msg.reply_markup.inline_keyboard
            if len(keyboard) >= 2 and len(keyboard[1]) >= 1:
                try:
                    await response_msg.click(i=1, j=0)
                    await asyncio.sleep(2.5)
                    response_msg = await user_client.get_messages(target_group, response_msg.id)
                except Exception as ce:
                    logger.warning(f"Click on row 2 button failed: {ce}")

        # Step 4: Detect quality selection buttons (e.g., "1080P", "720P", "480P")
        quality_buttons = []
        if response_msg.reply_markup and response_msg.reply_markup.inline_keyboard:
            for row_idx, row in enumerate(response_msg.reply_markup.inline_keyboard):
                for col_idx, btn in enumerate(row):
                    raw_txt = btn.text or ""
                    norm_txt = normalize_font_text(raw_txt).upper()
                    if any(q in norm_txt for q in ["1080P", "720P", "480P", "360P", "1440P", "2160P", "4K"]):
                        quality_buttons.append((row_idx, col_idx, btn, norm_txt, raw_txt))

        if not quality_buttons:
            qualities_to_process = [("1080P", "1080P", None, None, None)]
        else:
            qualities_to_process = [(norm, norm, raw, r_idx, c_idx) for r_idx, c_idx, btn, norm, raw in quality_buttons]

        for qual_norm, qual_display, raw_btn_text, r_idx, c_idx in qualities_to_process:
            # Click quality button (preferring 1080P if available or row 2 col 2)
            if response_msg.reply_markup and response_msg.reply_markup.inline_keyboard and raw_btn_text:
                try:
                    if r_idx is not None and c_idx is not None:
                        await response_msg.click(i=r_idx, j=c_idx)
                    else:
                        await response_msg.click(raw_btn_text)
                    await asyncio.sleep(3)
                except Exception as ce:
                    logger.warning(f"Could not click quality button by text '{raw_btn_text}': {ce}")

            # Re-fetch response message after clicking quality
            response_msg = await user_client.get_messages(target_group, response_msg.id)

            # Scan all pagination pages and aggregate entries
            all_entries = await scan_all_pages_and_get_entries(user_client, target_group, response_msg.id)

            # Select largest MB file size matching quality
            best_file = filter_highest_mb_file(all_entries, quality=qual_norm)
            if not best_file:
                logger.warning(f"No matching MB file found for quality {qual_norm}")
                continue

            # Step 5: Click deep link / send payload to moviebot
            deep_link = best_file.get("link")
            if deep_link:
                if "?start=" in deep_link and moviebot:
                    payload = deep_link.split("?start=")[1]
                    await user_client.send_message(moviebot, f"/start {payload}")
                elif moviebot:
                    await user_client.send_message(moviebot, f"/start {deep_link}")

            await asyncio.sleep(4)

            # Step 6: Monitor incoming file from moviebot (up to 30s)
            incoming_file_msg = None
            if moviebot:
                for _ in range(10):
                    async for m in user_client.get_chat_history(moviebot, limit=5):
                        if m.media or m.document or m.video or m.audio:
                            incoming_file_msg = m
                            break
                    if incoming_file_msg:
                        break
                    await asyncio.sleep(2)

            # Step 7: Forward file to linkbot & send formatted command to lgroup_target
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
                        cmd_text = format_lgroup_command(prefix, dl_link, task_name, qual_norm)
                        await user_client.send_message(lgroup_target, cmd_text)

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error during execute_task_flow for task '{task_name}': {e}")

task_queue_manager = TaskQueueManager()
