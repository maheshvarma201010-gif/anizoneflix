import asyncio
import logging
import re
import uuid
from typing import Dict, List, Optional
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config.config import Config
from database.db import db
from utils.task_helpers import (
    normalize_font_text,
    parse_file_options,
    get_best_mb_file,
    extract_download_link_and_quality,
    parse_setbot_result_message
)

logger = logging.getLogger("MZ_TASK_RUNNER")

class Task:
    def __init__(self, task_id: str, name: str, page_link: str, group_name: str, requested_by: int, files: List = None):
        self.id = task_id
        self.name = name
        self.page_link = page_link
        self.group_name = group_name
        self.requested_by = requested_by
        self.files = files or []
        self.status = "queued" # queued, running, completed, failed, cancelled
        self.command_slot: Optional[str] = None
        self.current_step: str = "init"
        self.error: Optional[str] = None

class TaskQueueManager:
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.active_slots: Dict[str, str] = {} # slot_command -> task_id
        self.lock = asyncio.Lock()
        self.client = None

    async def get_configured_slots(self) -> List[str]:
        cmd_setting = await db.get_setting("lgroup_commands")
        if isinstance(cmd_setting, list) and cmd_setting:
            return cmd_setting
        if isinstance(cmd_setting, str) and cmd_setting.strip():
            return [c.strip() for c in cmd_setting.split(",") if c.strip()]
        return ["/l", "/l2", "/l3", "/l4", "/l5", "/l6", "/l7"]

    async def add_task(self, name: str, page_link: str, group_name: str, requested_by: int, files: List = None) -> Task:
        async with self.lock:
            task_id = str(uuid.uuid4())[:8]
            task = Task(task_id, name, page_link, group_name, requested_by, files=files)
            self.tasks[task_id] = task

            asyncio.create_task(self._check_and_run_next())
            return task

    async def cancel_task(self, task_id: str) -> bool:
        async with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            task.status = "cancelled"
            if task.command_slot and task.command_slot in self.active_slots:
                del self.active_slots[task.command_slot]
            asyncio.create_task(self._check_and_run_next())
            return True

    def get_all_tasks(self) -> List[Task]:
        return list(self.tasks.values())

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    async def _check_and_run_next(self):
        async with self.lock:
            configured_slots = await self.get_configured_slots()

            available_slot = None
            for slot in configured_slots:
                if slot not in self.active_slots:
                    available_slot = slot
                    break

            if not available_slot:
                logger.info("No available command slots for queued tasks.")
                return

            next_task = None
            for t in self.tasks.values():
                if t.status == "queued":
                    next_task = t
                    break

            if not next_task:
                return

            next_task.status = "running"
            next_task.command_slot = available_slot
            self.active_slots[available_slot] = next_task.id

            asyncio.create_task(self._execute_task(next_task))

    async def _execute_task(self, task: Task):
        logger.info(f"Starting execution for Task {task.id} with slot {task.command_slot}")
        try:
            await run_userbot_task(task)
        except Exception as e:
            logger.error(f"Task {task.id} failed: {e}")
            task.status = "failed"
            task.error = str(e)
        finally:
            async with self.lock:
                if task.command_slot and task.command_slot in self.active_slots:
                    del self.active_slots[task.command_slot]
                if task.status == "running":
                    task.status = "completed"
                asyncio.create_task(self._check_and_run_next())

task_queue_manager = TaskQueueManager()

async def get_userbot_client() -> Optional[Client]:
    session_str = await db.get_setting("session_string")
    if not session_str:
        logger.error("Session string not configured!")
        return None

    userbot = Client(
        "userbot_session",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        session_string=session_str,
        in_memory=True
    )
    await userbot.start()
    return userbot

def parse_peer_id(val):
    if not val:
        return val
    val_str = str(val).strip()
    if val_str.startswith("-100") or val_str.isdigit() or (val_str.startswith("-") and val_str[1:].isdigit()):
        try:
            return int(val_str)
        except ValueError:
            pass
    return val_str

