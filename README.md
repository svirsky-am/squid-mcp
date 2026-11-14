# WB reporter

Служба выгрузки данных Wildberries (Marketplace API v3, Statistics API, Content API),
хранение в SQLite (SQLAlchemy) и генерация сводных xlsx-отчётов. Отчёты можно
выгружать на Google Drive. Есть MCP-сервер для аналитических запросов (Yandex Alice Pro).

## Структура

```
src/wb_reporter/   исходники
tests/             pytest-тесты
work_dir/          кеш: responses/, logs/, wb.db (создаётся автоматически)
.staff/env         секреты и переменные окружения (в .gitignore)
```

## Установка (venv + uv)

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install uv
just install          # uv sync --all-extras
just test             # pytest
```

Переменные окружения — в `.staff/env` (пример в `.staff/env.example`), загружаются
рецептами just через `set -a; . .staff/env; set +a`. Ключевые переменные:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `API_TOKEN` | — | токен WB API |
| `WB_SANDBOX_TOKEN` | = API_TOKEN | токен песочницы контента |
| `WORK_DIR` | `work_dir` | кеш, БД, логи, ответы API |
| `FETCH_DATA` | `1` | `0` — не ходить в сеть, работать с кешем/БД |
| `FETCH_INTERVAL_MINUTES` | `30` | период fetch в службе |
| `CARDS_INTERVAL_MINUTES` | `120` | период выгрузки карточек |
| `LOOKBACK_DAYS` | `30` | глубина выгрузки за проход |
| `USE_SANDBOX_UPDATE` | `0` | `1` — правки карточек в песочницу контента |
| `GDRIVE_ENABLED` / `GDRIVE_FOLDER_ID` / `GDRIVE_SA_FILE` | off | выгрузка отчётов на Drive |

## Задействованные эндпойнты

| Назначение | Метод и путь | Хост |
|---|---|---|
| Проверка подключения | `GET /ping` | common-api.wildberries.ru |
| Заказы FBS (сборочные задания) | `GET /api/v3/orders` (пагинация `next`, период ≤ 30 дней, даты в Unix-таймстампах) | marketplace-api.wildberries.ru |
| Актуальные статусы заказов | `POST /api/v3/orders/status` (до 1000 ID за запрос; поля `wbStatus`, `supplierStatus`) | marketplace-api.wildberries.ru |
| Склады продавца | `GET /api/v3/warehouses` | marketplace-api.wildberries.ru |
| Продажи и возвраты (цены в копейках) | `GET /api/v1/supplier/sales` | statistics-api.wildberries.ru |
| Поступления | `GET /api/v1/supplier/incomes` | statistics-api.wildberries.ru |
| Остатки | `GET /api/v1/supplier/stocks` | statistics-api.wildberries.ru |
| Список карточек | `POST /content/v2/get/cards/list` (курсор: `updatedAt` + `nmID`, ≤ 100 карточек за запрос, стоп при `total < limit`) | content-api.wildberries.ru |
| Правка карточек | `POST /content/v2/cards/update` | content-api.wildberries.ru или content-api-sandbox.wildberries.ru |
| Создание карточек (дубликаты) | `POST /content/v2/cards/upload` | content-api.wildberries.ru или content-api-sandbox.wildberries.ru |

## Архитектура службы

1. При старте — `GET /ping`.
2. Периодически (FETCH_INTERVAL_MINUTES) все эндпойнты из `WB_ENDPOINTS` выгружаются
   параллельно: asyncio + `asyncio.to_thread` (пул потоков), записи апсертятся в SQLite.
3. Отдельный поток (`cards_worker`) выгружает карточки по CARDS_INTERVAL_MINUTES.
4. После каждого fetch строится сводный xlsx (`Реестр`, `По дням`, `По артикулам`),
   при GDRIVE_ENABLED — уходит на Google Drive.
5. Всё, что отвечает WB, сохраняется в `work_dir/responses/<label>/*.json`;
   логи — в `work_dir/logs/wb_reporter.log` (ротация 5 МБ × 5).

Ретраи при 429: 2 мин → 30 мин → 1 ч → 2 ч → 4 ч → далее ×2 (потолок MAX_RETRY_SEC).

## Запуск

```bash
just run-client            # служба
just sync                  # разовая выгрузка
just report 2026-10-01 2026-10-31 wb_registry.xlsx   # отчёт вне службы, из БД
just mcp                   # MCP-сервер для агента
```

Дублирование карточки (сначала `just sync`-подобная выгрузка карточек,
`python -m wb_reporter.cli cards`):

```bash
uv run python -m wb_reporter.cli copy-card --nm-id 123 --article NEW-ART \
    --title "Новое название" --char "Состав=хлопок" --char "ТнВЭД=1234567890"
# с --update-only — правка существующей карточки через /content/v2/cards/update
# без него — создание копии через /content/v2/cards/upload
```

Для теста изменений установите `USE_SANDBOX_UPDATE=1` и токен `WB_SANDBOX_TOKEN` —
запросы уйдут на content-api-sandbox.wildberries.ru.

## systemd

```bash
just service-install /opt/wb-reporter
```

Юнит `deploy/wb-reporter.service` подхватывает `/opt/wb-reporter/.staff/env`
через `EnvironmentFile` и запускает `.venv/bin/python -m wb_reporter.cli run`.

## Тесты

```bash
just test          # все тесты
just test-cov      # с покрытием
```

Покрыты: конфиг (env-переопределения), backoff 429, ретраи и сохранение
ответов, пагинация orders/cards, апсерт без дублей, перевод копеек в рубли,
сборка отчёта из БД, дублирование карточек.

## Roadmap: Alice Pro

Клиент уже подготовлен к переезду на выделенный сервер (systemd-юнит приложен).
MCP-сервер (`just mcp`, инструменты `sync_data`, `build_report`, `copy_card`, ...)
регистрируется в MCP Hub Yandex AI Studio, и аналитик сможет просить Алису
строить сводные таблицы, которые уходят на Google Drive / Яндекс Диск.
