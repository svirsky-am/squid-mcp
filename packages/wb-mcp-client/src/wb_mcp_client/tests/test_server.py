import asyncio
import socket
import httpx
import httpx2
import pytest
import uvicorn

from mcp import ClientSession, MCPError
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from wb_mcp_server.server import create_app, mcp


@pytest.fixture
def mock_external_http(monkeypatch):
    """Мокает исходящие запросы httpx внутри инструмента get_example_page."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com"
        return httpx.Response(
            status_code=200,
            text="<html><body><h1>Example Domain</h1></body></html>",
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(transport=transport, **kwargs),
    )


@pytest.fixture
async def live_mcp_server():
    """Поднимает реальный Uvicorn-сервер на свободном порту для тестов Streamable HTTP."""
    token = "test-secret-token"
    app = create_app(domain="127.0.0.1", token=token)

    # Находим свободный локальный порт
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)

    yield f"http://127.0.0.1:{port}/mcp", token

    server.should_exit = True
    await task


# --- Сценарий 1: In-Memory тест без поднятия HTTP-сервера ---
async def test_tool_in_memory(mock_external_http):
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert any(t.name == "get_example_page" for t in tools.tools)

        result = await client.call_tool("get_example_page", {"url": "https://example.com"})
        assert not result.is_error
        assert "Example Domain" in result.content[0].text


# --- Сценарий 2: Ошибка авторизации по Streamable HTTP без токена ---
async def test_streamable_http_unauthorized(live_mcp_server):
    url, _ = live_mcp_server

    with pytest.RaisesGroup(
        pytest.RaisesExc(MCPError, check=lambda e: e.code == -32603),
        flatten_subgroups=True,
    ):
        async with streamable_http_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()


# --- Сценарий 3: Полный цикл работы по Streamable HTTP с валидным Bearer-токеном ---
async def test_streamable_http_authorized(live_mcp_server, mock_external_http):
    url, token = live_mcp_server

    # В mcp 2.x для streamable_http_client передается pre-built httpx2.AsyncClient с заголовками
    http_client = httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(10, read=30),
    )

    async with http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                assert [t.name for t in tools.tools] == ["get_example_page"]

                result = await session.call_tool(
                    "get_example_page",
                    arguments={"url": "https://example.com"},
                )
                assert not result.is_error
                assert "Example Domain" in result.content[0].text