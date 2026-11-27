# Развёртывание на VPS (порт 443) и интеграция с Яндекс Алисой

Документ описывает развёртывание фонового сборщика WB (`wb-collector`), MCP-сервера (`wb-mcp-server`) и HTTPS-прокси Caddy на стандартном порту `443`, а также подключение агента в Yandex AI Studio.

---

## 1. Подготовка сервера и файлов конфигурации

1. Установите Docker и плагин Docker Compose v2 на сервере (Ubuntu 24.04):
   ```bash
   apt update && apt install -y docker.io docker-compose-v2
   ```
2. Разместите в директории `.staff/` на сервере (папка не отслеживается Git):
   * `.staff/env` — переменные окружения;
   * `.staff/gdrive_token.json` — OAuth-токен Google Диска (см. `docs/gdrive_auth.md`);
   * `.staff/target_host/cert.pem` и `.staff/target_host/key.pem` — SSL-сертификат и приватный ключ для домена `market-squid-mcp.ru`.

### Пример `.staff/env`

```env
API_TOKEN="ваш_токен_wildberries"
WORK_DIR="/app/work_dir"

# Загрузка отчётов на Google Диск
ENABLE_GDRIVE_UPLOAD=true
GOOGLE_CREDENTIALS_PATH="/app/.staff/gdrive_token.json"
GOOGLE_DRIVE_FOLDER_ID="1V6W_-OqoYov5PkC78mwV6MxGU0EkjldH"

# Параметры MCP-сервера для Алисы
MCP_DOMAIN="market-squid-mcp.ru"
MCP_BEARER_TOKEN="сгенерированный_длинный_токен"
```

> Сгенерировать надёжный `MCP_BEARER_TOKEN` можно командой `openssl rand -hex 32`.

---

## 2. Конфигурация Caddy и Docker Compose (порт 443)

### `configs/Caddyfile`

```caddyfile
{
    auto_https off
}

https://market-squid-mcp.ru {
    tls /app/.staff/target_host/cert.pem /app/.staff/target_host/key.pem

    reverse_proxy wb-mcp-server:8000 {
        flush_interval -1
    }
}
```

### Запуск контейнеров

Откройте порт `443/tcp` в фаерволе сервера и запустите стек:

```bash
sudo ufw allow 443/tcp
docker compose up -d --build
```

### Проверка доступности

1. Без токена сервер должен отклонять запросы со статусом `401 Unauthorized`:
   ```bash
   curl -i -X POST https://market-squid-mcp.ru
   ```
2. С токеном на запрос `initialize` должен возвращаться статус `200 OK`:
   ```bash
   curl -i -X POST "https://market-squid-mcp.ru" \
     -H "Authorization: Bearer ВАШ_MCP_BEARER_TOKEN" \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
   ```

---

## 3. Назначение прав в Yandex Cloud

Перед регистрацией сервера в AI Studio убедитесь, что у вашей учётной записи в нужном каталоге Yandex Cloud назначены роли:
* `serverless.mcpGateways.editor` — для создания и управления внешними MCP-серверами в MCP Hub;
* `ai.assistants.editor` — для создания и настройки агентов в Agent Atelier.

Назначить роли можно в [консоли Yandex Cloud](https://yandex.cloud) (раздел **Каталог → Права доступа**) или через CLI:

```bash
yc resource-manager folder add-access-binding <FOLDER_ID> \
  --role serverless.mcpGateways.editor \
  --subject userAccount:<USER_ID>

yc resource-manager folder add-access-binding <FOLDER_ID> \
  --role ai.assistants.editor \
  --subject userAccount:<USER_ID>
```

---

## 4. Регистрация MCP-сервера в Yandex AI Studio

1. Откройте [Yandex AI Studio](https://yandex.ru) → **Agent Atelier** → **MCP-серверы**.
2. Нажмите **Создать MCP-сервер** → **Внешний MCP-сервер**.
3. Заполните параметры:
   * **Имя:** `wb-alice-server`
   * **URL сервера:** `https://market-squid-mcp.ru`
   * **Тип транспорта:** `Streamable HTTP`
   * **Авторизация:** Bearer-токен со значением `MCP_BEARER_TOKEN` из `.staff/env`.
4. Нажмите кнопку обновления списка инструментов, отметьте галочками все 5 инструментов (`get_orders_summary`, `get_top_articles`, `get_cancellations_stats`, `find_order_by_id`, `upload_latest_report_to_drive`) и сохраните сервер.

---

## 5. Создание агента и выдача доступа пользователям Алисы

1. Перейдите в **Agent Atelier → Создать агента**.
2. Выберите модель с поддержкой инструментов (например, **YandexGPT Pro** или **Alice AI**).
3. Вставьте системную инструкцию из `docs/alice_agent_skills.md`.
4. В разделе **Инструменты (Tools)** отметьте чекбокс `wb-alice-server`.
5. Нажмите **Опубликовать**, выберите доступ по ссылке / для выбранных пользователей, добавьте аккаунты коллег (например, `aouta91@yandex.ru`) и отправьте им прямую ссылку.
6. При переходе по ссылке под своим Яндекс ID агент откроется у пользователя в чате Алисы.

