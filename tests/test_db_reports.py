from datetime import datetime

from wb_reporter.db import WbDatabase
from wb_reporter.reports import build_registry_report
from openpyxl import load_workbook

SALE = {
    "saleID": "S1",
    "rid": "R1",
    "date": "2026-10-05T12:00:00",
    "article": "SKU-1",
    "subjectName": "Рюкзак",
    "brandName": "TestBrand",
    "warehouseName": "Коледино",
    "totalPrice": 2954800,
    "discountPercent": 5,
    "finishedPrice": 2807060,
    "isCancel": False,
}


def test_upsert_sales_no_duplicates_and_rubles(cfg):
    db = WbDatabase(cfg)
    n = db.upsert_sales([SALE])
    assert n == 1
    db.upsert_sales([SALE])  # повторный апсерт
    sales = db.load_sales(datetime(2026, 10, 1), datetime(2026, 10, 31))
    assert len(sales) == 1
    assert sales[0].total_price == 29548.0      # копейки -> рубли
    assert sales[0].finished_price == 28070.6


def test_upsert_orders_with_status(cfg):
    db = WbDatabase(cfg)
    order = {"id": "777", "article": "SKU-1", "createdAt": "2026-10-05T10:00:00", "price": 2500}
    status_map = {"777": {"wbStatus": "delivered", "supplierStatus": "complete"}}
    db.upsert_orders([order], status_map)
    orders = db.load_orders(datetime(2026, 10, 1), datetime(2026, 10, 31))
    assert orders[0].wb_status == "delivered"
    assert orders[0].id == "777"


def test_registry_report_built_from_db(cfg):
    db = WbDatabase(cfg)
    db.upsert_sales([SALE])
    out = build_registry_report(db, cfg, datetime(2026, 10, 1), datetime(2026, 10, 31))
    wb = load_workbook(out)
    assert wb.sheetnames == ["Реестр", "По дням", "По артикулам"]
    ws = wb["Реестр"]
    row = [c.value for c in ws[2]]
    assert row[0] == "Коледино"
    assert row[2] == "Доставлен"
    assert row[7] == 28070.6


def test_report_works_outside_service(cfg, tmp_path):
    """Отчёт строится по накопленным данным без обращения к сети."""
    db = WbDatabase(cfg)
    db.upsert_sales([SALE])
    out = build_registry_report(db, cfg, datetime(2026, 10, 1), datetime(2026, 10, 31), out_path=tmp_path / "r.xlsx")
    assert out.exists()
