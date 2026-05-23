import asyncio
import logging
import math
from typing import Dict, Union, Any, AsyncGenerator
from pyrogram import Client, utils, raw
from pyrogram.session import Session, Auth
from pyrogram.errors import AuthBytesInvalid
from pyrogram.file_id import FileId, FileType, ThumbnailSource

logger = logging.getLogger("ANIZONEFLIX_STREAMER")

class ByteStreamer:
    def __init__(self, client: Client):
        self.client: Client = client
        self.cached_file_ids: Dict[str, FileId] = {}

    async def get_file_properties(self, file_id_str: str) -> FileId:
        if file_id_str not in self.cached_file_ids:
            file_id = FileId.decode(file_id_str)
            self.cached_file_ids[file_id_str] = file_id
        return self.cached_file_ids[file_id_str]

    async def generate_media_session(self, file_id: FileId) -> Session:
        media_session = self.client.media_sessions.get(file_id.dc_id, None)

        if media_session is None:
            if file_id.dc_id != await self.client.storage.dc_id():
                media_session = Session(
                    self.client,
                    file_id.dc_id,
                    await Auth(
                        self.client, file_id.dc_id, await self.client.storage.test_mode()
                    ).create(),
                    await self.client.storage.test_mode(),
                    is_media=True,
                )
                await media_session.start()

                for _ in range(6):
                    exported_auth = await self.client.invoke(
                        raw.functions.auth.ExportAuthorization(dc_id=file_id.dc_id)
                    )

                    try:
                        await media_session.invoke(
                            raw.functions.auth.ImportAuthorization(
                                id=exported_auth.id, bytes=exported_auth.bytes
                            )
                        )
                        break
                    except AuthBytesInvalid:
                        continue
                else:
                    await media_session.stop()
                    raise AuthBytesInvalid
            else:
                media_session = Session(
                    self.client,
                    file_id.dc_id,
                    await self.client.storage.auth_key(),
                    await self.client.storage.test_mode(),
                    is_media=True,
                )
                await media_session.start()
            self.client.media_sessions[file_id.dc_id] = media_session
        return media_session

    @staticmethod
    async def get_location(file_id: FileId) -> Union[raw.types.InputPhotoFileLocation,
                                                     raw.types.InputDocumentFileLocation,
                                                     raw.types.InputPeerPhotoFileLocation]:
        file_type = file_id.file_type

        if file_type == FileType.CHAT_PHOTO:
            if file_id.chat_id > 0:
                peer = raw.types.InputPeerUser(
                    user_id=file_id.chat_id, access_hash=file_id.chat_access_hash
                )
            else:
                if file_id.chat_access_hash == 0:
                    peer = raw.types.InputPeerChat(chat_id=-file_id.chat_id)
                else:
                    peer = raw.types.InputPeerChannel(
                        channel_id=utils.get_channel_id(file_id.chat_id),
                        access_hash=file_id.chat_access_hash,
                    )

            location = raw.types.InputPeerPhotoFileLocation(
                peer=peer,
                volume_id=file_id.volume_id,
                local_id=file_id.local_id,
                big=file_id.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG,
            )
        elif file_type == FileType.PHOTO:
            location = raw.types.InputPhotoFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size,
            )
        else:
            location = raw.types.InputDocumentFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size,
            )
        return location

    async def yield_file(
        self,
        file_id: FileId,
        offset: int,
        first_part_cut: int,
        last_part_cut: int,
        part_count: int,
        chunk_size: int,
    ) -> AsyncGenerator[bytes, None]:
        media_session = await self.generate_media_session(file_id)
        current_part = 1
        location = await self.get_location(file_id)

        try:
            r = await media_session.invoke(
                raw.functions.upload.GetFile(
                    location=location, offset=offset, limit=chunk_size
                ),
            )
            if isinstance(r, raw.types.upload.File):
                while True:
                    chunk = r.bytes
                    if not chunk:
                        break
                    elif part_count == 1:
                        yield chunk[first_part_cut:last_part_cut]
                    elif current_part == 1:
                        yield chunk[first_part_cut:]
                    elif current_part == part_count:
                        yield chunk[:last_part_cut]
                    else:
                        yield chunk

                    current_part += 1
                    offset += chunk_size

                    if current_part > part_count:
                        break

                    r = await media_session.invoke(
                        raw.functions.upload.GetFile(
                            location=location, offset=offset, limit=chunk_size
                        ),
                    )
        except (TimeoutError, AttributeError):
            pass
