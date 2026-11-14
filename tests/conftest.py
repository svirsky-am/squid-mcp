import pytest

from wb_reporter.app_config import AppConfig


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Конфиг на тестах: свой work_dir, без сети, нулевые задержки ретраев."""
    monkeypatch.setenv("API_TOKEN", "test-token")
    for var in ("FETCH_DATA", "FETCH_INTERVAL_MINUTES", "USE_SANDBOX_UPDATE", "GDRIVE_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    cfg = AppConfig(work_dir=tmp_path / "work")
    cfg.retry_delays_sec = [0, 0, 0, 0, 0]
    return cfg
