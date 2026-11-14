# Установка и активация venv/uv
setup:
	python3 -m venv .venv
	. .venv/bin/activate
	pip install uv
	uv sync

# Запуск клиента (службы)
run-client:
    set -a; . .staff/env; set +a; uv run python -m src.msp_client

# Запуск генерации отчета (вне службы)
run-report:
	set -a; . .staff/env; set +a; \
	uv run python src/report_generator.py

# Запуск тестов
test:
	uv run pytest tests/