# Рецепты WB reporter. Переменные окружения — в .staff/env

set shell := ["bash", "-uc"]

default: test

# --- установка: venv + uv ---
venv:
    @[ -d .venv ] || python3 -m venv .venv
    @. .venv/bin/activate && pip install --upgrade pip && pip install uv

install: venv
    @. .venv/bin/activate && uv sync --all-extras

# --- тесты ---
test: install
    @. .venv/bin/activate && uv run pytest -q

test-cov: install
    @. .venv/bin/activate && uv run pytest --cov=src --cov-report=term-missing

# --- служба / разовые команды ---
run-client: install
    set -a; . .staff/env; set +a; echo "${API_TOKEN_IS_IMPORTED}"; \
    . .venv/bin/activate && uv run python -m wb_reporter.cli run

sync: install
    set -a; . .staff/env; set +a; \
    . .venv/bin/activate && uv run python -m wb_reporter.cli sync

report date_from="2026-10-01" date_to="2026-10-31" out="wb_registry.xlsx": install
    set -a; . .staff/env; set +a; \
    . .venv/bin/activate && uv run python -m wb_reporter.cli report \
        --from {{date_from}} --to {{date_to}} --out {{out}}

mcp: install
    set -a; . .staff/env; set +a; \
    . .venv/bin/activate && MCP_TRANSPORT=streamable-http uv run python -m wb_reporter.mcp_server

# --- systemd ---
service-install service_dir="/opt/wb-reporter":
    sudo cp deploy/wb-reporter.service /etc/systemd/system/
    sudo sed -i "s|WORK_DIR_PLACEHOLDER|$(pwd)|" /etc/systemd/system/wb-reporter.service
    sudo systemctl daemon-reload
    sudo systemctl enable --now wb-reporter
