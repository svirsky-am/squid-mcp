import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from wb_mcp_client.app_config import AppConfig
from wb_mcp_client.db import Database
from wb_mcp_client.logger import setup_logger

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from google.auth.transport.requests import Request
from google.oauth2 import credentials as user_credentials
from google.oauth2 import service_account

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

TIMESTAMP_FMT = "%Y.%m.%d_%H.%M.%S"

SUPPLIER_STATUS_LABELS = {
    "new": "Новое",
    "confirm": "На сборке",
    "complete": "В доставке",
    "cancel": "Отмена продавцом",
    "cancel_carrier": "Отмена перевозчиком",
}

WB_STATUS_LABELS = {
    "waiting": "В работе",
    "sorted": "Отсортировано",
    "sold": "Продано",
    "canceled": "Отмена",
    "canceled_by_client": "Отказ покупателем",
    "declined_by_client": "Отмена клиентом (1 час)",
    "defect": "Брак",
    "ready_for_pickup": "Ожидает в ПВЗ",
}

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
SUB_HEADER_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
TOTAL_FILL = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF")
SUB_HEADER_FONT = Font(bold=True, color="000000")
TOTAL_FONT = Font(bold=True)
THIN_SIDE = Side(style="thin", color="D9D9D9")
CELL_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)


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

def upload_report_file(
    report_path: Path,
    credentials_path: Path,
    folder_id: str,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    """Загружает готовый .xlsx файл на Google Диск без конвертации в Google Таблицы."""
    log = logger or logging.getLogger("wb_report_general")
    creds = _load_drive_credentials(Path(credentials_path))
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    metadata: Dict[str, Any] = {"name": report_path.name}
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaFileUpload(str(report_path), mimetype=XLSX_MIME, resumable=True)
    uploaded = (
        drive.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    log.info(
        "Отчёт загружен на Google Диск: %s (id=%s, link=%s)",
        uploaded.get("name"),
        uploaded.get("id"),
        uploaded.get("webViewLink"),
    )
    return uploaded
def build_and_upload_report(
    config: AppConfig,
    seller_name: str = "ИП (WB)",
    logger: Optional[logging.Logger] = None,
) -> Path:
    """Строит общий Excel-отчёт и при включённом флаге в конфиге загружает его на Google Диск."""
    log = logger or setup_logger(config.logs_dir, name="wb_report_general")
    report_path = build_excel_report_general(config, seller_name=seller_name, logger=log)

    if config.enable_gdrive_upload and config.google_credentials_path:
        upload_report_file(
            report_path=report_path,
            credentials_path=config.google_credentials_path,
            folder_id=config.google_drive_folder_id,
            logger=log,
        )

    return report_path

def _human_status(supplier_status: Optional[str], wb_status: Optional[str]) -> str:
    if wb_status == "sold":
        return "Продано"
    if wb_status in {"canceled", "canceled_by_client", "declined_by_client", "defect"}:
        return WB_STATUS_LABELS.get(wb_status, "Отмена")
    if supplier_status == "cancel":
        return "Отмена"
    if wb_status == "ready_for_pickup":
        return "Ожидает в ПВЗ"
    if supplier_status == "complete":
        return "Доставляется"
    if supplier_status == "confirm":
        return "На сборке"
    if supplier_status == "new":
        return "Новое"
    return SUPPLIER_STATUS_LABELS.get(supplier_status or "", supplier_status or "Неизвестно")


def _flatten_dict(data: Any, parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    items: Dict[str, Any] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
            items.update(_flatten_dict(v, new_key, sep=sep))
    elif isinstance(data, list):
        if not data:
            items[parent_key] = ""
        elif all(not isinstance(x, (dict, list)) for x in data):
            items[parent_key] = ", ".join(str(x) for x in data)
        else:
            for idx, v in enumerate(data):
                new_key = f"{parent_key}{sep}{idx}" if parent_key else str(idx)
                items.update(_flatten_dict(v, new_key, sep=sep))
    else:
        items[parent_key] = data
    return items


def _auto_fit_columns(ws, max_width: int = 45) -> None:
    for col_idx, col in enumerate(ws.columns, start=1):
        max_len = 0
        col_letter = get_column_letter(col_idx)
        for cell in col:
            val = str(cell.value or "")
            if val.startswith("="):
                val = "1234567890"
            max_len = max(max_len, len(val))
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), max_width)


def _build_sheet_raw_json(wb: Workbook, records: List[Dict[str, Any]]) -> None:
    ws = wb.active
    ws.title = "Плоский список (JSON)"

    flat_rows: List[Dict[str, Any]] = []
    all_keys: List[str] = []
    seen_keys = set()

    for rec in records:
        flat = _flatten_dict(rec.get("raw") or {})
        flat.setdefault("supplierStatus", rec.get("supplier_status", ""))
        flat.setdefault("wbStatus", rec.get("wb_status", ""))
        flat_rows.append(flat)
        for k in flat.keys():
            if k not in seen_keys:
                seen_keys.add(k)
                all_keys.append(k)

    if not all_keys:
        ws.append(["Нет данных"])
        return

    ws.append(all_keys)
    for c_i in range(1, len(all_keys) + 1):
        cell = ws.cell(row=1, column=c_i)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for flat in flat_rows:
        row_values = []
        for k in all_keys:
            val = flat.get(k, "")
            if isinstance(val, bool):
                val = "Да" if val else "Нет"
            elif val is None:
                val = ""
            row_values.append(val)
        ws.append(row_values)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(all_keys))}{max(len(flat_rows) + 1, 1)}"
    _auto_fit_columns(ws)

