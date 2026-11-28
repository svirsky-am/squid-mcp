import argparse
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from wb_mcp_client.app_config import AppConfig
from wb_mcp_client.db import Database
from wb_mcp_client.logger import setup_logger
from wb_mcp_client.wb_client import WBApiClient


def sync_funnel_now(
    config: Optional[AppConfig] = None,
    days: Optional[int] = None,
    logger: Optional[logging.Logger] = None,
    stop_event: Optional[threading.Event] = None,
) -> int:
    """Синхронизирует воронку продаж WB в SQLite и возвращает число обновлённых карточек."""
    cfg = config or AppConfig()
    log = logger or setup_logger(cfg.logs_dir, name="wb_funnel_sync")
    db = Database(cfg.db_path)
    client = WBApiClient(cfg, log)

    lookback = days if days is not None else cfg.funnel_lookback_days
    now_utc = datetime.now(timezone.utc)
    period_start = (now_utc - timedelta(days=lookback)).strftime("%Y-%m-%d")
    period_end = now_utc.strftime("%Y-%m-%d")

    try:
        products = client.fetch_sales_funnel(
            period_start=period_start,
            period_end=period_end,
            stop_event=stop_event,
        )
        saved = db.upsert_sales_funnel(products, period_start=period_start, period_end=period_end)
        log.info(
            "Синхронизировано карточек воронки (%s — %s): %d",
            period_start,
            period_end,
            saved,
        )
        return saved
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Синхронизация воронки продаж Wildberries")
    parser.add_argument("--days", type=int, default=7, help="Глубина периода в днях (по умолчанию 7)")
    args = parser.parse_args()

    saved = sync_funnel_now(days=args.days)
    print(f"Синхронизировано карточек воронки: {saved}")


if __name__ == "__main__":
    main()