"""MCP-сервер для агента (Yandex AI Studio / локально).

Инструменты: ping_wb, sync_data, build_report, list_cards, copy_card.
Запуск: MCP_TRANSPORT=streamable-http python -m wb_reporter.mcp_server
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from . import cards as cards_mod, reports
from .app_config import AppConfig
from .db import WbDatabase
from .logging_setup import setup_logging
from .scheduler import run_report, sync_all
from .wb_api import WbApiClient

cfg = AppConfig()
setup_logging(cfg.work_dir)
db = WbDatabase(cfg)

mcp = FastMCP("wb-reporter")


@mcp.tool()
def ping_wb() -> str:
    """Проверка подключения к WB API."""
    asyncio.run(WbApiClient(cfg).ping())
    return "OK"


@mcp.tool()
def sync_data() -> str:
    """Разовый fetch всех эндпойнтов в БД + построение сводного отчёта."""
    async def _go() -> str:
        api = WbApiClient(cfg)
        lines = await sync_all(cfg, api, db)
        out = await run_report(cfg, db)
        return "; ".join(lines) + f"; отчёт: {out}"

    return asyncio.run(_go())


@mcp.tool()
def build_report(date_from: str = "", date_to: str = "") -> str:
    """Сводный xlsx по данным из БД за период YYYY-MM-DD..YYYY-MM-DD."""
    to = datetime.strptime(date_to, "%Y-%m-%d") if date_to else datetime.now()
    frm = datetime.strptime(date_from, "%Y-%m-%d") if date_from else to.replace(day=1)
    out = reports.build_registry_report(db, cfg, frm, to)
    return str(out)


@mcp.tool()
def list_cards(limit: int = 20) -> str:
    """Список карточек товаров из БД."""
    rows = db.load_cards()[:limit]
    return "\n".join(f"{c.nm_id} | {c.article} | {c.title}" for c in rows) or "БД пуста"


@mcp.tool()
def copy_card(nm_id: int, article: str = "", title: str = "", characteristics: str = "") -> str:
    """Дублировать карточку (article/title/characteristics 'Имя=знач;Имя2=знач2')."""
    record = db.get_card(nm_id)
    if record is None or not record.raw:
        return f"Карточка nmID={nm_id} не найдена"
    changes: dict = {}
    if article:
        changes["vendorCode"] = article
    if title:
        changes["title"] = title
    for pair in characteristics.split(";"):
        key, _, value = pair.partition("=")
        if key.strip() and value:
            changes[key.strip()] = value
    api = WbApiClient(cfg)
    payload = cards_mod.build_duplicate_payload(record.raw, changes)
    result = asyncio.run(api.upload_cards(payload))
    return f"Отправлено на /content/v2/cards/upload: {result}"


if __name__ == "__main__":
    mcp.run()
