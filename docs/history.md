# 🍆 Пипирик Варс — История выполнения

> Хронологический журнал выполненных работ по проекту. Каждая запись — это завершённая задача / спринт / решение. Новые записи добавляются **сверху** (свежие — первыми).
>
> Формат записи:
>
> ```
> ## YYYY-MM-DD — Заголовок
> **Автор:** имя
> **Тип:** plan | feature | fix | refactor | infra | balance | doc | decision
> **Связано:** ссылка на задачу из current_tasks.md / PR / коммит
>
> Что сделано:
> - пункт 1
> - пункт 2
>
> Результат / артефакты:
> - ссылки на файлы, миграции, конфиги
>
> Заметки / решения:
> - почему сделано именно так
> ```

---

## 2026-05-04 — Спринт 1.3.D: bot-handler `/forest` + finish-нотификация + inline-кнопки

**Автор:** Devin (по запросу azurehannah)
**Тип:** feature (bot/handlers + bot/presenters + bot/notifications + application use-case + DI)
**Связано:** Текущий PR (Спринт 1.3.D), [development_plan.md §3 / Спринт 1.3, задачи 1.3.1 / 1.3.2 / 1.3.6](development_plan.md), [current_tasks.md Спринт 1.3 → 1.3.D](current_tasks.md). Закрывает Спринт 1.3 (после смерженных 1.3.A–C).

Узкий PR: пользовательская петля «лес» — игрок вызывает `/forest` и получает «ушёл в лес», по истечении кулдауна получает «вернулся из леса» с inline-кнопками. Ровно три фичи в одном PR: command-handler, finish-нотификатор и callback-handler `apply_name`. Применение item-дропа / drop_name / drop_item — placeholder-toast, чтобы не блокировать выпуск; полная реализация инвентаря — Спринт 1.4.

Что сделано:
- **Application (`application/forest/notifier.py`)** — порт `IForestFinishNotifier.notify(result: ForestRunFinished) -> None`. Контракт «best-effort, не бросает наружу»: реализация ловит ошибки сама. Используется APScheduler-адаптером после успешного `FinishForestRun.execute()` — пост-коммитный сайд-эффект, который не должен ронять job-у.
- **Application (`application/forest/apply_name_drop.py`)** — use-case `ApplyForestNameDrop(uow, players, runs, audit, clock)`. Срабатывает при нажатии «Заменить» под сообщением «вернулся из леса», когда у игрока **уже есть имя** и из леса выпал `NameDrop` (auto-apply невозможен). Защита: `ForestRunOwnershipError` (защита от форварда чужой кнопки), `ForestDropMismatchError` (run.drop ≠ NameDrop), идемпотентный no-op если `player.name == run.drop.name`. Audit: `NAME_GRANT` с `reason="forest_name_replacement"` и `idempotency_key=f"forest_name_replace:{run_id}"`.
- **Application DTO** — `ApplyForestNameDropInput(run_id, tg_id)` с pydantic-валидацией.
- **Domain (`domain/forest/errors.py`)** — добавлены `ForestRunOwnershipError(run_id, run_player_id, actor_player_id)` и `ForestDropMismatchError(run_id, expected, got)` для callback-сценариев.
- **Bot/presenters (`bot/presenters/forest.py`)** — чистые функции рендера + сборки `InlineKeyboardMarkup`. `render_forest_started(player, display_name, cooldown_minutes)`, `render_forest_finished(result, display_name_after)`, `build_finish_keyboard(result)`, `forest_callback_data(action, run_id)` / `parse_forest_callback_data(raw)` (формат `forest:<action>:<run_id>` ≤ 33 байт, под Telegram-лимит 64). Полный ник `[Титул] [Название] [Имя]` через существующий `render_full_nick(...)` из 1.1.E.
- **Bot/handlers (`bot/handlers/forest.py`)** — handler `/forest` (private only) и единый `handle_forest_callback` для всех `forest:*`-кнопок. Перехватывает `PlayerNotFoundError` / `AlreadyInForestError` / `ForestRunNotFoundError` / `ForestRunOwnershipError` / `ForestDropMismatchError` и шлёт toast / инструкцию. После успешного callback-а `edit_reply_markup(reply_markup=None)` снимает клавиатуру, чтобы повторные клики не проходили.
- **Bot/notifications (`bot/notifications/forest.py`)** — `TelegramForestFinishNotifier(IForestFinishNotifier)` рендерит сообщение и шлёт через `bot.send_message`. Catch `TelegramAPIError` / general `Exception` → лог + `return` (ни одной exc не пропускается в APScheduler-callback). Имя нотификатора живёт в `bot/`, а не в `infrastructure/telegram/`, потому что нужно `bot/presenters/forest.py` (`InlineKeyboardMarkup`), а `infrastructure → bot` запрещён import-linter-ом.
- **Infrastructure (`infrastructure/scheduler/aps.py`)** — `APSchedulerDelayedJobScheduler` теперь принимает опциональный `notifier: IForestFinishNotifier | None`. После успешного `FinishForestRun.execute()` зовёт `notifier.notify(result)`; ошибка нотификатора логируется через `logger.exception(...)`, но не пробрасывается (контракт notifier-а — «не бросать»; защита по второму уровню).
- **Composition root (`bot/main.py`)** — `build_container(settings, *, balance_yaml_path, bot=None)`. Если `bot is not None` — создаётся `TelegramForestFinishNotifier` и передаётся в scheduler. `ApplyForestNameDrop` добавлен в `Container` и в `build_dispatcher` workflow-data (`apply_forest_name_drop`). `run()` создаёт Settings → Bot → `build_container(settings, ..., bot=bot)`, чтобы нотификатор всегда был сконфигурирован в production.
- **Тесты** (всего +70 кейсов, общее число 736, покрытие 96.60 %):
  - `tests/unit/bot/presenters/test_forest.py` — 29 кейсов: `render_forest_started` (новичок без титула / титул+имя / минимальный кулдаун), `render_forest_finished` (`NoDrop`+титул, `ItemDrop`+редкость, `NameDrop` auto-apply, `NameDrop` с уже имеющимся именем), `build_finish_keyboard` (4 ветки), сериализация/парсинг callback-data (round-trip, malformed, негативный run_id, длина под 64 байта), хелперы.
  - `tests/unit/bot/handlers/test_forest.py` — 21 кейс: `/forest` happy / not-registered / already-in-forest / group / supergroup / channel / no-identity / профиль вернул None; callback `apply_name` (success / already-applied / run-not-found / player-not-found / ownership-mismatch / drop-mismatch); placeholder-toast для `drop_name`/`equip_item`/`drop_item`; malformed callback_data; `edit_reply_markup` swallow при ошибке.
  - `tests/unit/bot/notifications/test_forest.py` — 9 кейсов: `was_already_finished` → no-op; happy paths для `NoDrop` / `ItemDrop` / `NameDrop`-replacement; `TelegramAPIError` / `RuntimeError` / падение баланса все swallow-ятся; `display_name_for(after.length)` пересчитывается; работает без logger.
  - `tests/unit/application/forest/test_apply_name_drop.py` — 7 кейсов: happy (audit-запись с `NAME_GRANT`/`forest_name_replacement`), идемпотентность при том же имени, ошибки run-not-found / player-not-found / ownership-mismatch / drop-mismatch (NoDrop / ItemDrop), отсутствие commit-а при ошибках.
  - `tests/unit/infrastructure/scheduler/test_aps.py` — +4 кейса: notifier зовётся после успешного finish-а; не зовётся при доменной ошибке; ошибка notifier-а не ронит job-у; работает без notifier-а (обратная совместимость).
  - `tests/unit/bot/test_composition_root.py` — обновлён `_container_with_fakes()` для нового поля `apply_forest_name_drop`.

Результат / артефакты:
- `src/pipirik_wars/application/forest/notifier.py` (порт)
- `src/pipirik_wars/application/forest/apply_name_drop.py` (use-case)
- `src/pipirik_wars/application/dto/inputs.py` (DTO `ApplyForestNameDropInput`)
- `src/pipirik_wars/domain/forest/errors.py` (новые ошибки)
- `src/pipirik_wars/bot/handlers/forest.py` (новый handler + callback-router)
- `src/pipirik_wars/bot/presenters/forest.py` (новый презентер)
- `src/pipirik_wars/bot/notifications/forest.py` (`TelegramForestFinishNotifier`)
- `src/pipirik_wars/infrastructure/scheduler/aps.py` (notifier wiring)
- `src/pipirik_wars/bot/main.py` (composition root, build_container получает Bot)
- `tests/unit/bot/presenters/test_forest.py`, `tests/unit/bot/handlers/test_forest.py`, `tests/unit/bot/notifications/test_forest.py`, `tests/unit/application/forest/test_apply_name_drop.py`, `tests/unit/infrastructure/scheduler/test_aps.py`

Заметки / решения:
- **Нотификатор живёт в `bot/`, не в `infrastructure/telegram/`.** Ему нужны `InlineKeyboardMarkup` и `render_forest_finished` из `bot/presenters/forest.py`. Импорт `infrastructure → bot` запрещён import-linter-ом (это и правильно — инфраструктура не должна знать про презентационный слой). Поэтому нотификатор «телеграмный по реализации, бот-овый по слою»: presenter зависит от aiogram-типов, а нотификатор использует presenter. Это согласовано с layered_architecture-контрактом и не ломает направление зависимостей.
- **APScheduler не должен пометить job-у failed из-за нотификатора.** `_run_finish_job` сначала зовёт `FinishForestRun.execute()` (если падает — глотает); затем вызывает `notifier.notify(result)`. Сам нотификатор не бросает, но даже если бросит — APScheduler-адаптер ловит и логирует через `logger.exception`. Это «оборона в глубину»: ни логи telegram-API, ни внутренние баги не должны откатывать job-у.
- **Callback-handler делает `edit_reply_markup(None)` для всех завершающих действий.** Это снимает кнопки сразу после клика, чтобы пользователь не мог нажать повторно (даже если идемпотентный use-case это переживёт). При `ForestRunOwnershipError` (форвард в чужой чат) клавиатуру **не** трогаем — это чужое сообщение.
- **`drop_name` / `equip_item` / `drop_item` пока placeholder.** Они шлют toast «выбросил имя» / «надевание предмета — Спринт 1.4» и снимают клавиатуру, но НЕ зовут use-case. Применение `ItemDrop` (надеть/положить в инвентарь) и `drop_name` (запись `NAME_DROP`-аудита, потеря имени из инвентаря) появятся в Спринте 1.4 (предметы и инвентарь). Это сознательный компромисс: текущий PR закрывает 1.3.1 / 1.3.2 / 1.3.6 в части UX «вышел в лес → вернулся → видит дроп», но полное применение item-дропа отложено.
- **`ApplyForestNameDrop` идемпотентен через ownership-проверку и сравнение `player.name == drop.name`.** Аудит-`idempotency_key` (`forest_name_replace:{run_id}`) предотвращает race-condition при двойном клике быстрее, чем edit_reply_markup.
- **Composition root: `build_container(bot=...)`.** Чтобы создать notifier, нужен `Bot`. Сделали `bot` опциональным kwarg-ом `build_container`-а: tests могут вызывать без него (notifier остаётся `None`, scheduler работает без нотификации); production `run()` создаёт сначала Settings → Bot → передаёт его в build_container. Обратная совместимость сохранена для всех существующих тестов.

---

## 2026-05-04 — Спринт 1.3.C: `FinishForestRun` + APScheduler-job + титул «Новичок»

