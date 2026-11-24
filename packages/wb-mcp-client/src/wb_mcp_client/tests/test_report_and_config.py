from pathlib import Path
from unittest.mock import MagicMock

import openpyxl
import pytest

import wb_mcp_client.report as report_mod
from wb_mcp_client.app_config import AppConfig
from wb_mcp_client.db import Database
from wb_mcp_client.report import build_and_upload_report


def test_app_config_gdrive_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_TOKEN", "test-wb-token")
    monkeypatch.setenv("WORK_DIR", str(tmp_path))

    # 1. При выключенной загрузке параметры Google Drive не обязательны
    monkeypatch.setenv("ENABLE_GDRIVE_UPLOAD", "false")
    monkeypatch.delenv("GOOGLE_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_DRIVE_FOLDER_ID", raising=False)
    cfg = AppConfig()
    assert cfg.enable_gdrive_upload is False

    # 2. Включена загрузка, но не задан путь к ключу
    monkeypatch.setenv("ENABLE_GDRIVE_UPLOAD", "true")
    with pytest.raises(ValueError, match="GOOGLE_CREDENTIALS_PATH"):
        AppConfig()

    # 3. Задан несуществующий файл ключа
    missing_key = tmp_path / "missing.json"
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", str(missing_key))
    with pytest.raises(FileNotFoundError, match="не найден"):
        AppConfig()

    # 4. Файл ключа есть, но не задан ID папки
    valid_key = tmp_path / "creds.json"
    valid_key.write_text('{"type": "service_account"}', encoding="utf-8")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", str(valid_key))
    with pytest.raises(ValueError, match="GOOGLE_DRIVE_FOLDER_ID"):
        AppConfig()

    # 5. Все обязательные поля заполнены корректно
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "folder-abc-123")
    valid_cfg = AppConfig()
    assert valid_cfg.enable_gdrive_upload is True
    assert valid_cfg.google_drive_folder_id == "folder-abc-123"


def _seed_db(db_path: Path) -> None:
    db = Database(db_path)
    db.upsert_orders([
        {
            "id": 5001,
            "orderUid": "uid-5001",
            "rid": "rid-5001",
            "createdAt": "2026-11-24T10:15:00Z",
            "article": "jacket-black",
            "nmId": 987654,
            "chrtId": 112233,
            "skus": ["4600000000001"],
            "price": 450000,
            "convertedPrice": 450000,
            "currencyCode": 643,
            "convertedCurrencyCode": 643,
            "deliveryType": "fbs",
            "supplyId": "WB-GI-777",
            "warehouseId": 10,
            "officeId": 20,
            "cargoType": 1,
            "isZeroOrder": False,
        }
    ])
    db.update_order_statuses([
        {"id": 5001, "supplierStatus": "complete", "wbStatus": "sold"}
    ])


def test_build_and_upload_report_without_gdrive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("API_TOKEN", "test-wb-token")
    monkeypatch.setenv("WORK_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_GDRIVE_UPLOAD", "false")

    cfg = AppConfig()
    _seed_db(cfg.db_path)

    upload_spy = MagicMock()
    monkeypatch.setattr(report_mod, "upload_report_file", upload_spy)

    report_path = build_and_upload_report(cfg)

    assert report_path.exists()
    assert report_path.suffix == ".xlsx"
    upload_spy.assert_not_called()

    # Проверяем структуру 4 листов в созданном Excel
    wb = openpyxl.load_workbook(report_path)
    assert wb.sheetnames == [
        "Плоский список (JSON)",
        "Сводная (Артикулы)",
        "Сводная (По дням)",
        "Реестр FBS",
    ]


def test_build_and_upload_report_with_gdrive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    valid_key = tmp_path / "creds.json"
    valid_key.write_text('{"type": "service_account"}', encoding="utf-8")

    monkeypatch.setenv("API_TOKEN", "test-wb-token")
    monkeypatch.setenv("WORK_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_GDRIVE_UPLOAD", "true")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", str(valid_key))
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "drive-target-folder")

    cfg = AppConfig()
    _seed_db(cfg.db_path)

    mock_creds = MagicMock()
    monkeypatch.setattr(
        report_mod.service_account.Credentials,
        "from_service_account_file",
        lambda *args, **kwargs: mock_creds,
    )
    mock_drive = MagicMock()
    mock_create = mock_drive.files.return_value.create
    mock_create.return_value.execute.return_value = {
        "id": "file-id-1",
        "name": "report.xlsx",
        "webViewLink": "https://google.com",
    }
    monkeypatch.setattr(report_mod, "build", lambda *args, **kwargs: mock_drive)

    report_path = build_and_upload_report(cfg)

    assert report_path.exists()
    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["body"]["name"] == report_path.name
    assert call_kwargs["body"]["parents"] == ["drive-target-folder"]
    assert (
        call_kwargs["media_body"].mimetype()
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
