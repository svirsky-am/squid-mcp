from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


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
    sandbox_token: str = field(default_factory=lambda: os.getenv("WB_SANDBOX_TOKEN", os.getenv("API_TOKEN", "")))
    work_dir: Path = field(default_factory=lambda: Path(os.getenv("WORK_DIR", "work_dir")).resolve())
    fetch_data: bool = field(default_factory=lambda: _env_bool("FETCH_DATA", True))
    fetch_orders_interval_minutes: int = field(default_factory=lambda: _env_int("FETCH_INTERVAL_MINUTES", 30))
    cards_interval_minutes: int = field(default_factory=lambda: _env_int("CARDS_INTERVAL_MINUTES", 360))
    report_interval_minutes: int = field(default_factory=lambda: _env_int("REPORT_INTERVAL_MINUTES", 60))
    stocks_interval_minutes: int = field(default_factory=lambda: _env_int("STOCKS_INTERVAL_MINUTES", 60))
    lookback_days: int = field(default_factory=lambda: _env_int("LOOKBACK_DAYS", 30))
    max_workers: int = field(default_factory=lambda: _env_int("MAX_WORKERS", 4))

    # Настройки загрузки отчётов на Google Диск
    enable_gdrive_upload: bool = field(default_factory=lambda: _env_bool("ENABLE_GDRIVE_UPLOAD", False))
    google_credentials_path: Optional[Path] = field(
        default_factory=lambda: Path(os.getenv("GOOGLE_CREDENTIALS_PATH")).resolve()
        if os.getenv("GOOGLE_CREDENTIALS_PATH", "").strip()
        else None
    )
    google_drive_folder_id: str = field(default_factory=lambda: os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip())

    retry_delays_sec: List[int] = field(default_factory=lambda: list((120, 1800, 3600, 7200, 14400)))
    max_retry_sec: int = field(default_factory=lambda: _env_int("MAX_RETRY_SEC", 24 * 3600))

    db_filename: str = "wb.db"
    responses_dirname: str = "responses"
    logs_dirname: str = "logs"
    reports_dirname: str = "reports"

    def __post_init__(self) -> None:
        self.work_dir = Path(self.work_dir).resolve()
        self.responses_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        if not self.api_token:
            raise ValueError("API_TOKEN не задан: заполните .staff/env или переменные окружения")

        if self.enable_gdrive_upload:
            if not self.google_credentials_path:
                raise ValueError(
                    "ENABLE_GDRIVE_UPLOAD=True, но не задан путь к ключу GOOGLE_CREDENTIALS_PATH"
                )
            self.google_credentials_path = Path(self.google_credentials_path).resolve()
            if not self.google_credentials_path.exists():
                raise FileNotFoundError(
                    f"Файл ключа Google Service Account не найден: {self.google_credentials_path}"
                )
            if not self.google_drive_folder_id:
                raise ValueError(
                    "ENABLE_GDRIVE_UPLOAD=True, но не задан ID папки GOOGLE_DRIVE_FOLDER_ID"
                )

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
    def reports_dir(self) -> Path:
        return self.work_dir / self.reports_dirname

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def fetch_orders_interval_sec(self) -> int:
        return self.fetch_orders_interval_minutes * 60

    @property
    def cards_interval_sec(self) -> int:
        return self.cards_interval_minutes * 60

    @property
    def report_interval_sec(self) -> int:
        return self.report_interval_minutes * 60

    @property
    def stocks_interval_sec(self) -> int:
        return self.stocks_interval_minutes * 60