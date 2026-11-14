import httpx
import asyncio
import json
from datetime import datetime
from pathlib import Path
from src.logger_setup import get_logger
from src.config import AppConfig

logger = get_logger(__name__)

class WBClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self.headers = {"Authorization": config.api_token}
        self.base_url = "https://marketplace-api.wildberries.ru"
        self.responses_dir = config.responses_dir
        self.responses_dir.mkdir(parents=True, exist_ok=True)

    async def request(self, endpoint: str, method: str = "GET", **kwargs) -> dict:
        url = f"{self.base_url}{endpoint}"
        logger.info(f"Обращение к эндпоинту: {method} {url}")
        
        delays = list(self.config.retry_delays_sec)
        attempt = 0
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                try:
                    if method == "GET":
                        response = await client.get(url, headers=self.headers, **kwargs)
                    elif method == "POST":
                        response = await client.post(url, headers=self.headers, **kwargs)
                    else:
                        raise ValueError(f"Unsupported method: {method}")
                        
                    if response.status_code == 429:
                        if attempt < len(delays):
                            delay = delays[attempt]
                        else:
                            # Умножаем последний элемент на 2 (2мин -> 30м -> 1ч -> 2ч -> 4ч -> 8ч...)
                            delay = delays[-1] * (2 ** (attempt - len(delays) + 1))
                            delay = min(delay, self.config.max_retry_sec)
                            
                        logger.warning(f"Статус 429 (Too Many Requests). Пауза {delay} сек перед повтором...")
                        await asyncio.sleep(delay)
                        attempt += 1
                        continue
                        
                    response.raise_for_status()
                    self._save_response(endpoint, response)
                    return response.json()
                    
                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP ошибка при запросе {url}: {e.response.status_code} - {e.response.text}")
                    raise
                except Exception as e:
                    logger.error(f"Непредвиденная ошибка при запросе {url}: {e}")
                    raise

    def _save_response(self, endpoint: str, response: httpx.Response):
        try:
            safe_endpoint = endpoint.strip("/").replace("/", "_")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_endpoint}_{timestamp}.json"
            filepath = self.responses_dir / filename
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(response.json(), f, ensure_ascii=False, indent=2)
            logger.debug(f"Ответ сохранен: {filepath}")
        except Exception as e:
            logger.error(f"Не удалось сохранить ответ: {e}")