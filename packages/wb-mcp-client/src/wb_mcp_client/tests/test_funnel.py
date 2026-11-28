import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from mcp.client import Client

import wb_mcp_client.wb_client as wb_client_mod
from wb_mcp_client.app_config import AppConfig
from wb_mcp_client.db import Database
from wb_mcp_client.funnel import sync_funnel_now
from wb_mcp_server.server import mcp


def _make_funnel_item(nm_id: int, opens: int = 100, carts: int = 20, orders: int = 5) -> dict:
    return {
        "product": {
            "nmId": nm_id,
            "title": f"Товар воронки #{nm_id}",
            "vendorCode": f"art-{nm_id}",
            "brandName": "TestBrand",
            "subjectId": 105,
            "subjectName": "Футболки",
        },
        "statistic": {
            "selected": {
                "openCount": opens,
                "cartCount": carts,
                "orderCount": orders,
                "orderSum": orders * 1500.0,
                "buyoutCount": max(orders - 1, 0),
                "buyoutSum": max(orders - 1, 0) * 1500.0,
                "cancelCount": 1 if orders > 0 else 0,
                "cancelSum": 1500.0 if orders > 0 else 0.0,
                "addToWishlist": 7,
                "conversions": {
                    "addToCartPercent": round((carts / opens) * 100, 1) if opens else 0.0,
                    "cartToOrderPercent": round((orders / carts) * 100, 1) if carts else 0.0,
                    "buyoutPercent": 80.0,
                },
            }
        },
    }


def test_sync_sales_funnel_pagination_and_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_TOKEN", "test-wb-token")
    monkeypatch.setenv("WORK_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_GDRIVE_UPLOAD", "false")

    # Имитируем 2 страницы ответа: 100 карточек (лимит) + 1 карточка
    page_1 = {"data": {"products": [_make_funnel_item(i, opens=50, carts=10, orders=2) for i in range(1, 101)]}}
    page_2 = {"data": {"products": [_make_funnel_item(101, opens=200, carts=40, orders=10)]}}

    calls = []

    def fake_request_with_retry(self, method, url, endpoint_tag, stop_event=None, **kwargs):
        calls.append(kwargs.get("json"))
        return page_1 if len(calls) == 1 else page_2

    monkeypatch.setattr(wb_client_mod.WBApiClient, "request_with_retry", fake_request_with_retry)
    monkeypatch.setattr(wb_client_mod.time, "sleep", lambda _: None)

    cfg = AppConfig()
    saved = sync_funnel_now(config=cfg, days=7)

    assert saved == 101
    assert len(calls) == 2
    assert calls[0]["offset"] == 0
    assert calls[1]["offset"] == 100

    db = Database(cfg.db_path)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM sales_funnel WHERE nm_id = 101").fetchone()
        assert row is not None
        assert row["vendor_code"] == "art-101"
        assert row["open_count"] == 200
        assert row["cart_count"] == 40
        assert row["order_count"] == 10


async def test_mcp_sales_funnel_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_TOKEN", "test-wb-token")
    monkeypatch.setenv("WORK_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_GDRIVE_UPLOAD", "false")

    mock_fetch = MagicMock(return_value=[_make_funnel_item(555, opens=300, carts=60, orders=15)])
    monkeypatch.setattr(wb_client_mod.WBApiClient, "fetch_sales_funnel", mock_fetch)

    async with Client(mcp) as client:
        sync_res = await client.call_tool("sync_sales_funnel", {"days": 7})
        assert not sync_res.is_error
        sync_block = next(iter(sync_res.content))
        assert "1 шт." in sync_block.text

        summary_res = await client.call_tool("get_sales_funnel_summary", {"days": 7, "limit": 5})
        assert not summary_res.is_error
        sum_block = next(iter(summary_res.content))
        assert "Переходы в карточки: 300 шт." in sum_block.text
        assert "Добавления в корзину: 60 шт." in sum_block.text
        assert "Товар воронки #555" in sum_block.text


@pytest.mark.skipif(not os.getenv("RUN_REAL_WB_TESTS"), reason="Запускается вручную с RUN_REAL_WB_TESTS=1")
def test_real_wb_sales_funnel_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORK_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_GDRIVE_UPLOAD", "false")
    cfg = AppConfig()
    count = sync_funnel_now(config=cfg, days=7)
    assert count >= 0