"""Console + rotating file logging (backend/logs/app.log)."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.database import BACKEND_DIR

LOG_DIR = Path(os.getenv("LOG_DIR") or BACKEND_DIR / "logs")
_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging() -> None:
    """Idempotent. File logs rotate at 5MB (3 backups)."""
    root = logging.getLogger()
    if getattr(root, "_festival_logging", False):
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, (os.getenv("LOG_LEVEL") or "INFO").upper(), logging.INFO)
    fmt = logging.Formatter(_FORMAT)

    file_handler = RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    console = logging.StreamHandler()
    for h in (file_handler, console):
        h.setFormatter(fmt)
        root.addHandler(h)
    root.setLevel(level)
    # httpx logs full request URLs at INFO, which would leak the serviceKey.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._festival_logging = True  # type: ignore[attr-defined]
