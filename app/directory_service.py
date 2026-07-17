from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path, PurePosixPath

from .models import utcnow

LOG = logging.getLogger(__name__)
VALID_SEGMENT = re.compile(r"[A-Za-z0-9 _-]{1,100}\Z")


class DirectoryService:
    """Maintain and atomically persist one selected directory per allowed user."""

    def __init__(self, state_dir: Path, root_path: str, default_directory: str, allowed_users: dict[int, str]):
        self.state_path = state_dir / "user_directories.json"
        self.root_path = root_path.strip("/")
        self.default_directory = self.validate_directory_name(default_directory)
        self.allowed_users = dict(allowed_users)
        self._current_directories: dict[int, str] = {}
        self._updated_at: dict[int, str] = {}
        self._lock = asyncio.Lock()

    async def load(self) -> None:
        async with self._lock:
            try:
                payload = await asyncio.to_thread(self._read_sync)
                self._load_payload(payload)
            except FileNotFoundError:
                self._current_directories = {}
                self._updated_at = {}
            except Exception:
                self._current_directories = {}
                self._updated_at = {}
                LOG.exception("Invalid per-user directory state %s; using defaults", self.state_path)

    def _read_sync(self) -> dict[str, object]:
        value = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("per-user directory state must be an object")
        return value

    def _load_payload(self, payload: dict[str, object]) -> None:
        current: dict[int, str] = {}
        updated: dict[int, str] = {}
        for user_id in self.allowed_users:
            record = payload.get(str(user_id))
            if record is None:
                continue
            if not isinstance(record, dict):
                raise ValueError(f"directory state for {user_id} must be an object")
            current[user_id] = self.validate_directory_name(record.get("current_directory", ""))
            timestamp = record.get("updated_at")
            if isinstance(timestamp, str):
                updated[user_id] = timestamp
        self._current_directories = current
        self._updated_at = updated

    def get_allowed_username(self, user_id: int) -> str:
        try:
            return self.allowed_users[user_id]
        except KeyError as exc:
            raise PermissionError(f"Telegram user {user_id} is not allowed") from exc

    async def get_user_current_directory(self, user_id: int) -> str:
        self.get_allowed_username(user_id)
        async with self._lock:
            return self._current_directories.get(user_id, self.default_directory)

    async def set_user_current_directory(self, user_id: int, directory: str) -> str:
        self.get_allowed_username(user_id)
        validated = self.validate_directory_name(directory)
        async with self._lock:
            self._current_directories[user_id] = validated
            self._updated_at[user_id] = utcnow().isoformat().replace("+00:00", "Z")
            await asyncio.to_thread(self._write_sync)
            return validated

    async def reset_user_current_directory(self, user_id: int) -> str:
        return await self.set_user_current_directory(user_id, self.default_directory)

    def _write_sync(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".json.tmp")
        payload = {
            str(user_id): {
                "username": username,
                "current_directory": self._current_directories.get(user_id, self.default_directory),
                "updated_at": self._updated_at.get(user_id),
            }
            for user_id, username in self.allowed_users.items()
        }
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.state_path)

    def validate_directory_name(self, directory: object) -> str:
        if not isinstance(directory, str):
            raise ValueError("directory must be text")
        value = directory.strip()
        parts = [part.strip() for part in value.split("/")]
        if not parts or len(parts) > 10 or len(value) > 500 or any(
            part in {"", ".", ".."} or not VALID_SEGMENT.fullmatch(part)
            for part in parts
        ):
            raise ValueError("invalid directory name")
        return "/".join(parts)

    def build_user_directory(self, user_id: int, directory: str) -> str:
        username = self.get_allowed_username(user_id)
        validated = self.validate_directory_name(directory)
        return (PurePosixPath(username) / PurePosixPath(validated)).as_posix()

    def build_destination_directory(self, user_id: int, directory: str) -> str:
        return (PurePosixPath(self.root_path) / self.build_user_directory(user_id, directory)).as_posix()

    def build_snapshot_destination_directory(self, username: str, directory: str) -> str:
        validated = self.validate_directory_name(directory)
        if username:
            if username in {".", ".."} or not VALID_SEGMENT.fullmatch(username):
                raise ValueError("invalid configured username")
            return (PurePosixPath(self.root_path) / username / PurePosixPath(validated)).as_posix()
        # Jobs written by versions before per-user directories remain
        # recoverable and retain their original destination.
        return (PurePosixPath(self.root_path) / PurePosixPath(validated)).as_posix()

    async def build_upload_path(self, user_id: int, filename: str) -> str:
        directory = await self.get_user_current_directory(user_id)
        return (PurePosixPath(self.build_destination_directory(user_id, directory)) / filename).as_posix()
