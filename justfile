# Установка и активация venv/uv
setup:
    python3 -m venv .venv
    . .venv/bin/activate && pip install uv
    . .venv/bin/activate && uv pip install -e ".[dev]"

# Запуск тестов
test:
    set -a; . .staff/env; set +a; \
    . .venv/bin/activate && pytest -v

# Запуск сервиса (демона)
run-client:
    set -a; . .staff/env; set +a; echo "API_TOKEN_IS_IMPORTED: ${API_TOKEN:+yes}"; \
    . .venv/bin/activate && python3 src/service.py

# Генерация отчета вне сервиса (по данным из БД)
generate-report:
    set -a; . .staff/env; set +a; \
    . .venv/bin/activate && python3 src/report_generator.py