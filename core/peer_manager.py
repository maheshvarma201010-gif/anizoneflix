import asyncio
from core.logger import bot_logger
from database.db import db

class PeerManager:
    def __init__(self):
        self._cache = {}

    async def resolve_peer(self, client, peer_id):
        # 1. Memory Cache
        if peer_id in self._cache:
            return self._cache[peer_id]

        # 2. Database Cache
        cached = await db.get_cached_peer(str(peer_id))
        if cached:
            self._cache[peer_id] = cached["peer"]
            return cached["peer"]

        # 3. Live Resolution
        try:
            chat = await client.get_chat(peer_id)
            peer_data = {"id": chat.id, "username": chat.username, "type": str(chat.type)}
            await db.cache_peer(str(peer_id), {"peer": peer_data})
            self._cache[peer_id] = peer_data
            return peer_data
        except Exception as e:
            bot_logger.error(f"Peer resolution failed for {peer_id}: {e}")
            return None

peer_manager = PeerManager()
