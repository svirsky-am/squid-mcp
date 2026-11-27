import signal
import threading
from concurrent.futures import ThreadPoolExecutor

from wb_mcp_client.app_config import AppConfig
from wb_mcp_client.db import Database
from wb_mcp_client.logger import setup_logger
from wb_mcp_client.report import build_and_upload_report
from wb_mcp_client.wb_client import WBApiClient


from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SCOPES = ["https://googleapis.com"]


class WBCollectorService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.logger = setup_logger(config.logs_dir)
        self.db = Database(config.db_path)
        self.client = WBApiClient(config, self.logger)
        self.stop_event = threading.Event()
        self.executor = ThreadPoolExecutor(
            max_workers=config.max_workers,
            thread_name_prefix="wb-worker",
        )

    def _task_fetch_orders(self) -> None:
        try:
            self.logger.info("Старт задачи получения заказов FBS (/api/v3/orders)")
            orders = self.client.fetch_fbs_orders(stop_event=self.stop_event)
            saved_count = self.db.upsert_orders(orders)
            self.logger.info("Сохранено/обновлено в БД заказов: %d", saved_count)

            if orders and not self.stop_event.is_set():
                order_ids = [o["id"] for o in orders]
                statuses = self.client.fetch_orders_statuses(order_ids, stop_event=self.stop_event)
                updated_statuses = self.db.update_order_statuses(statuses)
                self.logger.info("Обновлено статусов заказов в БД: %d", updated_statuses)

            # После fetch запускаем построение сводного отчёта по данным из SQLite
            if not self.stop_event.is_set():
                build_and_upload_report(self.config, logger=self.logger)
        except Exception:
            self.logger.exception("Ошибка в задаче _task_fetch_orders")

    def _task_build_report(self) -> None:
        try:
            self.logger.info("Периодический запуск построения сводного отчёта xlsx")
            build_and_upload_report(self.config, logger=self.logger)
        except Exception:
            self.logger.exception("Ошибка при построении сводного отчёта")

    def _scheduler_loop(self, name: str, interval_sec: int, fn) -> None:
        self.logger.info("Планировщик '%s' запущен (интервал: %d сек)", name, interval_sec)
        while not self.stop_event.is_set():
            self.executor.submit(fn)
            if self.stop_event.wait(timeout=interval_sec):
                break

    def run(self) -> None:
        self.logger.info("Инициализация службы WB Collector (work_dir=%s)", self.config.work_dir)

        # 1. Обязательный ping при запуске службы
        if not self.client.ping_all(stop_event=self.stop_event):
            self.logger.warning("Один или несколько ping-эндпойнтов WB не ответили, продолжаем работу.")

        if not self.config.fetch_data:
            self.logger.info("FETCH_DATA=False: сбор данных отключён, строим только отчёт.")
            self._task_build_report()
            return

        # 2. Запускаем независимые периодические потоки в пуле
        threads = [
            threading.Thread(
                target=self._scheduler_loop,
                args=("orders-fetcher", self.config.fetch_orders_interval_sec, self._task_fetch_orders),
                daemon=True,
            ),
            threading.Thread(
                target=self._scheduler_loop,
                args=("xlsx-reporter", self.config.report_interval_sec, self._task_build_report),
                daemon=True,
            ),
        ]

        for t in threads:
            t.start()

        try:
            while not self.stop_event.is_set():
                self.stop_event.wait(timeout=1.0)
        finally:
            self.logger.info("Остановка службы WB Collector...")
            self.stop_event.set()
            self.executor.shutdown(wait=True, cancel_futures=True)
            self.client.close()
            self.logger.info("Служба остановлена.")


    def _upload_to_gdrive(self, report_path: Path) -> None:
        creds = service_account.Credentials.from_service_account_file(
            str(self.config.google_credentials_path), scopes=SCOPES
        )
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        metadata = {
            "name": report_path.name,
            "parents": [self.config.google_drive_folder_id],
        }
        media = MediaFileUpload(str(report_path), mimetype=XLSX_MIME, resumable=True)
        uploaded = (
            drive.files()
            .create(body=metadata, media_body=media, fields="id, name, webViewLink", supportsAllDrives=True)
            .execute()
        )
        self.logger.info(
            "Отчёт загружен на Google Диск: %s (id=%s, link=%s)",
            uploaded.get("name"),
            uploaded.get("id"),
            uploaded.get("webViewLink"),
        )

    def _build_and_maybe_upload_report(self) -> None:
        report_path = build_excel_report_general(self.config, logger=self.logger)
        if self.config.enable_gdrive_upload and not self.stop_event.is_set():
            self._upload_to_gdrive(report_path)


def main() -> None:
    config = AppConfig()
    service = WBCollectorService(config)

    def _handle_sig(signum, _frame):
        service.stop_event.set()

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)
    service.run()


if __name__ == "__main__":
    main()
