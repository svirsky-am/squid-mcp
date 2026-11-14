"""SQLite-хранилище через SQLAlchemy 2.0.

Цены статистического API приходят в копейках — при записи переводятся в рубли.
Апсерт по уникальному ключу исключает дубли при повторных выгрузках.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import DateTime, Float, Integer, JSON, String, select, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .app_config import AppConfig
from .wb_api import pick_status

logger = logging.getLogger(__name__)


def _to_rubles(value: Any) -> float:
    """Копейки -> рубли; пустые значения -> 0.0."""
    try:
        return round(float(value) / 100.0, 2)
    except (TypeError, ValueError):
        return 0.0


class Base(DeclarativeBase):
    pass


class Order(Base):
    """Сборочное задание FBS из /api/v3/orders + статус из /orders/status."""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    article: Mapped[str] = mapped_column(String, index=True, default="")
    sku: Mapped[int] = mapped_column(Integer, default=0)
    warehouse_id: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    wb_status: Mapped[str] = mapped_column(String, default="")
    supplier_status: Mapped[str] = mapped_column(String, default="")
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class Sale(Base):
    """Продажа/возврат из statistics-api /api/v1/supplier/sales."""

    __tablename__ = "sales"

    sale_id: Mapped[str] = mapped_column(String, primary_key=True)
    rid: Mapped[str] = mapped_column(String, index=True, default="")
    date: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    article: Mapped[str] = mapped_column(String, index=True, default="")
    subject: Mapped[str] = mapped_column(String, default="")
    brand: Mapped[str] = mapped_column(String, default="")
    category: Mapped[str] = mapped_column(String, default="")
    warehouse_name: Mapped[str] = mapped_column(String, default="")
    total_price: Mapped[float] = mapped_column(Float, default=0.0)  # рубли
    discount_percent: Mapped[float] = mapped_column(Float, default=0.0)
    finished_price: Mapped[float] = mapped_column(Float, default=0.0)  # рубли
    is_cancel: Mapped[bool] = mapped_column(default=False)
    income_id: Mapped[str] = mapped_column(String, default="")
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class Card(Base):
    """Карточка товара из /content/v2/get/cards/list."""

    __tablename__ = "cards"

    nm_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article: Mapped[str] = mapped_column(String, index=True, default="")
    title: Mapped[str] = mapped_column(String, default="")
    brand: Mapped[str] = mapped_column(String, default="")
    category: Mapped[str] = mapped_column(String, default="")
    attributes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def normalize_order(row: Dict[str, Any], status_obj: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    status_obj = status_obj or {}
    created = _parse_dt(row.get("createdAt"))
    if created is None and row.get("date"):
        created = _parse_dt(row.get("date"))
    return {
        "id": str(row.get("id") or row.get("orderID") or ""),
        "article": str(row.get("article") or ""),
        "sku": int(row.get("sku") or 0),
        "warehouse_id": int(row.get("warehouseId") or 0),
        "price": float(row.get("price") or 0.0),
        "created_at": created,
        "wb_status": str(status_obj.get("wbStatus") or ""),
        "supplier_status": str(status_obj.get("supplierStatus") or ""),
        "raw": row,
    }


def normalize_sale(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sale_id": str(row.get("saleID") or ""),
        "rid": str(row.get("rid") or ""),
        "date": _parse_dt(row.get("date")),
        "article": str(row.get("supplierOperatorArticle") or row.get("article") or ""),
        "subject": str(row.get("subjectName") or ""),
        "brand": str(row.get("brandName") or ""),
        "category": str(row.get("categoryName") or ""),
        "warehouse_name": str(row.get("warehouseName") or ""),
        "total_price": _to_rubles(row.get("totalPrice")),
        "discount_percent": float(row.get("discountPercent") or 0.0),
        "finished_price": _to_rubles(row.get("finishedPrice")),
        "is_cancel": bool(row.get("isCancel")),
        "income_id": str(row.get("incomeID") or ""),
        "raw": row,
    }


def normalize_card(card: Dict[str, Any]) -> Dict[str, Any]:
    characteristics = card.get("characteristics") or []
    attrs = {}
    for c in characteristics:
        if isinstance(c, dict) and c.get("name"):
            attrs[c["name"]] = c.get("value")
    return {
        "nm_id": int(card.get("nmID") or 0),
        "article": str(card.get("vendorCode") or ""),
        "title": str(card.get("title") or ""),
        "brand": str(card.get("brand") or ""),
        "category": str(card.get("category") or ""),
        "attributes": attrs,
        "raw": card,
    }


class WbDatabase:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.engine = create_engine(cfg.database_url, future=True)
        Base.metadata.create_all(self.engine)
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    # ------------------- upsert -------------------

    def upsert_orders(self, rows: Sequence[Dict[str, Any]], status_map: Optional[Dict[str, Dict[str, Any]]] = None) -> int:
        status_map = status_map or {}
        with Session(self.engine) as session:
            for row in rows:
                data = normalize_order(row, status_map.get(str(row.get("id") or "")))
                if not data["id"]:
                    continue
                existing = session.get(Order, data["id"])
                if existing is None:
                    session.add(Order(**data))
                else:
                    for key, value in data.items():
                        if value not in (None, "") or key in ("price",):
                            setattr(existing, key, value)
            session.commit()
        return len(rows)

    def upsert_sales(self, rows: Sequence[Dict[str, Any]]) -> int:
        with Session(self.engine) as session:
            for row in rows:
                data = normalize_sale(row)
                if not data["sale_id"]:
                    continue
                existing = session.get(Sale, data["sale_id"])
                if existing is None:
                    session.add(Sale(**data))
                else:
                    for key, value in data.items():
                        setattr(existing, key, value)
            session.commit()
        return len(rows)

    def upsert_cards(self, cards: Sequence[Dict[str, Any]]) -> int:
        with Session(self.engine) as session:
            for card in cards:
                data = normalize_card(card)
                if not data["nm_id"]:
                    continue
                session.merge(Card(**data))
            session.commit()
        return len(cards)

    # ------------------- чтение -------------------

    def load_sales(self, date_from: datetime, date_to: datetime) -> List[Sale]:
        with Session(self.engine) as session:
            stmt = select(Sale).where(Sale.date >= date_from, Sale.date <= date_to).order_by(Sale.date)
            return list(session.scalars(stmt))

    def load_orders(self, date_from: datetime, date_to: datetime) -> List[Order]:
        with Session(self.engine) as session:
            stmt = select(Order).where(Order.created_at >= date_from, Order.created_at <= date_to)
            return list(session.scalars(stmt))

    def load_cards(self) -> List[Card]:
        with Session(self.engine) as session:
            return list(session.scalars(select(Card).order_by(Card.nm_id)))

    def get_card(self, nm_id: int) -> Optional[Card]:
        with Session(self.engine) as session:
            return session.get(Card, int(nm_id))
