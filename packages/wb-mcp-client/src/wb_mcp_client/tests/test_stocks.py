from datetime import datetime, timezone
from pathlib import Path

import pytest
from mcp.client import Client

import wb_mcp_client.wb_client as wb_client_mod
from wb_mcp_client.app_config import AppConfig
from wb_mcp_client.db import Database
from wb_mcp_client.stocks import sync_stocks_now
from wb_mcp_server.server import mcp


async def test_sync_stocks_and_forecast_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_TOKEN", "test-wb-token")
    monkeypatch.setenv("WORK_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_GDRIVE_UPLOAD", "false")

    cfg = AppConfig()
    db = Database(cfg.db_path)

    # 1. Наполняем карточку и историю заказов (14 заказов за 14 дней = 1 шт./день)
    db.upsert_cards([
        {
            "nmID": 333444,
            "vendorCode": "hoodie-gray",
            "title": "Худи оверсайз серый",
            "brand": "TestBrand",
            "sizes": [{"skus": ["460000000333"]}],
        }
    ])
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.upsert_orders([
        {
            "id": 9000 + i,
            "createdAt": now_iso,
            "article": "hoodie-gray",
            "nmId": 333444,
            "skus": ["460000000333"],
            "price": 300000,
            "convertedPrice": 300000,
        }
        for i in range(14)
    ])

    # 2. Мокаем ответы складов и остатков (остаток 3 шт. -> хватит на 3 дня)
    monkeypatch.setattr(
        wb_client_mod.WBApiClient,
        "fetch_warehouses",
        lambda self, stop_event=None: [{"id": 77, "name": "Основной склад МСК"}],
    )
    monkeypatch.setattr(
        wb_client_mod.WBApiClient,
        "fetch_warehouse_stocks",
        lambda self, wh_id, skus, stop_event=None: [{"sku": "460000000333", "amount": 3}],
    )

    res = sync_stocks_now(config=cfg)
    assert res == {"warehouses": 1, "stocks_updated": 1}

    # 3. Проверяем инструменты Алисы в памяти
    async with Client(mcp) as client:
        stocks_res = await client.call_tool("get_fbs_stocks", {"query": "hoodie"})
        assert not stocks_res.is_error
        block = next(iter(stocks_res.content))
        assert "Худи оверсайз серый" in block.text
        assert "Основной склад МСК" in block.text
        assert "3 шт." in block.text

        forecast_res = await client.call_tool("get_low_stock_forecast", {"days_threshold": 5, "lookback_days": 14})
        assert not forecast_res.is_error
        f_block = next(iter(forecast_res.content))
        assert "Худи оверсайз серый" in f_block.text
        assert "хватит на ~3.0 дн." in f_block.text