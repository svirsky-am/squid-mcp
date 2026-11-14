import pytest
import httpx
import respx
import os
from pathlib import Path
from src.wb_client import WBClient
from src.config import AppConfig

@pytest.fixture
def config(tmp_path):
    os.environ["WORK_DIR"] = str(tmp_path)
    os.environ["API_TOKEN"] = "test_token"
    os.environ["FETCH_DATA"] = "false"
    os.environ["RETRY_DELAY_0"] = "1" # Ускоряем тесты
    os.environ["RETRY_DELAY_1"] = "2"
    return AppConfig()

@pytest.mark.asyncio
@respx.mock
async def test_fetch_success(config):
    client = WBClient(config)
    mock_route = respx.get("https://marketplace-api.wildberries.ru/api/v3/orders").mock(
        return_value=httpx.Response(200, json={"orders": []})
    )
    
    result = await client.request("/api/v3/orders")
    assert result == {"orders": []}
    assert mock_route.called

@pytest.mark.asyncio
@respx.mock
async def test_fetch_429_retry(config):
    client = WBClient(config)
    
    route = respx.get("https://marketplace-api.wildberries.ru/api/v3/orders")
    # Первый запрос - 429, второй - 200 OK
    route.side_effect = [
        httpx.Response(429),
        httpx.Response(200, json={"orders": [{"id": "123"}]})
    ]
    
    result = await client.request("/api/v3/orders")
    assert result == {"orders": [{"id": "123"}]}
    assert route.call_count == 2
    
    # Проверяем, что файл ответа сохранился в work_dir/responses
    assert len(list(config.responses_dir.glob("*.json"))) == 1