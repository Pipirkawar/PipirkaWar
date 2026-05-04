# Sprint 1.2.C — Handoff

**Branch:** `devin/1777914956-sprint-1-2c-signup-queue`
**Last commit:** `WIP: Sprint 1.2.C scaffold — signup_queue + DAU gate in RegisterPlayer`

> Этот документ описывает состояние работы в момент передачи и оставшийся
> чек-лист. После завершения PR-а HANDOFF.md можно удалить отдельным
> commit-ом — в репо его коммитить в финальный PR не нужно.

## Контекст

Спринт **1.2.C** закрывает задачи `1.2.4` (очередь `signup_queue` +
сообщение «Серверы переполнены») и `1.2.5` (авторазблокировка очереди
при падении DAU) из `docs/development_plan.md`. Полная спецификация
очереди — ГДД §18 (`docs/pipirik_wars_plan.md`).

DAU-инфраструктура (счётчик + лимит + `/admin_stats` + `/set_max_dau`)
уже есть из `1.2.B` (PR #14, смержен). Здесь мы её **подключаем** к
`RegisterPlayer` и `/start`.

## Что сделано в этом коммите

### Domain (`src/pipirik_wars/domain/signup_queue/`)
- `entities.py`: `SignupQueueEntry` (frozen dataclass) + `SignupQueueStatus` enum.
- `errors.py`: `SignupQueueError` → `AlreadyQueuedError(tg_id)`.
- `ports.py`: `ISignupQueueRepository` с методами `enqueue`,
  `get_by_tg_id`, `size`, `pop_front(limit)`.

### Domain shared
- `domain/shared/ports/audit.py`: добавлены `AuditAction.PLAYER_QUEUED`
  и `AuditAction.PLAYER_PROMOTED`.

### Infrastructure
- `infrastructure/db/models/signup_queue.py`: `SignupQueueORM`
  (UNIQUE на `tg_id`, индекс на `enqueued_at`).
- `infrastructure/db/migrations/versions/20260504_0003_signup_queue.py`:
  миграция `0003_signup_queue` (revises `0002_player_clan`).
- `infrastructure/db/repositories/signup_queue.py`:
  `SqlAlchemySignupQueueRepository` с lazy-расчётом `position` через
  `COUNT(*) WHERE enqueued_at < x` + tie-break по `tg_id`.

### Application
- **Перепиcaн** `application/player/register.py`:
  - Возвращает `RegisterPlayerResult = PlayerRegistered | PlayerQueued`
    (вместо raw `Player`).
  - Внутри UoW: читает `dau_counter.current()` и `dau_limit.get()`,
    при `current >= max` ставит в `signup_queue` с audit-записью
    `PLAYER_QUEUED` (idempotency_key = `queue_player:{tg_id}`).
  - `record_active(...)` зовётся **только** при успешной регистрации,
    чтобы очередники не съедали лимит.
  - Сигнатура `__init__` расширена: `signup_queue`, `dau_counter`, `dau_limit`.
- **Новый** `application/signup_queue/promote.py`:
  - `PromoteFromQueue` use-case + `PromoteFromQueueResult`.
  - Внутри UoW: считает `slots = max_dau - current_dau`,
    `pop_front(limit=slots)` → для каждой записи `players.add()` +
    audit `PLAYER_PROMOTED` (idempotency_key = `promote_player:{tg_id}`).
  - `record_active()` зовётся вне транзакции для каждого поднятого.
  - Кейс «игрок уже зарегистрирован через другой путь» → тихо
    пропускается, попадает в `skipped_already_registered`.

### Bot
- `bot/handlers/start.py`: новые сценарии — `PlayerQueued` →
  «Серверы переполнены, позиция #N», `AlreadyQueuedError` → читает
  текущую позицию из `signup_queue.get_by_tg_id`. Сигнатура
  `handle_start` расширена параметром `signup_queue: ISignupQueueRepository`.
- `bot/handlers/admin.py`:
  - `_format_dau_stats(current, max_dau, queue_size)` — третий аргумент.
  - `handle_admin_stats(..., signup_queue)` — теперь читает реальный
    размер очереди.
  - `handle_set_max_dau(..., promote_from_queue)` — при росте лимита
    зовёт `promote_from_queue.execute()` и добивает к ответу
    «↑ Из очереди поднято: N».
- `bot/main.py`:
  - `Container` получил `signup_queue: ISignupQueueRepository` и
    `promote_from_queue: PromoteFromQueue`.
  - `build_container()` собирает `SqlAlchemySignupQueueRepository` и
    `PromoteFromQueue`.
  - `build_dispatcher()` пробрасывает оба в workflow-data.

### Tests (частично)
- `tests/fakes/dau.py`: `FakeDauCounter`, `FakeDauLimit`.
- `tests/fakes/signup_queue.py`: `FakeSignupQueueRepository`
  (FIFO в `list[SignupQueueEntry]`, корректные `position` через
  пересчёт после `pop_front`).
- `tests/fakes/__init__.py`: экспорт новых фейков.
- `tests/unit/application/player/test_register_player.py` — переписан
  под новую сигнатуру; добавлен `class TestDauGate` с 6 кейсами
  (queued at limit / above limit / audit / FIFO positions / double-queue /
  below limit registers normally).
- `tests/unit/bot/handlers/test_start.py` — переписан под новый
  параметр `signup_queue` + добавлены `test_private_queued_replies_with_position`
  и `test_private_already_queued_reads_current_position_and_replies`.
- `tests/unit/bot/test_composition_root.py` — обновлён под новые поля
  `Container` (`signup_queue`, `promote_from_queue`) и новые
  workflow-data ключи в dispatcher.

Pre-commit hooks (`ruff`, `mypy`, `import-linter`) на коммите **прошли**.

## Что осталось (TODO для следующего работника)

### 1. Тесты `test_admin.py` — обязательно (handler-ы поменяли сигнатуру)

`tests/unit/bot/handlers/test_admin.py` вызывает старые сигнатуры
`handle_admin_stats(msg, identity, get_stats)` и
`handle_set_max_dau(msg, identity, set_max)`. Надо обновить:

- `handle_admin_stats` теперь принимает 4 параметра, последний —
  `signup_queue: ISignupQueueRepository`. Используй `FakeSignupQueueRepository()`
  или `MagicMock(spec=ISignupQueueRepository)` со стабом `size()`.
- `handle_set_max_dau` теперь принимает 4 параметра, последний —
  `promote_from_queue: PromoteFromQueue`. Используй
  `MagicMock(spec=PromoteFromQueue)` с `execute = AsyncMock(return_value=PromoteFromQueueResult(promoted=(), skipped_already_registered=(), available_slots=0))`.

Также добавь новые кейсы:
- `/admin_stats` отображает реальный размер очереди (например, `await queue.enqueue(...)` пару раз → assert на «Очередь регистраций: 2»).
- `/set_max_dau` при росте лимита зовёт `promote_from_queue.execute` и
  добивает к ответу «↑ Из очереди поднято: N» (где N > 0).
- При снижении лимита `promote_from_queue` НЕ зовётся (`assert_not_awaited`).
- При одинаковом лимите `promote_from_queue` НЕ зовётся.

### 2. Юнит-тесты для нового domain-слоя

Создать `tests/unit/domain/signup_queue/`:

- `test_entities.py`: `SignupQueueEntry` — frozen, slots, поля валидируются на типы (если применимо).
- `test_errors.py`: `AlreadyQueuedError(tg_id=42)` — наследник `DomainError`, корректный `__str__`, поле `tg_id`.

(Я уже создал пустые `__init__.py` в этих папках — их достаточно.)

### 3. Юнит-тесты `PromoteFromQueue`

Создать `tests/unit/application/signup_queue/test_promote.py`. Покрытие:

- Очередь пустая → `promoted=()`, `available_slots>0`.
- Очередь не пустая, но `slots=0` (DAU=MAX) → `promoted=()`, `available_slots=0`.
- DAU < MAX, в очереди 3 человека, slots=2 → поднимаются первые 2,
  третий остаётся.
- Каждый поднятый получает `record_active()` (DAU вырос на N).
- audit_log содержит `PLAYER_PROMOTED` с правильным `before` (из `entry.position`/`entry.enqueued_at`) и `after` (snapshot Player).
- Идемпотентность audit-key (`promote_player:{tg_id}`).
- Если `players.add` бросает `PlayerAlreadyRegisteredError` → попадает в `skipped_already_registered`, audit для этого `tg_id` НЕ пишется, остальные продолжают.
- `pop_front(limit=0)` (slots=0) → ранний return без `players.add`.

### 4. Integration-тесты репозитория `SqlAlchemySignupQueueRepository`

Файл по образцу `tests/integration/db/test_admin_repository.py`. Покрытие:

- `enqueue` сохраняет, возвращает entry с `id` и `position=1`.
- Повторный `enqueue` с тем же `tg_id` → `AlreadyQueuedError`.
- `get_by_tg_id` возвращает entry с актуальным `position` (1-based).
- `size()` корректно растёт/падает при enqueue/pop_front.
- `pop_front(limit=2)` забирает первых 2 в порядке `enqueued_at`.
- `pop_front(limit=0)` → `[]`, БД не меняется.
- FIFO: enqueue по разным `enqueued_at` → `pop_front` возвращает в порядке возрастания времени.
- `position` обновляется после `pop_front`: enqueue 3 → pop_front(1) → `get_by_tg_id` для второго возвращает position=1.
- Tie-break при одинаковом `enqueued_at` — по `tg_id`.

### 5. (Опционально, но желательно) E2E-тест полного цикла

`tests/integration/db/test_signup_queue_flow.py`:

- MAX_DAU=2, регистрируем 4 игроков → первые 2 в `users`, остальные 2 в `signup_queue` (#1, #2).
- `/set_max_dau 5` → `PromoteFromQueue.execute()` → оба поднимаются, очередь пустая, `users` имеет 4 строки, audit имеет соответствующие записи `PLAYER_REGISTER` и `PLAYER_PROMOTED`.

### 6. `make ci`

Проверить локально: `cd /home/ubuntu/repos/PipirkaWar && make ci`.

Должны пройти:
- `ruff check` (линт)
- `ruff format --check` (формат)
- `mypy` (типы)
- `lint-imports` (import-linter, контракты слоёв)
- `pytest --cov-fail-under=80` (тесты + ≥80% покрытия)

**Известный риск:** покрытие может упасть ниже 80%, потому что добавлено
много новых LoC. Если упало — добивай тестами по списку выше или подними
порог отдельно (но это не обсуждалось в плане; лучше добивать тестами).

### 7. Документация

`docs/current_tasks.md`:
- 1.2.A → ✅ (PR #13 смержен)
- 1.2.B → ✅ (PR #14 смержен)
- 1.2.C → 🟢 в работе → ✅ после мержа этого PR.

`docs/history.md`: добавить запись про 1.2.C (очередь + auto-promote).

### 8. PR

```bash
git push -u origin devin/1777914956-sprint-1-2c-signup-queue
```

Затем:
- `git_pr(action="fetch_template", repo="Pipirkawar/PipirkaWar", exec_dir="/home/ubuntu/repos/PipirkaWar")`
- `git_pr(action="create", repo="Pipirkawar/PipirkaWar", title="Спринт 1.2.C: signup_queue + DAU gate в RegisterPlayer + auto-promote", body=<по шаблону>, head_branch="devin/1777914956-sprint-1-2c-signup-queue", base_branch="main")`
- `git(action="pr_checks", wait_mode="all")`

Не забудь удалить `HANDOFF.md` отдельным коммитом перед мержем
(или просто не пушить его — оставить как локальный файл; `.gitignore`
уже не нужен, `HANDOFF.md` уже зафиксирован в коммите). Чтобы аккуратно
выкинуть из истории — `git rm HANDOFF.md && git commit -m "chore: drop handoff doc"`.

## Архитектурные решения / нюансы

- **Position lazy-вычисление:** `SqlAlchemySignupQueueRepository._position_of`
  считает `1 + COUNT(WHERE enqueued_at < x) + COUNT(WHERE enqueued_at = x AND tg_id < y)`.
  Это устраняет необходимость хранить `position` как колонку и
  обновлять её при `pop_front` (что было бы O(N) на каждое удаление).
  Tie-break по `tg_id` исключает «два первых места» при одинаковом
  `enqueued_at` (теоретически возможно при clock-truncation).

- **`SetMaxDau` не вызывает `PromoteFromQueue` напрямую:** мы оставили
  `SetMaxDau` use-case без изменений (он уже смержен в 1.2.B). Триггер
  promotion-а живёт в bot-handler-е `handle_set_max_dau`. Это
  сохраняет ответственности раздельными: use-case = «изменить лимит»,
  handler = «оркестрировать use-case-ы».

- **Periodic promote (cron / APScheduler) НЕ реализован.** ГДД §18.3
  упоминает «Когда DAU падает ниже лимита (вечер/ночь)» — это про
  смену игрового дня, когда `IDauCounter.current()` обнуляется на
  полночь МСК. В этом PR-е promote триггерится только при
  `/set_max_dau`. Cron-tick запланирован на 1.2.D вместе с 80%-alert-ом
  и `INotifier`. Если хочешь добавить уже сейчас — это не сложно,
  но потребует APScheduler в deps + lifecycle-hook в `run()`.

- **Уведомления игроку «ваш пипирик готов» (ГДД §18.3) НЕ
  отправляются.** Это требует `INotifier` порта + `Bot.send_message`
  адаптера; запланировано на 1.2.D. На текущей фазе игрок узнает о
  повышении при следующем `/start` («ты уже зарегистрирован, /profile»)
  или просто увидит карточку через `/profile`. Acceptance criteria
  1.2.5 формально неполностью закрыт без INotifier — учти при
  обновлении `current_tasks.md`. Можно отметить «1.2.4 ✅, 1.2.5 ⚠️
  (уведомление в 1.2.D)» или закрыть оба и завести таску на notifier.

## Команды для быстрого старта

```bash
cd /home/ubuntu/repos/PipirkaWar
git status                                     # должно быть чисто
git log --oneline -5                           # увидеть последний WIP-commit
make ci                                        # проверить, что не сломалось
pytest tests/unit/application/player/test_register_player.py -v
pytest tests/unit/bot/handlers/test_start.py -v
pytest tests/unit/bot/handlers/test_admin.py -v   # тут будут падать
pytest tests/unit/bot/test_composition_root.py -v
```

Удачной работы.
