# AGENT HANDOFF — Спринт 4.1-G (шаг G.0/G.8)

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
- **Сессия:** https://app.devin.ai/sessions/5255f01938424f58bcb1b5806e70a1ca.

## Текущая позиция

**G.1 в работе.** Сделано на ветке:

- **G.0** (`654fbab`) — pivot `current_tasks.md` под 4.1-G + sticky `AGENT_HANDOFF.md`. Baseline `make ci` зелён.
- **G.1** (этот коммит) — `pyproject.toml`: `redis>=5,<7` в `dependencies` (резолвится в `redis-6.4.0`) + `fakeredis>=2.21,<3` в `[project.optional-dependencies].dev` (`fakeredis-2.35.1`). `pip install -e ".[dev]"` прошёл. `pip-audit` — `No known vulnerabilities found` для всех пакетов. Smoke-проверка `fakeredis.aioredis.FakeRedis` подтверждает: `SET NX PX` атомарен (первый ОК → True, второй на занятом ключе → None), `PTTL` возвращает оставшийся TTL в ms, `DEL` сбрасывает ключ. Это всё, что нужно для `RedisActivityLockRepository`.

Сделано ранее:

1. `git fetch origin --prune` → `main = 555a5c50` (merge #134) → создана ветка `devin/1778606701-sprint-4-1-G-redis-migration` от свежего main.
2. Прочитаны: CONTRIBUTING.md «Уходящий агент» + «Промпт-приёмка», development_plan.md §7 4.1.12, current_tasks.md.
3. Изучено текущее состояние 3 SQL-репозиториев на миграцию:
   - `SqlAlchemyActivityLockRepository` (`src/.../infrastructure/db/repositories/activity_lock.py`, 112 строк): try_acquire/release/get; перезахват истёкших блоков; INSERT ... ON CONFLICT (PG) / INSERT OR IGNORE (SQLite).
   - `SqlAlchemyGlobalLobbyRepository` (85 строк): FIFO PvP, `SELECT FOR UPDATE SKIP LOCKED` на PG.
   - `SqlAlchemyDailyActivityRepository` (122 строки): DAU + `list_active_member_ids` JOIN-ом с `clan_members`/`users`.
4. Baseline `make ci` зелён на свежем main: **6876 passed + 2 skipped + 95.50% cov** (`ruff` + `mypy --strict` 1052 файла + `lint-imports` 562 файла 4/4 contracts + `pytest`).
5. `docs/current_tasks.md` перестроен под 4.1-G: новый чек-лист G.0–G.8, snapshot обновлён («Активный PR — 4.1-G»), 4.1-F-чек-лист помечен как `[АРХИВ]`, 4.1.13–4.1.15 переадресованы на 4.1-K (после миграции).

## Следующие шаги (G.2–G.8)
- **G.2** — `RedisSettings` (env-prefix `BOT_REDIS_`) в новом каталоге `src/pipirik_wars/infrastructure/redis/` (модуль не сущ.): `url`, `pool_max_connections`, `connect_timeout_seconds`, `socket_timeout_seconds`, `socket_keepalive`. `build_redis_client(settings) -> redis.asyncio.Redis` с явным connection-pool-ом. Добавить `Settings.redis: RedisSettings = Field(default_factory=...)` в `bot/main.py` или `bot/config.py` (там же, где другие Settings).
- **G.3** — `RedisActivityLockRepository(IActivityLockRepository)` в `src/.../infrastructure/redis/repositories/activity_lock.py`: key `lock:{actor_kind}:{actor_id}`, value `json.dumps({"reason": reason.value, "acquired_at": now.isoformat()})`, atomic `SET key value NX PX ttl_ms`. unit-тесты через `fakeredis.aioredis.FakeRedis`.
- **G.4** — config-flag `Settings.activity_lock_backend: Literal["sql","redis"] = "sql"` (env `BOT_ACTIVITY_LOCK_BACKEND`); в `bot/main.py::build_container` switch: `redis` → `build_redis_client(...)` + `RedisActivityLockRepository`; `sql` (default) → текущий `SqlAlchemyActivityLockRepository`. По аналогии с `BOT_TON_CONNECT_VERIFIER_MODE` из 4.1-F (см. F.7).
- **G.5** — integration-тесты `tests/integration/redis/test_activity_lock_redis.py` через `fakeredis.aioredis.FakeRedis` (или подключение к реальному Redis, если есть в CI — но проще fakeredis): happy try_acquire/release/re-acquire, race-condition двух одновременных try_acquire (asyncio.gather), expired-cleanup (manual clock advance).
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

- **Key-format Redis:** предложение `lock:{actor_kind}:{actor_id}` (плоский namespace). Альтернатива — `pipirik:lock:{actor_kind}:{actor_id}` (если в будущем будет shared Redis с другими сервисами).
- **Value-format:** JSON `{"reason": str, "acquired_at": ISO}` чтобы `get(...)` мог восстановить `ActivityLock`-domain-VO. Альтернатива — Redis HSET (отдельные fields), но усложняет atomic-acquire.
- **`expires_at`-восстановление в `get(...)`:** Redis `PTTL` возвращает ms-до-истечения; `expires_at = now + pttl_ms/ms`. Если key уже истёк — `PTTL=-2` → `None`. Domain `ActivityLock` требует `expires_at: datetime` — нужен `clock: IClock` инъецированный в репозиторий.
- **Connection lifecycle:** `redis.asyncio.Redis` — это short-lived объект или long-lived? По best-practice — long-lived с pool-ом; build_redis_client возвращает singleton, container хранит его. На shutdown — `await client.aclose()` (нужно ли добавлять в graceful-shutdown bot-а? — пока нет, runtime-leak небольшой).
