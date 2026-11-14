import asyncio
import json

from wb_reporter import wb_api
from wb_reporter.wb_api import WbApiClient


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    text = ""


class FakeSession:
    """Сессия с заданной последовательностью ответов."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def test_fetch_retries_on_429_and_saves_response(cfg, monkeypatch):
    seen_sleeps = []

    async def fake_sleep(sec):
        seen_sleeps.append(sec)

    monkeypatch.setattr(wb_api.asyncio, "sleep", fake_sleep)

    session = FakeSession([
        FakeResponse(429),
        FakeResponse(429),
        FakeResponse(200, {"orders": [{"id": "1", "article": "A1"}], "next": None}),
    ])
    api = WbApiClient(cfg, session=session)

    from datetime import datetime, timedelta
    items = asyncio.run(api.fetch_orders(datetime.now() - timedelta(days=1)))

    assert len(session.calls) == 3  # два 429 + один успех
    assert seen_sleeps == [0, 0]    # задержки из cfg (нулевые в тестах)
    assert items == [{"id": "1", "article": "A1"}]
    # ответ сохранён в work_dir/responses/orders
    saved = list((cfg.responses_dir / "orders").glob("*.json"))
    assert len(saved) == 1
    doc = json.loads(saved[0].read_text())
    assert doc["response"]["orders"] == [{"id": "1", "article": "A1"}]


def test_fetch_raises_on_http_error(cfg):
    api = WbApiClient(cfg, session=FakeSession([FakeResponse(401)]))
    try:
        asyncio.run(api.fetch("GET", "https://example.com", label="x"))
    except wb_api.WbApiError as exc:
        assert "401" in str(exc)
    else:
        raise AssertionError("Ожидали WbApiError")


def test_cards_pagination_stops_on_short_page(cfg, monkeypatch):
    async def fake_sleep(sec):
        pass

    monkeypatch.setattr(wb_api.asyncio, "sleep", fake_sleep)

    session = FakeSession([
        FakeResponse(200, {
            "data": {
                "cards": [{"nmID": i} for i in range(100)],
                "cursor": {"updatedAt": "2026-01-01", "nmID": 99, "total": 100},
            }
        }),
        FakeResponse(200, {
            "data": {
                "cards": [{"nmID": 1000}],
                "cursor": {"updatedAt": "2026-01-02", "nmID": 1000, "total": 1},
            }
        }),
    ])
    api = WbApiClient(cfg, session=session)
    cards = asyncio.run(api.fetch_cards())
    assert len(cards) == 101
    assert len(session.calls) == 2
