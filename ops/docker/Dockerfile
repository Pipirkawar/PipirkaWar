# syntax=docker/dockerfile:1.7
# Multi-stage Dockerfile для production-сборки Pipirik Wars (Спринт 1.5.H).
#
# Stage 1 (builder) — собирает виртуальное окружение `/opt/venv` с runtime-
# зависимостями (без dev-extras).
# Stage 2 (runtime) — slim-образ с непривилегированным пользователем, только
# runtime-зависимости и код приложения. Healthcheck — через `python -c` импорт
# модуля настроек: если pydantic не валидирует env, контейнер сразу падает.
#
# Build:
#   docker build -f ops/docker/Dockerfile -t pipirik-wars:dev .
# Run (compose):
#   docker compose -f ops/docker/docker-compose.yml up
#
# Образ намеренно НЕ содержит alembic-миграции в виде отдельного шага: миграции
# гонит sidecar-контейнер `migrations` в docker-compose.yml перед стартом бота
# (сервис `bot` ждёт `migrations: condition: service_completed_successfully`).

ARG PYTHON_VERSION=3.12

# -----------------------------------------------------------------------------
# Builder: создаёт venv с runtime-зависимостями.
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /build

# Системные либы под asyncpg/cryptography. `build-essential` — на случай
# отсутствия prebuilt wheel для какой-то транзитивной зависимости.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv "$VIRTUAL_ENV"

# Сначала pyproject.toml + README + src — pip install -e . без dev-extras.
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip \
    && pip install --no-cache-dir .

# -----------------------------------------------------------------------------
# Runtime: slim-образ с только venv + код.
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src

# libpq5 — runtime для asyncpg. tini — корректный init для PID 1
# (форвардинг сигналов в asyncio long-polling).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libpq5 \
       tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 pipirik \
    && useradd -u 1000 -g pipirik -m -s /usr/sbin/nologin pipirik

WORKDIR /app

# Венв с runtime-зависимостями.
COPY --from=builder /opt/venv /opt/venv

# Код, конфиги и локали проекта.
COPY --chown=pipirik:pipirik src ./src
COPY --chown=pipirik:pipirik config ./config
COPY --chown=pipirik:pipirik locales ./locales
COPY --chown=pipirik:pipirik alembic.ini ./alembic.ini

USER pipirik

# Healthcheck: импорт `Settings()` валидирует env (BOT_TOKEN, DATABASE_URL).
# Не лезет в Telegram / БД — дёшево и не зависит от внешних сервисов.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from pipirik_wars.infrastructure.settings import Settings; Settings()" || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "pipirik_wars.bot.main"]
