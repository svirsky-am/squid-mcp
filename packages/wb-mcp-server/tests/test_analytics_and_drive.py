import asyncio
import os
import socket
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import httpx2
import pytest
import pytest_asyncio
import uvicorn
from mcp import ClientSession, MCPError
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

import wb_mcp_server.gdrive as gdrive_mod
from wb_mcp_server.server import create_app, mcp


@pytest.fixture
def sample_work_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("WORK_DIR", str(tmp_path))

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / "wb_general_report_2026.11.25_00.00.00.xlsx"
    report_file.write_bytes(b"PK\x03\x04fake-xlsx-content")

    creds_file = tmp_path / "gdrive_token.json"
    creds_file.write_text(
        '{"type": "authorized_user", "client_id": "cid", "client_secret": "csec", "refresh_token": "rtok"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", str(creds_file))
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "test-folder-123")

    db_path = tmp_path / "wb.db"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fbs_orders (
            id INTEGER PRIMARY KEY,
            order_uid TEXT,
            rid TEXT,
            created_at TEXT,
            article TEXT,
            nm_id INTEGER,
            chrt_id INTEGER,
            sku TEXT,
            price REAL,
            converted_price REAL,
            currency_code INTEGER,
            converted_currency_code INTEGER,
            delivery_type TEXT,
            supply_id TEXT,
            warehouse_id INTEGER,
            office_id INTEGER,
            cargo_type INTEGER,
            is_zero_order INTEGER,
            supplier_status TEXT,
            wb_status TEXT,
            raw_json TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE product_cards (
            nm_id INTEGER PRIMARY KEY,
            imt_id INTEGER,
            vendor_code TEXT,
            title TEXT,
            brand TEXT,
            subject_id INTEGER,
            subject_name TEXT,
            skus_json TEXT,
            photo_url TEXT,
            wb_updated_at TEXT,
            raw_json TEXT,
            synced_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO product_cards (nm_id, vendor_code, title, brand, subject_name)
        VALUES (?, ?, ?, ?, ?)
        """,
        (111111, "art-alpha", "Футболка базовая Alpha", "TestBrand", "Футболки"),
    )
    conn.executemany(
        """
        INSERT INTO fbs_orders (
            id, created_at, article, nm_id, sku, price, converted_price,
            supply_id, supplier_status, wb_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1001, now_iso, "art-alpha", 111111, "200000000001", 150000, 150000, "WB-GI-10", "complete", "sold"),
            (1002, now_iso, "art-alpha", 111111, "200000000001", 150000, 150000, "WB-GI-10", "confirm", "waiting"),
            (1003, now_iso, "art-beta", 222222, "200000000002", 250000, 250000, None, "cancel", "canceled"),
        ],
    )
    conn.commit()
    conn.close()
    return tmp_path


@pytest.fixture
def mock_gdrive_api(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_creds = MagicMock()
    mock_creds.expired = False
    monkeypatch.setattr(
        gdrive_mod.user_credentials.Credentials,
        "from_authorized_user_info",
        lambda *args, **kwargs: mock_creds,
    )
    monkeypatch.setattr(
        gdrive_mod.service_account.Credentials,
        "from_service_account_info",
        lambda *args, **kwargs: mock_creds,
    )

    mock_service = MagicMock()
    mock_create = mock_service.files.return_value.create
    mock_create.return_value.execute.return_value = {
        "id": "gdrive-file-999",
        "name": "wb_general_report_2026.11.25_00.00.00.xlsx",
        "webViewLink": "https://google.com",
    }
    monkeypatch.setattr(gdrive_mod, "build", lambda *args, **kwargs: mock_service)
    return mock_create


@pytest_asyncio.fixture
async def live_http_server(sample_work_dir: Path):
    token = "ci-bearer-token"
    app = create_app(domain="127.0.0.1", token=token)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    _, port = sock.getsockname()
    sock.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)

    yield f"http://127.0.0.1:{port}/mcp", token

    server.should_exit = True
    await task

@pytest.mark.skipif(
    not os.getenv("RUN_REAL_WB_TESTS"),
    reason="Запускается вручную с RUN_REAL_WB_TESTS=1",
)
async def test_analytics_tools_in_memory(sample_work_dir: Path):
    async with Client(mcp) as client:
        summary = await client.call_tool("get_orders_summary", {"days": 7})
        assert not summary.is_error
        assert "Итого: 3 шт." in summary.content[0].text
        assert "5500.0 ₽" in summary.content[0].text

        top = await client.call_tool("get_top_articles", {"days": 30, "limit": 5})
        assert not top.is_error
        assert "art-alpha" in top.content[0].text
        assert "3000.0 ₽" in top.content[0].text
        assert "art-beta" not in top.content[0].text

        cancels = await client.call_tool("get_cancellations_stats", {"days": 30})
        assert not cancels.is_error
        assert "art-beta: 1 отмен на 2500.0 ₽" in cancels.content[0].text

        order_info = await client.call_tool("find_order_by_id", {"order_id": 1001})
        assert not order_info.is_error
        assert "Заказ №1001" in order_info.content[0].text
        assert "WB-GI-10" in order_info.content[0].text
        assert "Футболка базовая Alpha" in summary.content.text
        assert "Футболка базовая Alpha" in top.content.text


async def test_upload_report_tool_in_memory(sample_work_dir: Path, mock_gdrive_api: MagicMock):
    async with Client(mcp) as client:
        res = await client.call_tool("upload_latest_report_to_drive", {})
        assert not res.is_error
        assert "wb_general_report_2026.11.25_00.00.00.xlsx" in res.content[0].text
        assert "https://google.com" in res.content[0].text

        call_kwargs = mock_gdrive_api.call_args.kwargs
        assert call_kwargs["body"]["parents"] == ["test-folder-123"]
        assert (
            call_kwargs["media_body"].mimetype()
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


async def test_streamable_http_unauthorized(live_http_server):
    url, _ = live_http_server

    with pytest.RaisesGroup(
        pytest.RaisesExc(MCPError, check=lambda e: e.code == -32603),
        flatten_subgroups=True,
    ):
        async with streamable_http_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()


async def test_streamable_http_authorized_flow(live_http_server, mock_gdrive_api: MagicMock):
    url, token = live_http_server

    http_client = httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(10, read=30),
    )

    async with http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                tool_names = {t.name for t in tools.tools}
                assert {
                    "get_orders_summary",
                    "get_top_articles",
                    "get_cancellations_stats",
                    "find_order_by_id",
                    "upload_latest_report_to_drive",
                }.issubset(tool_names)

                res = await session.call_tool("get_orders_summary", {"days": 7})
                assert not res.is_error
                assert "Итого: 3 шт." in res.content[0].text
