"""Служба: периодический fetch нескольких эндпойнтов в пуле потоков,
поток карточек товаров и построение сводного отчёта после каждого fetch.

Запуск: python -m wb_reporter.cli run
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from . import cards as cards_mod
from . import gdrive, reports
from .app_config import AppConfig
from .db import WbDatabase
from .wb_api import WbApiClient, pick_status

logger = logging.getLogger(__name__)


async def _sync_one(name: str, api: WbApiClient, db: WbDatabase, date_from: datetime) -> str:
    if name == "orders":
        orders = await api.fetch_orders(date_from)
        ids = [str(o.get("id", "")) for o in orders if o.get("id")]
        status_map: Dict[str, Dict[str, Any]] = {}
        if ids:
            for s in await api.fetch_orders_status(ids):
                sid = str(s.get("id") or "")
                if sid:
                    status_map[sid] = {
                        "wbStatus": s.get("wbStatus") or pick_status(s),
                        "supplierStatus": s.get("supplierStatus") or "",
                    }
        n = await asyncio.to_thread(db.upsert_orders, orders, status_map)
    elif name == "sales":
        rows = await api.fetch_sales(date_from)
        n = await asyncio.to_thread(db.upsert_sales, rows)
    elif name == "incomes":
        rows = await api.fetch_incomes(date_from)
        logger.info("incomes: получено %d записей (в БД не складываются)", len(rows))
        return f"{name}: {len(rows)} записей"
    elif name == "stocks":
        rows = await api.fetch_stocks()
        logger.info("stocks: получено %d записей (в БД не складываются)", len(rows))
        return f"{name}: {len(rows)} записей"
    elif name == "warehouses":
        rows = await api.fetch_warehouses()
        logger.info("warehouses: %d складов", len(rows))
        return f"{name}: {len(rows)} записей"
    else:
        raise ValueError(f"Неизвестный эндпойнт: {name}")
    return f"{name}: {n} строк в БД"


async def sync_all(cfg: AppConfig, api: WbApiClient, db: WbDatabase) -> List[str]:
    """Выгрузка всех эндпойнтов параллельно (каждый — в своём потоке пула)."""
    date_from = datetime.now() - timedelta(days=cfg.lookback_days)
    results = await asyncio.gather(
        *[_sync_one(name, api, db, date_from) for name in cfg.endpoints],
        return_exceptions=True,
    )
    out: List[str] = []
    for name, result in zip(cfg.endpoints, results):
        if isinstance(result, Exception):
            logger.error("Эндпойнт %s завершился с ошибкой: %s", name, result)
            out.append(f"{name}: ОШИБКА {result}")
        else:
            logger.info("fetch %s", result)
            out.append(str(result))
    return out


async def run_report(cfg: AppConfig, db: WbDatabase) -> Any:
    now = datetime.now()
    out = await asyncio.to_thread(
        reports.build_registry_report, db, cfg, now - timedelta(days=cfg.lookback_days), now
    )
    if cfg.gdrive_enabled:
        await asyncio.to_thread(gdrive.upload_xlsx_as_sheets, cfg, out)
    return out


async def cards_worker(cfg: AppConfig, api: WbApiClient, db: WbDatabase) -> None:
    """Отдельный поток: выгрузка карточек товаров по своему интервалу."""
    while True:
        try:
            cards = await api.fetch_cards()
            n = await asyncio.to_thread(db.upsert_cards, cards)
            logger.info("cards: %d карточек в БД", n)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Поток карточек упал с ошибкой")
        await asyncio.sleep(cfg.cards_interval_sec)


async def run_service(cfg: AppConfig) -> None:
    api = WbApiClient(cfg)
    db = WbDatabase(cfg)

    logger.info("Проверка подключения к WB API (GET /ping)...")
    await api.ping()
    logger.info("Соединение в порядке")

    cards_task = asyncio.create_task(cards_worker(cfg, api, db), name="cards-worker")
    try:
        while True:
            await sync_all(cfg, api, db)
            try:
                out = await run_report(cfg, db)
                logger.info("Сводный отчёт готов: %s", out)
            except Exception:
                logger.exception("Не удалось построить отчёт")
            logger.info("Следующий fetch через %d мин", cfg.fetch_interval_minutes)
            await asyncio.sleep(cfg.fetch_interval_sec)
    finally:
        cards_task.cancel()
