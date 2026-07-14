import asyncio
import pytest

from app.models import UploadJob
from app.queue_manager import QueueManager


def job(mid):
    return UploadJob(job_key=f"1:{mid}", chat_id=1, message_id=mid, sender_id=1, filename="x")


async def test_capacity_and_duplicate():
    queue = QueueManager(1)
    await queue.add(job(1))
    with pytest.raises(asyncio.QueueFull): await queue.add(job(2))
    with pytest.raises(ValueError): await queue.add(job(1))

