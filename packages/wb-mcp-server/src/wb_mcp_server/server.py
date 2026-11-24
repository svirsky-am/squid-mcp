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
    """Возвращает сводку по заказам FBS и выручке за последние N дней."""
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
    return "\n".join(lines)


@mcp.tool()
def get_top_articles(days: int = 30, limit: int = 5) -> str:
    """Возвращает топ артикулов продавца по выручке без учёта отменённых заказов."""
    rows = _query_db(
        """
        SELECT
            COALESCE(article, 'без артикула') AS article,
            nm_id,
            COUNT(*) AS cnt,
            ROUND(SUM(COALESCE(converted_price, price, 0)) / 100.0, 2) AS total_rub
        FROM fbs_orders
        WHERE created_at >= datetime('now', ?)
          AND COALESCE(supplier_status, '') != 'cancel'
          AND COALESCE(wb_status, '') NOT IN ('canceled', 'canceled_by_client', 'declined_by_client')
        GROUP BY article, nm_id
        ORDER BY total_rub DESC
        LIMIT ?
        """,
        (f"-{days} days", limit),
    )
    if not rows:
        return f"Нет активных заказов за последние {days} дн."

    lines = [f"Топ-{limit} артикулов по выручке за {days} дн.:"]
    for idx, r in enumerate(rows, start=1):
        lines.append(f"{idx}. {r['article']} (nmId: {r['nm_id']}) — {r['cnt']} шт., {r['total_rub']} ₽")
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


if __name__ == "__main__":
    main()