from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from .config import Settings
from .exceptions import InsufficientDiskSpace
from .models import UploadJob
from .utils import sanitize_filename


class FileService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def prepare(self, job: UploadJob) -> Path:
        maximum = int(self.settings.max_file_size_gb * 1024**3)
        if maximum and job.file_size > maximum:
            raise InsufficientDiskSpace("File exceeds configured MAX_FILE_SIZE_GB")
        usage = await asyncio.to_thread(shutil.disk_usage, self.settings.download_dir)
        reserve = int(self.settings.min_free_disk_gb * 1024**3)
        if usage.free < job.file_size + reserve:
            raise InsufficientDiskSpace("Insufficient disk space for download plus configured reserve")
        directory = self.settings.download_dir / f"{job.chat_id}_{job.message_id}"
        await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
        path = directory / sanitize_filename(job.filename, f"file_{job.message_id}")
        if path.resolve().parent != directory.resolve():
            raise ValueError("Unsafe local path")
        job.local_path = str(path)
        return path

    async def remove_job_directory(self, job: UploadJob) -> None:
        if job.directory and job.directory.exists():
            await asyncio.to_thread(shutil.rmtree, job.directory, True)

