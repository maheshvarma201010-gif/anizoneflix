import asyncio
import logging
import re
import uuid
from typing import Dict, List, Optional
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from config.config import Config
from database.db import db
from utils.task_helpers import (
    normalize_font_text,
    parse_file_options,
    get_best_mb_file
)

logger = logging.getLogger("MZ_TASK_RUNNER")

class Task:
    def __init__(self, task_id: str, name: str, page_link: str, group_name: str, requested_by: int):
        self.id = task_id
        self.name = name
        self.page_link = page_link
        self.group_name = group_name
        self.requested_by = requested_by
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

    async def add_task(self, name: str, page_link: str, group_name: str, requested_by: int) -> Task:
        async with self.lock:
            task_id = str(uuid.uuid4())[:8]
            task = Task(task_id, name, page_link, group_name, requested_by)
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
    1. Send name to /SETGROUP.
    2. Monitor for result message matching '🏷 ᴛɪᴛʟᴇ : {name}'.
    3. Click second row button -> Quality menu appears.
    4. For qualities (480P, 720P, 1080P):
       - Click required quality button.
       - Scan all pages (if pagination NEXT exists).
       - Select highest MB file.
       - Click deep link.
       - Wait for incoming file from /SETMOVIEBOT.
       - Forward to /SETLINK.
       - Parse download link reply.
       - Send command to /SETLGROUP: '{command_slot} {download_link} -e -n {NAME} {QUALITY}.mkv'.
    5. Receive 3 files from /SETMOVIEBOT with '-n {NAME}'.
    6. Forward 3 files to /SETBOT.
    7. Parse /SETBOT reply and create media entry with quality buttons.
    """
    raw_group_target = await db.get_setting("setgroup")
    raw_setmoviebot = await db.get_setting("setmoviebot")
    raw_setlink = await db.get_setting("setlink")
    raw_setlgroup = await db.get_setting("setlgroup")
    raw_setbot = await db.get_setting("setbot")

    if not raw_group_target or not raw_setmoviebot or not raw_setlink or not raw_setlgroup or not raw_setbot:
        raise Exception("Required system settings (/SETGROUP, /SETMOVIEBOT, /SETLINK, /SETLGROUP, /SETBOT) are missing!")

    group_target = parse_peer_id(raw_group_target)
    setmoviebot = parse_peer_id(raw_setmoviebot)
    setlink = parse_peer_id(raw_setlink)
    setlgroup = parse_peer_id(raw_setlgroup)
    setbot = parse_peer_id(raw_setbot)

    ub = await get_userbot_client()
    if not ub:
        raise Exception("Failed to start Userbot client with configured session string.")

    try:
        # Step 1: Send name to /SETGROUP
        task.current_step = "sending_name_to_group"
        sent_msg = await ub.send_message(group_target, task.name)
        logger.info(f"Task {task.id}: Sent '{task.name}' to {group_target}")

        # Step 2: Wait for result message where 🏷 ᴛɪᴛʟᴇ matches task.name
        task.current_step = "waiting_for_result_message"
        result_msg = None

        for _ in range(60): # 60 seconds timeout
            if task.status == "cancelled":
                raise Exception("Task cancelled by admin.")

            async for msg in ub.get_chat_history(group_target, limit=10):
                if not msg.text and not msg.caption:
                    continue
                content = normalize_font_text(msg.text or msg.caption or "")
                if "TITLE :" in content or "TITLE:" in content:
                    title_match = re.search(r"TITLE\s*:\s*(.+)", content, re.IGNORECASE)
                    if title_match:
                        matched_title = title_match.group(1).strip()
                        if task.name.lower() in matched_title.lower() or matched_title.lower() in task.name.lower():
                            result_msg = msg
                            break
            if result_msg:
                break
            await asyncio.sleep(1)

        if not result_msg:
            raise Exception(f"Timeout waiting for result message for '{task.name}' in group {group_target}")

        logger.info(f"Task {task.id}: Result message received!")

        # Step 3 & 4: Process qualities (480P, 720P, 1080P)
        qualities = ["480P", "720P", "1080P"]

        for qual in qualities:
            if task.status == "cancelled":
                raise Exception("Task cancelled by admin.")

            task.current_step = f"processing_{qual}"

            # If not first quality, send name again to group as instructed
            if qual != "480P":
                sent_msg = await ub.send_message(group_target, task.name)
                result_msg = None
                for _ in range(30):
                    async for msg in ub.get_chat_history(group_target, limit=10):
                        content = normalize_font_text(msg.text or msg.caption or "")
                        if "TITLE :" in content or "TITLE:" in content:
                            title_match = re.search(r"TITLE\s*:\s*(.+)", content, re.IGNORECASE)
                            if title_match:
                                matched_title = title_match.group(1).strip()
                                if task.name.lower() in matched_title.lower() or matched_title.lower() in task.name.lower():
                                    result_msg = msg
                                    break
                    if result_msg:
                        break
                    await asyncio.sleep(1)

                if not result_msg:
                    raise Exception(f"Timeout waiting for result message for quality {qual}")

            # Click second row button to reveal quality buttons
            if result_msg.reply_markup and getattr(result_msg.reply_markup, "inline_keyboard", None):
                kb = result_msg.reply_markup.inline_keyboard
                if len(kb) >= 2 and len(kb[1]) > 0:
                    btn_to_click = kb[1][0]
                    cb_data = getattr(btn_to_click, "callback_data", None)
                    if cb_data:
                        await click_inline_button(ub, group_target, result_msg.id, cb_data)

            await asyncio.sleep(2)

            # Re-fetch result_msg to get quality buttons
            quality_msg = await ub.get_messages(group_target, result_msg.id)

            # Click specific quality button (e.g., 480P, 720P, 1080P)
            if quality_msg.reply_markup and getattr(quality_msg.reply_markup, "inline_keyboard", None):
                kb = quality_msg.reply_markup.inline_keyboard
                click_success = False
                for row in kb:
                    for b in row:
                        b_text = normalize_font_text(b.text or "").upper()
                        if qual in b_text:
                            cb_data = getattr(b, "callback_data", None)
                            if cb_data:
                                await click_inline_button(ub, group_target, quality_msg.id, cb_data)
                                click_success = True
                                break
                    if click_success:
                        break

            await asyncio.sleep(3)

            # Re-fetch message to get file listing, deep links & pagination
            all_file_options = []
            max_pages = 10
            page_count = 0

            while page_count < max_pages:
                updated_msg = await ub.get_messages(group_target, result_msg.id)
                full_text = updated_msg.text or updated_msg.caption or ""
                entities = updated_msg.entities or updated_msg.caption_entities

                page_files = parse_file_options(full_text, entities)
                all_file_options.extend(page_files)

                # Check for NEXT pagination button
                next_cb_data = None
                if updated_msg.reply_markup and getattr(updated_msg.reply_markup, "inline_keyboard", None):
                    for row in updated_msg.reply_markup.inline_keyboard:
                        for b in row:
                            b_text = normalize_font_text(b.text or "").upper()
                            if "NEXT" in b_text or "▶" in b_text or "NEXT ➔" in b_text:
                                next_cb_data = getattr(b, "callback_data", None)
                                break
                        if next_cb_data:
                            break

                if next_cb_data:
                    page_count += 1
                    await click_inline_button(ub, group_target, updated_msg.id, next_cb_data)
                    await asyncio.sleep(2)
                else:
                    break

            best_file = get_best_mb_file(all_file_options, quality_filter=qual, name_filter=task.name)
            deep_link = best_file.get("deep_link") if best_file else None

            if deep_link:
                if "start=" in deep_link or "?start=" in deep_link:
                    payload = deep_link.split("start=")[-1]
                    target_bot = deep_link.split("//t.me/")[-1].split("?")[0]
                    await ub.send_message(target_bot, f"/start {payload}")
                else:
                    await ub.send_message(setmoviebot, f"/start {qual}")
            else:
                await ub.send_message(setmoviebot, f"{task.name} {qual}")

            # Wait for file to arrive from /SETMOVIEBOT
            movie_file_msg = None
            for _ in range(60):
                async for m in ub.get_chat_history(setmoviebot, limit=5):
                    if m.media and (m.document or m.video or m.audio):
                        movie_file_msg = m
                        break
                if movie_file_msg:
                    break
                await asyncio.sleep(1)

            if not movie_file_msg:
                raise Exception(f"Timeout: Incoming file for {qual} did not arrive from {setmoviebot}")

            # Forward file to /SETLINK
            fwd_to_setlink = await ub.forward_messages(setlink, setmoviebot, movie_file_msg.id)

            # Wait for download/stream link reply from /SETLINK
            download_link = None
            for _ in range(30):
                async for m in ub.get_chat_history(setlink, limit=5):
                    content = m.text or m.caption or ""
                    if "http://" in content or "https://" in content:
                        urls = re.findall(r"https?://[^\s]+", content)
                        if urls:
                            download_link = urls[0]
                            break
                    if m.entities or m.caption_entities:
                        for ent in (m.entities or m.caption_entities or []):
                            if getattr(ent, "url", None):
                                download_link = ent.url
                                break
                    if download_link:
                        break
                if download_link:
                    break
                await asyncio.sleep(1)

            if not download_link:
                raise Exception(f"Timeout: Link response for {qual} did not arrive from {setlink}")

            # Send formatted command to /SETLGROUP
            # Format: {command_slot} {download_link} -e -n {ADMIN PROVIDED NAME} {QUALITY}.mkv
            lgroup_cmd = f"{task.command_slot} {download_link} -e -n {task.name} {qual}.mkv"
            await ub.send_message(setlgroup, lgroup_cmd)
            logger.info(f"Task {task.id}: Sent command to {setlgroup}: {lgroup_cmd}")

            await asyncio.sleep(2)

        # Step 5: Monitor incoming files with '-n {ADMIN PROVIDED NAME}'
        task.current_step = "collecting_final_files"
        monitorbots = await db.get_setting("monitorbots")
        monitor_sources = [setmoviebot]
        if monitorbots:
            if isinstance(monitorbots, list): monitor_sources.extend(monitorbots)
            elif isinstance(monitorbots, str): monitor_sources.extend([b.strip() for b in monitorbots.split(",") if b.strip()])

        matched_files = []
        for src in monitor_sources:
            try:
                async for m in ub.get_chat_history(src, limit=20):
                    if m.media and (m.document or m.video or m.audio):
                        fn = getattr(m.document or m.video or m.audio, "file_name", "") or m.caption or ""
                        if task.name.lower() in fn.lower():
                            matched_files.append((src, m.id))
            except Exception as e:
                logger.warning(f"Error checking chat history for source {src}: {e}")

        # Forward matched files to /SETBOT
        task.current_step = "forwarding_to_setbot"
        setbot_links = {}

        if matched_files:
            for src, mid in matched_files[:3]:
                await ub.forward_messages(setbot, src, mid)
                await asyncio.sleep(1)
        else:
            await ub.send_message(setbot, f"Files completed for {task.name}")

        # Wait for reply from /SETBOT with quality buttons
        for _ in range(15):
            async for m in ub.get_chat_history(setbot, limit=5):
                content = m.text or m.caption or ""
                urls = re.findall(r"https?://[^\s]+", content)
                if urls:
                    setbot_links["480P"] = urls[0]
                    if len(urls) > 1: setbot_links["720P"] = urls[1]
                    if len(urls) > 2: setbot_links["1080P"] = urls[2]
                    break
            if setbot_links:
                break
            await asyncio.sleep(1)

        if not setbot_links:
            setbot_links = {
                "480P": f"https://t.me/{setbot}?start=480p_{task.id}",
                "720P": f"https://t.me/{setbot}?start=720p_{task.id}",
                "1080P": f"https://t.me/{setbot}?start=1080p_{task.id}"
            }

        # Save media group entry with buttons
        from utils.utils import slugify
        media_slug = slugify(task.name)
        media_doc = {
            "id": f"task_{task.id}",
            "title": task.name,
            "slug": media_slug,
            "type": "movie",
            "year": "2026",
            "seasons_links": {
                task.group_name: setbot_links
            }
        }
        await db.add_media(media_doc)
        logger.info(f"Task {task.id}: Fully completed automation sequence for '{task.name}'!")

    finally:
        try:
            await ub.stop()
        except:
            pass
