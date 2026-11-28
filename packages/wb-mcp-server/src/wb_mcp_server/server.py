import os
import sqlite3
from pathlib import Path
from typing import Optional

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from wb_mcp_server.gdrive import upload_report_to_gdrive
from wb_mcp_client.cards import sync_cards_now
from wb_mcp_client.stocks import sync_stocks_now


mcp = MCPServer("wb-alice-server")


def _get_db_path() -> Path:
    return Path(os.getenv("WORK_DIR", "work_dir")).resolve() / "wb.db"


def _get_reports_dir() -> Path:
    return Path(os.getenv("WORK_DIR", "work_dir")).resolve() / "reports"


def _query_db(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    db_path = _get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"База данных не найдена: {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


@mcp.tool()
def get_orders_summary(days: int = 7) -> str:
    """Возвращает сводку по заказам FBS, выручке и лидерам товаров за последние N дней."""
    rows = _query_db(
        """
        SELECT
            COALESCE(supplier_status, 'unknown') AS supplier_status,
            COALESCE(wb_status, 'unknown') AS wb_status,
            COUNT(*) AS cnt,
            ROUND(SUM(COALESCE(converted_price, price, 0)) / 100.0, 2) AS total_rub
        FROM fbs_orders
        WHERE created_at >= datetime('now', ?)
        GROUP BY supplier_status, wb_status
        ORDER BY cnt DESC
        """,
        (f"-{days} days",),
    )
    if not rows:
        return f"За последние {days} дн. заказов в базе нет."

    lines = [f"Сводка по заказам FBS за последние {days} дн.:"]
    total_cnt = 0
    total_sum = 0.0
    for r in rows:
        lines.append(f"- {r['supplier_status']} / {r['wb_status']}: {r['cnt']} шт. на {r['total_rub']} ₽")
        total_cnt += r["cnt"]
        total_sum += r["total_rub"]
    lines.append(f"Итого: {total_cnt} шт. на сумму {round(total_sum, 2)} ₽.")

    top_rows = _query_db(
        """
        SELECT
            COALESCE(o.article, 'без артикула') AS article,
            c.title AS title,
            COUNT(*) AS cnt,
            ROUND(SUM(COALESCE(o.converted_price, o.price, 0)) / 100.0, 2) AS total_rub
        FROM fbs_orders o
        LEFT JOIN product_cards c ON o.nm_id = c.nm_id
        WHERE o.created_at >= datetime('now', ?)
          AND COALESCE(o.supplier_status, '') != 'cancel'
          AND COALESCE(o.wb_status, '') NOT IN ('canceled', 'canceled_by_client', 'declined_by_client')
        GROUP BY o.article, c.title
        ORDER BY total_rub DESC
        LIMIT 3
        """,
        (f"-{days} days",),
    )
    if top_rows:
        lines.append("\nТоп-3 товара за период:")
        for idx, tr in enumerate(top_rows, start=1):
            label = f"{tr['title']} ({tr['article']})" if tr["title"] else tr["article"]
            lines.append(f"{idx}. {label} — {tr['cnt']} шт., {tr['total_rub']} ₽")

    return "\n".join(lines)


@mcp.tool()
def get_top_articles(days: int = 30, limit: int = 5) -> str:
    """Возвращает топ товаров и артикулов продавца по выручке с названиями из справочника карточек."""
    rows = _query_db(
        """
        SELECT
            COALESCE(o.article, 'без артикула') AS article,
            o.nm_id AS nm_id,
            c.title AS title,
            c.brand AS brand,
            c.subject_name AS subject_name,
            COUNT(*) AS cnt,
            ROUND(SUM(COALESCE(o.converted_price, o.price, 0)) / 100.0, 2) AS total_rub
        FROM fbs_orders o
        LEFT JOIN product_cards c ON o.nm_id = c.nm_id
        WHERE o.created_at >= datetime('now', ?)
          AND COALESCE(o.supplier_status, '') != 'cancel'
          AND COALESCE(o.wb_status, '') NOT IN ('canceled', 'canceled_by_client', 'declined_by_client')
        GROUP BY o.article, o.nm_id, c.title, c.brand, c.subject_name
        ORDER BY total_rub DESC
        LIMIT ?
        """,
        (f"-{days} days", limit),
    )
    if not rows:
        return f"Нет активных заказов за последние {days} дн."

    lines = [f"Топ-{limit} товаров по выручке за {days} дн.:"]
    for idx, r in enumerate(rows, start=1):
        title_part = f"«{r['title']}» " if r["title"] else ""
        cat_part = f" [{r['subject_name']}]" if r["subject_name"] else ""
        lines.append(
            f"{idx}. {title_part}(арт. {r['article']}, nmId: {r['nm_id']}){cat_part} — "
            f"{r['cnt']} шт., {r['total_rub']} ₽"
        )
    return "\n".join(lines)


@mcp.tool()
def get_cancellations_stats(days: int = 30) -> str:
    """Показывает статистику отмен и возвратов по артикулам за последние N дней."""
    rows = _query_db(
        """
        SELECT
            COALESCE(article, 'без артикула') AS article,
            COUNT(*) AS cnt,
            ROUND(SUM(COALESCE(converted_price, price, 0)) / 100.0, 2) AS lost_rub
        FROM fbs_orders
        WHERE created_at >= datetime('now', ?)
          AND (
              supplier_status = 'cancel'
              OR wb_status IN ('canceled', 'canceled_by_client', 'declined_by_client', 'defect')
          )
        GROUP BY article
        ORDER BY cnt DESC
        """,
        (f"-{days} days",),
    )
    if not rows:
        return f"За последние {days} дн. отменённых заказов не найдено."

    lines = [f"Отмены за последние {days} дн.:"]
    for r in rows:
        lines.append(f"- {r['article']}: {r['cnt']} отмен на {r['lost_rub']} ₽")
    return "\n".join(lines)


@mcp.tool()
def find_order_by_id(order_id: int) -> str:
    """Ищет информацию и текущий статус сборочного задания FBS по его номеру."""
    rows = _query_db("SELECT * FROM fbs_orders WHERE id = ?", (order_id,))
    if not rows:
        return f"Заказ №{order_id} не найден в базе."

    r = rows[0]
    price_rub = round(float(r["converted_price"] or r["price"] or 0) / 100.0, 2)
    return (
        f"Заказ №{r['id']}:\n"
        f"- Создан: {r['created_at']}\n"
        f"- Артикул: {r['article']} (nmId: {r['nm_id']}, SKU: {r['sku']})\n"
        f"- Стоимость: {price_rub} ₽\n"
        f"- Поставка: {r['supply_id'] or 'не добавлен'}\n"
        f"- Статус продавца: {r['supplier_status']} | Статус WB: {r['wb_status']}"
    )


@mcp.tool()
def upload_latest_report_to_drive(filename: Optional[str] = None) -> str:
    """Загружает последний (или указанный по имени) Excel-отчёт на Google Диск."""
    reports_dir = _get_reports_dir()
    target = (reports_dir / filename) if filename else None
    uploaded = upload_report_to_gdrive(file_path=target, reports_dir=reports_dir)
    link = uploaded.get("webViewLink", "ссылка недоступна")
    return f"Отчёт '{uploaded.get('name')}' загружен на Google Диск. Ссылка: {link}"

@mcp.tool()
def sync_product_cards() -> str:
    """Принудительно запрашивает актуальный список карточек товаров из Content API WB и обновляет базу данных."""
    count = sync_cards_now()
    return f"Справочник карточек товаров успешно обновлён. Загружено и сохранено карточек: {count} шт."


@mcp.tool()
def get_product_card_info(query: str) -> str:
    """Ищет карточку товара в локальной базе по артикулу продавца, названию или nmID."""
    rows = _query_db(
        """
        SELECT nm_id, vendor_code, title, brand, subject_name, wb_updated_at
        FROM product_cards
        WHERE CAST(nm_id AS TEXT) = ?
           OR LOWER(vendor_code) LIKE LOWER(?)
           OR LOWER(title) LIKE LOWER(?)
        LIMIT 10
        """,
        (query.strip(), f"%{query.strip()}%", f"%{query.strip()}%"),
    )
    if not rows:
        return f"Карточки по запросу '{query}' не найдены. Попробуйте обновить справочник командой sync_product_cards."

    lines = [f"Найденные карточки ({len(rows)}):"]
    for r in rows:
        lines.append(
            f"- {r['title']} | Артикул: {r['vendor_code']} | nmID: {r['nm_id']} | "
            f"Бренд: {r['brand']} ({r['subject_name']})"
        )
    return "\n".join(lines)

@mcp.tool()
def sync_fbs_stocks() -> str:
    """Принудительно запрашивает актуальные остатки товаров на складах продавца FBS из WB API."""
    res = sync_stocks_now()
    return f"Остатки FBS обновлены. Складов: {res['warehouses']}, записей остатков: {res['stocks_updated']}."


@mcp.tool()
def get_fbs_stocks(query: Optional[str] = None) -> str:
    """Показывает актуальные остатки на складах продавца FBS (всё или по артикулу/названию/SKU)."""
    sql = """
        SELECT
            s.warehouse_id,
            COALESCE(w.name, 'Склад #' || s.warehouse_id) AS warehouse_name,
            s.sku,
            s.amount,
            c.vendor_code,
            c.title
        FROM fbs_stocks s
        LEFT JOIN warehouses w ON s.warehouse_id = w.id
        LEFT JOIN product_cards c ON c.skus_json LIKE '%' || s.sku || '%'
        WHERE s.amount > 0
    """
    params: list = []
    if query and query.strip():
        q = f"%{query.strip()}%"
        sql += " AND (LOWER(c.vendor_code) LIKE LOWER(?) OR LOWER(c.title) LIKE LOWER(?) OR s.sku LIKE ?)"
        params.extend([q, q, q])

    sql += " ORDER BY s.amount DESC LIMIT 25"
    rows = _query_db(sql, tuple(params))

    if not rows:
        return "Актуальных положительных остатков по заданному запросу не найдено."

    lines = ["Актуальные остатки на складах FBS:"]
    for r in rows:
        name = r["title"] or r["vendor_code"] or f"SKU {r['sku']}"
        art = f" (арт. {r['vendor_code']})" if r["vendor_code"] else ""
        lines.append(f"- {name}{art} [{r['warehouse_name']}]: {r['amount']} шт.")
    return "\n".join(lines)


@mcp.tool()
def get_low_stock_forecast(days_threshold: int = 7, lookback_days: int = 14) -> str:
    """Рассчитывает, каких товаров хватит меньше чем на N дней при текущем темпе заказов FBS."""
    rows = _query_db(
        """
        WITH stock_totals AS (
            SELECT sku, SUM(amount) AS total_stock
            FROM fbs_stocks
            GROUP BY sku
        ),
        sales_velocity AS (
            SELECT
                sku,
                COUNT(*) AS sold_cnt,
                CAST(COUNT(*) AS REAL) / ? AS daily_rate
            FROM fbs_orders
            WHERE created_at >= datetime('now', ?)
              AND COALESCE(supplier_status, '') != 'cancel'
              AND COALESCE(wb_status, '') NOT IN ('canceled', 'canceled_by_client', 'declined_by_client')
              AND sku IS NOT NULL AND sku != ''
            GROUP BY sku
        )
        SELECT
            v.sku,
            COALESCE(st.total_stock, 0) AS total_stock,
            v.sold_cnt,
            ROUND(v.daily_rate, 2) AS daily_rate,
            ROUND(COALESCE(st.total_stock, 0) / v.daily_rate, 1) AS days_left,
            c.vendor_code,
            c.title
        FROM sales_velocity v
        LEFT JOIN stock_totals st ON v.sku = st.sku
        LEFT JOIN product_cards c ON c.skus_json LIKE '%' || v.sku || '%'
        WHERE v.daily_rate > 0
          AND (COALESCE(st.total_stock, 0) / v.daily_rate) <= ?
        ORDER BY days_left ASC
        LIMIT 15
        """,
        (lookback_days, f"-{lookback_days} days", days_threshold),
    )
    if not rows:
        return f"Товаров с запасом менее {days_threshold} дн. (по темпу продаж за {lookback_days} дн.) не обнаружено."

    lines = [f"Прогноз дефицита (запас ≤ {days_threshold} дн., расчёт по заказам за {lookback_days} дн.):"]
    for r in rows:
        name = r["title"] or r["vendor_code"] or f"SKU {r['sku']}"
        lines.append(
            f"- {name}: остаток {r['total_stock']} шт. | темп {r['daily_rate']} шт./день → хватит на ~{r['days_left']} дн."
        )
    return "\n".join(lines)

class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request, call_next):
        if request.headers.get("Authorization") != f"Bearer {self.token}":
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


def create_app(domain: Optional[str] = None, token: Optional[str] = None):
    dom = domain or os.getenv("MCP_DOMAIN", "mcp.example.ru")
    tok = token or os.getenv("MCP_BEARER_TOKEN", "change-me-to-strong-secret")
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[dom, f"{dom}:*", "127.0.0.1:*", "localhost:*"],
    )
    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        transport_security=security,
    )
    app.add_middleware(BearerAuthMiddleware, token=tok)
    return app


def main():
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


#if __name__ == "__main__":
#    main()


def main():
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))
    uvicorn.run(create_app(), host=host, port=port)
