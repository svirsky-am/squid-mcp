run-module:
    uv run --package wb-mcp-client --active wb-mcp-client 


run-clietn-test:
    uv run --package wb-mcp-client pytest

install-all-packages:
    uv sync --all-packages

run-collector:
    uv run --no-sync --package wb-mcp-client wb-collector


run-mcp-server:
    uv run --package wb-mcp-server wb-mcp-server


gen-report:
    uv run --package wb-mcp-client wb-report

test-get-cards-list:
    uv run --package wb-mcp-client pytest -k test_real_wb_cards_fetch -v
    uv run --package wb-mcp-client wb-sync-cards


test-real-connection:
    RUN_REAL_WB_TESTS=1 uv run pytest -k test_real_wb_cards_fetch -v

check-open-8000-port:
    lsof -i :8000
#ss -tlnp | grep :8000