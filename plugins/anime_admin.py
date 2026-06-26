import asyncio
import logging
import traceback
import os
import json
import time
from pyrogram import Client, filters, enums, ContinuePropagation
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config.config import Config
from api.anime_api import anime_api
from database.db import db
from utils.utils import slugify
from bot import is_authorized, user_state, search_results
from bson import ObjectId

logger = logging.getLogger("ANIME_ADMIN")

# --- HANDLERS ---

@Client.on_message(filters.command("search") & filters.private)
async def search_cmd(client, message):
    if not await is_authorized(message.from_user.id): return
    query = " ".join(message.command[1:])
    if not query:
        user_state[message.from_user.id] = {"action": "ask_search_query"}
        return await message.reply("🛰 **Intelligence Aggregator**\n\nPlease send the **Title** of the series:")

    msg = await message.reply("📡 **Scanning Intelligence Feeds...**")
    results = await anime_api.search_all(query)
    if not results:
        user_state[message.from_user.id] = {"action": "ask_search_query"}
        return await msg.edit("😔 **Search Exhausted.** No matches found. Try again:")

    search_results[message.from_user.id] = results
    text = "🎯 **Select Match from Feed:**\n\n"
    for i, res in enumerate(results[:10], 1):
        text += f"**{i}.** {res['title']} ({res['year']}) `[{res['source'].upper()}]`\n"
    await msg.edit(text)
    user_state[message.from_user.id] = {"action": "select_anime"}

@Client.on_message(filters.command("add_post") & filters.private)
async def auto_post_handler(client, message):
    if not await is_authorized(message.from_user.id): return
    query = " ".join(message.command[1:])
    if not query: return await message.reply("💡 **Usage:** `/add_post <name>`")

    msg = await message.reply(f"⚡ **Rapid Publication: {query}...**")
    results = await anime_api.search_all(query)
    if not results: return await msg.edit("❌ **Publication Failed:** No match found.")

    best_match = results[0]
    details = await anime_api.get_details(best_match["source"], best_match["id"])
    if not details:
        details = {"title": best_match["title"], "synopsis": "N/A", "score": 0, "image": best_match["image"], "genres": [], "status": "N/A", "year": best_match["year"], "episodes": 0, "trailer": None, "studios": []}

    user_state[message.from_user.id] = {"action": "ask_category", "anime_data": details, "season": "1", "image": details["image"]}
    cats = await db.get_all_categories()
    buttons = [[InlineKeyboardButton(c['name'], callback_data=f"setcat_{c['name']}")] for c in (cats if cats else [{"name": "Anime"}])]
    await message.reply_photo(photo=details["image"] or Config.LOGO_URL, caption=f"🎬 **Archive Ready:** `{details['title']}`\n\nTarget **Category**:", reply_markup=InlineKeyboardMarkup(buttons))
    await msg.delete()

# --- CALLBACKS (Moved from bot/__init__.py backup logic) ---

@Client.on_callback_query(filters.regex("^setcat_"))
async def set_cat_cb(client, callback_query):
    uid = callback_query.from_user.id
    state = user_state.get(uid)
    if not state or state["action"] != "ask_category": return

    cat, data = callback_query.data.split("_")[1], state["anime_data"]
    slug = slugify(data["title"])
    # Default group "1"
    entry = {
        "mal_id": f"auto_{slug}", "title": data["title"], "slug": slug, "synopsis": data["synopsis"],
        "score": data["score"], "image": state["image"], "genres": data["genres"], "category": cat,
        "status": data["status"], "year": data["year"], "trailer": data["trailer"],
        "seasons_links": {"1": {"480p": None, "720p": None, "1080p": None}},
        "custom_buttons": [],
        "last_group": {"name": "1", "at": time.time()} # NEW: Track for glow effect
    }
    if await db.ping():
        await db.anime.update_one({"slug": slug}, {"$set": entry}, upsert=True)
        await callback_query.message.edit_caption(caption=f"⚡ **Deployment Success!**\nPortal: {Config.BASE_URL}/anime/{slug}", reply_markup=None)
        user_state.pop(uid, None)

@Client.on_callback_query(filters.regex("^finalcat_"))
async def final_publish_cb(client, callback_query):
    uid = callback_query.from_user.id
    state = user_state.get(uid)
    if not state or state["action"] != "ask_category_final": return

    cat, data = callback_query.data.split("_")[1], state["anime_data"]
    slug = slugify(data["title"])

    last_g = None
    if state["seasons_data"]:
        last_g_name = list(state["seasons_data"].keys())[-1]
        last_g = {"name": last_g_name, "at": time.time()}

    entry = {
        "mal_id": f"series_{slug}", "title": data["title"], "slug": slug, "synopsis": data["synopsis"],
        "score": data["score"], "image": state["image"], "genres": data["genres"], "category": cat,
        "status": data["status"], "year": data["year"], "trailer": data["trailer"],
        "seasons_links": state["seasons_data"], "custom_buttons": [],
        "last_group": last_g # NEW: Track for glow effect
    }
    if await db.ping():
        await db.anime.update_one({"slug": slug}, {"$set": entry}, upsert=True)
        await callback_query.message.edit_text(text=f"💎 **LIVE:** `{data['title']}`\nPortal: {Config.BASE_URL}/anime/{slug}", reply_markup=None)
        user_state.pop(uid, None)

# --- WIZARD HANDLERS (Called from bot.global_router) ---

async def anime_wizard(client, message, state):
    uid = message.from_user.id
    action = state.get("action")

    if action == "ask_edit_1080p":
        aid = state["slug"]
        gname = state["group_name"]
        anime = await db.get_anime(aid)
        current_groups = list(anime.get("seasons_links", {}).items()) if anime else []
        new_group_data = (gname, {"480p": state.get("480p"), "720p": state.get("720p"), "1080p": message.text if message.text != "/skip" else None})

        pos = state.get("insert_pos", -1)
        if pos == -1: current_groups.append(new_group_data)
        else: current_groups.insert(pos, new_group_data)

        if await db.ping():
            await db.anime.update_one(
                {"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid},
                {"$set": {"seasons_links": dict(current_groups), "last_group": {"name": gname, "at": time.time()}}} # NEW
            )
            await message.reply(f"💎 **Success!** Group synchronized.")
            user_state.pop(uid, None)

    # Add other wizard actions here...