def _build_sheet_pivot_articles(wb: Workbook, records: List[Dict[str, Any]]) -> None:
    ws = wb.create_sheet(title="Сводная (Артикулы)")

    all_statuses = sorted({rec["status_human"] for rec in records}) or ["Нет данных"]
    pivot_data: Dict[tuple, Dict[str, Dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: {"cnt": 0, "sum": 0.0})
    )

    for rec in records:
        key = (rec["article"], rec["nm_id"], rec["title"], rec["subject"])
        st = rec["status_human"]
        pivot_data[key][st]["cnt"] += 1
        pivot_data[key][st]["sum"] += rec["price_rub"]

    fixed_headers = ["Артикул продавца", "Артикул WB (nmId)", "Наименование", "Предмет"]
    for idx, h_text in enumerate(fixed_headers, start=1):
        ws.cell(row=1, column=idx, value=h_text)
        ws.merge_cells(start_row=1, start_column=idx, end_row=2, end_column=idx)

    col_idx = len(fixed_headers) + 1
    for st in all_statuses:
        ws.cell(row=1, column=col_idx, value=st)
        ws.merge_cells(start_row=1, start_column=col_idx, end_row=1, end_column=col_idx + 1)
        ws.cell(row=2, column=col_idx, value="Кол-во, шт.")
        ws.cell(row=2, column=col_idx + 1, value="Сумма, ₽")
        col_idx += 2

    total_cnt_col = col_idx
    total_sum_col = col_idx + 1
    ws.cell(row=1, column=total_cnt_col, value="Общий итог")
    ws.merge_cells(start_row=1, start_column=total_cnt_col, end_row=1, end_column=total_sum_col)
    ws.cell(row=2, column=total_cnt_col, value="Всего, шт.")
    ws.cell(row=2, column=total_sum_col, value="Всего, ₽")

    for r_i in (1, 2):
        for c_i in range(1, total_sum_col + 1):
            c = ws.cell(row=r_i, column=c_i)
            c.fill = HEADER_FILL if r_i == 1 else SUB_HEADER_FILL
            c.font = HEADER_FONT if r_i == 1 else SUB_HEADER_FONT
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border = CELL_BORDER

    sorted_keys = sorted(
        pivot_data.keys(),
        key=lambda k: sum(v["sum"] for v in pivot_data[k].values()),
        reverse=True,
    )

    start_data_row = 3
    curr_row = start_data_row
    for art, nm_id, title, subject in sorted_keys:
        ws.cell(row=curr_row, column=1, value=art).border = CELL_BORDER
        ws.cell(row=curr_row, column=2, value=nm_id).border = CELL_BORDER
        ws.cell(row=curr_row, column=3, value=title).border = CELL_BORDER
        ws.cell(row=curr_row, column=4, value=subject).border = CELL_BORDER

        cnt_cells = []
        sum_cells = []
        c_ptr = 5
        for st in all_statuses:
            vals = pivot_data[(art, nm_id, title, subject)][st]
            c_cnt = ws.cell(row=curr_row, column=c_ptr, value=vals["cnt"])
            c_sum = ws.cell(row=curr_row, column=c_ptr + 1, value=round(vals["sum"], 2))
            c_cnt.number_format = "#,##0"
            c_sum.number_format = "#,##0.00"
            c_cnt.border = CELL_BORDER
            c_sum.border = CELL_BORDER
            cnt_cells.append(f"{get_column_letter(c_ptr)}{curr_row}")
            sum_cells.append(f"{get_column_letter(c_ptr + 1)}{curr_row}")
            c_ptr += 2

        f_cnt = f"=SUM({','.join(cnt_cells)})" if cnt_cells else 0
        f_sum = f"=SUM({','.join(sum_cells)})" if sum_cells else 0
        c_tot_cnt = ws.cell(row=curr_row, column=total_cnt_col, value=f_cnt)
        c_tot_sum = ws.cell(row=curr_row, column=total_sum_col, value=f_sum)
        c_tot_cnt.font = TOTAL_FONT
        c_tot_sum.font = TOTAL_FONT
        c_tot_cnt.number_format = "#,##0"
        c_tot_sum.number_format = "#,##0.00"
        c_tot_cnt.border = CELL_BORDER
        c_tot_sum.border = CELL_BORDER

        curr_row += 1

    end_data_row = max(curr_row - 1, start_data_row)
    ws.cell(row=curr_row, column=1, value="Общий итог").font = TOTAL_FONT
    for c_i in range(1, 5):
        ws.cell(row=curr_row, column=c_i).fill = TOTAL_FILL

    for c_i in range(5, total_sum_col + 1):
        col_let = get_column_letter(c_i)
        cell = ws.cell(
            row=curr_row,
            column=c_i,
            value=f"=SUM({col_let}{start_data_row}:{col_let}{end_data_row})" if records else 0,
        )
        cell.font = TOTAL_FONT
        cell.fill = TOTAL_FILL
        cell.border = CELL_BORDER
        cell.number_format = "#,##0" if c_i % 2 == 1 else "#,##0.00"

    ws.freeze_panes = "E3"
    _auto_fit_columns(ws)

