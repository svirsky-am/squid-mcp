from pathlib import Path
from unittest.mock import MagicMock

import pytest
from mcp.client import Client

import wb_mcp_client.wb_client as wb_client_mod
from wb_mcp_client.app_config import AppConfig
from wb_mcp_client.cards import sync_cards_now
from wb_mcp_client.db import Database
from wb_mcp_server.server import mcp
import os

@pytest.mark.skipif(not os.getenv("WB_SANDBOX_TOKEN"), reason="Требуется WB_SANDBOX_TOKEN")
def test_sandbox_cards_upload_and_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORK_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_GDRIVE_UPLOAD", "false")
    monkeypatch.delenv("API_TOKEN", raising=False)

    cfg = AppConfig()
    log = setup_logger(cfg.logs_dir, name="wb_sandbox_test")
    client = wb_client_mod.WBApiClient(cfg, log, use_sandbox=True)

    try:
        upload_resp = client.upload_sandbox_cards([
            {
                "subjectID": 105,
                "variants": [
                    {
                        "vendorCode": "sandbox-test-001",
                        "title": "Тестовый товар Sandbox",
                        "brand": "TestBrand",
                        "dimensions": {"length": 20, "width": 15, "height": 5},
                        "sizes": [{"techSize": "42", "wbSize": "42", "price": 1500}],
                    }
                ],
            }
        ])
        assert upload_resp.get("error") is False
    finally:
        client.close()

    saved = sync_cards_now(config=cfg, use_sandbox=True)
    assert saved >= 1

def _make_card(nm_id: int) -> dict:
    return {
        "nmID": nm_id,
        "imtID": nm_id * 10,
        "vendorCode": f"art-{nm_id}",
        "title": f"Товар тестовый #{nm_id}",
        "brand": "TestBrand",
        "subjectID": 500,
        "subjectName": "Футболки",
        "updatedAt": "2026-11-28T10:00:00Z",
        "sizes": [{"skus": [f"20000000{nm_id}"]}],
        "photos": [{"big": f"https://example.com{nm_id}.webp"}],
    }


@pytest.mark.skipif(not os.getenv("RUN_REAL_WB_TESTS"), reason="Запускается вручную с RUN_REAL_WB_TESTS=1")
def test_real_wb_cards_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORK_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_GDRIVE_UPLOAD", "false")
    cfg = AppConfig()
    count = sync_cards_now(config=cfg)
    assert count >= 0

def test_sync_cards_pagination_and_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_TOKEN", "test-wb-token")
    monkeypatch.setenv("WORK_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_GDRIVE_UPLOAD", "false")

    page_1 = {
        "cards": [_make_card(i) for i in range(1, 101)],
        "cursor": {"updatedAt": "2026-11-28T09:00:00Z", "nmID": 100, "total": 100},
    }
    page_2 = {
        "cards": [_make_card(101), _make_card(102)],
        "cursor": {"updatedAt": "2026-11-28T08:00:00Z", "nmID": 102, "total": 2},
    }

    calls = []

    def fake_request_with_retry(self, method, url, endpoint_tag, stop_event=None, **kwargs):
        calls.append(kwargs.get("json"))
        return page_1 if len(calls) == 1 else page_2

    monkeypatch.setattr(wb_client_mod.WBApiClient, "request_with_retry", fake_request_with_retry)
    monkeypatch.setattr(wb_client_mod.time, "sleep", lambda _: None)

    cfg = AppConfig()
    saved_count = sync_cards_now(config=cfg)

    assert saved_count == 102
    assert len(calls) == 2
    second_call = next(iter(calls[1:]))
    assert second_call["settings"]["cursor"]["nmID"] == 100

    db = Database(cfg.db_path)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM product_cards WHERE nm_id = 102").fetchone()
        assert row is not None
        assert row["vendor_code"] == "art-102"
        assert row["title"] == "Товар тестовый #102"

async def test_mcp_sync_product_cards_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_TOKEN", "test-wb-token")
    monkeypatch.setenv("WORK_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_GDRIVE_UPLOAD", "false")

    mock_fetch = MagicMock(return_value=[_make_card(777)])
    monkeypatch.setattr(wb_client_mod.WBApiClient, "fetch_product_cards", mock_fetch)

    async with Client(mcp) as client:
        res = await client.call_tool("sync_product_cards", {})
        assert not res.is_error
        first_block = next(iter(res.content))
        assert "1 шт." in first_block.text

        info = await client.call_tool("get_product_card_info", {"query": "art-777"})
        assert not info.is_error
        info_block = next(iter(info.content))
        assert "Товар тестовый #777" in info_block.text