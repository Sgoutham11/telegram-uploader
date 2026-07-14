from datetime import timedelta

from app.cleanup_service import CleanupService
from app.config import Settings
from app.models import JobStatus, utcnow
from app.queue_manager import QueueManager
from app.state_store import StateStore


def test_retention_logic(tmp_path):
    settings = Settings(_env_file=None, telegram_api_id=1, telegram_api_hash="x", download_dir=tmp_path, state_dir=tmp_path, log_dir=tmp_path, log_file=tmp_path / "x", failed_file_retention_hours=2)
    cleanup = CleanupService(settings, StateStore(tmp_path), QueueManager(1))
    assert cleanup.should_delete(JobStatus.FAILED, utcnow() - timedelta(hours=3))
    assert not cleanup.should_delete(JobStatus.FAILED, utcnow() - timedelta(hours=1))