**Автор:** Devin (по запросу sandyemaroon)
**Тип:** feature (application + infra adapter + DI)
**Связано:** Текущий PR (Спринт 1.3.C), [development_plan.md §3 / Спринт 1.3, задачи 1.3.3 / 1.3.7 / 1.3.8](development_plan.md), [current_tasks.md Спринт 1.3 → 1.3.C](current_tasks.md). Продолжает Спринт 1.3 после смерженного 1.3.B (PR #18).

Узкий PR: завершение похода в лес (применение исхода + автовыдача титула «Новичок» + auto-apply имени), плюс `IDelayedJobScheduler` порт и его APScheduler-адаптер. Bot-handler `/forest` и inline-кнопки «Надеть/Выбросить» / «Заменить/Выбросить» остаются на 1.3.D.

Что сделано:
- **Domain** — добавлен порт `IDelayedJobScheduler` (`schedule_finish_forest_run` + `cancel_finish_forest_run`, оба идемпотентны), ошибка `ForestRunNotFoundError(run_id)`, методы `IPlayerRepository.get_by_id` и `IForestRunRepository.get_by_id`. Реализации `SqlAlchemyPlayerRepository.get_by_id` / `SqlAlchemyForestRunRepository.get_by_id` отзеркалены `tests/fakes/`.
- **Application (`application/forest/finish_run.py`)** — use-case `FinishForestRun(uow, players, runs, locks, audit, clock)`:
  1. `runs.get_by_id(run_id)` → `ForestRunNotFoundError` если запись отсутствует.
  2. `players.get_by_id(run.player_id)` → `PlayerNotFoundError` если ссылка «висит».
  3. Если `run.status is FINISHED` — идемпотентный no-op (`was_already_finished=True`).
  4. `player.with_length(...)` — `length += run.length_delta_cm` (всегда `>0`).
  5. Если `player.title is None` — выдать `Title.NEWBIE` (ПД §1.3.8 / ГДД §8.2 «первый успешный лес»). Идемпотентно по `player.title is None`.
  6. Если `run.drop is NameDrop` и `player.name is None` — auto-apply имя (ГДД §2.5).
  7. `runs.save(run.mark_finished(now))`, `locks.release(player, FOREST)`.
  8. Audit: `LENGTH_GRANT` всегда; `TITLE_GRANT` (`reason="first_forest_title"`) при `granted_title=True`; `NAME_GRANT` (`reason="forest_name_drop_auto_apply"`) при `granted_name=True`. `idempotency_key` строится по `forest_run_id`.
  9. Возвращает `ForestRunFinished(run, player_before, player_after, granted_title, granted_name, was_already_finished)`.
- **Application (`StartForestRun`)** — теперь принимает `IDelayedJobScheduler` и после `runs.add(...)` вызывает `scheduler.schedule_finish_forest_run(run_id, run_at=run.ends_at)`. Идемпотентно (`replace_existing=True` на адаптере); если бот рестартнётся — повторный `start` перезапишет job-у.
- **Infrastructure (`infrastructure/scheduler/aps.py`)** — `APSchedulerDelayedJobScheduler` поверх `AsyncIOScheduler`. `schedule_*` использует `replace_existing=True` и `misfire_grace_time=None` (job стрельнёт даже если бот пропустил `run_at`). `cancel_*` — best-effort (поглощает `JobLookupError`). Lifecycle: `start()` / `shutdown(wait=False)` идемпотентны. Callback `_run_finish_job` через `finish_factory: Callable[[], FinishForestRun]` (свежая ссылка на use-case) — поглощает `ForestRunNotFoundError` / `PlayerNotFoundError` (с `logger.warning`) и любую другую ошибку (с `logger.exception`), чтобы APScheduler не пометил job-у «failed» и не оставил её в job-store-е.
- **Composition root (`bot/main.py::build_container`)** — зарегистрированы `IDelayedJobScheduler` (реальный `APSchedulerDelayedJobScheduler` с `AsyncIOScheduler()`) и `FinishForestRun`. `StartForestRun` теперь получает scheduler. В `run()` вызывается `scheduler.start()` после `build_container` и `scheduler.shutdown(wait=False)` в `finally`-блоке.
- **Тесты** (всего +47 кейсов, общее количество 666, покрытие 96.65 %):
  - `tests/unit/domain/forest/test_errors.py` — `AlreadyInForestError` / `ForestRunNotFoundError` (наследование от `ForestError`, payload).
  - `tests/fakes/delayed_job_scheduler.py` (`FakeDelayedJobScheduler`) + `tests/unit/fakes/test_delayed_job_scheduler.py` — 4 кейса (schedule, overwrite, cancel, missing).
  - `tests/unit/application/forest/test_finish_run.py` — 9 кейсов: happy path с грантом титула, идемпотентность на уже-`FINISHED`, не-перевыдача титула, auto-apply имени, не-перетирание имени, `ItemDrop` без auto-apply имени, `ForestRunNotFoundError`, `PlayerNotFoundError`, проверка rollback UoW.
  - `tests/unit/application/forest/test_start_run.py` — обновлены все 8 тестов (новый параметр `scheduler`); добавлена проверка, что `scheduler.scheduled[run.id].run_at == run.ends_at`.
  - `tests/unit/infrastructure/scheduler/test_aps.py` — 10 кейсов: schedule добавляет job-у, schedule перезаписывает, cancel удаляет, cancel-missing — no-op, lifecycle идемпотентен, callback вызывает use-case, callback поглощает `ForestRunNotFoundError` / `PlayerNotFoundError` / `RuntimeError`, дефолтный logger подхватывается.
  - `tests/integration/db/test_player_repository.py` / `test_forest_run_repository.py` — добавлены `get_by_id_returns_*` и `get_by_id_missing_returns_none`.
  - `tests/unit/bot/test_composition_root.py` — обновлён `_container_with_fakes()` (передача `delayed_jobs` и `finish_forest_run`); добавлены проверки, что в `Container` и в `build_dispatcher`-workflow-data зарегистрированы оба новых компонента, и в реальном контейнере `delayed_jobs is APSchedulerDelayedJobScheduler`.

Результат / артефакты:
- Domain / app / infra: `src/pipirik_wars/domain/shared/ports/scheduler.py`, `src/pipirik_wars/domain/forest/errors.py` (+`ForestRunNotFoundError`), `src/pipirik_wars/domain/forest/repositories.py` (`get_by_id`), `src/pipirik_wars/domain/player/repositories.py` (`get_by_id`), `src/pipirik_wars/application/forest/finish_run.py`, `src/pipirik_wars/application/forest/start_run.py` (планирование finish-job-а), `src/pipirik_wars/application/dto/inputs.py` (`FinishForestRunInput`), `src/pipirik_wars/infrastructure/scheduler/aps.py`, `src/pipirik_wars/infrastructure/db/repositories/forest_run.py` (`get_by_id`), `src/pipirik_wars/infrastructure/db/repositories/player.py` (`get_by_id`).
- DI: `src/pipirik_wars/bot/main.py` (Container + build_container + build_dispatcher + run-lifecycle).
- Тесты: `tests/fakes/delayed_job_scheduler.py`, `tests/unit/application/forest/test_finish_run.py`, `tests/unit/infrastructure/scheduler/test_aps.py`, `tests/unit/fakes/test_delayed_job_scheduler.py`, `tests/unit/domain/forest/test_errors.py` + обновления `test_start_run.py`, `test_composition_root.py`, `test_player_repository.py`, `test_forest_run_repository.py`.
- Зависимости: `apscheduler>=3.10,<4` в `pyproject.toml`; mypy-override `apscheduler.* → ignore_missing_imports`; `.pre-commit-config.yaml` обновлён на ту же версию.

Заметки / решения:
- **Idempotency at scheduler layer** — `schedule_finish_forest_run` использует `replace_existing=True`, поэтому `StartForestRun` может вызываться повторно (например, после рестарта бота с retry-логикой) без побочных эффектов на сторону scheduler-а. На стороне БД защищает partial unique-индекс из 1.3.B.
- **Idempotency at use-case layer** — `FinishForestRun` сам поглощает повторные вызовы на уже-`FINISHED`-записи (без mutations / audit). Это защищает от misfire / двойного scheduler-а / ручного re-run-а.
- **Title auto-grant** — выдаём `NEWBIE`, только если `player.title is None`. Если игрок уже носит другой титул (например, из админ-панели в будущих спринтах) — не перетираем.
- **Name auto-apply** — только если `player.name is None`. Иначе drop остаётся в очереди handler-а 1.3.D, который даст inline «Заменить / Выбросить» (как в ГДД §2.5).
- **`ItemDrop` не применяется автоматически** — handler 1.3.D даст «Надеть / Выбросить»; авто-надевание не делаем, чтобы игрок мог осознанно решать, что лучше.
- **APScheduler error-handling** — три уровня: (а) `_run_finish_job` ловит `ForestRunNotFoundError` / `PlayerNotFoundError` и логирует `warning` (это не ошибка системы, а ситуация «запись съели вручную из БД» / «игрок удалён» / «cancel + повторный schedule»); (б) catch-all `Exception` логирует `exception` (полный traceback); (в) APScheduler сам не падает, потому что callback ничего не пробрасывает наружу — job помечается «успешно завершённой» и удаляется из job-store-а.
- **`finish_factory: Callable[[], FinishForestRun]`** — ленивая фабрика, чтобы можно было поменять реализацию use-case-а без переинициализации scheduler-а; в production используется `lambda: container.finish_forest_run`.
- **Зачем `IPlayerRepository.get_by_id`?** — `forest_runs.player_id` хранит внутренний `players.id`, а не `tg_id`. До 1.3.C use-case-ы леса работали только со старт-точкой (где есть `Player`), а в `FinishForestRun` есть только `run.player_id`. Поэтому добавили парный метод (фейк, ORM-репозиторий, integration-тесты).
- **Покрытие** — `make ci` локально: 666 тестов, 96.65 % (`fail_under=80 %`), все слои pre-commit-чисты (ruff/black/mypy/import-linter).

---

## 2026-05-04 — Спринт 1.3.B: persistence леса + use-case `StartForestRun`

**Автор:** Devin (по запросу sandyemaroon)
**Тип:** feature (persistence + application + infra DI)
**Связано:** Текущий PR (Спринт 1.3.B), [development_plan.md §3 / Спринт 1.3, задача 1.3.9](development_plan.md), [current_tasks.md Спринт 1.3 → 1.3.B](current_tasks.md). Продолжает Спринт 1.3 после смерженного 1.3.A (PR #17).

Узкий PR: persistence-слой леса + один use-case `StartForestRun`. Активная запись охраняется и `ActivityLockService` (in-memory защита от двойного `/forest`), и DB partial unique-индексом (last-line-of-defense на случай ручных SQL / миграций мимо доменного слоя). Bot-handler и `FinishForestRun` остаются на 1.3.D / 1.3.C.

Что сделано:
- **Domain (`domain/forest/`)** — добавлены `ForestRun` (frozen-dataclass со статусом `IN_PROGRESS / FINISHED`, фабрикой `starting()` и идемпотентным `mark_finished()`), `IForestRunRepository` (`add` / `get_active_by_player` / `save`) и `AlreadyInForestError(player_id)`. Инвариант `ends_at > started_at` охраняется в `starting()`.
- **Application (`application/forest/start_run.py`)** — use-case `StartForestRun(uow, players, runs, locks, balance, random, audit, clock)`:
  1. `players.get_by_tg_id(...)` → `PlayerNotFoundError` если нет.
  2. `random.randint(forest.cooldown_min_minutes, forest.cooldown_max_minutes)` → `cooldown_minutes`.
  3. `locks.acquire(actor_kind="player", actor_id=player.id, reason=FOREST, ttl=cooldown)` → `AlreadyInForestError` при `LockAlreadyHeldError`.
  4. `compute_forest_outcome(balance, random)` → `ForestRunOutcome`.
  5. `runs.add(ForestRun.starting(...))` → запись `IN_PROGRESS`.
  6. `audit.record(FOREST_RUN_STARTED, before=None, after={player_id, branch_name, length_delta_cm, drop_kind, cooldown_minutes, ends_at})`.
  7. Возвращает `ForestRunStarted(run, cooldown_minutes)`.
- **Infrastructure (`infrastructure/db/`)** — миграция `0004_forest_runs` (таблица `forest_runs` + 6 CHECK-constraint-ов на статусы / payload / временные интервалы + два index-а + partial unique `(player_id) WHERE status='in_progress'`); `ForestRunORM` с теми же CHECK-ами на ORM-уровне; `SqlAlchemyForestRunRepository` (`add` / `get_active_by_player` / `save`, сериализация `Drop` ADT в три колонки `drop_kind` / `drop_item_id` / `drop_name`; восстановление `Item` из текущего `IBalanceConfig`).
- **Composition root (`bot/main.py::build_container`)** — зарегистрированы `IActivityLockRepository`, `IForestRunRepository` и `StartForestRun` (в `Container` + `build_dispatcher` workflow-data). Use-case готов к подключению `/forest` handler-а в 1.3.D.
- **Тесты** — все четыре уровня покрытия:
  - `tests/unit/domain/forest/test_run.py` — 9 кейсов на `ForestRun.starting()` (статусы, копирование outcome, инвариант `ends_at > started_at`) и `mark_finished()` (идемпотентность, иммутабельность).
  - `tests/fakes/forest_run_repo.py` (`FakeForestRunRepository`) и `tests/fakes/lock_repo.py` (`FakeActivityLockRepository`) — общие in-memory фейки.
  - `tests/unit/application/forest/test_start_run.py` — happy path, audit-payload, `AlreadyInForestError`, `PlayerNotFoundError`, детерминизм при фиксированном seed.
  - `tests/integration/db/test_forest_run_repository.py` — 8 кейсов на real-SQLAlchemy + aiosqlite: serial id, partial unique, post-finish добавление новой активной записи, round-trip всех трёх вариантов `Drop` (`NoDrop` / `ItemDrop` / `NameDrop`).
  - `tests/integration/db/test_migrations.py` — добавлены `0004_forest_runs` к smoke-тестам (revisions, descend chain, files, expected tables).

Результат / артефакты:
- Domain / app / infra: `src/pipirik_wars/domain/forest/run.py`, `src/pipirik_wars/domain/forest/repositories.py`, `src/pipirik_wars/domain/forest/errors.py`, `src/pipirik_wars/application/forest/start_run.py`, `src/pipirik_wars/infrastructure/db/models/forest.py`, `src/pipirik_wars/infrastructure/db/repositories/forest_run.py`, `src/pipirik_wars/infrastructure/db/migrations/versions/20260504_0004_forest_runs.py`.
- DI: `src/pipirik_wars/bot/main.py` (Container + build_container + build_dispatcher).
- Тесты: `tests/unit/domain/forest/test_run.py`, `tests/unit/application/forest/test_start_run.py`, `tests/integration/db/test_forest_run_repository.py`, `tests/integration/db/test_migrations.py`, `tests/fakes/forest_run_repo.py`, `tests/fakes/lock_repo.py`, `tests/unit/bot/test_composition_root.py` (расширен).
- Доки: запись здесь + текущая задача 1.3.B → 🟢 PR open в `current_tasks.md`.

Заметки / решения:
- Двухуровневая защита от двойного `/forest`: `ActivityLockService` (короткий TTL = cooldown) — основной путь, partial unique-индекс `(player_id) WHERE status='in_progress'` — last-line-of-defense на случай прямого SQL / миграций. Это объясняет, почему integration-тест `test_partial_unique_blocks_second_active_run` обходит ActivityLock (он не задействован в репозитории напрямую).
- Сериализация `Drop` в три колонки (`drop_kind` / `drop_item_id` / `drop_name`) выбрана вместо JSONB по двум причинам: (а) каждая колонка проверяется CHECK-constraint-ами; (б) при `FinishForestRun` (1.3.C) нужно сделать FK-проверку `drop_item_id` против текущего `items_catalog` — JSONB здесь скрыл бы инвариант.
- `ForestRun.mark_finished()` идемпотентен (повторный вызов на уже финишированной записи возвращает `self`). Это упрощает APScheduler-job из 1.3.C: при перезапуске воркера джоб может дёрнуть `mark_finished` повторно — никаких двойных side-эффектов.
- Локально: `make ci` (lint / typecheck / imports / pytest --cov) — 637 тестов, покрытие **97 %** (≥80 % требование `pyproject.toml`).

---

## 2026-05-04 — Спринт 1.3.A: `balance.yaml` + `domain/forest/` (фундамент леса)

**Автор:** Devin (по запросу birgit865)
**Тип:** feature (balance + domain)
**Связано:** Текущий PR (Спринт 1.3.A), [development_plan.md §3 / Спринт 1.3, задачи 1.3.4 + 1.3.5](development_plan.md), [current_tasks.md Спринт 1.3 → 1.3.A](current_tasks.md). Открывает Спринт 1.3 после закрытого 1.2 (PR #13/14/15/16).

Узкий PR: только конфиг и чистый домен леса, без bot / persistence / use-case-ов. Шмот, имена и расчёт исхода теперь живут в одном месте, и любая последующая работа (1.3.B/C/D) ставит свою бизнес-логику поверх уже валидированных каталогов и детерминированной чистой функции.

Что сделано:
- **`config/balance.yaml`** — `version: 3`.
  - `forest.drop`: `probability_percent: 50` (общий шанс любого дропа), `name_share_percent: 5` (внутри дропов — доля имён vs предметов; ГДД §2.5 — единственный путь получить имя), `rarity_weights: {common: 70, rare: 25, epic: 5}` (ГДД §1.3.5).
  - `items_catalog`: 30 предметов на 6 слотов (`hat / body / legs / boots / ring / chain`), у каждого `id` (стабильный, формата `item.<slot>.<short>`) / `slot` / `display_name` / `rarity` (ГДД §2.6, тематика — «майка-алкоголичка», «лапти скорохода», «голда с рынка», и т. п.).
  - `names_catalog`: 32 имени из ГДД §2.5 (Колян, Толик, Жорик, Эдгар, Бананчик-Коляндр, …) — все уникальные, без редкости.
- **`domain/balance/config.py`** — расширили pydantic-схему.
  - Новые типы (StrEnum): `Slot` (6 значений) и `Rarity` (3 значения). Живут именно здесь, потому что ими типизирован сам каталог; `domain/forest/entities.py` реэкспортирует их для коротких импортов.
  - `ForestRarityWeights` — `common / rare / epic > 0`, все три обязательны (иначе rarity-roll получил бы недостижимую ветку).
  - `ForestDropConfig` — `probability_percent ∈ [0, 100]`, `name_share_percent ∈ [0, 100]`, `rarity_weights: ForestRarityWeights`. 0 % — валидное состояние «лес временно без дропа» под админ-панель.
  - `ForestConfig.drop: ForestDropConfig` — обязательное поле.
  - `ItemEntry` — frozen pydantic-модель (`id 1..64` non-empty, `slot: Slot`, `display_name 1..64`, `rarity: Rarity`).
  - `BalanceConfig.items_catalog: tuple[ItemEntry, ...]` (`min_length=30`) + `BalanceConfig.names_catalog: tuple[str, ...]` (`min_length=30`).
  - Два новых валидатора `BalanceConfig`: ID предметов уникальны + каждая редкость покрыта ≥ 1 предметом; имена — non-empty, не whitespace-only, уникальны.
- **`domain/forest/`** (новый пакет) — чистая модель леса (ГДД §8.2, §1.3.4-§1.3.5).
  - `entities.py`: реэкспорт `Slot` / `Rarity`; frozen-dataclass-ы `Item` / `Name` / `OutcomeBranch`. ADT `Drop = NoDrop | ItemDrop | NameDrop` (`NoDrop` — пустой dataclass для pattern-match). Корневой результат — `ForestRunOutcome(branch, length_cm, drop)`.
  - `errors.py`: пустой пока `ForestError` для будущих use-case-ных ошибок (1.3.B/C).
  - `services.py::compute_forest_outcome(*, balance, random)` — ровно один публичный API. Алгоритм:
    1. `random.weighted_choice([0..n-1], [outcome.weight])` → ветка.
    2. `random.randint(branch.min, branch.max)` → длина.
    3. `random.randint(1, 100) > probability_percent` → `NoDrop`. Иначе — `random.randint(1, 100) <= name_share_percent` → имя (`random.choice(names_catalog)`), иначе — предмет: `weighted_choice` по rarity_weights → `random.choice(pool)` среди предметов выбранной редкости.
  - Все 5 шагов идут через инжектируемый `IRandom` — никаких прямых обращений к `random.*`. Side-эффектов нет.
- **`tests/`** — 35 новых тестов.
  - `tests/unit/domain/balance/test_config.py`: 19 новых кейсов на `ForestRarityWeights` / `ForestDropConfig` / `ItemEntry` / items_catalog (size, duplicate ids, missing rarity) / names_catalog (size, empty, whitespace, duplicate). Все существующие forest-кейсы дополнены валидным `_VALID_DROP_PAYLOAD`.
  - `tests/unit/domain/forest/test_entities.py`: 8 кейсов на frozen-инвариант + полное покрытие pattern-match по ADT `Drop`.
  - `tests/unit/domain/forest/test_services.py`: 11 кейсов на `compute_forest_outcome`. Использует локальный `ScriptedRandom` (FIFO-очереди по каждому методу `IRandom`) для покапилярных проверок — какая ветка / длина / дроп. Стресс-сэмплинг 5 000 прогонов на `FakeRandom(seed=12345)` проверяет инварианты (длина в `[branch.min, branch.max]`, item.id принадлежит каталогу, name — каталогу). Smoke на реальном `config/balance.yaml` отдельным тестом.
  - `tests/unit/domain/balance/factories.py::valid_balance_payload` — теперь генерирует валидный 30-предметный каталог (5 на каждый слот, по паттерну `common/common/rare/rare/epic` = 12/12/6) и `[ИмяТест-01..30]`.

Результат / артефакты:
- `config/balance.yaml` (расширен на ~120 строк).
- `src/pipirik_wars/domain/forest/` (4 файла, ~150 LoC чистого домена).
- `src/pipirik_wars/domain/balance/config.py` (+ Slot/Rarity/ItemEntry/ForestDropConfig/ForestRarityWeights + 2 model_validator).
- `src/pipirik_wars/domain/balance/__init__.py` — обновлён публичный экспорт.
- `tests/unit/domain/balance/test_config.py` + `tests/unit/domain/balance/factories.py` — обновлены под новый schema.
- `tests/unit/domain/forest/test_entities.py` + `tests/unit/domain/forest/test_services.py` — новые.
- Локальный `make ci`: lint / typecheck / imports / 610 тестов, покрытие **97.52 %**.

Заметки / решения:
- **Slot/Rarity в `domain/balance/config.py`, а не в `domain/forest/`**. Изначально хотелось хранить их рядом с forest-сущностями, но `domain/balance/config.py` импортирует их в `ItemEntry`, а `domain/forest/services.py` импортирует `BalanceConfig` — получался цикл. Перенос Slot/Rarity в balance/config.py — правильный также архитектурно: ими типизирован сам каталог. `domain/forest/entities.py` реэкспортирует их для удобного `from pipirik_wars.domain.forest import Slot`.
- **`probability_percent`, а не `probability` (float)**. Целое число `[0, 100]` устойчивее к 0-tolerance багам с 0.01 при правках админ-панелью + удобнее раздавать пользователям («50 %», «5 %»).
- **`ScriptedRandom`, а не `MagicMock(side_effect=...)`**. FIFO-очереди по каждому методу `IRandom` дают тесту явный список значений: видно, что именно проверяется, и при добавлении нового `randint` в `compute_forest_outcome` ScriptedRandom падает с осмысленным `IndexError`/`AssertionError`, а не молчаливо подставляет `None`.
- **Никаких side-эффектов в `compute_forest_outcome`** — это домен. Применение исхода (запись в `forest_runs`, начисление длины, добавление в инвентарь, смена имени, аудит) уйдёт в `application/forest/finish_run.py` в Спринте 1.3.C. Так удержим domain покрытым 100 % unit-тестами без БД.
- **`NoDrop` — пустой frozen-dataclass, а не `None`**. Pattern-match на `Drop = NoDrop | ItemDrop | NameDrop` короче и устойчивее к будущему расширению (например, гипотетический `BonusDrop` для горы — без ломки сигнатур).
- **Поле `branch.length_cm` дублирует `ForestRunOutcome.length_cm`** — намеренно. У ветки в проде будет своя «история» (для аудита: какой именно был broadcasted к игроку диапазон). Сейчас это просто синоним, но, чтобы не переписывать сигнатуры в 1.3.C, оставили оба.
- **Покрытие на 30 предметов / 30 имён** — это нижний порог из ПД. Реальный YAML уже идёт с 30 предметами и 32 именами, чтобы было пространство добавить пару тематических без правки тестов.

---

## 2026-05-04 — Спринт 1.2.D: алёрт админу при достижении 80 % от `MAX_DAU`

**Автор:** Devin (по запросу birgit865)
**Тип:** feature (domain + application + infrastructure)
**Связано:** Текущий PR (Спринт 1.2.D), [development_plan.md §3 / Спринт 1.2, задача 1.2.7](development_plan.md), [current_tasks.md Спринт 1.2 → 1.2.D](current_tasks.md), завершает Спринт 1.2 после PR #13/14/15.

Финальный PR Спринта 1.2 — алёртинг по DAU. Когда суммарный DAU дошёл до 80 % от `MAX_DAU`, system один раз в сутки пишет audit-запись и structlog-warning, чтобы у админов было время заранее повысить лимит/докинуть мощности до того, как игроки начнут попадать в очередь регистраций.

Что сделано:
- **`domain/dau/`** — добавлен новый порт.
  - `ports.py::IDauThresholdAlerter` — абстрактный эмиттер алёрта (`emit(*, current_dau, max_dau, percent, occurred_at)`). Идемпотентность «1 раз в сутки» в порт **не** заложена: его задача — отправить событие. За «слать или нет» отвечает use-case через `IIdempotencyKey`. Это даст потом без правки `CheckDauThreshold` подключить второй адаптер (например, Telegram-уведомление админам или Slack) и собрать `CompositeDauThresholdAlerter`.
  - `shared/ports/audit.py::AuditAction.DAU_THRESHOLD_REACHED` — новое значение, чтобы фильтровать алёрты в audit-логе.
- **`infrastructure/dau/alert.py::StructlogDauThresholdAlerter`** — реализация поверх `structlog.get_logger("pipirik_wars.dau.threshold").warning("dau.threshold.reached", ...)`. Полей четыре: `current_dau`, `max_dau`, `percent`, `occurred_at` (ISO-строка). Stdout/JSON-формат настраивается на уровне приложения (в `bot/main.py` уже сконфигурирован).
- **`application/dau/check_threshold.py::CheckDauThreshold`** — новый use-case (use-case-name выбран синхронным с остальной кодовой базой).
  - Константы: `DAU_THRESHOLD_PERCENT = 80`, `DAU_THRESHOLD_NAMESPACE = "dau_threshold_alert"`.
  - Проверка порога — целочисленная: `5 * current >= 4 * max_dau` (без float-погрешностей; для `max_dau = 1` алёрт сработает на первом игроке, что соответствует семантике «80 % исчерпано»).
  - Алгоритм: `current = dau_counter.current()` → если ниже порога → `triggered=False` без транзакции. Иначе строится idempotency-ключ `dau_threshold_alert:{moscow_date}`, открывается UoW, проверяется `idempotency.is_seen(key)` — если уже видели сегодня, `triggered=False`. Иначе `idempotency.mark(key)` + `audit.write(AuditAction.DAU_THRESHOLD_REACHED, target_kind="dau", target_id=moscow_date.isoformat(), after={current_dau, max_dau, percent}, idempotency_key=key)` → коммит → **после коммита** `alerter.emit(...)`. Эмит вне транзакции, чтобы откат не оставлял после себя «висячих» алёртов.
  - Дата привязана к `clock.moscow_date()` — той же, что использует `IDauCounter` для ежедневного сброса.
- **Точки вызова** — `CheckDauThreshold.execute()` дёргается **после** `dau_counter.record_active(...)`:
  - `application/player/register.py::RegisterPlayer` — после успешной регистрации (только в активной ветке, не в `PlayerQueued`).
  - `application/signup_queue/promote.py::PromoteFromQueue` — после loop-а промоута, если хоть кто-то поднят (`if promoted: await check_threshold.execute()`).
- **`bot/main.py::Container`** — расширен `dau_threshold_alerter: IDauThresholdAlerter` и `check_dau_threshold: CheckDauThreshold`. В `build_container()` алертер собирается до прочих use-case-ов, чтобы прокинуть его в `RegisterPlayer` и `PromoteFromQueue`.
- **`tests/fakes/dau.py`** — `FakeDauThresholdAlerter` (накапливает `events: list[DauAlertEvent]`).

Тесты (новые):
- **Application (19)**: `_is_threshold_reached` — таблица из 11 параметризованных кейсов (включая граничные `4/5`, `4/6`, `5/6`, `1/1`); `CheckDauThreshold` — ниже порога (без транзакции и аудита), первое пересечение (audit + commit + alerter), второй вызов того же дня (no-op, но UoW открывается на `is_seen`), переход через сутки (новый ключ → новый алёрт), `MAX=1` (алёрт на первом игроке), pre-seeded ключ (idempotency пропускает алёрт), `current > max_dau` (overshoot — алёрт всё равно ровно один).
- **Application — `RegisterPlayer` (4 новых)**: алёрт после регистрации, пересекающей 80 %; нет алёрта при низкой загрузке; нет алёрта, когда игрок ушёл в очередь; ровно 1 алёрт за сутки даже при подряд идущих регистрациях после порога.
- **Application — `PromoteFromQueue` (3 новых)**: алёрт срабатывает, когда промоут довёл DAU до ≥ 80 %; без промоута alerter не зовётся; при низкой загрузке нет алёрта.
- **Infrastructure (2)**: `StructlogDauThresholdAlerter` — `structlog.testing.LogCapture` ловит warning-событие со всеми полями; default-logger используется при отсутствии явного.
- **Composition root**: добавлены проверки на `dau_threshold_alerter`/`check_dau_threshold` в обеих вариантах (фейковый Container и `build_container()` с реальным `StructlogDauThresholdAlerter`).
- Все существующие тесты `RegisterPlayer` / `PromoteFromQueue` / `JoinClan` / composition-root приведены к новой сигнатуре конструкторов (через общий `_build`-helper, использующий `FakeDauThresholdAlerter`).

Контракты `import-linter` не нарушены: `application` не импортирует `structlog`, доступ к нему — только через `IDauThresholdAlerter`.

CI: `make ci` локально проходит — ruff (lint+format), mypy --strict, pytest с покрытием 97.40 % (565 тестов), import-linter (3/3 контракта), pip-audit отдельным шагом в CI workflow.

---

## 2026-05-04 — Спринт 1.2.C: `signup_queue` + DAU Gate в `RegisterPlayer` + auto-promote

**Автор:** Devin (по запросу birgit865)
**Тип:** feature (domain + application + infrastructure + bot)
**Связано:** Текущий PR (Спринт 1.2.C), [development_plan.md §3 / Спринт 1.2, задачи 1.2.4 / 1.2.5](development_plan.md), [current_tasks.md Спринт 1.2 → 1.2.C](current_tasks.md), предшествуют — PR #13 (1.2.A) и PR #14 (1.2.B).

Третий PR Спринта 1.2 — закрытие FIFO-очереди регистраций для случая «DAU достиг MAX_DAU». До этого PR попытка `/start` при заполненном лимите просто возвращала ошибку; теперь игрок ставится в очередь, а при повышении `MAX_DAU` через `/set_max_dau` система сама поднимает первых из очереди обратно в активные.

Что сделано:
- **`domain/signup_queue/`** — новый под-домен.
  - `entities.py::SignupQueueEntry` — frozen+slots dataclass (`id`, `tg_id`, `username`, `locale`, `position`, `enqueued_at`).
  - `entities.py::SignupQueueStatus` — `WAITING` / `PROMOTED` (на текущий момент колонкой не сохраняется, оставлен для будущих расширений).
  - `errors.py::SignupQueueError` (база) + `AlreadyQueuedError(tg_id=...)` (наследник `DomainError`).
  - `ports.py::ISignupQueueRepository` — 4 метода: `enqueue` (бросает `AlreadyQueuedError` на дубль), `get_by_tg_id`, `size`, `pop_front(limit)`.
- **`infrastructure/db/`** — реализация порта.
  - Новая alembic-миграция `0003_signup_queue` — таблица `signup_queue` (BIGINT autoincrement `id`, UNIQUE `tg_id`, индекс на `enqueued_at`, поля `username VARCHAR(32)`, `locale VARCHAR(16)`).
  - `infrastructure/db/models/signup_queue.py::SignupQueueORM` — ORM в едином стиле с другими (`Base.metadata`, `Mapped[…]`, `_AutoIncBigInt` для портабельности SQLite ↔ Postgres).
  - `infrastructure/db/repositories/signup_queue.py::SqlAlchemySignupQueueRepository` — реализация. Ключевые решения:
    - `position` **не хранится в таблице**: считается «на лету» (`COUNT(*) WHERE enqueued_at < x` + tie-break `tg_id < y`), чтобы избежать O(N)-обновлений при `pop_front`. Это держит таблицу маленькой и не плодит конкурирующие UPDATE-ы.
    - `enqueue` ловит `IntegrityError` от UNIQUE-нарушения и преобразует в доменный `AlreadyQueuedError` — слой выше не знает про SQL.
    - `pop_front(limit)` — ORDER BY `enqueued_at, id` + DELETE WHERE `id IN (...)` за одну операцию.
- **`application/signup_queue/`** — use-case для авто-разблокировки.
  - `application/signup_queue/promote.py::PromoteFromQueue` — поднимает первых из очереди на освободившиеся места: `slots = max(0, MAX_DAU - DAU)` → `pop_front(limit=slots)` → для каждого вызывает `players.add(...)` (с обработкой `PlayerAlreadyRegisteredError` → `skipped_already_registered`) → пишет audit-запись `PLAYER_PROMOTED` с `idempotency_key="promote_player:{tg_id}"` и `before={'queued_at', 'queued_position'}` → вне транзакции вызывает `dau_counter.record_active(...)`.
  - DTO `PromoteFromQueueResult` (`promoted: tuple[Player, ...]`, `skipped_already_registered: tuple[int, ...]`, `available_slots: int`).
- **`application/player/register.py::RegisterPlayer`** — расширен DAU-гейтом.
  - Перед добавлением игрока проверяет `current_dau >= max_dau`. Если да — ставит в `signup_queue` и возвращает `PlayerQueued(entry=...)`. Если нет — обычная ветка с `PlayerRegistered(player=...)`. Тип результата — union `PlayerRegistered | PlayerQueued`.
  - Ошибка `AlreadyQueuedError` пробрасывается наружу (handler покажет дружелюбное сообщение).
  - `idempotency_key` для запроса в очередь — `queue_player:{tg_id}`.
- **`bot/handlers/admin.py`** — два изменения.
  - `handle_admin_stats` теперь принимает `signup_queue: ISignupQueueRepository` и в ответе показывает `«Очередь регистраций: N»`.
  - `handle_set_max_dau` теперь принимает `promote_from_queue: PromoteFromQueue`. После успешного `set_max_dau.execute(...)` он вызывает `promote_from_queue.execute()` **только** если `result.changed and result.new_max_dau > result.previous_max_dau` (повышение). При понижении или равенстве промоут не запускается. Если кто-то поднят — в ответе появляется строка `«↑ Из очереди поднято: N»`.
- **`bot/main.py::Container`** — расширен `signup_queue: ISignupQueueRepository` и `promote_from_queue: PromoteFromQueue`. В `build_container()`: `signup_queue = SqlAlchemySignupQueueRepository(uow)`, `promote_from_queue` собирается из uow + players + signup_queue + dau_counter + dau_limit + audit + clock. В `build_dispatcher()`: workflow-data DI обоих в роутер.
- **`tests/fakes/signup_queue.py::FakeSignupQueueRepository`** — in-memory FIFO с автонумерацией `id` и пересчётом `position` при `pop_front`.

Тесты (новые):
- **Domain (12)**: `SignupQueueEntry` — frozen, slots, optional-поля, эквивалентность; `AlreadyQueuedError` — наследование, `tg_id`, формат `str()`.
- **Application `PromoteFromQueue` (9)**: пустая очередь / нулевые слоты, частичный/полный slot range, audit-записи с idempotency-ключами `promote_player:*`, `before` содержит `queued_position`, propagate `PlayerAlreadyRegisteredError` в `skipped_already_registered`, корректный rollback uow при неожиданной ошибке репо.
- **Integration `SqlAlchemySignupQueueRepository` (11)**: enqueue → id + position=1, последовательные позиции, AlreadyQueuedError, защита от pre-set id, get_by_tg_id с актуальной позицией, size, pop_front(0/-N) — no-op, FIFO ordering, drain, повторная постановка после pop_front, tie-break по `tg_id` при равном `enqueued_at`.
- **Bot handler `test_admin.py`**: добавлен тест-кейс для отображения непустой очереди в `/admin_stats`; для `/set_max_dau` — три новых кейса (нулевая очередь → промоут вызывается, но строки нет; повышение с непустой очередью → строка «↑ Из очереди поднято: N»; понижение → промоут НЕ вызывается).
- **Migrations**: новый тест `test_0003_descends_from_0002` + `signup_queue` добавлен в expected-таблицы и в whitelist файлов миграций.

Результат:
- Полный `make ci` зелёный (lint + format + mypy --strict + import-linter + 537 тестов с покрытием 97.35 %).
- DAU Gate работает в полном цикле: переполнение → постановка в очередь → `/admin_stats` показывает текущую очередь → админ повышает `MAX_DAU` → автопромоут первых N в активные игроки.

Заметки / решения:
- **Почему не storage-side `position`:** хранение `position` колонкой требовало бы O(N) UPDATE при каждом `pop_front`. Поскольку запросы «сколько передо мной» относительно редки (только в ответе пользователю «вы №X»), дешевле считать через `COUNT(*)`.
- **Почему промоут только при повышении:** понижение `MAX_DAU` — административное «закрытие двери», очередь должна оставаться нетронутой, а текущие игроки — продолжать играть. Равенство — no-op.
- **Tie-break в `_position_of`:** при одинаковом `enqueued_at` (теоретически возможно при «массовом наплыве в одну миллисекунду») мы добиваем порядок сравнением по `tg_id`, чтобы исключить коллизию «два первых места».

---

## 2026-05-04 — Спринт 1.1.E: `/profile` + `/balance_reload`

**Автор:** Devin (по запросу jorey7467)
**Тип:** feature (domain + application + bot)
**Связано:** PR #12, [development_plan.md §3 / Спринт 1.1, задачи 1.1.8 / 1.1.9](development_plan.md), [current_tasks.md Спринт 1.1 → 1.1.E](current_tasks.md), предшествуют — PR #8/#9/#10/#11 (1.1.A–D).

Финальный PR серии Спринта 1.1: закрывает «карточку игрока» (read-side) и инструмент геймдиза «hot-reload `display_names`» (write-side). После этого PR Спринт 1.1 закрыт целиком — следующий заход (Спринт 1.2) уже про экономику и DAU Gate.

Что сделано:
- **`domain/balance/ports.py::IBalanceReloader`** — отдельный порт для `reload()` (по ISP отделён от `IBalanceConfig.get()`). `YamlBalanceLoader` теперь реализует **оба** интерфейса. В DI это один и тот же объект, но use-case-ам разрешено зависеть только от того подмножества capabilities, которое им реально нужно: `GetProfile` берёт только `IBalanceConfig`, `ReloadBalance` — оба.
- **`domain/shared/ports/audit.py::AuditAction.BALANCE_RELOAD`** — новый action для аудита `/balance_reload`.
- **`application/player/get_profile.py::GetProfile`** — use-case-обёртка вокруг `IPlayerRepository.get_by_tg_id(...)` + `IBalanceConfig.display_name_for(length_cm)`. Возвращает `ProfileView | None`. Транзакция читающая (commit без записи), `None` для незарегистрированного — handler сам решит, что показать.
- **`application/balance/reload.py::ReloadBalance`** — use-case с гейтом `Admin.can_write_balance()` (`super_admin` / `economist`). При отказе бросает `AuthorizationError` ДО вызова `reloader.reload()` — никаких side-эффектов на неавторизованных. Аудит `BALANCE_RELOAD` пишется только после успешного reload, с `before={'version': N}` / `after={'version': M}` и `idempotency_key="balance_reload:{tg_id}:{ts}"`.
- **`bot/presenters/profile.py`** — чистые функции `render_full_nick(...)` и `render_profile_card(...)`. Формат ника по ГДД §2.1 — «`Титул Название Имя`», `None`-поля просто пропускаются (новичок без титула/имени → ровно «Пипирик»). Карточка по §2.2: `🏷 ник` / `📏 длина` / `📐 толщина` / `🎽 экипировка` (последняя — пока заглушка «пока пусто», в Спринте 1.3 добавим реальные слоты). Локализация `Title` живёт в `_TITLE_RU` — добавление нового члена `Title` без правки маппинга роняет тест `test_only_known_titles_supported`.
- **`bot/handlers/profile.py::handle_profile`** — `/profile`. Только `chat_kind == "private"` → `GetProfile` → presenter. Группа/супергруппа → инструкция «зайди в ЛС». Канал/прочие → нейтральный fallback. Без `tg_identity` (теоретически невозможно) — тоже fallback.
- **`bot/handlers/admin.py::handle_balance_reload`** — `/balance_reload`. Только в private. Ловит `AuthorizationError` → `«⛔️ только админам»`, `ConfigError` → `«❌ некорректный YAML»`. Успех → `«✅ перечитан (v1 → v2)»` или `«✅ … версия не изменилась»`, если файл не правили.
- **`bot/main.py::Container`** — расширен 4 полями: `balance_reloader`, `admins`, `get_profile`, `reload_balance`. В `build_container()`: `admins = SqlAlchemyAdminRepository(uow)`, оба порта баланса инжектятся одним и тем же `YamlBalanceLoader`. В `build_dispatcher()`: workflow-data DI для двух новых use-case-ов.
- **`tests/fakes/admin_repo.py::FakeAdminRepository`** — in-memory `IAdminRepository` с `seed(...)` и `deactivate(...)` для удобного arrange. `FakeBalanceConfig` теперь реализует и `IBalanceConfig`, и `IBalanceReloader` — паритет с `YamlBalanceLoader` в production. Метод `queue_next_reload(snapshot)` позволяет имитировать «после reload-а — другой YAML».

Тесты (45 новых):
- **Presenter**: 8 кейсов (`render_full_nick` ×4 для всех сочетаний title/name + три инвариантных + один на `_TITLE_RU` coverage) + 3 на `render_profile_card`.
- **`GetProfile`**: 4 кейса — найден / не найден / полный игрок / hot-reload меняет название.
- **`ReloadBalance`**: 10 кейсов — авторизация (super_admin ✅, economist ✅, неизвестный ❌, support ❌, read_only ❌, деактивированный ❌) + reload (аудит-запись с версиями, без изменения версии, `ConfigError` пропагируется без аудита).
- **Handler `/profile`**: 6 кейсов — private+зарегистрирован (вызов use-case + правильный текст), private+не зарегистрирован, group, supergroup, channel, без identity.
- **Handler `/balance_reload`**: 6 кейсов — успех с версиями, успех без изменений, AuthorizationError → friendly text, ConfigError → friendly text, group → не вызывается use-case, без identity → не вызывается.
- **Integration на `YamlBalanceLoader`**: новый `test_display_name_for_same_length_changes_after_reload` — пишем YAML v1, читаем, меняем YAML на v2, `loader.reload()`, и проверяем `display_name_for(15)` = новое название. Старый снимок остаётся валидным (immutability).
- **Composition root**: расширены ассерты — все 4 новые поля Container присутствуют в обоих режимах (фейк и реальный), `c.balance_reloader is c.balance` (DI-инвариант), оба новых router-а (`profile`, `admin`) подключены, оба use-case-а в workflow-data.

Метрики:
- **411 тестов** (+45 к 1.1.D), **96.88 %** покрытия. Локальный `make ci` зелёный, GitHub Actions матрица 3.11/3.12 — зелёная.
- **27 файлов изменено**, +1608 / −27 строк.

Заметки / решения:
1. **ISP по `IBalanceConfig` / `IBalanceReloader`.** В production `YamlBalanceLoader` — один объект, реализующий обе capabilities. Но в use-case-ах **зависимость от `IBalanceReloader` — это уже capability «писать»**, и она нужна одному use-case (`ReloadBalance`). Все остальные (`GetProfile` сейчас, `ForestService` в 1.3, `OracleService` в 1.4) зависят только от read-side. Это позволяет в тестах «писательских» use-case-ов мокать reload отдельно, не тащась через файловую систему, и оставляет архитектурный signal: «hot-reload — административная операция, не часть нормального workflow».
2. **Authorization до reload.** Альтернатива «сначала reload, потом проверка прав» хуже: пробрасывает side-эффект в неуполномоченного актора. `ReloadBalance` сначала зовёт `IAdminRepository.get_by_tg_id(tg_id)` + `Admin.can_write_balance()`, и только при `True` вызывает `reloader.reload()`. Аудит — после reload (нет state change → нет записи).
3. **Презентер — чистые функции, не классы.** `bot/presenters/profile.py` намеренно без классов: ввод/выход явные, нет состояния, юнит-тестирование тривиальное (`assert render_X(...) == "..."`). Локализация `Title.NEWBIE → "Новичок"` хранится в module-level `_TITLE_RU` — когда добавится Title.SCOUT/SAGE/etc, тест `test_only_known_titles_supported` упадёт и напомнит локализовать.
4. **Карточка в Спринте 1.1.E без слотов экипировки.** ГДД §2.2 описывает 6 слотов экипировки, но самих предметов нет до Спринта 1.3 (дроп из леса). Поэтому секция «🎽 Экипировка» в карточке — стабильный заголовок и плейсхолдер «пока пусто». Это **не** TODO в коде — это намеренный stub, который заменится в 1.3.5 без изменения сигнатур handler/presenter.
5. **Hot-reload — атомарный.** `loader.reload()` сначала **полностью** парсит и валидирует новый YAML; только после успешной валидации меняет `_snapshot`. При `ConfigError` старый снимок сохраняется. Тест `test_invalid_yaml_propagates_config_error_no_audit` фиксирует это поведение.

---

## 2026-05-04 — Спринт 1.1.D: use-case-ы + handler-ы регистрации игрока и клана

**Автор:** Devin (по запросу 612amaranth)
**Тип:** feature (application + bot)
**Связано:** PR #11 (TBD), [development_plan.md §3 / Спринт 1.1, задачи 1.1.3 / 1.1.4 / 1.1.5 / 1.1.6](development_plan.md), [current_tasks.md Спринт 1.1 → 1.1.D](current_tasks.md), предшествуют — PR #8 (1.1.A domain), PR #9 (1.1.B db+repos), PR #10 (1.1.C aiogram).

Четвёртый PR серии Спринта 1.1: до этого `/start` отвечал в чате, но **никаких сущностей** в БД не создавал. Теперь handler-ы реально дёргают use-case-ы, а use-case-ы — пишут в БД и аудит. Это первый «живой» цикл пользовательских взаимодействий: «`/start` в ЛС → запись в `users`», «бота добавили в группу → запись в `clans`», «игрок зашёл в чат-клан → запись в `clan_members`».

Что сделано:
- **`application/player/register.py`** — `RegisterPlayer(uow, players, audit, clock).execute(input_dto)` — создаёт игрока со стартерами по ГДД §1.1 (`length=2cm`, `thickness=1`, `title=None`, `name=None`), пишет audit `PLAYER_REGISTER` с `idempotency_key="register_player:{tg_id}"`. Если игрок уже зарегистрирован — `PlayerAlreadyRegisteredError` пробрасывается дальше (handler ловит).
- **`application/clan/register.py`** — `RegisterClan` с тремя ветвями: `created` (новый клан + audit `CLAN_REGISTER`), `unfrozen` (бот вернулся в чат, который ранее замораживали — клан расконсервируется и audit `CLAN_UNFREEZE`), `already_active` (no-op без аудита, идемпотентно).
- **`application/clan/migrate.py`** — `MigrateClanChatId` для группы → супергруппы. Идемпотентен: `migrated` (есть старый id), `already_migrated` (старого нет, но новый — есть; либо вызвали с одинаковым id), `not_found` (бросает `ClanNotFoundError`). Сохраняет внутренний `id` клана при переходе.
- **`application/clan/join.py`** — `JoinClan` для чат-апдейтов. Три исхода: `joined` (новый членский запрос + audit `CLAN_MEMBER_JOIN`), `already_member` (no-op без аудита), `not_registered` (игрока нет в `users` — handler шлёт DM-инструкцию). Респектирует БД-инвариант UNIQUE(player_id) (один игрок ↔ один клан).
- **`application/clan/freeze.py`** — `FreezeClan` для бот-`left/kicked`. `frozen` (audit `CLAN_FREEZE` с `before/after`/`reason`), `already_frozen` (idempotent), `not_found` (тихо возвращает outcome — бот мог быть удалён до регистрации).
- **`bot/handlers/start.py`** — переписан под use-case `RegisterPlayer`. В ЛС зовёт `register_player.execute(...)`, ловит `PlayerAlreadyRegisteredError` → разные тексты «зарегистрированы»/«уже зарегистрированы». В группе/супергруппе — текст-инструкция «напишите в ЛС». Прочие типы — нейтральный fallback.
- **`bot/handlers/registration.py`** — три новых handler-а: `my_chat_member` (бот добавлен → `RegisterClan`; бот удалён → `FreezeClan`; пропускает private), `chat_member` (не-бот зашёл в группу/супергруппу → `JoinClan`; outcome=`not_registered` → `bot.send_message(chat_id=user.id, text=JOIN_NOT_REGISTERED_RU)`), `migrate_to_chat_id` на `Message`-апдейте (group→supergroup → `MigrateClanChatId`).
- **`bot/main.py`** — `Container` расширен 3 репозиториями (`players/clans/clan_members`) и 5 use-case-ами (`register_player/register_clan/migrate_clan/join_clan/freeze_clan`). `build_container()` инстанцирует SQLAlchemy-репо и use-case-ы. `build_dispatcher()` прокидывает все 5 use-case-ов в `dispatcher["..."]` — это аналог DI через aiogram workflow-data, handler-ы получают их по имени параметра.
- **`bot/main.py::run()`** — добавлен `_ALLOWED_UPDATES = ("message", "callback_query", "my_chat_member", "chat_member")` и передаётся в `start_polling(allowed_updates=...)`. По умолчанию aiogram **не** запрашивает `chat_member` — без явного списка JoinClan не будет триггериться.
- **`application/dto/inputs.py`** — добавлены `MigrateClanChatIdInput / JoinClanInput / FreezeClanInput`, в `RegisterClanInput` теперь обязательное поле `chat_kind: Literal["group", "supergroup"]`. Валидация через pydantic-strict (extra=forbid, нелитеральные значения отклоняются).
- **`domain/shared/ports/audit.py::AuditAction`** — добавлены 4 enum-а: `PLAYER_REGISTER`, `CLAN_REGISTER`, `CLAN_MIGRATE`, `CLAN_MEMBER_JOIN` (всё ещё в порядке возрастания «энтропии»: ADMIN_COMMAND по-прежнему последний).

Тесты:
- **Unit (use-cases, fakes)**: 16 новых тестов — `test_register_player.py`, `test_register_clan.py`, `test_migrate_clan.py`, `test_join_clan.py`, `test_freeze_clan.py`. Используют `FakeUnitOfWork / FakeAuditLogger / FakeClock` + новые `FakePlayerRepository / FakeClanRepository / FakeClanMembershipRepository`. Покрывают все исходы (created/unfrozen/already_active/migrated/already_migrated/joined/already_member/not_registered/frozen/already_frozen/not_found) + аудит-инварианты + ГДД §4 «один игрок — один клан».
- **Unit (handlers)**: 12 новых тестов — `test_registration.py`. Моки aiogram-апдейтов, проверка корректного маппинга на DTO-input-ы, ветвление по `chat_type`/`new_status`/`is_bot`. `test_start.py` переписан под новую сигнатуру (`register_player` вместо `_reply_text_for`).
- **Composition root**: тесты `test_composition_root.py` обновлены — Container теперь требует 8 новых полей, `build_dispatcher()` проверен на наличие 5 use-case-ов в workflow-data.
- **Итого:** 373 теста (было 341), покрытие 96.56%, все 3 import-linter-контракта на месте.

Результат / артефакты:
- Use-cases: `src/pipirik_wars/application/player/register.py`, `src/pipirik_wars/application/clan/{register,migrate,join,freeze}.py`.
- Handlers: `src/pipirik_wars/bot/handlers/{start,registration}.py`.
- Composition root: `src/pipirik_wars/bot/main.py`.
- DTO/audit: `src/pipirik_wars/application/dto/inputs.py`, `src/pipirik_wars/domain/shared/ports/audit.py`.
- Тесты: `tests/unit/application/{player,clan}/`, `tests/unit/bot/handlers/test_registration.py`.
- Fakes: `tests/fakes/{player_repo,clan_repo}.py`.

Заметки / решения:
- **Workflow-data DI**: использован idiom aiogram — `dispatcher["register_player"] = container.register_player`. aiogram автоматически прокидывает значение в handler по имени параметра (`async def handle_start(..., register_player: RegisterPlayer)`). Без глобального state, без factory-pattern на каждом апдейте.
- **`allowed_updates`**: явный список — критично. По умолчанию aiogram не подписан на `chat_member`, и `JoinClan` не сработал бы. Это был бы тихий баг, легко не заметить в QA.
- **Идемпотентность по умолчанию**: все 5 use-case-ов «толерантны» к повторам (созданный → no-op, удалённый → no-op-not-found, замороженный → no-op-already-frozen и т.д.). Это нужно для устойчивости в условиях «лагающих» апдейтов от Telegram-а и потенциальных ретраев.
- **БД-инвариант UNIQUE(player_id)**: `JoinClan` опирается на DB-уровень, fake-репозиторий тоже его моделирует, чтобы тесты ловили нарушение ГДД §4 раньше боевого CHECK-constraint-а.
- **Routers — singleton-ы**: `start_router` и `registration_router` создаются на уровне модуля и не могут быть переиспользованы между Dispatcher-ами. Поэтому в `test_composition_root.py` теперь только **один** тест с `build_dispatcher()` (раньше было 2).
- **Migration handler**: `migrate_to_chat_id` приходит **до** `my_chat_member` от Telegram-а при group→supergroup. Если поменять порядок — будет дубликат регистрации. Логика обрабатывает оба порядка через идемпотентные исходы.

---

## 2026-05-04 — Спринт 1.1.C: aiogram 3.x bootstrap (dispatcher + middleware-стек + `/start` stub)

**Автор:** Devin (по запросу 612amaranth)
**Тип:** feature (bot / scaffold)
**Связано:** PR #N (TBD), [development_plan.md §3 / Спринт 1.1, задача 1.1.1](development_plan.md), [current_tasks.md Спринт 1.1 → 1.1.C](current_tasks.md), предшествуют — PR #8 (1.1.A domain), PR #9 (1.1.B db+repos)

Третий PR серии Спринта 1.1: первый «живой» bot-слой. До этого `bot/main.py:main()` был `NotImplementedError`-stub-ом; теперь — реальный entry-point поллинга с aiogram 3.x, middleware-стеком и `/start`-handler-ом, отвечающим во всех трёх типах чатов (acceptance criteria 1.1.1).

Что сделано:
- **Зависимость:** `aiogram>=3.13,<4` добавлена в runtime-deps `pyproject.toml`. Притянулись транзитивно `aiohttp / aiofiles / magic-filter / pydantic-core 2.41` (последний — апгрейд, прошёл совместимо).
- **`infrastructure/settings/settings.py`** — новая под-секция `BotSettings` с полями: `token: SecretStr` (env `BOT_TOKEN`, плейсхолдер по умолчанию), `default_throttle_per_second: float = 5.0`, `default_throttle_capacity: int = 10`. Притянута в корневой `Settings` как `bot: BotSettings`. Devin Secret для production: `PIPIRIK_BOT_TOKEN` (`save_scope: org`).
- **`bot/middlewares/auth.py`** — `AuthMiddleware` извлекает Telegram-идентичность из апдейта (`Message`, `CallbackQuery`, `ChatMemberUpdated`) в неизменяемый `TgIdentity(tg_user_id, chat_id, chat_kind, language_code)` и кладёт в `data["tg_identity"]`. Если апдейт без user-а (например, сервисное `my_chat_member` без инициатора) — пишем `None`, не падаем. **Не делает проверку прав** — это работа `requires_*`-декораторов из `application.auth` (Спринт 0.2.5).
- **`bot/middlewares/locale.py`** — `LocaleMiddleware` пока всегда выставляет `data["locale"] = "ru"`. Telegram-овский `language_code` сохраняется в `data["telegram_language_code"]` для будущего i18n-пайплайна (fluent — Фаза 2). Зарезервирован, чтобы handler-ы не «прибивали» язык по месту.
- **`bot/middlewares/throttle.py`** — `ThrottleMiddleware(IRateLimiter)`. Ключ бакета `f"{tg_user_id}:{chat_id}"` — лимит на пару (пользователь × чат). На `try_acquire()=False` для `Message` отвечает «⏳ Слишком быстро…», для прочих апдейтов молча проглатывает. Без `tg_identity` (системные апдейты) — пропускает throttle вовсе.
- **`bot/middlewares/error_handler.py`** — `ErrorHandlerMiddleware`, последний рубеж. `DomainError` превращает в дружелюбное сообщение пользователю (`❌ {message}`), **не пробрасывает дальше** (это «ожидаемая» ошибка). Любое другое исключение логирует через `structlog` (`unexpected_handler_error`) с traceback-ом, отвечает пользователю «⚠️ Что-то пошло не так…», и **прокидывает** дальше — пусть видит aiogram/observability.
- **`bot/middlewares/__init__.py::register_middlewares()`** — регистрирует все 4 middleware-а в порядке `error → auth → locale → throttle` на трёх observer-ах: `dp.message`, `dp.callback_query`, `dp.my_chat_member` (последний — для регистрации клана через `bot_added_to_chat` в 1.1.D).
- **`bot/handlers/start.py`** — `Router(name="start")` с `@router.message(CommandStart())`. Handler `handle_start(message, tg_identity)` вычисляет ответ через чистую функцию `_reply_text_for(chat_kind)` — три варианта текста (private / group+supergroup / channel-fallback). Pытается читать `tg_identity.chat_kind`, но если его нет — fallback на `message.chat.type` (страховка для апдейтов без `from_user`).
- **`bot/main.py`**:
  - `Container` теперь содержит `rate_limiter: IRateLimiter` (нужен `ThrottleMiddleware`).
  - `build_container()` собирает `InMemoryTokenBucketRateLimiter` поверх `RealClock` с параметрами из `settings.bot.default_throttle_*`.
  - Новая функция `build_dispatcher(container) -> Dispatcher` — собирает `Dispatcher`, регистрирует middleware-стек и роутеры.
  - `run()` — реальный entry-point: создаёт `Bot` с `parse_mode="HTML"`, поднимает long-polling, корректно закрывает сессию в `finally`.
  - `main()` теперь — sync-обёртка `asyncio.run(run())`, не `NotImplementedError`.

Тесты:
- 31 новый тест:
  - `tests/unit/bot/middlewares/test_auth.py` (6 тестов): извлечение из `Message`, `Message` без user-а, `CallbackQuery`, callback без msg/user, `ChatMemberUpdated`, неизвестный тип события.
  - `tests/unit/bot/middlewares/test_locale.py` (2 теста): дефолт `"ru"` + сохранение `tg_lang`, отсутствие identity не ломает.
  - `tests/unit/bot/middlewares/test_throttle.py` (4 теста): пропуск при acquire, ответ «слишком быстро» при reject для `Message`, тихий drop для не-`Message`, отсутствие identity → пропуск throttle.
  - `tests/unit/bot/middlewares/test_error_handler.py` (4 теста): passthrough, `DomainError` → reply (не пробрасывается), `DomainError` без `Message` тихо проглатывается, неожиданное исключение → reply + reraise.
  - `tests/unit/bot/handlers/test_start.py` (9 тестов): `_reply_text_for` для всех типов чата + handler в private/group/supergroup/без identity.
  - `tests/unit/bot/test_composition_root.py` обновлён: `Container` теперь содержит `rate_limiter`; новый класс `TestBuildDispatcher` — проверка регистрации 4 middleware-ов на 3 observer-ах + наличия router-а `start`.
  - `tests/unit/infrastructure/test_settings.py` — добавлен `TestBotSettings` (5 тестов: дефолтный плейсхолдер-токен, маскирование repr-ом, валидация `> 0` для throttle-настроек, явные значения).

Результат:
- **341 тест** (311 + 30 новых), покрытие **95.96%**, локальный `make ci` зелёный (lint + format + mypy --strict + import-linter + pytest).
- 3 import-linter-контракта по-прежнему на месте: `bot.middlewares` зависит только от `aiogram + bot.middlewares` + `pipirik_wars.infrastructure.rate_limit / pipirik_wars.shared.errors`. Никаких импортов из `application` или `domain` в bot-слой не утекло.

Заметки / решения:
- **Почему `_reply_text_for` — отдельная чистая функция.** Чтобы не привязывать тесты к `Message`-моку и aiogram-у целиком: чистая функция тестируется тривиально (`assert _reply_text_for("private") == REPLY_PRIVATE_RU`), а handler-тест ограничивается проверкой делегирования. Дешёвая декомпозиция, по которой потом будет жить весь bot/handlers — логика выносится в чистые функции, а `@router.message` — тонкий адаптер.
- **Почему throttle-key — `user_id:chat_id`, а не только `user_id`.** Пользователь может одновременно играть в нескольких чатах (личка + группа клана + супергруппа); общий per-user лимит создал бы ложные срабатывания. Per-chat per-user — строгий минимум, который ловит спам в одном чате и не мешает параллельной активности.
- **Почему `ErrorHandlerMiddleware` пробрасывает неожиданные ошибки, а доменные — нет.** Доменные ошибки — ожидаемая часть бизнес-логики (например, «уже зарегистрирован», «клан заморожен»). Пробрасывать их в aiogram = шуметь в логе при штатной работе. Неожиданные исключения, наоборот, — bug, и observability должна их видеть.
- **Тестовая помесь `MagicMock(spec=Message)` + ручной `AsyncMock` для `answer`.** `spec=Message` нужен, чтобы прошёл `isinstance(event, Message)` в production-коде middleware-ов; `MagicMock` отдаёт `answer` как sync-метод, поэтому переопределяем на `AsyncMock`. mypy --strict устраивает: helper типизирован как `MagicMock`, а в `await mw(handler, cast(Message, event), data)` мы явно кастуем для соответствия сигнатуре middleware.
- **`structlog` уже в deps с 0.2** — доменно-агностичный structured-logger; здесь использован впервые, не тянем новые runtime-зависимости.

Дальше: PR 1.1.D — `application/use_cases/RegisterPlayer / RegisterClan / JoinClan / FreezeClan` + `bot/handlers/registration.py` (включит сюда первого реального потребителя репозиториев из 1.1.B).

---

## 2026-05-04 — Спринт 1.1.B: alembic-миграция, ORM-модели и SQLAlchemy-репозитории игрока/клана

**Автор:** Devin (по запросу 612amaranth)
**Тип:** feature (infrastructure)
**Связано:** PR #N (TBD), [development_plan.md §3 / Спринт 1.1, задача 1.1.2](development_plan.md), [current_tasks.md Спринт 1.1 → 1.1.B](current_tasks.md), предшествует — PR #8 (1.1.A domain layer)

Второй PR серии Спринта 1.1: материализация доменных портов 1.1.A в адаптеры поверх SQLAlchemy 2.x async. Новые таблицы — `users`, `clans`, `clan_members` — добавлены alembic-миграцией `0002_player_clan`, продолжающей `0001_initial` из Спринта 0.2.

Что сделано:
- **ORM-модели (`infrastructure/db/models/`)**:
  - `UserORM` (таблица `users`): `id`, `tg_id` UNIQUE, `username` (nullable, indexed), `length_cm`, `thickness_level`, `title`, `name`, `status` (default `active`), `created_at`, `updated_at`. CHECK-constraint-ы дублируют доменные инварианты VO `Length` (≥0) и `Thickness` (≥1) — защита от ручных UPDATE-ов в обход домена.
  - `ClanORM` (таблица `clans`): `id`, `chat_id` UNIQUE (BigInteger — для `-100…` супергрупп), `chat_kind`, `title` (≤255), `status`, `created_at`, `updated_at`.
  - `ClanMemberORM` (таблица `clan_members`): PK `(clan_id, player_id)` + дополнительный `UNIQUE(player_id)` — DB-инвариант ГДД §4 «один игрок = один клан за раз». FK с `ON DELETE CASCADE` на обе стороны.
- **Alembic-миграция `0002_player_clan`** (`infrastructure/db/migrations/versions/20260504_0002_player_clan_schema.py`) — `down_revision = "0001_initial"`. Полные `upgrade()` и `downgrade()` для всех трёх таблиц, индексов, FK и CHECK-constraint-ов. `BigInteger().with_variant(Integer, "sqlite")` для совместимости тестового SQLite.
- **`alembic.ini`** — добавлено `path_separator = os` (alembic 1.16+ требует явный, иначе `DeprecationWarning` падает в strict-режиме).
- **`migrations/env.py`** — расширен импорт ORM-моделей (необходим для регистрации в `Base.metadata`, иначе alembic не увидит новые таблицы при `alembic check` / `revision --autogenerate`).
- **Реальные репозитории (`infrastructure/db/repositories/`)**:
  - `SqlAlchemyPlayerRepository` — реализует `IPlayerRepository`. `add()` — INSERT, ловит `IntegrityError` → `PlayerAlreadyRegisteredError(tg_id)`. `save()` — UPDATE известного `id` (CHECK-constraint бьёт по доменным инвариантам). `get_by_tg_id` — точечный SELECT. Все методы исполняются строго внутри активного `SqlAlchemyUnitOfWork`.
  - `SqlAlchemyClanRepository` — реализует `IClanRepository`. INSERT-ошибка превращается в `ClanAlreadyRegisteredError(chat_id)`. `save()` корректно обрабатывает миграцию group→supergroup (`chat_id` мог измениться, поэтому повторный `IntegrityError` — тоже «уже занято»).
  - `SqlAlchemyClanMembershipRepository` — реализует `IClanMembershipRepository`. `add()` ловит как PK-дубль `(clan_id, player_id)`, так и нарушение `UNIQUE(player_id)` (попытка добавить игрока в новый клан, не выйдя из старого) — оба → `ClanMembershipExistsError`. `remove()` идемпотентен (DELETE rowcount=0 → возвращаем `False`, без исключения).
- **`infrastructure/db/utils.py`** — хелпер `ensure_utc(dt)` нормализует `datetime` до tz-aware. Postgres + asyncpg отдают datetime с tzinfo, но aiosqlite — naive (даже для `DateTime(timezone=True)`). Чтобы тесты на SQLite вели себя как production на Postgres, в маппинге ORM → domain дописываем UTC, если tzinfo отсутствует.

Тесты:
- **`tests/integration/db/test_player_repository.py`** (10 тестов) — round-trip add/get, дубль `tg_id`, save с мутациями, очистка optional-полей, freeze/unfreeze, защита от `add()` сущности с pre-set `id` и `save()` сущности без `id`, ошибка save для несуществующего id.
- **`tests/integration/db/test_clan_repository.py`** (13 тестов) — клан: round-trip, дубль `chat_id`, save title/status, миграция group→supergroup (id сохраняется); membership: добавление, `UNIQUE(player_id)` ловит вторую группу, идемпотентный remove, `list_by_clan` сортирует по `joined_at`.
- **`tests/integration/db/test_migrations.py`** (6 тестов) — структурные (один HEAD, наличие 0001/0002, корректный `down_revision`, контроль состава `versions/`) + smoke (`alembic upgrade head` создаёт ожидаемый набор таблиц на свежей SQLite-БД, `upgrade → downgrade base → upgrade` round-trip без ошибок). `migrations/env.py` тянет URL из `DatabaseSettings()`, поэтому переопределение через env-переменную `DATABASE_URL` (`monkeypatch.setenv`) — а не `cfg.set_main_option`.

Результат:
- 311 тестов (282 + 29 новых), покрытие 95.91 %, локальный `make ci` зелёный.
- `alembic upgrade head` чисто отрабатывает с пустой SQLite, downgrade всё корректно сворачивает (acceptance criteria 1.1.2 выполнен).

Заметки / решения:
- **Зачем `UNIQUE(player_id)` в `clan_members`.** Правило ГДД §4 «один игрок = один клан за раз» — критическое; держать его только на доменном уровне небезопасно при гонках двух одновременных `JoinClan` от разных чатов. Дублирование в БД-индексе превращает гонку в честный `IntegrityError`, который use-case переводит в `ClanMembershipExistsError`.
- **`ensure_utc` вместо нормализации в каждом тесте.** Альтернативы — (а) сделать тесты лояльными к naive vs aware, (б) хранить datetime как `String`/`Float`. (а) приводит к расхождению поведения тестов и production, (б) ломает SQL-операторы вроде `WHERE created_at > now() - interval`. Хелпер на границе ORM → domain — компромисс, не утечка инфраструктуры в домен (домен по-прежнему получает `datetime` с UTC).
- **Pure-sync миграционный smoke-тест.** Объяснение в docstring `test_migrations.py`: `command.upgrade()` сам вызывает `asyncio.run()` (через `env.py`), а pytest-asyncio запускает тест внутри своего loop — две загруженные ссылки на event-loop конфликтуют. Помечать тест `@pytest.mark.asyncio` нельзя; вместо этого делаем sync-тест и переопределяем URL через `DATABASE_URL`.
- **Repository не коммитит и не открывает UoW.** `add()`/`save()` делают `flush()` (чтобы получить сгенерированный PK/поймать IntegrityError до конца транзакции), но коммит — ответственность UoW в `__aexit__`. Это сохраняет атомарность мульти-репозиторных use-case-ов из 1.1.D (`RegisterPlayer + AuditLog + IdempotencyKey`).

Дальше: PR 1.1.C — aiogram bootstrap (dispatcher + middleware-стек + `/start` stub).

---

## 2026-05-04 — Спринт 1.1.A: domain layer для игрока и клана

**Автор:** Devin (по запросу 612amaranth)
**Тип:** feature (domain) / scaffold
**Связано:** PR #N (TBD), [development_plan.md §3 / Спринт 1.1, задачи 1.1.7 / часть 1.1.3 / 1.1.4 / 1.1.10 (доменная половина)](development_plan.md), [current_tasks.md Спринт 1.1 → 1.1.A](current_tasks.md)

Стартовый PR серии Спринта 1.1: чистый доменный слой для игрока и клана. Никакого I/O, никакого aiogram, никакой БД — только value-objects, агрегаты, репозиторий-порты и доменные ошибки. Дальнейшие PR-ы серии (1.1.B alembic+repos, 1.1.C aiogram bootstrap, 1.1.D use-cases+handlers, 1.1.E `/profile` + `/balance_reload`) будут опираться на эти типы.

Что сделано:
- **`domain/player/value_objects.py`** — `Length` (≥0 см), `Thickness` (≥1), `Title(str, Enum)` с единственным значением `NEWBIE` (расширим в 1.3.8/Q12b/Q13), `PlayerName` (строка с инвариантами), `DisplayName` (типизированная обёртка для расчётного «названия» из `balance.yaml.display_names`), `Username` (без `@`, ≤32, не пустая).
- **`domain/player/entities.py`** — агрегат `Player` (frozen-датакласс, slots): `id|None / tg_id / username / length / thickness / title / name / status / created_at / updated_at`. Фабрика `Player.new(tg_id, username, now)` ставит стартовое состояние ГДД §1.1: длина=2, толщина=1, без титула, без имени, status=ACTIVE. Мутаторы `with_username/with_length/with_thickness/with_title/with_name/without_name` возвращают новый инстанс; на `frozen`-игроке бросают `PlayerFrozenError`. `freeze`/`unfreeze` идемпотентны и работают и на frozen-игроке (это администраторский путь).
- **`domain/player/errors.py`** — `PlayerAlreadyRegisteredError(ConcurrencyError)`, `PlayerFrozenError(DomainError)`.
- **`domain/player/repositories.py`** — порт `IPlayerRepository` (`get_by_tg_id / add / save`). Все методы — внутри активного UoW, собственный коммит репозиторий не делает (правило Спринта 0.2).
- **`domain/clan/value_objects.py`** — `ChatKind` (`group / supergroup`), `ClanStatus` (`active / frozen`), `ClanTitle` (с инвариантами).
- **`domain/clan/entities.py`** — агрегат `Clan` (frozen+slots): `id|None / chat_id / chat_kind / title / status / created_at / updated_at`. Фабрика `Clan.new(chat_id, chat_kind, title, now)`. Мутатор `with_chat_id(new_chat_id, new_chat_kind, now)` для миграции `group → supergroup` (Telegram меняет `chat_id` при промоушене, внутренний `id` сохраняется). `with_title / freeze / unfreeze` — идемпотентные. `ClanMember` — отдельный «связующий» агрегат `(clan_id, player_id, role, joined_at)` с ролью `MEMBER / LEADER`.
- **`domain/clan/errors.py`** — `ClanAlreadyRegisteredError(ConcurrencyError)`, `ClanFrozenError(DomainError)`, `ClanMembershipExistsError(ConcurrencyError)`.
- **`domain/clan/repositories.py`** — порты `IClanRepository` (`get_by_chat_id / get_by_id / add / save`) и `IClanMembershipRepository` (`get_by_player / list_by_clan / add / remove`). `remove` идемпотентен (повторный кик — не ошибка).

Тесты:
- 94 новых юнит-теста (`tests/unit/domain/player/{test_value_objects, test_entities, test_errors}.py` + аналогичные для clan). Покрытие веток ≥ 95 % на новых файлах.
- Проверены: VO-инварианты (границы, пустые/whitespace, длина), стартовые значения регистрации (ГДД §1.1), идемпотентность мутаций (с=прежнее → возвращаем `is`-тот же инстанс), миграция group→supergroup, frozen-блокировка мутаций (кроме freeze/unfreeze).

Результат:
- 282 теста (188 предыдущих + 94 новых), покрытие 95.63% (порог 80%).
- `make ci` зелёный (lint + format + mypy --strict + import-linter + pytest).
- Все три import-linter-контракта сохранены: domain/player и domain/clan не импортируют ничего, кроме stdlib и `pipirik_wars.shared.errors`.

Заметки / решения:
- **Иммутабельность вместо мутирующих setter-ов.** Player/Clan — frozen-датаклассы, мутации возвращают новый инстанс. Это делает невозможной частичную мутацию объекта, который держит UoW/audit-buffer/кэш — старая ссылка остаётся валидной. Use-case всегда работает с явной заменой `player = player.with_length(...)`, что хорошо матчится с audit-логом «было/стало».
- **`Title` как `str, Enum` с одним значением.** Сейчас в ГДД доступен только `NEWBIE`; остальные титулы (Нежный, Умный и т. п.) ждут уточнений геймдиза (Q12b/Q13). Расширение enum-а — backwards-compatible, существующий код менять не придётся.
- **`DisplayName` — отдельный VO, а не `str`.** Это требование dev_plan.md §1.1.7 («value object DisplayName»). Сама лукап-логика остаётся в `BalanceConfig.display_name_for(length_cm)`, но в use-case-ах и презентерах мы несём типизированный VO, а не голую строку — ниже шанс перепутать «название» и «имя».
- **`with_chat_id` для миграции group→supergroup.** Telegram меняет `chat_id` при промоушене группы в супергруппу (с положительного в `-100…`), но внутренняя сущность клана при этом не должна пересоздаваться. Метод-мутатор делает атомарную замену `(chat_id, chat_kind)` без потери `id` и `created_at`.
- **`ClanMember.remove` идемпотентен.** Telegram может присылать дубль `chat_member`-евента, и use-case не должен валиться при «уже ушёл».

---

## 2026-05-04 — Спринт 0.2 «достройка»: BalanceLoader (0.2.9 + 0.2.10)
**Автор:** Devin (по запросу 612amaranth)
**Тип:** infra / config
**Связано:** PR (TBD), [development_plan.md §3 Фаза 0 / Спринт 0.2 «достройка»](development_plan.md), [current_tasks.md Спринт 0.2 «достройка»](current_tasks.md)

Что сделано (2 пункта плана):

1. **Pydantic-схема `BalanceConfig` (0.2.9).** Чистая (domain-only) модель в `src/pipirik_wars/domain/balance/config.py`. Все ноды — `frozen=True, extra="forbid", populate_by_name=True` (двойная защита: иммутабельность + отказ на лишних полях + поддержка как алиаса YAML, так и имени поля в Python). Подмодели:
   - `DisplayNameRange` — полуоткрытый интервал `[from, to)`, `to=null` только для последнего ряда. Алиасы `from`/`to` маппятся на `from_cm`/`to_cm` через `Field(alias=...)` (Python-keyword conflict).
   - `ForestOutcome`/`ForestConfig` — веса > 0, `min ≤ max`, `cooldown_min_minutes ≤ cooldown_max_minutes`, имена веток уникальны.
   - `OracleConfig` — `bonus_min ≤ bonus_max`, оба > 0, `distribution` — `Literal["uniform"]` (на будущее можно расширить до `weighted_buckets`).
   - `ReferralConfig` — `on_thickness_milestones` строго отсортированы по `thickness` без дублей.
   - `ThicknessConfig` — `cost_base > 0`, `cost_exponent ≥ 1`, `unlock_levels` — непустой dict, каждый level ≥ 1.
   - `DauGateConfig` — `0 < alert_threshold ≤ 1`.
   - `DailyHeadConfig` — `bonus_min ≤ bonus_max`, `schedule_mode` ∈ {`button`, `cron`, `hybrid`}, `cron_random_offset_hours ∈ (0, 48]`.
   - `ContentPolicy` / `ContentPolicyClanQuotes` — bool-флаги.
   - **Главный инвариант** на корневом `BalanceConfig`: `display_names` стартуют с 0, ряды примыкают друг к другу без дыр и пересечений (`prev.to == next.from`), последний ряд имеет `to=null`. Любое нарушение → `ValidationError`.
   - Метод `display_name_for(length_cm)` — поиск названия по длине (полуоткрытый интервал, `length_cm < 0` → `ValueError`, недостижимая ветка → `IntegrityError` для защиты от рассинхрона).
2. **`YamlBalanceLoader` + порт `IBalanceConfig` (0.2.10).** Порт `IBalanceConfig` живёт в `domain/balance/ports.py` (`abc.ABC` с одним методом `get() -> BalanceConfig`). Реализация — `infrastructure/balance/loader.py:YamlBalanceLoader`:
   - **Lazy-загрузка**: конструктор не читает файл, чтобы тесты могли создавать loader на несуществующих путях; первый `get()` читает + парсит + валидирует.
   - **Кэш**: повторные `get()` отдают **тот же** объект (тождественность через `is`); подмена файла снаружи без `reload()` не вызывает перечтение.
   - **Hot-reload**: `reload()` перечитывает файл и **атомарно** подменяет внутреннюю ссылку; старый снимок остаётся валидным благодаря `frozen=True`. Если новый YAML невалиден — `ConfigError`, кэш не трогается (тест `test_reload_failure_keeps_old_snapshot`).
   - **Маппинг ошибок**: любая ошибка чтения / парсинга / валидации → `pipirik_wars.shared.errors.ConfigError` с понятным `path` и причиной (для будущего алёрта в админ-чат).
3. **Composition root.** В `bot/main.py:Container` добавлено поле `balance: IBalanceConfig`; `build_container()` принимает опциональный `balance_yaml_path` (default — `Path("config/balance.yaml")`). Loader не блокирует импорт — `create_async_engine`-стиль lazy.

Покрытие порта в тестах:

- 39 новых тестов в `tests/unit/domain/balance/test_config.py` (валидация + boundary checks + `display_name_for`).
- 11 новых тестов в `tests/unit/infrastructure/test_balance_loader.py` (lazy, кэш, reload, ошибки, smoke-тест на реальном `config/balance.yaml`).
- Существующие тесты `test_composition_root.py` обновлены под новое поле `balance` в `Container`; добавлен `tests/fakes/balance.py:FakeBalanceConfig` для тестов use-case-ов в Спринтах 1.1+.
- Общая статистика: **188 тестов** (138 предыдущих + 50 новых), покрытие **94.30 %** (порог 80%). `make ci` зелёный (lint + format + mypy --strict + import-linter + pytest + pre-commit).

Результат / артефакты:

- `src/pipirik_wars/domain/balance/{__init__,config,ports}.py` — domain-схема и порт.
- `src/pipirik_wars/infrastructure/balance/{__init__,loader}.py` — YAML-loader.
- `tests/fakes/balance.py` + регистрация в `tests/fakes/__init__.py`.
- `tests/unit/domain/balance/{__init__,factories,test_config}.py` + `tests/unit/infrastructure/test_balance_loader.py`.
- `bot/main.py:Container` обогащён полем `balance`.
- 3 контракта import-linter сохранены: `domain.balance` импортирует только stdlib и pydantic; `infrastructure.balance` зависит от domain (через интерфейсы) и pyyaml/pydantic.

Заметки / решения:

- **Алиасы `from`/`to`.** YAML использует ключи `from`/`to` (как в ГДД §2.3), но это — Python keywords. Pydantic `Field(alias="from")` + `populate_by_name=True` даёт «и YAML, и Python field-name» работать одновременно. В тестах конструируем через `model_validate(dict)` — это не зависит от типов `__init__` (без pydantic.mypy plugin static-сигнатура `**data: Any`).
- **Единый `ConfigError`.** Все три класса ошибок (OSError при чтении, `yaml.YAMLError` при парсинге, `pydantic.ValidationError` при валидации) маппятся в один `ConfigError` из `shared.errors` — это даст единое место для алёрта/логирования в Спринте 1.5 (админ-команды).
- **Lazy + cache + atomic reload.** Эти три свойства в одном loader-е делают возможным hot-reload без перезапуска процесса (план Спринта 2.5: админ-команда `/balance_reload`). Старые `BalanceConfig`-снимки остаются валидными ровно потому, что `frozen=True` запрещает мутации — клиенты, схватившие ссылку до `reload()`, не увидят неконсистентного состояния.
- **`__slots__` отсортированы.** Ruff `RUF023` требует сортировки имён в `__slots__` — учли (`("_cached", "_path")`).

---

## 2026-05-04 — Спринт 0.2: каркас безопасности
**Автор:** Devin (по запросу 144keri)
**Тип:** infra / security
**Связано:** PR #5, [development_plan.md §3 Фаза 0 / Спринт 0.2](development_plan.md), [current_tasks.md Спринт 0.2](current_tasks.md)

Что сделано (11 пунктов плана):

1. **Расширение зависимостей (0.2.0).** В `pyproject.toml` добавлены: `SQLAlchemy[asyncio]>=2.0.30`, `asyncpg>=0.29`, `alembic>=1.13`, `structlog>=24.1`, `aiosqlite` и `freezegun` в dev-deps (тесты адаптеров на in-memory SQLite, мокирование времени).
2. **pydantic-settings (0.2.6).** `infrastructure/settings/`: `Settings` + `DatabaseSettings` + `BootstrapSettings`. URL хранится как `SecretStr` (не утекает в repr/log). `BootstrapSettings.admin_ids` парсит CSV из env (`"100, 200, 300"` → `(100, 200, 300)`). Никаких хардкод-секретов в коде.
3. **Alembic (0.2.0b).** `alembic.ini` + `infrastructure/db/migrations/` (env.py async-режим + URL из pydantic-settings). Первая миграция `0001_initial` создаёт `idempotency_keys`, `audit_log`, `activity_locks`, `admins`. `BigInteger.with_variant(Integer, "sqlite")` для autoincrement, `with constraint naming convention` (детерминированный rename в alembic autogenerate).
4. **`SqlAlchemyUnitOfWork` (0.2.0c).** Async-CM с `auto-rollback` на исключение, защита от nested-context, явные `commit()`/`rollback()` методы. Реализует `IUnitOfWork`.
5. **`SqlAlchemyIdempotencyService` (0.2.2).** `INSERT ... ON CONFLICT DO NOTHING` (диалект-специфично для PG/SQLite). Повторный `mark()` — NO-OP, не портит транзакцию.
6. **`SqlAlchemyAuditLogger` (0.2.3).** Запись в `audit_log` через сессию UoW. Откатывается с транзакцией. JSON-поля `before`/`after` для diff-снимков.
7. **`SqlAlchemyActivityLockRepository` (0.2.1) + `ActivityLockService`.** PK `(actor_kind, actor_id)`. Истёкшие блоки удаляются перед попыткой `try_acquire`. `LockAlreadyHeldError` бросается из application-сервиса при отказе. Тест «двойной захват» зелёный.
8. **`SqlAlchemyAdminRepository` + bootstrap.** Use-case `BootstrapSuperAdmin` (из `BOOTSTRAP_ADMIN_IDS`): при пустой `admins` выдаёт каждому `tg_id` роль `super_admin` + audit-запись `bootstrap`; при непустой — NO-OP. Дубли в списке dedupe-ятся, неактивные админы не считаются.
9. **DTO входов (0.2.4).** `application/dto/inputs.py`: `RegisterPlayerInput`, `RegisterClanInput`, `GrantLengthInput`. `model_config = {extra="forbid", strict=True, frozen=True}` — никаких неявных конверсий и лишних полей.
10. **Декораторы авторизации (0.2.5).** `application/auth/`: `AuthContext` (DTO), `requires_level(min)`, `requires_length(min_cm)`, `requires_clan_member`. Ошибка → `AuthorizationError(requirement=…, detail=…)`. Все 5 путей покрыты тестами.
11. **`InMemoryTokenBucketRateLimiter` (0.2.7).** Реализует `IRateLimiter`. Тест `10 cmd/s` → 11-й отказ. Per-key bucket (отдельный лимит на игрока). Refill — линейный по `IClock.now().timestamp()`.

Реальный composition root (`bot/main.py:build_container()`): собирает `RealClock` + `RealRandom` + `SqlAlchemyUnitOfWork` + `SqlAlchemyIdempotencyService` + `SqlAlchemyAuditLogger` + `Settings`. `main()` остаётся `NotImplementedError("1.1")` — entry point с aiogram появится в Спринте 1.1.

Результат / артефакты:

- Локально: 138 тестов (49 unit Спринта 0.1 + 89 новых: unit + integration на in-memory SQLite). Покрытие 93% (порог 80%). `make ci` зелёный (lint + format + mypy --strict + import-linter + pytest + pip-audit).
- Alembic: `alembic upgrade head && alembic downgrade base` отрабатывают чисто на SQLite (в Postgres проверим в Спринте 1.1).
- 3 контракта import-linter сохранены: `domain` и `application` не зависят от `sqlalchemy/asyncpg/aiogram/httpx/infrastructure`.

Заметки / решения:

- **SQLite в integration-тестах.** Использован `aiosqlite` через `Base.metadata.create_all()` — даёт быстрый smoke-test адаптеров без поднятия Postgres. Production будет на asyncpg/Postgres; миграции тестируем на обоих диалектах (Spring 1.1 поднимет docker-compose с Postgres в CI).
- **`with_variant(Integer, "sqlite")`.** SQLite не умеет AUTOINCREMENT на BigInteger. Используем `Integer` (32-битный) на SQLite — для тестов хватит, в Postgres — нативный `bigserial`.
- **Нет повсеместного `Any`/`getattr`.** В двух местах с диалект-специфичным `Insert`-стейтментом введены типизированные ветки `PgInsert`/`SqliteInsert` с присваиванием в общий `DialectInsert`. Mypy `--strict` зелёный.
- **`build_container()` теперь работает.** Раньше (Спринт 0.1) бросал `NotImplementedError("0.2")`. В Спринте 1.1 будет добавлен `aiogram.Dispatcher` поверх контейнера в `main()`.

---

## 2026-05-04 — Спринт 0.1: каркас clean architecture
**Автор:** Devin (по запросу 144keri)
**Тип:** infra / refactor
**Связано:** PR #3, [development_plan.md §3 Фаза 0 / Спринт 0.1](development_plan.md), [current_tasks.md Спринт 0.1](current_tasks.md)

Что сделано (8 пунктов плана):

1. **Структура папок (0.1.1).** Доукомплектован каркас: добавлены `src/pipirik_wars/domain/shared/ports/`, `src/pipirik_wars/shared/errors.py`, `tests/fakes/`, `tests/unit/{domain/shared/ports,fakes,bot}/`. Все слои на месте, в каждом — `__init__.py` с docstring о роли слоя и правилах импортов.
2. **import-linter (0.1.2).** Создан `.importlinter` с 3 контрактами:
   - `layered_architecture` — порядок слоёв `bot/admin → infrastructure → application → domain → shared`.
   - `domain_must_not_import_infrastructure` — `domain/` не имеет права тянуть `infrastructure`, `bot`, `admin`, `aiogram`, `sqlalchemy`, `asyncpg`, `httpx`.
   - `application_must_not_import_io_libs` — то же ограничение для `application/` (use-cases не знают про БД и Telegram).
3. **Доменные порты (0.1.3).** В `pipirik_wars.domain.shared.ports`:
   - `IClock` (`now()`, `moscow_date()`).
   - `IRandom` (`randint`, `uniform`, `choice`, `weighted_choice`, `deterministic_uint(seed, modulo)` — последний для per-clan offset Главы клана дня).
   - `IUnitOfWork` (async-context-manager: `commit/rollback`, авто-rollback на исключении).
   - `IIdempotencyKey` (`build`, `is_seen`, `mark`).
   - `IAuditLogger` (`record(AuditEntry)` + `AuditAction` enum + `AuditEntry` dataclass).
   - Все порты — абстрактные (`abc.ABC`), любая попытка прямой инстанциации падает `TypeError`.
   - В `tests/fakes/` пять in-memory реализаций: `FakeClock`, `FakeRandom`, `FakeUnitOfWork`, `FakeIdempotencyKey`, `FakeAuditLogger`. На них уже сейчас 49 unit-тестов, покрытие 100%.
4. **Composition root (0.1.4).** В `pipirik_wars.bot.main` создан `Container` (frozen `dataclass(slots=True)` с пятью портами) и `build_container()/main()` — пока заглушки, бросающие `NotImplementedError` с указанием спринта, в котором они появятся. Никакого сервис-локатора, никаких глобальных DI-контейнеров.
5. **`pyproject.toml` (0.1.5).** Полный конфиг: Python ≥ 3.11, runtime-deps минимальны (pydantic, pydantic-settings, PyYAML), dev-deps — ruff, mypy, pytest+pytest-asyncio+pytest-cov, pip-audit, pre-commit, import-linter, types-PyYAML.
   - `ruff.lint` = `E/W/F/I/B/UP/SIM/N/PL/RUF`, `RUF001/2/3` отключены (проект на русском).
   - `mypy --strict` со строгими `disallow_*` и `mypy_path = src`.
   - `pytest` с `--cov-fail-under=80`, `asyncio_mode = auto`.
6. **Pre-commit (0.1.6).** `.pre-commit-config.yaml`: pre-commit-hooks v4.6 (whitespace, EOF, yaml/toml, large-files, merge-conflict, private-key), `ruff` + `ruff-format`, `mypy` (с `additional_dependencies`), `import-linter` через `repo: local` (чтобы видеть проектный venv).
7. **GitHub Actions CI (0.1.7).** `.github/workflows/ci.yml`: матрица Python 3.11/3.12, кеш pip, шаги ruff lint + ruff format check + mypy --strict + lint-imports + pytest + coverage artifact. Отдельный job `audit` для `pip-audit --skip-editable`.
8. **Makefile (0.1.8 бонус).** Таргеты `install`, `install-dev`, `lint`, `format`, `typecheck`, `imports`, `test`, `cov`, `audit`, `pre-commit`, `ci`, `clean`. `make ci` локально прогоняет lint+types+imports+test (audit отдельно — он сетевой).

Результат / артефакты:
- `pyproject.toml`, `Makefile`, `.importlinter`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`.
- 73 файла Python в проекте; 49 unit-тестов; покрытие 100%.
- Локальный `make ci` зелёный; pip-audit без CVE; pre-commit без замечаний.

Заметки / решения:
- Pytest подняли с `>=8.2,<9` до `>=9.0.3,<10` (CVE-2025-71176 в 8.x). Соответственно pytest-asyncio — до `>=1.3,<2`.
- `pip-audit` не умеет аудитить editable-пакеты — везде используем `--skip-editable`, чтобы не сообщать о собственном `pipirik-wars` как «не найден на PyPI».
- Production-зависимостей (aiogram, sqlalchemy, asyncpg, structlog, apscheduler) пока нет — они появятся в Спринте 1.1+. Это снижает площадь pip-audit и держит CI быстрым.
- Никакого бизнес-кода ещё нет — только инфраструктурный каркас. ГДД-баланс заморожен в `config/balance.yaml` v2.

---

## 2026-05-04 — ГДД v9: уточнения после мержа PR #1
**Автор:** Devin (по запросу 144keri)
**Тип:** doc / decision / balance
**Связано:** PR #2 (пост-мерж правки)

После мержа PR #1 заказчик ответил на 6 из 8 открытых вопросов. Внесены правки в ГДД v8 → v9.

Что сделано:

1. **Глава клана дня — гибридный триггер.** §6.1 ГДД переписан:
   - Бонус: было `+3` см → стало **`uniform(1, 20)` см** (`balance.yaml: daily_head.bonus_min/bonus_max`).
   - Триггер: было «cron 12:00 UTC всем сразу» → стало **гибрид «кнопка `/clan_head` ИЛИ фоновый cron с per-clan `random_offset(0..24h)` от 00:00 МСК»**. Что наступит первым — то и побеждает. Идемпотентность по `(clan_id, moscow_date)`. Распределяет нагрузку по суткам и добавляет элемент «кто первый дёрнет рулетку».
   - Добавлены use-cases `RequestDailyHead` (button-driven) и `RunDailyHeadCron` (cron) поверх единого доменного сервиса `DailyHeadService.assign_or_get`.
   - В Спринте 2.3 теперь 8 задач (было 7) с новыми пунктами на кнопочный триггер и детерминированный per-clan offset.
2. **Контент-полиси цитат — уместный мат разрешён.** §6.1 ГДД и `balance.yaml: content_policy.clan_quotes`:
   - `mild_profanity: true` (Q9 v9).
   - Запрещены: политика, межнацоскорбления, насилие, реклама, секс.
   - Цитаты с матом помечаются тегом `profanity` для будущего фильтра «детский режим клана».
3. **Bootstrap первого `super_admin`-а.** §18.6.4 ГДД дополнен:
   - Первый `super_admin` берётся из env-переменной `BOOTSTRAP_ADMIN_IDS` (список `tg_id` через запятую).
   - Bootstrap-логика срабатывает **только один раз** (если таблица `admins` пуста).
   - Значение хранится в Devin Secrets (`PIPIRIK_BOOTSTRAP_ADMIN_TG_ID`, `save_scope: org`), в git/конфиг/логи никогда не попадает.
   - Спринт 0.2.6 расширен: добавлен критерий приёмки «bootstrap-логика сработала ровно один раз; повторный запуск с непустой `admins` — env игнорируется».
   - `.env.example` добавлен placeholder `BOOTSTRAP_ADMIN_IDS=` с комментарием.
4. **«Нежный» переедет на другой триггер.** §2.4 ГДД: «Новичок» = первый лес (как в v8), «Нежный» — TBD (открытый вопрос Q12b). Это не блокирует разработку Спринта 1.3.
5. **Каналы как кланы — отказ полностью; канал-анонсы — отдельный спринт.**
   - §1.1 ГДД переписан: «канал = клан» НЕ ПОДДЕРЖИВАЕТСЯ, отказ.
   - §22 (приоритеты) и `current_tasks.md` (бэклог): добавлен **Спринт 4.9 «Канал-анонсы перед публичным релизом»** — отдельный публичный TG-канал бота с автопостингом итогов недели / лидербордов / релиз-нот, настраивается **в самом конце Фазы 4** перед маркетинг-релизом.
6. **Веса веток леса 50/35/15 утверждены по умолчанию** (объяснил среднюю прибавку: ≈ 8.5 см/поход; разные распределения дают разный игровой эффект). Балансироваться будут после альфа-теста.
7. **Финальная таблица `display_names`** — заглушка из v8 остаётся; финальную таблицу геймдиз пришлёт отдельным PR.

Результат / артефакты:
- `docs/pipirik_wars_plan.md` (ГДД v9): шапка, §1.1, §2.4, §6.1, §18.6.4, §22, footer
- `docs/development_plan.md`: Спринт 0.2.6, Спринт 2.3, §2.3 БД-схема (`clan_daily_head`), §11 (открытые вопросы)
- `docs/current_tasks.md`: «Закрыто в v9» секция, обновлён бэклог (Спринт 2.3, Спринт 4.9)
- `config/balance.yaml`: версия 1 → 2; `daily_head` (1–20, hybrid); `content_policy.clan_quotes`
- `.env.example`: `BOOTSTRAP_ADMIN_IDS`
- Devin Secrets: `PIPIRIK_BOOTSTRAP_ADMIN_TG_ID` (org-scope, sensitive)

Заметки / решения:
- **Гибридный триггер** — это не просто «оптимизация нагрузки». Это улучшение игрового опыта: фиксированный 12:00 UTC создаёт «дежурный» статус (все знают что в полдень будет назначение, никто не интересуется); рандомный offset + кнопка возвращают непредсказуемость и повод заглянуть в чат клана.
- **`uniform(1, 20)`** вместо `+3` фиксированного — повторяет паттерн `/oracle` (тот же диапазон, та же распределённая природа). Игрок получает «вау, мне выпало 18!» моменты вместо предсказуемой выдачи.
- **`BOOTSTRAP_ADMIN_IDS` в env, не в `balance.yaml`** — намеренно. Список админов не должен попадать в git (это PII + риск). Хранить в Devin Secrets, прокидывать в env при деплое.
- **«Нежный» на TBD-триггере** — лучше иметь явный TBD в открытых вопросах, чем тихо переименовать в коде. Геймдиз увидит и решит позже.
- **Канал-анонсы как Спринт 4.9** — это «закладка» в самом конце Фазы 4. Обоснование: нет смысла настраивать публичный канал, пока нет публичного релиза; до релиза итоги недели и лидерборды живут в чатах кланов.

---

## 2026-05-04 — ГДД v8: уточнения от заказчика (перед мержем PR #1)
**Автор:** Devin (по запросу 144keri)
**Тип:** doc / decision / balance
**Связано:** PR #1 (поправки до мержа)

Что сделано (11 правок ГДД v7 → v8):

1. **Имя при регистрации убрано.** §1.1 и §2.5: новичок при регистрации **не получает имени**. Имя — это тип предмета, выбивается дропом из леса. До первого дропа карточка показывает «Титул Название», без имени.
2. **Название по длине вынесено в `balance.yaml`.** §2.3 переписан: вместо хардкода в ГДД — редактируемая таблица `display_names` в `config/balance.yaml`. ГДД содержит только заглушку и ссылку. Валидация: без дыр и пересечений.
3. **Стартовые параметры зафиксированы.** §1.1 / §2 / §22: длина = **2 см**, толщина = **1**, **титул = нет**, **имя = нет**. Титул «Новичок» выдаётся автоматически при первом возвращении из леса (§8.2, идемпотентно).
4. **Реферальная схема — 3-этапная.** §13.1: при регистрации новичок +5 см, реферер +1 см. При достижении новичком толщины 3 → реферер +10 см. При толщине 5 → реферер +30 см. Все начисления — после регистрации, через `progression.add_length` с уникальным `idempotency_key` вида `referral:{milestone}:{referrer_id}:{referred_id}`.
5. **Лес — 3 ветки исходов.** §8.2: `scarce` (1–10 см, вес 50), `normal` (5–15 см, вес 35), `abundant` (10–20 см, вес 15). Все ветки положительные. Веса и диапазоны — в `balance.yaml`.
6. **`/oracle` — по Москве, +1..+20 см.** §11: `cooldown_tz = "Europe/Moscow"`, сброс в 00:00 МСК; `bonus = uniform(1, 20)` см.
7. **Кик бота из чата клана → `frozen` (не `archived`).** §1.1 + БД: статус `clans.status` теперь `active|frozen|archived`. Заморозка не удаляет данные; повторное добавление бота → `active`.
8. **Основной интерфейс админки — Telegram-бот.** §18.6 переписан: бот = первый класс (Спринт 1.5/2.5, `/admin_*` команды + TOTP-подтверждение опасных действий). Веб-панель опциональна и переехала в Спринт **4.5** Фазы 4 (поверх готовых use-cases).
9. **Пацанские цитаты — иронично-смешные.** §6.1: стилистика Стэтхем / ВК-паблик / АУФ, с самоиронией. Без мата и политики. Каталог цитат тегируется (`statham`, `vk_pablik`, `auf`, `meme`) для будущего A/B.
10. **План разработки и текущие задачи синхронизированы:**
    - Спринт 1.1 — пересмотрен под старт без имени/титула + frozen вместо archived.
    - Спринт 1.3 — добавлены 3 ветки леса + автотитул «Новичок».
    - Спринт 1.4 — `/oracle` по `Europe/Moscow`, `uniform(1, 20)`.
    - Спринт 2.3 — иронично-смешные цитаты, пропуск `frozen` кланов.
    - Спринт 2.4 — расписана 3-этапная реферальная схема с idempotency.
    - Спринт 2.5 — переименован в «Админ-интерфейс в боте (основной)»; веб-панель — Спринт 4.5.
    - Добавлен Спринт 0.2.9–0.2.10 — скелет `balance.yaml` + `BalanceLoader`.
    - В §11 раздел «Открытые вопросы» 11 пунктов закрыто, 7 остаются актуальными.
11. **Создан `config/balance.yaml`** со стартовыми секциями (`display_names`, `forest.outcomes`, `oracle`, `referral`, `thickness`, `dau_gate`, `daily_head`).

Результат / артефакты:
- `docs/pipirik_wars_plan.md` (ГДД v8)
- `docs/development_plan.md` (синхронизирован с v8)
- `docs/current_tasks.md` (открытые вопросы пересортированы)
- `config/balance.yaml` (новый файл)

Заметки / решения:
- **Имя как предмет** — это намеренно ограничивает контент-политику: новичок без имени не отображается с «странным» дефолтным ником в чате клана (только «Пипирик» по длине). Имя нужно ещё «заработать».
- **Реферальная схема многоэтапная** — это усиливает удержание реферера: одного клика мало, нужно «довести» нового игрока хотя бы до толщины 3, что само по себе требует ~14000 см длины. Это естественный антифрод.
- **TZ Москвы для `/oracle`** упрощает прогноз поведения пользователей (в РФ-аудитории — большинство), но потребует учёта при расчёте «сегодня» в БД. Решено хранить `moscow_date` отдельно от UTC `created_at`.
- **Бот-админка вместо веб-панели** меняет философию проекта: не «отдельное приложение для команды», а «расширение бота для уполномоченных пользователей». Это упрощает запуск (один процесс, один деплой) и аутентификацию (только Telegram-сторона). Веб-панель остаётся как позднее улучшение для операций, неудобных в чате.
- **`balance.yaml` с pydantic-валидацией** заменяет хардкод. Это позволит горячо менять баланс без релиза кода (через `/balance_reload` или веб-редактор) и хранить историю версий для rollback.
- **Конфликт титула «Нежный»** (выдаётся за «первый поход в лес») с автоматическим «Новичок» — открытый вопрос Q12, требует решения геймдиза.

---

## 2026-05-04 — ГДД v7 + Фаза 0 + админ-панель + Глава клана дня + git-репозиторий
**Автор:** Devin (по запросу 144keri)
**Тип:** doc / plan / decision
**Связано:** PR #1 в `Pipirkawar/PipirkaWar`

Что сделано:
- **ГДД переведён в v7** (`pipirik_wars_plan.md`):
  - Добавлен §0 «Политика разработки» — SOLID/ООП-принципы и безопасность/целостность данных как обязательные требования.
  - Добавлен §1.1 «Регистрация игрока и клана» — игрок только через ЛС бота, клан только через добавление бота в группу/супергруппу. Каналы как кланы — не поддерживаются на MVP.
  - Добавлен §6.1 «Глава клана дня» — ежедневный розыгрыш в кланах ≥ 5 человек, +N см и иронично-пацанская цитата.
  - Добавлен §18.6 «Админ-панель» — отдельное FastAPI-приложение, RBAC, 2FA, аудит-лог админских действий.
  - Обновлён §22 «Приоритеты разработки» — добавлена Фаза 0 (Фундамент), уточнены задачи Фаз 1–4.
- **План разработки переведён под v7** (`development_plan.md`):
  - Добавлен §0 — рабочий чек-лист SOLID и безопасности, требуемый на каждом PR.
  - Архитектура переведена на clean architecture: `domain → application → infrastructure → bot/admin`.
  - Добавлена **Фаза 0 — Фундамент** (Спринты 0.1 и 0.2) с конкретными задачами под каркас и безопасность.
  - Спринт 1.1 переписан под «регистрация только через ЛС / клан только через группу».
  - Добавлены спринты **2.3 «Глава клана дня»** и **2.5 «Админ-панель v1»**.
  - Покрытие тестов поднято с 70 % до 80 % (`domain/` + `application/`).
  - Расширена БД-схема (`clan_daily_head`, `payments`, `admins`, `admin_audit_log`).
  - Список открытых вопросов расширен (баланс «Главы клана дня», список админов, доступ к панели, контент-политика цитат).
- **Список текущих задач переведён на Фазу 0** (`current_tasks.md`): 8 задач Спринта 0.1 + 8 задач Спринта 0.2 с приоритетами и оценками.
- **Заведён git-репозиторий** `Pipirkawar/PipirkaWar`:
  - Клонирован пустой репо в `/home/ubuntu/PipirkaWar`.
  - Добавлены документы в `docs/`.
  - Добавлен `.gitignore` под Python-проект.
  - Подготовлена структура папок будущего проекта (`domain/`, `application/`, `infrastructure/`, `bot/`, `admin/`, `tests/`, `config/`, `ops/`) с пустыми `__init__.py` и README в каждой папке, описывающим её назначение.
  - Сделан коммит и открыт PR `devin/<ts>-initial-setup` → `main`.

Результат / артефакты:
- `Pipirkawar/PipirkaWar` (репозиторий)
- `docs/pipirik_wars_plan.md` (ГДД v7)
- `docs/development_plan.md`
- `docs/history.md`
- `docs/current_tasks.md`
- `.gitignore`
- Каркас директорий проекта

Заметки / решения:
- **SOLID/ООП и безопасность подняты до уровня политики компании** (раздел §0 ГДД). Это значит, что ни одна фича Фазы 1+ не принимается без прохождения чек-листа из `development_plan.md` §0.
- **Введена Фаза 0** — её задача в том, чтобы инфраструктурные решения (clean architecture, idempotency, audit log, activity lock, RBAC-каркас, CI gates) были приняты до старта геймплея, а не ретроспективно. Это снижает технический долг и предотвращает классические race-conditions с двойным начислением длины.
- **Регистрация клана** реализуется через `my_chat_member`-событие aiogram при добавлении бота в группу. Это исключает возможность «фейковых» кланов через ЛС бота.
- **Админ-панель** вынесена в отдельный FastAPI-процесс с собственным DB-юзером (минимально необходимые права). Это разделяет blast-radius между ботом и инструментами поддержки.
- **«Глава клана дня»** — лёгкая фича, но требует idempotency (повторный запуск джобы за тот же день — no-op), `IRandom` (для тестируемости) и контент-политики для цитат. Все эти моменты зафиксированы в плане.
- Структура папок отражает clean architecture с самого начала, чтобы избежать рефакторинга на полпути.

---

## 2026-05-04 — Создание стартовой документации проекта
**Автор:** Devin (по запросу 144keri)
**Тип:** doc / plan
**Связано:** —

Что сделано:
- Прочитан и проанализирован геймдиз `pipirik_wars_plan.md` (ГДД v6).
- Создан подробный план разработки `development_plan.md` с разбивкой на 4 фазы и спринты.
- Заведён файл истории выполнения `history.md` (этот файл).
- Заведён файл текущих задач `current_tasks.md` со списком задач на ближайший спринт (Спринт 1.1 — Каркас и регистрация).

Результат / артефакты:
- `pipirik_wars/development_plan.md`
- `pipirik_wars/history.md`
- `pipirik_wars/current_tasks.md`

Заметки / решения:
- План разработки разбит на 4 фазы согласно ГДД §22, но с детализацией до спринтов и конкретных задач с критериями приёмки.
- В план вынесен список из 10 открытых вопросов к ГДД (стартовая длина/толщина, диапазон прибавки в лесу, названия для 501+ см и т. д.) — требуется уточнение у геймдизайнера до старта реализации.
- Все балансовые числа (множители каравана, цены толщины, кулдауны) предложено хранить в отдельном `config/balance.yaml` — чтобы менять баланс без релиза кода.
- Стек зафиксирован по ГДД §17: Python 3.11+ / aiogram 3.x / managed PostgreSQL (Neon) / APScheduler / fluent-i18n. Redis — отложен до Фазы 4.

---

<!-- Шаблон для новой записи (копируйте и заполняйте сверху):

## YYYY-MM-DD — Заголовок
**Автор:**
**Тип:** plan | feature | fix | refactor | infra | balance | doc | decision
**Связано:**

Что сделано:
-

Результат / артефакты:
-

Заметки / решения:
-

---
-->
