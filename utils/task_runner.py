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
    normalize_font_text,
    parse_setbot_links,
    is_matching_file
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
            setbot = await db.get_setting("setbot")
            monitorbots = await db.get_setting("monitorbots") or []
            lgroup_setting = await db.get_setting("setlgroup")

            lgroup_target = None
            if isinstance(lgroup_setting, dict):
                lgroup_target = lgroup_setting.get("target")
            elif isinstance(lgroup_setting, str):
                lgroup_target = lgroup_setting

            user_client = await self.get_user_client()

            quality_links = await execute_task_flow(
                user_client=user_client,
                task_name=task_name,
                page_link=page_link,
                group_name=group_name,
                prefix=prefix,
                target_group=target_group,
                moviebot=moviebot,
                linkbot=linkbot,
                lgroup_target=lgroup_target,
                setbot=setbot,
                monitorbots=monitorbots
            )
            if task_id in self.tasks and self.tasks[task_id]["status"] == "running":
                self.tasks[task_id]["status"] = "completed"
                self.tasks[task_id]["quality_links"] = quality_links
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

async def execute_task_flow(user_client, task_name, page_link, group_name, prefix, target_group, moviebot, linkbot, lgroup_target, setbot=None, monitorbots=None):
    """
    Complete task execution flow:
    1. Userbot sends task_name to /setgroup target.
    2. Processes 3 incoming files from /setmoviebot in quality order (480p, 720p, 1080p).
    3. For each incoming file:
       a. Userbot receives incoming file from /setmoviebot.
       b. Userbot forwards file to /setlink bot.
       c. Extract download link from /setlink response.
       d. Send format: '{prefix} {download_link} -e -n {task_name} {quality}.mkv' to /setlgroup.
       e. Monitor all /monitorbots for file where filename or caption matches '{task_name} {quality}.mkv'.
       f. Userbot forwards matching file to /setbot.
       g. Receive generated link from /setbot reply and assign to quality button (480p, 720p, 1080p).
    """
    quality_results = {
        "480p": None,
        "720p": None,
        "1080p": None
    }

    if not user_client or not target_group:
        logger.info(f"Simulated flow completed for task '{task_name}' with prefix '{prefix}'")
        return quality_results

    try:
        # Step 1: Send exact task_name to target_group (/setgroup)
        sent_msg = await user_client.send_message(target_group, task_name)
        await asyncio.sleep(2)

        qualities_sequence = ["480p", "720p", "1080p"]
        seen_moviebot_msg_ids = set()
        seen_monitorbot_msg_ids = set()

        if isinstance(monitorbots, str):
            monitorbots = [b.strip() for b in re.split(r"[\s,]+", monitorbots) if b.strip()]
        elif not isinstance(monitorbots, list):
            monitorbots = []

        for qual in qualities_sequence:
            logger.info(f"Processing quality '{qual}' for task '{task_name}'")

            # Step 2: Monitor /setmoviebot for incoming file (strictly document, video, or audio; excluding photo, sticker, animation)
            incoming_file_msg = None
            if moviebot:
                for _ in range(15):
                    async for m in user_client.get_chat_history(moviebot, limit=5):
                        if (m.document or m.video or m.audio) and not (m.photo or m.sticker or m.animation) and m.id not in seen_moviebot_msg_ids:
                            incoming_file_msg = m
                            seen_moviebot_msg_ids.add(m.id)
                            break
                    if incoming_file_msg:
                        break
                    await asyncio.sleep(2)

            if not incoming_file_msg:
                logger.warning(f"No incoming file received from moviebot '{moviebot}' for quality '{qual}'")
                continue

            # Step 3: Forward incoming file to /setlink bot
            if not linkbot:
                logger.warning(f"No linkbot configured for task '{task_name}'")
                continue

            fwd_to_linkbot = await incoming_file_msg.forward(linkbot)
            await asyncio.sleep(3)

            # Step 4: Monitor /setlink bot for reply and extract download link
            dl_link = None
            linkbot_msg = None
            for _ in range(15):
                async for lmsg in user_client.get_chat_history(linkbot, limit=5):
                    if lmsg.text or lmsg.caption:
                        linkbot_msg = lmsg
                        dl_text = lmsg.text or lmsg.caption
                        entities = lmsg.entities or lmsg.caption_entities
                        dl_link = extract_download_link(dl_text, entities)
                        if dl_link and ("http://" in dl_link or "https://" in dl_link):
                            break
                if dl_link and ("http://" in dl_link or "https://" in dl_link):
                    break
                await asyncio.sleep(2)

            if not dl_link:
                logger.warning(f"Failed to extract download link from linkbot reply for quality '{qual}'")
                continue

            # Step 5: Send command format to /setlgroup target
            # Format: {prefix} {download_link} -e -n {task_name} {quality}.mkv
            if lgroup_target:
                cmd_text = format_lgroup_command(prefix, dl_link, task_name, qual)
                await user_client.send_message(lgroup_target, cmd_text)
                await asyncio.sleep(3)

            # Step 6: Monitor all configured /monitorbots for matching file
            # Filename or caption matches '{task_name} {quality}.mkv'
            matching_file_msg = None
            active_monitor_targets = list(monitorbots)
            if lgroup_target and lgroup_target not in active_monitor_targets:
                active_monitor_targets.append(lgroup_target)

            for _ in range(30): # Loop checking configured monitor bots
                for bot_target in active_monitor_targets:
                    try:
                        async for m in user_client.get_chat_history(bot_target, limit=10):
                            if (m.document or m.video or m.audio) and not (m.photo or m.sticker or m.animation) and m.id not in seen_monitorbot_msg_ids:
                                fname = getattr(m.document or m.video or m.audio, "file_name", "") or ""
                                cap = m.caption or m.text or ""
                                if is_matching_file(fname, cap, task_name, qual):
                                    matching_file_msg = m
                                    seen_monitorbot_msg_ids.add(m.id)
                                    break
                        if matching_file_msg:
                            break
                    except Exception as me:
                        logger.error(f"Error checking monitorbot '{bot_target}': {me}")

                if matching_file_msg:
                    break
                await asyncio.sleep(2)

            if not matching_file_msg:
                logger.warning(f"No matching file found on monitorbots for '{task_name} {qual}.mkv'")
                continue

            # Step 7: Forward matching file to /setbot
            if not setbot:
                logger.warning("No /setbot configured")
                continue

            await matching_file_msg.forward(setbot)
            await asyncio.sleep(3)

            # Step 8: Monitor /setbot reply and extract generated link for quality
            generated_link = None
            for _ in range(15):
                async for sb_msg in user_client.get_chat_history(setbot, limit=5):
                    if sb_msg.text or sb_msg.caption:
                        sb_text = sb_msg.text or sb_msg.caption
                        sb_entities = sb_msg.entities or sb_msg.caption_entities
                        parsed = parse_setbot_links(sb_text, sb_entities)

                        # Match quality key
                        norm_qual_key = qual.upper()
                        if norm_qual_key in parsed:
                            generated_link = parsed[norm_qual_key]
                            break

                        # Direct URL fallback in setbot reply
                        urls = re.findall(r"https?://[^\s<>\"]+", sb_text)
                        if urls:
                            generated_link = urls[0]
                            break
                if generated_link:
                    break
                await asyncio.sleep(2)

            if generated_link:
                quality_results[qual] = generated_link
                logger.info(f"Assigned link for '{qual}' button: {generated_link}")
            else:
                logger.warning(f"No generated link received from setbot for quality '{qual}'")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error during execute_task_flow for task '{task_name}': {e}")

    return quality_results

task_queue_manager = TaskQueueManager()
