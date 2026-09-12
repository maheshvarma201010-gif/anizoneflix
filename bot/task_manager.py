import asyncio
import logging
import re
from urllib.parse import urlparse
from database.db import db
from config.config import Config

logger = logging.getLogger("MZ_TASK_MANAGER")
logger.setLevel(logging.INFO)

def utf16_len(s):
    return len(s.encode('utf-16-le')) // 2

def parse_file_options(text, entities=None, reply_markup=None):
    """
    Parses file option list from message text/caption and entities/reply_markup.
    Returns list of dicts:
    [
      {
        "index": 1,
        "size_num": 1.78,
        "unit": "GB",
        "size_mb": 1822.72,
        "filename": "Vishwanath and Sons 2026...",
        "deep_link": "https://..." or button entity
      }
    ]
    """
    if not text:
        return []

    lines = text.split("\n")
    results = []

    pattern = re.compile(r"^\s*(\d+)\.\s*\[([\d\.]+)\s*(MB|GB)\]\s*(.+)$", re.IGNORECASE)

    cumulative_utf16_offset = 0

    for line in lines:
        line_utf16_len = utf16_len(line + "\n")
        line_clean = line.strip()
        match = pattern.match(line_clean)
        if match:
            idx = int(match.group(1))
            size_num = float(match.group(2))
            unit = match.group(3).upper()
            filename = match.group(4).strip()

            size_mb = size_num * 1024.0 if unit == "GB" else size_num

            # Extract deep link if embedded in text entity for this specific line
            deep_link = None

            if entities:
                for entity in entities:
                    etype = str(getattr(entity, "type", ""))
                    e_offset = getattr(entity, "offset", -1)
                    if "text_link" in etype.lower() or "url" in etype.lower():
                        if cumulative_utf16_offset <= e_offset <= cumulative_utf16_offset + line_utf16_len:
                            url = getattr(entity, "url", None)
                            if url:
                                deep_link = url
                                break

            # If no entity link found, check reply_markup for matching button
            if not deep_link and reply_markup and hasattr(reply_markup, "inline_keyboard"):
                for row in reply_markup.inline_keyboard:
                    for btn in row:
                        btn_text = btn.text.strip()
                        if str(idx) in btn_text or btn_text == str(idx):
                            deep_link = getattr(btn, "url", None) or getattr(btn, "callback_data", None)
                            break

            if not deep_link:
                deep_link = f"deep_link_idx_{idx}"

            results.append({
                "index": idx,
                "size_num": size_num,
                "unit": unit,
                "size_mb": size_mb,
                "filename": filename,
                "deep_link": deep_link
            })

        cumulative_utf16_offset += line_utf16_len

    return results


def select_best_file_for_quality(files, quality_label):
    """
    Selects the best matching file for a given quality label (480P, 720P, 1080P).
    Rules:
    - 480P: MB only. Select largest MB file.
    - 720P: Allow MB and GB. Select largest file size.
    - 1080P: Allow MB and GB under 4GB (size_mb < 4096). Select largest file size under 4GB.
    - Quality matching: match quality label in filename if multiple qualities exist.
    """
    if not files:
        return None

    norm_quality = quality_label.upper().replace("P", "")  # e.g., "480", "720", "1080"

    # 1. First filter by quality string matching in filename if present
    quality_matching = []
    for f in files:
        fname = f["filename"].upper()
        # Check if requested quality matches filename or no explicit quality mentioned
        if norm_quality in fname or quality_label.upper() in fname:
            quality_matching.append(f)

    candidates = quality_matching if quality_matching else list(files)

    # 2. Filter by quality specific size rules
    q_upper = quality_label.upper()
    valid_candidates = []

    for f in candidates:
        if "480" in q_upper:
            # 480P: MB only
            if f["unit"] == "MB":
                valid_candidates.append(f)
        elif "1080" in q_upper:
            # 1080P: under 4GB (4096 MB)
            if f["size_mb"] < 4096.0:
                valid_candidates.append(f)
        elif "720" in q_upper:
            # 720P: MB and GB allowed
            valid_candidates.append(f)
        else:
            valid_candidates.append(f)

    if not valid_candidates:
        # Fallback to candidates if size constraints produced no matches
        valid_candidates = candidates if candidates else list(files)

    # Select candidate with largest size in MB
    return max(valid_candidates, key=lambda x: x["size_mb"])


def extract_download_link(text_or_caption):
    """
    Extracts the download link from message text/caption or return first http/https URL.
    """
    if not text_or_caption:
        return ""
    urls = re.findall(r"https?://[^\s><\"\']+", text_or_caption)
    if urls:
        return urls[0]
    return text_or_caption.strip()


