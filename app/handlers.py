from __future__ import annotations

import asyncio
import logging
from datetime import timezone

from telethon import events

from .command_service import CommandService
from .config import Settings
from .directory_service import DirectoryService
from .models import JobStatus, UploadJob
from .queue_manager import QueueManager
from .state_store import StateStore
from .utils import fallback_filename, format_bytes, sanitize_filename

LOG = logging.getLogger(__name__)


def _display_name(entity: object | None) -> str:
    if entity is None:
        return "N/A"
    title = getattr(entity, "title", None)
    if title:
        return str(title)
    name = " ".join(filter(None, (getattr(entity, "first_name", None), getattr(entity, "last_name", None)))).strip()
    return name or "N/A"


def _message_type(message: object) -> str:
    if getattr(message, "document", None) is not None:
        return "document"
    if getattr(message, "photo", None) is not None:
        return "photo"
    media = getattr(message, "media", None)
    if media is None:
        return "text"
    name = media.__class__.__name__
    return name.removeprefix("MessageMedia").lower() or "media"


async def log_debug_telegram_ids(event: object) -> None:
    """Log setup identifiers without allowing lookup failures to affect handling."""
    chat = sender = None
    try:
        getter = getattr(event, "get_chat", None)
        if getter:
            chat = await getter()
    except Exception:
        LOG.debug("Unable to fetch chat details for Telegram ID debugging", exc_info=True)
    try:
        getter = getattr(event, "get_sender", None)
        if getter:
            sender = await getter()
    except Exception:
        LOG.debug("Unable to fetch sender details for Telegram ID debugging", exc_info=True)

    if getattr(event, "is_channel", False) and getattr(event, "is_group", False):
        chat_type = "supergroup"
    elif getattr(event, "is_group", False):
        chat_type = "group"
    elif getattr(event, "is_channel", False):
        chat_type = "channel"
    elif getattr(event, "is_private", False):
        chat_type = "private"
    else:
        chat_type = "N/A"

    username = getattr(sender, "username", None)
    message = getattr(event, "message", None)
    raw_text = getattr(event, "raw_text", None) or getattr(message, "message", None) or "N/A"
    text = str(raw_text).replace("\r", " ").replace("\n", " ")[:500]
    LOG.info(
        "==================================================\n"
        "Telegram Debug Information\n"
        "--------------------------------------------------\n"
        "Chat ID      : %s\n"
        "Chat Name    : %s\n"
        "Chat Type    : %s\n\n"
        "Sender ID    : %s\n"
        "Sender Name  : %s\n"
        "Username     : %s\n\n"
        "Message Type : %s\n"
        "Message Text : %s\n"
        "==================================================",
        getattr(event, "chat_id", None) or "N/A",
        _display_name(chat),
        chat_type,
        getattr(event, "sender_id", None) or getattr(sender, "id", None) or "N/A",
        _display_name(sender),
        f"@{username}" if username else "N/A",
        _message_type(message) if message is not None else "N/A",
        text,
    )


def register_handlers(client: object, settings: Settings, queue: QueueManager, state: StateStore, commands: CommandService, directories: DirectoryService, self_id: int) -> None:
    completed: set[str] = set()

    async def initialize() -> None:
        completed.update(k for k, j in (await state.load_all()).items() if j.status == JobStatus.COMPLETED)

    asyncio.create_task(initialize())

    @client.on(events.NewMessage)
    async def on_message(event: object) -> None:
        if settings.debug_telegram_ids:
            await log_debug_telegram_ids(event)
        expected_chat = self_id if settings.watch_mode == "saved_messages" else settings.watch_chat_id
        if event.chat_id != expected_chat:
            return
        sender_id = event.sender_id or 0
        if not settings.is_authorized(sender_id, self_id):
            return
        if event.raw_text.strip().startswith("."):
            await commands.handle(event)
            return
        if not event.message.media:
            return
        key = f"{event.chat_id}:{event.message.id}"
        if key in completed or key in queue.pending or key in queue.active:
            await event.reply("This Telegram message was already processed.")
            return
        file = event.message.file
        size = int(getattr(file, "size", 0) or 0)
        original = getattr(file, "name", None)
        media_type = event.message.media.__class__.__name__.lower()
        timestamp = event.message.date.astimezone(timezone.utc)
        filename = sanitize_filename(original or fallback_filename(event.message.id, media_type, timestamp, getattr(file, "mime_type", None)))
        upload_directory = await directories.get_user_current_directory(sender_id)
        upload_username = directories.get_allowed_username(sender_id)
        job = UploadJob(job_key=key, chat_id=event.chat_id, message_id=event.message.id, sender_id=sender_id, filename=filename, file_size=size, upload_username=upload_username, upload_directory=upload_directory, media_group_id=str(event.message.grouped_id) if event.message.grouped_id else None)
        if queue.queue.full():
            await event.reply("Upload queue is full. Please retry later.")
            return
        # Create and persist the status message before exposing the job to a
        # worker. Otherwise a fast worker can start with no message ID and all
        # early progress edits are lost.
        position = queue.queue.qsize() + 1
        destination = directories.build_destination_directory(sender_id, upload_directory)
        status = await event.reply(f"Queued\n\nFile: {filename}\nSize: {format_bytes(size)}\nDirectory: {upload_directory}\nDestination: {destination}\nPosition: {position}")
        job.status_message_id = status.id
        await state.save(job)
        try:
            await queue.add(job)
        except asyncio.QueueFull:
            job.status = JobStatus.FAILED
            job.error_message = "Upload queue became full before the job could be accepted"
            await state.save(job)
            try:
                await status.edit("Upload queue is full. Please retry later.")
            except Exception:
                await event.reply("Upload queue is full. Please retry later.")
