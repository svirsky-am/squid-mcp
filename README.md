# squid-mcp

Монорепозиторий (`uv` workspace) для автоматического сбора аналитики Wildberries (FBS), формирования многостраничных Excel-отчётов с выгрузкой на Google Диск и предоставления доступа к данным через чат **Яндекс Алисы** по протоколу **MCP (Streamable HTTP)**.

---

## Архитектура и структура репозитория

```text
squid-mcp/
├── .agents/skills/
│   ├── wb-fbs-analytics/SKILL.md     # Навык для пользователей / агента Yandex AI Studio
│   └── squid-mcp-devops/SKILL.md     # Навык для разработчиков и сопровождения (DevOps)
├── .github/workflows/deploy.yml      # CI/CD: прогон pytest и автодеплой на VPS
├── configs/
│   └── Caddyfile                     # HTTPS-терминатор на порту 443 для Streamable HTTP
├── docs/
│   ├── deploy_and_alice.md           # Развёртывание на VPS (порт 443) и подключение к Алисе
│   ├── gdrive_auth.md                # Настройка Google Cloud и получение gdrive_token.json
│   └── alice_agent_skills.md         # Системный промпт и сценарии агента в Agent Atelier
├── packages/
│   ├── wb-mcp-client/                # Сборщик данных WB API, SQLite (WAL) и генератор .xlsx
│   └── wb-mcp-server/                # MCP-сервер (mcp 2.x, Streamable HTTP + Bearer Auth)
├── tools/
│   └── generate_gdrive_token.py      # CLI-утилита генерации OAuth-токена Google Диска
├── .staff/                           # (в .gitignore) Секреты, .staff/env, токены и SSL PEM
├── work_dir/                         # (в .gitignore) База wb.db, логи, сырые JSON и отчёты
├── AGENTS.md                         # Правила и соглашения репозитория для ИИ-агентов
├── Dockerfile                        # Сборка Python-образа с uv (--no-lock)
└── docker-compose.yml                # Оркестрация wb-collector, wb-mcp-server и caddy
```

---

## Быстрый старт (локальная разработка)

1. **Установите зависимости workspace:**
   ```bash
   uv sync --all-packages
   ```

2. **Подготовьте переменные окружения в `.staff/env`:**
   ```env
   API_TOKEN="ваш_токен_wildberries"
   WORK_DIR="work_dir"

   ENABLE_GDRIVE_UPLOAD=true
   GOOGLE_CREDENTIALS_PATH=".staff/gdrive_token.json"
   GOOGLE_DRIVE_FOLDER_ID="ваш_id_папки_google_drive"

   MCP_DOMAIN="market-squid-mcp.ru"
   MCP_BEARER_TOKEN="ваш_секретный_токен_для_алисы"
   ```

3. **Запустите тесты:**
   ```bash
   uv run pytest -v
   ```

---

## Основные команды

```bash
# Фоновый сборщик заказов WB API -> SQLite -> Excel -> Google Диск
set -a && source .staff/env && set +a
uv run --package wb-mcp-client wb-collector

# Ручная генерация сводного Excel-отчёта (и выгрузка на диск при ENABLE_GDRIVE_UPLOAD=true)
uv run --package wb-mcp-client wb-report

# Ручная выгрузка последнего готового .xlsx на Google Диск без пересборки
uv run --package wb-mcp-server wb-upload-gdrive

# Генерация OAuth-токена Google Диска из oauth_client.json
uv run --package wb-mcp-client python tools/generate_gdrive_token.py

# Запуск MCP-сервера локально
uv run --package wb-mcp-server wb-mcp-server
```

---

## Развёртывание на сервере (Docker + Caddy на порту 443)

1. Разместите на сервере в `.staff/` файлы `env`, `gdrive_token.json`, `target_host/cert.pem` и `target_host/key.pem`.
2. Запустите стек контейнеров:
   ```bash
   docker compose up -d --build
   ```
3. Проверьте доступность MCP-эндпоинта (без токена должен вернуться статус `401 Unauthorized`):
   ```bash
   curl -i -X POST https://market-squid-mcp.ru
   ```

---

## Документация и навыки

* [Развёртывание на VPS (порт 443) и подключение к Яндекс Алисе](docs/deploy_and_alice.md)
* [Настройка авторизации Google Drive и получение `gdrive_token.json`](docs/gdrive_auth.md)
* [Инструкция и промпт агента для Yandex AI Studio](docs/alice_agent_skills.md)
* [Руководство для ИИ-агентов (`AGENTS.md`)](AGENTS.md)
* [Пользовательский навык аналитики WB FBS (`SKILL.md`)](.agents/skills/wb-fbs-analytics/SKILL.md)
* [Навык разработки и эксплуатации (`SKILL.md`)](.agents/skills/squid-mcp-devops/SKILL.md)

