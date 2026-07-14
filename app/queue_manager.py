from __future__ import annotations

import asyncio
from collections import OrderedDict

from .models import UploadJob


class QueueManager:
    def __init__(self, max_size: int):
        self.queue: asyncio.Queue[UploadJob] = asyncio.Queue(maxsize=max_size)
        self.pending: OrderedDict[str, UploadJob] = OrderedDict()
        self.active: dict[str, UploadJob] = {}
        self.cancel_events: dict[str, asyncio.Event] = {}

    async def add(self, job: UploadJob) -> int:
        if job.job_key in self.pending or job.job_key in self.active:
            raise ValueError("Job is already queued")
        self.queue.put_nowait(job)
        self.pending[job.job_key] = job
        self.cancel_events[job.job_key] = asyncio.Event()
        return self.queue.qsize()

    async def get(self) -> UploadJob:
        job = await self.queue.get()
        self.pending.pop(job.job_key, None)
        self.active[job.job_key] = job
        return job

    def finish(self, job: UploadJob) -> None:
        self.active.pop(job.job_key, None)
        self.cancel_events.pop(job.job_key, None)
        self.queue.task_done()

    def request_cancel(self, job_key: str) -> bool:
        event = self.cancel_events.get(job_key)
        if not event:
            return False
        event.set()
        return True

    def is_cancelled(self, job_key: str) -> bool:
        return self.cancel_events.get(job_key, asyncio.Event()).is_set()

    def snapshot(self) -> list[UploadJob]:
        return list(self.pending.values())

