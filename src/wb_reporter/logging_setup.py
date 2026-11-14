"""Настройка логирования: консоль + ротируемый файл в work_dir/logs."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_LOG_FILE = "wb_reporter.log"
_FMT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def setup_logging(work_dir: Path, level: str = "INFO") -> Path:
    """Идемпотентная-настройка root-логгера. Возвращает путь к файлу лога."""
    work_dir = Path(work_dir)
    log_dir = work_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / _LOG_FILE

    root = logging.getLogger()
    if getattr(root, "_wb_configured", False):
        return log_path

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter(_FMT)

    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(formatter)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    root.addHandler(fh)
    root.addHandler(sh)
    root._wb_configured = True  # type: ignore[attr-defined]
    return log_path
