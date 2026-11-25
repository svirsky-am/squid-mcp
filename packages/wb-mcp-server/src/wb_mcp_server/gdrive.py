import json
import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2 import credentials as user_credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://googleapis.com" + "drive.file"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def get_latest_report(reports_dir: Path) -> Path:
    files = sorted(reports_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"В папке {reports_dir} не найдено ни одного .xlsx отчёта")
    return next(iter(files))


def _load_drive_credentials(credentials_path: Path):
    info = json.loads(credentials_path.read_text(encoding="utf-8"))
    cred_type = info.get("type")

    if cred_type == "authorized_user" or ("refresh_token" in info and "client_id" in info):
        creds = user_credentials.Credentials.from_authorized_user_info(info, scopes=SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            updated = json.loads(creds.to_json())
            updated.setdefault("type", "authorized_user")
            credentials_path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
        return creds

    if cred_type == "service_account":
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    raise ValueError(
        f"Неподдерживаемый тип ключа Google ({cred_type!r}) в файле {credentials_path}."
    )

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
            "Не задан или не найден файл ключа Google GOOGLE_CREDENTIALS_PATH"
        )

    target_folder = folder_id or os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    creds = _load_drive_credentials(Path(creds_file))
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    metadata: dict = {"name": target_file.name}
    if target_folder:
        metadata["parents"] = [target_folder]

    media = MediaFileUpload(str(target_file), mimetype=XLSX_MIME, resumable=True)
    return (
        service.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )


def main() -> None:
    res = upload_report_to_gdrive()
    print(f"Файл загружен: {res.get('name')} | ID: {res.get('id')} | Ссылка: {res.get('webViewLink')}")


if __name__ == "__main__":
    main()
