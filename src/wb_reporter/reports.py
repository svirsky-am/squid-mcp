"""Сводные xlsx-отчёты: реестр + срезы по дням и артикулам.

Отчёт строится из БД (SQLite), сеть не задействована — поэтому одинаково
работает и внутри службы после fetch, и отдельно по накопленным данным.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .app_config import AppConfig
from .db import WbDatabase

logger = logging.getLogger(__name__)

HEADER_FILL = PatternFill("solid", fgColor="4472C4")
HEADER_FONT = Font(color="FFFFFF", bold=True)
BORDER = Border(*[Side(style="thin", color="B0B0B0")] * 4)
CENTER = Alignment(horizontal="center", vertical="center")
MONEY_FMT = "#,##0.00"

REGISTRY_HEADERS = [
    "Магазин", "Номер отправления", "Статус", "Принят", "Кол-во",
    "Артикул", "Название товара", "Стоимость", "Склад",
]


def _status_for(
    sale_article: str,
    sale_date: Optional[datetime],
    status_map: Dict[tuple, str],
    is_cancel: bool,
) -> str:
    key = (sale_article, sale_date.date() if sale_date else None)
    matched = status_map.get(key)
    if matched:
        return matched
    return "Отменен" if is_cancel else "Доставлен"


def _registry_rows(db: WbDatabase, date_from: datetime, date_to: datetime) -> List[list]:
    sales = db.load_sales(date_from, date_to)
    orders = db.load_orders(date_from, date_to)
    status_map: Dict[tuple, str] = {}
    for o in orders:
        if o.created_at and (o.wb_status or o.supplier_status):
            status_map.setdefault((o.article, o.created_at.date()), o.wb_status or o.supplier_status)
    rows = []
    for s in sales:
        rows.append([
            s.warehouse_name,
            s.sale_id,
            _status_for(s.article, s.date, status_map, s.is_cancel),
            s.date.strftime("%d.%m.%Y %H:%M") if s.date else "",
            1,
            s.article,
            f"{s.brand} {s.subject}".strip(),
            s.finished_price,
            s.warehouse_name,
        ])
    return rows


def _by_day_rows(db: WbDatabase, date_from: datetime, date_to: datetime) -> List[list]:
    sales = db.load_sales(date_from, date_to)
    buckets: Dict[str, dict] = {}
    for s in sales:
        day = s.date.strftime("%Y-%m-%d") if s.date else "без даты"
        b = buckets.setdefault(day, {"qty": 0, "revenue": 0.0, "cancels": 0})
        b["qty"] += 1
        if s.is_cancel:
            b["cancels"] += 1
        else:
            b["revenue"] += s.finished_price
    rows = []
    for day in sorted(buckets):
        b = buckets[day]
        avg = round(b["revenue"] / b["qty"], 2) if b["qty"] else 0.0
        rows.append([day, b["qty"], b["revenue"], avg, b["cancels"]])
    return rows


def _by_article_rows(db: WbDatabase, date_from: datetime, date_to: datetime) -> List[list]:
    sales = db.load_sales(date_from, date_to)
    buckets: Dict[str, dict] = {}
    for s in sales:
        b = buckets.setdefault(
            s.article, {"name": f"{s.brand} {s.subject}".strip(), "qty": 0, "revenue": 0.0, "cancels": 0}
        )
        b["qty"] += 1
        if s.is_cancel:
            b["cancels"] += 1
        else:
            b["revenue"] += s.finished_price
    rows = []
    for article in sorted(buckets, key=lambda a: -buckets[a]["revenue"]):
        b = buckets[article]
        avg = round(b["revenue"] / b["qty"], 2) if b["qty"] else 0.0
        rows.append([article, b["name"], b["qty"], b["revenue"], avg, b["cancels"]])
    return rows


def _write_sheet(ws, headers: Sequence[str], rows: Sequence[Sequence], money_cols: Sequence[int] = ()) -> None:
    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = BORDER
    for r, row in enumerate(rows, start=2):
        for c, value in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.border = BORDER
            if (c - 1) in money_cols:
                cell.number_format = MONEY_FMT
    for col in range(1, len(headers) + 1):
        width = max(
            [len(str(headers[col - 1]))]
            + [len(str(row[col - 1])) for row in rows if col - 1 < len(row)]
        )
        ws.column_dimensions[get_column_letter(col)].width = min(max(width + 2, 10), 60)
    ws.freeze_panes = "A2"


def build_registry_report(
    db: WbDatabase,
    cfg: AppConfig,
    date_from: datetime,
    date_to: datetime,
    out_path: Optional[Path] = None,
) -> Path:
    """Собирает xlsx: Реестр + По дням + По артикулам. Возвращает путь к файлу."""
    if out_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        out_path = cfg.work_dir / f"wb_report_{stamp}.xlsx"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Реестр"
    _write_sheet(ws, REGISTRY_HEADERS, _registry_rows(db, date_from, date_to), money_cols=(7,))

    ws2 = wb.create_sheet("По дням")
    _write_sheet(
        ws2,
        ["День", "Заказов", "Выручка", "Средний чек", "Отменено"],
        _by_day_rows(db, date_from, date_to),
        money_cols=(2, 3),
    )

    ws3 = wb.create_sheet("По артикулам")
    _write_sheet(
        ws3,
        ["Артикул", "Название товара", "Кол-во", "Выручка", "Средняя цена", "Отменено"],
        _by_article_rows(db, date_from, date_to),
        money_cols=(3, 4),
    )

    wb.save(out_path)
    logger.info("Отчёт сохранён: %s", out_path)
    return out_path
