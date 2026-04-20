"""Конфигурация логирования для приложения ``range_program``.

Модуль централизует настройку файлового логирования:
- определяет корневое имя логгера приложения;
- вычисляет путь к файлу логов ``data/logs/app.log`` в корне проекта;
- создает директорию логов при необходимости;
- настраивает формат записей и предотвращает дублирование сообщений
  через корневой logger.

Функция ``setup_logging()`` должна вызываться один раз при старте CLI.
После этого остальные части приложения получают логгеры через
``get_logger()``.
"""

from __future__ import annotations

import logging
from pathlib import Path

_LOGGER_NAME = "range_program"


def project_root() -> Path:
    """Вернуть абсолютный путь к корню проекта.

    Корень определяется относительно текущего файла модуля.
    """
    return Path(__file__).resolve().parents[2]


def log_file_path() -> Path:
    """Сформировать путь до файла логов приложения.

    Returns:
        Path: Путь вида ``<project_root>/data/logs/app.log``.
    """
    return project_root() / "data" / "logs" / "app.log"


def setup_logging() -> None:
    """Инициализировать файловое логирование для ``range_program``.

    Настройка выполняется только один раз: если у корневого логгера
    приложения уже есть обработчики, функция завершается без изменений.

    Что настраивается:
    - уровень ``INFO``;
    - файл логов ``data/logs/app.log``;
    - формат записи с временем, уровнем, именем логгера и сообщением;
    - ``propagate = False`` для исключения дублирования в root logger.
    """
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
    """Вернуть именованный дочерний логгер приложения.

    Args:
        name: Суффикс имени логгера (например, ``"cli"``).

    Returns:
        logging.Logger: Логгер вида ``range_program.<name>``.
    """
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
