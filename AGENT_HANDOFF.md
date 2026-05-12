# AGENT HANDOFF — Спринт 4.1-G (шаг G.4/G.8)

> **Sticky-режим.** Этот файл обновляется в КАЖДОМ коммите этой фичевой ветки до открытия PR-а. Удаляется отдельным коммитом перед `git_pr(action="create")`. См. CONTRIBUTING.md «Уходящий агент».

## Контекст

- **Спринт:** 4.1 «Монетизация и масштаб», Фаза 4. Активный PR — **4.1-G «Redis-инфра + ActivityLocks-миграция»**.
- **Задача из development_plan.md §7:** 4.1.12 «Переход на Redis (лобби, очереди, DAU, locks). Нагрузочный тест 10× от MVP.»
- **Декомпозиция 4.1.12 на 4 PR (принята в этой сессии):**
  - **4.1-G (этот PR)** — Redis-инфра + ActivityLocks-миграция.
  - **4.1-H (следующий)** — Lobby-миграция через Redis LIST + Lua-atomic.
  - **4.1-I (после H)** — DAU-миграция (sorted-set per day + JOIN с SQL по `clan_members`/`users`).
  - **4.1-J (закрывает 4.1.12)** — Load-test 10× от MVP + Prometheus-метрики Redis-операций.
