import httpx
from mcp.server.mcpserver import MCPServer

# В mcp 2.x вместо FastMCP используется MCPServer
mcp = MCPServer("wb-example-server")


@mcp.tool()
async def get_example_page(url: str = "https://example.com") -> str:
    """Загружает HTML-страницу по указанному URL (по умолчанию example.com)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text[:500]


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()