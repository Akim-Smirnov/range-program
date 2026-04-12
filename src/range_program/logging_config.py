"""Базовая настройка логирования (этап 8). Ротация и лимиты — отдельно позже."""

from __future__ import annotations

import logging
from pathlib import Path

_LOGGER_NAME = "range_program"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def log_file_path() -> Path:
    return project_root() / "data" / "logs" / "app.log"


def setup_logging() -> None:
    """Один раз: файл `data/logs/app.log`, уровень INFO."""
    log = logging.getLogger(_LOGGER_NAME)
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    log_dir = log_file_path().parent
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_file_path(), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    log.addHandler(fh)
    # Не дублировать в корневой logger
    log.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Дочерний логгер под `range_program.*`."""
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