def _build_sheet_daily(wb: Workbook, records: List[Dict[str, Any]]) -> None:
    ws = wb.create_sheet(title="Сводная (По дням)")
    daily_headers = [
        "Дата создания",
        "Всего заказов, шт.",
        "Общая сумма, ₽",
        "Продано / Доставляется, шт.",
        "Выручка активных, ₽",
        "Отменено, шт.",
        "Сумма отмен, ₽",
        "Средний чек, ₽",
    ]
    ws.append(daily_headers)
    for c_i in range(1, len(daily_headers) + 1):
        cell = ws.cell(row=1, column=c_i)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    daily_map: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"cnt": 0, "sum": 0.0, "ok_cnt": 0, "ok_sum": 0.0, "cancel_cnt": 0, "cancel_sum": 0.0}
    )
    for rec in records:
        d = rec["created_date"] or "Без даты"
        daily_map[d]["cnt"] += 1
        daily_map[d]["sum"] += rec["price_rub"]
        if "Отмена" in rec["status_human"]:
            daily_map[d]["cancel_cnt"] += 1
            daily_map[d]["cancel_sum"] += rec["price_rub"]
        else:
            daily_map[d]["ok_cnt"] += 1
            daily_map[d]["ok_sum"] += rec["price_rub"]

    d_row = 2
    for dt_str in sorted(daily_map.keys(), reverse=True):
        m = daily_map[dt_str]
        ws.append([
            dt_str,
            m["cnt"],
            round(m["sum"], 2),
            m["ok_cnt"],
            round(m["ok_sum"], 2),
            m["cancel_cnt"],
            round(m["cancel_sum"], 2),
            f"=IF(B{d_row}>0, C{d_row}/B{d_row}, 0)",
        ])
        for c_i in (2, 4, 6):
            ws.cell(row=d_row, column=c_i).number_format = "#,##0"
        for c_i in (3, 5, 7, 8):
            ws.cell(row=d_row, column=c_i).number_format = "#,##0.00"
        d_row += 1

    if daily_map:
        last_d_row = d_row - 1
        ws.append([
            "Общий итог",
            f"=SUM(B2:B{last_d_row})",
            f"=SUM(C2:C{last_d_row})",
            f"=SUM(D2:D{last_d_row})",
            f"=SUM(E2:E{last_d_row})",
            f"=SUM(F2:F{last_d_row})",
            f"=SUM(G2:G{last_d_row})",
            f"=IF(B{d_row}>0, C{d_row}/B{d_row}, 0)",
        ])
        for c_i in range(1, len(daily_headers) + 1):
            c = ws.cell(row=d_row, column=c_i)
            c.font = TOTAL_FONT
            c.fill = TOTAL_FILL
            if c_i in (2, 4, 6):
                c.number_format = "#,##0"
            elif c_i in (3, 5, 7, 8):
                c.number_format = "#,##0.00"

    ws.freeze_panes = "A2"
    _auto_fit_columns(ws)


