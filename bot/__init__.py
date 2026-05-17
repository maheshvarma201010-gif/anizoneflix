import asyncio
import logging
import traceback
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config.config import Config
from api.jikan import jikan
from database.db import db
from utils.utils import slugify

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ANIZONEFLIX_BOT")

bot = Client(
    "anizoneflix_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    in_memory=True
)

async def set_commands(client):
    from pyrogram.types import BotCommand
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help menu"),
        BotCommand("search", "Search and add anime (Admin)"),
        BotCommand("categories", "Manage categories (Admin)"),
        BotCommand("del", "Delete anime (Admin)"),
        BotCommand("cancel", "Cancel current operation")
    ]
    await client.set_bot_commands(commands)
    logger.info("Bot commands set successfully!")

# Temporary storage for search flow
search_results = {}
user_state = {}

@bot.on_message(filters.all, group=-1)
async def debug_updates(client, message):
    try:
        print(f"UPDATE: {message.text}")
    except Exception:
        traceback.print_exc()

@bot.on_message(filters.command("ping"))
async def ping(client, message):
    try:
        await message.reply_text("Pong!")
    except Exception:
        traceback.print_exc()

@bot.on_message(filters.command("start"))
async def start(client, message):
    logger.info(f"Start command from {message.from_user.id if message.from_user else 'Unknown'}")
    try:
        await message.reply_photo(
            photo=Config.LOGO_URL,
            caption=(
                f"👋 **Hi {message.from_user.first_name}!**\n\n"
                f"Welcome to **ANIZONEFLIX** Management Bot.\n\n"
                "I help you search for anime via Jikan API and publish them instantly to your website.\n\n"
                "📜 **Available Commands:**\n"
                "• /search <name> - Find and add anime\n"
                "• /categories - Manage genres\n"
                "• /help - Full command list"
            )
        )
    except Exception as e:
        logger.error(f"Error in start cmd: {e}")
        await message.reply(f"Welcome to **ANIZONEFLIX**! Use /help to see commands.")

async def is_authorized(user_id):
    is_admin = user_id in Config.ADMIN_IDS or await db.is_admin(user_id)
    if not is_admin:
        logger.warning(f"Unauthorized access attempt by {user_id}")
    return is_admin

@bot.on_message(filters.command(["search", "add_post"]))
async def search_cmd(client, message):
    if not await is_authorized(message.from_user.id): return

    query = " ".join(message.command[1:])
    if not query:
        return await message.reply("❌ **Error:** Please provide an anime name.\nExample: `/search Naruto`")

    msg = await message.reply("🔍 **Searching Jikan API...**")
    try:
        results = await jikan.search_anime(query)
    except Exception as e:
        logger.error(f"Jikan Search Error: {e}")
        return await msg.edit("❌ **Error fetching data from Jikan API.**")

    if not results:
        return await msg.edit("😔 **No results found.** Try a different name.")

    search_results[message.from_user.id] = results[:8]

    text = "📌 **Select the correct anime:**\n\n"
    for i, anime in enumerate(search_results[message.from_user.id], 1):
        year = anime.get('year') or (anime.get('aired', {}).get('from', '')[:4])
        text += f"**{i}.** {anime['title']} ({year if year else 'N/A'})\n"

    text += "\n*Reply with the number to continue.*"

    await msg.edit(text)
    user_state[message.from_user.id] = {"action": "select_anime"}