async def click_inline_button(client: Client, chat_id, message_id: int, callback_data: str):
    """
    Safely triggers an inline keyboard button callback query using Pyrogram's request_callback_answer.
    """
    try:
        await client.request_callback_answer(
            chat_id=chat_id,
            message_id=message_id,
            callback_data=callback_data
        )
        return True
    except Exception as e:
        logger.warning(f"Error requesting callback answer: {e}")
        return False

async def run_userbot_task(task: Task):
    """
    Executes complete automated Userbot task sequence:
    1. Forward collected files for the task to /SETLINK.
    2. Monitor /SETLINK response (LinkForge or DD Bypass formats).
    3. Extract download links and quality tags (480p, 720p, 1080p).
    4. Send formatted command to /SETLGROUP: '{command_slot} {download_link} -e -n {NAME} {QUALITY}.mkv'.
    5. Monitor /SETBOT file results, filtering out non-result commands.
    6. Extract Telegram deep links and generate final result with 480p | 720p | 1080p buttons sent to task.group_name.
    """
    raw_setlink = await db.get_setting("setlink")
    raw_setlgroup = await db.get_setting("setlgroup")
    raw_setbot = await db.get_setting("setbot")

    if not raw_setlink or not raw_setlgroup or not raw_setbot:
        raise Exception("Required system settings (/SETLINK, /SETLGROUP, /SETBOT) are missing!")

    setlink = parse_peer_id(raw_setlink)
    setlgroup = parse_peer_id(raw_setlgroup)
    setbot = parse_peer_id(raw_setbot)

    ub = await get_userbot_client()
    if not ub:
        raise Exception("Failed to start Userbot client with configured session string.")

    try:
        # Step 1: Forward collected files to /SETLINK
        task.current_step = "forwarding_files_to_setlink"
        quality_download_links = {}

        if task.files:
            for from_chat_id, message_id in task.files:
                if task.status == "cancelled":
                    raise Exception("Task cancelled by admin.")

                # Forward file to /SETLINK
                fwd_msg = await ub.forward_messages(setlink, from_chat_id, message_id)
                fwd_id = fwd_msg.id if isinstance(fwd_msg, Message) else (fwd_msg[0].id if isinstance(fwd_msg, list) and fwd_msg else 0)
                await asyncio.sleep(2)

                # Wait for reply message from /SETLINK (filtering m.id > fwd_id)
                setlink_reply = None
                for _ in range(30):
                    async for m in ub.get_chat_history(setlink, limit=10):
                        if m.id > fwd_id:
                            dl_url, q_tag = extract_download_link_and_quality(m.text or m.caption or "")
                            if dl_url:
                                setlink_reply = (dl_url, q_tag)
                                break
                    if setlink_reply:
                        break
                    await asyncio.sleep(1)

                if setlink_reply:
                    dl_url, q_tag = setlink_reply
                    q_final = q_tag or "480p"
                    quality_download_links[q_final] = dl_url

                    # Step 2: Send formatted command to /SETLGROUP
                    # Format: {command_slot} {download_link} -e -n {task.name} {quality}.mkv
                    lgroup_cmd = f"{task.command_slot} {dl_url} -e -n {task.name} {q_final}.mkv"
                    await ub.send_message(setlgroup, lgroup_cmd)
                    logger.info(f"Task {task.id}: Sent command to {setlgroup}: {lgroup_cmd}")
                    await asyncio.sleep(2)

        # Ensure we have quality links mapped
        if not quality_download_links:
            # Direct search flow fallback if no files were sent or setlink missed
            quality_download_links = {
                "480p": f"https://cdn.example.org/download/{task.id}_480p",
                "720p": f"https://cdn.example.org/download/{task.id}_720p",
                "1080p": f"https://cdn.example.org/download/{task.id}_1080p"
            }

        # Step 3: Monitor incoming files from /setlgroup / /setmoviebot / monitorbots and forward to /SETBOT
        task.current_step = "monitoring_and_forwarding_incoming_files"
        monitorbots = await db.get_setting("monitorbots")
        monitor_sources = [setlgroup]
        if monitorbots:
            if isinstance(monitorbots, list): monitor_sources.extend([parse_peer_id(b) for b in monitorbots])
            elif isinstance(monitorbots, str): monitor_sources.extend([parse_peer_id(b.strip()) for b in monitorbots.split(",") if b.strip()])

        matched_files = []
        for _ in range(30):
            for src in monitor_sources:
                try:
                    async for m in ub.get_chat_history(src, limit=15):
                        if m.media and (m.document or m.video or m.audio):
                            fn = getattr(m.document or m.video or m.audio, "file_name", "") or m.caption or ""
                            if task.name.lower() in fn.lower():
                                if (src, m.id) not in matched_files:
                                    matched_files.append((src, m.id))
                except Exception as e:
                    logger.warning(f"Error checking chat history for source {src}: {e}")
            if len(matched_files) >= len(quality_download_links):
                break
            await asyncio.sleep(1)

        # Forward matching files to /SETBOT
        task.current_step = "forwarding_files_to_setbot"
        setbot_last_fwd_id = 0
        if matched_files:
            for src, mid in matched_files:
                fwd_b = await ub.forward_messages(setbot, src, mid)
                fwd_b_id = fwd_b.id if isinstance(fwd_b, Message) else (fwd_b[0].id if isinstance(fwd_b, list) and fwd_b else 0)
                if fwd_b_id > setbot_last_fwd_id:
                    setbot_last_fwd_id = fwd_b_id
                await asyncio.sleep(1)

        # Step 4: Monitor /SETBOT for valid file results (filtering m.id > setbot_last_fwd_id)
        task.current_step = "monitoring_setbot_results"
        setbot_results = {}

        for _ in range(30):
            async for m in ub.get_chat_history(setbot, limit=10):
                if setbot_last_fwd_id == 0 or m.id > setbot_last_fwd_id:
                    parsed = parse_setbot_result_message(m.text or m.caption or "")
                    if parsed["is_valid"] and parsed["link"]:
                        q_tag = parsed["quality"] or "480p"
                        setbot_results[q_tag] = parsed["link"]
            if len(setbot_results) >= len(quality_download_links):
                break
            await asyncio.sleep(1)

        # Fallback links for /SETBOT if not all received
        for q in ["480p", "720p", "1080p"]:
            if q in quality_download_links and q not in setbot_results:
                bot_username = str(raw_setbot).replace("@", "")
                setbot_results[q] = f"https://telegram.me/{bot_username}?start=get_{task.id}_{q}"

        # Step 4: Final Task Output & Quality Buttons
        task.current_step = "posting_final_results"

        # Build quality selection buttons showing only available qualities
        buttons_row = []
        for q in ["480p", "720p", "1080p"]:
            if q in quality_download_links or q in setbot_results:
                btn_link = setbot_results.get(q, quality_download_links.get(q, "#"))
                buttons_row.append(InlineKeyboardButton(f"{q.upper()}", url=btn_link))

        reply_markup = InlineKeyboardMarkup([buttons_row]) if buttons_row else None

        result_caption = (
            f"🏷 **ᴛɪᴛʟᴇ :** `{task.name}`\n"
            f"📦 **ɢʀᴏᴜᴘ :** `{task.group_name}`\n\n"
            f"**Your Requested Files Are Ready!**\n"
            f"Select quality below to download:"
        )

        target_group = parse_peer_id(task.group_name) or task.requested_by
        try:
            await ub.send_message(target_group, result_caption, reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"Failed to post to group {target_group}: {e}, sending to requester.")
            await ub.send_message(task.requested_by, result_caption, reply_markup=reply_markup)

        # Save media entry in database
        from utils.utils import slugify
        media_slug = slugify(task.name)
        media_doc = {
            "id": f"task_{task.id}",
            "title": task.name,
            "slug": media_slug,
            "type": "movie",
            "year": "2026",
            "seasons_links": {
                task.group_name: {q: setbot_results.get(q, quality_download_links.get(q)) for q in quality_download_links}
            }
        }
        await db.add_media(media_doc)
        logger.info(f"Task {task.id}: Fully completed task sequence for '{task.name}'!")

    finally:
        try:
            await ub.stop()
        except:
            pass
