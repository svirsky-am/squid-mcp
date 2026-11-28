import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from wb_mcp_client.app_config import AppConfig


class WBApiClient:
    PING_ENDPOINTS = [
        "https://content-api.wildberries.ru/ping",
        "https://marketplace-api.wildberries.ru/ping",
    ]
    PROD_MARKETPLACE_URL = "https://marketplace-api.wildberries.ru"
    SANDBOX_MARKETPLACE_URL = "https://marketplace-api-sandbox.wildberries.ru"

    PROD_CONTENT_URL = "https://content-api.wildberries.ru"
    SANDBOX_CONTENT_URL = "https://content-api-sandbox.wildberries.ru"

    def __init__(
        self,
        config: AppConfig,
        logger: logging.Logger,
        use_sandbox: bool = False,
    ) -> None:
        self.config = config
        self.logger = logger
        self.use_sandbox = use_sandbox

        token = self.config.sandbox_token if use_sandbox else self.config.api_token
        self.marketplace_base_url = (
            self.SANDBOX_MARKETPLACE_URL if use_sandbox else self.PROD_MARKETPLACE_URL
        )
        self.content_base_url = (
            self.SANDBOX_CONTENT_URL if use_sandbox else self.PROD_CONTENT_URL
        )

        self._client = httpx.Client(
            headers={
                "Authorization": token,
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(30.0),
        )

    def upload_sandbox_cards(
        self,
        cards_payload: List[Dict[str, Any]],
        stop_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """Создаёт тестовые карточки в песочнице (/content/v2/cards/upload)."""
        if not self.use_sandbox:
            raise ValueError("Метод upload_sandbox_cards разрешён только при use_sandbox=True")

        url = f"{self.content_base_url}/content/v2/cards/upload"
        return self.request_with_retry(
            "POST",
            url,
            endpoint_tag="content_v2_cards_upload",
            stop_event=stop_event,
            json=cards_payload,
        )

    def close(self) -> None:
        self._client.close()

    def _next_retry_delay(self, attempt: int) -> int:
        base_delays = self.config.retry_delays_sec
        if attempt < len(base_delays):
            delay = base_delays[attempt]
        else:
            # После последнего элемента списка (4 часа) продолжаем умножать на 2
            extra_steps = attempt - len(base_delays) + 1
            delay = base_delays[-1] * (2 ** extra_steps)
        return min(delay, self.config.max_retry_sec)

    def _save_raw_response(self, endpoint_tag: str, payload: Any) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        safe_tag = endpoint_tag.strip("/").replace("/", "_")
        filepath = self.config.responses_dir / f"{ts}_{safe_tag}.json"
        filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def request_with_retry(
        self,
        method: str,
        url: str,
        endpoint_tag: str,
        stop_event: Optional[threading.Event] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        attempt = 0
        while True:
            if stop_event and stop_event.is_set():
                raise RuntimeError("Остановка запроса по сигналу завершения службы")

            self.logger.info("Запрос к эндпойнту WB: %s %s (params=%s)", method, url, kwargs.get("params"))
            response = self._client.request(method, url, **kwargs)

            if response.status_code == 429:
                delay = self._next_retry_delay(attempt)
                self.logger.warning(
                    "Получен статус 429 от %s. Попытка #%d. Повтор через %d сек (%.1f мин).",
                    url,
                    attempt + 1,
                    delay,
                    delay / 60.0,
                )
                attempt += 1
                if stop_event:
                    if stop_event.wait(timeout=delay):
                        raise RuntimeError("Прервано во время ожидания ретрая 429")
                else:
                    time.sleep(delay)
                continue

            response.raise_for_status()
            data = response.json() if response.content else {}
            self._save_raw_response(endpoint_tag, data)
            return data

    def ping_all(self, stop_event: Optional[threading.Event] = None) -> bool:
        """Проверяет доступность доменов WB API перед запуском основного цикла."""
        all_ok = True
        for ping_url in self.PING_ENDPOINTS:
            tag = ping_url.replace("https://", "").replace("/", "_")
            try:
                data = self.request_with_retry("GET", ping_url, endpoint_tag=tag, stop_event=stop_event)
                self.logger.info("Ping %s успешен: %s", ping_url, data)
            except Exception as exc:
                self.logger.error("Ошибка ping %s: %s", ping_url, exc)
                all_ok = False
        return all_ok

    def fetch_fbs_orders(
        self,
        date_from_ts: Optional[int] = None,
        date_to_ts: Optional[int] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> List[Dict[str, Any]]:
        """Получает все сборочные задания FBS за период с пагинацией по next."""
        now_utc = datetime.now(timezone.utc)
        if date_to_ts is None:
            date_to_ts = int(now_utc.timestamp())
        if date_from_ts is None:
            # По документации WB максимум 30 календарных дней за один запрос
            days = min(self.config.lookback_days, 30)
            date_from_ts = int((now_utc - timedelta(days=days)).timestamp())

        url = f"{self.marketplace_base_url}/api/v3/orders"
        all_orders: List[Dict[str, Any]] = []
        next_cursor = 0
        limit = 1000

        while True:
            params = {
                "limit": limit,
                "next": next_cursor,
                "dateFrom": date_from_ts,
                "dateTo": date_to_ts,
            }
            data = self.request_with_retry(
                "GET",
                url,
                endpoint_tag="api_v3_orders",
                stop_event=stop_event,
                params=params,
            )
            batch = data.get("orders") or []
            all_orders.extend(batch)
            new_next = data.get("next", 0)

            self.logger.info(
                "Получено %d заказов (всего: %d, next=%s)",
                len(batch),
                len(all_orders),
                new_next,
            )

            # Если пришел пустой список или курсор перестал двигаться — выходим
            if not batch or not new_next or new_next == next_cursor:
                break

            next_cursor = new_next
            # Соблюдаем интервал 200 мс (лимит 300 запросов/мин)
            time.sleep(0.25)

        return all_orders

    def fetch_orders_statuses(
        self,
        order_ids: List[int],
        stop_event: Optional[threading.Event] = None,
    ) -> List[Dict[str, Any]]:
        """Получает статусы сборочных заданий батчами по 1000 ID (/api/v3/orders/status)."""
        url = f"{self.marketplace_base_url}/api/v3/orders/status"
        all_statuses: List[Dict[str, Any]] = []

        for i in range(0, len(order_ids), 1000):
            chunk = order_ids[i : i + 1000]
            data = self.request_with_retry(
                "POST",
                url,
                endpoint_tag="api_v3_orders_status",
                stop_event=stop_event,
                json={"orders": chunk},
            )
            all_statuses.extend(data.get("orders") or [])
            time.sleep(0.25)

        return all_statuses
    
    def fetch_product_cards(
        self,
        stop_event: Optional[threading.Event] = None,
    ) -> List[Dict[str, Any]]:
        """Получает все карточки товаров продавца через /content/v2/get/cards/list."""
        url = f"{self.content_base_url}/content/v2/get/cards/list"
        all_cards: List[Dict[str, Any]] = []
        limit = 100
        cursor: Dict[str, Any] = {"limit": limit}

        while True:
            payload = {
                "settings": {
                    "cursor": cursor,
                    "filter": {"withPhoto": -1},
                }
            }
            data = self.request_with_retry(
                "POST",
                url,
                endpoint_tag="content_v2_get_cards_list",
                stop_event=stop_event,
                json=payload,
            )
            batch = data.get("cards") or []
            all_cards.extend(batch)

            resp_cursor = data.get("cursor") or {}
            total = resp_cursor.get("total", 0)
            self.logger.info(
                "Получено %d карточек (всего: %d, cursor.total=%s)",
                len(batch),
                len(all_cards),
                total,
            )

            if not batch or total < limit:
                break

            cursor = {
                "limit": limit,
                "updatedAt": resp_cursor["updatedAt"],
                "nmID": resp_cursor["nmID"],
            }
            # Лимит Content API: 100 запросов/мин (интервал 600 мс)
            time.sleep(0.65)

        return all_cards

    def fetch_warehouses(self, stop_event: Optional[threading.Event] = None) -> List[Dict[str, Any]]:
        """Получает список складов продавца (/api/v3/warehouses)."""
        url = f"{self.marketplace_base_url}/api/v3/warehouses"
        data = self.request_with_retry(
            "GET",
            url,
            endpoint_tag="api_v3_warehouses",
            stop_event=stop_event,
        )
        return data if isinstance(data, list) else []

    def fetch_warehouse_stocks(
        self,
        warehouse_id: int,
        skus: List[str],
        stop_event: Optional[threading.Event] = None,
    ) -> List[Dict[str, Any]]:
        """Запрашивает актуальные остатки на складе продавца по списку SKU батчами по 1000 шт."""
        if not skus:
            return []

        url = f"{self.marketplace_base_url}/api/v3/stocks/{warehouse_id}"
        all_stocks: List[Dict[str, Any]] = []
        chunk_size = 1000

        for idx in range(0, len(skus), chunk_size):
            batch = skus[idx : idx + chunk_size]
            data = self.request_with_retry(
                "POST",
                url,
                endpoint_tag=f"api_v3_stocks_{warehouse_id}",
                stop_event=stop_event,
                json={"skus": batch},
            )
            items = data.get("stocks") or [] if isinstance(data, dict) else []
            all_stocks.extend(items)
            if idx + chunk_size < len(skus):
                time.sleep(0.35)

        return all_stocks