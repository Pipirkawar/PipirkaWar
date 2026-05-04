# Sprint 1.3.B — handoff (WIP)

Ветка: `devin/1777920275-sprint-1-3b-forest-persistence`.
Базис: `main` после мерджа PR #17 (1.3.A).

## Что уже сделано в этом коммите (production-код)

- **Domain:**
  - `domain/forest/run.py` — `ForestRun` (frozen dataclass, slots) + `ForestRunStatus` (`IN_PROGRESS`/`FINISHED`).
    - `ForestRun.starting(player_id, outcome, started_at, ends_at)` — фабрика свежей записи.
    - `mark_finished(finished_at)` — идемпотентный перевод в `FINISHED`.
  - `domain/forest/repositories.py` — `IForestRunRepository` (`add` / `get_active_by_player` / `save`).
  - `domain/forest/errors.py` — добавлен `AlreadyInForestError(player_id)` (наследник `ForestError`).
  - `domain/forest/__init__.py` — реэкспортирует новые символы.
  - `domain/player/errors.py` + `__init__.py` — добавлен `PlayerNotFoundError(tg_id)`.
  - `domain/shared/ports/audit.py` — добавлен `AuditAction.FOREST_RUN_STARTED`.

- **Migrations:**
  - `infrastructure/db/migrations/versions/20260504_0004_forest_runs.py` — таблица `forest_runs`:
    - PK `id`, FK `player_id → users.id` (CASCADE).
    - Колонки: `status`, `started_at`, `ends_at`, `branch_name`, `length_delta_cm`, `drop_kind`, `drop_item_id`, `drop_name`, `finished_at`.
    - CHECK-инварианты: status ∈ enum, drop_kind ∈ enum, payload совместим с drop_kind, `IN_PROGRESS ⇔ finished_at IS NULL`, `ends_at > started_at`, `length_delta_cm >= 0`.
    - Индексы: `ix_forest_runs_player_id_status`, `ix_forest_runs_status_ends_at`, **partial unique** `uq_forest_runs_one_active_per_player` (на SQLite/Postgres через `sqlite_where=` / `postgresql_where=`).

- **ORM:**
  - `infrastructure/db/models/forest.py` — `ForestRunORM` (Mapped + `__table_args__` с теми же CHECK-инвариантами и индексами, что и в миграции).
  - `infrastructure/db/models/__init__.py` — `ForestRunORM` экспортирован.

- **Repositories:**
  - `infrastructure/db/repositories/forest_run.py` — `SqlAlchemyForestRunRepository`:
    - DI: `uow: SqlAlchemyUnitOfWork`, `balance: IBalanceConfig` (нужен для восстановления `Item` из `drop_item_id` при `_row_to_entity`).
    - Сериализация `Drop` → 3 колонки через `_drop_to_columns`.
    - Десериализация → `Item` лукапится в `balance.get().items_catalog`. Если каталог админ почистил между стартом и финишем — `IntegrityError`, и `FinishForestRun` (1.3.C) сможет это осознанно обработать.
    - Реализованы `add` / `get_active_by_player` / `save` (последний — для будущего `FinishForestRun`).
    - SQL `IntegrityError` мапится в доменный `IntegrityError`.
  - `infrastructure/db/repositories/__init__.py` — `SqlAlchemyForestRunRepository` экспортирован.

- **Application:**
  - `application/dto/inputs.py` — добавлен `StartForestRunInput(tg_id)`.
  - `application/forest/__init__.py` + `start_run.py` — use-case `StartForestRun`:
    - DI: `uow, players, runs, locks (ActivityLockService), balance, random, audit, clock`.
    - Шаги внутри `async with self._uow`:
      1. `players.get_by_tg_id(tg_id)` → `PlayerNotFoundError`, если нет.
      2. `cooldown_minutes = random.randint(forest.cooldown_min_minutes, forest.cooldown_max_minutes)`.
      3. `locks.acquire(actor_kind="player", actor_id=player.id, reason=LockReason.FOREST, ttl=cooldown)` → `LockAlreadyHeldError → AlreadyInForestError`.
      4. `outcome = compute_forest_outcome(balance=cfg, random=random)` (исход ролится **на старте**, не на финише).
      5. `runs.add(ForestRun.starting(...))`.
      6. `audit.record(AuditAction.FOREST_RUN_STARTED, ...)` с `idempotency_key=f"forest_run_started:{run.id}"`.
    - Возврат `ForestRunStarted(run, cooldown_minutes)`.

## Локальные проверки (зелёные на этом коммите)

- `make lint` — All checks passed.
- `make typecheck` — Success: no issues found in 258 source files.
- `make imports` — Contracts: 3 kept, 0 broken (layered, domain-purity, application-purity).

## Что осталось доделать (TODO для следующего воркера)

