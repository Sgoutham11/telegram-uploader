from __future__ import annotations

import asyncio
import getpass

from telethon.errors import SessionPasswordNeededError

from .config import Settings
from .telegram_client import create_client


async def authenticate() -> None:
    settings = Settings()
    settings.telegram_session_path.parent.mkdir(parents=True, exist_ok=True)
    client = create_client(settings)
    await client.connect()
    try:
        if await client.is_user_authorized():
            print("Telegram session is already authenticated.")
            return
        phone = settings.telegram_phone or input("Telegram phone number (international format): ").strip()
        await client.send_code_request(phone)
        code = input("Telegram login code: ").strip()
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            await client.sign_in(password=getpass.getpass("Two-step verification password: "))
        me = await client.get_me()
        print(f"Authentication successful for user ID {me.id}.")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(authenticate())

