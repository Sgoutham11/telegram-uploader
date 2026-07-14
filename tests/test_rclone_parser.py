from app.config import Settings
from app.rclone_service import RcloneService, parse_rclone_progress


def settings(tmp_path):
    return Settings(_env_file=None, telegram_api_id=1, telegram_api_hash="x", download_dir=tmp_path, state_dir=tmp_path, log_dir=tmp_path, log_file=tmp_path / "x.log")


def test_progress_parser():
    assert parse_rclone_progress('{"bytes":100,"speed":20.5,"eta":4}') == (100, 20.5, 4.0)
    assert parse_rclone_progress('{"level":"notice","msg":"Transferred:","stats":{"bytes":200,"speed":25,"eta":8}}') == (200, 25.0, 8.0)
    assert parse_rclone_progress('{"stats":{"bytes":4500,"speed":10,"eta":99,"transferring":[{"bytes":1400,"size":1500,"speed":8,"eta":12}]}}') == (1400, 8.0, 12.0)
    assert parse_rclone_progress('{"level":"info","msg":"ordinary log"}') is None
    assert parse_rclone_progress("noise") is None


def test_default_destination_has_no_date_folder(tmp_path):
    service = RcloneService(settings(tmp_path))
    result = service.build_remote_path("movie.mkv", "DOWNLOADS")
    assert result == "gdrive:UPLOADS/DOWNLOADS/movie.mkv"


def test_custom_destination(tmp_path):
    assert RcloneService(settings(tmp_path)).build_remote_path("movie.mkv", "goutham") == "gdrive:UPLOADS/goutham/movie.mkv"


async def test_collision_rename(tmp_path, monkeypatch):
    service = RcloneService(settings(tmp_path))
    async def exists(path): return not path.endswith("_2.mkv")
    monkeypatch.setattr(service, "remote_exists", exists)
    assert await service.resolve_collision("gdrive:folder/movie.mkv") == "gdrive:folder/movie_2.mkv"


async def test_eventual_verification_handles_delayed_drive_visibility(tmp_path, monkeypatch):
    service = RcloneService(settings(tmp_path))
    results = iter([False, False, True])
    async def verify(_job): return next(results)
    async def no_sleep(_seconds): return None
    monkeypatch.setattr(service, "verify_upload", verify)
    monkeypatch.setattr("app.rclone_service.asyncio.sleep", no_sleep)
    assert await service.verify_upload_eventually(object()) is True