def detect_quality_buttons(reply_markup, text=""):
    """
    Detects available quality options (e.g. 480P, 720P, 1080P) from message reply markup or text.
    """
    qualities = []
    seen = set()

    if reply_markup and hasattr(reply_markup, "inline_keyboard"):
        for row in reply_markup.inline_keyboard:
            for btn in row:
                btn_text = btn.text.upper()
                match = re.search(r"\b(480P|720P|1080P|2160P|4K|360P)\b", btn_text)
                if match:
                    q = match.group(1)
                    if q not in seen:
                        seen.add(q)
                        qualities.append({"label": q, "button": btn})

    if not qualities:
        matches = re.findall(r"\b(480P|720P|1080P|2160P|4K|360P)\b", text.upper())
        for q in matches:
            if q not in seen:
                seen.add(q)
                qualities.append({"label": q, "button": None})

    if not qualities:
        qualities = [{"label": "480P", "button": None}, {"label": "720P", "button": None}, {"label": "1080P", "button": None}]

    return qualities


def resolve_chat_target(target):
    """
    Converts string numeric IDs like "-100123456" or "123456" to integer if possible.
    """
    if not target:
        return "me"
    if isinstance(target, str):
        target_clean = target.strip()
        if re.match(r"^-?\d+$", target_clean):
            return int(target_clean)
        return target_clean
    return target


