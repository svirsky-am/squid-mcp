"""Асинхронный клиент WB API.

- Все эндпойнты вызываются через asyncio + пул потоков (asyncio.to_thread).
- Каждый ответ сохраняется в work_dir/responses/<label>/*.json.
- При 429 повторяем: 2 мин, 30 мин, 1 ч, 2 ч, 4 ч, далее умножаем на 2
  (с потолком cfg.max_retry_sec).
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

import requests

from .app_config import AppConfig

logger = logging.getLogger(__name__)

BACKOFF_DEFAULT_SEC: List[int] = [120, 1800, 3600, 7200, 14400]
STATUS_CHUNK = 1000


def retry_delay(attempt: int, delays: Sequence[int] = BACKOFF_DEFAULT_SEC, cap: int = 86400) -> int:
    """Задержка перед повтором №`attempt` (0-based).

    Первые пять повторов — из таблицы delays, дальше удвоение последней,
    не выше cap.
    """
    if not delays:
        raise ValueError("delays не должен быть пустым")
    if attempt < 0:
        raise ValueError("attempt >= 0")
    if attempt < len(delays):
        return min(delays[attempt], cap)
    return min(delays[-1] * (2 ** (attempt - len(delays) + 1)), cap)


def chunked(seq: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


class WbApiError(RuntimeError):
    """Любая HTTP-ошибка WB API, кроме 429."""


class _RateLimited(Exception):
    """Сигнал 429 для повторной попытки в async-цикле."""


class WbApiClient:
    MARKETPLACE = "https://marketplace-api.wildberries.ru"
    STATISTICS = "https://statistics-api.wildberries.ru"
    CONTENT = "https://content-api.wildberries.ru"
    CONTENT_SANDBOX = "https://content-api-sandbox.wildberries.ru"
    COMMON = "https://common-api.wildberries.ru"

    def __init__(self, cfg: AppConfig, session: Optional[requests.Session] = None) -> None:
        self.cfg = cfg
        self._session = session or self._make_session(cfg.api_token)
        self._sandbox_session = self._make_session(cfg.sandbox_token)

    @staticmethod
    def _make_session(token: str) -> requests.Session:
        s = requests.Session()
        s.headers.update({"Authorization": token, "Accept": "application/json"})
        return s

    # ------------------- низкий уровень -------------------

    def _request_once(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Any] = None,
        session: Optional[requests.Session] = None,
    ) -> Any:
        s = session or self._session
        try:
            resp = s.request(method, url, params=params, json=json_body, timeout=60)
        except requests.RequestException as exc:
            raise WbApiError(f"Сетевая ошибка {url}: {exc}") from exc
        if resp.status_code == 429:
            raise _RateLimited()
        if resp.status_code >= 400:
            raise WbApiError(f"{resp.status_code} {url}: {resp.text[:500]}")
        try:
            return resp.json()
        except ValueError:
            return resp.text

    def _save_response(
        self,
        label: str,
        url: str,
        params: Optional[Dict[str, Any]],
        json_body: Optional[Any],
        payload: Any,
    ) -> str:
        out_dir = self.cfg.responses_dir / label
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        digest = hashlib.md5(
            json.dumps(params or json_body, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:8]
        path = out_dir / f"{ts}_{digest}.json"
        doc = {
            "fetched_at": datetime.now().isoformat(),
            "url": url,
            "params": params,
            "request": json_body,
            "response": payload,
        }
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return str(path)

    async def fetch(
        self,
        method: str,
        url: str,
        *,
        label: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Any] = None,
        session: Optional[requests.Session] = None,
    ) -> Any:
        attempt = 0
        while True:
            try:
                payload = await asyncio.to_thread(
                    self._request_once,
                    method,
                    url,
                    params=params,
                    json_body=json_body,
                    session=session,
                )
                break
            except _RateLimited:
                delay = retry_delay(attempt, self.cfg.retry_delays_sec, self.cfg.max_retry_sec)
                logger.warning(
                    "%s: 429, повтор №%d через %d мин", label, attempt + 1, delay // 60
                )
                await asyncio.sleep(delay)
                attempt += 1
        await asyncio.to_thread(self._save_response, label, url, params, json_body, payload)
        return payload

    # ------------------- health check -------------------

    async def ping(self) -> Any:
        """GET /ping — проверка подключения при старте службы."""
        return await self.fetch("GET", f"{self.COMMON}/ping", label="ping")

    # ------------------- Маркетплейс: заказы FBS -------------------

    async def fetch_orders(self, date_from: datetime) -> List[Dict[str, Any]]:
        """GET /api/v3/orders — сборочные задания FBS (без актуальных статусов).

        Пагинация токеном `next`, период до 30 дней, даты — Unix-таймстампы.
        """
        items: List[Dict[str, Any]] = []
        nxt = 0
        while True:
            params = {
                "limit": 1000,
                "next": nxt,
                "dateFrom": int(date_from.timestamp()),
            }
            payload = await self.fetch(
                "GET", f"{self.MARKETPLACE}/api/v3/orders", label="orders", params=params
            )
            page = payload.get("orders", []) if isinstance(payload, dict) else []
            items.extend(page)
            nxt = payload.get("next") if isinstance(payload, dict) else None
            if nxt is None or not page:
                break
        return items

    async def fetch_orders_status(self, order_ids: Sequence[str]) -> List[Dict[str, Any]]:
        """POST /api/v3/orders/status — актуальные статусы по списку ID (до 1000)."""
        results: List[Dict[str, Any]] = []
        for chunk in chunked(list(order_ids), STATUS_CHUNK):
            payload = await self.fetch(
                "POST",
                f"{self.MARKETPLACE}/api/v3/orders/status",
                label="orders_status",
                json_body={"orders": [str(i) for i in chunk]},
            )
            results.extend(payload.get("orders", []) if isinstance(payload, dict) else [])
        return results

    async def fetch_warehouses(self) -> List[Dict[str, Any]]:
        payload = await self.fetch(
            "GET", f"{self.MARKETPLACE}/api/v3/warehouses", label="warehouses"
        )
        return payload if isinstance(payload, list) else payload.get("warehouses", [])

    # ------------------- Статистика -------------------

    async def fetch_sales(self, date_from: datetime) -> List[Dict[str, Any]]:
        payload = await self.fetch(
            "GET",
            f"{self.STATISTICS}/api/v1/supplier/sales",
            label="sales",
            params={"dateFrom": date_from.isoformat(), "flag": 0},
        )
        return payload if isinstance(payload, list) else []

    async def fetch_incomes(self, date_from: datetime) -> List[Dict[str, Any]]:
        payload = await self.fetch(
            "GET",
            f"{self.STATISTICS}/api/v1/supplier/incomes",
            label="incomes",
            params={"dateFrom": date_from.isoformat()},
        )
        return payload if isinstance(payload, list) else []

    async def fetch_stocks(self) -> List[Dict[str, Any]]:
        payload = await self.fetch(
            "GET",
            f"{self.STATISTICS}/api/v1/supplier/stocks",
            label="stocks",
            params={"dateFrom": "0001-01-01T00:00:00"},
        )
        return payload if isinstance(payload, list) else []

    # ------------------- Контент: карточки -------------------

    async def fetch_cards(self, page_size: int = 100) -> List[Dict[str, Any]]:
        """POST /content/v2/get/cards/list — курсорная пагинация по 100 карточек.

        Стоп-условие: страница короче лимита (cursor.total < limit).
        Между страницами — пауза под лимит метода.
        """
        items: List[Dict[str, Any]] = []
        cursor: Dict[str, Any] = {"limit": page_size}
        while True:
            body = {"settings": {"filter": {"withPhoto": -1}, "cursor": cursor}}
            payload = await self.fetch(
                "POST",
                f"{self.CONTENT}/content/v2/get/cards/list",
                label="cards",
                json_body=body,
            )
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            page = data.get("cards", [])
            items.extend(page)
            next_cursor = data.get("cursor") or {}
            if len(page) < page_size or not next_cursor.get("nmID"):
                break
            cursor = {
                "limit": page_size,
                "updatedAt": next_cursor.get("updatedAt"),
                "nmID": next_cursor.get("nmID"),
            }
            await asyncio.sleep(0.7)  # пауза под лимит метода
        return items

    def _content_host(self) -> str:
        return self.CONTENT_SANDBOX if self.cfg.use_sandbox_update else self.CONTENT

    def _content_session(self) -> requests.Session:
        return self._sandbox_session if self.cfg.use_sandbox_update else self._session

    async def update_cards(self, cards: List[Dict[str, Any]]) -> Any:
        """POST /content/v2/cards/update — правка атрибутов существующих карточек."""
        return await self.fetch(
            "POST",
            f"{self._content_host()}/content/v2/cards/update",
            label="cards_update",
            json_body={"cards": cards},
            session=self._content_session(),
        )

    async def upload_cards(self, cards: List[Dict[str, Any]]) -> Any:
        """POST /content/v2/cards/upload — создание новых карточек (дубликаты)."""
        return await self.fetch(
            "POST",
            f"{self._content_host()}/content/v2/cards/upload",
            label="cards_upload",
            json_body={"cards": cards},
            session=self._content_session(),
        )


def pick_status(obj: Dict[str, Any]) -> str:
    """Терпимый к вариациям вытащитель статуса из ответа orders/status."""
    for key in ("wbStatus", "status", "supplierStatus", "statusName"):
        value = obj.get(key)
        if value:
            return str(value)
    return ""
