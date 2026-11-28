import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._write_lock = threading.Lock()
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_schema(self) -> None:
        with self._write_lock, self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS warehouses (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    office_id INTEGER,
                    cargo_type INTEGER,
                    delivery_type INTEGER,
                    raw_json TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fbs_stocks (
                    warehouse_id INTEGER NOT NULL,
                    sku TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (warehouse_id, sku)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fbs_orders (
                    id INTEGER PRIMARY KEY,
                    order_uid TEXT,
                    rid TEXT,
                    created_at TEXT,
                    article TEXT,
                    nm_id INTEGER,
                    chrt_id INTEGER,
                    sku TEXT,
                    price REAL,
                    converted_price REAL,
                    currency_code INTEGER,
                    converted_currency_code INTEGER,
                    delivery_type TEXT,
                    supply_id TEXT,
                    warehouse_id INTEGER,
                    office_id INTEGER,
                    cargo_type INTEGER,
                    is_zero_order INTEGER,
                    supplier_status TEXT,
                    wb_status TEXT,
                    raw_json TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fbs_orders_created_at ON fbs_orders(created_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fbs_orders_article ON fbs_orders(article);")
            conn.commit()
            # Внутри _init_schema(self):
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS product_cards (
                    nm_id INTEGER PRIMARY KEY,
                    imt_id INTEGER,
                    vendor_code TEXT,
                    title TEXT,
                    brand TEXT,
                    subject_id INTEGER,
                    subject_name TEXT,
                    skus_json TEXT,
                    photo_url TEXT,
                    wb_updated_at TEXT,
                    raw_json TEXT,
                    synced_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_product_cards_vendor_code ON product_cards(vendor_code);")

    def upsert_orders(self, orders: List[Dict[str, Any]]) -> int:
        if not orders:
            return 0

        rows = []
        for o in orders:
            skus = o.get("skus") or []
            rows.append(
                (
                    o["id"],
                    o.get("orderUid"),
                    o.get("rid"),
                    o.get("createdAt"),
                    o.get("article"),
                    o.get("nmId"),
                    o.get("chrtId"),
                    skus[0] if skus else None,
                    o.get("price"),
                    o.get("convertedPrice"),
                    o.get("currencyCode"),
                    o.get("convertedCurrencyCode"),
                    o.get("deliveryType"),
                    o.get("supplyId"),
                    o.get("warehouseId"),
                    o.get("officeId"),
                    o.get("cargoType"),
                    1 if o.get("isZeroOrder") else 0,
                    json.dumps(o, ensure_ascii=False),
                )
            )

        with self._write_lock, self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO fbs_orders (
                    id, order_uid, rid, created_at, article, nm_id, chrt_id, sku,
                    price, converted_price, currency_code, converted_currency_code,
                    delivery_type, supply_id, warehouse_id, office_id, cargo_type,
                    is_zero_order, raw_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    supply_id = excluded.supply_id,
                    price = excluded.price,
                    converted_price = excluded.converted_price,
                    delivery_type = excluded.delivery_type,
                    raw_json = excluded.raw_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
            conn.commit()
        return len(rows)

    def update_order_statuses(self, statuses: List[Dict[str, Any]]) -> int:
        if not statuses:
            return 0
        rows = [(s.get("supplierStatus"), s.get("wbStatus"), s["id"]) for s in statuses]
        with self._write_lock, self.connect() as conn:
            conn.executemany(
                """
                UPDATE fbs_orders
                SET supplier_status = ?, wb_status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                rows,
            )
            conn.commit()
        return len(rows)

    def upsert_cards(self, cards: List[Dict[str, Any]]) -> int:
        if not cards:
            return 0

        rows = []
        for c in cards:
            skus: List[str] = []
            for size in c.get("sizes") or []:
                skus.extend(size.get("skus") or [])


            photos = c.get("photos") or []
            first_photo = next(iter(photos), {})
            photo_url = first_photo.get("big") or first_photo.get("c246x328") or ""

            rows.append(
                (
                    c["nmID"],
                    c.get("imtID"),
                    c.get("vendorCode"),
                    c.get("title"),
                    c.get("brand"),
                    c.get("subjectID"),
                    c.get("subjectName"),
                    json.dumps(skus, ensure_ascii=False),
                    photo_url,
                    c.get("updatedAt"),
                    json.dumps(c, ensure_ascii=False),
                )
            )

        with self._write_lock, self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO product_cards (
                    nm_id, imt_id, vendor_code, title, brand,
                    subject_id, subject_name, skus_json, photo_url,
                    wb_updated_at, raw_json, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(nm_id) DO UPDATE SET
                    imt_id = excluded.imt_id,
                    vendor_code = excluded.vendor_code,
                    title = excluded.title,
                    brand = excluded.brand,
                    subject_id = excluded.subject_id,
                    subject_name = excluded.subject_name,
                    skus_json = excluded.skus_json,
                    photo_url = excluded.photo_url,
                    wb_updated_at = excluded.wb_updated_at,
                    raw_json = excluded.raw_json,
                    synced_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
            conn.commit()
        return len(rows)

    def upsert_warehouses(self, warehouses: List[Dict[str, Any]]) -> int:
        if not warehouses:
            return 0
        rows = [
            (
                w["id"],
                w.get("name", ""),
                w.get("officeId"),
                w.get("cargoType"),
                w.get("deliveryType"),
                json.dumps(w, ensure_ascii=False),
            )
            for w in warehouses
        ]
        with self._write_lock, self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO warehouses (id, name, office_id, cargo_type, delivery_type, raw_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    office_id = excluded.office_id,
                    cargo_type = excluded.cargo_type,
                    delivery_type = excluded.delivery_type,
                    raw_json = excluded.raw_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
            conn.commit()
        return len(rows)

    def get_all_known_skus(self) -> List[str]:
        """Собирает уникальный список всех баркодов из справочника карточек и истории заказов."""
        skus_set = set()
        with self.connect() as conn:
            card_rows = conn.execute("SELECT skus_json FROM product_cards WHERE skus_json IS NOT NULL").fetchall()
            for r in card_rows:
                try:
                    for s in json.loads(r["skus_json"]):
                        if s:
                            skus_set.add(str(s))
                except Exception:
                    pass

            order_rows = conn.execute("SELECT DISTINCT sku FROM fbs_orders WHERE sku IS NOT NULL AND sku != ''").fetchall()
            for r in order_rows:
                skus_set.add(str(r["sku"]))

        return sorted(skus_set)

    def upsert_stocks(self, warehouse_id: int, stocks: List[Dict[str, Any]]) -> int:
        if not stocks:
            return 0
        rows = [(warehouse_id, str(item["sku"]), int(item.get("amount", 0))) for item in stocks]
        with self._write_lock, self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO fbs_stocks (warehouse_id, sku, amount, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(warehouse_id, sku) DO UPDATE SET
                    amount = excluded.amount,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
            conn.commit()
        return len(rows)
