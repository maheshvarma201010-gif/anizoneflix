import asyncio
import os
from database.db import Database

async def test_songs_management():
    db = Database()
    await db.connect()

    print("--- Test 1: Add Songs ---")
    s1 = {"id": "song_test_1", "title": "Test Song 1", "filename": "song_test_1.mp3", "url": "/api/songs/file/song_test_1.mp3"}
    s2 = {"id": "song_test_2", "title": "Test Song 2", "filename": "song_test_2.mp3", "url": "/api/songs/file/song_test_2.mp3"}

    await db.add_song(s1)
    await db.add_song(s2)

    all_songs = await db.get_all_songs()
    ids = [s["id"] for s in all_songs]
    print(f"Active songs count: {len(all_songs)}, IDs: {ids}")
    assert "song_test_1" in ids
    assert "song_test_2" in ids

    print("--- Test 2: Song Channel Setting ---")
    await db.set_song_channel("-1001999999999")
    chan = await db.get_song_channel()
    print("Song channel:", chan)
    assert chan == "-1001999999999"

    print("--- Test 3: Delete Song ---")
    await db.delete_song("song_test_1")
    after_del = await db.get_all_songs()
    after_ids = [s["id"] for s in after_del]
    assert "song_test_1" not in after_ids
    assert "song_test_2" in after_ids

    # Cleanup s2
    await db.delete_song("song_test_2")

    print("\nALL SONG TESTS PASSED SUCCESSFULLY! 🚀")

if __name__ == "__main__":
    asyncio.run(test_songs_management())