class TaskManager:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.used_prefixes = set()
        self.prefix_available_event = asyncio.Event()
        self.prefix_available_event.set()
        self.worker_task = None
        self.active_tasks_count = 0

    async def add_task(self, task_name: str, page_link: str, group_name: str):
        task_data = {
            "task_name": task_name,
            "page_link": page_link,
            "group_name": group_name
        }
        await self.queue.put(task_data)
        logger.info(f"Enqueued task: '{task_name}' (Queue size: {self.queue.qsize()})")

        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self._worker_loop())

        return {"position": self.queue.qsize(), "task": task_data}

    async def _worker_loop(self):
        logger.info("Task Manager worker loop started.")
        while True:
            try:
                task_data = await self.queue.get()

                # Get configured prefixes from setlgroup setting
                lgroup_setting = await db.get_setting("setlgroup")
                configured_prefixes = []
                if isinstance(lgroup_setting, dict):
                    configured_prefixes = lgroup_setting.get("commands", [])
                elif isinstance(lgroup_setting, list):
                    configured_prefixes = lgroup_setting

                if not configured_prefixes:
                    configured_prefixes = ["/l", "/l2", "/l3", "/l4", "/l5", "/l6", "/l7"]

                # Wait for an available prefix
                assigned_prefix = None
                while True:
                    for pref in configured_prefixes:
                        if pref not in self.used_prefixes:
                            assigned_prefix = pref
                            break
                    if assigned_prefix:
                        break
                    # All prefixes are busy, wait until one is freed
                    self.prefix_available_event.clear()
                    logger.info("All task prefixes busy. Waiting for a prefix to become free...")
                    await self.prefix_available_event.wait()

                # Mark prefix as used
                self.used_prefixes.add(assigned_prefix)
                self.active_tasks_count += 1

                logger.info(f"Starting task '{task_data['task_name']}' with prefix '{assigned_prefix}'")
                asyncio.create_task(self._run_task_wrapper(task_data, assigned_prefix))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in task worker loop: {e}")
                await asyncio.sleep(1)

    async def _run_task_wrapper(self, task_data: dict, prefix: str):
        try:
            await self.execute_task(task_data, prefix)
        except Exception as e:
            logger.error(f"Task '{task_data['task_name']}' failed with error: {e}")
        finally:
            self.used_prefixes.discard(prefix)
            self.active_tasks_count -= 1
            self.prefix_available_event.set()
            self.queue.task_done()
            logger.info(f"Task '{task_data['task_name']}' finished. Prefix '{prefix}' is now free.")

    async def execute_task(self, task_data: dict, prefix: str):
        task_name = task_data["task_name"]
        setgroup_val = await db.get_setting("setgroup")
        setbot_val = await db.get_setting("setbot")
        setmoviebot_val = await db.get_setting("setmoviebot")
        setlink_val = await db.get_setting("setlink")
        setlgroup_val = await db.get_setting("setlgroup")
        ss_val = await db.get_setting("ss")

        logger.info(f"Executing task '{task_name}' with prefix '{prefix}'.")

        if not ss_val:
            logger.warning("Session string (/SS) not set. Running simulated task flow.")
            await asyncio.sleep(0.5)
            return

        from pyrogram import Client
        userbot = Client(
            "task_userbot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            session_string=ss_val,
            in_memory=True
        )

        try:
            await userbot.start()

            # Target group destination
            target_group = resolve_chat_target(setgroup_val)

            # Step 1: Send exact task_name text to /SETGROUP
            sent_msg = await userbot.send_message(target_group, task_name)
            logger.info(f"Sent task name '{task_name}' to group {target_group}")

            await asyncio.sleep(2)

            # Retrieve recent messages to detect quality buttons & response
            history = []
            async for m in userbot.get_chat_history(target_group, limit=5):
                history.append(m)

            response_msg = history[0] if history else sent_msg
            qualities = detect_quality_buttons(response_msg.reply_markup, response_msg.text or response_msg.caption or "")

            lgroup_raw = setlgroup_val.get("target") if isinstance(setlgroup_val, dict) else setlgroup_val
            lgroup_target = resolve_chat_target(lgroup_raw)

            for q_info in qualities:
                quality_label = q_info["label"]

                # Click quality button if present
                if q_info["button"] and hasattr(q_info["button"], "callback_data"):
                    try:
                        await userbot.request_callback_answer(
                            chat_id=response_msg.chat.id,
                            message_id=response_msg.id,
                            callback_data=q_info["button"].callback_data
                        )
                    except Exception as ce:
                        logger.error(f"Callback answer error: {ce}")

                await asyncio.sleep(2)

                # Pagination & file search across pages
                all_matching_files = []
                page_count = 0
                max_pages = 10

                while page_count < max_pages:
                    page_count += 1
                    curr_msg = None
                    async for m in userbot.get_chat_history(target_group, limit=3):
                        curr_msg = m
                        break

                    if not curr_msg:
                        break

                    files = parse_file_options(
                        curr_msg.text or curr_msg.caption or "",
                        entities=curr_msg.entities or curr_msg.caption_entities,
                        reply_markup=curr_msg.reply_markup
                    )
                    all_matching_files.extend(files)

                    next_btn = None
                    if curr_msg.reply_markup and hasattr(curr_msg.reply_markup, "inline_keyboard"):
                        for row in curr_msg.reply_markup.inline_keyboard:
                            for btn in row:
                                if "NEXT" in btn.text.upper() or "▶" in btn.text:
                                    next_btn = btn
                                    break

                    if next_btn and hasattr(next_btn, "callback_data"):
                        try:
                            await userbot.request_callback_answer(
                                chat_id=curr_msg.chat.id,
                                message_id=curr_msg.id,
                                callback_data=next_btn.callback_data
                            )
                            await asyncio.sleep(1.5)
                        except Exception:
                            break
                    else:
                        break

                if not all_matching_files:
                    logger.warning(f"No matching files found for quality {quality_label}")
                    continue

                # Filter and pick best file for quality
                selected_file = select_best_file_for_quality(all_matching_files, quality_label)
                if not selected_file:
                    continue

                logger.info(f"Selected file for {quality_label}: {selected_file['filename']} ({selected_file['size_num']} {selected_file['unit']})")

                # Click deep link
                deep_link = selected_file["deep_link"]
                if isinstance(deep_link, str) and (deep_link.startswith("http://") or deep_link.startswith("https://") or deep_link.startswith("t.me/")):
                    # Deep link URL (e.g., https://t.me/bot?start=...)
                    match = re.search(r"t\.me/([^/?]+)(?:\?start=(.+))?", deep_link)
                    if match:
                        bot_username = match.group(1)
                        start_param = match.group(2)
                        if start_param:
                            await userbot.send_message(bot_username, f"/start {start_param}")
                        else:
                            await userbot.send_message(bot_username, "/start")
                elif isinstance(deep_link, str) and not deep_link.startswith("deep_link_"):
                    try:
                        await userbot.request_callback_answer(
                            chat_id=target_group,
                            message_id=curr_msg.id if curr_msg else response_msg.id,
                            callback_data=deep_link
                        )
                    except Exception as e:
                        logger.error(f"Deep link callback error: {e}")

                # Wait for incoming file from /SETMOVIEBOT
                moviebot_target = resolve_chat_target(setmoviebot_val)
                await asyncio.sleep(3)

                incoming_file_msg = None
                async for m in userbot.get_chat_history(moviebot_target, limit=5):
                    if m.media or m.document or m.video:
                        incoming_file_msg = m
                        break

                if incoming_file_msg:
                    # Forward file to /SETLINK bot
                    linkbot_target = resolve_chat_target(setlink_val)
                    fwd_msg = await incoming_file_msg.forward(linkbot_target)

                    await asyncio.sleep(2)

                    # Get response from /SETLINK bot
                    link_resp_msg = None
                    async for m in userbot.get_chat_history(linkbot_target, limit=3):
                        link_resp_msg = m
                        break

                    download_link = extract_download_link(link_resp_msg.text or link_resp_msg.caption if link_resp_msg else "")
                else:
                    download_link = f"https://example.com/download/{quality_label}"

                # Send formatted command to /SETLGROUP
                if lgroup_target:
                    cmd_text = f"{prefix} {download_link} -e -n {task_name} {quality_label}.mkv"
                    await userbot.send_message(lgroup_target, cmd_text)
                    logger.info(f"Sent to LGroup ({lgroup_target}): {cmd_text}")

        except Exception as ex:
            logger.error(f"Userbot execution error for task '{task_name}': {ex}")
        finally:
            try:
                await userbot.stop()
            except Exception:
                pass


task_manager = TaskManager()
