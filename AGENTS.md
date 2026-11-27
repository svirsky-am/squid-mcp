# AGENTS.md — Руководство для ИИ-агентов по репозиторию `squid-mcp`

## Обзор проекта

Монорепозиторий (`uv` workspace) для автоматического сбора аналитики Wildberries (FBS) и предоставления доступа к ней через чат Яндекс Алисы по протоколу **MCP (Streamable HTTP)**.

### Структура репозитория

* `packages/wb-mcp-client/` — фоновый сборщик данных WB API (`/api/v3/orders`, `/api/v3/orders/status`, `/ping`), запись в SQLite (`work_dir/wb.db`), генератор многостраничных Excel-отчётов (`openpyxl`) и автозагрузка на Google Диск.
* `packages/wb-mcp-server/` — MCP-сервер на базе `mcp 2.x` (`MCPServer`), предоставляющий read-only инструменты аналитики по `wb.db` и ручную выгрузку отчётов на Google Диск.
* `tools/` — вспомогательные CLI-утилиты (в т.ч. `generate_gdrive_token.py` для генерации OAuth-токена Google).
* `configs/` — конфигурации инфраструктуры (`Caddyfile` для HTTPS-терминации на порту `443`).
* `docs/` — проектная документация и инструкции по развёртыванию.
* `.staff/` *(в `.gitignore`)* — секреты, `.staff/env`, OAuth-токены Google и SSL-сертификаты (`cert.pem`, `key.pem`).
* `work_dir/` *(в `.gitignore`)* — база данных `wb.db`, сырые JSON-ответы WB (`responses/`), логи (`logs/`) и сформированные `.xlsx`-отчёты (`reports/`).

---

## Правила разработки и архитектурные соглашения

1. **Менеджер пакетов и окружение:**
   * Используйте исключительно `uv` (`uv add --package <pkg>`, `uv run ...`).
   * В `Dockerfile` не используйте флаг `--frozen`, чтобы сборка не зависела от версии Python в локальном `uv.lock`; используйте `uv sync --no-lock --all-packages`.
2. **SDK MCP (`mcp 2.x`):**
   * Используйте `from mcp.server.mcpserver import MCPServer` (класс `FastMCP` удалён в `mcp 2.x`).
   * Настройки DNS rebinding (`TransportSecuritySettings`) должны разрешать домен `MCP_DOMAIN` и локальные адреса.
   * Эндпоинт `/mcp` защищён `BearerAuthMiddleware` через переменную `MCP_BEARER_TOKEN`.
3. **Работа с SQLite:**
   * В `wb-mcp-client` используется режим `PRAGMA journal_mode=WAL;`.
   * В `wb-mcp-server` база данных открывается **строго в режиме только чтения**: `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)`.
4. **Форматирование времени и логирование:**
   * Запрещено использовать `print()` в основном коде служб — используйте `logging` с записью в `work_dir/logs/`.
   * Единый формат таймстемпов в именах файлов ответов и отчётов: `%Y.%m.%d_%H.%M.%S`.
5. **Обработка лимитов WB API (`429 Too Many Requests`):**
   * Повтор запросов выполняется по расписанию задержек из `AppConfig.retry_delays_sec`: `120 -> 1800 -> 3600 -> 7200 -> 14400` секунд, далее умножение на 2 до `max_retry_sec`.
6. **Интеграция с Google Диском:**
   * Используется `_load_drive_credentials()`, поддерживающая оба формата: `authorized_user` (OAuth с `refresh_token`) и `service_account` (для Shared Drives).
   * Файлы загружаются с оригинальным MIME-типом `.xlsx` без конвертации в Google Таблицы.

---

## Команды для проверки и запуска

```bash
# Запуск всех тестов workspace (обязательно перед коммитом)
uv run pytest -v

# Ручная генерация Excel-отчёта и загрузка на Google Диск
uv run --package wb-mcp-client wb-report

# Ручная загрузка последнего отчёта на Google Диск
uv run --package wb-mcp-server wb-upload-gdrive

# Сборка и перезапуск в Docker на сервере
docker compose up -d --build
```

