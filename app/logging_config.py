import logging
from logging.handlers import RotatingFileHandler

from .config import Settings


def configure_logging(settings: Settings) -> None:
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = RotatingFileHandler(settings.log_file, maxBytes=settings.log_max_bytes, backupCount=settings.log_backup_count)
    file_handler.setFormatter(formatter)
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), handlers=[console, file_handler], force=True)

