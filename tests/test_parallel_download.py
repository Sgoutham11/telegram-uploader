import asyncio
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.models import UploadJob
from app.queue_manager import QueueManager
from app.worker import Worker


class FakeIterator:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.chunks)
        except StopIteration:
            raise StopAsyncIteration

    async def close(self):
        return None


class FakeClient:
    def __init__(self, source: bytes):
        self.source = source

    def iter_download(self, _media, *, offset, stride, limit, chunk_size, **_kwargs):
        chunks = []
        position = offset
        for _ in range(limit):
            if position >= len(self.source):
                break
            chunks.append(self.source[position : min(position + chunk_size, len(self.source))])
            position += stride
        return FakeIterator(chunks)


class StalledIterator:
    async def __anext__(self):
        await asyncio.Event().wait()

    async def close(self):
        return None


class StalledClient:
    def iter_download(self, *_args, **_kwargs):
        return StalledIterator()


async def test_parallel_download_writes_chunks_at_correct_offsets(tmp_path):
    chunk = 512 * 1024
    source = b"".join(bytes([index]) * chunk for index in range(7)) + b"tail"
    settings = Settings(
        _env_file=None,
        telegram_api_id=1,
        telegram_api_hash="x",
        telegram_download_connections=4,
        download_dir=tmp_path,
        state_dir=tmp_path,
        log_dir=tmp_path,
        log_file=tmp_path / "x.log",
    )
    queue = QueueManager(1)
    worker = Worker(FakeClient(source), settings, queue, None, None, None, None)
    job = UploadJob(job_key="1:2", chat_id=1, message_id=2, sender_id=1, filename="file", file_size=len(source))
    path = tmp_path / "download.bin"
    progress = []
    await worker._download_parallel(SimpleNamespace(media=object()), path, job, lambda current, total: progress.append((current, total)))
    assert path.read_bytes() == source
    assert progress[-1] == (len(source), len(source))


async def test_parallel_download_times_out_a_stalled_lane(tmp_path):
    settings = Settings(
        _env_file=None,
        telegram_api_id=1,
        telegram_api_hash="x",
        telegram_download_connections=4,
        telegram_download_stall_timeout_seconds=.01,
        download_dir=tmp_path,
        state_dir=tmp_path,
        log_dir=tmp_path,
        log_file=tmp_path / "x.log",
    )
    queue = QueueManager(1)
    worker = Worker(StalledClient(), settings, queue, None, None, None, None)
    job = UploadJob(job_key="1:3", chat_id=1, message_id=3, sender_id=1, filename="file", file_size=2 * 1024**2)

    with pytest.raises(TimeoutError, match="lane .* received no data"):
        await worker._download_parallel(SimpleNamespace(media=object()), tmp_path / "stalled.bin", job, lambda *_: None)