1. **Юнит-тесты `application/forest/StartForestRun`** (`tests/unit/application/forest/test_start_run.py`):
   - happy path: успешный старт ролит cooldown ∈ [10, 20], создаёт `ForestRun` со `status=IN_PROGRESS`, пишет audit `FOREST_RUN_STARTED`, возвращает `ForestRunStarted` с правильным `cooldown_minutes` и `run.ends_at = started_at + cooldown`.
   - `AlreadyInForestError` если `LockAlreadyHeldError` (повторный `/forest`).
   - `PlayerNotFoundError` если игрока нет.
   - Outcome вычисляется через `compute_forest_outcome` — детерминированно при фиксированном `FakeRandom(seed=...)`.
   - Audit-запись содержит `before=None`, `after={player_id, branch_name, length_delta_cm, drop_kind, cooldown_minutes, ends_at}`.
   - При ошибке внутри UoW — rollback (counts через `FakeUnitOfWork.rollbacks`).

2. **Юнит-тесты `domain/forest/run.py`** (`tests/unit/domain/forest/test_run.py`):
   - `ForestRun.starting(...)` корректно проставляет статус и outcome.
   - `ends_at <= started_at` → `ValueError`.
   - `mark_finished` идемпотентен (повторный вызов — no-op).

3. **Fake-репозиторий `tests/fakes/forest_run_repo.py`** + регистрация в `tests/fakes/__init__.py`:
   - In-memory list, `add` присваивает serial id, `get_active_by_player` фильтрует по `IN_PROGRESS`, `save` ищет по id.
   - При попытке `add` с уже активным `IN_PROGRESS`-походом игрока — `IntegrityError` (имитация partial unique-индекса).

4. **Integration-тесты `tests/integration/db/test_forest_run_repository.py`**:
   - Регистрация `ForestRunORM` в `tests/integration/db/conftest.py` (добавить в `from ... import (...)`).
   - `add` присваивает id, статус `IN_PROGRESS`.
   - `add` второй раз для того же игрока с активным походом — `IntegrityError` (partial unique-индекс срабатывает на SQLite — проверить, что `sqlite_where` действительно создаёт partial unique, иначе придётся через `WHERE` в SELECT).
   - После `save(run.mark_finished(...))` — partial unique-индекс ОТПУСКАЕТ старую запись и можно `add` нового активного.
   - `get_active_by_player` возвращает только `IN_PROGRESS`.
   - Round-trip всех трёх вариантов `Drop` (NoDrop / ItemDrop / NameDrop).

5. **Migrations smoke-test** (`tests/integration/db/test_migrations.py`):
   - Добавить `"0004_forest_runs"` в `test_expected_revisions_exist`.
   - Добавить `test_0004_descends_from_0003`.
   - Добавить `"20260504_0004_forest_runs.py"` в `test_versions_dir_lists_only_known_files`.
   - Добавить `"forest_runs"` в `expected` в `test_upgrade_head_creates_all_tables`.

6. **DI в `bot/main.py::build_container`** — зарегистрировать `IForestRunRepository` и `StartForestRun` (по аналогии с `register_player`). Без этого 1.3.D не подключится.

7. **`make ci`** — должен пройти ≥80% покрытия.

8. **Docs:**
   - `docs/current_tasks.md` — Sprint 1.3.B → 🟢 PR open (потом ✅ после мерджа).
   - `docs/history.md` — добавить раздел про 1.3.B.

9. **PR:**
   - `git_pr(action="fetch_template")`, потом `git_pr(action="create")`.
   - `git(action="pr_checks", wait_mode="all")`.
   - Удалить `HANDOFF.md` отдельным коммитом перед PR.

## Архитектурные ключевые решения (кратко)

- **Outcome ролится на старте, не на финише.** Branch / length_delta / drop сохраняются в `forest_runs` сразу. `FinishForestRun` (1.3.C) только применит — это устойчиво к рестарту воркера и hot-reload-у баланса посреди похода.
- **Activity-lock + partial unique index** — двойная защита от двух активных походов одного игрока. Lock срабатывает первым (быстрее, без round-trip в БД), unique — last-line-of-defense.
- **`Slot` / `Rarity` живут в `domain/balance/config.py`** (закрыто в 1.3.A) — `domain/forest/entities.py` их только реэкспортирует.
- **`SqlAlchemyForestRunRepository` зависит от `IBalanceConfig`** — для восстановления `Item` из `drop_item_id` при чтении строки. Это сознательно: каталог = источник правды.

## Не входит в 1.3.B (это 1.3.C/D)

- `FinishForestRun` use-case.
- APScheduler-job на ends_at.
- `inventory_items` таблица + `IInventoryRepository`.
- `/forest` bot-handler, инлайн-кнопки «Надеть/Выбросить», смена ника.
- Титул «Новичок».