@bot.on_message(filters.private & (filters.reply | filters.text) & ~filters.command(["start", "help", "search", "ping", "categories", "del", "cancel", "add_admin"]))
async def handle_reply(client, message):
    try:
        if not message.from_user: return
        if not message.text: return
        if not await is_authorized(message.from_user.id): return
        if message.text.startswith("/") and message.text != "/skip": return

        uid = message.from_user.id
        state = user_state.get(uid)
        if not state: return

        # 1. Select Anime
        if state["action"] == "select_anime":
            try:
                idx = int(message.text) - 1
                if not (0 <= idx < len(search_results[uid])):
                    return await message.reply("❌ **Invalid selection.** Choose 1-8.")

                selected = search_results[uid][idx]
                msg = await message.reply("⏳ **Fetching full metadata...**")
                details = await jikan.get_anime_details(selected["mal_id"])

                genres = ", ".join([g['name'] for g in details.get('genres', [])])
                caption = (
                    f"🎬 **{details['title']}**\n\n"
                    f"⭐ **Score:** {details.get('score', 'N/A')}\n"
                    f"📺 **Episodes:** {details.get('episodes', 'N/A')}\n"
                    f"📌 **Status:** {details.get('status', 'N/A')}\n"
                    f"🏷 **Genres:** {genres}\n\n"
                    f"📖 **Synopsis:** {details.get('synopsis', 'N/A')[:400]}..."
                )

                user_state[uid] = {"action": "ask_season", "anime_data": details}

                await message.reply_photo(
                    photo=details['images']['jpg']['large_image_url'],
                    caption=caption
                )
                await message.reply("🔢 **Step 1:** Enter the **Season Number** (e.g. 1):")
                await msg.delete()

            except Exception as e:
                logger.error(f"Selection Error: {e}")
                await message.reply("❌ **Error processing selection.**")

        # 2. Ask Season
        elif state["action"] == "ask_season":
            user_state[uid]["season"] = message.text
            user_state[uid]["action"] = "ask_480p"
            await message.reply(
                "🔗 **Step 2:** Enter **480p Link** (or /skip):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Skip", callback_data="skip_480p")]])
            )

        # 3. Quality Links
        elif state["action"] == "ask_480p":
            user_state[uid]["links_480p"] = message.text if message.text != "/skip" else None
            user_state[uid]["action"] = "ask_720p"
            await message.reply(
                "🔗 **Step 3:** Enter **720p Link** (or /skip):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Skip", callback_data="skip_720p")]])
            )

        elif state["action"] == "ask_720p":
            user_state[uid]["links_720p"] = message.text if message.text != "/skip" else None
            user_state[uid]["action"] = "ask_1080p"
            await message.reply(
                "🔗 **Step 4:** Enter **1080p Link** (or /skip):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Skip", callback_data="skip_1080p")]])
            )

        elif state["action"] == "ask_1080p":
            user_state[uid]["links_1080p"] = message.text if message.text != "/skip" else None
            user_state[uid]["action"] = "ask_batch"
            await message.reply(
                "📦 **Step 5:** Enter **Batch Link** (or /skip):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Skip", callback_data="skip_batch")]])
            )

        elif state["action"] == "ask_batch":
            user_state[uid]["links_batch"] = message.text if message.text != "/skip" else None
            user_state[uid]["action"] = "ask_trailer"
            await message.reply(
                "🎥 **Step 6:** Enter **Trailer Link** (or /skip):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Skip", callback_data="skip_trailer")]])
            )

        # 4. Final Publish
        elif state["action"] == "ask_trailer":
            user_state[uid]["trailer_link"] = message.text if message.text != "/skip" else None

            try:
                data = state["anime_data"]
                season = state["season"]
                slug = slugify(f"{data['title']} Season {season}")

                anime_entry = {
                    "mal_id": data["mal_id"],
                    "title": data["title"],
                    "slug": slug,
                    "season": season,
                    "synopsis": data.get("synopsis"),
                    "score": data.get("score"),
                    "image": data['images']['jpg']['large_image_url'],
                    "genres": [g['name'] for g in data.get('genres', [])],
                    "studios": [s['name'] for s in data.get('studios', [])],
                    "episodes": data.get("episodes"),
                    "rating": data.get("rating"),
                    "status": data.get("status"),
                    "aired": data.get("aired", {}).get("string"),
                    "year": data.get("year"),
                    "trailer": user_state[uid]["trailer_link"],
                    "links": {
                        "480p": user_state[uid]["links_480p"],
                        "720p": user_state[uid]["links_720p"],
                        "1080p": user_state[uid]["links_1080p"],
                        "batch": user_state[uid]["links_batch"]
                    }
                }

                await db.add_anime(anime_entry)
                logger.info(f"Published: {data['title']} S{season}")

                url = f"{Config.BASE_URL}/anime/{slug}"
                await message.reply(
                    f"✅ **Successfully Published!**\n\n"
                    f"🎬 **Anime:** {data['title']} (S{season})\n"
                    f"🌐 **Website URL:** {url}",
                    disable_web_page_preview=False
                )
            except Exception as e:
                logger.error(f"Publish Error: {e}")
                await message.reply("❌ **Error publishing to database.**")
            finally:
                del user_state[uid]

        # 5. Category Name
        elif state["action"] == "add_category_name":
            await db.add_category(message.text)
            await message.reply(f"✅ Category **{message.text}** added successfully!")
            del user_state[uid]
    except Exception:
        traceback.print_exc()

