import asyncio
import signal
import json
from datetime import datetime, timedelta
from src.config import AppConfig
from src.wb_client import WBClient
from src.db import init_db, save_orders, get_db_connection
from src.logger_setup import get_logger

logger = get_logger(__name__)
shutdown_event = asyncio.Event()

def _signal_handler():
    logger.info("Получен сигнал завершения работы (SIGINT/SIGTERM)...")
    shutdown_event.set()

async def fetch_orders_task(client: WBClient, config: AppConfig):
    while not shutdown_event.is_set():
        try:
            logger.info("Запуск задачи: получение заказов (FBS)")
            date_from = (datetime.utcnow() - timedelta(days=config.lookback_days)).isoformat() + "Z"
            params = {"limit": 1000, "dateFrom": date_from}
            
            data = await client.request("/api/v3/orders", method="GET", params=params)
            if data and "orders" in data:
                save_orders(data["orders"])
        except Exception as e:
            logger.error(f"Ошибка в задаче получения заказов: {e}")
            
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=config.fetch_interval_sec)
            break
        except asyncio.TimeoutError:
            continue

async def fetch_cards_task(client: WBClient, config: AppConfig):
    while not shutdown_event.is_set():
        try:
            logger.info("Запуск задачи: получение карточек товаров")
            payload = {"settings": {"cursor": {"limit": 100}, "filter": {"withPhoto": -1}}}
            data = await client.request("/api/v2/cards/list", method="POST", json=payload)
            
            if data and "cards" in data:
                conn = get_db_connection()
                cursor = conn.cursor()
                for card in data["cards"]:
                    cursor.execute("INSERT OR REPLACE INTO cards (nmID, raw_json) VALUES (?, ?)",
                                   (card.get("nmID"), json.dumps(card, ensure_ascii=False)))
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"Ошибка в задаче получения карточек: {e}")
            
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=config.cards_interval_sec)
            break
        except asyncio.TimeoutError:
            continue

async def run_service():
    config = AppConfig()
    init_db()
    client = WBClient(config)
    
    # Первичный ping при старте службы
    logger.info("Первичное обращение (ping) к /api/v2/cards/list...")
    try:
        await client.request("/api/v2/cards/list", method="POST", json={"settings": {"cursor": {"limit": 1}, "filter": {"withPhoto": -1}}})
        logger.info("Ping успешен. Запуск основных потоков.")
    except Exception as e:
        logger.error(f"Ошибка при первичном ping: {e}. Проверьте API_TOKEN.")
        
    tasks = [
        asyncio.create_task(fetch_orders_task(client, config)),
        asyncio.create_task(fetch_cards_task(client, config))
    ]
    
    await asyncio.gather(*tasks)
    logger.info("Служба полностью остановлена.")