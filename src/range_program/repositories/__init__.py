"""
Пакет репозиториев (слой хранения данных).

Содержит репозитории для работы с локальными JSON-файлами в `data/` и
реэкспортирует основные классы для импорта из `range_program.repositories`.
"""

from range_program.repositories.check_history_repository import CheckHistoryRepository
from range_program.repositories.coin_repository import CoinRepository

__all__ = ["CheckHistoryRepository", "CoinRepository"]
