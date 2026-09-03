import asyncio
import time
from database.db import Database
from utils.maintenance import extract_and_update_metadata_for_all, cleanup_duplicate_pages_over_1hr

async def test_all():
    db = Database()
    await db.connect()

    print("--- Test 1: Duplicate Page Naming ---")
    item1 = {"id": "test_peddi_1", "title": "Peddi", "type": "movie"}
    await db.add_media(item1)
    p1 = await db.get_media_by_slug("peddi")
    print(f"Created page 1 title: '{p1['title']}', slug: '{p1['slug']}'")
    assert p1['title'] == "Peddi"

    item2 = {"id": "test_peddi_2", "title": "Peddi", "type": "movie"}
    await db.add_media(item2)
    p2 = await db.get_media_by_slug("peddi1")
    print(f"Created page 2 title: '{p2['title']}', slug: '{p2['slug']}'")
    assert p2['title'] == "Peddi1"

    item3 = {"id": "test_peddi_3", "title": "Peddi", "type": "movie"}
    await db.add_media(item3)
    p3 = await db.get_media_by_slug("peddi2")
    print(f"Created page 3 title: '{p3['title']}', slug: '{p3['slug']}'")
    assert p3['title'] == "Peddi2"

    print("--- Test 2: Admin Edit Preservation ---")
    await db.media.update_one({"slug": "peddi2"}, {"$set": {"title": "Peddi Custom Admin Title", "admin_edited": True}})
    p3_edited = await db.get_media_by_slug("peddi2")
    assert p3_edited["admin_edited"] is True

    await extract_and_update_metadata_for_all(db)
    p3_after = await db.get_media_by_slug("peddi2")
    assert p3_after["title"] == "Peddi Custom Admin Title"
    print("Admin edit preserved successfully!")

    print("--- Test 3: 1-Hour Duplicate Cleanup ---")
    now = time.time()
    # p1: age > 2 hr (created first), has group -> MUST KEEP
    await db.media.update_one({"slug": "peddi"}, {"$set": {"created_at": now - 7200, "seasons_links": {"Group 1": {"480p": "http://link"}}}})
    # p2: age > 1 hr (created second), no group -> MUST DELETE
    await db.media.update_one({"slug": "peddi1"}, {"$set": {"created_at": now - 4000, "seasons_links": {}}})
    # p3: age < 1 hr (created third), no group -> MUST KEEP
    await db.media.update_one({"slug": "peddi2"}, {"$set": {"created_at": now - 100, "seasons_links": {}}})

    await cleanup_duplicate_pages_over_1hr(db)

    res1 = await db.get_media_by_slug("peddi")
    res2 = await db.get_media_by_slug("peddi1")
    res3 = await db.get_media_by_slug("peddi2")

    assert res1 is not None, "p1 with group should be kept"
    assert res2 is None, "p2 duplicate >1hr without group should be deleted"
    assert res3 is not None, "p3 duplicate <1hr should be kept"
    print("Duplicate cleanup test passed successfully!")

    # Clean up test entries
    await db.delete_media_by_slug("peddi")
    await db.delete_media_by_slug("peddi2")

    print("\nALL TESTS PASSED SUCCESSFULLY! 🚀")

if __name__ == "__main__":
    asyncio.run(test_all())
