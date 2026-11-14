import pandas as pd
import sqlite3
import json
from src.config import AppConfig
from src.logger_setup import get_logger

logger = get_logger(__name__)

def generate_report():
    config = AppConfig()
    logger.info("Формирование сводного отчета XLSX...")
    
    conn = sqlite3.connect(config.db_path)
    df_orders = pd.read_sql_query("SELECT raw_json FROM orders", conn)
    
    if df_orders.empty:
        logger.warning("В базе нет данных для отчета.")
        conn.close()
        return
        
    orders_data = [json.loads(row['raw_json']) for _, row in df_orders.iterrows()]
    df = pd.json_normalize(orders_data)
    
    # Маппинг колонок под ваш шаблон (адаптируйте под реальные поля API v3)
    mapping = {
        'createdAt': 'Дата создания',
        'id': 'Номер заказа',
        'trackingNumber': 'Номер отправления (ШК)',
        'status': 'Статус',
        'price': 'Стоимость',
        'article': 'Артикул продавца',
        'nmId': 'Артикул WB',
    }
    
    df_report = df.rename(columns=mapping)
    cols = [c for c in mapping.values() if c in df_report.columns]
    df_report = df_report[cols]
    
    out_dir = config.work_dir / "reports"
    out_dir.mkdir(exist_ok=True, parents=True)
    out_file = out_dir / "wb_summary_report.xlsx"
    
    # Запись в Excel
    with pd.ExcelWriter(out_file, engine='openpyxl') as writer:
        df_report.to_excel(writer, index=False, sheet_name="Реестр ВБ")
        
    logger.info(f"Сводный отчет сохранен: {out_file}")
    conn.close()

if __name__ == "__main__":
    generate_report()