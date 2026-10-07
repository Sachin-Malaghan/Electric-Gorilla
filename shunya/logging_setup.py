"""Logging for a long-running studio: a rotating file with everything, a quiet console."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure(log_dir: Path, *, level: str = "INFO", console_level: str = "WARNING") -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "studio.log"
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)
    file_handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(FORMAT))
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, console_level.upper(), logging.WARNING))
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(file_handler)
    root.addHandler(console)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return path