@bot.on_message(filters.command("cancel"))
async def cancel(client, message):
    if not await is_authorized(message.from_user.id): return
    if message.from_user.id in user_state:
        del user_state[message.from_user.id]
        await message.reply("⏹ **Current operation cancelled.**")
    else:
        await message.reply("Nothing to cancel.")

@bot.on_message(filters.command("del"))
async def delete_anime_cmd(client, message):
    if not await is_authorized(message.from_user.id): return
    if len(message.command) < 2:
        return await message.reply("❌ **Error:** Provide MAL ID or Website URL.")

    input_data = message.command[1]
    try:
        if "/anime/" in input_data:
            slug = input_data.split("/anime/")[1].split("?")[0]
            await db.delete_anime_by_slug(slug)
            await message.reply(f"🗑 Deleted: `{slug}`")
        else:
            mal_id = int(input_data)
            await db.delete_anime(mal_id)
            await message.reply(f"🗑 Deleted MAL ID: `{mal_id}`")
    except Exception as e:
        await message.reply(f"❌ **Error:** {e}")

@bot.on_message(filters.command("categories"))
async def categories_cmd(client, message):
    if not await is_authorized(message.from_user.id): return
    categories = await db.get_all_categories()
    text = "📂 **Current Categories:**\n\n"
    for cat in categories:
        text += f"• {cat['name']}\n"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add", callback_data="add_cat"),
            InlineKeyboardButton("➖ Remove", callback_data="del_cat")
        ]
    ])
    await message.reply(text, reply_markup=keyboard)

@bot.on_callback_query(filters.regex("^add_cat$"))
async def add_cat_cb(client, callback_query):
    await callback_query.message.edit("📝 **Send the name of the new category:**")
    user_state[callback_query.from_user.id] = {"action": "add_category_name"}

@bot.on_callback_query(filters.regex("^del_cat$"))
async def del_cat_cb(client, callback_query):
    categories = await db.get_all_categories()
    if not categories:
        return await callback_query.answer("No categories to delete.", show_alert=True)

    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(cat['name'], callback_data=f"remove_cat_{cat['name']}")])

    await callback_query.message.edit("🗑 **Select category to remove:**", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^remove_cat_"))
async def remove_cat_confirm(client, callback_query):
    cat_name = callback_query.data.split("remove_cat_")[1]
    await db.delete_category(cat_name)
    await callback_query.answer(f"Removed {cat_name}", show_alert=True)
    await categories_cmd(client, callback_query.message)

@bot.on_callback_query(filters.regex("^skip_"))
async def skip_callback(client, callback_query):
    uid = callback_query.from_user.id
    if uid not in user_state: return

    # Simulate /skip
    class MockMessage:
        def __init__(self, uid, text):
            self.from_user = type('obj', (object,), {'id': uid})
            self.text = text
            self.private = True
        async def reply(self, text, reply_markup=None):
            return await bot.send_message(uid, text, reply_markup=reply_markup)
        def delete(self): pass

    await handle_reply(client, MockMessage(uid, "/skip"))
    await callback_query.answer()

@bot.on_message(filters.command("update_channel"))
async def update_channel_cmd(client, message):
    if not await is_authorized(message.from_user.id): return
    await message.reply("📢 **Channel Update feature is active.** Posts are automatically synced.")

@bot.on_message(filters.command("help"))
async def help_cmd(client, message):
    text = (
        "🛠 **ANIZONEFLIX Admin Help**\n\n"
        "• /start - Wake up the bot\n"
        "• /search <name> - Add new anime to website\n"
        "• /categories - Manage genres/categories\n"
        "• /del <id/url> - Remove anime from database\n"
        "• /add_admin <id> - Authorize another admin\n"
        "• /cancel - Stop current flow\n\n"
        "**Adding Flow:**\n"
        "Search -> Pick -> Enter Season -> Links (480p, 720p, 1080p, Batch) -> Trailer -> AUTO PUBLISH."
    )
    await message.reply(text)

@bot.on_message(filters.command("add_admin"))
async def add_admin_cmd(client, message):
    if not await is_authorized(message.from_user.id): return
    if len(message.command) < 2:
        return await message.reply("Usage: `/add_admin 12345678`")
    try:
        user_id = int(message.command[1])
        await db.add_admin(user_id)
        await message.reply(f"✅ User `{user_id}` is now an admin.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")
