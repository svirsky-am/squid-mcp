import logging
import threading
from typing import Optional

from wb_mcp_client.app_config import AppConfig
from wb_mcp_client.db import Database
from wb_mcp_client.logger import setup_logger
from wb_mcp_client.wb_client import WBApiClient


def sync_cards_now(
    config: Optional[AppConfig] = None,
    logger: Optional[logging.Logger] = None,
    stop_event: Optional[threading.Event] = None,
    use_sandbox: bool = False,
) -> int:
    """Синхронизирует карточки товаров WB в SQLite и возвращает количество обновлённых записей."""
    cfg = config or AppConfig()
    log = logger or setup_logger(cfg.logs_dir, name="wb_cards_sync")
    db = Database(cfg.db_path)
    client = WBApiClient(cfg, log, use_sandbox=use_sandbox)
    try:
        cards = client.fetch_product_cards(stop_event=stop_event)
        saved = db.upsert_cards(cards)
        log.info("Синхронизировано карточек товаров в БД (sandbox=%s): %d", use_sandbox, saved)
        return saved
    finally:
        client.close()

def main() -> None:
    """Точка входа CLI для ручного обновления карточек товаров."""
    saved = sync_cards_now()
    print(f"Синхронизировано карточек товаров: {saved}")


if __name__ == "__main__":
    main()