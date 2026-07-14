from pathlib import Path

from telethon import TelegramClient

from .config import Settings


def create_client(settings: Settings) -> TelegramClient:
    path = str(settings.telegram_session_path)
    if path.endswith(".session"):
        path = path[:-8]
    return TelegramClient(path, settings.telegram_api_id, settings.telegram_api_hash)

