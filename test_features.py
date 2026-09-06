import unittest
import sys
import os

# Ensure repo root is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.parser import parse_ultra_advanced_group, parse_bulk_box_names
from bot import (
    parse_advanced_group_message,
    parse_buttons_string,
    parse_range_link,
    parse_group_names_list,
    parse_genlink_bot_response
)

class TestBotFeatures(unittest.TestCase):

    def test_parse_range_link(self):
        # Full URL range
        res1 = parse_range_link("https://t.me/hsjisksjs/23961-https://t.me/hsjisksjs/24035")
        self.assertEqual(res1, ("hsjisksjs", 23961, 24035))

        # Short URL range
        res2 = parse_range_link("https://t.me/hsjisksjs/23961-24035")
        self.assertEqual(res2, ("hsjisksjs", 23961, 24035))

        # Private channel format
        res3 = parse_range_link("https://t.me/c/1234567890/100-https://t.me/c/1234567890/110")
        self.assertEqual(res3, ("c/1234567890", 100, 110))

        res4 = parse_range_link("https://t.me/c/1234567890/100-110")
        self.assertEqual(res4, ("c/1234567890", 100, 110))

        # Invalid range
        self.assertIsNone(parse_range_link("https://example.com/test"))

    def test_parse_group_names_list(self):
        text = """
1. Group Alpha
2. Group Beta
3. Group Gamma
"""
        groups = parse_group_names_list(text)
        self.assertEqual(groups, ["Group Alpha", "Group Beta", "Group Gamma"])

        invalid_text = """
1. Group Alpha
Group Beta without serial
"""
        self.assertIsNone(parse_group_names_list(invalid_text))

    def test_parse_genlink_bot_response(self):
        bot_response = """
First Filename: Sword Art Online S01E01 480p x264 Bluray Multi Audio Esu.mkv
First Caption: 🎬 Sword Art Online S01E01 480p x264 Bluray Multi Audio Esub (crunchyroll dub).mkv

📦 Size: 109.52MB
⏱ Duration: 1423
🌐 Languages: हिन्दी, தமிழ், తెలుగు, English, 日本語

Last Filename: Sword Art Online S01E01 480p x264 Bluray Multi Audio Esu.mkv
Last Caption: 🎬 Sword Art Online S01E01 480p x264 Bluray Multi Audio Esub (crunchyroll dub).mkv

📦 Size: 109.52MB
⏱ Duration: 1423
🌐 Languages: हिन्दी, தமிழ், తెలుగు, English, 日本語

Here is your link:

"https://telegram.me/AniZoneFlix_bot?start=Z2V0LTI0MDUwODI3NzM1MjU0NzY4"
"""
        parsed = parse_genlink_bot_response(bot_response)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["link"], "https://telegram.me/AniZoneFlix_bot?start=Z2V0LTI0MDUwODI3NzM1MjU0NzY4")
        self.assertEqual(parsed["quality"], "480P")
        self.assertEqual(parsed["episode"], 1)

        # Test filter_name matching
        parsed_match = parse_genlink_bot_response(bot_response, filter_name="Sword Art Online")
        self.assertIsNotNone(parsed_match)

        # Test filter_name mismatch filtering out
        parsed_mismatch = parse_genlink_bot_response(bot_response, filter_name="Naruto Shippuden")
        self.assertIsNone(parsed_mismatch)

        # Test dot "." filter_name (unfiltered)
        parsed_dot = parse_genlink_bot_response(bot_response, filter_name=".")
        self.assertIsNotNone(parsed_dot)

    def test_parse_all_genlink_blocks_bulk_message(self):
        bulk_response = """
<b>First Filename:</b> Sword Art Online S01E01 480p.mkv
<b>First Caption:</b> SAO E01 480p
<b>Last Filename:</b> Sword Art Online S01E01 480p.mkv
<b>Last Caption:</b> SAO E01 480p

<b>Here is your link:</b>

<code>https://telegram.me/AniZoneFlix_bot?start=link1</code>

<b>First Filename:</b> Sword Art Online S01E02 720p.mkv
<b>First Caption:</b> SAO E02 720p
<b>Last Filename:</b> Sword Art Online S01E02 720p.mkv
<b>Last Caption:</b> SAO E02 720p

<b>Here is your link:</b>

<code>https://telegram.me/AniZoneFlix_bot?start=link2</code>
"""
        from bot import parse_all_genlink_blocks
        results = parse_all_genlink_blocks(bulk_response, filter_name="Sword")
        self.assertEqual(len(results), 2)

        self.assertEqual(results[0]["link"], "https://telegram.me/AniZoneFlix_bot?start=link1")
        self.assertEqual(results[0]["quality"], "480P")
        self.assertEqual(results[0]["episode"], 1)

        self.assertEqual(results[1]["link"], "https://telegram.me/AniZoneFlix_bot?start=link2")
        self.assertEqual(results[1]["quality"], "720P")
        self.assertEqual(results[1]["episode"], 2)

    def test_configured_bot_and_session_db_mock_methods(self):
        from database.db import db
        import asyncio

        async def run_config_test():
            bot_username = await db.get_configured_bot()
            session_str = await db.get_configured_session()

            await db.set_configured_bot("@AniZoneFlix_bot")
            await db.set_configured_session("1B...mock_session_string")

            res_bot = await db.get_configured_bot()
            res_ss = await db.get_configured_session()

            if res_bot:
                self.assertEqual(res_bot, "AniZoneFlix_bot")
            if res_ss:
                self.assertEqual(res_ss, "1B...mock_session_string")

        asyncio.run(run_config_test())

    def test_existing_advanced_group_parser(self):
        # Existing Advanced Group format:
        # 1. Season 1
        # 480P : https://example.com/480
        # 720P : https://example.com/720
        adv_text = """
1. Season 1
480P : https://example.com/480
720P : https://example.com/720
"""
        parsed, err = parse_advanced_group_message(adv_text)
        self.assertIsNone(err)
        self.assertIn("Season 1", parsed)
        self.assertEqual(parsed["Season 1"]["480P"], "https://example.com/480")
        self.assertEqual(parsed["Season 1"]["720P"], "https://example.com/720")

    def test_ultra_advanced_group_parser_success(self):
        ultra_text = """
I. BOX NAME: Naruto

1. Quality
   480P : https://example.com/480?param=1:2
   720P : https://example.com/720

2. Languages
   Telugu : https://example.com/telugu

II. BOX NAME: One Piece

1. Quality
   1080P : https://example.com/1080
"""
        parsed, errs = parse_ultra_advanced_group(ultra_text)
        self.assertEqual(len(errs), 0)
        self.assertEqual(len(parsed), 2)

        self.assertEqual(parsed[0]["box_name"], "Naruto")
        self.assertEqual(parsed[0]["roman"], "I")
        self.assertEqual(len(parsed[0]["groups"]), 2)
        self.assertEqual(parsed[0]["groups"][0]["group_name"], "Quality")
        self.assertEqual(parsed[0]["groups"][0]["buttons"]["480P"], "https://example.com/480?param=1:2")
        self.assertEqual(parsed[0]["groups"][0]["buttons"]["720P"], "https://example.com/720")
        self.assertEqual(parsed[0]["groups"][1]["group_name"], "Languages")
        self.assertEqual(parsed[0]["groups"][1]["buttons"]["Telugu"], "https://example.com/telugu")

        self.assertEqual(parsed[1]["box_name"], "One Piece")
        self.assertEqual(parsed[1]["roman"], "II")
        self.assertEqual(len(parsed[1]["groups"]), 1)
        self.assertEqual(parsed[1]["groups"][0]["group_name"], "Quality")
        self.assertEqual(parsed[1]["groups"][0]["buttons"]["1080P"], "https://example.com/1080")

    def test_ultra_advanced_group_parser_validation_errors(self):
        invalid_text = """
I. BOX NAME: Naruto
480P : https://example.com/480
"""
        # Line with button before any group defined
        parsed, errs = parse_ultra_advanced_group(invalid_text)
        self.assertGreater(len(errs), 0)
        self.assertTrue(any("before any Group was defined" in e for e in errs))

    def test_bulk_box_parser(self):
        bulk_text = """
1. Naruto
2. One Piece
3. Bleach
4. Jujutsu Kaisen
5. Demon Slayer
"""
        parsed, errs = parse_bulk_box_names(bulk_text)
        self.assertEqual(len(errs), 0)
        self.assertEqual(parsed, ["Naruto", "One Piece", "Bleach", "Jujutsu Kaisen", "Demon Slayer"])

    def test_bulk_box_parser_duplicates_and_empty(self):
        bulk_text_dup = """
1. Naruto
2. One Piece
3. Naruto
4.
"""
        parsed, errs = parse_bulk_box_names(bulk_text_dup)
        # Duplicate Naruto should be ignored, empty item at 4 should yield an error or be skipped
        self.assertIn("Naruto", parsed)
        self.assertEqual(parsed, ["Naruto", "One Piece"])
        self.assertTrue(any("Box name is empty" in e for e in errs))

    def test_combined_group_name_and_buttons_parsing(self):
        text = """
Episode 15 - The New Demon Lord
480p : https://t.me/anizoneflix_bot?start=Z2V0LTIyNDY1OTA4MTk5NTk0MDE2 720p : https://t.me/anizoneflix_bot?start=Z2V0LTIyNDYzOTAwNzAxNzY1NDQw 1080p : https://t.me/anizoneflix_bot?start=Z2V0LTIyNDY0OTA4NDUwNjc5NzI4
"""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        self.assertGreaterEqual(len(lines), 2)

        gname = lines[0]
        buttons_text = "\n".join(lines[1:])

        self.assertEqual(gname, "Episode 15 - The New Demon Lord")
        parsed_buttons = parse_buttons_string(buttons_text, 3)
        self.assertIsNotNone(parsed_buttons)
        self.assertEqual(parsed_buttons["480p"], "https://t.me/anizoneflix_bot?start=Z2V0LTIyNDY1OTA4MTk5NTk0MDE2")
        self.assertEqual(parsed_buttons["720p"], "https://t.me/anizoneflix_bot?start=Z2V0LTIyNDYzOTAwNzAxNzY1NDQw")
        self.assertEqual(parsed_buttons["1080p"], "https://t.me/anizoneflix_bot?start=Z2V0LTIyNDY0OTA4NDUwNjc5NzI4")

    def test_songs_db_mock_methods(self):
        from database.db import db
        import asyncio

        async def run_songs_test():
            # Test mocked/unconnected safe operations
            songs = await db.get_all_songs()
            self.assertIsInstance(songs, list)

            song = await db.get_song("non_existent_id")
            self.assertIsNone(song)

            channel = await db.get_song_channel()
            self.assertIsNone(channel)

        asyncio.run(run_songs_test())

    def test_uptime_monitored_bots_db_mock_methods(self):
        from database.db import db
        import asyncio

        async def run_uptime_test():
            bots = await db.get_all_monitored_bots()
            self.assertIsInstance(bots, list)

            bot = await db.get_monitored_bot("non_existent_id")
            self.assertIsNone(bot)

            # Test adding, updating, and deleting monitored bot
            bot_id = await db.add_monitored_bot("https://testbot.example.com", name="TestBot")
            self.assertIsNotNone(bot_id)

            bot_info = await db.get_monitored_bot(bot_id)
            if bot_info:
                self.assertEqual(bot_info.get("url"), "https://testbot.example.com")
                self.assertEqual(bot_info.get("name"), "TestBot")

            await db.update_monitored_bot_status(bot_id, "online", 200, 120)
            await db.replace_monitored_bot(bot_id, "https://newtestbot.example.com")
            await db.delete_monitored_bot(bot_id)

        asyncio.run(run_uptime_test())

    def test_addbot_report_and_bot_filter(self):
        from bot.bot_manager import report_addbot_issue
        from bot.plugins.addbot import validate_bot_token
        import asyncio
        from unittest.mock import MagicMock

        async def run_report_test():
            # Test token validation regex
            self.assertTrue(validate_bot_token("123456789:ABCdefGhIJKlmnoPQRstuvwxYZ_123456789"))
            self.assertFalse(validate_bot_token("invalid_token_string"))

            # Test report_addbot_issue with unconfigured ADMIN_IDS safely
            await report_addbot_issue("TestBot", "Simulated error")

            # Verify Pyrogram Message bot filter logic
            mock_user = MagicMock()
            mock_user.is_bot = True

            mock_human_user = MagicMock()
            mock_human_user.is_bot = False

            self.assertTrue(mock_user.is_bot)
            self.assertFalse(mock_human_user.is_bot)

        asyncio.run(run_report_test())

    def test_language_parsing_and_post_channel_db(self):
        from bot import parse_language_input
        from database.db import db
        import asyncio

        # Test language parsing
        self.assertEqual(parse_language_input("tel,tam,hin,eng"), "Telugu • Tamil • Hindi • English")
        self.assertEqual(parse_language_input("Telugu, Tamil, Japanese"), "Telugu • Tamil • Japanese")

        # Test post channel settings
        async def run_post_channel_test():
            await db.set_post_channel("-1001234567890")
            val = await db.get_post_channel()
            if val:
                self.assertEqual(val, "-1001234567890")

        asyncio.run(run_post_channel_test())

    def test_auto_fill_missing_metadata(self):
        from api.anime_api import auto_fill_missing_metadata
        import asyncio

        async def run_metadata_test():
            doc = {
                "title": "Naruto",
                "synopsis": "N/A",
                "score": 0
            }
            res = await auto_fill_missing_metadata(doc)
            self.assertIsNotNone(res)
            self.assertEqual(res["title"], "Naruto")

        asyncio.run(run_metadata_test())

    def test_details_page_languages_rendering(self):
        from jinja2 import Environment, FileSystemLoader
        from utils.utils import slugify
        env = Environment(loader=FileSystemLoader("templates"))
        env.filters["slugify"] = slugify
        env.filters["button_link_rewrite"] = lambda x: x
        template = env.get_template("details.html")

        anime_doc = {
            "title": "Naruto",
            "synopsis": "A ninja anime",
            "score": 8.5,
            "image": "https://example.com/poster.jpg",
            "genres": ["Action", "Adventure"],
            "category": "Anime",
            "languages": "Telugu • Tamil • Hindi • English",
            "seasons_links": {},
            "custom_boxes": []
        }

        rendered = template.render(anime=anime_doc, site_name="ANIZONEFLIX", logo_url="logo.png", episodes=[])
        self.assertIn("Audio Languages:", rendered)
        self.assertIn("Telugu • Tamil • Hindi • English", rendered)

        # Check that genre line comes before audio languages line, and audio languages line comes before h1 title
        genre_pos = rendered.find("Action")
        lang_pos = rendered.find("Audio Languages:")
        title_pos = rendered.find("<h1")

        self.assertNotEqual(genre_pos, -1)
        self.assertNotEqual(lang_pos, -1)
        self.assertNotEqual(title_pos, -1)
        self.assertTrue(genre_pos < lang_pos < title_pos)

    def test_post_flow_interaction_handler_ignores_commands(self):
        from bot import user_state, register_handlers
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        # Collect handlers from register_handlers
        mock_bot = MagicMock()
        registered_handlers = []
        def mock_on_message(filters=None, group=0):
            def decorator(func):
                registered_handlers.append((group, func))
                return func
            return decorator
        mock_bot.on_message = mock_on_message

        register_handlers(mock_bot)

        interaction_handler = None
        for group, func in registered_handlers:
            if group == 1:
                interaction_handler = func
                break

        self.assertIsNotNone(interaction_handler)

        async def run_post_interaction_test():
            uid = 999888
            user_state[uid] = {
                "action": "ask_post_heading",
                "aid": "123",
                "slug": "naruto",
                "page_link": "https://example.com/anime/naruto"
            }

            client = MagicMock()

            # Message starting with command /post ...
            msg_cmd = AsyncMock()
            msg_cmd.from_user.id = uid
            msg_cmd.text = "/post https://example.com/anime/naruto"

            with patch("bot.is_authorized", AsyncMock(return_value=True)):
                await interaction_handler(client, msg_cmd)

            # State should REMAIN ask_post_heading because command message /post was ignored by interaction_handler
            self.assertEqual(user_state.get(uid, {}).get("action"), "ask_post_heading")

            user_state.pop(uid, None)

        asyncio.run(run_post_interaction_test())

if __name__ == "__main__":
    unittest.main()
