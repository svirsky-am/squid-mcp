from mcp.server.mcpserver import MCPServer

# Создаем экземпляр сервера
mcp = MCPServer("Demo Helper")

# 1. Инструмент (Tool) — модель сама решает, когда его вызвать
@mcp.tool()
def calculate_discount(price: float, discount_percent: float) -> str:
    """Рассчитывает итоговую цену товара с учетом скидки в процентах."""
    if not (0 <= discount_percent <= 100):
        raise ValueError("Скидка должна быть в диапазоне от 0 до 100")
    final_price = price * (1 - discount_percent / 100)
    return f"Итоговая цена: {final_price:.2f}"

# 2. Ресурс (Resource) — данные для чтения по URI
@mcp.resource("config://app-version")
def get_version() -> str:
    """Возвращает текущую версию внутреннего сервиса."""
    return "v2.4.1-production"

# 3. Промпт (Prompt) — готовый шаблон запроса для пользователя
@mcp.prompt()
def review_code_prompt(code: str) -> str:
    """Шаблон для ревью кода на уязвимости."""
    return f"Проверь этот Python-код на ошибки безопасности и утечки памяти:\n\n{code}"

if __name__ == "__main__":
    # По умолчанию запускается через транспорт stdio (для локальных клиентов)
    mcp.run()