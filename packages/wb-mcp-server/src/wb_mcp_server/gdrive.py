import os
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

import json
from google.auth.transport.requests import Request
from google.oauth2 import credentials as user_credentials
from google.oauth2 import service_account

def _load_drive_credentials(creds_path: Path):
    info = json.loads(creds_path.read_text(encoding="utf-8"))
    if info.get("type") == "authorized_user":
        creds = user_credentials.Credentials.from_authorized_user_info(info, scopes=SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

def get_latest_report(reports_dir: Path) -> Path:
    files = sorted(reports_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"В папке {reports_dir} не найдено ни одного .xlsx отчёта")
    return files[0]


def upload_report_to_gdrive(
    file_path: Optional[Path] = None,
    reports_dir: Optional[Path] = None,
    credentials_path: Optional[str] = None,
    folder_id: Optional[str] = None,
) -> dict:
    """Загружает .xlsx файл на Google Диск без конвертации в Google Таблицы."""
    work_dir = Path(os.getenv("WORK_DIR", "work_dir")).resolve()
    r_dir = reports_dir or (work_dir / "reports")
    target_file = Path(file_path) if file_path else get_latest_report(r_dir)

    if not target_file.exists():
        raise FileNotFoundError(f"Файл отчёта не найден: {target_file}")

    creds_file = credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH", "")
    if not creds_file or not Path(creds_file).exists():
        raise FileNotFoundError(
            "Не задан или не найден файл ключа сервисного аккаунта GOOGLE_CREDENTIALS_PATH"
        )

    target_folder = folder_id or os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

    credentials = service_account.Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)

    metadata: dict = {"name": target_file.name}
    if target_folder:
        metadata["parents"] = [target_folder]

    media = MediaFileUpload(str(target_file), mimetype=XLSX_MIME, resumable=True)
    uploaded = (
        service.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    return uploaded


def main() -> None:
    """Точка входа CLI для ручной загрузки последнего отчёта на Google Диск."""
    res = upload_report_to_gdrive()
    print(f"Файл загружен: {res.get('name')} | ID: {res.get('id')} | Ссылка: {res.get('webViewLink')}")


if __name__ == "__main__":
    main()
