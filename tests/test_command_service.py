from app.command_service import CommandService
from app.config import Settings
from app.directory_service import DirectoryService
from app.queue_manager import QueueManager
from app.state_store import StateStore
from app.handlers import register_handlers


class Event:
    def __init__(self, text, sender_id=123):
        self.raw_text = text
        self.sender_id = sender_id
        self.replies = []

    async def reply(self, text):
        self.replies.append(text)


class FakeClient:
    def __init__(self):
        self.handler = None

    def on(self, _event_type):
        def decorator(callback):
            self.handler = callback
            return callback
        return decorator


def settings(tmp_path):
    return Settings(_env_file=None, telegram_api_id=1, telegram_api_hash="x", download_dir=tmp_path, state_dir=tmp_path, log_dir=tmp_path, log_file=tmp_path / "x.log")


async def service(tmp_path):
    config = settings(tmp_path)
    directories = DirectoryService(tmp_path, config.rclone_base_path, config.default_upload_directory)
    await directories.load()
    return CommandService(config, QueueManager(5), StateStore(tmp_path), directories), directories


async def test_dir_show_set_and_reset(tmp_path):
    commands, directories = await service(tmp_path)
    show = Event(".dir")
    await commands.handle(show)
    assert "UPLOADS/DOWNLOADS" in show.replies[0]
    change = Event(".dir goutham")
    await commands.handle(change)
    assert "UPLOADS/goutham" in change.replies[0]
    assert await directories.get_current_directory() == "goutham"
    reset = Event(".dir reset")
    await commands.handle(reset)
    assert "Upload directory reset" in reset.replies[0]
    assert await directories.get_current_directory() == "DOWNLOADS"


async def test_dir_rejects_unsafe_name(tmp_path):
    commands, directories = await service(tmp_path)
    event = Event(".dir ../secret")
    await commands.handle(event)
    assert event.replies == ["Invalid directory name.\nUse only letters, numbers, spaces, hyphens, and underscores."]
    assert await directories.get_current_directory() == "DOWNLOADS"


async def test_dir_authorization_and_monitored_chat_are_enforced(tmp_path):
    commands, directories = await service(tmp_path)
    client = FakeClient()
    config = commands.settings
    queue = commands.queue
    state = commands.state
    register_handlers(client, config, queue, state, commands, directories, self_id=123)
    unauthorized = Event(".dir Movies", sender_id=999)
    unauthorized.chat_id = 123
    await client.handler(unauthorized)
    assert unauthorized.replies == ["You are not authorized to use this uploader."]
    unrelated = Event(".dir Movies", sender_id=123)
    unrelated.chat_id = 456
    await client.handler(unrelated)
    assert unrelated.replies == []
    assert await directories.get_current_directory() == "DOWNLOADS"
