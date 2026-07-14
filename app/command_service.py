from __future__ import annotations

import shutil

from .config import Settings
from .directory_service import DirectoryService
from .models import JobStatus
from .queue_manager import QueueManager
from .state_store import StateStore
from .utils import format_bytes, format_duration


class CommandService:
    def __init__(self, settings: Settings, queue: QueueManager, state: StateStore, directories: DirectoryService):
        self.settings, self.queue, self.state, self.directories = settings, queue, state, directories

    async def handle(self, event: object) -> None:
        text = event.raw_text.strip()
        command, *args = text.split(maxsplit=1)
        if command == ".help":
            response = ".status - active transfer\n.queue - pending jobs\n.dir <name> - Set the upload directory for new files\n.dir - Show the current upload directory\n.dir default - Reset to the default directory\n.cancel [message_id] - cancel a job\n.retry <message_id> - retry failed job\n.config - safe configuration\n.help - this help"
        elif command == ".dir":
            current = await self.directories.get_current_directory()
            destination = self.directories.build_destination_directory(current)
            if not args:
                response = f"Current upload directory: {current}\nDestination: {destination}"
            elif args[0].strip().lower() in {"default", "reset"}:
                current = await self.directories.reset_directory(event.sender_id or 0)
                response = f"Upload directory reset\n\nCurrent directory: {current}\nDestination: {self.directories.build_destination_directory(current)}"
            else:
                try:
                    current = await self.directories.set_directory(args[0], event.sender_id or 0)
                    response = f"Upload directory changed\n\nCurrent directory: {current}\nDestination: {self.directories.build_destination_directory(current)}"
                except ValueError:
                    response = "Invalid directory name.\nUse only letters, numbers, spaces, hyphens, and underscores."
        elif command == ".status":
            active = next(iter(self.queue.active.values()), None)
            free = shutil.disk_usage(self.settings.download_dir).free
            current = await self.directories.get_current_directory()
            current_line = f"Current default directory: {current}"
            response = f"Active: {active.filename}\nPhase: {active.status}\nProgress: {active.progress_percent:.1f}%\nSpeed: {format_bytes(active.speed_bytes_per_second)}/s\nETA: {format_duration(active.eta_seconds)}\n{current_line}\nActive job directory: {active.upload_directory}\nDestination: {active.remote_path or self.settings.rclone_remote + ':' + self.directories.build_destination_directory(active.upload_directory) + '/' + active.filename}\nQueue: {self.queue.queue.qsize()}\nDisk free: {format_bytes(free)}" if active else f"Active: none\n{current_line}\nDestination: {self.directories.build_destination_directory(current)}\nQueue: {self.queue.queue.qsize()}\nDisk free: {format_bytes(free)}\nRemote: {self.settings.rclone_remote}:"
        elif command == ".queue":
            rows = [f"{i}. {j.filename}\n   Size: {format_bytes(j.file_size)}\n   Directory: {j.upload_directory}\n   Message ID: {j.message_id}" for i, j in enumerate(self.queue.snapshot(), 1)]
            response = "Pending jobs:\n" + ("\n".join(rows) if rows else "none")
        elif command == ".cancel":
            target = args[0] if args else None
            jobs = list(self.queue.active.values()) + self.queue.snapshot()
            job = next((j for j in jobs if target is None or str(j.message_id) == target), None)
            response = "Cancellation requested." if job and self.queue.request_cancel(job.job_key) else "Job not found."
        elif command == ".retry" and args:
            jobs = await self.state.load_all()
            job = next((j for j in jobs.values() if str(j.message_id) == args[0] and j.status in {JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.RECOVERABLE}), None)
            if job:
                job.status, job.error_message = JobStatus.QUEUED, None
                await self.state.save(job)
                await self.queue.add(job)
                response = "Job queued for retry."
            else:
                response = "Retryable job not found."
        elif command == ".config":
            current = await self.directories.get_current_directory()
            response = f"Configuration:\nRoot path: {self.settings.rclone_base_path}\nDefault directory: {self.settings.default_upload_directory}\nCurrent directory: {current}\nRemote: {self.settings.rclone_remote}\nCollision policy: {self.settings.remote_collision_policy}"
        else:
            return
        await event.reply(response[:4000])
