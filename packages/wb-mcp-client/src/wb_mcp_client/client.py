import httpx

import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def fetch_example_page(url: str = "https://example.com") -> str:
    """Выполняет GET-запрос и возвращает HTML-текст страницы."""
    response = httpx.get(url, timeout=10.0)
    response.raise_for_status()
    return response.text

async def fetch_example_page(url: str = "https://example.com") -> str:
    """Асинхронно выполняет GET-запрос и возвращает текст ответа."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text

async def call_mcp_example_tool() -> str:
    # Настраиваем запуск локального MCP-сервера из нашего workspace
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "--package", "wb-mcp-server", "wb-mcp-server"],
    )

    # Устанавливаем соединение по stdio
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Инициализируем MCP-сессию
            await session.initialize()

            # (Опционально) можно посмотреть список доступных инструментов
            # tools = await session.list_tools()

            # Вызываем инструмент get_example_page на сервере
            result = await session.call_tool(
                "get_example_page",
                arguments={"url": "https://example.com"},
            )
            return result.content[0].text


if __name__ == "__main__":
    output = asyncio.run(call_mcp_example_tool())
    print("Ответ от MCP-сервера:\n", output)