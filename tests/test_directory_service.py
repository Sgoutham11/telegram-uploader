import json

import pytest

from app.directory_service import DirectoryService
from app.models import UploadJob
from app.queue_manager import QueueManager


async def test_default_set_reset_and_persistence(tmp_path):
    service = DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS")
    await service.load()
    assert await service.get_current_directory() == "DOWNLOADS"
    assert service.build_destination_directory("DOWNLOADS") == "UPLOADS/DOWNLOADS"
    assert await service.set_directory("  My Downloads  ", 123) == "My Downloads"
    payload = json.loads((tmp_path / "current_directory.json").read_text())
    assert payload["directory"] == "My Downloads"
    assert payload["updated_by"] == 123
    assert payload["updated_at"].endswith("Z")
    assert not list(tmp_path.glob("*.tmp"))
    restarted = DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS")
    await restarted.load()
    assert await restarted.get_current_directory() == "My Downloads"
    assert restarted.build_destination_directory("My Downloads") == "UPLOADS/My Downloads"
    assert await restarted.reset_directory(123) == "DOWNLOADS"


async def test_corrupt_state_falls_back_to_default(tmp_path):
    (tmp_path / "current_directory.json").write_text("{broken")
    service = DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS")
    await service.load()
    assert await service.get_current_directory() == "DOWNLOADS"


async def test_queued_job_retains_directory_snapshot(tmp_path):
    service = DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS")
    await service.load()
    await service.set_directory("Movies", 1)
    queue = QueueManager(5)
    job = UploadJob(job_key="1:1", chat_id=1, message_id=1, sender_id=1, filename="a.mkv", upload_directory=await service.get_current_directory())
    await queue.add(job)
    await service.set_directory("Series", 1)
    assert queue.snapshot()[0].upload_directory == "Movies"
    assert await service.get_current_directory() == "Series"


@pytest.mark.parametrize("name", ["goutham", "Movies", "My Downloads", "telegram_backup", "films-2026"])
def test_valid_directory_names(tmp_path, name):
    assert DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS").validate_directory_name(name) == name


@pytest.mark.parametrize("name", ["", ".", "..", "../secret", "/root", "a/b", "a\\b", "${HOME}", "movie;rm -rf", "x" * 101, "bad\x00name"])
def test_unsafe_directory_names_are_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS").validate_directory_name(name)
