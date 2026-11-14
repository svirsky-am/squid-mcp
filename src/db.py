import sqlite3
import json
from src.config import AppConfig
from src.logger_setup import get_logger

logger = get_logger(__name__)
config = AppConfig()

def get_db_connection():
    return sqlite3.connect(config.db_path)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            raw_json TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            nmID INTEGER PRIMARY KEY,
            raw_json TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована.")

def save_orders(orders: list):
    if not orders: return
    conn = get_db_connection()
    cursor = conn.cursor()
    for order in orders:
        order_id = str(order.get("id"))
        cursor.execute("""
            INSERT OR REPLACE INTO orders (id, raw_json)
            VALUES (?, ?)
        """, (order_id, json.dumps(order, ensure_ascii=False)))
    conn.commit()
    conn.close()
    logger.info(f"Сохранено {len(orders)} заказов в БД.")