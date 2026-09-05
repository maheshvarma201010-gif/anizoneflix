import unittest
import sys
import os

# Ensure repo root is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.parser import parse_ultra_advanced_group, parse_bulk_box_names
from bot import parse_advanced_group_message, parse_buttons_string

class TestBotFeatures(unittest.TestCase):

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

if __name__ == "__main__":
    unittest.main()
