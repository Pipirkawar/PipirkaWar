# 🍆 Пипирик Варс

Telegram-бот PvP/PvE-игры с прокачкой «пипирика», походами, караванами, рейдами и кланами. Построен по принципам clean architecture / SOLID, security-first, локализован на **RU + EN** (Mozilla Fluent), полностью покрыт типами (`mypy --strict`) и тестами (≥ 80 %, фактически ~97 %).

> **MVP-релиз** закрывает Спринт 1.5 (`docs/development_plan.md` §3). Definition of Done MVP — см. [`docs/dod_mvp.md`](docs/dod_mvp.md).

## 📚 Документация

- [`docs/pipirik_wars_plan.md`](docs/pipirik_wars_plan.md) — Игровой Дизайн-Документ (ГДД).
- [`docs/development_plan.md`](docs/development_plan.md) — Подробный план разработки по фазам и спринтам.
- [`docs/current_tasks.md`](docs/current_tasks.md) — Текущие задачи (актуальный спринт).
- [`docs/history.md`](docs/history.md) — Хронологический журнал выполненных работ.
- [`docs/dod_mvp.md`](docs/dod_mvp.md) — Definition of Done для MVP-релиза.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — правила разработки, чек-листы PR, security-чек-лист.
- [`ops/runbooks/deploy_vps.md`](ops/runbooks/deploy_vps.md) — деплой на VPS 1 GB + Neon free.

> ⚠ **Перед началом любой работы** — прочитать §0 ГДД («Политика разработки»: SOLID/ООП/безопасность). Эти требования обязательны.

## 🚀 Быстрый старт (локально, через Docker)

Самый быстрый путь поднять бота локально — **docker compose**. Цель — запуск за < 5 минут.

```bash
# 1. Получить токен у @BotFather в Telegram (BOT_TOKEN).
# 2. Узнать свой Telegram tg_id (например, через @userinfobot).
# 3. Подготовить .env:
cp .env.example .env
# Открыть .env и проставить:
#   BOT_TOKEN=123456:ABC...                 # из @BotFather
#   BOOTSTRAP_ADMIN_IDS=123456789           # ваш tg_id (можно несколько через запятую)

# 4. Запустить compose-стек (Postgres + миграции + бот):
docker compose -f ops/docker/docker-compose.yml up --build

# В логах:
#   pipirik-postgres      | database system is ready to accept connections
#   pipirik-migrations    | alembic INFO Running upgrade -> 0006_users_locale_override
#   pipirik-bot           | INFO     aiogram.dispatcher ... Run polling for bot @YourBotUsername
```

Бот отвечает на `/start` в Telegram. Для остановки — `Ctrl+C`, для полной очистки (включая БД) — `docker compose -f ops/docker/docker-compose.yml down -v`.

### Что делает compose-стек

| Сервис | Что | Зачем |
|---|---|---|
| `postgres` | Postgres 16-alpine с локальным volume `pipirik_pg_data` | БД для разработки. В production — внешний managed Postgres (Neon free). |
| `migrations` | Одноразовый sidecar: `alembic upgrade head` | Гонит миграции **до** старта бота. Бот ждёт через `service_completed_successfully`. |
| `bot` | Long-polling Telegram-бот | Зависит от `postgres: service_healthy` + `migrations: service_completed_successfully`. |

## 🛠 Локальная разработка (без Docker)

Если хочется пушить код / гонять тесты без оверхеда контейнеров:

```bash
# 1. Python 3.11 или 3.12 (project requires-python = ">=3.11").
python3.12 --version   # 3.12.x

# 2. Создать venv и поставить dev-зависимости.
python3.12 -m venv .venv
source .venv/bin/activate         # (Linux/macOS)  или  .venv\Scripts\activate  (Windows)
pip install -e ".[dev]"
pre-commit install

# 3. Поднять локальную Postgres (вариант 1 — Docker):
docker run -d --name pipirik-pg \
    -e POSTGRES_USER=pipirik -e POSTGRES_PASSWORD=pipirik_dev_password -e POSTGRES_DB=pipirik \
    -p 5432:5432 postgres:16-alpine

# 4. Подготовить .env (как в Docker-варианте, но DATABASE_URL смотрит на localhost):
cp .env.example .env
# В .env:
#   DATABASE_URL=postgresql+asyncpg://pipirik:pipirik_dev_password@localhost:5432/pipirik

# 5. Накатить миграции и запустить бота:
alembic upgrade head
python -m pipirik_wars.bot.main
```

### Полезные команды (см. также `Makefile`)

| Команда | Что делает |
|---|---|
| `make lint` | `ruff check .` |
| `make format` | `ruff format .` |
| `make typecheck` | `mypy --strict` (370+ файлов, **0 issues**) |
| `make imports` | `import-linter` — контракт слоёв clean architecture |
| `make test` | `pytest` + coverage (`--cov-fail-under=80`) |
| `make ci` | lint + typecheck + imports + test (то, что гоняется в CI) |
| `make audit` | `pip-audit` (CVE-проверка) — отдельной job-ой в CI |
| `pre-commit run --all-files` | Все pre-commit хуки (ruff, mypy, import-linter) |

