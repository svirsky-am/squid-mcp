from datetime import datetime, timedelta
from wb_client import WBClient
from app_config import AppConfig
from db import SessionLocal, Order, Card
import logging

def fetch_orders(client: WBClient, config: AppConfig, logger: logging.Logger, Session):
    logger.info("Старт потока: Загрузка заказов (FBS)")
    url = f"{client.marketplace_api}/api/v3/orders"
    
    date_to = datetime.utcnow()
    # date_from = date_to - timedelta(days=config.lookback_days)
    
    date_from = str(int(datetime.timestamp() * 1000)) 
    # Базовые параметры (в реальности нужна пагинация через nextCursor)
    params = {"dateFrom": date_from.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 1000}
    data = client.request("GET", url, "v3_orders", params=params)
    
    if data and "orders" in data:
        logger.info(f"Получено заказов: {len(data['orders'])}")
        with Session() as session:
            for o in data["orders"]:
                # Упрощенное сохранение
                session.merge(Order(order_uid=str(o.get("id", o.get("orderUid"))), raw_data=o))
            session.commit()

def fetch_cards(client: WBClient, config: AppConfig, logger: logging.Logger, Session):
    logger.info("Старт потока: Загрузка карточек товаров")
    url = f"{client.content_api}/api/v2/get/cards/list"
    payload = {"settings": {"cursor": {"limit": 100}, "filter": {"withPhoto": -1}}}
    
    data = client.request("POST", url, "v2_getCardsList", json=payload)
    if data and "cards" in data:
        logger.info(f"Получено карточек: {len(data['cards'])}")
        with Session() as session:
            for c in data["cards"]:
                session.merge(Card(nm_id=c.get("nmID"), raw_data=c))
            session.commit()