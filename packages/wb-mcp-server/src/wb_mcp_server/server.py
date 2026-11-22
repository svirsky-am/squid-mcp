import os
import httpx
import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

mcp = MCPServer("wb-alice-server")


@mcp.tool()
async def get_example_page(url: str = "https://example.com") -> str:
    """Загружает текстовое содержимое страницы по URL."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text[:500]


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request, call_next):
        if request.headers.get("Authorization") != f"Bearer {self.token}":
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


def create_app(domain: str = "mcp.example.ru", token: str = "test-secret"):
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[domain, f"{domain}:*", "127.0.0.1:*", "localhost:*"],
    )
    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        transport_security=security,
    )
    app.add_middleware(BearerAuthMiddleware, token=token)
    return app


def main():
    domain = os.environ.get("MCP_DOMAIN", "mcp.example.ru")
    token = os.environ.get("MCP_BEARER_TOKEN", "change-me-to-strong-secret")
    uvicorn.run(create_app(domain=domain, token=token), host="127.0.0.1", port=8000)