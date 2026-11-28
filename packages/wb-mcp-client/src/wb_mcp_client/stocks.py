import argparse
import logging
import threading
from typing import Dict, Optional

from wb_mcp_client.app_config import AppConfig
from wb_mcp_client.db import Database
from wb_mcp_client.logger import setup_logger
from wb_mcp_client.wb_client import WBApiClient


def sync_stocks_now(
    config: Optional[AppConfig] = None,
    logger: Optional[logging.Logger] = None,
    stop_event: Optional[threading.Event] = None,
    use_sandbox: bool = False,
) -> Dict[str, int]:
    """Синхронизирует склады продавца и остатки FBS по всем известным баркодам."""
    cfg = config or AppConfig()
    log = logger or setup_logger(cfg.logs_dir, name="wb_stocks_sync")
    db = Database(cfg.db_path)
    client = WBApiClient(cfg, log, use_sandbox=use_sandbox)

    try:
        warehouses = client.fetch_warehouses(stop_event=stop_event)
        wh_count = db.upsert_warehouses(warehouses)
        log.info("Обновлено складов продавца: %d", wh_count)

        skus = db.get_all_known_skus()
        if not skus:
            log.warning("В БД нет известных баркодов (SKU) для запроса остатков. Сначала синхронизируйте карточки.")
            return {"warehouses": wh_count, "stocks_updated": 0}

        total_stocks = 0
        for wh in warehouses:
            if stop_event and stop_event.is_set():
                break
            wh_id = wh["id"]
            stocks = client.fetch_warehouse_stocks(wh_id, skus, stop_event=stop_event)
            saved = db.upsert_stocks(wh_id, stocks)
            total_stocks += saved
            log.info("Склад '%s' (ID=%s): обновлено остатков по %d SKU", wh.get("name"), wh_id, saved)

        return {"warehouses": wh_count, "stocks_updated": total_stocks}
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Синхронизация складов и остатков FBS Wildberries")
    parser.add_argument("--sandbox", action="store_true", help="Использовать песочницу WB")
    args = parser.parse_args()

    res = sync_stocks_now(use_sandbox=args.sandbox)
    print(f"Синхронизировано складов: {res['warehouses']}, позиций остатков: {res['stocks_updated']}")


if __name__ == "__main__":
    main()
