import pytest
import responses
import logging
from pathlib import Path
from wb_client import WBClient
from app_config import AppConfig

@pytest.fixture
def mock_config(tmp_path, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test_token")
    monkeypatch.setenv("WORK_DIR", str(tmp_path))
    
    config = AppConfig()
    # Ускоряем ретраи для тестов
    config.retry_delays_sec = [0.1, 0.2] 
    config.max_retry_sec = 1
    return config

@pytest.fixture
def mock_logger():
    logger = logging.getLogger("test_wb_client")
    logger.setLevel(logging.DEBUG)
    return logger

@responses.activate
def test_ping_success(mock_config, mock_logger):
    responses.add(responses.GET, "https://marketplace-api.wildberries.ru/ping", status=200)
    responses.add(responses.GET, "https://content-api.wildberries.ru/ping", status=200)
    
    client = WBClient(mock_config, mock_logger)
    client.ping()
    
    assert len(responses.calls) == 2

@responses.activate
def test_request_429_retry_logic(mock_config, mock_logger):
    url = "https://marketplace-api.wildberries.ru/api/v3/orders"
    
    # Первый запрос - 429, второй - 200 OK
    responses.add(responses.GET, url, status=429)
    responses.add(responses.GET, url, json={"orders": [{"id": 123}]}, status=200)
    
    client = WBClient(mock_config, mock_logger)
    data = client.request("GET", url, "v3_orders")
    
    assert data == {"orders": [{"id": 123}]}
    assert len(responses.calls) == 2
    
    # Проверяем, что сырые ответы сохранились в work_dir/responses
    saved_files = list(client.config.responses_dir.glob("*.json"))
    assert len(saved_files) == 2