- **Ветка:** `devin/1778606701-sprint-4-1-G-redis-migration` от `main = 555a5c50` (merge PR #134 «4.1-F Real TonConnectVerifier»).
- **Сессия:** https://app.devin.ai/sessions/9914ce0dc9c84129bd472bda22bc0f2c (вторая сессия в этой ветке; предыдущая — `5255f0193842...`).

## Текущая позиция

**G.4 завершён, G.5 готов к началу.** Сделано на ветке:

- **G.0** (`654fbab`) — pivot `current_tasks.md` под 4.1-G + sticky `AGENT_HANDOFF.md`. Baseline `make ci` зелён.
- **G.1** (`d35810f`) — `pyproject.toml`: `redis>=5,<7` в `dependencies` (резолвится в `redis-6.4.0`) + `fakeredis>=2.21,<3` в `[project.optional-dependencies].dev` (`fakeredis-2.35.1`). `pip install -e ".[dev]"` прошёл. `pip-audit` — `No known vulnerabilities found`. Smoke-проверка `fakeredis.aioredis.FakeRedis` подтверждает `SET NX PX` атомарность.
- **G.2** (`b13e014`) — `infrastructure/redis/` модуль: `RedisSettings` (env-prefix `BOT_REDIS_`) + `build_redis_client(settings) -> redis.asyncio.Redis` (явный `ConnectionPool.from_url(...)`) + `Settings.redis: RedisSettings`. +11 unit-тестов. `redis>=5,<7` добавлен в `additional_dependencies` mypy-хука `.pre-commit-config.yaml`.
- **G.3** (`292b962`) — `RedisActivityLockRepository(IActivityLockRepository)`:
  - File: `src/pipirik_wars/infrastructure/redis/repositories/activity_lock.py` (+`__init__.py`).
  - `try_acquire` — атомарный `SET key value NX PX ttl_ms` (NX + PX-millis). `ttl_ms <= 0` ⇒ fail-safe `False` без обращения к Redis.
  - `release` — `DEL key`. NO-OP если key нет.
  - `get` — `GET` + `PTTL` в одном MULTI/EXEC-pipeline (atomic, исключает TOCTOU между двумя командами). Восстанавливает `ActivityLock` из JSON-payload-а; `expires_at = clock.now() + PTTL`. `PTTL=-2` (key expired) или `-1` (no TTL) → `None`.
  - Key-format: `lock:{actor_kind}:{actor_id}`. Конструктор принимает кастомный `key_prefix` (default `"lock"`); namespace для будущих 4.1-H/I.
  - Value-format: JSON `{"reason": LockReason.value, "acquired_at": ISO-8601}`. JSON ради human-readability в `redis-cli`.
  - +13 unit-тестов через `fakeredis.aioredis.FakeRedis`: happy `try_acquire`/`release`/`get`, NX-conflict, re-acquire после release, fail-safe на `expires_at <= now`, разные акторы не конфликтуют, key-format & TTL sanity, release-noop, get на отсутствующий key, get reconstruction (reason + acquired_at + expires_at), get → None после expire, get с advance-нутым clock, custom `key_prefix`.
- **G.4** (этот коммит) — Config-flag + composition-root switch:
  - `BotSettings.activity_lock_backend: Literal["sql","redis"] = "sql"` (`infrastructure/settings/settings.py`); env-флаг автоматически `BOT_ACTIVITY_LOCK_BACKEND` (`BotSettings.env_prefix="BOT_"`). Default `sql` — backward-compat на momentum мерджа 4.1-G.
  - `bot/main.py::build_container` switch: `redis` → `build_redis_client(settings.redis)` + `RedisActivityLockRepository(client=..., clock=clock)`; `sql` (default) → текущий `SqlAlchemyActivityLockRepository(uow=uow)`. `build_redis_client` ленивый — реальное TCP-подключение произойдёт только при первой команде (`SET`/`DEL`/...). По аналогии с 4.1-F-switch-ем `BOT_TON_CONNECT_VERIFIER_MODE`.
  - +2 composition-root-теста в `tests/unit/bot/test_composition_root.py::TestBuildContainer`: default `sql` → `SqlAlchemyActivityLockRepository`, `activity_lock_backend="redis"` → `RedisActivityLockRepository`.

Сделано ранее в текущей сессии:

1. `git fetch origin --prune` → подтверждён `main = 555a5c5` (merge PR #134) и активная ветка `devin/1778606701-sprint-4-1-G-redis-migration` от `main`.
2. Прочитаны: CONTRIBUTING.md «Промпт-приёмка», development_plan.md §7 4.1.12, current_tasks.md, history.md (последние записи 4.1-F).
3. Baseline `make ci` зелён на `d35810f`: **6876 passed + 2 skipped + 95.49% cov** (ruff + mypy --strict 1052 файла + import-linter 562 файла 4/4 contracts + pytest).
4. `pre-commit install` выполнен.

## Следующие шаги (G.5–G.8)
- **G.5** — integration-тесты `tests/integration/redis/test_activity_lock_redis.py` через `fakeredis.aioredis.FakeRedis`: happy try_acquire/release/re-acquire, race-condition двух одновременных try_acquire (asyncio.gather), expired-cleanup.
- **G.6** — `make ci` локально зелён.
- **G.7** — doc-sync: `docs/history.md` +1 запись «Спринт 4.1-G» сверху, `current_tasks.md` снимок под `main = <будущий-merge-sha>`, чек-лист передвинуть на 4.1-H (Lobby-миграция).
- **G.8** — `git rm AGENT_HANDOFF.md` + commit + `git_pr(action="create")` + `git(action="pr_checks")` до зелёного CI.

## Команды

```
. .venv/bin/activate
make ci                  # lint + typecheck + imports + tests
make lint                # ruff
make typecheck           # mypy --strict
make imports             # lint-imports
make test                # pytest + coverage gate 80%
pre-commit run --all-files
```

## Открытые решения для следующих шагов

- **Key-format Redis:** выбран `lock:{actor_kind}:{actor_id}` (плоский namespace). Альтернатива — `pipirik:lock:{actor_kind}:{actor_id}` (если в будущем будет shared Redis с другими сервисами). Решение принять в G.3 при имплементации.
- **Value-format:** JSON `{"reason": str, "acquired_at": ISO}` чтобы `get(...)` мог восстановить `ActivityLock`-domain-VO.
- **`expires_at`-восстановление в `get(...)`:** Redis `PTTL` возвращает ms-до-истечения; `expires_at = now + pttl_ms/1000`. Если key уже истёк — `PTTL=-2` → `None`. Domain `ActivityLock` требует `expires_at: datetime` — нужен `clock: IClock` инъецированный в репозиторий.
- **Connection lifecycle:** `redis.asyncio.Redis` — long-lived singleton с pool-ом; `build_redis_client` возвращает один Redis-client, container хранит его. На shutdown — `await client.aclose()` (пока не добавляется в graceful-shutdown bot-а; runtime-leak небольшой).
