"""Конфигурация приложения.

Подход прежний: датакласс AppConfig + переопределение значений
переменными окружения (секреты и параметры — в .staff/env).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "да"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw.strip()) if raw and raw.strip() else default
    except ValueError:
        return default


@dataclass
class AppConfig:
    api_token: str = field(default_factory=lambda: os.getenv("API_TOKEN", ""))
    # Токен для песочницы контента (дублирование карточек пробуем сначала там)
    sandbox_token: str = field(
        default_factory=lambda: os.getenv(
            "WB_SANDBOX_TOKEN", os.getenv("API_TOKEN", "")
        )
    )
    work_dir: Path = field(
        default_factory=lambda: Path(os.getenv("WORK_DIR", "work_dir")).resolve()
    )

    # Глобальный тумблер: не ходить в сеть, работать только с кешем и БД
    fetch_data: bool = field(default_factory=lambda: _env_bool("FETCH_DATA", True))

    # Периодический fetch в службе
    fetch_interval_minutes: int = field(
        default_factory=lambda: _env_int("FETCH_INTERVAL_MINUTES", 30)
    )
    # Отдельный интервал для потока карточек товаров
    cards_interval_minutes: int = field(
        default_factory=lambda: _env_int("CARDS_INTERVAL_MINUTES", 120)
    )
    # Глубина выгрузки за один проход (в сутках)
    lookback_days: int = field(default_factory=lambda: _env_int("LOOKBACK_DAYS", 30))

    # Эндпойнты, которые тянет пул fetch-потоков
    endpoints: List[str] = field(
        default_factory=lambda: os.getenv(
            "WB_ENDPOINTS", "orders,sales,incomes,stocks,warehouses"
        ).split(",")
    )

    # Задержки при 429: 2 мин, 30 мин, 1 час, 2 часа, 4 часа, далее удвоение
    retry_delays_sec: List[int] = field(
        default_factory=lambda: [
            _env_int(f"RETRY_DELAY_{i}", d)
            for i, d in enumerate([120, 1800, 3600, 7200, 14400])
        ]
    )
    max_retry_sec: int = field(default_factory=lambda: _env_int("MAX_RETRY_SEC", 24 * 3600))

    # Дублирование/правка карточек: 1 — слать в песочницу контента
    use_sandbox_update: bool = field(
        default_factory=lambda: _env_bool("USE_SANDBOX_UPDATE", False)
    )

    # Google Drive
    gdrive_enabled: bool = field(default_factory=lambda: _env_bool("GDRIVE_ENABLED", False))
    gdrive_folder_id: str = field(default_factory=lambda: os.getenv("GDRIVE_FOLDER_ID", ""))
    gdrive_service_account_file: str = field(
        default_factory=lambda: os.getenv("GDRIVE_SA_FILE", "")
    )

    db_filename: str = "wb.db"
    responses_dirname: str = "responses"
    logs_dirname: str = "logs"

    def __post_init__(self) -> None:
        self.work_dir = Path(self.work_dir).resolve()
        self.responses_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        if not self.api_token:
            raise ValueError(
                "API_TOKEN не задан: заполните .staff/env или переменные окружения"
            )

    # --- производные пути ---
    @property
    def db_path(self) -> Path:
        return self.work_dir / self.db_filename

    @property
    def responses_dir(self) -> Path:
        return self.work_dir / self.responses_dirname

    @property
    def logs_dir(self) -> Path:
        return self.work_dir / self.logs_dirname

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def fetch_interval_sec(self) -> int:
        return self.fetch_interval_minutes * 60

    @property
    def cards_interval_sec(self) -> int:
        return self.cards_interval_minutes * 60
