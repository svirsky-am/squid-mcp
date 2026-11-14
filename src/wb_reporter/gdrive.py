"""Выгрузка сводных таблиц в Google Drive (опционально, пакет gspread).

Требуется сервисный аккаунт Google:
  - JSON-ключ сервисного аккаунта (путь — GDRIVE_SA_FILE);
  - ID папки на Drive (GDRIVE_FOLDER_ID);
  - e-mail сервисного аккаунта должен иметь доступ на запись в папку.
Установка: uv sync --extra drive
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from .app_config import AppConfig

logger = logging.getLogger(__name__)


def upload_xlsx_as_sheets(cfg: AppConfig, xlsx_path: Path) -> Optional[str]:
    """Создаёт Google Spreadsheet из xlsx и возвращает ссылку (или None)."""
    if not cfg.gdrive_enabled or not cfg.gdrive_folder_id:
        logger.info("Выгрузка на Google Drive отключена (GDRIVE_ENABLED/GDRIVE_FOLDER_ID)")
        return None
    try:
        import gspread
    except ImportError:
        logger.error("gspread не установлен: выполните 'uv sync --extra drive'")
        return None

    gc = gspread.service_account(filename=cfg.gdrive_service_account_file or None)
    title = f"WB сводный отчёт {xlsx_path.stem}"
    spreadsheet = gc.create(title, folder_id=cfg.gdrive_folder_id)
    try:
        sheets = pd.read_excel(xlsx_path, sheet_name=None)
        first_name, first_df = next(iter(sheets.items()))
        ws = spreadsheet.get_worksheet(0)
        ws.update_title(first_name)
        ws.update(
            [list(first_df.columns)]
            + first_df.astype(object).where(pd.notna(first_df), "").values.tolist()
        )
        for name, df in list(sheets.items())[1:]:
            w = spreadsheet.add_worksheet(name, rows=len(df) + 1, cols=max(len(df.columns), 1))
            w.update(
                [list(df.columns)] + df.astype(object).where(pd.notna(df), "").values.tolist()
            )
        logger.info("Загружено на Google Drive: %s", spreadsheet.url)
        return spreadsheet.url
    except Exception:
        logger.exception("Ошибка выгрузки на Google Drive")
        try:
            spreadsheet.del_spreadsheet()
        except Exception:
            pass
        return None
