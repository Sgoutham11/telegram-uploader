import pytest
from pydantic import ValidationError

from app.config import Settings


BASE = {"TELEGRAM_API_ID": "123", "TELEGRAM_API_HASH": "hash"}


def test_environment_parsing(monkeypatch):
    for key, value in BASE.items(): monkeypatch.setenv(key, value)
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2")
    monkeypatch.setenv("DELETE_LOCAL_AFTER_SUCCESS", "false")
    monkeypatch.setenv("TELEGRAM_DOWNLOAD_CONNECTIONS", "6")
    settings = Settings(_env_file=None)
    assert settings.allowed_user_ids == [1, 2]
    assert settings.delete_local_after_success is False
    assert settings.telegram_download_connections == 6
    assert settings.default_upload_directory == "DOWNLOADS"
    assert settings.remote_folder_pattern == ""


def test_chat_mode_requires_id(monkeypatch):
    for key, value in BASE.items(): monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, watch_mode="chat")


def test_invalid_drive_chunk_size(monkeypatch):
    for key, value in BASE.items(): monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rclone_drive_chunk_size="--bad")


def test_upload_timeout_must_be_positive(monkeypatch):
    for key, value in BASE.items(): monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rclone_upload_timeout_minutes=0)


def test_retry_sleep_must_not_be_negative(monkeypatch):
    for key, value in BASE.items(): monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rclone_retries_sleep_seconds=-1)


def test_authorization(monkeypatch):
    for key, value in BASE.items(): monkeypatch.setenv(key, value)
    settings = Settings(_env_file=None)
    assert settings.is_authorized(9, 9)
    assert not settings.is_authorized(8, 9)


def test_low_memory_defaults(monkeypatch):
    for key, value in BASE.items(): monkeypatch.setenv(key, value)
    settings = Settings(_env_file=None)
    assert settings.max_concurrent_jobs == 1
    assert settings.telegram_download_connections == 4
    assert settings.telegram_download_stall_timeout_seconds == 120
    assert settings.rclone_transfers == 1
    assert settings.rclone_checkers == 2
    assert settings.rclone_drive_chunk_size == "64Mi"


def test_runtime_requires_writable_rclone_directory(tmp_path, monkeypatch):
    for key, value in BASE.items(): monkeypatch.setenv(key, value)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = config_dir / "rclone.conf"
    config.write_text("[gdrive]\ntype = drive\n")
    session = tmp_path / "telegram.session"
    session.write_text("session")
    monkeypatch.setattr("app.config.shutil.which", lambda _: "/usr/bin/rclone")
    settings = Settings(
        _env_file=None,
        rclone_config_path=config,
        telegram_session_path=session,
        download_dir=tmp_path / "downloads",
        state_dir=tmp_path / "state",
        log_dir=tmp_path / "logs",
        log_file=tmp_path / "logs" / "uploader.log",
    )
    settings.validate_runtime()
    assert not (config_dir / ".rclone-write-test").exists()
