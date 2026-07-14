from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path, PurePosixPath

from .models import utcnow

LOG = logging.getLogger(__name__)
VALID_DIRECTORY = re.compile(r"[A-Za-z0-9 _-]{1,100}\Z")


class DirectoryService:
    """Maintain and atomically persist the directory selected for new jobs."""

    def __init__(self, state_dir: Path, root_path: str, default_directory: str):
        self.state_path = state_dir / "current_directory.json"
        self.root_path = root_path.strip("/")
        self.default_directory = self.validate_directory_name(default_directory)
        self._current_directory = self.default_directory
        self._lock = asyncio.Lock()

    async def load(self) -> None:
        async with self._lock:
            try:
                payload = await asyncio.to_thread(self._read_sync)
                self._current_directory = self.validate_directory_name(payload["directory"])
            except FileNotFoundError:
                self._current_directory = self.default_directory
            except Exception:
                self._current_directory = self.default_directory
                LOG.exception("Invalid directory state %s; using %s", self.state_path, self.default_directory)

    def _read_sync(self) -> dict[str, object]:
        value = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("directory state must be an object")
        return value

    async def get_current_directory(self) -> str:
        async with self._lock:
            return self._current_directory

    async def set_directory(self, directory: str, user_id: int) -> str:
        validated = self.validate_directory_name(directory)
        async with self._lock:
            await asyncio.to_thread(self._write_sync, validated, user_id)
            self._current_directory = validated
            return validated

    async def reset_directory(self, user_id: int) -> str:
        return await self.set_directory(self.default_directory, user_id)

    def _write_sync(self, directory: str, user_id: int) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".json.tmp")
        payload = {"directory": directory, "updated_by": user_id, "updated_at": utcnow().isoformat().replace("+00:00", "Z")}
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.state_path)

    def validate_directory_name(self, directory: str) -> str:
        if not isinstance(directory, str):
            raise ValueError("directory must be text")
        value = directory.strip()
        if value in {"", ".", ".."} or not VALID_DIRECTORY.fullmatch(value):
            raise ValueError("invalid directory name")
        return value

    def build_destination_directory(self, directory: str) -> str:
        validated = self.validate_directory_name(directory)
        return (PurePosixPath(self.root_path) / validated).as_posix()

