from pyrogram.enums import ChatMemberStatus
from core.logger import logger

class PermissionChecker:
    @staticmethod
    async def is_admin(client, chat_id, user_id=None):
        """
        Checks if the client (or a specific user_id) is an administrator in the given chat.
        """
        try:
            if user_id is None:
                me = await client.get_me()
                user_id = me.id

            member = await client.get_chat_member(chat_id, user_id)
            return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
        except Exception as e:
            logger.error(f"Error checking admin permissions for {user_id} in {chat_id}: {e}")
            return False

    @staticmethod
    async def can_send_messages(client, chat_id):
        """
        Checks if the client has permission to send messages in the chat.
        """
        try:
            # We can't always check permissions directly without being admin,
            # so we try a test message or check member status.
            member = await client.get_chat_member(chat_id, "me")
            if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                return True
            # For public channels/groups, restricted might apply
            return not member.privileges or member.privileges.can_post_messages
        except Exception:
            return False

permission_checker = PermissionChecker()
