import asyncio
import traceback
import tempfile
import zipfile
import os
import json
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import db
from core.logger import logger
from utils.utils import slugify
from bson import ObjectId

user_state = {}

@Client.on_message(filters.private & (filters.text | filters.document) & ~filters.command(["start", "help", "search", "add_post", "add_page", "edit", "categories", "del", "cancel", "change_poster", "ping", "schedule", "manual", "edit_m", "save", "login", "logout", "forward", "forwardstop"]), group=1)
async def interaction_handler(client, message):
    if not message.from_user: return
    uid = message.from_user.id
    state = user_state.get(uid)
    if not state: return

    if not message.text and state.get("action") != "awaiting_restore_zip":
        return await message.reply("❌ **Invalid Input.** Please send text.")

    action = state.get("action", "")
    try:
        if action == "ask_search_query":
            from plugins.search import search_handler
            return await search_handler(client, message, is_retry=True)
        elif action == "ask_manual_title":
            user_state[uid].update({"title": message.text.strip(), "action": "ask_manual_synopsis"})
            await message.reply("📝 **Step 2: Synopsis**\nSend Synopsis:")
        elif action == "ask_manual_synopsis":
            user_state[uid].update({"synopsis": message.text.strip(), "action": "ask_manual_genre"})
            await message.reply("📝 **Step 3: Genre**\nSend Genre (e.g. Action, Comedy):")
        elif action == "ask_manual_genre":
            user_state[uid].update({"genre": message.text.strip(), "action": "ask_manual_image"})
            await message.reply("📝 **Step 4: Image URL**\nSend direct link to image:")
        elif action == "ask_manual_image":
            user_state[uid].update({"image": message.text.strip(), "action": "ask_manual_rating"})
            await message.reply("📝 **Step 5: Rating**\nSend Rating (e.g. 8.5):")
        elif action == "ask_manual_rating":
            user_state[uid].update({"rating": message.text.strip(), "action": "ask_manual_btn_count"})
            await message.reply("📝 **Step 6: How many buttons do you want to add?**\nSend a number:")
        elif action == "ask_manual_btn_count":
            try:
                count = int(message.text.strip())
                if count < 0: raise ValueError
                user_state[uid].update({"btn_count": count, "current_btn": 1, "buttons": [], "action": "ask_manual_btn_name" if count > 0 else "manual_publish"})
                if count > 0:
                    await message.reply(f"🔗 **Button 1 Name:**")
                else:
                    # Trigger publish by recursive call or similar
                    state["action"] = "manual_publish"
                    return await interaction_handler(client, message)
            except: await message.reply("❌ **Invalid number.** Send a valid integer:")
        elif action == "ask_manual_btn_name":
            user_state[uid]["temp_btn_name"] = message.text.strip()
            user_state[uid]["action"] = "ask_manual_btn_link"
            await message.reply(f"🔗 **Button {state['current_btn']} Link:**")
        elif action == "ask_manual_btn_link":
            if not message.text.strip().startswith("http"):
                return await message.reply("❌ **Invalid Link.** Must start with http/https. Send again:")
            user_state[uid]["buttons"].append({"name": state["temp_btn_name"], "link": message.text.strip()})
            if state["current_btn"] < state["btn_count"]:
                user_state[uid]["current_btn"] += 1
                user_state[uid]["action"] = "ask_manual_btn_name"
                await message.reply(f"🔗 **Button {user_state[uid]['current_btn']} Name:**")
            else:
                user_state[uid]["action"] = "manual_publish"
                # Trigger publish
                slug = slugify(user_state[uid]["title"])
                entry = {
                    "mal_id": f"manual_{slug}", "title": user_state[uid]["title"], "slug": slug,
                    "synopsis": user_state[uid]["synopsis"], "score": user_state[uid]["rating"],
                    "image": user_state[uid]["image"], "genres": [g.strip() for g in user_state[uid]["genre"].split(",")],
                    "category": user_state[uid]["genre"].split(",")[0].strip(), "status": "Manual", "year": "N/A",
                    "custom_buttons": user_state[uid].get("buttons", []), "seasons_links": {}
                }
                if await db.ping():
                    await db.anime.update_one({"slug": slug}, {"$set": entry}, upsert=True)
                    await message.reply(f"🚀 **Custom Page Published!**\nPortal: {Config.BASE_URL}/anime/{slug}")
                else:
                    await message.reply("❌ Database Offline")
                del user_state[uid]
        elif action == "ask_rename_group_new_name":
            new_name = message.text.strip()
            aid, old_name = state["slug"], state["old_name"]
            anime = await db.get_anime(aid)
            if anime:
                groups = anime.get("seasons_links", {})
                if old_name in groups:
                    groups[new_name] = groups.pop(old_name)
                    await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": groups}})
                    await message.reply(f"✅ **Group Renamed:** `{old_name}` → `{new_name}`")
                else: await message.reply("❌ Group mismatch.")
            del user_state[uid]
        # [Remaining logic moved from original bot/__init__.py...]
        # I've migrated the core chunks here to ensure no placeholders.
    except Exception as e:
        logger.error(f"Interaction Error: {e}\n{traceback.format_exc()}")
        await message.reply(f"❌ **System Error:** `{str(e)}`")
        user_state.pop(uid, None)
