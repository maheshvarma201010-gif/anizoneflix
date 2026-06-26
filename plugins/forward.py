import asyncio
from pyrogram import Client, filters
from bot import is_authorized, user_state
from core.session import session_manager
from core.forward_engine import ForwardEngine, active_tasks
from core.peer_manager import peer_manager

@Client.on_message(filters.command("forward") & filters.private)
async def forward_cmd(client, message):
    if not await is_authorized(message.from_user.id):
        return await message.reply("🚫 **Unauthorized.**")

    ubot = await session_manager.get_client()
    if not ubot:
        return await message.reply("❌ **Not Logged In.** Use /login to authorize your user account first.")

    user_state[message.from_user.id] = {"action": "fwd_start_link"}
    await message.reply("📥 **Forwarding Wizard**\n\nPlease send the **FIRST** message link:")

async def forward_wizard(client, message, state):
    uid = message.from_user.id
    action = state.get("action")
    ubot = await session_manager.get_client()

    if action == "fwd_start_link":
        try:
            parts = message.text.strip().split("/")
            chat_id = parts[-2]
            msg_id = int(parts[-1])
            user_state[uid].update({"action": "fwd_end_link", "from_chat": chat_id, "start_id": msg_id})
            await message.reply("📤 **Send the LAST message link:**")
        except:
            await message.reply("❌ **Invalid Link.** Send a valid Telegram message link:")

    elif action == "fwd_end_link":
        try:
            msg_id = int(message.text.strip().split("/")[-1])
            user_state[uid].update({"action": "fwd_target", "end_id": msg_id})
            await message.reply("🎯 **Send the TARGET channel username or ID:**")
        except:
            await message.reply("❌ **Invalid Link.** Send a valid Telegram message link:")

    elif action == "fwd_target":
        target = message.text.strip()
        try:
            # Resolve & Verify
            target_peer = await peer_manager.resolve_peer(ubot, target)
            if not target_peer:
                return await message.reply("❌ **Target Not Found.** Ensure the userbot is a member/admin of the channel.")

            source_peer = await peer_manager.resolve_peer(ubot, state["from_chat"])

            # Permission Test
            try:
                test = await ubot.send_message(target_peer["id"], "🔄 **System Initializing...**")
                await test.delete()
            except Exception as pe:
                return await message.reply(f"❌ **Permission Denied:** Userbot cannot post to target. Error: {pe}")

            task = ForwardEngine(uid, source_peer["id"], target_peer["id"], state["start_id"], state["end_id"])
            active_tasks[uid] = task

            prog_msg = await message.reply("🚀 **Forwarding Process Initialized.** Status updates every 5 messages.")

            async def update_ui(stats, progress):
                try:
                    await prog_msg.edit(
                        f"🔄 **Forwarding in Progress...**\n\n"
                        f"📦 `{progress['processed']} / {stats['total']}`\n"
                        f"📊 `{progress['percentage']}%` | ETA: `{progress['eta']}`"
                    )
                except: pass

            async def run_task():
                res = await task.run(ubot, update_ui)
                summary = (
                    f"✅ **Forward Completed**\n\n"
                    f"📊 **Final Stats:**\n"
                    f"• Success: `{res['success']}`\n"
                    f"• Failed: `{res['failed']}`\n"
                    f"• Skipped: `{res['skipped']}`"
                )
                await client.send_message(uid, summary)
                active_tasks.pop(uid, None)

            asyncio.create_task(run_task())
            user_state.pop(uid, None)

        except Exception as e:
            await message.reply(f"❌ **Wizard Error:** {e}")
