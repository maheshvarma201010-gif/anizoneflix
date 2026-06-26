from pyrogram import Client, filters
from bot import is_authorized
import aiohttp
import logging

logger = logging.getLogger("REDIRECT")

@Client.on_message(filters.command("redirect") & filters.private)
async def redirect_cmd(client, message):
    if not await is_authorized(message.from_user.id):
        return await message.reply("🚫 **Unauthorized.**")

    urls = []
    if len(message.command) > 1:
        urls.extend(message.text.split(None, 1)[1].split())

    if message.reply_to_message:
        reply = message.reply_to_message
        text = reply.text or reply.caption or ""
        if text:
            import re
            urls.extend(re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[himBHs_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text))

    if not urls:
        return await message.reply("💡 **Usage:** `/redirect <url>` or reply to a list of links.")

    status = await message.reply(f"🔍 **Tracing {len(urls)} URLs...**")
    results = []

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        for url in urls[:50]:
            try:
                async with session.get(url, allow_redirects=True) as resp:
                    results.append(f"original link: `{url}`\nFinal link : `{resp.url}`")
            except Exception as e:
                results.append(f"original link: `{url}`\nError : `{str(e)}`")

    await status.edit("\n\n".join(results) if results else "❌ No valid URLs traced.")
