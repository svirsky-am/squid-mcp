FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Сначала копируем файлы зависимостей для кэширования слоёв Docker
COPY pyproject.toml uv.lock ./
COPY packages/wb-mcp-client/pyproject.toml packages/wb-mcp-client/pyproject.toml
COPY packages/wb-mcp-server/pyproject.toml packages/wb-mcp-server/pyproject.toml

RUN uv sync --frozen --all-packages --no-install-project --no-install-workspace

# Копируем исходный код и устанавливаем пакеты workspace
COPY packages packages
RUN uv sync --frozen --all-packages
