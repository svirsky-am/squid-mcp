import httpx


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