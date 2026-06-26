import asyncio
from pyrogram.errors import FloodWait, PeerIdInvalid, ChannelInvalid
from core.logger import logger

class PeerManager:
    def __init__(self):
        self.cache = {} # username/ID -> peer_id

    async def resolve_peer(self, client, peer_id):
        """
        Resolves a username or ID to a Peer ID with caching and retry logic.
        """
        if peer_id in self.cache:
            return self.cache[peer_id]

        for attempt in range(3):
            try:
                peer = await client.get_chat(peer_id)
                self.cache[peer_id] = peer.id
                return peer.id
            except FloodWait as e:
                logger.warning(f"FloodWait while resolving peer {peer_id}: {e.value}s")
                await asyncio.sleep(e.value)
            except (PeerIdInvalid, ChannelInvalid) as e:
                logger.error(f"Invalid peer {peer_id}: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error resolving peer {peer_id}: {e}")
                await asyncio.sleep(attempt + 1)

        return peer_id # Fallback to original

peer_manager = PeerManager()
