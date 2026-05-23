import math
import asyncio
import json
import tempfile
import os
import logging
import traceback
import subprocess
from typing import Optional, List, AsyncGenerator
from telethon import TelegramClient
from fastapi import Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger("ANIZONEFLIX_STREAMER")

# --- CORE STREAMING ENGINE ---

async def ultra_high_speed_streamer(clients: List[TelegramClient], file, start: int, end: int, chunk_size: int = 1024 * 1024) -> AsyncGenerator[bytes, None]:
    """
    Multi-session parallel streamer from FileToLink.
    Distributes chunk requests across multiple Telethon sessions.
    """
    total_to_send = end - start + 1
    bytes_sent = 0
    session_count = len(clients)

    if session_count == 1:
        logger.info("Single Telethon session. Using sequential stream.")
        try:
            async for chunk in clients[0].iter_download(file, offset=start, limit=total_to_send, request_size=chunk_size):
                if not chunk: continue
                yield bytes(chunk)
                bytes_sent += len(chunk)
            return
        except Exception as e:
            logger.error(f"Sequential stream failed: {e}. Falling back to parallel.")

    # Parallel Logic
    concurrency_per_session = 8
    total_concurrency = concurrency_per_session * session_count
    offsets = list(range(start, end + 1, chunk_size))
    chunk_queue = asyncio.Queue()

    for offset in offsets:
        remaining = end - offset + 1
        current_chunk_size = min(chunk_size, remaining)
        chunk_queue.put_nowait((offset, current_chunk_size))

    received_chunks = {}
    completion_event = asyncio.Event()

    async def fetch_worker(client: TelegramClient, worker_id: int):
        while True:
            try:
                offset, size = chunk_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            success = False
            for attempt in range(3):
                try:
                    chunk = b""
                    async for part in client.iter_download(file, offset=offset, limit=size):
                        chunk += part
                    if len(chunk) > 0:
                        received_chunks[offset] = chunk
                        chunk_queue.task_done()
                        completion_event.set()
                        success = True
                        break
                except Exception as e:
                    await asyncio.sleep((attempt + 1) * 1)

            if not success:
                chunk_queue.put_nowait((offset, size))
                await asyncio.sleep(2)

    workers = [asyncio.create_task(fetch_worker(clients[i % session_count], i)) for i in range(total_concurrency)]

    next_offset = start
    while bytes_sent < total_to_send:
        if next_offset in received_chunks:
            chunk = received_chunks.pop(next_offset)
            if bytes_sent + len(chunk) > total_to_send:
                chunk = chunk[:total_to_send - bytes_sent]
            yield bytes(chunk)
            bytes_sent += len(chunk)
            next_offset += len(chunk)
        else:
            completion_event.clear()
            try:
                await asyncio.wait_for(completion_event.wait(), timeout=20.0)
            except asyncio.TimeoutError:
                if bytes_sent >= total_to_send: break
                if all(w.done() for w in workers): break

    for w in workers: w.cancel()

# --- FFmpeg REMUX ENGINE ---

async def remux_streamer(client: TelegramClient, file, file_size: int, audio_track: int = 0) -> AsyncGenerator[bytes, None]:
    """
    On-the-fly remuxing to select specific audio tracks using FFmpeg.
    """
    ffmpeg_cmd = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error',
        '-i', 'pipe:0',
        '-map', '0:v:0', '-map', f'0:a:{audio_track}',
        '-c', 'copy',
        '-f', 'mp4', '-movflags', 'frag_keyframe+empty_moov+default_base_moof',
        'pipe:1'
    ]

    process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    async def feed_ffmpeg():
        try:
            async for chunk in client.iter_download(file, offset=0, limit=file_size):
                if not chunk or process.poll() is not None: break
                await asyncio.to_thread(process.stdin.write, bytes(chunk))
        except Exception as e:
            logger.error(f"FFmpeg feed error: {e}")
        finally:
            try: process.stdin.close()
            except: pass

    feed_task = asyncio.create_task(feed_ffmpeg())

    try:
        while True:
            chunk = await asyncio.to_thread(process.stdout.read, 256 * 1024)
            if not chunk: break
            yield chunk
    finally:
        await feed_task
        if process.poll() is None:
            process.kill()
            process.wait()

# --- PROBE ENGINE ---

async def probe_tracks(client: TelegramClient, file, file_size: int) -> dict:
    """
    Downloads header and uses ffprobe to identify tracks.
    """
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix=".mkv")
        os.close(fd)

        probe_size = min(5 * 1024 * 1024, file_size)
        downloaded = 0

        with open(temp_path, 'wb') as f:
            async for chunk in client.iter_download(file, offset=0, request_size=512*1024):
                f.write(bytes(chunk))
                downloaded += len(chunk)
                if downloaded >= probe_size: break

        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', '-show_format', temp_path]
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True)

        if result.returncode != 0:
            return {"audio_tracks": [], "has_multiple_audio": False}

        probe_data = json.loads(result.stdout.decode(errors='replace'))
        audio_tracks = []
        a_idx = 0

        for s in probe_data.get('streams', []):
            if s.get('codec_type') == 'audio':
                tags = s.get('tags', {})
                lang = tags.get('language', 'und')
                title = tags.get('title', '')
                codec = s.get('codec_name', '').upper()
                label = f"{lang.upper()} {title} ({codec})"
                audio_tracks.append({"index": s.get('index'), "audio_index": a_idx, "label": label})
                a_idx += 1

        return {
            "audio_tracks": audio_tracks,
            "has_multiple_audio": len(audio_tracks) > 1
        }
    except Exception as e:
        logger.error(f"Probe failed: {e}")
        return {"audio_tracks": [], "has_multiple_audio": False}
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
