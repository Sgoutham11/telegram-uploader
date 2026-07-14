from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    telegram_api_id: int
    telegram_api_hash: str
    telegram_phone: str = ""
    telegram_session_path: Path = Path("/data/session/telegram.session")
    watch_mode: Literal["saved_messages", "chat"] = "saved_messages"
    watch_chat_id: int | None = None
    allowed_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    rclone_remote: str = "gdrive"
    rclone_base_path: str = "UPLOADS"
    default_upload_directory: str = "DOWNLOADS"
    remote_folder_pattern: str = ""  # Deprecated; retained only for env compatibility.
    remote_collision_policy: Literal["rename", "overwrite", "skip"] = "rename"
    download_dir: Path = Path("/data/downloads")
    state_dir: Path = Path("/data/state")
    log_dir: Path = Path("/data/logs")
    rclone_config_path: Path = Path("/config/rclone/rclone.conf")
    max_concurrent_jobs: int = Field(1, ge=1, le=16)
    queue_max_size: int = Field(20, ge=1)
    max_file_size_gb: float = Field(0, ge=0)
    min_free_disk_gb: float = Field(5, ge=0)
    progress_update_interval_seconds: float = Field(5, ge=1)
    telegram_download_connections: int = Field(4, ge=1, le=16)
    parallel_download_min_size_mb: int = Field(64, ge=1)
    rclone_transfers: int = Field(1, ge=1)
    rclone_checkers: int = Field(4, ge=1)
    rclone_retries: int = Field(5, ge=0)
    rclone_low_level_retries: int = Field(10, ge=0)
    rclone_retries_sleep_seconds: int = Field(10, ge=0)
    rclone_stats_interval_seconds: int = Field(2, ge=1)
    rclone_drive_chunk_size: str = "64Mi"
    rclone_upload_timeout_minutes: int = Field(180, ge=1)
    rclone_extra_args: str = ""
    delete_local_after_success: bool = True
    delete_partial_on_failure: bool = False
    failed_file_retention_hours: float = Field(24, ge=0)
    cleanup_interval_minutes: float = Field(30, gt=0)
    retry_interrupted_jobs: bool = True
    generate_public_link: bool = False
    log_level: str = "INFO"
    log_file: Path = Path("/data/logs/uploader.log")
    log_max_bytes: int = Field(10_485_760, ge=1024)
    log_backup_count: int = Field(5, ge=0)

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def parse_ids(cls, value: object) -> object:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [int(x.strip()) for x in value.split(",") if x.strip()]
        return value

    @field_validator("rclone_remote")
    @classmethod
    def remote_name_is_safe(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise ValueError("RCLONE_REMOTE contains invalid characters")
        return value

    @field_validator("default_upload_directory")
    @classmethod
    def default_directory_is_safe(cls, value: str) -> str:
        value = value.strip()
        if value in {"", ".", ".."} or not re.fullmatch(r"[A-Za-z0-9 _-]{1,100}", value):
            raise ValueError("DEFAULT_UPLOAD_DIRECTORY contains invalid characters")
        return value

    @field_validator("rclone_drive_chunk_size")
    @classmethod
    def drive_chunk_size_is_safe(cls, value: str) -> str:
        if not re.fullmatch(r"[1-9][0-9]*(?:Ki|Mi|Gi|K|M|G)?", value):
            raise ValueError("RCLONE_DRIVE_CHUNK_SIZE must be a positive rclone size such as 64Mi")
        return value

    @model_validator(mode="after")
    def validate_mode(self) -> "Settings":
        if self.watch_mode == "chat" and self.watch_chat_id is None:
            raise ValueError("WATCH_CHAT_ID is required when WATCH_MODE=chat")
        return self

    def prepare_directories(self) -> None:
        for directory in (self.download_dir, self.state_dir, self.log_dir, self.telegram_session_path.parent):
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()

    def validate_runtime(self, require_session: bool = True) -> None:
        self.prepare_directories()
        if shutil.which("rclone") is None:
            raise ValueError("rclone executable was not found")
        if not self.rclone_config_path.is_file():
            raise ValueError(f"rclone config not found: {self.rclone_config_path}")
        # OAuth providers such as Google Drive periodically refresh their
        # token. rclone saves that token by creating a sibling temporary file
        # and atomically replacing rclone.conf, so checking only file write
        # access is insufficient.
        config_probe = self.rclone_config_path.parent / ".rclone-write-test"
        try:
            config_probe.write_text("ok", encoding="utf-8")
            config_probe.unlink()
        except OSError as exc:
            raise ValueError(
                f"rclone config directory is not writable: {self.rclone_config_path.parent}; "
                "OAuth remotes require a writable config to persist refreshed tokens"
            ) from exc
        if require_session and not session_exists(self.telegram_session_path):
            raise ValueError("Telegram session missing; run: python -m app.auth")

    def is_authorized(self, sender_id: int, self_id: int) -> bool:
        return sender_id in (self.allowed_user_ids or [self_id])

    def public_dict(self) -> dict[str, object]:
        hidden = {"telegram_api_hash", "telegram_phone"}
        return {k: str(v) if isinstance(v, Path) else v for k, v in self.model_dump().items() if k not in hidden}


def session_exists(path: Path) -> bool:
    return path.is_file() or path.with_suffix(path.suffix + ".session").is_file()