### Прогон тестов

```bash
# Все тесты (~1100 кейсов, < 1 минуты):
pytest

# Только unit-тесты домена:
pytest tests/unit/domain/ --no-cov

# Конкретный файл:
pytest tests/unit/application/forest/test_start_run.py -q
```

## 🧱 Архитектура

Проект построен по принципам **clean architecture**:

```
domain/         ← чистая бизнес-логика (зависит только от себя)
   ↑
application/    ← use-cases (оркестрация домена)
   ↑
infrastructure/ ← реализации портов (PG, APScheduler, Telegram, локализация)
   ↑
bot/            ← тонкий aiogram-слой (handlers + presenters + middlewares)
```

Зависимости направлены строго **внутрь**. Импорт `domain → infrastructure` блокируется CI (`import-linter`, контракты `layered_architecture` / `domain_must_not_import_infrastructure` / `application_must_not_import_io_libs`).

См. [`docs/development_plan.md`](docs/development_plan.md) §2 для полной структуры.

## 📂 Структура репозитория

```
.
├── docs/                  # документация (ГДД, план, история, задачи, DoD MVP)
├── src/pipirik_wars/      # код проекта
│   ├── domain/            # чистый домен (player, clan, forest, oracle, …)
│   ├── application/       # use-cases (StartForestRun, RegisterPlayer, …)
│   ├── infrastructure/    # PG, Alembic, APScheduler, Telegram, i18n, шаблоны
│   ├── bot/               # aiogram (handlers, presenters, middlewares)
│   └── shared/            # logger, errors, общие утилиты
├── tests/                 # unit / integration / load
│   ├── unit/              # быстрые, in-memory (FakeUnitOfWork, FakeRandom, …)
│   ├── integration/       # БД + миграции (через aiosqlite в CI)
│   └── load/              # параллельные сценарии (например, 100 одновременных /forest)
├── config/                # balance.yaml + JSON-каталоги шаблонов (oracle, forest)
├── locales/               # ru.ftl + en.ftl (Mozilla Fluent)
├── ops/                   # docker, deploy-runbooks, инцидент-runbook-и
└── .github/workflows/     # CI (lint + types + tests на 3.11/3.12 + pip-audit)
```

## 🌍 Локализация

Бот поддерживает **RU и EN** через [Mozilla Fluent](https://projectfluent.org/) (`locales/{ru,en}.ftl`). Локаль резолвится в три уровня:

1. `users.locale_override` — если игрок выставил `/lang ru` или `/lang en`.
2. `Telegram.User.language_code` — если override не задан.
3. `DEFAULT_LOCALE = "ru"` — fallback.

Команды бота (`/start`, `/profile`, `/forest`, `/oracle`, `/upgrade`, `/top`, `/lang`) полностью локализованы.

## 🔐 Политика разработки (кратко)

- **SOLID/ООП** — обязательно. Каждый PR проходит чек-лист в [`CONTRIBUTING.md`](CONTRIBUTING.md).
- **Безопасность и целостность данных** — приоритет №1. Транзакции через `IUnitOfWork`, idempotency через `IIdempotencyService`, audit log на каждое изменение, RBAC через middleware.
- **Тесты** — покрытие `domain/` + `application/` + критическая инфра ≥ 80 % (фактически ~97 %).
- **CI gates**: `ruff`, `mypy --strict`, `import-linter`, `pytest`, `pip-audit` (отдельной job-ой). Все обязательны.
- **Никаких прямых пушей в `main`** — только через PR с code review.

Полный текст — в [`docs/pipirik_wars_plan.md`](docs/pipirik_wars_plan.md) §0 + [`CONTRIBUTING.md`](CONTRIBUTING.md).

## 🚢 Деплой на production

См. [`ops/runbooks/deploy_vps.md`](ops/runbooks/deploy_vps.md). Кратко: VPS 1 GB RAM + Neon free Postgres — это достаточный baseline для MVP (закрытый альфа-тест). Бот гоняется через `docker compose` в **production-режиме** (без локального `postgres`-сервиса; `DATABASE_URL` смотрит на Neon).

## 🤝 Как участвовать

1. Прочитать ГДД §0 и [`CONTRIBUTING.md`](CONTRIBUTING.md).
2. Взять задачу из [`docs/current_tasks.md`](docs/current_tasks.md).
3. Завести feature-branch (`devin/<timestamp>-<slug>` или подобный формат).
4. Реализовать с тестами, пройти SOLID + security чек-лист.
5. Открыть PR. Дождаться CI и ревью.
6. После мержа — записать выполненное в [`docs/history.md`](docs/history.md), убрать строку из [`docs/current_tasks.md`](docs/current_tasks.md) (или поменять статус на ✅ смержено).

## 📜 Лицензия

Proprietary. См. [`pyproject.toml`](pyproject.toml).
