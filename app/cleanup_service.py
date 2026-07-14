from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import timedelta

from .config import Settings
from .models import JobStatus, utcnow
from .queue_manager import QueueManager
from .state_store import StateStore

LOG = logging.getLogger(__name__)


class CleanupService:
    def __init__(self, settings: Settings, state: StateStore, queue: QueueManager):
        self.settings, self.state, self.queue = settings, state, queue

    def should_delete(self, status: JobStatus, completed_at) -> bool:
        return status in {JobStatus.FAILED, JobStatus.CANCELLED} and completed_at is not None and utcnow() - completed_at >= timedelta(hours=self.settings.failed_file_retention_hours)

    async def run_once(self) -> None:
        jobs = await self.state.load_all()
        active = set(self.queue.active)
        for job in jobs.values():
            if job.job_key in active or not job.directory or not job.directory.exists():
                continue
            delete = job.status == JobStatus.COMPLETED and self.settings.delete_local_after_success
            delete = delete or self.should_delete(job.status, job.completed_at)
            if delete:
                LOG.info("Cleanup deleting %s", job.directory)
                await asyncio.to_thread(shutil.rmtree, job.directory, True)
        for path in self.settings.download_dir.iterdir():
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.settings.cleanup_interval_minutes * 60)
            try:
                await self.run_once()
            except Exception:
                LOG.exception("Cleanup pass failed")

