import httpx
import pytest
from wb_mcp_client.client import fetch_example_page


def test_fetch_example_page_http_error(monkeypatch):
    # Проверяем обработку ошибки (например, 404 или 500)
    def mock_get(url: str, timeout: float):
        return httpx.Response(
            status_code=500,
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", mock_get)

    with pytest.raises(httpx.HTTPStatusError):
        fetch_example_page()

async def test_fetch_example_page_success(monkeypatch):
    # Создаем обработчик, который перехватит запрос внутри AsyncClient
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com"
        return httpx.Response(
            status_code=200,
            text="<html><body><h1>Example Domain</h1></body></html>",
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    # Подменяем AsyncClient, чтобы он использовал наш MockTransport
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(transport=transport, **kwargs),
    )

    result = await fetch_example_page()
    assert "Example Domain" in result


async def test_fetch_example_page_http_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500)

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(transport=transport, **kwargs),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_example_page()