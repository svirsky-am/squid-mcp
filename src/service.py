import time
import threading
from concurrent.futures import ThreadPoolExecutor
from app_config import AppConfig
from logger_setup import setup_logger
from wb_client import WBClient
from fetchers import fetch_orders, fetch_cards
from db import init_db
from report_generator import generate_summary_report

def run_fetchers(config, logger, client, Session):
    with ThreadPoolExecutor(max_workers=len(config.endpoints)) as executor:
        futures = []
        if "orders" in config.endpoints:
            futures.append(executor.submit(fetch_orders, client, config, logger, Session))
        if "cards" in config.endpoints:
            futures.append(executor.submit(fetch_cards, client, config, logger, Session))
            
        for future in futures:
            future.result() # Ждем завершения всех потоков в пуле

def report_thread(config, logger):
    """Фоновый поток для периодического построения сводного XLSX отчета"""
    while True:
        time.sleep(config.cards_interval_sec)
        try:
            logger.info("Фоновый поток: Генерация периодического XLSX отчета...")
            generate_summary_report(config, logger)
        except Exception as e:
            logger.error(f"Ошибка генерации отчета в фоне: {e}")

def main():
    config = AppConfig()
    logger = setup_logger(config)
    Session = init_db(config)
    
    client = WBClient(config, logger)
    client.ping()
    
    # Запуск потока генерации отчетов
    t = threading.Thread(target=report_thread, args=(config, logger), daemon=True)
    t.start()
    
    logger.info(f"Сервис запущен. Интервал fetch: {config.fetch_interval_minutes} мин.")
    while True:
        try:
            run_fetchers(config, logger, client, Session)
        except Exception as e:
            logger.error(f"Критическая ошибка в цикле fetch: {e}")
            
        logger.info(f"Цикл завершен. Сон на {config.fetch_interval_minutes} мин...")
        time.sleep(config.fetch_interval_sec)

if __name__ == "__main__":
    main()