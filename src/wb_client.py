import time
import requests
import json
from datetime import datetime
from app_config import AppConfig
import logging

class WBClient:
    def __init__(self, config: AppConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({"Authorization": self.config.api_token})
        self.marketplace_api = "https://marketplace-api.wildberries.ru"
        self.content_api = "https://content-api.wildberries.ru"

    def ping(self):
        self.logger.info("Проверка доступности API (ping)...")
        for name, url in [("Marketplace", f"{self.marketplace_api}/ping"), ("Content", f"{self.content_api}/ping")]:
            try:
                r = self.session.get(url, timeout=10)
                r.raise_for_status()
                self.logger.info(f"{name} API ping OK: {r.status_code}")
            except Exception as e:
                self.logger.error(f"{name} API ping failed: {e}")

    def _save_response(self, endpoint: str, data: dict | list | str, status_code: int):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_endpoint = endpoint.replace("/", "_").strip("_")
        filepath = self.config.responses_dir / f"{timestamp}_{safe_endpoint}_{status_code}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def request(self, method: str, url: str, endpoint_name: str, **kwargs) -> dict | list | None:
        delays = list(self.config.retry_delays_sec)
        attempt = 0
        
        while True:
            self.logger.info(f"Запрос {method} {url} ({endpoint_name})")
            try:
                response = self.session.request(method, url, timeout=60, **kwargs)
                
                if response.status_code == 429:
                    if attempt < len(delays):
                        delay = delays[attempt]
                    else:
                        # Умножаем на 2 после исхождения стандартного списка
                        delay = delays[-1] * (2 ** (attempt - len(delays) + 1))
                    
                    delay = min(delay, self.config.max_retry_sec)
                    self.logger.warning(f"429 Too Many Requests. Пауза {delay} сек...")
                    self._save_response(endpoint_name, {"error": "429"}, response.status_code)
                    time.sleep(delay)
                    attempt += 1
                    continue
                
                response.raise_for_status()
                data = response.json()
                self._save_response(endpoint_name, data, response.status_code)
                return data
                
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Ошибка сети для {endpoint_name}: {e}")
                self._save_response(endpoint_name, {"error": str(e)}, 500)
                return None