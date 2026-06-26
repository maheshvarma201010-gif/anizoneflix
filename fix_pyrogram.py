import pyrogram.utils
import logging

# Patch Pyrogram's internal range check for modern Channel IDs
pyrogram.utils.MIN_CHANNEL_ID = -1002500000000 # Just an example, let's go even lower
pyrogram.utils.MIN_CHANNEL_ID = -1009999999999

print(f"Patched MIN_CHANNEL_ID to: {pyrogram.utils.MIN_CHANNEL_ID}")

try:
    print(f"Test resolution: {pyrogram.utils.get_peer_type(-1002561623965)}")
except Exception as e:
    print(f"Error: {e}")
