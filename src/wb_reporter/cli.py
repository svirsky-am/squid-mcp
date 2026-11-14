"""CLI: запуск службы, разовый sync, отчёт вне службы, дублирование карточек.

    python -m wb_reporter.cli run                        # служба (цикл fetch)
    python -m wb_reporter.cli sync                      # один fetch без цикла
    python -m wb_reporter.cli report --from 2026-10-01 --to 2026-10-31
    python -m wb_reporter.cli cards                     # разовая выгрузка карточек
    python -m wb_reporter.cli copy-card --nm-id 123 --article NEW-1 --char "Название=Новое"
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime

from .app_config import AppConfig
from . import cards as cards_mod, reports
from .db import WbDatabase
from .logging_setup import setup_logging
from .scheduler import cards_worker, run_service, sync_all, run_report
from .wb_api import WbApiClient

logger = logging.getLogger(__name__)


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def cmd_report(args: argparse.Namespace, cfg: AppConfig) -> None:
    db = WbDatabase(cfg)
    date_to = _parse_date(args.to) if args.to else datetime.now()
    date_from = _parse_date(args.from_date) if args.from_date else date_to.replace(day=1)
    out = reports.build_registry_report(db, cfg, date_from, date_to, args.out)
    logger.info("Готово: %s", out)


def cmd_sync(args: argparse.Namespace, cfg: AppConfig) -> None:
    api = WbApiClient(cfg)
    db = WbDatabase(cfg)
    asyncio.run(sync_all(cfg, api, db))
    if not args.no_report:
        out = asyncio.run(run_report(cfg, db))
        logger.info("Отчёт: %s", out)


def cmd_run(args: argparse.Namespace, cfg: AppConfig) -> None:
    asyncio.run(run_service(cfg))


def cmd_cards(args: argparse.Namespace, cfg: AppConfig) -> None:
    api = WbApiClient(cfg)
    db = WbDatabase(cfg)

    async def once() -> None:
        cards = await api.fetch_cards()
        n = await asyncio.to_thread(db.upsert_cards, cards)
        logger.info("Карточек в БД: %d", n)

    asyncio.run(once())


def cmd_copy_card(args: argparse.Namespace, cfg: AppConfig) -> None:
    db = WbDatabase(cfg)
    record = db.get_card(args.nm_id)
    if record is None or not record.raw:
        raise SystemExit(f"Карточка nmID={args.nm_id} не найдена в БД — сначала выполните 'cards'")
    changes: dict = {}
    if args.article:
        changes["vendorCode"] = args.article
    if args.title:
        changes["title"] = args.title
    for pair in args.char or []:
        key, _, value = pair.partition("=")
        if key and value:
            changes[key] = value
    payload = cards_mod.build_duplicate_payload(record.raw, changes)
    api = WbApiClient(cfg)

    async def send() -> None:
        if args.update_only:
            result = await api.update_cards([cards_mod.apply_changes(record.raw, changes)])
        else:
            result = await api.upload_cards(payload)
        logger.info("Ответ WB: %s", result)

    asyncio.run(send())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wb_reporter", description="WB reporter")
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="служба: периодический fetch + отчёты")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("sync", help="один fetch всех эндпойнтов (+ отчёт)")
    p.add_argument("--no-report", action="store_true")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("report", help="отчёт вне службы по данным из БД")
    p.add_argument("--from", dest="from_date", default=None)
    p.add_argument("--to", dest="to", default=None)
    p.add_argument("--out", default=None, help="путь к xlsx")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("cards", help="разовая выгрузка карточек товаров")
    p.set_defaults(func=cmd_cards)

    p = sub.add_parser("copy-card", help="дублировать/изменить карточку")
    p.add_argument("--nm-id", type=int, required=True)
    p.add_argument("--article", default=None, help="новый vendorCode")
    p.add_argument("--title", default=None, help="новое название")
    p.add_argument("--char", action="append", default=[], help="Характеристика=значение")
    p.add_argument("--update-only", action="store_true", help="править существующую (cards/update)")
    p.set_defaults(func=cmd_copy_card)

    return parser


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = AppConfig()
    setup_logging(cfg.work_dir, args.log_level)
    args.func(args, cfg)


if __name__ == "__main__":
    main()
