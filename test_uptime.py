import asyncio
import aiohttp
from database.db import Database
from utils.uptime import ping_target

async def test_uptime_monitoring():
    db = Database()
    await db.connect()

    print("--- Test 1: Add Uptime Bots ---")
    b1 = {"id": "upt_test_1", "name": "httpbin.org", "url": "https://httpbin.org/get"}
    b2 = {"id": "upt_test_2", "name": "example.com", "url": "https://example.com"}

    await db.add_uptime_bot(b1)
    await db.add_uptime_bot(b2)

    bots = await db.get_all_uptime_bots()
    ids = [b["id"] for b in bots]
    print(f"Monitored bots count: {len(bots)}, IDs: {ids}")
    assert "upt_test_1" in ids
    assert "upt_test_2" in ids

    print("--- Test 2: Ping Targets ---")
    async with aiohttp.ClientSession() as session:
        target1 = await db.get_uptime_bot_by_id("upt_test_1")
        await ping_target(session, target1)
        print("Target 1 Status:", target1.get("status"), "Latency:", target1.get("latency"), "ms")
        assert target1.get("status") in ["online", "degraded"]

    print("--- Test 3: Replace & Delete Uptime Bot ---")
    await db.update_uptime_bot("upt_test_1", {"url": "https://httpbin.org/status/200"})
    updated = await db.get_uptime_bot_by_id("upt_test_1")
    assert updated["url"] == "https://httpbin.org/status/200"

    await db.delete_uptime_bot("upt_test_1")
    await db.delete_uptime_bot("upt_test_2")

    after_del = await db.get_all_uptime_bots()
    after_ids = [b["id"] for b in after_del]
    assert "upt_test_1" not in after_ids
    assert "upt_test_2" not in after_ids

    print("\nALL UPTIME MONITOR TESTS PASSED SUCCESSFULLY! 🚀")

if __name__ == "__main__":
    asyncio.run(test_uptime_monitoring())
