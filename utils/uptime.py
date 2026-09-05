import asyncio
import aiohttp
import time
import logging

logger = logging.getLogger("MZ_UPTIME")

async def ping_target(session, bot):
    url = bot.get("url")
    if not url: return
    t0 = time.time()
    status = "offline"
    latency = 0
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            latency = round((time.time() - t0) * 1000, 1)
            if resp.status < 500:
                status = "online"
            else:
                status = "degraded"
    except Exception as e:
        status = "offline"

    bot["status"] = status
    bot["latency"] = latency
    bot["last_checked"] = time.time()

async def run_uptime_monitor_loop(db):
    """
    24/7 Uptime Monitor Worker that pings all registered URLs every 1 second.
    """
    logger.info("24/7 Uptime Monitor Service active (monitoring every 1s)...")
    connector = aiohttp.TCPConnector(limit=100)
    async with aiohttp.ClientSession(connector=connector, headers={"User-Agent": "MoviesZoneFlix-UptimeMonitor/1.0"}) as session:
        while True:
            try:
                bots = await db.get_all_uptime_bots()
                if bots:
                    tasks = [ping_target(session, b) for b in bots]
                    await asyncio.gather(*tasks, return_exceptions=True)

                    # Persist status updates to DB
                    for b in bots:
                        await db.update_uptime_bot(b["id"], {
                            "status": b.get("status", "offline"),
                            "latency": b.get("latency", 0),
                            "last_checked": b.get("last_checked", time.time())
                        })
            except Exception as e:
                logger.error(f"Uptime Monitor Loop Error: {e}")

            await asyncio.sleep(1)