def _build_sheet_registry(wb: Workbook, records: List[Dict[str, Any]]) -> None:
    ws = wb.create_sheet(title="Реестр FBS")
    raw_headers = [
        "Дата отчета",
        "ИП",
        "№ задания",
        "QR-код поставки",
        "Дата и время создания",
        "Дата создания",
        "Стоимость",
        "Валюта",
        "Артикул Wildberries",
        "Артикул продавца",
        "Наименование",
        "Бренд",
        "Предмет",
        "Баркод (SKU)",
        "ID склада продавца",
        "ID офиса WB",
        "Статус (сводный)",
        "Статус продавца (WB API)",
        "Статус системы WB",
        "Признак продажи юрлицу",
        "RID",
    ]
    ws.append(raw_headers)
    for c_i in range(1, len(raw_headers) + 1):
        cell = ws.cell(row=1, column=c_i)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for r_idx, rec in enumerate(records, start=2):
        ws.append([
            rec["report_date"],
            rec["seller"],
            rec["order_id"],
            rec["supply_id"],
            rec["created_at"],
            rec["created_date"],
            rec["price_rub"],
            rec["currency"],
            rec["nm_id"],
            rec["article"],
            rec["title"],
            rec["brand"],
            rec["subject"],
            rec["sku"],
            rec["warehouse_id"],
            rec["office_id"],
            rec["status_human"],
            rec["supplier_status"],
            rec["wb_status"],
            rec["is_b2b"],
            rec["rid"],
        ])
        ws.cell(row=r_idx, column=7).number_format = "#,##0.00"

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(raw_headers))}{max(len(records) + 1, 1)}"
    _auto_fit_columns(ws)



def build_excel_report_general(
    config: AppConfig,
    seller_name: str = "ИП (WB)",
    logger: Optional[logging.Logger] = None,
) -> Path:
    log = logger or setup_logger(config.logs_dir, name="wb_report_general")
    db = Database(config.db_path)
    report_date_str = datetime.now().strftime("%Y-%m-%d")

    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT
                o.*,
                c.title AS card_title,
                c.brand AS card_brand,
                c.subject_name AS card_subject
            FROM fbs_orders o
            LEFT JOIN product_cards c ON o.nm_id = c.nm_id
            ORDER BY o.created_at DESC
            """
        ).fetchall()

    records: List[Dict[str, Any]] = []
    for r in rows:
        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
        created_iso = r["created_at"] or ""
        created_date = created_iso[:10] if len(created_iso) >= 10 else created_iso
        raw_price = r["converted_price"] if r["converted_price"] is not None else (r["price"] or 0)
        price_rub = round(float(raw_price) / 100.0, 2)
        is_b2b = "Да" if (raw.get("options") or {}).get("isB2B") else "Нет"

        records.append({
            "raw": raw,
            "report_date": report_date_str,
            "seller": str(seller_name),
            "order_id": r["id"],
            "supply_id": r["supply_id"] or "-",
            "created_at": created_iso,
            "created_date": created_date,
            "price_rub": price_rub,
            "currency": "₽",
            "nm_id": r["nm_id"] or "",
            "article": r["article"] or "Без артикула",
            "title": r["card_title"] or "",
            "brand": r["card_brand"] or "",
            "subject": r["card_subject"] or "",
            "sku": r["sku"] or "",
            "warehouse_id": r["warehouse_id"] or "",
            "office_id": r["office_id"] or "",
            "status_human": _human_status(r["supplier_status"], r["wb_status"]),
            "supplier_status": r["supplier_status"] or "",
            "wb_status": r["wb_status"] or "",
            "is_b2b": is_b2b,
            "rid": r["rid"] or "",
        })


    wb = Workbook()
    _build_sheet_raw_json(wb, records)
    _build_sheet_pivot_articles(wb, records)
    _build_sheet_daily(wb, records)
    _build_sheet_registry(wb, records)

    ts = datetime.now().strftime(TIMESTAMP_FMT)
    report_path = config.reports_dir / f"wb_general_report_{ts}.xlsx"
    wb.save(report_path)
    log.info("Общий сводный отчёт сформирован: %s (строк: %d)", report_path, len(records))
    return report_path


def main() -> None:
    config = AppConfig()
    report_path = build_and_upload_report(config)
    print(f"Отчёт сохранён: {report_path}")

if __name__ == "__main__":
    main()
