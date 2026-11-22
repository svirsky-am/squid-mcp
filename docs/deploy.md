# Развёртывание MCP-сервера и подключение к Алисе (Yandex AI Studio)

Документ описывает процесс развёртывания Python MCP-сервера (`wb-mcp-server`) на выделенном сервере с публичным IP и доменом, настройку HTTPS и регистрацию в **Yandex AI Studio / MCP Hub** для работы через чат в Алисе.

---

## 1. Подготовка сервера и окружения

Предполагается, что у вас есть Linux-сервер (Ubuntu/Debian) с белым IP и A-записью в DNS, указывающей на этот IP (например, `mcp.example.ru`).

### Установка `uv` и Caddy

Подключитесь к серверу по SSH и установите менеджер пакетов `uv` и веб-сервер **Caddy** (он автоматически выпустит и будет продлевать SSL-сертификат Let's Encrypt):

```bash
# Установка uv
curl -LsSf https://astral.sh | sh
source $HOME/.local/bin/env

# Установка Caddy (Ubuntu / Debian)
sudo apt update && sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://cloudsmith.io' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://cloudsmith.io' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

### Клонирование проекта и установка зависимостей

```bash
sudo mkdir -p /opt/wb-alice-tool
sudo chown $USER:$USER /opt/wb-alice-tool
git clone <URL_ВАШЕГО_РЕПОЗИТОРИЯ> /opt/wb-alice-tool
cd /opt/wb-alice-tool

# Установка Python и всех зависимостей workspace
uv sync --all-packages
```

---

## 2. Настройка автозапуска (systemd)

Сгенерируйте надёжный секретный токен для защиты эндпоинта `/mcp` от посторонних запросов:

```bash
openssl rand -hex 32
```

Создайте systemd-юнит `/etc/systemd/system/wb-mcp.service`:

```ini
[Unit]
Description=WB MCP Server for Alice
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/wb-alice-tool
Environment="MCP_DOMAIN=mcp.example.ru"
Environment="MCP_BEARER_TOKEN=ВСТАВЬТЕ_СГЕНЕРИРОВАННЫЙ_ТОКЕН"
ExecStart=/home/ubuntu/.local/bin/uv run --package wb-mcp-server wb-mcp-server
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

*(Замените `ubuntu` на имя вашего пользователя на сервере и `mcp.example.ru` на ваш реальный домен.)*

Запустите службу и проверьте её статус:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wb-mcp
sudo systemctl status wb-mcp
```

---

## 3. Настройка HTTPS и обратного прокси (Caddy)

Откройте порты `80` и `443` в фаерволе (если включён `ufw`):

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

Настройте `/etc/caddy/Caddyfile` для проксирования запросов на локальный порт `8000`:

```caddyfile
mcp.example.ru {
    reverse_proxy 127.0.0.1:8000 {
        # Обязательно для протокола Streamable HTTP (SSE): отключаем буферизацию
        flush_interval -1
    }
}
```

Перезапустите Caddy для применения настроек и выпуска SSL-сертификата:

```bash
sudo systemctl reload caddy
```

### Проверка доступности

Убедитесь с локального компьютера, что сервер отвечает по HTTPS и требует авторизацию:

```bash
# Без токена должен вернуться статус 401
curl -i -X POST https://example.ru
```

---

## 4. Регистрация в MCP Hub (Yandex AI Studio)

1. Перейдите в консоль [Yandex AI Studio](https://yandex.ru).
2. Убедитесь, что в выбранном каталоге Yandex Cloud у вас назначены роли `serverless.mcpGateways.editor` и `iam.serviceAccounts.user`.
3. В левом меню откройте **Agent Atelier** (или **Agent Core**) → **MCP-серверы**.
4. Нажмите **Создать MCP-сервер** → выберите тип **Внешний MCP-сервер**.
5. Заполните параметры:
   * **Имя:** уникальное имя латиницей (например, `wb-alice-server`).
   * **URL сервера:** `https://example.ru`
   * **Тип транспорта:** `Streamable HTTP`
   * **Авторизация:** выберите передачу Bearer-токена (через секрет Yandex Lockbox или заголовок `Authorization`) и укажите значение вашего `MCP_BEARER_TOKEN`.
6. Нажмите **Проверить подключение / Получить инструменты** — в списке должны отобразиться ваши функции, помеченные декоратором `@mcp.tool()` (например, `get_example_page`).
7. Сохраните MCP-сервер.

---

## 5. Создание агента и открытие доступа в Алисе

1. В **Yandex AI Studio** перейдите в раздел **Agent Atelier** → **Создать агента**.
2. Задайте имя и описание агента (они будут видны пользователям в чате Алисы).
3. В поле **Инструкция (системный промпт)** опишите роль агента и правила вызова ваших инструментов.
4. В блоке **Инструменты (Tools)** нажмите **Добавить** → **MCP-сервер** и выберите зарегистрированный `wb-alice-server`.
5. Протестируйте работу агента во встроенном окне отладки справа, отправив тестовый запрос.
6. Нажмите **Опубликовать** и выберите уровень доступа **По ссылке (приватный)**.
7. Скопируйте полученную ссылку и отправьте вашим 2–3 пользователям — при переходе по ней агент откроется в интерфейсе чата Алисы под их Яндекс ID.

---

## 6. Обновление кода на сервере

При добавлении новых инструментов в код:

```bash
cd /opt/wb-alice-tool
git pull
uv sync --all-packages
sudo systemctl restart wb-mcp
```

*Примечание: если вы добавили новые `@mcp.tool()` или изменили их параметры, откройте карточку MCP-сервера в Yandex AI Studio и нажмите кнопку обновления списка инструментов.*
