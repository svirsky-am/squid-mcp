3. Напишите тесты (In-Memory + реальный Streamable HTTP)

Создайте файл packages/wb-mcp-server/tests/test_server.py:
В файле тестов реализуются три сценария:
1. test_tool_in_memory — проверка работы инструмента get_example_page напрямую через Client(mcp) с замоканным транспортом httpx.MockTransport без запуска HTTP-сервера.
2. Фикстура live_mcp_server — динамически поднимает Uvicorn-сервер на свободном локальном порту с помощью сокетов и приложения из create_app().
3. test_streamable_http_unauthorized — проверка того, что запросы к Streamable HTTP без корректного Bearer-токена возвращают ошибку авторизации (MCPError).
4. test_streamable_http_authorized — проверка полного цикла работы по протоколу Streamable HTTP с использованием httpx2.AsyncClient, авторизационным токеном и замоканным ответом.