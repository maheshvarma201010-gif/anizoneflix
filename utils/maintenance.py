import asyncio
import logging
import time
import re
from api.media_api import media_api

logger = logging.getLogger("MZ_MAINTENANCE")

def get_base_title(t):
    if not t: return ""
    m = re.match(r"^(.*?)\d+$", t.strip())
    if m and m.group(1).strip():
        return m.group(1).strip().lower()
    return t.strip().lower()

async def extract_and_update_metadata_for_all(db):
    """
    After redeploy, automatically extract and set the metadata for every page.
    If an admin edits any page name/metadata using /edit, admin_edited is set to True,
    and this function will not change anything in that page.
    """
    try:
        all_media = await db.get_all_media(limit=10000)
        logger.info(f"Starting post-redeploy metadata check for {len(all_media)} media pages...")
        for media in all_media:
            if media.get("admin_edited"):
                logger.info(f"Skipping metadata auto-extraction for admin-edited page: '{media.get('title')}'")
                continue

            title = media.get("title")
            if not title:
                continue

            # Check for missing or 'N/A' fields
            need_director = not media.get("director") or media.get("director") == "N/A"
            need_cast = not media.get("cast") or media.get("cast") == ["N/A"] or len(media.get("cast", [])) == 0
            need_runtime = not media.get("runtime") or media.get("runtime") == "N/A"
            need_year = not media.get("year") or media.get("year") == "N/A"
            need_genres = not media.get("genres") or len(media.get("genres", [])) == 0
            need_score = not media.get("score") or media.get("score") == 0
            need_synopsis = not media.get("synopsis")
            need_image = not media.get("image")

            if not (need_director or need_cast or need_runtime or need_year or need_genres or need_score or need_synopsis or need_image):
                continue

            updates = {}
            media_type = media.get("type") or "movie"

            # 1. Try TMDb
            tmdb_id = media.get("tmdb_id")
            details = None
            if tmdb_id:
                details = await media_api.get_tmdb_details(media_type, tmdb_id)

            if not details:
                search_res = await media_api.search_tmdb(title)
                if search_res:
                    first = search_res[0]
                    details = await media_api.get_tmdb_details(first.get("type", media_type), first["id"])

            if details:
                if need_synopsis and details.get("overview"):
                    updates["synopsis"] = details.get("overview")
                if need_score and details.get("vote_average"):
                    updates["score"] = round(details.get("vote_average"), 1)
                if need_year:
                    y = (details.get("release_date") or details.get("first_air_date") or "")[:4]
                    if y: updates["year"] = y
                if need_genres and details.get("genres"):
                    updates["genres"] = [g["name"] for g in details.get("genres", [])]
                if need_image and details.get("poster_path"):
                    updates["image"] = f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}"
                if need_runtime:
                    if details.get("runtime"): updates["runtime"] = f"{details['runtime']} min"
                    elif details.get("episode_run_time") and len(details["episode_run_time"]) > 0:
                        updates["runtime"] = f"{details['episode_run_time'][0]} min"

                credits = details.get("credits") or {}
                if need_director:
                    crew = credits.get("crew") or []
                    for member in crew:
                        if member.get("job") == "Director":
                            updates["director"] = member.get("name")
                            break
                if need_cast:
                    cast_members = credits.get("cast") or []
                    c_list = [c.get("name") for c in cast_members[:6] if c.get("name")]
                    if c_list: updates["cast"] = c_list

            # 2. Try OMDb if still missing fields
            if (need_director and "director" not in updates) or (need_cast and "cast" not in updates) or (need_runtime and "runtime" not in updates):
                try:
                    omdb_data = await media_api.get_omdb_metadata(title, updates.get("year") or media.get("year"))
                    if omdb_data and omdb_data.get("Response") == "True":
                        if need_director and "director" not in updates and omdb_data.get("Director") and omdb_data["Director"] != "N/A":
                            updates["director"] = omdb_data["Director"]
                        if need_cast and "cast" not in updates and omdb_data.get("Actors") and omdb_data["Actors"] != "N/A":
                            updates["cast"] = [c.strip() for c in omdb_data["Actors"].split(",") if c.strip()]
                        if need_runtime and "runtime" not in updates and omdb_data.get("Runtime") and omdb_data["Runtime"] != "N/A":
                            updates["runtime"] = omdb_data["Runtime"]
                except Exception as e:
                    logger.error(f"OMDb fallback metadata error: {e}")

            if updates:
                logger.info(f"Auto-extracted metadata for '{title}': {list(updates.keys())}")
                await db.media.update_one({"id": media["id"]}, {"$set": updates})

    except Exception as e:
        logger.error(f"Error in extract_and_update_metadata_for_all: {e}")

async def cleanup_duplicate_pages_over_1hr(db):
    """
    Automatically delete duplicate pages that have existed for more than 1 hour without groups.
    """
    try:
        now = time.time()
        all_media = await db.get_all_media(limit=10000)

        pages_by_base = {}
        for m in all_media:
            title = m.get("title", "")
            base = get_base_title(title)
            if base not in pages_by_base:
                pages_by_base[base] = []
            pages_by_base[base].append(m)

        deleted_count = 0
        for base, group in pages_by_base.items():
            if len(group) <= 1:
                continue

            # Sort group by created_at (earliest first) to preserve original page
            group.sort(key=lambda x: x.get("created_at", 0))

            # Leave primary page group[0], check subsequent duplicate copies
            duplicates = group[1:]
            for dup in duplicates:
                seasons_links = dup.get("seasons_links")
                has_groups = bool(seasons_links) and len(seasons_links) > 0
                created_at = dup.get("created_at", 0)
                age = now - created_at

                if not has_groups and age > 3600:
                    slug = dup.get("slug")
                    logger.info(f"Purging duplicate page without groups (>1hr old): '{dup.get('title')}' (slug: {slug})")
                    await db.delete_media_by_slug(slug)
                    deleted_count += 1

        if deleted_count > 0:
            logger.info(f"Successfully cleaned up {deleted_count} duplicate pages without groups (>1hr old).")

    except Exception as e:
        logger.error(f"Error in cleanup_duplicate_pages_over_1hr: {e}")

async def start_maintenance_tasks(db):
    """Run initial post-redeploy maintenance and schedule periodic loop."""
    await extract_and_update_metadata_for_all(db)
    await cleanup_duplicate_pages_over_1hr(db)

    # Periodic background loop every 15 minutes
    while True:
        await asyncio.sleep(900)
        await cleanup_duplicate_pages_over_1hr(db)
