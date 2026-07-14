from __future__ import annotations

import asyncio
from datetime import timezone

from telethon import events

from .command_service import CommandService
from .config import Settings
from .directory_service import DirectoryService
from .models import JobStatus, UploadJob
from .queue_manager import QueueManager
from .state_store import StateStore
from .utils import fallback_filename, format_bytes, sanitize_filename


def register_handlers(client: object, settings: Settings, queue: QueueManager, state: StateStore, commands: CommandService, directories: DirectoryService, self_id: int) -> None:
    completed: set[str] = set()

    async def initialize() -> None:
        completed.update(k for k, j in (await state.load_all()).items() if j.status == JobStatus.COMPLETED)

    asyncio.create_task(initialize())

    @client.on(events.NewMessage)
    async def on_message(event: object) -> None:
        expected_chat = self_id if settings.watch_mode == "saved_messages" else settings.watch_chat_id
        if event.chat_id != expected_chat:
            return
        sender_id = event.sender_id or 0
        if not settings.is_authorized(sender_id, self_id):
            await event.reply("You are not authorized to use this uploader.")
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
        upload_directory = await directories.get_current_directory()
        job = UploadJob(job_key=key, chat_id=event.chat_id, message_id=event.message.id, sender_id=sender_id, filename=filename, file_size=size, upload_directory=upload_directory, media_group_id=str(event.message.grouped_id) if event.message.grouped_id else None)
        if queue.queue.full():
            await event.reply("Upload queue is full. Please retry later.")
            return
        # Create and persist the status message before exposing the job to a
        # worker. Otherwise a fast worker can start with no message ID and all
        # early progress edits are lost.
        position = queue.queue.qsize() + 1
        destination = directories.build_destination_directory(upload_directory)
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
