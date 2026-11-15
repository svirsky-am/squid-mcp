import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine
from app_config import AppConfig
import logging

def generate_summary_report(config: AppConfig, logger: logging.Logger = None):
    if not logger:
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger("report_generator")
        
    logger.info("Чтение данных из БД для сводного отчета...")
    engine = create_engine(config.database_url)
    
    try:
        # Читаем таблицы (в реальном проекте здесь будет сложный JOIN и маппинг полей)
        df_orders = pd.read_sql_table("orders", engine)
        df_cards = pd.read_sql_table("cards", engine)
        
        # Заготовка под ваш формат "Реестр ВБ"
        report_data = {
            "Дата отчета": [datetime.now().strftime("%d.%m.%Y")] * len(df_orders),
            "ИП": ["ИП Олейник"] * len(df_orders),
            "Номер заказа": df_orders['order_uid'] if not df_orders.empty else [],
            "Статус": ["Доставляется"] * len(df_orders),
            "Артикул WB": ["-"] * len(df_orders),
            "Название товара": ["Товар из БД"] * len(df_orders),
        }
        
        df_report = pd.DataFrame(report_data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        report_path = config.work_dir / f"WB_Summary_Report_{timestamp}.xlsx"
        
        with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
            df_report.to_excel(writer, sheet_name="Реестр ВБ", index=False)
            # Можно добавить лист с карточками
            if not df_cards.empty:
                df_cards.to_excel(writer, sheet_name="Карточки", index=False)
            
        logger.info(f"Сводный отчет успешно сохранен: {report_path}")
    except Exception as e:
        logger.error(f"Ошибка формирования XLSX: {e}")

if __name__ == "__main__":
    # Точка входа для запуска ВНЕ сервиса (через justfile generate-report)
    config = AppConfig()
    generate_summary_report(config)