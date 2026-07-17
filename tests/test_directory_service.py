import json

import pytest

from app.directory_service import DirectoryService
from app.models import UploadJob
from app.queue_manager import QueueManager


USERS = {111: "GOUTHAM", 222: "GALAXY"}


async def test_per_user_default_set_reset_and_persistence(tmp_path):
    service = DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS", USERS)
    await service.load()
    assert await service.get_user_current_directory(111) == "DOWNLOADS"
    assert await service.get_user_current_directory(222) == "DOWNLOADS"
    assert service.build_destination_directory(111, "DOWNLOADS") == "UPLOADS/GOUTHAM/DOWNLOADS"

    assert await service.set_user_current_directory(111, " Series / Friends ") == "Series/Friends"
    assert await service.set_user_current_directory(222, "Anime") == "Anime"
    payload = json.loads((tmp_path / "user_directories.json").read_text())
    assert payload["111"]["username"] == "GOUTHAM"
    assert payload["111"]["current_directory"] == "Series/Friends"
    assert payload["222"]["current_directory"] == "Anime"
    assert payload["111"]["updated_at"].endswith("Z")
    assert not list(tmp_path.glob("*.tmp"))

    restarted = DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS", USERS)
    await restarted.load()
    assert await restarted.get_user_current_directory(111) == "Series/Friends"
    assert await restarted.get_user_current_directory(222) == "Anime"
    assert await restarted.reset_user_current_directory(111) == "DOWNLOADS"
    assert await restarted.get_user_current_directory(222) == "Anime"


async def test_corrupt_state_falls_back_to_each_users_default(tmp_path):
    (tmp_path / "user_directories.json").write_text("{broken")
    service = DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS", USERS)
    await service.load()
    assert await service.get_user_current_directory(111) == "DOWNLOADS"
    assert await service.get_user_current_directory(222) == "DOWNLOADS"


async def test_queued_job_retains_user_and_directory_snapshot(tmp_path):
    service = DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS", USERS)
    await service.load()
    await service.set_user_current_directory(111, "Movies")
    queue = QueueManager(5)
    job = UploadJob(
        job_key="1:1",
        chat_id=1,
        message_id=1,
        sender_id=111,
        filename="a.mkv",
        upload_username=service.get_allowed_username(111),
        upload_directory=await service.get_user_current_directory(111),
    )
    await queue.add(job)
    await service.set_user_current_directory(111, "Series")
    assert queue.snapshot()[0].upload_username == "GOUTHAM"
    assert queue.snapshot()[0].upload_directory == "Movies"
    assert queue.snapshot()[0].remote_directory == "GOUTHAM/Movies"
    assert await service.get_user_current_directory(111) == "Series"


async def test_build_upload_path_uses_configured_name_and_user_directory(tmp_path):
    service = DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS", USERS)
    await service.load()
    await service.set_user_current_directory(111, "Series/Friends")
    assert await service.build_upload_path(111, "episode01.mkv") == "UPLOADS/GOUTHAM/Series/Friends/episode01.mkv"


def test_unknown_user_is_rejected(tmp_path):
    service = DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS", USERS)
    with pytest.raises(PermissionError):
        service.get_allowed_username(999)


@pytest.mark.parametrize("name", ["goutham", "Movies", "My Downloads", "telegram_backup", "films-2026", "Series/Friends"])
def test_valid_directory_names(tmp_path, name):
    assert DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS", USERS).validate_directory_name(name) == name


@pytest.mark.parametrize("name", ["", ".", "..", "../secret", "/root", "Series//Friends", "a\\b", "${HOME}", "movie;rm -rf", "x" * 101, "bad\x00name"])
def test_unsafe_directory_names_are_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        DirectoryService(tmp_path, "UPLOADS", "DOWNLOADS", USERS).validate_directory_name(name)
