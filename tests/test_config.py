import pytest

from wb_reporter.app_config import AppConfig


def test_work_dir_created(cfg, tmp_path):
    assert (cfg.work_dir / "responses").exists()
    assert (cfg.work_dir / "logs").exists()
    assert cfg.db_path == cfg.work_dir / "wb.db"


def test_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "t")
    monkeypatch.setenv("FETCH_DATA", "0")
    monkeypatch.setenv("FETCH_INTERVAL_MINUTES", "7")
    monkeypatch.setenv("USE_SANDBOX_UPDATE", "1")
    monkeypatch.setenv("WB_ENDPOINTS", "orders,sales")
    cfg = AppConfig(work_dir=tmp_path / "w")
    assert cfg.fetch_data is False
    assert cfg.fetch_interval_minutes == 7
    assert cfg.use_sandbox_update is True
    assert cfg.endpoints == ["orders", "sales"]


def test_missing_token_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    with pytest.raises(ValueError):
        AppConfig(work_dir=tmp_path / "w")


def test_backoff_intervals():
    from wb_reporter.wb_api import retry_delay, BACKOFF_DEFAULT_SEC

    for i, d in enumerate(BACKOFF_DEFAULT_SEC):
        assert retry_delay(i) == d
    # далее удвоение
    assert retry_delay(5) == 28800
    assert retry_delay(6) == 57600
    # потолок 24 часа
    assert retry_delay(7) == 86400
    assert retry_delay(20) == 86400
