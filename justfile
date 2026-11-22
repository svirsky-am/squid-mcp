run-module:
    uv run --package wb-mcp-client --active wb-mcp-client 


run-clietn-test:
    uv run --package wb-mcp-client pytest

install-all-packages:
    uv sync --all-packages



run-client:
    uv run --package wb-mcp-client python packages/wb-mcp-client/src/wb_mcp_client/client.py   \


run-mcp-server:
    uv run --package wb-mcp-server wb-mcp-server