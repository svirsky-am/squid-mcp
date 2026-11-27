---
name: squid-mcp-devops
description: Разработка, тестирование, деплой на VPS (Docker + Caddy на порту 443) и управление OAuth-токенами Google Drive в монорепозитории squid-mcp (wb-mcp-client и wb-mcp-server).
---

# Навык разработки и эксплуатации репозитория `squid-mcp`

Используй этот навык при внесении изменений в пакеты `wb-mcp-client` или `wb-mcp-server`, настройке CI/CD, обновлении OAuth-токенов Google Drive или развёртывании стека на выделенном сервере `market-squid-mcp.ru`.

---

## 1. Архитектура и ограничения стека

* **Workspace (`uv`):**
  * `packages/wb-mcp-client` — фоновый сборщик WB API (`/api/v3/orders`, `/api/v3/orders/status`, `/ping`), SQLite (`WAL`-режим), генерация многостраничного `.xlsx` (`build_excel_report_general`) и автозагрузка на Google Диск (`build_and_upload_report`).
  * `packages/wb-mcp-server` — MCP-сервер (`mcp 2.x`, класс `MCPServer` из `mcp.server.mcpserver`), читающий `work_dir/wb.db` строго в режиме `mode=ro` и обслуживающий транспорт `Streamable HTTP` на `/mcp` с проверкой `BearerAuthMiddleware`.
* **Docker и версии Python:**
  * На VPS и в локальной среде могут отличаться минорные версии Python 3.14, поэтому в `Dockerfile` и `docker-compose.yml` используется `uv sync --no-lock` / `uv run --no-lock --no-sync` без привязки к `uv.lock`.
* **Сеть и HTTPS:**
  * Внешний вход работает строго на стандартном порту **`443`** через контейнер `caddy` с ручными сертификатами `.staff/target_host/cert.pem` и `.staff/target_host/key.pem` (`auto_https off`, `flush_interval -1`).

---

## 2. Типовые сценарии и команды

### Добавление зависимостей и запуск тестов
Перед любым коммитом или деплоем обязательно прогоняй все тесты workspace:
```bash
uv add --package <wb-mcp-client|wb-mcp-server> <package_name>
uv run pytest -v
```

### Перевыпуск OAuth-токена Google Диска (`gdrive_token.json`)
Если `refresh_token` был отозван или сменился аккаунт, сгенерируй токен локально на машине с браузером (используется тип `authorized_user`, так как сервисные аккаунты не имеют квоты в личном Google Диске) и скопируй его на VPS в `.staff/gdrive_token.json`:
```bash
uv run --package wb-mcp-client python tools/generate_gdrive_token.py \
  --client-secrets .staff/oauth_client.json \
  --output .staff/gdrive_token.json \
  --port 8080
```

### Ручной запуск сборки отчёта и выгрузки на Google Диск
```bash
set -a && source .staff/env && set +a

# Построить .xlsx из SQLite и выгрузить на Google Диск (если ENABLE_GDRIVE_UPLOAD=true)
uv run --package wb-mcp-client wb-report

# Выгрузить последний готовый .xlsx без пересборки
uv run --package wb-mcp-server wb-upload-gdrive
```

### Деплой и диагностика на VPS (`market-squid-mcp.ru`)
```bash
# Сборка и перезапуск всех контейнеров (wb-collector, wb-mcp-server, caddy)
docker compose up -d --build

# Просмотр логов в реальном времени
docker compose logs -f

# Проверка доступности MCP-эндпоинта снаружи (без токена ожидается 401)
curl -i -X POST https://market-squid-mcp.ru
```

---

## 3. Чек-лист при добавлении нового `@mcp.tool()`

1. Реализуй инструмент в `packages/wb-mcp-server/src/wb_mcp_server/server.py`, используя `_query_db()` (read-only соединение к `wb.db`).
2. Добавь тест в `packages/wb-mcp-server/tests/test_analytics_and_drive.py` (проверка через `Client(mcp)` и `Streamable HTTP`).
3. Обнови описание нового инструмента в пользовательском навыке `.agents/skills/wb-fbs-analytics/SKILL.md`.
4. После деплоя на VPS нажми **Обновить инструменты** в карточке `wb-alice-server` в Yandex AI Studio, чтобы агент увидел новую функцию.

