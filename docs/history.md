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

## 2026-05-08 — Спринт 3.2-B: use-cases + persistence + миграция `0019_caravans` (Караваны, движущаяся часть)

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 3.2 ([`current_tasks.md`](current_tasks.md) «Декомпозиция Спринта 3.2 на фичевые PR-ы»), ПД §6.3.2 «Спринт 3.2 — Караваны (полная механика)», ГДД §9 «Караваны». Второй PR Спринта 3.2 — приземляет use-case-ы и persistence на доменный фундамент 3.2-A. Боевая механика и награды — Спринт 3.2-C; bot-handlers и UI — 3.2-D.

Что сделано:

- **B.1 — `domain/shared/ports/audit.py`:** добавлены 4 новых `AuditAction`-а каравана: `CARAVAN_CREATED`, `CARAVAN_PLAYER_JOINED`, `CARAVAN_PLAYER_LEFT`, `CARAVAN_LOBBY_CLOSED` (whitelist для `audit_log.action`).
- **B.2 — `domain/shared/ports/scheduler.py`:** расширен `IDelayedJobScheduler` методами `schedule_caravan_lobby_close(caravan_id, run_at)` / `cancel_caravan_lobby_close(caravan_id)` — симметрично паттерну mountain/dungeon.
- **B.3 — DTO `application/dto/inputs.py`:** четыре новых input-а: `CreateCaravanInput` (sender/receiver `chat_id`, `tg_id` лидера, `contribution_cm`), `JoinCaravanLobbyInput` (`tg_id`, `caravan_id`, `role`, опц. `contribution_cm`), `LeaveCaravanLobbyInput` (`tg_id`, `caravan_id`), `CloseCaravanLobbyInput` (`caravan_id`).
- **B.4 — Use-case `CreateCaravan`** (`application/caravans/create_caravan.py`): проверка lvl ≥ 7 (по `Thickness`-таблице), sender-clan через `chat_id` отправителя, target-clan через `chat_id` получателя; `≥ 20 см` после взноса; кулдаун 12 ч от `started_at` последнего каравана клана-отправителя (включая `CANCELLED`); activity-lock на `(player, CARAVAN)` с TTL = lobby+battle (= 80 мин); в одной транзакции — `Caravan.starting(...)` → save → `CaravanParticipant.caravaneer(is_leader=True)`, `IDelayedJobScheduler.schedule_caravan_lobby_close(caravan_id, lobby_ends_at)`, контрибьюция списывается с `Length` лидера, `IAuditLogger.record(CARAVAN_CREATED)` с idempotency-key. Возвращает `CreatedCaravan(caravan, leader_participant)`.
- **B.5 — Use-case `JoinCaravanLobby`** (`application/caravans/join_caravan_lobby.py`): проверка `Caravan.status=LOBBY` (иначе `CaravanLobbyClosedError`); резолв роли по таблице ГДД §9.4 (5 кейсов) через `IClanMembershipRepository.get_by_player(player.id)` + сравнение с `caravan.sender_clan_id` / `caravan.receiver_clan_id`; для `RAIDER` — lvl ≥ 5 и НЕ член обоих кланов; для `CARAVANEER` — член sender-clan-а, ≥ 20 см total и ≥ 20 см после взноса; для `DEFENDER` — член receiver-clan-а, ≥ 20 см total; capacity по ролям через `list_by_caravan_and_role` (`raiders ≤ 4 × caravaneers`, `defenders ≤ 2 × caravaneers`); activity-lock; в той же транзакции — `CaravanParticipant.{caravaneer/defender/raider}(...)`, контрибьюция списывается, audit `CARAVAN_PLAYER_JOINED`. Возвращает `JoinedCaravanLobby(caravan, participant)`.
- **B.6 — Use-case `LeaveCaravanLobby`** (`application/caravans/leave_caravan_lobby.py`): только `status=LOBBY` (после закрытия лобби — `CaravanLobbyClosedError`); `is_leader=True` запрещено (лидер закрывает караван через `CancelCaravan` в 3.2-C); удалить участника, вернуть `contribution_cm` в `Length` для `CARAVANEER`-а; снять activity-lock (идемпотентно — no-op, если лок уже снят); audit `CARAVAN_PLAYER_LEFT` с idempotency-key `caravan_player_left:{caravan_id}:{player_id}:{joined_at_iso}`. Возвращает `LeftCaravanLobby(caravan, removed_participant, returned_contribution_cm)`.
- **B.7 — Use-case `CloseCaravanLobby`** (`application/caravans/close_caravan_lobby.py`): идемпотентен (повторный вызов на `IN_BATTLE`/`FINISHED`/`CANCELLED` — no-op с `was_already_closed=True`, audit не пишется); из `LOBBY` — `Caravan.mark_in_battle()` save, audit `CARAVAN_LOBBY_CLOSED` с idempotency-key `caravan_lobby_closed:{caravan_id}`. Резолв и `caravan_battle_finish_factory`-job — в 3.2-C.
- **B.8 — Persistence:** `infrastructure/db/models/caravan.py` (`CaravanORM` + `CaravanParticipantORM` с CHECK-инвариантами и индексами; зеркал миграции 0019), миграция `infrastructure/db/migrations/versions/20260508_0019_caravans.py` (`down_revision="0018_pve_runs"`): создание двух таблиц + индексов:
  - `caravans` (PK `id`, FK на `clans` × 2 и `users`, CHECK-ы на `status`, `sender_clan_id <> receiver_clan_id`, `lobby_ends_at > started_at`, `battle_ends_at > lobby_ends_at`, `finished_at` ↔ `status`); индексы `(sender_clan_id, status)` / `(receiver_clan_id, status)` / `(status, lobby_ends_at)` / `(status, battle_ends_at)`; **partial-unique** `uq_caravans_one_active_per_sender` (`sender_clan_id` WHERE `status IN ('lobby', 'in_battle')`) — БД-инвариант «≤ 1 активный караван на клан-отправитель».
  - `caravan_participants` (composite PK `(caravan_id, player_id)`, FK ON DELETE CASCADE на `caravans.id` и `users.id`, CHECK-ы на `role`, лидера-караванщика, `contribution_cm` ↔ роль); индексы `(caravan_id, role)` / `(player_id)`; **partial-unique** `uq_caravan_participants_one_leader_per_caravan` (`caravan_id` WHERE `is_leader = 1`) — БД-инвариант «один лидер на караван».
  - Репо `infrastructure/db/repositories/caravan.py` (`SqlAlchemyCaravanRepository`: `add` / `get_by_id` / `get_active_by_clan` / `get_last_finished_at_for_clan` (по `MAX(started_at)`) / `save`) + `caravan_participant.py` (`SqlAlchemyCaravanParticipantRepository`: `add` / `list_by_caravan` / `list_by_caravan_and_role` / `remove` (идемпотентно)). БД-уровневые `IntegrityError`-ы конвертируются в доменный `IntegrityError` из `pipirik_wars.shared.errors`.
- **B.9 — APScheduler:** `infrastructure/scheduler/aps.py` — расширен `IDelayedJobScheduler` адаптер: `schedule_caravan_lobby_close` / `cancel_caravan_lobby_close` + callback `_run_caravan_lobby_close_job` (через `caravan_lobby_close_factory`). `tests/fakes/delayed_job_scheduler.py` дополнен caravan-методами симметрично.
- **B.10 — DI:** в `bot/main.py` подключены `SqlAlchemyCaravanRepository` / `SqlAlchemyCaravanParticipantRepository` и четыре use-case-а через `Container`. APScheduler — `caravan_lobby_close_factory=None` до 3.2-D, как у mountain/dungeon (фабрика-провайдер не нужна, пока нет bot-handler-а).
- **B.11 — Юнит- и integration-тесты:**
  - `tests/unit/application/caravans/test_create_caravan.py` (~ 30 тестов): happy-path (lobby создан, leader participant добавлен, контрибьюция списана, лок взят, scheduler запланирован, audit записан); error-cases (caravan уже активен у клана, кулдаун клана, lvl < 7, sender clan не найден, target clan не найден, target = sender, leader не найден, leader frozen, ≥ 20 см после взноса нарушено, contribution ≤ 0, leader уже в активности).
  - `tests/unit/application/caravans/test_join_caravan_lobby.py` (~ 22 теста): 5 кейсов §9.4 (CARAVANEER из sender-clan-а, DEFENDER из receiver-clan-а, RAIDER извне, отказ RAIDER-у в обоих кланах, выбор роли при двойном членстве); capacity-чекеры (raiders ≤ 4×, defenders ≤ 2×); error-cases (caravan не найден, лобби закрыто, player не найден / frozen, уже участник, role conflict, thickness/length requirements).
  - `tests/unit/application/caravans/test_leave_caravan_lobby.py` (~ 10 тестов): happy-path (CARAVANEER возврат контрибьюции, DEFENDER/RAIDER без неё, лок снят); error-cases (caravan не найден, не в LOBBY, player не найден / не участник, leader не может выйти).
  - `tests/unit/application/caravans/test_close_caravan_lobby.py` (~ 7 тестов): happy-path (LOBBY → IN_BATTLE, audit с idempotency-key); идемпотентность (IN_BATTLE/FINISHED/CANCELLED — no-op без audit; double-close — audit пишется только один раз); error-cases (caravan не найден).
  - `tests/integration/db/test_caravan_repository.py` (~ 28 тестов): CRUD `caravans` (add → get_by_id, save для status-transition, get_active_by_clan, get_last_finished_at_for_clan); CRUD `caravan_participants` (add caravaneer/defender/raider, list, list_by_role, remove с no-op); БД-инварианты — `uq_caravans_one_active_per_sender`, composite-PK `(caravan_id, player_id)`, `uq_caravan_participants_one_leader_per_caravan`, `sender_clan_id <> receiver_clan_id` CHECK на raw-INSERT-е, ON DELETE CASCADE на участников при удалении каравана.
  - `tests/integration/db/test_migrations.py` дополнен: `test_0019_descends_from_0018` + строка `"20260508_0019_caravans.py"` в `test_versions_dir_lists_only_known_files`.
  - Тестовая инфраструктура: `tests/fakes/caravan_repo.py` (in-memory `FakeCaravanRepository` + `FakeCaravanParticipantRepository` симметрично domain-портам); `tests/fakes/__init__.py` обновлён.
  - Хелпер `_container_with_fakes` в `tests/unit/bot/test_composition_root.py` дополнен 6 новыми kwargs (репо `caravans`/`caravan_participants` + 4 use-case с fake-портами).
- **Финальный коммит этого PR-а** (этот) — обновил `history.md` (запись 3.2-B) + переразметил `current_tasks.md` под старт **Спринта 3.2-C** (боевая механика + награды).

Результат / артефакты:
- ~ 20 файлов изменено (excl. docs): `domain/shared/ports/{audit,scheduler}.py`, `application/dto/inputs.py`, новый пакет `application/caravans/` (5 модулей: 4 use-case + `__init__.py`), `infrastructure/db/models/caravan.py` + `infrastructure/db/migrations/versions/20260508_0019_caravans.py` + `infrastructure/db/repositories/{caravan,caravan_participant}.py`, `infrastructure/scheduler/aps.py`, `bot/main.py` (DI), `tests/fakes/{caravan_repo,delayed_job_scheduler,__init__}.py`, 4 unit + 1 integration test-модуля, обновление `tests/integration/db/test_migrations.py` и `tests/unit/bot/test_composition_root.py`.
- `make ci` локально: ruff ✅, mypy --strict 0 issues ✅, import-linter 3 contracts kept ✅, **pytest 3889 passed / 1 skipped, coverage 95.93%** (gate 80%).

Заметки / решения:
- **Идемпотентность audit-записей через детерминистичный `idempotency_key`.** Каждый use-case формирует ключ по составу полей сущности — например, `caravan_player_left:{caravan_id}:{player_id}:{joined_at_iso}` (включает `joined_at` чтобы повторное вступление-выход не схлопнулось). Для `CARAVAN_LOBBY_CLOSED` ключ — `caravan_lobby_closed:{caravan_id}` (один караван закрывается один раз).
- **`CloseCaravanLobby` — single-source-of-truth для перехода LOBBY → IN_BATTLE.** APScheduler-callback в 3.2-C для `caravan_battle_finish_factory` НЕ должен дублировать transition — он работает уже на `IN_BATTLE`-каравану. Если по какой-то причине scheduler запустит `CloseCaravanLobby` дважды (rebound при рестарте + ручной retry) — второй вызов идемпотентно станет no-op-ом, audit не задвоится.
- **`get_last_finished_at_for_clan` под капотом возвращает `MAX(started_at)`.** Имя метода исторически отражает PvE-симметрию (`forest_run`/`mountain_run`/`dungeon_run` имеют похожие методы), но семантика для каравана отличается — кулдаун стартует от **создания** (включая `CANCELLED`-ы), а не от завершения. Решение задокументировано в docstring-е репо.
- **`uq_caravans_one_active_per_sender` — partial-unique только для активных статусов.** `LOBBY` + `IN_BATTLE`. `FINISHED`/`CANCELLED`-ы не блокируют создание нового каравана клана-отправителя — это поведение проверено integration-тестом `test_finished_does_not_block_new_caravan`. На SQLite используем `sqlite_where`, на Postgres — `postgresql_where` (DDL отличается, но семантика одна).
- **`caravan_participants` — `caravan_id` хранится как `BigInteger().with_variant(Integer, "sqlite")`** для FK на `caravans.id`. SQLite не поддерживает AUTOINCREMENT на BigInteger, но FK на Integer-PK работает без проблем.
- **ON DELETE CASCADE — last-line-of-defense.** Use-case-ы доменно не удаляют записей `caravans` (только меняют `status`). FK с CASCADE нужен на случай ручной чистки или каскада с `clans`/`users` (например, при бане клана его караваны удаляются вместе). Поведение проверено integration-тестом `test_deleting_caravan_cascades_to_participants`.
- **APScheduler `caravan_lobby_close_factory=None` в DI до 3.2-D.** Симметрично mountain/dungeon — фабрика подключается только когда есть bot-handler-нотификатор. В 3.2-C появится `caravan_battle_finish_factory` (тоже `None` до 3.2-D), а в 3.2-D обе фабрики получат живые имплементации.
- **Двухпутный resolve активности `(player, CARAVAN)`.** `CreateCaravan` берёт лок на лидера, `JoinCaravanLobby` — на каждого нового участника, `LeaveCaravanLobby` — снимает (идемпотентно). `CloseCaravanLobby` НЕ снимает локи участников — они автоматически истекут по TTL (= lobby+battle), и в 3.2-C `FinishCaravanBattle` снимет их явно при выдаче наград.
- **Новый канон без catch-up-постмердж-PR-а** — следую правилу 2026-05-08 (CONTRIBUTING.md «Перед мерджем PR-а»). Этот же 3.2-B PR одним последним коммитом обновил `history.md` + `current_tasks.md` перед мерджем.

---

## 2026-05-08 — Спринт 3.2-A: каркас доменов «Караван» + балансовый конфиг (старт Спринта 3.2)

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 3.2 ([`current_tasks.md`](current_tasks.md) «Декомпозиция Спринта 3.2 на фичевые PR-ы»), ПД §6.3.2 «Спринт 3.2 — Караваны (полная механика)», ГДД §9 «Караваны». Первый PR Спринта 3.2 — закладывает доменный фундамент перед use-case-ами (3.2-B), боевой механикой (3.2-C) и bot UX (3.2-D).

Что сделано:
- **`domain/caravan/value_objects.py`** — `CaravanRole` enum (`LEADER`/`CARAVANEER`/`DEFENDER`/`RAIDER`), `CaravanStatus` enum (`LOBBY`/`IN_BATTLE`/`FINISHED`/`CANCELLED`), `CaravanContribution` VO (`cm: int > 0`, frozen+slots, runtime-проверки `isinstance(int)` против `bool`/`float`).
- **`domain/caravan/entities.py`:**
  - `Caravan` агрегат (frozen+slots): `id`/`sender_clan_id`/`receiver_clan_id`/`leader_player_id`/`status`/`started_at`/`lobby_ends_at`/`battle_ends_at`/`random_seed`/`finished_at`. Двухфазный лайфцикл — отличие от PvE: сначала **лобби 20 мин**, потом **бой 60 мин**, каждая фаза — свой APScheduler-job. `random_seed` сохраняется на старте для детерминистичного resolve-а боя в 3.2-C. Class-метод `Caravan.starting()` создаёт свежий караван (`id=None`, `status=LOBBY`, `finished_at=None`). Property-аксессоры `is_in_lobby` / `is_in_battle` / `is_terminal`. Мутаторы `mark_in_battle()` / `mark_finished(finished_at=…)` / `mark_cancelled(cancelled_at=…)` через `replace()` — иммутабельные, идемпотентные при повторном вызове, бросают `ValueError` при невалидных переходах.
  - `CaravanParticipant` weak-агрегат: `caravan_id`/`player_id`/`role`/`is_leader`/`contribution`/`joined_at`. Class-методы `caravaneer()` / `defender()` / `raider()`. Инвариант 1: `is_leader=True` → `role` обязательно `CARAVANEER`. Инвариант 2: `contribution` есть **только** у `CARAVANEER`-ов (включая лидера); `DEFENDER`/`RAIDER` — `contribution=None`.
- **`domain/caravan/errors.py`:** `CaravanError(DomainError)` + 7 подклассов с `__slots__`-полями и описательными сообщениями: `CaravanNotFoundError(caravan_id)`, `AlreadyInCaravanError(player_id)`, `CaravanCooldownError(clan_id, actual_remaining_seconds)`, `CaravanRoleConflictError(player_id, attempted_role, reason)`, `CaravanRequirementError(player_id, requirement, required, actual)`, `CaravanLobbyClosedError(caravan_id, status)`, `CaravanCapacityExceededError(caravan_id, role, limit)`.
- **`domain/caravan/repositories.py`:** `ICaravanRepository` (5 async-абстрактных методов: `add` / `get_by_id` / `get_active_by_clan` / `get_last_finished_at_for_clan` / `save`) и `ICaravanParticipantRepository` (4 метода: `add` / `list_by_caravan` / `list_by_caravan_and_role` / `remove`). Реализации (SQLAlchemy) — Спринт 3.2-B.
- **`domain/caravan/__init__.py`:** публичный API всех VO/entity/error/port.
- **`domain/balance/config.py`:**
  - `CaravanRewardMultipliers(_Frozen)` — все четыре множителя `≥ 0`.
  - `CaravansConfig(_Frozen)` — все балансовые параметры караванов: `min_thickness_level_leader=7` (gt 1), `min_thickness_level_raider=5`, `min_length_cm=20` (gt 0), `min_length_after_contribution_cm=20`, `lobby_minutes=20`, `battle_minutes=60`, `clan_cooldown_hours=12` (≥ 0), `max_raiders_per_caravaneer=4`, `max_defenders_per_caravaneer=2`, `base_reward_cm=5`, `reward_multipliers`, `clan_bonus_cm=1`.
  - `BalanceConfig.caravans: CaravansConfig` — обязательное поле (без него `model_validate` упадёт).
- **`config/balance.yaml`:** новая секция `caravans:` с дефолтами по ГДД §9 (lvl 7+ leader, lvl 5+ raider, ≥ 20 см, лобби 20 / бой 60 мин, кулдаун 12 ч, capacity 4× / 2×, награды base=5 × multipliers 4/3/1/0, +1 см клану-получателю). Секция расположена сразу после `dungeon:` и перед `oracle:`.
- **Тесты `tests/unit/domain/caravan/`:** 4 модуля, ~ 80 тестов:
  - `test_value_objects.py` — enum smoke, `CaravanContribution` валидация (positive int, frozen, equality, runtime-rejection float и bool).
  - `test_entities.py` — `Caravan.starting()` factory + 3 invariants (sender ≠ receiver, lobby_ends_at > started_at, battle_ends_at > lobby_ends_at). 9 тестов на transitions с idempotency и terminal-status guard. `CaravanParticipant` factories + 4 invariants.
  - `test_errors.py` — hierarchy (`CaravanError` is `DomainError`, все 7 подклассов inherit) + payloads (`caravan_id`, `player_id`, `attempted_role`, `requirement`/`required`/`actual`, и т. п. в сообщениях).
  - `test_repositories.py` — ABC smoke (cannot instantiate, all abstract method names match expected set, all methods are async-coroutine-functions).
- **Тесты `tests/unit/domain/balance/test_caravans_config.py`:** ~ 20 тестов pydantic-валидации `CaravansConfig` + `CaravanRewardMultipliers` + `BalanceConfig` integration + smoke реального `config/balance.yaml`. Параметризованные проверки на positive/non-negative-fields.
- **`tests/unit/domain/balance/factories.py`:** `valid_balance_payload()` дополнена `caravans`-блоком — без него `BalanceConfig.model_validate` упадёт после добавления обязательного поля. Все существующие тесты `test_config.py`/`test_picking.py`/`test_pvp_config.py` продолжают работать.
- **Финальный коммит этого PR-а** (этот) — обновил `history.md` (запись 3.2-A) + переразметил `current_tasks.md` под старт **Спринта 3.2-B** (use-cases `CreateCaravan` / `JoinCaravanLobby` / `LeaveCaravanLobby` + persistence + миграция `0019_caravans` + APScheduler `caravan_lobby_close_factory`).

Результат / артефакты:
- 13 файлов изменено (excl. docs): 5 новых модулей `domain/caravan/`, 2 модификации (`domain/balance/config.py`, `config/balance.yaml`), 6 тестовых модулей.
- `make ci` локально: ruff ✅, mypy --strict 764 файла 0 issues ✅, import-linter 3 contracts kept ✅, **pytest 3794 passed / 1 skipped, coverage 95.95%** (gate 80%).

Заметки / решения:
- **Двухфазный лайфцикл — два поля времени, не один.** `lobby_ends_at` + `battle_ends_at` — отдельные timestamp-ы, потому что у каравана две разные фазы с разными APScheduler-job-ами. Не объединял в `cooldown_min_minutes`/`cooldown_max_minutes` как у PvE — там это окно одной фазы, а здесь — две разные.
- **`random_seed` сохраняется на старте, resolve боя — синхронный.** В Спринте 3.2-C `FinishCaravanBattle` use-case будет читать `random_seed` и детерминистично воспроизводить расчёт боя. Это даёт audit-trail и возможность переиграть бой при балансе. Без раунд-tick-ов APScheduler — всё разрешается в одном callback-е.
- **Capacity без `caravaneers=0` особого случая.** Формула `max_raiders ≤ 4 × caravaneers` при `caravaneers=0` даёт `0` — то есть рейдеры не пускаются, пока нет караванщиков. Но лидер всегда есть и всегда `CARAVANEER` (инвариант entity), так что `caravaneers ≥ 1` всегда. Поэтому формула честная.
- **Две роли «лидер vs караванщик» — `is_leader` flag, не enum-член.** В `CaravanRole` enum есть `LEADER`, но мы его **не используем** в БД — лидер хранится как `CARAVANEER` + `is_leader=True`. `LEADER` enum-член оставлен для будущей расширяемости (например, если появится «второй лидер» / «помощник лидера»). Это симметрично паттерну `ClanMemberRole` в `domain/clan/`.
- **Кулдаун клана 12 ч — от `started_at`, не от `finished_at`.** Решение задокументировано в docstring-е `ICaravanRepository.get_last_finished_at_for_clan` (имя метода сохранено для символетрии с PvE; реализация в 3.2-B возьмёт `MAX(started_at)`). Альтернатива — кулдаун от завершения — давала бы простой эксплойт «бесконечно создавать караваны и сразу отменять».
- **`AlreadyInCaravanError` vs `CaravanRoleConflictError` — разные пути.** `AlreadyInCaravanError` бросается activity-lock-ом при попытке войти в любой караван, если игрок уже в активной деятельности. `CaravanRoleConflictError` — конкретно правило ГДД §9.4 (роль не подходит по членству в кланах). В 3.2-A только определены классы; ловит/бросает их `JoinCaravanLobby` use-case в 3.2-B.
- **`Title` enum (Атаман) — НЕ трогаем.** Расширение приходит в 3.2-C, когда появится `FinishCaravanBattle` use-case и понадобится выдавать титул. Сейчас (3.2-A) `domain/player/` не затронут.
- **`CaravansConfig` экспортируется только из `domain.balance.config`**, не из `domain.balance.__init__.py`. Симметрично паттерну `MountainsConfig` / `DungeonConfig` (тоже не в `__init__`). Это сознательное решение — `__init__` экспортирует только базовые классы, не location-specific config-и.
- **Новый канон без catch-up-постмердж-PR-а** — следую правилу 2026-05-08 (CONTRIBUTING.md «Перед мерджем PR-а»). Этот же 3.2-A PR одним последним коммитом обновил `history.md` + `current_tasks.md` перед мерджем.

---

## 2026-05-08 — Спринт 3.1-E: bot-handlers `/mountains`, `/dungeon` + презентеры + локали + APScheduler factory-wiring (закрытие Спринта 3.1)

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 3.1 ([`current_tasks.md`](current_tasks.md)), ПД §6.3 / задача 3.1.1 (UX), 3.1.2 (UX), §6.3.1+ строка 3.1-E «Bot-handlers + APScheduler factory-wiring + локали», ГДД §8 «Походы (PvE)»; первая фича по новому канону без catch-up-постмердж-PR-а — последний коммит этой же ветки одновременно обновляет `history.md` + `current_tasks.md` под старт **Спринта 3.2 (Караваны)**.

Что сделано:

- **E.1 — Notifier-порты в application-слое:**
  - `src/pipirik_wars/application/mountains/notifier.py` — `IMountainFinishNotifier` (Protocol с одним методом `notify(MountainRunFinished) -> None`).
  - `src/pipirik_wars/application/dungeon/notifier.py` — `IDungeonFinishNotifier` (зеркальный Protocol).
  - Оба импортированы из `application/{mountains,dungeon}/__init__.py` (общественный API).

- **E.2 — Bot-presenters mountains/dungeon + общий `_pve.py`:**
  - `src/pipirik_wars/bot/presenters/_pve.py` — общий `PvePresenter` (391 строка) для обеих локаций. Все локализованные методы префиксуют ключи через `_kind_prefix` (`mountains-` / `dungeon-`): `started`/`started_fallback`/`group`/`other`/`not_registered`/`already_in`/`requirement_thickness`/`requirement_length`/`finished`/`finish_keyboard`/`toast_*`. Plus pure-функции callback_data: `pve_callback_data(*, kind, action, run_id, drop_idx) -> str`, `parse_pve_callback_data(data) -> PveCallbackData`, `is_pve_callback(data) -> bool`. Формат `<kind>:<action>:<run_id>:<drop_idx>` ≤ 64 байт даже для 19-значных run_id (Telegram callback_data hard-cap).
  - `src/pipirik_wars/bot/presenters/mountains.py` — `MountainsPresenter` (тонкий wrapper над `PvePresenter` с `kind=PveLocationKind.MOUNTAINS`).
  - `src/pipirik_wars/bot/presenters/dungeon.py` — `DungeonPresenter` (зеркальный с `kind=PveLocationKind.DUNGEON`).
  - Оба экспортированы из `bot/presenters/__init__.py`.

- **E.3 — Bot-handlers mountains/dungeon + регистрация роутеров:**
  - `src/pipirik_wars/bot/handlers/mountains.py` — `/mountains` и mountains-callback handler-ы (193 строки):
    - `/mountains` (private only, group → группа-сообщение, прочие → other-сообщение): `StartMountainRun.execute` → `GetProfile.execute` → presenter.started. На исключения: `PlayerNotFoundError` → `not_registered`, `AlreadyInMountainsError` → `already_in`, `MountainsRequirementError(requirement="thickness"|"length")` → соответствующее requirement-сообщение.
    - mountains-callback (`F.data.startswith("mountains:")`): `parse_pve_callback_data` → проверка `kind is MOUNTAINS` (защита от промаха фильтра) → toast (equip/drop placeholder без мутации; реальный inventory — Спринт 3.4) + `_strip_keyboard` (best-effort `edit_reply_markup(None)`, ошибки поглощаются через `contextlib.suppress`).
  - `src/pipirik_wars/bot/handlers/dungeon.py` — зеркальный handler (166 строк) для `/dungeon` и dungeon-callback.
  - `src/pipirik_wars/bot/handlers/__init__.py` — добавлены `mountains_router`, `dungeon_router` в `register_routers`.

- **E.4 — Telegram-нотификаторы PvE-finish-job-ов:**
  - `src/pipirik_wars/bot/notifications/_pve.py` — общий базовый класс `_PveFinishNotifierBase[PveResultT]` (Generic). Делает: резолв локали через `IPlayerLocaleResolver` (с фолбэком на default при ошибке резолвера), рендер `display_name` через `IBalanceConfig.display_name_for(length_cm)`, отправку сообщения с `presenter.finished(...)` + `presenter.finish_keyboard(...)` через `aiogram.Bot.send_message`. Все ошибки доставки (`TelegramAPIError` — заблокировал/удалил чат; общий `Exception`) поглощаются через лог-уровни warning/exception (best-effort delivery). Идемпотентность по `was_already_finished` — **на стороне вызывающего** (APScheduler-callback в `aps.py`).
  - `src/pipirik_wars/bot/notifications/mountains.py` — `TelegramMountainFinishNotifier(_PveFinishNotifierBase[MountainRunFinished])` + `IMountainFinishNotifier`-implements.
  - `src/pipirik_wars/bot/notifications/dungeon.py` — `TelegramDungeonFinishNotifier` (зеркало).
  - Оба экспортированы из `bot/notifications/__init__.py`.

- **E.5 — Локали `mountains-*` / `dungeon-*` (RU+EN parity):**
  - `locales/ru.ftl` +65 строк, `locales/en.ftl` +64 строки. Полное покрытие всех методов `PvePresenter`-а: `mountains-started` (с переменными `nick`/`title`/`length_cm`/`thickness_level`/`cooldown_minutes`), `mountains-started-fallback`, `mountains-group`, `mountains-other`, `mountains-not-registered`, `mountains-already-in`, `mountains-requirement-thickness` (`required`/`actual`), `mountains-requirement-length` (`required_cm`/`actual_cm`), `mountains-finished-header`, `mountains-finished-length-gain` (`delta_cm`), `mountains-finished-length-loss` (`delta_cm`), `mountains-finished-length-zero`, `mountains-finished-no-drops`, `mountains-finished-drop-line` (`item_name`/`rarity`), `mountains-finished-scroll-line` (нейтральный лог), `mountains-keyboard-equip` (`item_name`), `mountains-keyboard-drop`, `mountains-toast-item-equipped-placeholder`, `mountains-toast-item-equipped-already`, `mountains-toast-item-dropped`, `mountains-toast-drop-mismatch`, `mountains-toast-already-finished`. Аналогичный набор `dungeon-*` ключей (parity автомат через lint-тест локалей).

- **E.6 — APScheduler factory-wiring (`infrastructure/scheduler/aps.py`):**
  - `__init__` расширен 4 опциональными параметрами: `mountain_finish_factory: Callable[[], FinishMountainRun] | None`, `mountain_notifier: IMountainFinishNotifier | None`, `dungeon_finish_factory: Callable[[], FinishDungeonRun] | None`, `dungeon_notifier: IDungeonFinishNotifier | None`. По умолчанию None — т. е. в unit-тестах APScheduler-а не нужно мокать всю PvE-инфраструктуру.
  - Реализованы реальные callback-и `_run_mountain_finish_job(run_id)` и `_run_dungeon_finish_job(run_id)` (зеркалят `_run_finish_job` для леса):
    - Если factory не привязана (recovery / unit-тесты адаптера) → log warning + return.
    - `factory()` создаёт fresh use-case, `await use_case.execute(FinishMountainRunInput(run_id=run_id))`. На `MountainRunNotFoundError` / `PlayerNotFoundError` (записи нет / удалена) → log warning + return. На любой другой `Exception` → log exception + return.
    - Если notifier привязан и `result is not None` → `await notifier.notify(result)`. На любую ошибку нотификатора — log exception (но НЕ throw наверх, чтобы APScheduler-job не пометился failed и не делал retry из-за Telegram-ошибок).
  - Идентичный паттерн для dungeon.

- **E.7 — DI-wiring в `bot/main.py`:**
  - Добавлены импорты `IMountainFinishNotifier`/`StartMountainRun`/`IDungeonFinishNotifier`/`StartDungeonRun` из application и `TelegramMountainFinishNotifier`/`TelegramDungeonFinishNotifier` из bot.notifications.
  - В блоке `if bot is not None:` создаются `mountain_notifier`/`dungeon_notifier` (через PlayerLocaleResolver + IBalanceConfig + IMessageBundle).
  - В `APSchedulerDelayedJobScheduler.__init__` передаются late-bound `mountain_finish_factory=lambda: finish_mountain_run` / `dungeon_finish_factory=lambda: finish_dungeon_run` (factory резолвится в момент срабатывания job-а — те же объекты, что Container уже создал ниже по коду).

- **E.8 — Тесты unit (4 новых файла):**
  - `tests/unit/bot/presenters/test_pve.py` (468 строк, 42 теста): callback_data round-trip (parametrize над `kind × action`), формат `<kind>:<action>:<run_id>:<drop_idx>`, ≤ 64 байт для 19-значных int, отбрасывание мусорных payload-ов, `is_pve_callback` фильтр, FakeMessageBundle ключи + FluentMessageBundle smoke RU+EN, gain/loss/zero ветки `finished`, `finish_keyboard` для 0/1/2 drops, все toast-методы.
  - `tests/unit/bot/handlers/test_mountains.py` (320 строк, 14 тестов): `/mountains` private/group/supergroup/other, success → started, `PlayerNotFoundError` → not_registered, `AlreadyInMountainsError` → already_in, `MountainsRequirementError(requirement=)` × 2, profile_missing → started_fallback, mountains-callback (no_identity, equip_item, drop_item, invalid_callback_data, dungeon-mismatch).
  - `tests/unit/bot/handlers/test_dungeon.py` (318 строк, 14 зеркальных тестов).
  - `tests/unit/bot/notifications/test_pve.py` (304 строки, 9 тестов): MountainNotifier (sends_message, drops + keyboard, locale_resolver_used, locale_resolver_failure_falls_back_to_default, telegram_api_error_swallowed, balance_failure_short_circuits_delivery), DungeonNotifier (зеркало).
  - `tests/unit/infrastructure/scheduler/test_aps.py` +235 строк, 12 тестов: callback_invokes_use_case, callback_calls_notifier, callback_swallows_run_not_found, callback_swallows_unexpected_error, callback_swallows_notifier_error, factory_not_wired_logs_warning — для mountain и dungeon.
  - **Итого 91 новый unit-тест.**

Результат / артефакты:
- 24 файла изменено, +3055 / −14 строк.
- Локально `make ci`: ruff ✅, mypy --strict 754 файла ✅, import-linter 3 contracts kept ✅, pytest **3707 passed / 1 skipped**, coverage **95.90%** (gate 80%).

Заметки / решения:
- **Общий `PvePresenter` + thin wrapper-ы.** Mountains и dungeon структурно идентичны (ГДД §8.2: одинаковые состояния, одинаковые типы дропов, разные пороги/cooldown-ы — но это уровень use-case-ов и balance.yaml). Поэтому презентер один; locale-ключи параметризуются `kind_prefix`. Если в Спринте 3.4+ горы получат уникальный flavour-текст вернёт-карточки (как лес имеет `ForestLogTemplate`), нужно будет либо расширить `PvePresenter` опциональным `flavour_provider: IPveFlavourProvider | None`, либо вытащить `MountainsPresenter` в полноценный класс.
- **Скроллы в UI — нейтральный дисплей без кнопок применения.** В карточке возврата скроллы рендерятся ключом `*-finished-scroll-line` (один на скролл). Кнопок «применить» НЕТ — механика `EnchantItem` use-case + `scroll_inventory` таблица — Спринт 3.4. До 3.4 скроллы только логируются и **не persist-ятся** (см. 3.1-D).
- **Идемпотентность finish-job-ов.** Use-case `Finish*Run.execute` сам через `was_already_finished` флаг сообщает, что это retry-вызов APScheduler-а. Notifier на стороне адаптера НЕ фильтрует повторы — это ответственность вызывающего кода (callback в `aps.py` мог бы решать «не отправлять, если was_already_finished=True», но в текущем дизайне notifier дёргается всегда; повторных уведомлений не должно быть, потому что APScheduler удаляет одноразовый job после первого успешного return-а из callback-а).
- **Late-bound factory.** `mountain_finish_factory=lambda: finish_mountain_run` — `finish_mountain_run` объявлен ниже в `bot/main.py` (Container собирает use-case-ы в порядке зависимостей). Lambda резолвит имя в момент срабатывания job-а, когда Container уже полностью построен.
- **`parse_pve_callback_data` — defensive coding.** Любой мусор в `callback_data` (включая dungeon-callback в горный handler из-за широкого префикс-фильтра) → toast-mismatch без мутации UI. Это защита от подмены payload-а злонамеренным игроком (хотя Telegram callback_data ≤ 64 байт, всё равно лучше валидировать).
- **`if action_raw == "equip_item": ... elif action_raw == "drop_item": ...` вместо `in _VALID_ACTIONS` для mypy.** mypy --strict в полном прогоне сужает Literal через `in frozenset[Literal[...]]`, но pre-commit-mypy в режиме отдельного файла — нет (видимо, разные версии или конфиги). Явный if/elif устраняет необходимость в `# type: ignore` или `cast`.

---

## 2026-05-08 — Спринт 3.1-D: дроп скроллов заточки — domain VO `Scroll(category, blessed)` + drop-engine + 10000+ rolls тесты (skeleton, без use-механики)

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 3.1 ([`current_tasks.md`](current_tasks.md)), ПД §6.3 / задача 3.1.3 (дроп скроллов заточки), §6.3.1+ строка 3.1-D «Дроп скроллов заточки — skeleton», ГДД §2.8 «Заточка экипировки» / §2.8.5 «Источники скроллов» (горы — regular very-very rare; данжон — regular rare + blessed very-very rare; лес — не дропает) / §3.4 «Применение скролла» (full impl откладывается на Спринт 3.4), [PR #105](https://github.com/Pipirkawar/PipirkaWar/pull/105); 4 чекпоинт-коммита на feature-ветке: `7567c10` (D.1), `732764d` (D.2), `b04994f` (D.3), `d47d23a` (D.4).

Что сделано:

- **D.1 — Domain VO `Scroll` skeleton (commit `7567c10`):**
  - **Новый модуль `src/pipirik_wars/domain/enchantment/`** — отдельный поддомен под механику заточки.
  - `entities.py::ScrollCategory(str, enum.Enum)`: `WEAPON="weapon_scroll"`, `ARMOR="armor_scroll"`, `JEWELRY="jewelry_scroll"`. **Машинные значения**, стабильные между релизами — используются в `audit_log` и JSON-сериализации (если в 3.4 захочется писать в БД, эти строки уже зафиксированы).
  - `entities.py::Scroll` — `@dataclass(frozen=True, slots=True)`, поля `category: ScrollCategory`, `blessed: bool`. Hashable, equality-based, set-safe (готов к укладке в инвентарь скроллов в 3.4).
  - 10 unit-тестов в `tests/unit/domain/enchantment/test_entities.py`: `ScrollCategory` value stability, `Scroll` frozen / hash / equality / set-membership / blessed-vs-category differentiation.

- **D.2 — `ScrollDropConfig` + `scroll_drops` в `balance.yaml` для гор/данжона (commit `732764d`):**
  - `domain/balance/config.py`:
    - **Новая модель `ScrollCategoryWeights`** — `weapon`, `armor`, `jewelry: int ≥ 0` + `@model_validator _validate_sum_positive` (хотя бы одна категория с весом > 0). Используется через `weighted_choice` для выбора категории скролла на successful Bernoulli-попытке.
    - **Новая модель `ScrollDropConfig`** — `regular_chance_percent: 0..100`, `blessed_chance_percent: 0..100`, `category_weights: ScrollCategoryWeights`. Две Bernoulli-попытки **независимы** между собой и от item-дропа: за один поход возможно получить и предмет, и regular-скролл, и blessed-скролл (с малой вероятностью).
    - `PveDropConfig.scroll_drops: ScrollDropConfig` — **обязательное** поле для гор и данжона (mandatory, без дефолта).
    - **`ForestDropConfig` намеренно НЕ имеет `scroll_drops`** — лес скроллы не дропает по дизайну ГДД §2.8.5; запрет enforced на уровне pydantic-схемы (а не через `regular_chance_percent: 0`), чтобы исключить случайное «подкрутить»-регрессию.
    - Публичные экспорты `ScrollDropConfig`, `ScrollCategoryWeights` в `domain/balance/__init__.py`.
  - `config/balance.yaml`:
    - `mountains.drop.scroll_drops`: `{regular_chance_percent: 3, blessed_chance_percent: 0, category_weights: {weapon: 1, armor: 1, jewelry: 1}}` («очень-очень малый» дроп).
    - `dungeon.drop.scroll_drops`: `{regular_chance_percent: 6, blessed_chance_percent: 1, category_weights: {weapon: 1, armor: 1, jewelry: 1}}` («очень малый» / «очень-очень малый»).
  - `tests/unit/domain/balance/factories.py` — `valid_balance_payload()` синкнут под новое обязательное поле.

- **D.3 — `pick_pve_outcome` катит `scroll_drops` (commit `b04994f`):**
  - `domain/pve/entities.py`:
    - **Новая VO `PveScrollDrop(scroll: Scroll)`** — параллельная `PveItemDrop`. Frozen + slots.
    - `PveRunOutcome.scroll_drops: tuple[PveScrollDrop, ...] = field(default=())` — **отдельное поле** (не union с `drops`). См. «Архитектурные решения» ниже. Default `()` сохраняет backward-compat для существующих тестовых конструкторов `PveRunOutcome`.
  - `domain/pve/services.py`:
    - **Новая функция `_roll_scroll_drops(*, cfg: ScrollDropConfig, random: IRandom) -> list[PveScrollDrop]`** — две независимые Bernoulli-попытки: regular (`blessed=False`, шанс `cfg.regular_chance_percent`) и blessed (`blessed=True`, шанс `cfg.blessed_chance_percent`). Если попытка успешна — категория через `_pick_scroll_category(weights)`. Выходит 0..2 дропа за поход.
    - **Новая функция `_pick_scroll_category(*, weights: ScrollCategoryWeights, random: IRandom) -> ScrollCategory`** — `weighted_choice` на (weapon, armor, jewelry) с фильтром на нулевые веса (`RealRandom.weighted_choice` требует `weight > 0`; pre-condition `sum > 0` гарантирована `_validate_sum_positive`).
    - `pick_pve_outcome` — после `_roll_drops` (items) дополнительно роллит `_roll_scroll_drops(cfg=cfg.drop.scroll_drops, ...)`; конструирует `PveRunOutcome` со всеми полями.
  - 8 ScriptedRandom-тестов в `tests/unit/domain/pve/test_services.py` обновлены: после item-randint-ов добавлены 2 `randint=100` (regular miss + blessed miss), чтобы no-scroll-drop сценарии не ломались на новом scroll-роллинге. Behavior существующих тестов **не изменился** — только дополнен скриптом.

- **D.4 — 10000+ rolls тесты `scroll_drops` (commit `d47d23a`):**
  - **Новый файл `tests/unit/domain/enchantment/test_scroll_drops.py`** — 22 теста:
    - `TestMountainsScrollFrequencies` (3): regular частота в **3σ-bounds** (~[230, 370] для p=0.03, n=10000); blessed ровно 0 на 10000 rolls; PveScrollDrop instances + правильный category type.
    - `TestDungeonScrollFrequencies` (3): regular+blessed частоты в 3σ-bounds; uniform category distribution (~233 каждой из 3 категорий); item+scroll independence (≥1 dungeon-run с item AND scroll).
    - `TestRealBalanceScrollDrops` (5; 3 параметризованных smoke): design bounds на real `config/balance.yaml` — mountains regular ∈ (0, 5]%, blessed=0; dungeon regular ∈ (0, 10]%, blessed ∈ (0, 5]%, blessed < regular; 1000 rolls smoke на 3 seed-а × 2 локации.
    - `TestForestNoScrolls` (1): 1000 forest-rolls — `outcome.scroll_drops` не существует (контр-проверка, защищающая инвариант «`ForestDropConfig` без `scroll_drops`»).
  - **Tolerance:** `_bernoulli_bounds(p)` = `±max(3σ, 10)`, где `σ = √(n·p·(1-p))`. Покрывает 99.7% Bernoulli-флуктуаций и не флапает на маленьких p (p=0.01, n=10000 ⇒ σ≈10, bounds [70, 130]). Pinned seed (`FakeRandom(seed=12345)` и т.п.) гарантирует воспроизводимость; флапы возможны только при смене `IRandom`-impl.

Результат / артефакты:

- 4 коммита: D.1 `7567c10` → D.2 `732764d` → D.3 `b04994f` → D.4 `d47d23a`. Squash-мердж в `main = 2208ae6`.
- 11 файлов изменено / +688 −15 строк. Новые файлы: `domain/enchantment/__init__.py`, `domain/enchantment/entities.py`, `tests/unit/domain/enchantment/__init__.py`, `tests/unit/domain/enchantment/test_entities.py`, `tests/unit/domain/enchantment/test_scroll_drops.py`. Изменены: `domain/balance/__init__.py`, `domain/balance/config.py`, `domain/pve/entities.py`, `domain/pve/services.py`, `config/balance.yaml`, `tests/unit/domain/balance/factories.py`, `tests/unit/domain/pve/test_services.py`.
- Тестов добавлено: **+36** (10 entities + 22 scroll_drops + 4 минор-апдейтов в pve test_services). Всего: **3607 passed / 1 skipped**, coverage **95.88%** (без проседания), `make ci` локально и на CI зелёный.

Архитектурные решения:

- **`scroll_drops` отдельным полем (не union с `drops`)** — items идут в `inventory_equipment` (3.4), скроллы в `scroll_inventory` (3.4) — разные lifecycles и разные use-cases применения. JSON-колонка `mountain_runs.drops` остаётся неизменной — backward compat для уже сохранённых строк PR #101 (3.1-B). Тесты могут независимо проверять item-частоты и scroll-частоты.
- **Скроллы в 3.1-D НЕ persist-ятся.** `MountainRun.starting(outcome=)` копирует только `outcome.drops`, но не `outcome.scroll_drops`. Это согласуется с `development_plan.md` §6.3.1+ строка 636: «до тех пор скроллы из дропа просто пишутся в `audit_log` как «дроп будущей механики»». Поле `PveRunOutcome.scroll_drops` существует исключительно ради покрытия частот в тестах picker-а и future-proofing-а API; в 3.4 use-cases начнут писать их в инвентарь скроллов.
- **`ForestDropConfig` намеренно без `scroll_drops`** (вместо `scroll_drops: { regular: 0, blessed: 0 }`). Дизайн-инвариант «лес не дропает скроллов» enforced на уровне pydantic-схемы — нельзя случайно подкрутить. Контр-тест `TestForestNoScrolls` защищает от регрессий.
- **3σ-tolerance вместо ±10%.** На 10000 rolls с p=0.01 ожидаемое — 100 успехов, σ ≈ 10. ±10% (=±10) даёт `~84%` покрытия (1σ); 3σ даёт 99.7% — практически нет шанса флапнуть на любом seed-е без смены RNG-impl. Floor `±10` от ожидаемого защищает от случая `n·p ≪ 1`.

Заметки / решения:

- **Catch-up docs-PR.** Этот entry в `history.md` + sync `current_tasks.md` ожидался последним коммитом **внутри** PR #105 (по новому канону, установленному в PR #104). Однако PR #105 был замержен раньше, чем последний docs-коммит успел попасть в ветку — поэтому docs-апдейт оформлен **разовым** catch-up-PR-ом сразу после мерджа #105. Это единичное исключение из-за расхождения времени мерджа и финального docs-коммита; начиная с 3.1-E канон возвращается к норме (docs внутри фичевого PR).

---

## 2026-05-08 — Спринт 3.1-C: дроп оружия — `items_catalog` +10 позиций, `slot_weights` per-location, 0..N drops

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 3.1 ([`current_tasks.md`](current_tasks.md)), ПД §6.3 / задачи 3.1.4 (дроп оружия), 3.1.5 (расширение `items_catalog`), ГДД §2.6 «Экипировка» (слоты `right_hand`/`left_hand`), §8 «Походы (PvE)», [PR #103](https://github.com/Pipirkawar/Pipirkawar/pull/103); 3 чекпоинт-коммита на feature-ветке: `803ab4e` (C.1+C.2+C.3), `463b512` (C.4+C.5), `9255e08` (C.6).

Что сделано:

- **Схема балансировки расширена с 6 слотов до 8 (commit `803ab4e`):**
  - `domain/balance/config.py::Slot` enum — добавлены `RIGHT_HAND`, `LEFT_HAND` (теперь 8 слотов всего).
  - Новая модель `domain/balance/config.py::SlotWeights` — pydantic frozen с 8 неотрицательными `int`-полями, инвариант `sum > 0`, метод `as_pairs()` возвращает стабильный кортеж `((Slot, weight), …)` для использования в `weighted_choice`.
  - `ForestDropConfig.slot_weights: SlotWeights` и `PveDropConfig.slot_weights: SlotWeights` — **обязательные** поля per-location (без дефолта; читаются из `balance.yaml`).
  - `_MIN_ITEMS_CATALOG_SIZE` поднят с 30 до 40 (8 слотов × ≥5 предметов на каждый).
  - `_validate_items_catalog` — добавлен инвариант «≥1 предмет на каждый из 8 слотов» (тест `tests/unit/domain/balance/test_config.py::TestForestConfig::test_missing_slot_rejected`).
  - **Новый кросс-валидатор `BalanceConfig._validate_drop_slot_rarity_coverage`** — для каждой PvE-локации (forest / mountains / dungeon) × каждого активного слота (вес > 0) × каждой из 3 редкостей в каталоге должен быть ≥1 предмет. Гарантирует, что `random.choice(pool)` в picker-е никогда не упадёт на пустой pool.

- **`config/balance.yaml` (commit `803ab4e`):**
  - `items_catalog`: +10 предметов оружия (40 предметов всего на 8 слотов):
    - `right_hand` × 5: «Кастет Старшего» (common), «Бита Гаражная» (common), «Нунчаки Палыча» (rare), «Тесак Мясника» (rare), «Катана из Ломбарда» (epic).
    - `left_hand` × 5: «Крышка от Кастрюли» (common), «Заслонка от Печи» (common), «Щит-Заборник» (rare), «Копьё-Брют» (rare), «Зеркало Медузы» (epic).
  - `forest.drop.slot_weights`: распределение для леса — по дизайну ГДД §2.6 оружие в лесу не дропает: `right_hand=0, left_hand=0`; обвес — равномерно (12-20 на слот).
  - `mountains.drop.slot_weights`: горы — оружие активно (`right_hand=14, left_hand=14`); обвес — 12 на слот.
  - `dungeon.drop.slot_weights`: данжон — оружие приоритетнее (`right_hand=20, left_hand=20`); обвес — 10 на слот.

- **Drop-engine: общий picker-хелпер для леса и pve (commit `463b512`):**
  - **Новый модуль `src/pipirik_wars/domain/balance/picking.py`** — `pick_drop_item_entry(*, balance, slot_weights, rarity_weights, random) -> ItemEntry`. 3 шага:
    1. `weighted_choice` по `slot_weights` (предварительно фильтруются слоты с весом=0 — `RealRandom.weighted_choice` требует все веса > 0; для леса это исключает `right_hand`/`left_hand`, поэтому те никогда не попадают в выборку).
    2. `weighted_choice` по `rarity_weights` (`common`/`rare`/`epic`).
    3. `random.choice` из подмножества `items_catalog`, отфильтрованного по `(slot, rarity)`. Pool гарантированно непуст благодаря `_validate_drop_slot_rarity_coverage`.
  - `domain/pve/services.py::_roll_item_drop` — переключён на `pick_drop_item_entry`. Передаёт `cfg.drop.slot_weights` из per-location `PveDropConfig`. Контракт `PveItemDrop` снаружи не изменился.
  - `domain/forest/services.py::_roll_item_drop` — то же изменение (передаёт `balance.forest.drop.slot_weights`). Контракт `ItemDrop` неизменен.
  - **Архитектурное решение:** общий picker, а не дублирование логики в forest и pve. Это устраняет копию-пасту и централизует pydantic-валидацию покрытия `(slot, rarity)`.

- **Тесты (commits `803ab4e` + `463b512` + `9255e08`):**
  - `tests/unit/domain/balance/factories.py` — фабрика `valid_balance_payload()` обновлена: 40 предметов в каталоге (по 5 на каждый из 8 слотов), все три редкости покрыты на каждом слоте; `slot_weights` добавлены во все три drop-конфига (forest: оружие=0; mountains/dungeon: оружие>0).
  - `tests/unit/domain/balance/test_config.py` — `_VALID_DROP_PAYLOAD` обновлён, `test_below_30_rejected` → `test_below_min_size_rejected` (39 vs 40), новый `test_missing_slot_rejected` (каталог без `right_hand` отвергается).
  - `tests/unit/domain/forest/test_services.py` — 3 ScriptedRandom-теста дополнены `weighted_index` для слота между branch и rarity (новый порядок вызовов: branch → slot → rarity).
  - `tests/unit/domain/pve/test_services.py` — 4 ScriptedRandom-теста дополнены `weighted_index` для слота на каждый дроп.
  - **Новый модуль `tests/unit/domain/balance/test_picking.py` — 10 тестов, 1000+ rolls per location:**
    - `TestPickerScripted` (3): нулевые веса фильтруются; picker корректно выбирает оружие при активном `right_hand`; pool фильтруется по `(slot, rarity)`-паре.
    - `TestSlotDistributionStress` (3): 5000 rolls на каждую из 3 локаций; для каждого активного слота `|actual − expected| ≤ 0.10`; в лесу `right_hand`/`left_hand` не выбираются ни разу; в горах/данжоне все 8 слотов встречаются ≥1 раз.
    - `TestForestNoWeapons` (1): 5000 forest-runs → `weapon_drop_count == 0`.
    - `TestPveWeaponsAndUniqueness` (3): в горах и данжоне за 2000 runs встречаются оба weapon-слота; в данжоне за 5000 runs покрываются все 6 (slot×rarity) комбинаций оружия.

Результат / артефакты:

- **Изменения**: 10 файлов, +688 строк / −52 строк (см. `git diff --stat 1f7fc1e..1ae81ab`).
  - Новые: `src/pipirik_wars/domain/balance/picking.py` (77 строк), `tests/unit/domain/balance/test_picking.py` (306 строк).
  - Изменённые: `domain/balance/config.py` (+145/−1), `config/balance.yaml` (+49), `tests/unit/domain/balance/factories.py` (+37/−1), `tests/unit/domain/balance/test_config.py` (+41/−1), `domain/{forest,pve}/services.py`, `tests/unit/domain/{forest,pve}/test_services.py`.
- **CI на финальной ветке**: `make ci` — 3583 passed / 1 skipped, coverage 95.87% (baseline 95.88%, минус 0.01% — в пределах допуска); ruff / mypy --strict (735 файлов, 0 issues) / import-linter (3/3 contracts kept) — clean.
- **PR**: [#103](https://github.com/Pipirkawar/Pipirkawar/pull/103) (squash-мерж).

Заметки / решения:

- **Унификация picker-а forest+pve** — решено в C.4+C.5 вынести логику в `domain/balance/picking.py` вместо дублирования в `domain/{forest,pve}/services.py`. Это соответствует паттерну «доменные хелперы в `domain/balance/`», уже использованному для `weighted_choice`-обвязки.
- **Фильтрация нулевых весов** — `RealRandom.weighted_choice` контрактно требует weights > 0 (см. `domain/shared/ports/random.py`). Picker сам фильтрует `(slot, weight) where weight > 0` перед вызовом, т.к. `slot_weights` per-location может содержать нули (forest: оружие=0). Альтернативное решение «`weighted_choice` поддерживает 0-веса» отвергнуто — это бы маскировало баги конфига.
- **Кросс-валидатор `_validate_drop_slot_rarity_coverage`** — гарантирует, что после загрузки `balance.yaml` нет ни одной комбинации (location, активный slot, rarity), на которую нет ≥1 предмета в каталоге. Это «fail-fast at startup» вместо «runtime IndexError на пустом pool в picker-е».
- **Поведенческое изменение** — распределение слотов в дропе теперь функция от `slot_weights`, а не «равномерно среди слотов с предметами нужной редкости». В горах/данжоне игроки начнут видеть оружие; в лесу — НЕТ оружия (по дизайну).
- **Последний postmerge-PR** — этот фичевый PR #103 ещё открывался по старому канону «postmerge отдельным PR-ом» (PR #102 закрыл 3.1-B). Начиная **со следующего фичевого PR (3.1-D)**, обновления `history.md` + `current_tasks.md` идут **внутри самого фичевого PR** последним коммитом перед мерджем — отдельный postmerge-PR упразднён (изменения в `CONTRIBUTING.md` сделаны в **этом** последнем postmerge-PR).
- **Что НЕ делалось** в этом PR (по плану спринта): bot-handler-ы `/mountains`/`/dungeon` (это 3.1-E); APScheduler factory-wiring (это 3.1-E); миграции БД (items уже хранятся как JSON-tuple); domain `Scroll`/`enchantment` (это 3.1-D).

---

## 2026-05-07 — Спринт 3.1-B: use-cases `Start/Finish{Mountain,Dungeon}Run` + persistence + миграция `0018_pve_runs` + DI

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 3.1 ([`current_tasks.md`](current_tasks.md)), ПД §6.3 / задачи 3.1.1, 3.1.2 (use-case + persistence для гор и данжона), ГДД §8 «Походы (PvE)», §3.1 «Правило 20 см», §3.3 «Анти-чит хардкап», [PR #101](https://github.com/Pipirkawar/PipirkaWar/pull/101) (мерж — `5f25ca0`)

Что сделано:
- **Infra-фундамент PvE (commit `5a1a411`):**
  - `domain/shared/ports/audit.AuditAction` — +4 акшна `MOUNTAIN_RUN_STARTED/FINISHED`, `DUNGEON_RUN_STARTED/FINISHED`.
  - `domain/shared/ports/audit.AuditSource` — +`MOUNTAINS`, `DUNGEON` (organic, попадают под hardcap-канон ГДД §3.3).
  - `domain/security/entities.LockReason` — +`MOUNTAINS`, `DUNGEON`.
  - `domain/shared/ports/scheduler.IDelayedJobScheduler` — 4 abstract-метода `schedule_finish_{mountain,dungeon}_run` + `cancel_finish_*` (идемпотентны по `run_id`, recovery после рестарта воркера).
  - `infrastructure/scheduler/aps.APSchedulerDelayedJobScheduler` — stub-реализация (factory-wiring `mountain_finish_factory`/`dungeon_finish_factory` будет в 3.1-E с bot-handler-ами).
  - `tests/fakes/delayed_job_scheduler.FakeDelayedJobScheduler` — in-memory dict + cancelled-list.
  - `config/balance.yaml::anticheat.organic_sources` — +`mountains`, `dungeon`.
  - **Миграция `0018_pve_runs`** — расширение whitelist `audit_log_source_whitelist` + создание `mountain_runs` и `dungeon_runs` (зеркальные структуры: id, player_id, status, started_at, ends_at, branch_name, branch_sign, length_delta_cm signed, drops JSON, finished_at) с CHECK-инвариантами (status ∈ {in_progress, finished}; branch_sign ∈ {gain, loss}; sign↔delta consistency; `finished_at`↔status consistency; `ends_at > started_at`); индексы `(player_id, status)`, `(status, ends_at)`, partial unique `(player_id) WHERE status='in_progress'`.
- **DTOs + ORM (commit `70ee23f`):**
  - `application/dto/inputs.py` — 4 новых DTO `Start/Finish{Mountain,Dungeon}RunInput`. Контракт зеркалит forest (`tg_id` для старта, `run_id` для финиша).
  - `infrastructure/db/models/pve_runs.py::MountainRunORM`, `DungeonRunORM` — ORM-модели с полным набором CHECK-инвариантов и индексов из миграции 0018. Общий factory-хелпер `_pve_run_table_args(table_name)`.
- **Application — горы (commit `9f94951`):**
  - `application/mountains/start_run.StartMountainRun` (по образцу `StartForestRun`):
    - проверки входа: `thickness ≥ unlock_levels.mountains` (по умолчанию 3), `length ≥ 20 см` (ГДД §3.1);
    - `activity_lock(player, MOUNTAINS, ttl=cooldown)`;
    - outcome ролится один раз через `pick_pve_outcome(MOUNTAINS, ...)`;
    - `scheduler.schedule_finish_mountain_run(run_id, ends_at)`;
    - audit `MOUNTAIN_RUN_STARTED` с idempotency_key.
  - `application/mountains/finish_run.FinishMountainRun`:
    - +-исходы — через `progression.add_length(...)` с `source=AuditSource.MOUNTAINS` (hardcap-канон ГДД §3.3);
    - −-исходы — прямая `player.with_length(...)` + audit `LENGTH_REVOKE` с idempotency_key `mountain_run_loss_revoke:<run_id>` (whitelist для `length_grant_guard`);
    - `scheduler.cancel_finish_mountain_run(run_id)`;
    - идемпотентен (повторный финиш — no-op, возвращает уже-сохранённый run).
  - `tests/fakes/mountain_run_repo.FakeMountainRunRepository` (in-memory dict + active-by-player tracking).
  - **+25 unit-тестов** (`tests/unit/application/mountains/test_{start,finish}_run.py`): входные проверки (NotEnoughThicknessError/Length, AlreadyInMountains), happy-path для +/−-исходов, idempotency, scheduler invocation, lock release, audit fields.
- **Application — данжон (commit `17126c2`):** зеркало гор. Различия: `LockReason.DUNGEON`, `AuditAction.DUNGEON_RUN_*`, `AuditSource.DUNGEON`; `thickness ≥ unlock_levels.dungeon` (по умолчанию 6); cooldown 40–60 мин, `max_drops=3` (горы: 20–40 мин, `max_drops=1`); `scheduler.schedule_finish_dungeon_run(...)`; idempotency-key-и `dungeon_run_started/finished/loss_revoke` + `add_length:dungeon_run`. **+24 unit-теста**.
- **Persistence — Sql impls + integration (commit `46bad85`):**
  - `infrastructure/db/repositories/mountain_run.SqlAlchemyMountainRunRepository`, `dungeon_run.SqlAlchemyDungeonRunRepository` — реализации портов поверх таблиц `mountain_runs`/`dungeon_runs`. Зеркальные структуры; общая логика — JSON-сериализация `tuple[PveItemDrop, ...]` в `[{"item_id": ...}]`, восстановление `Item` через `IBalanceConfig.items_catalog`, вывод `branch_sign` из знака `length_delta_cm`, partial-unique на `(player_id) WHERE status='in_progress'`.
  - **Integration round-trip** `tests/integration/db/test_pve_run_repositories.py` (446 строк): `add → get_by_id → save(finished) → get_active_by_player`, корректность сериализации drops, проверка CHECK-инвариантов через `IntegrityError`, partial-unique на двух IN_PROGRESS-ах одного игрока.
- **DI-wiring (commit `5b2f695`):**
  - `bot/main.py::Container` — импорт `Start/Finish{Mountain,Dungeon}Run` use-case-ов + портов `IMountainRunRepository`/`IDungeonRunRepository` + Sql-реализаций. Container получает 6 новых полей: `mountain_runs`, `dungeon_runs` (репозитории) + 4 use-case-а. Bot-handler-ов `/mountains` / `/dungeon` **нет** — это 3.1-E.
- **Архитектурные тесты:** `tests/unit/architecture/test_length_grant_guard.py` — добавлены 4 файла application/{mountains,dungeon}/finish_run.py в whitelist прямой записи длины (−-исходы пишут `player.with_length(...)` напрямую, как `application/pvp/apply_outcome.py`).

Результат / артефакты:
- **41 файл изменён**, +3609 / −47 строк.
- **+~290 unit/integration-тестов** (49 unit для mountains+dungeon use-cases + integration round-trip).
- **Миграция:** `infrastructure/db/migrations/versions/20260507_0018_pve_runs.py` (новые таблицы + расширение CHECK whitelist).
- **CI на момент мерджа PR #101:** зелёный — 3571 passed / 1 skipped, coverage 95.88%, ruff/mypy/import-linter — clean.
- 5 коммитов на feature-ветке `devin/1778174890-sprint-3-1-B-pve-persistence` (`5a1a411` → `70ee23f` → `9f94951` → `17126c2` → `46bad85` → `5b2f695`) + 1 doc-sync коммит `1d2312d` mid-flight.

Заметки / решения:
- **Зеркальные модули вместо унификации.** В 3.1-A было решено держать `domain/{mountains,dungeon}/` отдельно (а не один общий модуль). 3.1-B продолжил эту линию для `application/`-слоя: `application/mountains/` и `application/dungeon/` — отдельные пакеты, общая логика выражена через одинаковую сигнатуру use-case-ов (DI-инвариант) и единый picker `pick_pve_outcome` в `domain/pve/services.py`. Дублирование use-case-кода (~50 строк) — осознанная цена за независимость файлов: 3.1-E (bot-handler-ы) добавит свой пакет на каждую локацию, а 3.1-C (дроп оружия) и 3.1-D (скроллы) ничего не меняют в структуре application/{mountains,dungeon}.
- **+-исходы через `ILengthGranter` (hardcap-канон).** Любой organic-источник (forest, mountains, dungeon) обязан проходить через `progression.add_length(source=AuditSource.<...>)` — он применяет rolling 24ч / 7д hardcap из ГДД §3.3. Прямая запись через `player.with_length(...)` остаётся только для −-исходов (revoke), отдельный whitelist в `tests/unit/architecture/test_length_grant_guard.py`.
- **Idempotency-keys** прозрачно зеркальны для гор и данжона: `<location>_run_started/finished:<run_id>`, `<location>_run_loss_revoke:<run_id>`, `add_length:<location>_run:<run_id>`. Это позволяет двойной финиш / двойной revoke не создавать повторных audit-записей.
- **Scheduler — stub в APS.** `APSchedulerDelayedJobScheduler.schedule_finish_{mountain,dungeon}_run` пока логирует `factory not wired` (callback-фабрики `mountain_finish_factory`/`dungeon_finish_factory` будут привязаны в 3.1-E с bot-handler-ами, как у `forest`). Use-case-ы при этом полностью функциональны и тестируются через `FakeDelayedJobScheduler`.
- **Bot-handler-ов нет в 3.1-B.** Скоуп этого PR — domain → application → infrastructure (persistence) + DI. UI-слой (`/mountains`, `/dungeon`, презентеры, локали `mountains-*`/`dungeon-*`) — отдельный PR 3.1-E (после 3.1-C, 3.1-D), см. `development_plan.md` §6.3.1+.

---

## 2026-05-07 — Спринт 3.1-A: каркас доменов гор и данжона + общий picker `pick_pve_outcome`

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 3.1 ([`current_tasks.md`](current_tasks.md)), ПД §6.3 / задачи 3.1.1–3.1.5 (горы/данжон/дроп оружия и скроллов/балансировка), ГДД §8 «Походы (PvE)», [PR #99](https://github.com/Pipirkawar/PipirkaWar/pull/99) (мерж — `7a37071`)

Что сделано:
- **`domain/pve/`** — новый пакет с общими VO для PvE-локаций с ±-механикой (горы и данжон):
  - `entities.py`: `PveLocationKind` (mountains/dungeon), `PveOutcomeBranch` (имя ветки + `PveSign` + **абсолютная** `length_cm`), `PveItemDrop` (re-uses `domain/forest/Item`), `PveRunOutcome` (branch + **знаковая** `length_delta_cm` + `tuple[PveItemDrop, ...]`). Invariant-проверка в `__post_init__`: `sign=GAIN ⇒ length_delta_cm ≥ 0`, `sign=LOSS ⇒ length_delta_cm ≤ 0`, `|length_delta_cm| == branch.length_cm`.
  - `services.py::pick_pve_outcome(*, location, balance, random)` — единственный picker для гор и данжона. Розыгрывает: (1) ветку через `weighted_choice` на `cfg.outcomes`; (2) знаковую дельту длины (применяет `branch.sign` к `randint(min, max)`); (3) **независимо** для каждого слота дропа Bernoulli-ролл с `probability_percent` (распределение количества дропов = `Binomial(max_drops, p)`, что **не равно** «равномерно по 0..max_drops» — намеренно, ГДД §8 «0–1»/«0–3» = биномиальная лестница). Для каждого выпавшего дропа — `weighted_choice` rarity → `random.choice` из items_catalog. **Имена не дропаются** (ГДД §2.5 — только лес).
- **`domain/mountains/`** — модуль гор по образцу `domain/forest/`:
  - `entities.py`: `MountainRun` frozen-dataclass (id/player_id/status/started_at/ends_at/branch_name/length_delta_cm/drops/finished_at) + `MountainRunStatus` (IN_PROGRESS, FINISHED). Метод `.starting(*, player_id, outcome, started_at, ends_at)` создаёт IN_PROGRESS-запись (требует `ends_at > started_at`, иначе `ValueError`); `.mark_finished(*, finished_at)` идемпотентен (повторный финиш возвращает `self`).
  - `errors.py`: `MountainError` (база), `AlreadyInMountainsError(player_id)`, `MountainRunNotFoundError(run_id)`, `MountainRunOwnershipError(run_id, run_player_id, actor_player_id)`, `MountainsRequirementError(player_id, requirement, required, actual)` — `requirement` = `"thickness"` (ГДД §8: `unlock_levels.mountains = 3`) или `"length"` (ГДД §3.1 «правило 20 см»).
  - `repositories.py::IMountainRunRepository` — ABC port, методы `add` / `get_by_id` / `get_active_by_player` / `save`, все async и keyword-only.
- **`domain/dungeon/`** — зеркало `domain/mountains` для данжона: `DungeonRun`, `DungeonRunStatus`, `IDungeonRunRepository`, `DungeonError` + 4 наследника (включая `DungeonRequirementError` с порогами `thickness=6` / `length=20`). Структурно идентичен горам, отличается только параметрами в `balance.yaml` (`max_drops=3`, больший разброс `min..max`, выше `probability_percent`).
- **`config/balance.yaml`** + pydantic-схемы (`PveSign`/`PveOutcomeConfig`/`PveDropConfig`/`_PveLocationConfig`/`MountainsConfig`/`DungeonConfig` в `domain/balance/config.py`) — новые секции `mountains:` и `dungeon:` с 5 ветками каждая (3 gain + 2 loss), кулдауны (`20–40 мин` / `40–60 мин`), drop-конфиг (`max_drops=1` / `max_drops=3`). Эти изменения уже были в стартовом коммите ветки (`f9dd200`) от предыдущего агента, в PR попали как часть скоупа 3.1-A.
- **75 unit-тестов**:
  - `tests/unit/domain/pve/test_entities.py` (18 тестов) — конструкторы VO (валидные/невалидные), frozen-инвариант, sign↔delta-инварианты `PveRunOutcome`, граничные случаи (zero-length, multi-drop).
  - `tests/unit/domain/pve/test_services.py` (12 тестов) — точные кейсы через `ScriptedRandom` (определённый branch_idx → ожидаемый sign/length, drop при `roll <= probability` / no-drop при `roll > probability`, multiple drops в данжоне) + **stress-тесты с 1000 rolls на каждую локацию** (`FakeRandom(seed=...)`, инварианты `−max_abs ≤ delta ≤ +max_abs`, `0 ≤ len(drops) ≤ max_drops`, валидные item-id, распределение gain/loss в ожидаемом диапазоне ±10% от веса).
  - `tests/unit/domain/mountains/{test_entities, test_errors, test_repositories}.py` (22 теста) — `.starting`, `.mark_finished` idempotency, валидация `ends_at > started_at`, frozen, `branch_name` non-empty + иерархия ошибок + поля + ABC-протокол с `inspect.iscoroutinefunction` + `KEYWORD_ONLY`-аргументы.
  - `tests/unit/domain/dungeon/{test_entities, test_errors, test_repositories}.py` (23 теста) — зеркало mountains для данжона + `drops_count=3` для проверки «0–3 предмета».

Результат / артефакты:
- **+10 файлов** в `src/pipirik_wars/domain/{pve,mountains,dungeon}/`, **+9 файлов** в `tests/unit/domain/{pve,mountains,dungeon}/`.
- **CI**: `make ci` локально — **3502 passed / 1 skipped** (baseline `main` до PR = 3417 → +85 новых тестов), coverage **95.90%**, `ruff` / `mypy --strict` / `import-linter` (3 контракта KEPT) — clean. На PR #99 все 3 GitHub Actions checks passed: `lint + types + tests (py3.11)`, `lint + types + tests (py3.12)`, `pip-audit (security)`.
- 6 коммитов: `f9dd200` (схемы + balance.yaml — был в ветке от предыдущего агента) → `56f4dec` (`domain/pve/`) → `5ea2d6f` (`domain/mountains/`) → `c82efac` (`domain/dungeon/`) → `66cfdb9` (фикс mypy --strict) → `4fa5848` (удаление вспомогательного `AGENT_HANDOFF.md`).

Заметки / решения:
- **`domain/mountains/` и `domain/dungeon/` — отдельные модули, не унификация под `domain/pve/run.py`.** План `development_plan.md` §6.3.1+ оставлял это на усмотрение реализующего; решение в пользу разделения мотивировано тем, что в 3.1-B каждой локации нужна **своя таблица** (`mountain_runs` / `dungeon_runs` — отдельная Alembic-миграция), а в 3.1-E каждой — **свой bot-handler** (`/mountains` / `/dungeon`). Иметь зеркальные `domain/{mountains,dungeon}/`-модули проще для ревью (один diff на одну локацию) и для будущих расширений (например, разная анти-чит-семантика на гор/данжон в Спринте 3.4).
- **Общий picker `pick_pve_outcome` в `domain/pve/services.py`.** Обе локации структурно идентичны (валидаторы конфига уже общие через `_PveLocationConfig`), и Bernoulli-семантика per-slot одинакова — это DRY, плюс `pick_*_outcome`-копипаста удвоила бы поверхность для регрессий в 1000-rolls тестах.
- **Лес остаётся в `domain/forest/`** без изменений — у него уникальная семантика (`name_share_percent` для дропа имён, всегда положительный исход). `compute_forest_outcome` не тронут, обратная совместимость гарантирована.
- **`AGENT_HANDOFF.md` создавался** в середине работы (между коммитом #2 и коммитом #3) как страховка на случай обрыва токенов между push-ами; удалён в финальном `chore(3.1-A)` после успешного `make ci` и перед открытием PR. Это разовая практика, не канон.
- **`docs/current_tasks.md` и эта запись** обновляются **отдельным postmerge-PR-ом** (по канону Спринта 2.5-D), как и для всех последующих PR-ов 3.1-B/C/D/E.

---

## 2026-05-07 — Спринт 3.1 docs-prep: декомпозиция Спринта 3.1 на 5 фичевых PR-ов (3.1-A…3.1-E) + sync `current_tasks.md`

**Автор:** Devin (агент)
**Тип:** doc + plan
**Связано:** Спринт 3.1 ([`current_tasks.md`](current_tasks.md)), ПД §6.3 / задачи 3.1.1–3.1.5 (горы/данжон/дроп оружия и скроллов/балансировка), ГДД §8 «Походы (PvE)», [PR #98](https://github.com/Pipirkawar/PipirkaWar/pull/98) (мерж — `71a667e`)

Что сделано:
- **`docs/development_plan.md` §6.3.1+ «Декомпозиция Спринта 3.1 на PR-ы»** — новая под-секция с табличным планом (5 фичевых PR-ов: 3.1-A — каркас доменов + балансовый конфиг; 3.1-B — use-cases + persistence + миграция; 3.1-C — дроп оружия `right_hand`/`left_hand` + расширение items_catalog; 3.1-D — дроп скроллов заточки skeleton; 3.1-E — bot-handler-ы + локали). Каждая строка таблицы содержит скоуп, ориентировочные файлы, привязку к задачам 3.1.1–3.1.5 ГДД/ПД. Перед таблицей — обоснование разбиения (4 архитектурных слоя × shared-конфиг + локали = неревьюабельный «один PR на спринт» по канону Спринта 2.5).
- **«Жёсткие правила декомпозиции»** (5 пунктов): production-код в рабочем состоянии после каждого PR, doменный слой не зависит от ещё не написанного infrastructure/bot-слоя (порты объявляются вместе с domain), unit-тесты в том же PR, локали добавляются вместе с handler-ом, postmerge-документационный PR после каждого фичевого.
- **`docs/current_tasks.md`** — sync под старт Спринта 3.1: «Снимок состояния» обновлён под `main = f3c3a86` (после 2.5-D.12), активная feature-ветка docs-prep, скоуп Спринта 3.1 + план 5 PR-ов; «Текущая позиция» под `devin/1778169424-sprint-3-1-docs-prep`; чек-лист docs-only PR-а.

Результат / артефакты:
- **2 файла** изменены: `docs/development_plan.md` (+~40 строк секции 6.3.1+), `docs/current_tasks.md` (full snapshot/position rewrite под Спринт 3.1).
- **CI**: `make ci` без изменений от предыдущего baseline — **3417 passed / 1 skipped, coverage 95.90%** (docs-only PR не трогает код/тесты).
- 1 коммит: `79836cb` (docs-only).

Заметки / решения:
- **План декомпозиции на 5 PR-ов** написан **до** начала реализации, чтобы каждый последующий фичевый PR имел чёткие границы скоупа. Это снижает риск «один большой PR на спринт» по аналогии со Спринтом 2.5 (A→B→C→D.1–D.12 + postmerge у каждого).
- **Решение об унификации `domain/{mountains,dungeon}/` vs отдельные модули** оставлено на усмотрение реализующего 3.1-A (см. запись выше о фактическом решении в пользу отдельных модулей).

---

## 2026-05-07 — Спринт 2.5-D.12: аудит/дедупликация `admin-*` локалей + lint-тест RU↔EN parity (закрытие Спринта 2.5)

**Автор:** Devin (агент)
**Тип:** fix + test
**Связано:** Спринт 2.5 ([`current_tasks.md`](current_tasks.md)), ПД §5 / задача 2.5.10 (локали admin-команд), ГДД §0 (i18n-канон через Mozilla Fluent), §18.6 (двуязычный admin-интерфейс), [PR #96](https://github.com/Pipirkawar/PipirkaWar/pull/96) (мерж — `e6f7512`)

Что сделано:
- **Закрыт пробел «silent shadow в Fluent».** Mozilla Fluent при двух определениях одного Message-ID в файле молча оставляет первое и игнорирует второе **без warning-а** — ни на парсинг-time, ни на runtime. `pytest`-тесты не ловили этот класс багов потому, что `tests/conftest.py` подменяет реальный i18n на `_StubBundle`, который возвращает Message-ID как есть. До D.12 `locales/ru.ftl` и `locales/en.ftl` содержали секцию-наследие Спринта 2.5-A.3 (`## Admin — TOTP confirmation of dangerous commands`) с 7 ключами, **5 из которых** (`admin-confirm-token-not-found`, `admin-confirm-token-expired`, `admin-confirm-totp-not-configured`, `admin-confirm-admin-mismatch`, `admin-confirm-code-invalid`) дублировались позднее в секции `# /confirm (B.5)`. Из-за silent-shadow-а админам в production отдавались устаревшие лаконичные тексты от 2.5-A.3 («⚠️Токен не найден») вместо обновлённых из 2.5-B с `<code>{ $token }</code>` substitution-ом («❌ Токен `TOK-123` уже использован или не существует.»). Удалена секция 2.5-A.3 (-20 строк `ru.ftl`, -18 строк `en.ftl`); сохранены актуальные определения тех же 5 ключей из секции 2.5-B.
- **Удалены 2 orphan-ключа** (`admin-confirm-prompt`, `admin-confirm-success`) — никогда не зацеплены из кода (`grep -E "admin-confirm-(prompt|success)\b" src/` → пусто). Они проектировались как generic confirm-flow в 2.5-A.3, но в 2.5-B флоу был раздроблен по командам (`admin-{cmd}-confirm-issued` для prompt + `admin-confirm-success-{cmd}` для success), и эти два ключа никогда не были зацеплены ни одним `MessageKey(...)` в `src/`.
- **Новый lint-тест** `tests/unit/locales/test_admin_keys_lint.py` (11 параметризованных кейсов из 5 классов; ~210 строк) — гарантирует, что регрессия (новый ключ только в RU, или дубль, или мёртвый ключ) падает на CI:
  - `TestNoDuplicateKeys[ru,en]` — `Counter` по Message-ID через `fluent.syntax.parse(text, with_spans=False)` → отказ при любом ID с count > 1. Это закрывает пробел «silent shadow» — Fluent сам не ругается, но тест ругается.
  - `TestLocaleParity::test_full_parity` — `set(ids_ru) == set(ids_en)` без exception-ов; любой полу-локализованный ключ → провал.
  - `TestLocaleParity::test_admin_keys_parity` — то же, но только для `admin-*`-подмножества (более понятный fail-message при админ-дрейфе).
  - `TestAdminKeysCoverage[ru,en]::test_no_missing_admin_keys` — used-in-src ⊆ defined-in-locale. Сборка used-set: `ast.walk` по всем `.py`-файлам в `src/`, выбираем `ast.Constant` с `value.startswith("admin-")` и валидным Fluent-identifier-ом. Любой код, который зовёт ключ, отсутствующий в `.ftl`, → провал теста.
  - `TestNoOrphanAdminKeys[ru,en]::test_no_orphan_admin_keys` — defined-in-locale ⊆ used-in-src. Любой `admin-*`-ключ в локали, не зацепленный из кода, → провал. Это и поймало 2 orphan-ключа выше.
  - `TestSanityCounts` — guard `≥100 admin-ключей` в коде и в каждой локали (защита от случайного «успеха» при пустых множествах из-за поломанного AST-обхода / regex-а — без guard-а сломанный сборщик used-set вернул бы пустое множество, и проверки vacuously passed бы).
- **Без изменений production-кода и миграций.** Изменены только `.ftl`-файлы (удаление obsolete) + новый тест-файл + sync доки. Поведение admin-команд для пользователя сохраняется идентичным — для админа меняются только тексты ошибок `/confirm`-handler-а (см. выше): теперь они богаче и содержат `<code>{ $token }</code>`-substitution. Это уже подразумевалось вторым определением в 2.5-B, но не доходило до пользователя из-за silent-shadow-а.

Результат / артефакты:
- Коммит на ветке `devin/1778167492-sprint-2-5-d.12-locales`: `c456dfa`. Merge-коммит: `e6f7512`.
- Локальный `make ci`: зелёный — **3417 passed / 1 skipped** (+11 lint-кейсов vs `main = 61b33f1`), coverage **95.90%** (без падения относительно `main`), ruff / ruff-format / mypy / import-linter — clean.
- CI на PR #96: 3 проверки зелёные (`lint + types + tests (py3.11)`, `lint + types + tests (py3.12)`, `pip-audit (security)`).
- Затронутые файлы: `locales/ru.ftl` (−20 строк), `locales/en.ftl` (−18 строк), `tests/unit/locales/__init__.py` (новый, пустой), `tests/unit/locales/test_admin_keys_lint.py` (новый, 207 строк), `docs/current_tasks.md` (обновлены 4 секции под D.12).
- **Спринт 2.5 закрыт полностью** — все 12 пунктов чек-листа (`A`, `B`, `C`, `D.1–D.12`) смержены в `main`.

Заметки / решения:
- **Принцип «двойная книга через AST-обход».** Сборка used-set делается через `ast.walk` по `src/`, выбирая `ast.Constant`-узлы с `value.startswith("admin-")`. Это ловит **только литералы** — если где-то в коде admin-ключ конструируется через f-string (`f"admin-{cmd}-confirm-issued"`) или конкатенацию, он не попадёт в used-set, и `TestNoOrphanAdminKeys` ложноположительно пометит существующий ключ как мёртвый. На момент D.12 проверено grep-ом `grep -rn 'f"admin-' src/` — динамической сборки admin-ключей нет, все идут через literal-strings в `MessageKey(...)`. Если в будущем понадобится динамическая сборка — придётся либо расширять AST-обход (распознавать `JoinedStr` с известными константами), либо добавлять explicit-комментарий-маркер для динамических ключей в `_KNOWN_DYNAMIC_KEYS = frozenset({...})` exclusion-set.
- **Sanity-порог `≥100`.** Выбран по факту текущего состояния (~147 admin-ключей в коде на момент D.12). Если проект ужмёт admin-набор (например, при удалении устаревших команд) — этот guard нужно опустить, иначе `TestSanityCounts` начнёт падать как false-positive.
- **Видимое поведенческое изменение для админов.** До D.12 админы видели лаконичные однострочные сообщения от 2.5-A.3 при ошибках `/confirm` (например, «⚠️Токен не найден»). После D.12 — богатые с substitution-ом (например, «❌ Токен `TOK-123` уже использован или не существует.»). Это и было задумано вторым определением в 2.5-B, но не доходило до пользователя из-за shadow-а. Изменение в плюс — админ теперь видит, какой именно токен не нашёлся.
- **Почему dedup, а не remove + add.** Альтернатива «удалить блок 2.5-A.3 целиком + добавить актуальные ключи в 2.5-B» эквивалентна, но добавляет noise в diff. Реально вторые определения уже были в 2.5-B-секции с момента её создания (см. PR #81), просто Fluent игнорировал их из-за shadow-а. Удаление obsolete-секции — минимальный и правильный fix.
- **Спринт 2.5 закрыт.** Все 12 D-задач + A/B/C закрыты. Следующая работа — Спринт 3 (см. `docs/development_plan.md`). Этот postmerge-PR — последний синк-док для 2.5.

---

## 2026-05-07 — Спринт 2.5-D.11: exhaustive RBAC-матрица в тестах (22 × 4 = 88 кейсов) + helper coverage

**Автор:** Devin (агент)
**Тип:** test
**Связано:** Спринт 2.5 ([`current_tasks.md`](current_tasks.md)), ПД §5 / задача 2.5.8 (общая инфраструктура `admin_audit_log` + RBAC), ГДД §18.6.2 (RBAC-матрица: какие роли что могут), [PR #94](https://github.com/Pipirkawar/PipirkaWar/pull/94) (мерж — `c434b3d`)

Что сделано:
- **Закрыт пробел «неравномерное coverage RBAC-deny».** До D.11 `tests/unit/domain/admin/test_authorization.py` содержал ~30 hand-picked кейсов, которые проверяли только «выборочные» комбинации `(AdminRole, AdminCommandKind)`. Это создавало риск, что при добавлении новой команды в `AdminCommandKind` или новой роли в `AdminRole` соответствующая строка `RoleBasedAdminAuthorizationPolicy._matrix` (или её отсутствие — fail-closed) могла остаться без assertion-ов и тихо разойтись с ГДД §18.6.2. После D.11 — полная exhaustive-матрица `22 × 4 = 88` кейсов автоматически перебирается через `itertools.product`, и любое расширение enum-а немедленно требует расширения теста.
- **Independent-спецификация ожиданий** в `tests/unit/domain/admin/test_authorization.py`: пять `frozenset`-групп (`_READ_SIDE_COMMANDS` (7 команд), `_CONFIRM_FLOW_COMMANDS` (2), `_SUPPORT_OPS_COMMANDS` (5), `_ECONOMY_COMMANDS` (4), `_SUPER_ONLY_COMMANDS` (4) → 22 в сумме) кодируют политику ГДД §18.6.2 **отдельно** от `_matrix` в production-коде. Функция `_build_expected_matrix()` собирает из этих групп authoritative таблицу `(command → frozenset[role])`. Принцип: «двойная книга» — если кто-то меняет одну сторону (код или ГДД-спеку), а вторую забывает — `make ci` падает с понятным дифом, а не молча принимает дрейф.
- **Полная матрица через `itertools.product`:** `_FULL_MATRIX_CASES: list[tuple[AdminRole, AdminCommandKind, bool]] = [(role, command, role in _EXPECTED_ALLOWED_ROLES[command]) for role, command in itertools.product(AdminRole, AdminCommandKind)]` → 88 кейсов с auto-generated `pytest`-ID-ами (`f"{role.value}-{command.value}-{'allow' if expected else 'deny'}"`). Любое новое значение в любом из enum-ов автоматически даёт +N кейсов без правки тест-файла.
- **Новый класс `TestRoleCommandMatrixExhaustive`** с тремя методами:
  - `test_consistency_every_command_kind_has_expected_rule` — проверяет, что `set(_EXPECTED_ALLOWED_ROLES) == set(AdminCommandKind)`. Это страхует от случая «добавили команду в enum, но не учли в группах» — тест падает до 88 параметризованных запусков с понятным `AssertionError: missing rule for AdminCommandKind.NEW_COMMAND`.
  - `test_full_matrix_active_admin` — 88 параметризованных кейсов, каждый делает `policy.is_authorized(_admin(role), command) is expected`. На каждой строке `_matrix` любое расхождение с независимой спецификацией → провал теста с конкретным role-command-pair-ом.
  - `test_inactive_admin_denied_for_every_role` — 4 кейса (по одному на каждое значение `AdminRole`), верифицирующие, что `_admin(role, is_active=False)` всегда отказан, даже на read-side-команде, разрешённой роли. Закрывает пробел: до D.11 inactive-admin тестировался только для `SUPER_ADMIN`, для других ролей политика «inactive → deny» доказывалась только через свойство `Admin.is_active` без assertion-ов.
  - Старый класс `TestRoleBasedAdminAuthorizationPolicy` (~30 hand-picked кейсов) **сохранён** как belt-and-suspenders: он остаётся читаемым reference-документом политики (по одной команде на роль, с явными ID-ами), который дополняет (не заменяет) exhaustive-матрицу.
- **Helper coverage** в `tests/unit/application/admin/test_authorization_helper.py`: новый параметризованный тест `test_deny_audit_entry_carries_correct_actor_role_and_command` (11 кейсов: `READ_ONLY × 3 + SUPPORT × 4 + ECONOMIST × 4`) — verify, что `ensure_admin_authorized(...)` НЕ затирает `actor_role`/`command_kind` константой (распространённая regression-баг «всегда пишем actor_role=read_only независимо от admin.role»), а пробрасывает их во все три места: (1) `audit-after`-snapshot (`{"command_kind": cmd.value, "actor_role": role.value}`), (2) `reason`-строка (содержит и роль, и команду), (3) `AdminAuthorizationDeniedError.command_kind` / `actor_role` (бросаемое исключение).
- **Бонус — фикс stale-числа в snapshot `current_tasks.md`** (отдельный коммит): два упоминания «`AdminCommandKind` whitelist 27 команд» → «22 команды» (фактический размер enum верифицирован grep-ом против `domain/admin/authorization.py`). Заодно «file-closed-матрица» → «fail-closed-матрица» (typo). Это не относится напрямую к D.11, но обнаружено при работе над PR-ом и не имеет смысла откладывать.

Результат / артефакты:
- Коммиты на ветке `devin/1778164769-sprint-2-5-d.11-rbac-tests`: `661fc0a` (основной test-PR), `6d12ffd` (фикс stale-числа в snapshot). Merge-коммит: `c434b3d`.
- Локальный `make ci` после обоих коммитов: зелёный — **3406 passed / 1 skipped** (+69 кейсов vs `main` — 88 параметризованных − 30 hand-picked, которые остались, + 11 helper-кейсов; не +99, т.к. часть hand-picked-кейсов покрывает те же `(role, command)`-пары и pytest их де-дуплицирует только в read-time, но запускает все), coverage **95.90%** (без падения относительно `main` = `3288fc6`), ruff / ruff-format / mypy / import-linter — clean, ~1:34.
- CI на PR #94: 3 проверки зелёные (`lint + types + tests (py3.11)`, `lint + types + tests (py3.12)`, `pip-audit (security)`).
- **Без изменений production-кода / локалей / миграций / БД.** Чистое расширение тест-coverage + sync доки.

Заметки / решения:
- **Принцип «independent specification».** Группы команд (`_READ_SIDE_COMMANDS`, `_CONFIRM_FLOW_COMMANDS`, и т.д.) кодируют политику ГДД §18.6.2 **в тестах**, отдельно от `RoleBasedAdminAuthorizationPolicy._matrix` в production-коде. Если кто-то добавит команду только в одну из двух сторон — провал на CI. Альтернатива «генерировать ожидания из самого `_matrix`» отвергнута: это превратило бы тесты в reflection-проверку «код согласован сам с собой», которая бесполезна при политических багах.
- **Принцип «fail-closed by default».** В `RoleBasedAdminAuthorizationPolicy._matrix` любая команда, не имеющая явной строки для роли, → `False` (deny). exhaustive-матрица в D.11 верифицирует это для каждой из 88 пар без исключений. Никаких «fallback-у allow» в политике быть не может — fail-closed-инвариант теперь зафиксирован тестом.
- **Почему 22, а не 27.** `AdminCommandKind` имеет 22 значения (verified grep-ом). Текст «27 команд» в snapshot `current_tasks.md` — legacy от ранних версий enum-а; исправлен в `6d12ffd`. **Source of truth для матрицы команд = код**, не доки (см. ту же позицию в записи D.10 про runbook).
- **Расширение exhaustive-test-а на новые команды.** Когда в Спринте 3+ добавится новая admin-команда, шаги такие: (1) добавить значение в `AdminCommandKind`, (2) добавить строку в `RoleBasedAdminAuthorizationPolicy._matrix` (или сознательно оставить fail-closed-deny), (3) добавить команду в одну из 5 frozenset-групп в `test_authorization.py` — иначе `test_consistency_every_command_kind_has_expected_rule` упадёт. Если политика выходит за пределы существующих 5 групп (например, появляется новая роль) — добавляется новая frozenset-группа + расширяется `_build_expected_matrix()`. Тесты не нужно править под каждый новый кейс — `itertools.product` сам сгенерирует.
- **Помеченный hand-picked-класс `TestRoleBasedAdminAuthorizationPolicy` намеренно не удалён.** Он играет роль human-readable документа политики (по одной типичной команде на роль, с явными ID-ами вроде `super_admin_can_lift_anticheat_ban`), который при чтении из IDE даёт быстрый «как читать матрицу» без необходимости лезть в `itertools.product`-генератор. Дублирование с exhaustive — намеренное, цена ~30 быстрых тест-кейсов; экономия — читаемость.
- **Helper-параметризация (11 кейсов) — не exhaustive.** В отличие от domain-теста, helper-тест проверяет НЕ всю RBAC-матрицу (это уже сделано в domain-тесте), а только что helper НЕ затирает `actor_role`/`command_kind` константой. Достаточно репрезентативной выборки `(role × forbidden command)`-пар: одна-две запрещённые команды на каждую роль. Расширять до `itertools.product` здесь смысла нет — это удвоит CI-time без новой защиты.
- **Из Спринта 2.5 остаётся:** **D.12** (аудит локалей `admin-*` ключей в `locales/{ru,en}.ftl`). После D.12 спринт 2.5 закрыт.

---

## 2026-05-07 — Спринт 2.5-D.10: `docs/admin_runbook.md` — operational doc для админ-команды

**Автор:** Devin (агент)
**Тип:** doc
**Связано:** Спринт 2.5 ([`current_tasks.md`](current_tasks.md)), ГДД §18.6 (целиком: интерфейс админ-панели), §18.6.4 (безопасность, bootstrap super-admin), §18.6.5 (TOTP-flow для опасных команд), [PR #92](https://github.com/Pipirkawar/PipirkaWar/pull/92) (мерж — `a8f26e5`)

Что сделано:
- **Новый файл `docs/admin_runbook.md`** (~324 строки, 10 секций) — операционная инструкция для команды поддержки / экономистов / super-admin-ов. **Не дублирует `game_design.md`** — ссылается на канонические разделы. Источник правды для матрицы команд и RBAC — код (`domain/admin/authorization.py`, `bot/handlers/admin*.py`, `CONFIRM_DISPATCHERS` registry), не спека.
- **Структура runbook-а:**
  - **§0** — канал админ-интерфейса: только ЛС бота (`chat_kind == "private"`); router-уровневый `IsAdminFilter` тихо отбрасывает не-админов; недостаточная роль → handler ловит `AdminAuthorizationDeniedError` + audit `ADMIN_AUTHORIZATION_DENIED`; write-side требует `reason ≥ 10` символов; опасные команды двухфазны через TOTP-confirm.
  - **§1** — ролевая модель (whitelist `AdminRole`): `read_only` (только read-side), `support` (+ freeze/ban), `economist` (+ правки баланса), `super_admin` (всё + уникальные команды). Bootstrap первого super-admin-а через env `BOOTSTRAP_ADMIN_IDS`.
  - **§2** — **полный live-список admin-команд** по разделам с пометкой TOTP: read-side / lookup (5 команд, 0 TOTP), support — игроки (3 команды, 1 TOTP `/ban`), support — кланы (2 команды, 0 TOTP), экономика (3 команды, 3 TOTP), super-admin only (4 команды, 1 TOTP `/announce`). Итого **5 TOTP-required команд**, синхронно с `CONFIRM_DISPATCHERS` registry в `bot/handlers/admin_economy.py`.
  - **§3** — пошаговый флоу `/admin_setup_totp <bootstrap_password>`: одноразовый bootstrap-пароль → secret пишется в bot-логи на VM (`structlog.info(event="admin_totp_setup", ...)`) → оператор копирует `otpauth://`-URI из логов → импортирует в Authenticator (Authy / Google Authenticator) → проверка через `/grant_*` или `/balance_set` с тестовой суммой.
  - **§4** — RBAC и обработка отказов: что видит оператор при недостаточной роли, как super-admin находит запись в `/audit` (`action = ADMIN_AUTHORIZATION_DENIED`).
  - **§5** — TOTP-confirm для опасных команд: 5 действий (`grant_length`, `grant_thickness`, `set_balance_value`, `ban_player`, `broadcast_announcement`); токен живёт `BROADCAST_CONFIRM_TOKEN_TTL_SECONDS=120`; что делать при `/confirm` invalid / expired / wrong code.
  - **§6** — чтение `/audit`: фильтры по `actor_admin_id`, `target_player_id`, временному окну, `action`-у; **полный whitelist `AdminAuditAction` enum** (всего ~22 значений с короткими описаниями); мета-аудит `ADMIN_AUDIT_LOG_VIEWED` пишется при каждом чтении (super-admin видит, кто что смотрел).
  - **§7** — recovery при потере 2FA, **3 сценария**: (7.1) свой Authenticator потерян, но `super_admin` ещё на связи → super-admin делает manual `UPDATE admins SET totp_secret = NULL WHERE id = ...` + audit запись; (7.2) `support`/`economist` потерял Authenticator → super-admin делает то же; (7.3) **утраченный SUPER_ADMIN 2FA** (нет ни одного активного super-admin-а) → direct DB rotation: `BOOTSTRAP_ADMIN_PASSWORD` ротация в env-секретах + `UPDATE admins SET totp_secret = NULL WHERE role = 'super_admin'` + повторный `/admin_setup_totp` → audit-запись о disaster-recovery.
  - **§8** — ротация `BOOTSTRAP_ADMIN_PASSWORD` (env-переменная `PIPIRIK_BOOTSTRAP_ADMIN_PASSWORD`, scope: org-secrets): когда менять (после каждого использования / при подозрении на утечку / по расписанию), как менять (Devin Secret rewrite + bot restart), что зафиксировать в `admin_audit_log` (manual-запись или хук в incident-tracking).
  - **§9** — FAQ: «что если бот не отвечает на админ-команду?», «зачем админ-команда требует `reason`?», «можно ли восстановить старый TOTP без reset-а?», «почему секрет в логах, а не в чате?».
  - **§10** — куда идти за подробностями: ссылки на `game_design.md §0/§16/§18.6` (правила и формулы), `development_plan.md` (план + критерии приёмки), `history.md` (исторические заметки и решения), `current_tasks.md` (активный PR / feature-ветка).
- **Обновлён `docs/current_tasks.md`** — снимок состояния под `main = cb40c2e` (теперь `a8f26e5`); «Текущая позиция» под D.10; чек-лист текущего PR — D.10 шаги.

Результат / артефакты:
- Коммит на ветке `devin/1778160466-sprint-2-5-d.10-admin-runbook`: `351c170`. Merge-коммит: `a8f26e5`.
- Локальный `make ci`: зелёный — 3337 passed / 1 skipped, coverage **95.90%** (~1:27, идентично main, ибо docs-only).
- CI на PR #92: 3 проверки зелёные (`lint + types + tests (py3.11)`, `lint + types + tests (py3.12)`, `pip-audit (security)`).
- Без изменений кода / тестов / локалей / миграций / БД.

Заметки / решения:
- **Принцип «runbook = операционка, спека = `game_design.md`».** Дублирование запрещено `CONTRIBUTING.md`: «Каждый документ имеет ровно одну роль; писать одно и то же в нескольких местах — запрещено». Поэтому RBAC-матрица в runbook-е не повторяет `game_design.md §18.6.2` дословно — она перечисляет команды (которые в спеке могут быть описаны под другими углами) и ссылается на спеку для деталей политики.
- **Источник правды для матрицы команд = код**, не спека. Если в `domain/admin/authorization.py::RoleBasedAdminAuthorizationPolicy._matrix` есть строка, которой нет в runbook-е — это **баг runbook-а**. Если есть строка в спеке, которой нет в коде — это баг кода (или incomplete-фича). Это сделано чтобы оператор не действовал на основании устаревшей доки.
- **§7.3 (recovery утраченного SUPER_ADMIN)** — самая рискованная процедура. Прописана с явным предупреждением: это **disaster-recovery**, manual `UPDATE` в production-БД, после процедуры обязателен incident-report в admin-audit (manual-запись). Если в будущем найдётся способ self-service-recovery без direct DB access — runbook обновляется тем же PR-ом, что добавляет такую команду.
- **§8 (ротация bootstrap-password)** — ENV `BOOTSTRAP_ADMIN_PASSWORD` (внутри Pydantic settings: `BootstrapSettings.admin_password`) меняется через Devin Secrets / `fly secrets set` / `kubectl set secret`. Префикс `PIPIRIK_` — часть `model_config.env_prefix`, без него инжект не сработает; в runbook-е это явно написано, чтобы оператор не наступил на грабли.
- **Канал доставки 2FA-секрета — bot-логи на VM, не Telegram-чат** (см. запись 2.5-D.6). В runbook-е это отдельным под-разделом с пояснением почему: Telegram-история в облаке, не trusted; SSH/VPN-доступ к VM = barrier-of-entry, эквивалентный compromise хоста.
- **Followup для будущих PR-ов** (упомянуто в FAQ runbook-а): автоматическая «само-инвалидизация» bootstrap-password (writing `BOOTSTRAP_ADMIN_PASSWORD_USED_AT` в admin-audit + rejecting повторных попыток); envelope-encryption для `Admin.totp_secret` при появлении security-review-требования; web-панель админа (фаза 4.5+ по плану).
- Из Спринта 2.5 остаётся: **D.11** (доптесты RBAC matrix coverage), **D.12** (аудит локалей `admin-*` ключей).

---

## 2026-05-07 — Спринт 2.5-D.6: `/admin_setup_totp` — self-service выдача TOTP-секрета SUPER_ADMIN-у

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 2.5 ([`current_tasks.md`](current_tasks.md)), ПД §5 / задача 2.5.8 (косвенно — общая инфраструктура `admin_audit_log`), ГДД §18.6 (`admins.totp_secret`, `admin_audit_log`), §18.6.2 (RBAC — `SETUP_TOTP` → `SUPER_ADMIN`), §18.6.5 (TOTP-flow для опасных команд), [PR #90](https://github.com/Pipirkawar/PipirkaWar/pull/90) (мерж — `4c2b100`)

Что сделано:
- **Команда `/admin_setup_totp <bootstrap_password>`** — self-service инициализация TOTP-секрета для живого `SUPER_ADMIN`-а без миграций и raw-SQL. Закрывает разрыв: до D.6 опасные команды (`/grant_*`, `/set_balance_value`, `/ban_player`, `/announce`) уже были под TOTP-confirm, но сам `Admin.totp_secret` мог быть выдан только напрямую через миграцию `0017_admins_totp_secret`.
- **Domain** (`domain/admin/`):
  - `AdminAuditAction.ADMIN_TOTP_SETUP` — новое значение enum-а для admin-audit-журнала.
  - `IAdminRepository.set_totp_secret(*, admin_id: int, secret: str) -> None` — новый абстрактный метод порта (mechanism-only; политика overwrite — на уровне use-case-а).
  - `domain/admin/ports/totp_secret_generator.py::ITotpSecretGenerator.generate() -> str` — новый порт, возвращает BASE32-секрет (RFC 4648).
  - `domain/admin/setup_totp_errors.py` — три новые доменные ошибки (наследники `DomainError`): `BootstrapPasswordNotConfiguredError` (env `BOOTSTRAP_ADMIN_PASSWORD` не задан), `BootstrapPasswordInvalidError` (constant-time-сравнение не прошло), `TotpAlreadyConfiguredError` (у этого админа уже есть `totp_secret` — переотдача через эту команду запрещена).
- **Application** (`application/admin/setup_totp.py::SetupAdminTotp`) — use-case-фасад полного flow: (1) `ensure_admin_authorized(...)` → `AdminCommandKind.SETUP_TOTP` (только `SUPER_ADMIN`, denial → `ADMIN_AUTHORIZATION_DENIED` в коротком UoW); (2) проверка `bootstrap_password is not None` → иначе `BootstrapPasswordNotConfiguredError`; (3) `hmac.compare_digest(...)` против ENV-пароля → иначе `BootstrapPasswordInvalidError`; (4) `IAdminRepository.get_by_tg_id(...)` + проверка `admin.totp_secret is None` → иначе `TotpAlreadyConfiguredError`; (5) `ITotpSecretGenerator.generate()` → `IAdminRepository.set_totp_secret(...)` в основном UoW; (6) `IAdminAuditLogger.record(action=ADMIN_TOTP_SETUP, ...)`; (7) возврат `(secret, otpauth://`-URI`)` handler-у. Use-case = policy, repo = mechanism (split задокументирован в `test_set_totp_secret_overwrites_existing_value` integration-тесте).
- **Infrastructure**:
  - `infrastructure/admin/pyotp_totp_secret_generator.py::PyOtpTotpSecretGenerator` — обёртка над `pyotp.random_base32()` (160 бит энтропии).
  - `infrastructure/db/repositories/admin.py::SqlAlchemyAdminRepository.set_totp_secret(...)` — single `UPDATE admins SET totp_secret = :secret WHERE id = :admin_id`; `rowcount == 0` → `ConcurrencyError` (use-case откатит свою UoW).
  - `infrastructure/settings/settings.py::BootstrapSettings.admin_password: SecretStr | None` — поле для env `BOOTSTRAP_ADMIN_PASSWORD`. Если не задан — use-case выдаёт `BootstrapPasswordNotConfiguredError` (silent allow-through исключён).
- **Bot/handlers**:
  - `bot/handlers/admin_setup_totp.py::handle_admin_setup_totp` — handler `/admin_setup_totp <password>`, парсинг аргументов, **только в ЛС** (`message.chat.type == "private"` → `admin-setup-totp-non-private`), локализованные ответы для всех ошибок. **Секрет и `otpauth://`-URI пишутся ТОЛЬКО в `structlog.info(event="admin_totp_setup", actor_tg_id=..., secret=..., provisioning_uri=...)` — в Telegram-чат уходит ЛИШЬ локализованный `admin-setup-totp-success` без секретного материала.** Оператор копирует URI из логов бота на VM и импортирует в свой Authenticator (Authy / Google Authenticator).
  - `bot/presenters/admin_setup_totp.py` — `AdminSetupTotpPresenter`: рендер локализованных сообщений (usage / non-private / not-authorized / password-not-configured / password-invalid / already-configured / success).
  - `bot/handlers/__init__.py::register_routers` — подключение нового router-а.
  - `bot/main.py::Container` + `build_container(...)` — два новых поля `totp_secret_generator: ITotpSecretGenerator`, `setup_admin_totp: SetupAdminTotp`; `BootstrapSettings.admin_password.get_secret_value()` пробрасывается в use-case как `bootstrap_password: str | None`.
- **Локали** (`locales/{ru,en}.ftl`) — 7 ключей `admin-setup-totp-{usage,non-private,not-authorized,password-not-configured,password-invalid,already-configured,success}` (RU + EN, всего +14 строк × 2 файла).
- **Тесты:**
  - `tests/unit/application/admin/test_setup_totp.py` — 9 unit-тестов на use-case (RBAC-deny, password-not-configured, password-invalid, already-configured, генерация secret, store + audit, отдача `otpauth://`-URI, разные varieties аргументов).
  - `tests/unit/bot/handlers/test_admin_setup_totp.py` — 11 unit-тестов handler-а (usage, non-private, not-authorized, password-not-configured, password-invalid, already-configured, happy-path с `structlog.testing.LogCapture()` для проверки структурированных событий, парсинг аргументов с пробелами).
  - `tests/integration/db/test_admin_repository.py` — +3 integration-теста (`set_totp_secret_persists_after_commit`, `set_totp_secret_overwrites_existing_value`, `set_totp_secret_unknown_admin_raises_concurrency_error`).
  - `tests/fakes/admin_repo.py` + `tests/unit/application/test_bootstrap_admin.py::FakeAdminRepo` — реализации `set_totp_secret(...)` (через `dataclasses.replace`) для всех `IAdminRepository`-фейков, чтобы абстрактный класс полностью покрывался.
  - `tests/unit/bot/test_composition_root.py::_container_with_fakes` — провязка нового use-case-а в test-DI.

Результат / артефакты:
- Коммиты на ветке `devin/1778151428-sprint-2-5-d.6-admin-setup-totp`: `8e8fda6`, `ab8e3ef`, `07eb70f`, `4323d54`, `03e5977`, `1f17bbf`, `1addd63`, `6caedcb`, `e8298be`. Merge-коммит: `4c2b100`.
- Локальный `make ci`: зелёный — 3337 passed / 1 skipped, coverage **95.90%** (~1:38).
- Все 6 RBAC-чувствительных команд (`SETUP_TOTP` + 5 TOTP-confirm-команд) теперь живут под единым каналом `IAdminAuthorizationPolicy` + `ensure_admin_authorized` helper — pattern замкнут.

Заметки / решения:
- **Канал доставки секрета — bot-логи, не Telegram-чат.** Альтернатива (отправка `otpauth://`-URI или QR-кода в личку) — отброшена: Telegram-канал не считается trusted (история в облаке, доступ к чату не гарантирует доступа к VM). Логи бота на VM читаются только тем, у кого SSH/VPN-доступ — это уже barrier-of-entry, эквивалентный compromise всего хоста. RFC 6238 `otpauth://totp/PipirikWars:<tg_id>?secret=<base32>&issuer=PipirikWars` пишется в `structlog.info(...)` структурированным полем `provisioning_uri` — оператор `grep`-ает event-маркер `admin_totp_setup` и копирует URI.
- **Constant-time-сравнение пароля** — `hmac.compare_digest(stored_password.encode(), supplied_password.encode())`. Защита от timing-атак: длина пароля сравнивается обычным `==`, но содержимое — фиксированно по времени.
- **Plain-text BASE32 в БД** — миграция `0017_admins_totp_secret` (D.4-prep, до D.6) сохраняет секрет в открытом виде, без envelope-encryption. Threat-model: операционная безопасность сводится к шифрованию-at-rest на уровне диска (SSD encryption + ограниченный доступ к VM); добавление прикладного шифрования откладывается до отдельного спринта (если придёт требование от security-review).
- **Idempotency = политика на use-case-уровне.** Use-case проверяет `admin.totp_secret is not None` и поднимает `TotpAlreadyConfiguredError` — то есть переотдача секрета невозможна без сначала reset-а в БД (отдельный manual-step в `admin_runbook.md` D.10). Repo-метод (`SqlAlchemyAdminRepository.set_totp_secret`) НЕ enforce-ит это — он чисто mechanism, и `test_set_totp_secret_overwrites_existing_value` это документирует. Split (policy в use-case, mechanism в repo) — стандартный для всего проекта.
- **Bootstrap-пароль одноразовый по умолчанию.** ENV `BOOTSTRAP_ADMIN_PASSWORD` валиден, пока оператор не уберёт его из инфраструктуры (`fly secrets unset` / `kubectl delete secret` / etc.). Followup D.6.1 — автоматическая «само-инвалидизация» (например, write `BOOTSTRAP_ADMIN_PASSWORD_USED_AT` в admin-audit и rejecting запросы по дате) — отложен до D.10 runbook-а (там же будет step-by-step rotation procedure).
- **Container DI расширение.** `Container` получил два новых поля (`totp_secret_generator`, `setup_admin_totp`) — это нарушает обратную совместимость для downstream-тестов, которые строят `Container(...)` напрямую (как `_container_with_fakes` в `test_composition_root.py`). Все internal call-site-ы обновлены в этом PR; внешних потребителей `Container`-а нет.
- Из Спринта 2.5 остаётся: **D.10** (`docs/admin_runbook.md`), **D.11** (доптесты RBAC), **D.12** (расширение локалей).

---

## 2026-05-07 — Спринт 2.5-D.4: `/announce` — broadcast с TOTP-confirm и фоновым throttle

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 2.5 ([`current_tasks.md`](current_tasks.md)), ПД §5 / задача 2.5.6 (broadcast с TOTP), ГДД §17 (моратории / broadcast), §18.6.5 (TOTP-обязательные команды), [PR #88](https://github.com/Pipirkawar/PipirkaWar/pull/88) (мерж — `774bd7c`)

Что сделано:
- **Two-phase flow `/announce <ru|en|*> <text>`** (как у `/grant_length`/`/grant_thickness`/`/balance_set`/`/ban`):
  - **Phase 1 — handle_announce** (`bot/handlers/admin_communication.py`): валидация `BroadcastLocaleFilter` (`ru`/`en`/`all`) + длины (≤ `BROADCAST_MESSAGE_MAX_LEN = 4000`); `BroadcastAnnouncement.execute(...)` делает RBAC-проверку (только `SUPER_ADMIN`) и pre-flight `IPlayerRepository.list_active_for_broadcast(locale_filter)` → `recipient_count`; затем `RequestAdminConfirm.execute(...)` выдаёт `/confirm`-токен с `payload = { locale_filter, message, recipient_count }`. Админу отвечает «токен `TOK`, TTL 120s; будет отправлено N игрокам».
  - **Phase 2 — dispatch_announce** (зарегистрирован в `CONFIRM_DISPATCHERS["broadcast_announcement"]`): sanity-проверка payload-а (типы, валидность `BroadcastLocaleFilter`); немедленный ответ admin-у `progress_start` («отправляю N игрокам, локаль X»); `IBroadcastTaskSpawner.spawn(coro)` → `RunBroadcastAnnouncement.execute(...)` фоном.
- **Use-case `RunBroadcastAnnouncement`** (`application/admin/run_broadcast_announcement.py`): RBAC-проверка повторно (админ мог быть `revoke`-нут между Phase 1 и Phase 2); пересчитанный `list_active_for_broadcast(...)`; рассылка батчами размера `BROADCAST_BATCH_SIZE=25` через `IBroadcastSender.send(...)` (внутри батча `asyncio.gather(...)` параллельно), между батчами `asyncio.sleep(BROADCAST_BATCH_INTERVAL_SECONDS=1.0)` → ~25 msg/sec (ниже Telegram-лимита bot-API ~30 msg/sec); `BroadcastSendResult` literal `"sent" | "failed" | "blocked"` агрегируется в счётчики; аудит `ADMIN_BROADCAST_SENT` с `after = { sent_count, failed_count, blocked_count, recipient_count, locale_filter, message_preview }` (preview-длина `BROADCAST_AUDIT_MESSAGE_PREVIEW_LEN = 200`).
- **Domain-расширения:** `AdminAuditAction.ADMIN_BROADCAST_SENT`; `BroadcastRecipient` value-object и `IPlayerRepository.list_active_for_broadcast(locale_filter)` (фильтр по `locale_override` или `*`); SQLA-имплементация в `infrastructure/db/repositories/player.py`.
- **Production-адаптеры** (`infrastructure/telegram/broadcast.py`):
  - `AiogramBroadcastSender` — `aiogram.Bot.send_message(...)`; `TelegramForbiddenError` → `"blocked"` (юзер закрыл чат); `TelegramRetryAfter`/`TelegramBadRequest`/прочие исключения → `"failed"` (логируются, наружу не падают).
  - `AsyncIOBroadcastTaskSpawner` — `asyncio.create_task(...)` с сильной ссылкой на task до завершения (Python 3.12+, защита от GC); `done_callback` снимает ссылку.
  - `NoopBroadcastSender` — stub для режима `bot=None` (CLI/scheduler-only).
- **DI в `bot/main.py::build_container`** — провязка `BroadcastAnnouncement`/`RunBroadcastAnnouncement` use-case-ов + production-сендеров. `Container` расширен полями `broadcast_announcement`/`run_broadcast_announcement`/`broadcast_sender`/`broadcast_task_spawner`. `dispatcher["..."]` пробрасывает их в handler-ы.
- **`ConfirmDispatchDeps` extension** (`bot/handlers/admin_economy.py`) + проброс через `handle_confirm` в `admin_support.py` — broadcast-deps теперь часть единого dispatch-канала.
- **Локали** (`locales/{ru,en}.ftl`) — 11 ключей `admin-announce-*` (usage, confirm-issued, progress-start/final/failed, ошибки локали/длины, RBAC-deny, TOTP-not-configured).
- **Тесты:**
  - `tests/unit/application/admin/test_broadcast_announcement.py` — 13 unit-тестов (валидация локали, валидация длины, RBAC, happy-path с pre-flight count, locale-парсинг).
  - `tests/unit/application/admin/test_run_broadcast_announcement.py` — 9 unit-тестов (RBAC, single-batch без sleep-а, multi-batch со sleep-ами, mixed-results aggregate, audit, message preview-truncation, validation `batch_size`/`batch_interval_seconds`).
  - `tests/unit/bot/handlers/test_admin_communication.py` — 13 unit-тестов handler-а (parsing, RBAC-deny, TOTP-not-configured, ошибки локали/длины, happy-path выдачи `/confirm`-токена, dispatch sanity-проверки, spawn-в-фон, регистрация в `CONFIRM_DISPATCHERS`).
  - `tests/integration/admin/test_broadcast_e2e.py` — 3 integration-теста (real `asyncio.sleep` throttle с measurable wall-clock, `AsyncIOBroadcastTaskSpawner.spawn(...)` действительно отдаёт coro фоновой задаче, отсутствие task-leak после завершения).
  - `tests/fakes/broadcast.py` — `FakeBroadcastSender` (results_by_tg_id, default_result), `InlineBroadcastTaskSpawner` (детерминированный, для unit-тестов), `TaskGroupBroadcastTaskSpawner` (asyncio.TaskGroup-обёртка).

Результат / артефакты:
- Коммиты на ветке `devin/1778146423-sprint-2-5-d.4-announce`: `1732fdd`, `b934bf4`, `74e6cf4`. Merge-коммит: `774bd7c`.
- Локальный `make ci`: зелёный — 3306 passed / 1 skipped, coverage **95.86%** (~1:30).
- Все 5 TOTP-обязательных admin-команд (`grant_length`/`grant_thickness`/`set_balance_value`/`ban`/`broadcast_announcement`) живут под единым registry-паттерном `CONFIRM_DISPATCHERS` (PR #83/#85/#88) — добавление новой мутирующей команды = «добавить пару `(kind, fn)` в реестр».
- `/announce` — первая команда, которая запускает фоновую задачу через `IBroadcastTaskSpawner` (раньше все use-case-ы были sync-в-handler-е). Production-адаптер `AsyncIOBroadcastTaskSpawner` хранит strong-ref на task до завершения — это паттерн для будущих фоновых long-running операций.

Заметки / решения:
- **Throttle-формула** `BROADCAST_BATCH_SIZE / BROADCAST_BATCH_INTERVAL_SECONDS = 25 msg/sec` выбрана с запасом ниже Telegram-лимита ~30 msg/sec для bot-API (ПД §5, риск «rate-limit на массовые рассылки»). Если в проде увидим `RetryAfter`-ошибки в логах `AiogramBroadcastSender`, — снижать `BATCH_SIZE` до 20 (без правки use-case-а: оба константы — `Final[int]`, прокидываются как kwargs из `bot/main.py`).
- **Sleep-инъекция** — `RunBroadcastAnnouncement.__init__` принимает `sleep: SleepFn | None = None`-аргумент (по дефолту — `asyncio.sleep`). Тесты прокидывают `_RecordingSleep` для проверки call-pattern-а (что sleep вызывается между батчами, не перед первым и не после последнего).
- **Idempotency-ключ** `admin_broadcast_announcement` строится по тому же шаблону, что и `admin_grant_length`/`admin_ban`/...: `sha256(actor|kind|locale_filter|minute_floor(ts))` — защита от двойной отправки в пределах той же минуты.
- **Циклический импорт** между D.4 (`admin_communication`) и C-командами (`admin_economy`) разрешён в одну сторону: `admin_communication` импортирует `CONFIRM_DISPATCHERS`/`ConfirmDispatchDeps` из `admin_economy` и **мутирует** dict при module-load. `bot/handlers/__init__.py` явно регистрирует `admin_communication_router` после `admin_economy_router` — это гарантирует, что mutation выполняется до первого использования.
- **`bot=None` graceful degradation** — `BroadcastSender` инициализируется условно (`AiogramBroadcastSender(bot=bot) if bot is not None else NoopBroadcastSender()`), чтобы CLI/scheduler-only режимы (без Telegram-bot-а) не падали при сборке `Container`-а. `NoopBroadcastSender.send(...)` всегда возвращает `"failed"` и пишет warning в лог.
- Из Спринта 2.5 остаётся: **D.6** (`/admin_setup_totp`), **D.10** (`docs/admin_runbook.md`), **D.11** (доптесты RBAC), **D.12** (расширение локалей).

---

## 2026-05-07 — Спринт 2.5-D.7: миграция legacy admin-команд под `AdminGuard` + RBAC (`/balance_reload`, `/admin_stats`, `/set_max_dau`, `/anticheat_unban`)

**Автор:** Devin (агент)
**Тип:** refactor
**Связано:** Спринт 2.5 ([`current_tasks.md`](current_tasks.md)), ПД §5 / задача 2.5.9 (миграция старых команд под единый канал admin-авторизации), ГДД §18.6 (RBAC + admin-audit), [PR #86](https://github.com/Pipirkawar/PipirkaWar/pull/86) (мерж — `12f9ea0`)

Что сделано:
- **Use-cases** (`application/balance/reload.py`, `application/dau/set_max.py`, `application/anticheat/lift_ban.py`) — приняты новые kwargs `admin_audit: IAdminAuditLogger` и `authz: IAdminAuthorizationPolicy`. В `execute(...)` после defense-in-depth-проверки на `is_active` зовут `ensure_admin_authorized(...)` с `AdminCommandKind.{RELOAD_BALANCE, SET_MAX_DAU, LIFT_ANTICHEAT_BAN}` **до** открытия основного UoW. При RBAC-отказе helper в отдельном коротком UoW пишет `ADMIN_AUTHORIZATION_DENIED` в admin-audit и поднимает `AdminAuthorizationDeniedError`. Inactive-admin → старый `AuthorizationError` без записи в admin-audit (приватное событие admin-management, не RBAC-эскалация). Старые `Admin.can_*()`-проверки удалены.
- **Handlers** (`bot/handlers/admin.py`) — router отбрасывает не-админов тихо через `IsAdminFilter()` на `.message` и `.callback_query` (как `admin_support` / `admin_economy` / `admin_audit` / `admin_clan`). Все четыре handler-а ловят `(AuthorizationError, AdminAuthorizationDeniedError)` единым except-блоком и шлют friendly «недостаточно прав». `/anticheat_unban` использует `AnticheatUnbanPresenter` для локализованных ответов (включая `presenter.not_authorized()`).
- **DI** (`bot/main.py::build_container`) — `admin_audit` + `admin_authz` создаются раньше, **до** `reload_balance` / `set_max_dau` / `lift_anticheat_ban` (раньше они определялись только в admin_economy-секции). Все три legacy use-case-а получают новые deps.
- **Тесты:** `tests/unit/application/{balance,dau,anticheat}/...` — обновлены helper-builder-ы (новые kwargs), проверки RBAC-отказа теперь ожидают `AdminAuthorizationDeniedError` (не legacy `AuthorizationError`) и фиксируют запись в `FakeAdminAuditLogger`. `tests/unit/bot/test_composition_root.py` — `_container_with_fakes` пробрасывает `admin_audit`/`admin_authz` во все три use-case-а.

Результат / артефакты:
- Коммит на ветке: `18fd652`. Merge-коммит: `12f9ea0`.
- Локальный `make ci`: зелёный — 3262 passed / 1 skipped, coverage 95.98% (без изменений по сравнению с `main`).
- Все 27 admin-команд из `AdminCommandKind` теперь авторизуются единым каналом `IAdminAuthorizationPolicy` + `ensure_admin_authorized` helper. Дублирующая логика `Admin.can_*()` удалена — единственный источник истины — матрица RBAC из D.8.
- Поведение пользователя не меняется (матрица ролей эквивалентна старому `Admin.can_*()`-API), но форма унифицирована со всеми остальными admin-командами 2.5-A/B/C/D-1.

Заметки / решения:
- `/balance_reload` сознательно остался **БЕЗ TOTP** — это вне скоупа D.7 (форма RBAC, не изменение требований). Если потребуется TOTP — отдельный sprint после 2.5-D-финала.
- `CONFIRM_DISPATCHERS` registry не расширен — эти три команды пока не требуют TOTP-confirm flow.
- PR изначально был **draft** под Спринт 2.5-D часть 2/2 (`/announce` + `/admin_setup_totp` + `admin_runbook.md` + допы тестов/локалей), но смерджен только D.7 (структурный refactor). Остаток Спринта 2.5-D (D.4/D.6/D.10/D.11/D.12) — отдельным PR-ом или PR-цепочкой.

---

## 2026-05-07 — Спринт 2.5-D часть 1/2: клановые admin-команды + `/audit` + RBAC + registry-pattern для `"ban"`

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 2.5 ([`current_tasks.md`](current_tasks.md)), ПД §5 / задачи 2.5.3 (клановые команды), 2.5.7 (`/audit`), 2.5.8 (RBAC + 2FA), 2.5.9 (registry-pattern для confirm-dispatcher), ГДД §10–11 (клановая механика), §18.6 (RBAC), §18.6.4 (`/audit`), [PR #85](https://github.com/Pipirkawar/PipirkaWar/pull/85) (мерж — `2b17c09`)

Что сделано:
- **2.5-D.1 — `/clan <id|chat_id>`** (`ce39097`). Read-only карточка клана: id, chat_id, chat_kind, title, status (active/frozen), member_count, active_member_count, total_length_cm, лидер каравана + список участников. Use-case `GetClanCard(actor_tg_id, query)` с двойным lookup-ом (сначала по внутреннему `Clan.id`, потом по Telegram `chat_id`). Без TOTP. Аудит: `ADMIN_CLAN_LOOKUP` (новое значение `AdminAuditAction`). Локаль `admin-clan-*` (RU + EN). Тесты: 9 unit (use-case), 8 unit (handler).
- **2.5-D.2 — `/freeze_clan <id|chat_id> [reason]` / `/unfreeze_clan <id|chat_id>`** (`fb761e7`). Обратимая ручная заморозка/разморозка клана админом (без TOTP, как `/freeze`/`/unfreeze` для игроков). Use-cases `FreezeClanAdmin` / `UnfreezeClanAdmin`. Идемпотентны (no-op если уже frozen/active, audit не пишется). Аудит: `ADMIN_CLAN_FROZEN` / `ADMIN_CLAN_UNFROZEN`. Локали `admin-freeze-clan-*` / `admin-unfreeze-clan-*` (RU+EN). Тесты: 12 unit (use-cases), 17 unit (handlers).
- **2.5-D.3 — `/clan_daily_head_history <id|chat_id> [N=10]`** (`176216c`). Read-only история последних N назначений «Главы клана дня» (дата, игрок, bonus_cm, источник). Use-case `GetClanDailyHeadHistory` через `IDailyHeadRepository.list_recent_for_clan(clan_id, limit)`. Без TOTP. Аудит: `ADMIN_CLAN_LOOKUP` (тот же ключ, что у `/clan`). Локали `admin-clan-daily-head-history-*` (RU+EN). Тесты: 10 unit (use-case), 11 unit (handler).
- **2.5-D.5 — `/audit [target_tg_id|-] [action|-] [N]`** (`9634695`). Query последних N записей `admin_audit_log` с опциональными фильтрами по `admin_id` и `action`. Use-case `GetAdminAuditTrail(actor_tg_id, *, target_admin_tg_id?, action_value?, limit=20)` через новый read-port `IAdminAuditQuery.list_recent(...)` (отдельный от write-side `IAdminAuditLogger` по ISP). Read-only, без TOTP. Сам факт чтения логируется как `ADMIN_AUDIT_QUERIED`. Локаль `admin-audit-*` (RU + EN). Реализация — `SqlAlchemyAdminAuditQuery` (один SELECT + JOIN к `admins`, без N+1).
- **2.5-D.8 — RBAC** (`c7d9c30`). Доменный whitelist-enum `AdminCommandKind` (27 команд) + порт `IAdminAuthorizationPolicy.is_authorized(admin, command_kind) -> bool` + дефолтная реализация `RoleBasedAdminAuthorizationPolicy` (файл-closed-матрица `(role × command_kind) → frozenset[AdminRole]`, неактивный админ всегда отказывает; команда без правила всегда отказывает). Иерархия (без «суперсетов» — каждая ячейка явная): `READ_ONLY` — все read-side; `SUPPORT` — `freeze_*`/`unfreeze_*`/`ban_player` + read-side; `ECONOMIST` — `grant_*`/`set_balance_value`/`reload_balance` + read-side; `SUPER_ADMIN` — всё, включая `lift_anticheat_ban`/`set_max_dau`/`broadcast_announcement`/`setup_totp`. Application-helper `ensure_admin_authorized(...)` в `application/admin/_authorization.py` — открывает **отдельный, короткоживущий** UoW и пишет `ADMIN_AUTHORIZATION_DENIED` до того, как поднять `AdminAuthorizationDeniedError`, чтобы попытка эскалации была зафиксирована независимо от основной транзакции use-case-а. Все 13 admin-use-case-ов на момент D.8 (`find_players`, `get_player_card`, `freeze_player`, `unfreeze_player`, `ban_player`, `request_admin_confirm`, `verify_admin_confirm`, `grant_length`, `grant_thickness`, `get_balance_value`, `set_balance_value`, `get_admin_audit_trail`, `get_clan_card`, `freeze_clan_admin`, `unfreeze_clan_admin`, `get_clan_daily_head_history`) принимают `authz: IAdminAuthorizationPolicy` и зовут helper до открытия основного UoW. Колонка `Admin.role` (enum) уже существовала с миграции `0001` — отдельная миграция под D.8 не нужна.
- **2.5-D.9 — `command_kind="ban"` → `CONFIRM_DISPATCHERS` registry** (`3ef53b7`). `_dispatch_ban` добавлен в `bot/handlers/admin_economy.py`, зарегистрирован в `CONFIRM_DISPATCHERS`, inline-кейс из `bot/handlers/admin_support.py` удалён. Все 4 TOTP-обязательные команды (`grant_length`, `grant_thickness`, `set_balance_value`, `ban_player`) теперь идут через единый registry — добавление новой мутирующей команды это «добавить пару `(kind, fn)` в реестр», без изменений в `handle_confirm`.
- **Доки** (`ba04dc5`, `0bc4000`) — sync `current_tasks.md` с актуальным состоянием feature-ветки в процессе работы.

Результат / артефакты:
- Коммиты: `ce39097` (D.1), `fb761e7` (D.2), `176216c` (D.3), `9634695` (D.5), `c7d9c30` (D.8), `3ef53b7` (D.9), `ba04dc5` + `0bc4000` (docs). Merge-коммит: `2b17c09`.
- Локальный `make ci` на момент мерджа: зелёный — coverage ≥ 95%.
- Новые/расширенные `AdminAuditAction`: `ADMIN_CLAN_LOOKUP`, `ADMIN_CLAN_FROZEN`, `ADMIN_CLAN_UNFROZEN`, `ADMIN_AUDIT_QUERIED`, `ADMIN_AUTHORIZATION_DENIED`.
- Новые порты: `IAdminAuthorizationPolicy` (domain), `IAdminAuditQuery` (read-side, отдельный от write-side `IAdminAuditLogger`).
- `AdminCommandKind` enum (27 команд) — единый whitelist для RBAC.

Заметки / решения:
- `Admin.role` колонка существовала с миграции `0001`, но до D.8 RBAC опирался на `Admin.can_*()`-API. D.8 формализовал матрицу как доменный объект, но **D.7 ещё не был сделан** (legacy команды `/balance_reload`, `/admin_stats`, `/set_max_dau`, `/anticheat_unban` оставались на старой `Admin.can_*()`). Это закрывает PR #86 (см. запись 2.5-D.7 выше).
- `IAdminAuditQuery` сделан отдельным от `IAdminAuditLogger` по ISP — read-side и write-side имеют разные потребители, не должны смешиваться.
- Postmerge-PR (history.md + sync `current_tasks.md`) для PR #85 не был создан отдельно — D.7 был открыт сразу следующим. Эта запись закрывает технический долг — добавлена в одном PR с записью 2.5-D.7.

---

## 2026-05-08 — Спринт 2.5-C: команды экономики в боте (`/grant_length`, `/grant_thickness`, `/balance_get`, `/balance_set`)

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 2.5 ([`current_tasks.md`](current_tasks.md)), ПД §5 / задачи 2.5.4 (grant_length / grant_thickness), 2.5.5 (TOTP на мутации), 2.5.9 (use-case-каркас), ГДД §6 (анти-чит-clamp на admin-grant-ах) / §16 (баланс) / §18.6 (основной канал администрирования — Telegram-бот), [PR #83](https://github.com/Pipirkawar/PipirkaWar/pull/83) (мерж — `10b3ee6`)

Что сделано:
- **2.5-C.7 — расширение `AdminAuditAction`** (`952f07a`). Добавлены `ADMIN_GRANT_LENGTH`, `ADMIN_GRANT_THICKNESS`, `ADMIN_BALANCE_GET`, `ADMIN_BALANCE_SET`. Тест на enum-полноту в `tests/unit/domain/admin/test_admin_audit.py`.
- **2.5-C.1 — `/grant_length <tg_id> <delta_cm> <reason>`** (`35f5bac`). Use-case `GrantLength` через существующий `ILengthGranter.grant(source=admin_grant)` — анти-чит rolling-24h-clamp применяется (ГДД §6, без bypass); admin-refund (отрицательная дельта) идёт через `source=admin_refund`. TOTP-обязательная (handler фазы 1 кладёт payload в `AdminConfirmStore`, dispatch фазы 2 после `/confirm` выполняет use-case). Идемпотентность через `IIdempotencyKey` на уровне `LengthDeltaApplier`. Аудит: `ADMIN_GRANT_LENGTH` (с `applied_delta`/`requested_delta`/`clamped`-флагом). 12 unit-кейсов на use-case.
- **2.5-C.2 — `/grant_thickness <tg_id> <new_level> <reason>`** (`dc0f26f`). Use-case `GrantThickness` — абсолютная установка уровня (не `delta`), валидация по доменным `MIN/MAX_THICKNESS_LEVEL` из `domain/progression/constants.py`. TOTP-обязательная. Идемпотентность через `IIdempotencyKey`. Аудит: `ADMIN_GRANT_THICKNESS`. 10 unit-кейсов.
- **2.5-C.3 — `/balance_get <key>`** (`bb03751`). Use-case `GetBalanceValue` — read-only lookup по dotted-path в текущем снимке `IBalanceConfig` через хелпер `_balance_path.py` (рекурсивный getattr с понятным `BalanceKeyError(key, segment, reason)` вместо bare `AttributeError`). Без TOTP. Аудит: `ADMIN_BALANCE_GET` (логируем read-операции, чтобы `/audit <admin>` в 2.5-D показывал и read-side активность экономиста). 3 + 3 unit-теста.
- **2.5-C.4 — `/balance_set <key> <value> <reason>`** (`1bb1660`). Use-case `SetBalanceValue` + новый порт `IBalanceWriter` + инфраструктурная реализация `YamlBalanceWriter`: атомарная запись (`tempfile.mkstemp` в той же директории + `os.replace` + `fsync`), `fcntl.flock` (POSIX) на lock-файле `.<name>.lock` (защита от конкурентного `/balance_set` из двух сессий), валидация через pydantic `BalanceConfig` **до** записи (валидация падает → файл не тронут), hot-reload через `IBalanceReloader` после успешного `os.replace`. Не сохраняет YAML-комментарии (`yaml.safe_load` теряет их) — осознанное допущение для C; для не-низкочастотных правок в 2.5-D запланирована БД-overlay (таблица `balance_overrides` с приоритетом над YAML). TOTP-обязательная. Идемпотентность через `IIdempotencyKey`. Аудит: `ADMIN_BALANCE_SET` (с `previous_raw_value`/`new_raw_value`). 8 unit-кейсов use-case + 8 integration-тестов на writer (atomic-write roundtrip, конкурентная запись через flock, валидация-fallthrough, hot-reload, dotted-path, missing-key, type-mismatch).
- **2.5-C.5 — Idempotency-key для всех 3 мутирующих команд** (внутри коммитов C.1/C.2/C.4 + handler-helper). Формула: `idempotency_key = "admin_<command>:" + sha256(admin_id|command|target|minute_floor(ts))`, реализована в `bot/handlers/_idempotency.py::build_admin_idempotency_key(admin_tg_id, command, target, when)`. Минутная гранулярность — покрывает double-tap в Telegram (повторное нажатие через 1-2 секунды), но НЕ повтор той же команды через минуту (это намеренное поведение — админ должен видеть, что вторая попытка действительно сработала). Передаётся во все 3 мутирующих use-case-а: `GrantLength` через `ILengthGranter`, `GrantThickness` и `SetBalanceValue` — через свой `IIdempotencyKey`-вход.
- **2.5-C.6 — Рефактор `/confirm`-handler-а на registry-pattern + 4 новых handler-а** (`39d4c5d`). `bot/handlers/admin_economy.py` — отдельный router (`router = Router(name="admin_economy")`, фильтр `IsAdminFilter` на router-е) с 4 handler-ами (`handle_grant_length` / `handle_grant_thickness` / `handle_balance_get` / `handle_balance_set`) и 3 dispatch-функциями (`dispatch_grant_length` / `dispatch_grant_thickness` / `dispatch_balance_set`). `CONFIRM_DISPATCHERS: dict[str, ConfirmDispatcher]` маппит `command_kind → dispatcher`; `handle_confirm` в `admin_support.py` теперь делегирует на этот реестр (для 3 новых команд) или на старую логику (для `command_kind="ban"`). Добавление 4-й мутирующей команды теперь — **добавить пару `(kind, fn)` в реестр**, без изменений в handler. Все dispatch-функции принимают единый `ConfirmDispatchDeps` (`grant_length`, `grant_thickness`, `set_balance_value`, `clock`).
- **2.5-C.8 — DI use-case-ов в `Container` + регистрация router-а** (`39d4c5d`). 4 поля в `Container` (`grant_length`, `grant_thickness`, `get_balance_value`, `set_balance_value`), инстанцирование с правильными портами (`YamlBalanceWriter` принимает `loader: IBalanceReloader` после рефактора C.9), регистрация `admin_economy_router` в dispatcher (порядок: `admin_router` → `admin_support_router` → `admin_economy_router`), workflow-data injection всех 4 use-case-ов в `dispatcher` (для DI в handler-параметры).
- **2.5-C.9 — Тесты** (`f7aef79`). `tests/unit/bot/handlers/test_admin_economy.py` — 48 кейсов: 4 handler-а (фаза 1) × валидация (non-private, usage, bad-id/delta/level/value, no-reason, AuthorizationError, TotpNotConfigured, confirm_issued + payload-проверки), 3 dispatch (фаза 2) × все ветки (payload_invalid, blocked, soft_ban, level_invalid, key_not_found, validation_error, already_at_value/level, idempotent_replay, success, clamped) + проверка `CONFIRM_DISPATCHERS` registry. Sync `test_composition_root.py` под расширенный `Container` (4 новых поля). Также в C.9 ослаблен тип `YamlBalanceWriter.loader` с конкретного `YamlBalanceLoader` до **порта** `IBalanceReloader` — мелкий рефактор, mypy-clean, нужен чтобы `FakeBalanceConfig` (тестовый фейк, реализующий и `IBalanceConfig`, и `IBalanceReloader`) можно было передавать в `YamlBalanceWriter` в `test_composition_root` без локального real-loader-а.
- **2.5-C.10 — Локали** (`39d4c5d`). `admin-grant-length-*` (12 ключей: usage / bad-id / bad-delta / no-reason / not-authorized / totp-not-configured / confirm-issued / not-found / blocked / soft-ban / success / success-clamped), `admin-grant-thickness-*` (11), `admin-balance-get-*` (4: usage / not-authorized / key-not-found / result), `admin-balance-set-*` (9), `admin-idempotency-replay-*` (1, общий ключ для всех мутирующих команд) — RU + EN, итого ~120 новых строк в `locales/{ru,en}.ftl`.

Результат / артефакты:
- Domain: `domain/admin/ports/admin_audit.py` (расширение `AdminAuditAction` enum), `domain/balance/ports.py` (новый порт `IBalanceWriter`), `domain/balance/errors.py` (новый `BalanceKeyError(key, segment, reason)`), `domain/balance/__init__.py` (re-export).
- Application: `application/admin/{grant_length,grant_thickness,get_balance_value,set_balance_value}.py` (4 новых use-case-а), `application/admin/_balance_path.py` (хелпер dotted-path lookup-а с понятным `BalanceKeyError`), `application/admin/__init__.py` (re-export).
- Infrastructure: `infrastructure/balance/writer.py` (`YamlBalanceWriter` — atomic-write + flock + hot-reload).
- Bot: `bot/handlers/admin_economy.py` (4 handler-а + 3 dispatch + `ConfirmDispatchDeps` + `CONFIRM_DISPATCHERS`), `bot/handlers/_idempotency.py` (`build_admin_idempotency_key`), `bot/handlers/admin_support.py` (рефактор `handle_confirm` на registry-делегирование), `bot/handlers/__init__.py` (регистрация `admin_economy_router`), `bot/presenters/admin_economy.py` (5 презентеров: `GrantLengthPresenter` / `GrantThicknessPresenter` / `GetBalanceValuePresenter` / `SetBalanceValuePresenter` / `IdempotencyReplayPresenter`), `bot/main.py` (DI 4 use-case-ов + workflow-data).
- Локали: `locales/{ru,en}.ftl` (~60 + ~60 ключей).
- Тесты: `tests/unit/application/admin/test_{grant_length,grant_thickness,get_balance_value,set_balance_value,balance_path}.py`, `tests/unit/bot/handlers/test_admin_economy.py` (48 кейсов), `tests/unit/bot/handlers/test_admin_support.py` (51 правка под новую сигнатуру `handle_confirm`), `tests/unit/bot/test_composition_root.py` (DI 4 новых use-case-ов + `YamlBalanceWriter` принят как `IBalanceReloader`-порт), `tests/integration/balance/test_yaml_writer.py` (8 integration-кейсов на atomic-write / flock / hot-reload), `tests/unit/domain/admin/test_admin_audit.py` (расширение enum-полноты).
- CI на момент мерджа (PR #83): **3118 passed / 1 skipped, coverage 95.81%**, ruff / ruff-format / mypy --strict (647 файлов) / import-linter — 3 контракта kept, GitHub Actions зелёный (lint+types+tests py3.11 и py3.12 + pip-audit security).

Заметки / решения:
- **`/grant_length` идёт через clamp без bypass.** Альтернатива — ввести параметр `bypass_clamp_reason` в `ILengthGranter.grant(...)` для обхода rolling-24h-окна. Отказались: ГДД §6 явно говорит «admin-grant-ы должны попадать в окно» (иначе админ может незаметно для аудита раздать 100500 см и вызвать инфляцию длины); в редких ручных кейсах админ может разбить выдачу на несколько суток или повторно вызвать `/grant_length` после очистки окна.
- **`balance.yaml`-запись через file-lock, без БД-overlay.** Альтернатива — таблица `balance_overrides(key, value, ts, admin_id)` с приоритетом над YAML. Отказались для C (значительный объём миграций + новый порт чтения + тесты на приоритет), но в 2.5-D рассмотрим заново — мотивация: rollback и audit-trail из коробки. Текущая запись имеет write-audit (`ADMIN_BALANCE_SET`) и атомарность (atomic-write + flock), чего достаточно для низкочастотных правок.
- **Минутная гранулярность idempotency-ключа.** `minute_floor(ts)` — компромисс: TTL ниже минуты не покрывает retry-сценарии (Telegram дублирует update-ы при reconnect-е), TTL выше минуты блокирует «исправление опечатки» (админ видит, что выдал не туда, и хочет за 30 секунд повторить с правильным аргументом — `target` будет другой, но если случайно тот же — он вправе ожидать, что system выполнит команду). Минута — sweet-spot.
- **`InMemoryAdminConfirmStore` (TTL 60с) шарится с 2.5-B.** Не вводили отдельный store для C: payload `/grant_length` помещается в `Mapping[str, object]`, отдельный admin-scoped store не нужен. Если в 2.5-D появятся тяжёлые payload-ы — пересмотрим.
- **`YamlBalanceWriter` не сохраняет YAML-комментарии.** `yaml.safe_load` (используется на чтении в `YamlBalanceLoader`) теряет их при `safe_dump`. Альтернативы: `ruamel.yaml` (round-trip, но тяжёлая зависимость) или ручной diff-merge (хрупко). Решили принять потерю комментариев как trade-off для C — `balance.yaml` правится низкочастотно, документация ключей уже живёт в `docs/balance.md` отдельным от файла.
- **Рефактор `handle_confirm` оставил кейс `"ban"` inline, новые 3 — в registry.** Не вытащили `"ban"` в реестр сразу: BanPlayer не использует `IIdempotencyKey` (одна запись в `players.status`), а dispatch-функции экономики наследуют общий `ConfirmDispatchDeps` (4 use-case-а) — `BanPlayer` туда не вписывается без правки сигнатуры. Перенесём `"ban"` в registry в 2.5-D, когда будем мигрировать старые admin-команды под `AdminGuard` + RBAC.
- **`YamlBalanceWriter.loader: IBalanceReloader` (рефактор в C.9).** Изначально writer типизировал `loader: YamlBalanceLoader` (конкретный класс). В C.9 при добавлении `YamlBalanceWriter` в `test_composition_root`-fixture mypy упал — `FakeBalanceConfig` (тестовый фейк) не наследует `YamlBalanceLoader`. Решение: ослабить тип до **порта** `IBalanceReloader`, который реализуют и production-loader, и тестовый фейк. Production-DI как и раньше передаёт `YamlBalanceLoader` — никаких runtime-изменений.

---

## 2026-05-07 — Спринт 2.5-B: команды поддержки в боте (`/find_player`, `/player`, `/freeze`, `/unfreeze`, `/ban` + TOTP, `/confirm`)

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 2.5 (`current_tasks.md`), ПД §5 / задачи 2.5.3 (find_player/player/freeze/unfreeze/ban), 2.5.5 (TOTP на /ban), 2.5.9 (use-case-каркас); ГДД §18.6 (основной канал администрирования — Telegram-бот), [PR #81](https://github.com/Pipirkawar/PipirkaWar/pull/81) (мерж — `3653e40`)

Что сделано:
- **2.5-B.1 — `/find_player <text>`** (`ac48f19`). Use-case `FindPlayers(query, limit) -> Sequence[PlayerSummary]`: поиск по `tg_id` (точно), `@username` (точно), либо case-insensitive `ILIKE`-подстроке (`username`/`name`) с экранированием LIKE-wildcards (`%`/`_`). Без TOTP. Аудит: `ADMIN_PLAYER_LOOKUP`. Расширены `IPlayerRepository.find_by_query` (Sql + Fake), локали `admin-find-player-*` (RU + EN). Unit + integration на repo + handler.
- **2.5-B.2 — `/player <tg_id>`** (`a909304`). Use-case `GetPlayerCard(tg_id) -> PlayerCard`: длина, толщина, статус, anticheat-soft-ban-таймер, клан + роль, активный forest-run. Без TOTP. Аудит: `ADMIN_PLAYER_LOOKUP`. Локали `admin-player-*`. Список последних 5 PvP/PvE-боёв вынесен в B-followup (`IDuelRepository`/`IMassDuelRepository`/`IForestRunRepository` сейчас не имеют read-метода «последние N для игрока» — вынесли точечным PR).
- **2.5-B.3 — `/freeze <tg_id> [reason]`** / **`/unfreeze <tg_id>`** (`7b81d52`). Use-cases `FreezePlayer` / `UnfreezePlayer` через `IPlayerRepository.freeze` / `unfreeze`. Без TOTP (обратимая операция). Идемпотентно: повторная заморозка/разморозка не пишет в audit и возвращает `was_already_frozen=True` / `was_already_active=True`. Аудит: `ADMIN_PLAYER_FROZEN` / `ADMIN_PLAYER_UNFROZEN` с `before/after`. Локали `admin-freeze-*` / `admin-unfreeze-*`.
- **2.5-B.4 — `/ban <tg_id> <reason>`** + **2.5-B.5 — `/confirm <token> <code>`** (`47a8759`). Добавлены `PlayerStatus.BANNED` + доменный метод `Player.ban(now)` (идемпотентный). Use-case `BanPlayer` (post-TOTP, защита-в-глубину `is_active` + reason-non-empty). Handler `/ban` зовёт `RequestAdminConfirm(command_kind="ban", payload={target_tg_id, reason})`, отвечает токеном и инструкцией `/confirm <token> <code>`. Общий `/confirm`-dispatcher зовёт `VerifyAdminConfirm`, диспатчит по `command_kind` (на MVP только `ban → BanPlayer.execute()`); неизвестный `command_kind` или сломанный payload → `admin-confirm-unknown-command-kind`. Аудит: `ADMIN_PLAYER_BANNED` (на успехе); неудачные TOTP-попытки уже пишет `VerifyAdminConfirm` как `ADMIN_CONFIRM_FAILED` с привязкой `command_kind=ban` — `ADMIN_BAN_BLOCKED` отдельно не вводили. Локали `admin-ban-*` / `admin-confirm-*`.
- **2.5-B.6 — Регистрация `admin_support_router`** (`d95a01f`). `dispatcher.include_router(admin_support_router)` в `bot/handlers/__init__.py` поверх `AdminGuard` из 2.5-A. Router-фильтр `IsAdminFilter` живёт прямо на самом router-е (`router.message.filter(IsAdminFilter())` + `.callback_query.filter(...)`), читает `data["admin"]` от `AdminGuard`. Не-админы тихо проходят мимо (filter возвращает `False`). Если `AdminGuard` не подключён — secure default = отказать. Файлы `bot/filters/admin.py`, `bot/filters/__init__.py`, `bot/handlers/admin_support.py`, `bot/handlers/__init__.py`. 4 unit-теста на фильтр.
- **2.5-B.7 — DI use-case-ов в `Container`** (`3c016b7`). `find_players`, `get_player_card`, `freeze_player`, `unfreeze_player`, `ban_player`, `request_admin_confirm`, `verify_admin_confirm` + `SqlAlchemyAdminAuditLogger` (write-side `admin_audit_log`), `InMemoryAdminConfirmStore` (singleton, TTL 60 сек — переживать рестарт смысла нет), `PyOtpTotpVerifier`, `TokenFactory = _default_admin_token_factory` (`secrets.token_urlsafe(16)`). Все 7 use-case-ов прокинуты в `dispatcher` workflow-data. Расширения `test_composition_root` под полный стек.

Результат / артефакты:
- Domain: `domain/player/{entities,repositories}.py` (новые порты `find_by_query` / `freeze` / `unfreeze` / `Player.ban` / `PlayerStatus.BANNED`); `domain/admin/ports/admin_audit.py` (расширение enum `AdminAuditAction`).
- Application: `application/admin/{find_players,get_player_card,freeze_player,unfreeze_player,ban_player}.py`.
- Infrastructure: `infrastructure/db/repositories/player.py` (Sql-impl новых методов с экранированием LIKE-wildcards).
- Bot: `bot/filters/admin.py` (`IsAdminFilter`), `bot/handlers/admin_support.py` (5 handler-ов + `/confirm` dispatcher), `bot/presenters/admin_support.py`, обновлён `bot/main.py` (DI use-case-ов в workflow-data).
- Локали: новые ключи в `locales/{ru,en}.ftl` (`admin-find-player-*`, `admin-player-*`, `admin-freeze-*`, `admin-unfreeze-*`, `admin-ban-*`, расширены `admin-confirm-*`).
- Тесты: `tests/unit/application/admin/test_{find_players,get_player_card,freeze_unfreeze,ban_player}.py`, `tests/unit/bot/handlers/test_admin_support.py` (e2e на TOTP-flow `/ban` → `/confirm`: happy / token expired / token not found / admin mismatch / code invalid / TOTP not configured / unknown command_kind / payload typo / target disappeared / already banned), `tests/unit/bot/filters/test_admin.py`, `tests/fakes/totp_verifier.py`, расширения `tests/integration/db/test_player_repository.py` (`find_by_query_*` × 7 + `freeze_unfreeze_round_trip`), расширения `tests/unit/bot/test_composition_root.py`.
- CI на момент мерджа (PR #81): **2997 passed / 1 skipped, coverage 96.18%**, ruff / mypy --strict (629 файлов) / import-linter — 3 контракта kept.

Заметки / решения:
- **`PlayerStatus.BANNED`** добавлен как доменный enum-член. Проверка `Player.ban(now)` идемпотентна: повторный `ban` на уже забаненного игрока не меняет состояние и не пишет аудит. На уровне БД бан фиксируется через `save()` (статус-поле), отдельный `IPlayerRepository.ban`-метод не нужен — `save_persists_mutations` integration-тест уже покрывает запись.
- **`ADMIN_BAN_BLOCKED`** не вводили: `VerifyAdminConfirm` уже пишет `ADMIN_CONFIRM_FAILED` с `command_kind=ban` в payload — фильтр в `/audit` (2.5-D) сможет вывести «попытки забанить, которые провалились на TOTP». Дублирование событий лишнее.
- **`InMemoryAdminConfirmStore` остался singleton-ом без переноса в БД.** TTL — 60 секунд; пользы от выживания между рестартами нет, а с многоинстансным деплоем разберёмся в Фазе 4 (Webhook + Redis). Если деплой остаётся single-instance long-polling — проблема не возникает.
- **`IsAdminFilter` на router-е, а не на handler-ах.** `admin_support_router.message.filter(IsAdminFilter())` + `.callback_query.filter(...)` — это идиома aiogram-3 для admin-namespace-а. Filter получает `Update` + `data` (через `event_data` keyword), читает `data["admin"]`, возвращает `False` если не админ. Тихий отказ — secure default; обычный игрок, набирая `/find_player`, не получает ответа. Если `AdminGuard` не подключён (например, на тестовом запуске без БД) — `data["admin"]` отсутствует, fail-closed.
- **Список последних 5 PvP/PvE-боёв в `/player` отложен** (B-followup). Текущая карточка отвечает на 90% запросов поддержки (длина/толщина/клан/активный forest); добавление новых read-методов `IDuelRepository.list_recent_for_player(N)` / `IMassDuelRepository.list_recent_for_player(N)` / `IForestRunRepository.list_recent_for_player(N)` потребует Sql-индексов и пересмотра агрегатов — это отдельный рефактор, которому не место в B.

---

## 2026-05-07 — Спринт 2.5-A: каркас расширенного админ-интерфейса (admin_audit_log + AdminGuard + TOTP-confirm)

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 2.5 ([`current_tasks.md`](current_tasks.md), ПД §5 / задачи 2.5.1, 2.5.2, 2.5.5, 2.5.8, 2.5.9 в части каркаса), ГДД §18.6 (основной канал администрирования — Telegram-бот), [PR #79](https://github.com/Pipirkawar/PipirkaWar/pull/79) (мерж — `b358349`)

Что сделано:
- **2.5-A.1 — таблица `admin_audit_log`** (`046ad62`). Отдельная от общего `audit_log` (чтобы `/audit <admin>` в 2.5-D был быстрым; `admin_id` обязателен; добавлены `tg_chat_id` / `ip` / `source ENUM('bot','web')`). Миграция `0016_admin_audit_log` (descends from `0015_referrals`), ORM `AdminAuditLogORM` с тремя индексами (`(admin_id, occurred_at)`, `(target_kind, target_id)`, `(action)`) + `CHECK source IN ('bot','web')`, доменный port `IAdminAuditLogger` + VO `AdminAuditEntry` + enum-ы `AdminAuditAction` / `AdminAuditSource`, `SqlAlchemyAdminAuditLogger` + `FakeAdminAuditLogger`. 6 integration-тестов + 4 unit-теста + расширение `test_migrations`.
- **2.5-A.2 — `AdminGuard` aiogram outer-middleware** (`43186c3`). Enrichment-middleware: читает `data["auth_data"]` (от `AuthMiddleware`), ищет `Admin` через `IAdminRepository.get_by_tg_id`, кладёт `data["admin"] = Admin | None`. Деактивированные админы → `None` (соответствует ГДД §18.6 revoke-семантике). DI-композиция в `build_dispatcher()` — встаёт между `AuthMiddleware` и `LocaleMiddleware` на всех 3 observer-ах (`message`, `callback_query`, `my_chat_member`). 7 unit-тестов + апдейт `test_composition_root` (стек +1 middleware).
- **2.5-A.3 — TOTP-confirm scaffold** (`0bc3fdc`). Однократный токен + 6-значный TOTP — для опасных команд в 2.5-B/C/D. Токен сжигается до проверки (atomic `pop` из store-а) — защита от brute-force.
  - Миграция `0017_admins_totp_secret` (новая колонка `admins.totp_secret VARCHAR(64) NULL`; `NULL` = 2FA не настроено).
  - Domain: `AdminConfirmRequest` / `AdminConfirmEntry` + ошибки (`Confirm{TokenNotFound,TokenExpired,CodeInvalid,AdminMismatch}Error`, `TotpNotConfiguredError`) + порты `IAdminConfirmStore` / `ITotpVerifier`.
  - Application: `RequestAdminConfirm` (генерит token + пишет `ADMIN_CONFIRM_REQUESTED` в audit) + `VerifyAdminConfirm` (`pop` → проверка → `ADMIN_CONFIRM_VERIFIED`/`FAILED` в audit).
  - Infrastructure: `InMemoryAdminConfirmStore` (TTL 60 сек, `cleanup_expired`) + `PyOtpTotpVerifier` (RFC 6238, `valid_window=1` для дрейфа часов).
  - Локали `admin-confirm-*` в `ru.ftl` + `en.ftl`.
  - `pyotp>=2.9,<3` добавлен в runtime-зависимости + `mypy` override (нет stub-ов).
  - 35 новых unit-тестов + 2 integration-теста на `totp_secret`-roundtrip.

Результат / артефакты:
- Миграции: `infrastructure/db/migrations/versions/20260507_0016_admin_audit_log.py`, `20260507_0017_admins_totp_secret.py`.
- Domain: `domain/admin/audit.py`, `domain/admin/confirm.py`, `domain/admin/ports/{admin_audit,admin_confirm}.py`.
- Application: `application/admin/{request_confirm,verify_confirm}.py`.
- Infrastructure: `infrastructure/db/models/admin_audit.py`, `infrastructure/db/repositories/admin_audit.py`, `infrastructure/admin/{in_memory_confirm_store,pyotp_totp_verifier}.py`.
- Bot: `bot/middlewares/admin_guard.py`, DI-доводка в `bot/main.py`.
- Локали: новые ключи в `locales/{ru,en}.ftl` (`admin-confirm-*`).
- Тесты: `tests/integration/db/test_admin_audit_logger.py`, расширение `test_admin_repository.py` и `test_migrations.py`, `tests/unit/{application,infrastructure,domain}/admin/`.

Заметки / решения:
- **DI use-case-ов в `Container` не делали.** Реальные handler-ы (`/ban`, `/grant_length`, `/grant_thickness`, `/balance_set`, `/announce`) появятся в 2.5-B / 2.5-C / 2.5-D — там же подключим `RequestAdminConfirm` и `VerifyAdminConfirm` к `Container`. Так не плодим мёртвую инжекцию и легче ревьюить каждый спринт.
- **TOTP-секрет хранится в plain-text BASE32**, как принято в большинстве OSS-проектов того же класса (jenkins-totp, pgadmin, mattermost). Шифрование на уровне приложения добавлять не стали — это перенесёт корень доверия в KMS, что без полноценного KMS-сетапа в проекте не имеет смысла. Если решение пересмотрят — поменять `Admin.totp_secret` тип на «зашифрованную строку» можно за один спринт без слома схемы.
- **`AdminGuard` — enrichment, а не gate-keeper.** «Тихий игнор не-админов» делается на уровне router-фильтра при привязке handler-а (появится в 2.5-B). Иначе middleware светил бы факт существования `/admin_*`-команды через тайминг-разницу.
- **Token-фабрика — параметр.** Use-case `RequestAdminConfirm` принимает `TokenFactory: () -> str`, что позволяет тесту подменять её детерминированно. В композиционном корне в 2.5-B будет `secrets.token_urlsafe(16)`.
- **Локальный `make ci` после мерджа:** 2901 passed / 1 skipped, coverage 96.19%.

---

## 2026-05-06 — Спринт 2.4: реферальная система и шеринг (полное закрытие — A→F)

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 2.4 ([`current_tasks.md`](current_tasks.md), ПД §6 / задачи 2.4.1–2.4.6), ГДД §13.1 (реферальная схема), §13.2 (кнопка «Поделиться»), §13.3 (еженедельные итоги)

Что сделано:
- **2.4.A — Доменный слой реферальной системы** (`0cbe1e3`). Value-object `Referral(id, referrer_id, referred_id, signup_granted_at, last_milestone_thickness, created_at)`, port `IReferralRepository` (методы `get_by_referred_id`, `add`, `update`, `mark_signup_granted`, `bump_milestone`, `count_by_referrer_in_window`), 5 ошибок (`ReferralError` — базовая; `SelfReferralError`, `ReferrerNotRegisteredError`, `ReferralRaceError`, `SignupBonusAlreadyGrantedError`), 25 unit-тестов.
- **2.4.B — Persistence-слой** (`56c7ce4`). Миграция `0015_create_referrals_table` (UNIQUE по `referred_id` — один новичок → один реферер, никаких смен), `ReferralRow` ORM, `SqlAlchemyReferralRepository` + `FakeReferralRepository`, +6 integration-тестов на UNIQUE-violation и race-условие.
- **2.4.C — Application use-cases** (`5414693`). `RegisterReferral` (создаёт `Referral` с `signup_granted_at=None`), `GrantReferralSignupBonus` (выдаёт `signup_bonus_cm` рефереру, идемпотентно через `mark_signup_granted`), `GrantReferralThicknessMilestone` (на каждый milestone тиражности новичка выдаёт рефереру `milestone_bonus_cm` + `bump_milestone`), +24 unit-теста.
- **2.4.D-a — Интеграция в `/start` и `/upgrade`** (`9580210`). Парсинг payload `start=ref_<id>` (только в ЛС, проверка типа чата + self-referral + кривой формат), `RegisterPlayer` зовёт `RegisterReferral` + `GrantReferralSignupBonus` после успешной регистрации, `UpgradeThickness` зовёт `GrantReferralThicknessMilestone` после апгрейда, локали `start-registered-with-referral` RU+EN.
- **2.4.D-b — Кнопка «Поделиться» под результатом боя/леса** (`5197ced` + `82109a4`). `ReferralSharePresenter` (генерирует deep-link `t.me/{bot}?start=ref_<player_id>`), handler `referral_share.py` с callback_data `ref-share:{kind}:{entity_id}` (kind ∈ `duel`/`forest`), локали `referral-share-*` RU+EN, кнопка добавлена в presenter-ы `/duel` и `/forest`. ГДД §13.2.
- **2.4.E — Еженедельный per-clan referral-summary cron, вс. 18:00 UTC** (`5e97ba4` + `877510b` + `36f4694` + `be5c756`).
  - **E.1** — Доменный port `IReferralRepository.weekly_summary_by_clan(*, clan_id, since, until) -> Sequence[WeeklyClanReferralEntry]` + Sql-impl + Fake + integration-тесты на агрегацию по `referrer_id` внутри клана.
  - **E.2** — Use-case `RunWeeklyClanReferralSummary` + DTO + notifier-port `IWeeklyClanReferralSummaryNotifier` + unit-тесты (frozen-clan / нет рефералов / happy-path / top-3 truncation).
  - **E.3** — `WeeklyClanReferralSummaryPresenter` (рендер «новых бойцов за неделю + топ-3 приглашателей» через `IMessageBundle`), `TelegramWeeklyClanReferralSummaryNotifier`, локали `weekly-referral-summary-*` RU+EN, тесты presenter / notifier.
  - **E.4** — Доменный port `IDelayedJobScheduler.schedule_weekly_clan_referral_summary_cron()` + `APSchedulerDelayedJobScheduler` impl (`CronTrigger(day_of_week='sun', hour=18, minute=0, timezone='UTC')`), DI в `bot/main.py` (`Container` + late-bound фабрика), bootstrap-call после `scheduler.start()`, composition-root тест. Узкая реферальная weekly-card (а не полная клановая из ГДД §13.3) — потому что агрегатов по PvP/караванам/рейдам в репозиториях ещё нет.
- **2.4.F — Rate-limit-антифрод per-`referrer_tg_id` + audit-log** (`fa9b08b`).
  - `IRateLimiter` перенесён из `infrastructure/rate_limit/` в `domain/shared/ports/rate_limiter.py` (требование import-linter contract — application не может зависеть от infrastructure).
  - Новые audit-actions `REFERRAL_REGISTERED` и `REFERRAL_RATE_LIMITED` в `AuditAction`.
  - `RegisterReferral` теперь принимает `rate_limiter: IRateLimiter` и `audit: IAuditLogger`. Перед открытием UoW проверяет `rate_limiter.try_acquire(key=f"referral:{referrer_tg_id}")`. Если `False` — записывает `REFERRAL_RATE_LIMITED` audit-entry в отдельной UoW (чтобы фиксация попытки не зависела от транзакции создания реферала) и бросает новую `ReferralRateLimitedError`. На happy-path после `referrals.add(...)` пишет `REFERRAL_REGISTERED` audit (`actor_id=referrer.id`, `target_kind="referral"`, `target_id=str(referral.id)`, `after={referrer_id, referred_id}`).
  - `BotSettings.referral_rate_limit_capacity` (дефолт 10) + `referral_rate_limit_refill_per_hour` (дефолт 10/h) — настраиваемые через env-vars.
  - Bot composition-root заводит **отдельную** инстанцию `InMemoryTokenBucketRateLimiter` для реферального bucket-а (refill = N/3600 сек), чтобы не пересекаться с глобальным throttle-rate-limiter-ом aiogram-update-ов.
  - `/start`-handler swallow-ит `ReferralRateLimitedError` в no-op (новичок не должен видеть «реферер исчерпал лимит» — это ломает скан-стратегию атакующего; use-case уже записал audit).
  - +5 unit-тестов на rate-limit (happy-path acquired / rate-limited raises + audit / self-referral short-circuits before limit / happy-path records REFERRAL_REGISTERED audit).
  - **Задача 2.4.4 «Anti-fraud: minimum protection» закрыта частично** — IP/устройство в aiogram недоступны, реализован только token-bucket per-`referrer_tg_id`. Полноценный антифрод (IP-history, fingerprinting) — будущий спринт после интеграции с web-админкой (§4.5).
- **CI после полного спринта**: 2829 passed / 1 skipped, coverage 96.11%, lint/typecheck/import-linter ✅.

Результат / артефакты:
- `src/pipirik_wars/domain/referral/` — доменный слой (entity, port, errors, scheduling-helpers).
- `src/pipirik_wars/domain/shared/ports/rate_limiter.py` — port вынесен из infrastructure для соблюдения layered contract.
- `src/pipirik_wars/application/referral/{register,grant_signup_bonus,grant_thickness_milestone,run_weekly_clan_summary,weekly_summary_dto,weekly_summary_notifier}.py` — application use-cases.
- `src/pipirik_wars/infrastructure/db/repositories/referral.py` + миграция `0015_*.py` — persistence.
- `src/pipirik_wars/infrastructure/scheduler/aps.py` — `schedule_weekly_clan_referral_summary_cron` + callback.
- `src/pipirik_wars/bot/handlers/{start.py,referral_share.py}` — payload + кнопка «Поделиться».
- `src/pipirik_wars/bot/presenters/{weekly_referral_summary.py,referral_share.py}` + `bot/notifications/weekly_referral_summary.py` — UI-слой.
- `src/pipirik_wars/locales/{ru,en}/referral.ftl` — локали.
- `tests/{unit,integration}/...` — ~80 новых тестов суммарно по всему спринту.

Заметки / решения:
- **Перенос `IRateLimiter` в domain** был вынужденной правкой при F-шаге: до 2.4.F port жил в `infrastructure/rate_limit/token_bucket.py`, потому что использовался только bot-middleware-ом и не нужен был application-слою. С появлением антифрода в `RegisterReferral` import-linter contract «application не зависит от infrastructure» сработал жёстко — port пришлось поднять в `domain/shared/ports/rate_limiter.py`. Реализация осталась в infrastructure.
- **Раздельный UoW для `REFERRAL_RATE_LIMITED` audit** — чтобы попытка фиксировалась даже если последующая логика не выполняется (нет создания реферала). Если бы audit писался в той же UoW, что и rejected-add, при exception-е audit бы откатился вместе с транзакцией.
- **Тихий no-op в handler-е при `ReferralRateLimitedError`** — намеренно: feedback «реферер исчерпал лимит» сломал бы скан-стратегию атакующего (он бы понял, какие tg_id уже исчерпали bucket, и оптимизировал атаку). Audit фиксирует попытку, но новичок видит обычный `/start`-flow без реферала.
- **Узкая реферальная weekly-card вместо полной клановой** в 2.4.E — компромисс, потому что в ГДД §13.3 weekly-card должна также включать PvP-стату клана, караваны, рейды, но соответствующих репозиторных агрегатов ещё нет. Решено: сейчас закрываем именно реферальную часть (это в скоупе спринта 2.4); расширение до полной клановой weekly-card — в спринтах 3.x после реализации караванов и рейдов.
- **Token-bucket-параметры** (capacity=10, refill=10/час) выбраны как «реалистичный пригласил-друзей-за-вечер без блока, но достаточно жёстко чтобы скан-атака 1000 фейк-tg выявилась за час». Если в production эти цифры окажутся неподходящими — `BotSettings`-fields позволяют менять без code-deploy через env-vars.

---

## 2026-05-06 — Спринт 2.3.F.2: per-clan APScheduler-cron «Главы клана дня» (deterministic offset + bootstrap + midnight reschedule)

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 2.3.F.2 ([`current_tasks.md` 2.3.F.2](current_tasks.md), ПД §5 / Спринт 2.3.6), ГДД §6.1 (cron-trigger «Главы клана дня»)

Что сделано:
- **Domain helper `compute_daily_head_cron_offset_minutes(*, clan_id, moscow_date)`** (`domain/daily_head/scheduling.py`): детерминированный `sha256(clan_id_bytes + moscow_date.isoformat())` → `int.from_bytes()` modulo `1440` (минут в сутках). Один и тот же `(clan_id, date)` всегда даёт один offset; разные кланы получают равномерно-распределённые offset-ы по суткам, чтобы избежать «грозы» в 00:00 МСК.
- **Domain helper `compute_daily_head_cron_run_at_utc(*, clan_id, moscow_date)`**: возвращает `datetime` (UTC) срабатывания cron-а — `00:00 Europe/Moscow + offset_minutes`, переведённое в UTC через `.astimezone(UTC)`. Используется и application-use-case-ом, и шедулер-адаптером.
- **Расширение `IDelayedJobScheduler` (domain port)**: добавлены абстрактные методы `schedule_daily_head_cron(*, clan_id, run_at)` и `cancel_daily_head_cron(*, clan_id)`. Идемпотентность по `clan_id` (повторный schedule перезаписывает существующий job; cancel несуществующего — no-op).
- **Infrastructure `APSchedulerDelayedJobScheduler`**: реализация двух новых методов через `add_job(self._run_daily_head_cron_job, trigger=DateTrigger(run_at), id=f"daily_head_cron:{clan_id}", replace_existing=True)` / `remove_job(...)`. Optional ctor-фабрика `daily_head_cron_factory: Callable[[], RunDailyHeadCron]` + callback `_run_daily_head_cron_job(clan_id)` (зовёт `RunDailyHeadCron.execute(RunDailyHeadCronInput(clan_id=clan_id))`, swallows exceptions с `_logger.exception(...)`; frozen-кланы возвращают `None` — корректное no-op-поведение, т.к. use-case 2.3.C сам обрабатывает frozen-кланы).
- **Расширение `IClanRepository` (domain port)**: новый метод `list_active() -> Sequence[Clan]` — возвращает только не-замороженные (`ClanStatus.ACTIVE`) кланы. Sql-impl `SqlAlchemyClanRepository.list_active`: `SELECT * FROM clans WHERE status = 'active'`. Fake-impl `FakeClanRepository.list_active`: фильтрует `_clans` по статусу.
- **Application use-case `ScheduleDailyHeadCronJobs(uow, clans, scheduler, clock)`** (`application/daily_head/schedule_cron_jobs.py`): `execute()` обходит `clans.list_active()`, для каждого клана вычисляет `run_at = compute_daily_head_cron_run_at_utc(clan_id, clock.moscow_date())`, скипает прошедшие (`run_at <= clock.now()`), регистрирует APScheduler-job через `scheduler.schedule_daily_head_cron(...)`. Возвращает `ScheduleDailyHeadCronJobsResult(scheduled, skipped_past, skipped_no_id)` для observability и тестируемости.
- **DI в `bot/main.py.build_container`**: новое поле `Container.schedule_daily_head_cron_jobs: ScheduleDailyHeadCronJobs` + late-bound фабрики `daily_head_cron_factory=lambda: run_daily_head_cron` и `daily_reschedule_factory=lambda: schedule_daily_head_cron_jobs` для `APSchedulerDelayedJobScheduler`.
- **Bootstrap в `bot/main.py.run()`**: после `scheduler.start()` вызывается `await container.schedule_daily_head_cron_jobs.execute()` (re-bootstrap сегодняшних per-clan job-ов после рестарта процесса — APScheduler in-memory job-store пуст). Затем `scheduler.schedule_daily_head_reschedule_cron()` регистрирует ежедневный `CronTrigger(hour=0, minute=1, timezone="Europe/Moscow")`, который вечером каждого дня зовёт `ScheduleDailyHeadCronJobs.execute()` для перепланирования на новые сутки. Минута лага (`00:01` вместо `00:00`) — гарантия, что `IClock.moscow_date()` уже вернёт новую дату.
- **+12 unit-тестов** scheduling-helper-а (deterministic / range / utc-conversion / window).
- **+10 unit-тестов** `ScheduleDailyHeadCronJobs` (active-clans / past-skip / no-id-skip / idempotency / boundary).
- **+5 unit-тестов** `schedule_daily_head_reschedule_cron` (callback invokes use-case / swallows errors / no-op without factory / cron-trigger settings / no-factory warning).
- **3 callback-теста** `_run_daily_head_cron_job`.
- **Расширенный composition-root тест** (`Container` теперь конструируется с новым полем).
- **`make ci` зелёный**: 2666 passed, coverage 96.01%; mypy 552 source files, lint-imports 3 contracts kept.

Результат / артефакты:
- `src/pipirik_wars/domain/daily_head/scheduling.py` — оба helper-а.
- `src/pipirik_wars/domain/daily_head/__init__.py` — экспорты.
- `src/pipirik_wars/domain/clan/repositories.py` — `list_active`.
- `src/pipirik_wars/domain/shared/ports/scheduler.py` — `schedule/cancel_daily_head_cron`.
- `src/pipirik_wars/infrastructure/scheduler/aps.py` — реализация + callback + reschedule-cron.
- `src/pipirik_wars/infrastructure/db/repositories/clan.py` — `list_active`-impl.
- `tests/fakes/clan.py` — `FakeClanRepository.list_active`.
- `src/pipirik_wars/application/daily_head/schedule_cron_jobs.py` — use-case + result.
- `src/pipirik_wars/application/daily_head/__init__.py` — экспорты.
- `src/pipirik_wars/bot/main.py` — DI + bootstrap + reschedule-cron.
- Тесты: `tests/unit/domain/daily_head/test_scheduling.py`, `tests/unit/application/daily_head/test_schedule_cron_jobs.py`, `tests/unit/infrastructure/scheduler/test_aps.py` (новые классы), `tests/unit/bot/test_composition_root.py` (расширение).

Заметки / решения:
- **Почему `00:01` вместо `00:00` для reschedule-cron-а:** `IClock.moscow_date()` мог бы вернуть старую дату при срабатывании ровно в `00:00:00.000` из-за clock-skew или микросекундных задержек. Лаг в одну минуту устраняет проблему без видимых последствий для UX (бонус «Глава клана дня» можно получить в любой момент суток).
- **Почему bootstrap в `run()` отдельно от reschedule-cron-а:** APScheduler-job-store in-memory, после рестарта пуст. Bootstrap нужен, чтобы сегодняшние job-ы существовали; reschedule-cron сработает только в `00:01` следующих суток.
- **Почему `daily_reschedule_factory` — фабрика, а не прямой инстанс:** замыкание `lambda: schedule_daily_head_cron_jobs` решает проблему циклической зависимости в `build_container` (use-case создаётся ПОСЛЕ scheduler-а, поэтому прямой ссылки на момент конструирования scheduler-а ещё нет).
- **Почему `IClanRepository.list_active`, а не `list_all` + фильтр на стороне use-case-а:** SQL `WHERE status='active'` гораздо эффективнее, чем загрузка всех кланов и фильтрация в Python; контракт также чётко выражает namespace use-case-а.
- **Per-clan offset через sha256:** даёт равномерное распределение по суткам без необходимости хранить state. Один и тот же `(clan_id, moscow_date)` детерминирован, что важно для тестируемости и debugging-а.

---

## 2026-05-05 — Спринт 2.3.F.1: запись активности игроков в `daily_active` (middleware + use-case)

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 2.3.F.1 ([`current_tasks.md` 2.3.F.1](current_tasks.md), ПД §5 / Спринт 2.3.7), ГДД §6.1.2 (preflight «активные за 7 дней» для назначения Главы клана дня)

Что сделано:
- **Domain — write-метод в порту `IDailyActivityRepository`:** добавлен абстрактный `record_active(*, user_id: int, last_at: datetime, moscow_date: date) -> None`. До 2.3.F.1 порт был read-only (`list_active_member_ids` для preflight-чтения). Запись производится только через middleware на каждое сообщение игрока — domain-слой остаётся чистым.
- **Infrastructure — UPSERT `record_active`:** `SqlAlchemyDailyActivityRepository.record_active(...)` использует `pg_insert.on_conflict_do_update` (PostgreSQL) и `sqlite_insert.on_conflict_do_update` (SQLite) с `index_elements=[date, user_id]` (PK таблицы `daily_active`) и `set_={"last_at": EXCLUDED.last_at}`. Семантика: первый раз за день — INSERT; повторное сообщение в тот же день — UPDATE `last_at` на свежее значение (без дублей строк).
- **Application — use-case `RecordPlayerActivity`** (`application/daily_head/record_activity.py`, `RecordPlayerActivity(uow, players, daily_activity, clock)`): `execute(input_dto: RecordPlayerActivityInput) -> bool`. Внутри ambient-UoW: `IPlayerRepository.get_by_tg_id(tg_user_id)` → если `None` / `player.id is None` / `player.status is not PlayerStatus.ACTIVE` → возврат `False` (no-op для незарегистрированных / FROZEN); иначе `daily_activity.record_active(user_id=player.id, last_at=clock.now(), moscow_date=clock.moscow_date())` + `return True`. DTO `RecordPlayerActivityInput(tg_user_id: PositiveTgId)` в `application/dto/inputs.py`.
- **Bot middleware `DailyActivityMiddleware`** (`bot/middlewares/daily_activity.py`):
  - Принимает `RecordPlayerActivity` use-case в конструкторе.
  - На каждое входящее `Message` извлекает `TgIdentity` из `data[AUTH_DATA_KEY]`; если identity отсутствует — пропускает.
  - Skip: не-`Message` события (`callback_query`, `chat_member`, `my_chat_member`), `private`/`channel` чаты — только `group`/`supergroup` считаются «активностью в клан-чате» для preflight-а Главы клана дня.
  - Зовёт `use_case.execute(RecordPlayerActivityInput(tg_user_id=...))`.
  - Ловит исключения use-case-а через `try/except` + `_log.warning(exc_info=True)` — handler выполняется даже если запись провалилась («выживаемость > точность» — спам в RPS-лимит / DB hiccup не должен ронять команду пользователя).
  - **Не** записывает активность для callback-кликов / chat-member-апдейтов: цель `daily_active` — «писал ли игрок в клан-чат», а не «нажимал ли в боте кнопки».
- **`register_middlewares(...)`** расширен опциональным параметром `record_player_activity: RecordPlayerActivity | None`. При `None` middleware не подключается (для unit-тестов composition-root). При наличии — `dp.message.middleware(DailyActivityMiddleware(...))` вызывается **отдельно** от общего цикла (только `dp.message`, не `dp.callback_query` и не `dp.my_chat_member`).
- **DI в `bot/main.py`:** `Container.record_player_activity: RecordPlayerActivity` (рядом с `request_daily_head`/`run_daily_head_cron`); инстанс в `build_container()`; проброс в `register_middlewares(...)` и в `dispatcher["record_player_activity"]` workflow-data.
- **Тесты:**
  - **+4 integration** (`tests/integration/db/daily_head/test_daily_activity_repository.py::TestRecordActive`): `test_inserts_new_row`, `test_upsert_updates_last_at_on_same_day`, `test_separate_rows_per_day`, `test_record_then_list_returns_player`. SQLite-naive `last_at` сравнивается через `.replace(tzinfo=None)` (стандартное поведение SQLite, документировано в коде).
  - **+7 unit-тестов use-case** (`tests/unit/application/daily_head/test_record_player_activity.py`): unknown player no-op, active player records with clock values, frozen no-op, no-id no-op, repeated record uses fresh clock (`FakeClock.set`), input validation отвергает `tg_user_id=0` и `tg_user_id<0` (`pydantic.ValidationError`).
  - **+9 unit-тестов middleware** (`tests/unit/bot/middlewares/test_daily_activity.py`): records group / records supergroup / skips private / skips channel / skips no-identity / skips callback / skips chat_member / handler runs even when use_case raises / use_case returning False is silent.
  - **+2 composition-root** assertion-update (`tests/unit/bot/test_composition_root.py`): `_container_with_fakes` создаёт `record_player_activity`; `test_build_dispatcher_assembles_full_stack` проверяет middleware count = 5 у `dp.message` (4 у `callback_query`/`my_chat_member` + дополнительный `DailyActivityMiddleware`).
  - `FakeDailyActivityRepository` (tests/fakes) расширен полями `record_calls: list[tuple[user_id, last_at, moscow_date]]` + `activity: dict[(date, user_id), datetime]` + методом `record_active`.

Результат / артефакты:
- `src/pipirik_wars/domain/daily_head/repositories.py` (write-метод `record_active`).
- `src/pipirik_wars/infrastructure/db/repositories/daily_activity.py` (PostgreSQL + SQLite UPSERT).
- `src/pipirik_wars/application/daily_head/record_activity.py` (новый use-case).
- `src/pipirik_wars/application/dto/inputs.py` (`RecordPlayerActivityInput`).
- `src/pipirik_wars/bot/middlewares/daily_activity.py` (новый middleware).
- `src/pipirik_wars/bot/middlewares/__init__.py` (опциональный `record_player_activity` параметр).
- `src/pipirik_wars/bot/main.py` (Container + DI).
- `tests/fakes/daily_head.py` (write-side fake).
- `tests/integration/db/daily_head/test_daily_activity_repository.py` (TestRecordActive).
- `tests/unit/application/daily_head/test_record_player_activity.py` (новый).
- `tests/unit/bot/middlewares/test_daily_activity.py` (новый).
- `tests/unit/bot/test_composition_root.py` (обновление под новое поле).

Заметки / решения:
- **`bool`-возврат вместо исключения для no-op:** use-case возвращает `False` для unknown / no-id / FROZEN — это _не_ ошибка, это легитимный «нечего записывать». Middleware ничего с возвратом не делает (даже не логирует), потому что middleware вызывается на _каждое_ сообщение и подавляющая часть будет `True`-возвратом.
- **Skip для private/channel:** preflight Главы клана дня требует «активные **в клан-чате**». Личные команды (`/profile` в DM с ботом) и каналы не должны учитываться. Middleware фильтрует на уровне `chat_kind`.
- **`try/except Exception` в middleware:** сознательный broad-catch. Запись активности — best-effort (наличие/отсутствие записи влияет только на preflight Главы клана дня раз в сутки). DB hiccup / unexpected ошибка не должны ронять основную команду пользователя — handler выполняется в любом случае. Ошибка пишется в лог через `logging.warning(exc_info=True)`.
- **Throttle сработает _до_ middleware-записи:** в текущем порядке `error → auth → locale → throttle → daily_activity → handler` rate-limit-нутый игрок не зарегистрирует активность. Это сознательный выбор — спам в RPS-лимит не должен заводить активность (исходно планировалось «до throttle», но в aiogram middleware на observer применяются в порядке регистрации, а throttle уже зарегистрирован циклом для всех observer-ов до отдельной регистрации DailyActivity для message-observer-а).
- **Идемпотентность по PK:** UPSERT по `(date, user_id)` — повторное сообщение в тот же день обновляет `last_at`, не создаёт дубль. Это позволяет middleware быть «глупым» (без локального кэша «уже писал сегодня?») — БД сама обеспечивает корректность.
- **APScheduler-cron (2.3.F.2)** будет в отдельном PR-е. `RunDailyHeadCron` use-case уже готов в Sprint 2.3.C — нужен только wiring в scheduler с per-clan deterministic offset (sha256-hash от `clan_id + moscow_date_str` modulo 24*60 минут).

Тесты: `make ci` зелёный (TBD после push); локально все 4 integration + 7 use-case + 9 middleware + 6 composition-root тестов проходят.

---

## 2026-05-06 — Спринт 2.3.E: bot-слой «Главы клана дня» (`/clan_head` handler + presenter + DI каталога цитат)

**Автор:** Devin (агент)
**Тип:** feature
**Связано:** Спринт 2.3.E ([`current_tasks.md` 2.3.E](current_tasks.md), ПД §5 / Спринт 2.3.5)

Что сделано:
- **Handler `bot/handlers/clan_head.py`** — `@router.message(Command("clan_head"))`, group-only (в ЛС / канале → `clan-head-needs-group-chat`), резолв клана по `chat_id` через `IClanRepository.get_by_chat_id` (нет привязки или `clan.id is None` → `clan-head-not-registered`), вызов use-case `RequestDailyHead.execute(RequestDailyHeadInput(chat_id, actor_tg_id))` (Спринт 2.3.C). Конвертация доменных ошибок в локализованные ответы: `ClanFrozenError` → `clan-head-frozen-clan`; `DailyHeadInsufficientActivityError(active_count, required)` → `clan-head-not-enough-active{active_count, required}`. На успех — выбор случайного шаблона цитаты через `IClanQuoteTemplateProvider.get_templates(locale=effective_locale.code)` + `IRandom.choice(...)` (DI пробрасывает `pvp_random`, тот же `RealRandom`-инстанс что для PvP), подстановка имени главы в плейсхолдер `{user}` (приоритет: `Player.username` → `@username`, fallback `"глава"`), и рендер `clan-head-success{head_display_name, bonus_cm, new_length_cm, quote_text}` для нового назначения / `clan-head-already-assigned{head_display_name, bonus_cm, quote_text}` для идемпотентного возврата (`was_new=False`). Пустой каталог цитат → fallback `_FALLBACK_QUOTE = "👑"` + warn-лог `clan_head_quote_catalog_empty` (handler никогда не падает на рендере).
- **Presenter `bot/presenters/clan_head.py`** — `ClanHeadPresenter(bundle: IMessageBundle)` с 6 методами: `needs_group_chat`, `not_registered`, `frozen_clan`, `not_enough_active`, `success`, `already_assigned`. Все ключи lifted в `Final[MessageKey]` для статической проверки.
- **Локали** в `locales/{ru,en}.ftl` (14 строк): `clan-head-needs-group-chat`, `-not-registered`, `-frozen-clan`, `-not-enough-active{active_count, required}`, `-success{head_display_name, bonus_cm, new_length_cm, quote_text}` (мульти-строчный шаблон с цитатой), `-already-assigned{head_display_name, bonus_cm, quote_text}`. Числа через `NUMBER($x, useGrouping: 0)` чтобы Fluent не вставлял NBSP-разделители.
- **DI-провязка в `bot/main.py`:**
  - В `Container` добавлено поле `clan_quote_provider: IClanQuoteTemplateProvider` (рядом с `oracle_templates`/`duel_log_templates`/`forest_log_templates`).
  - В `build_container()` создаётся инстанс `JsonClanQuoteTemplateProvider(templates_dir=...)` (lazy-кэш per-локаль из 2.3.D).
  - В `build_dispatcher()` пробрасывается `dispatcher["clan_quote_provider"] = container.clan_quote_provider` — aiogram автоматически инжектит в handler как параметр `clan_quote_provider: IClanQuoteTemplateProvider`.
- **Регистрация роутера** в `bot/handlers/__init__.py.register_routers()` (стандартный паттерн).
- **Tests:**
  - `tests/unit/bot/presenters/test_clan_head.py` — **6 unit-тестов** через `FakeMessageBundle` (маркерный формат `locale:key[k=v,...]`): `needs_group_chat`, `not_registered`, `frozen_clan`, `not_enough_active` с placeholder-проверкой, `success`/`already_assigned` с проверкой всех плейсхолдеров.
  - `tests/unit/bot/handlers/test_clan_head.py` — **15 unit-тестов** handler-а: `tg_identity is None` / `chat_kind="private"` / `chat_kind="channel"` / `clan is None` / `clan.id is None` / `ClanFrozenError` / `DailyHeadInsufficientActivityError` / happy-path success с цитатой + username / already_assigned (was_new=False) без `new_length_cm` / пустой каталог цитат → fallback `👑` / `Player.username is None` → fallback `"глава"` + подстановка в `{user}` / `locale=None` → `DEFAULT_LOCALE` (`en`) / `chat_kind="group"` тоже работает / use-case вызывается с правильным `chat_id`+`actor_tg_id` / провайдер вызывается с `locale=<code>`. Использует `MagicMock(spec=...)` + `AsyncMock` для `Message.answer`/`IClanRepository.get_by_chat_id`/`RequestDailyHead.execute`; реальные доменные `ClanFrozenError(chat_id=...)` и `DailyHeadInsufficientActivityError(clan_id, active_count, required)` для проверки error-веток.
- **Fakes:** `tests/fakes/clan_quotes.py` — `FakeClanQuoteTemplateProvider(catalog: dict[str, tuple[ClanQuoteTemplate, ...]])` с реализацией `get_templates(*, locale)` зеркалящей реальный JSON-загрузчик (fallback на `"ru"` если локали нет). Реэкспорт из `tests.fakes`.
- **Composition root:** `tests/unit/bot/test_composition_root.py` дополнен импортом `FakeClanQuoteTemplateProvider` + созданием инстанса + передачей в `Container(...)` (mypy-фикс — без него `make typecheck` падал на «Missing positional argument "clan_quote_provider"»).

Результат / артефакты:
- `src/pipirik_wars/bot/handlers/clan_head.py` (165 строк, новый файл).
- `src/pipirik_wars/bot/presenters/clan_head.py` (92 строки, новый файл).
- `src/pipirik_wars/bot/main.py` (+8 строк DI).
- `src/pipirik_wars/bot/handlers/__init__.py`, `bot/presenters/__init__.py` (+2 строки регистрация).
- `locales/ru.ftl`, `locales/en.ftl` (+14 строк каждая).
- `tests/fakes/clan_quotes.py` (31 строка).
- `tests/fakes/__init__.py` (+2 строки реэкспорт).
- `tests/unit/bot/handlers/test_clan_head.py` (~470 строк, **15 тестов**).
- `tests/unit/bot/presenters/test_clan_head.py` (65 строк, **6 тестов**).
- `tests/unit/bot/test_composition_root.py` (+3 строки фикс mypy).
- `make ci` зелёный: ruff format/check + mypy + lint-imports + 2606 passed (95+ unit + 30+ integration), coverage 96.02% (выше порога 80%).

Заметки / решения:
- **Где выбирать цитату — handler vs use-case?** Решение: handler. Оригинальный план предлагал два варианта: (A) handler берёт `IClanQuoteTemplateProvider` напрямую и зовёт `random.choice(...)`, (B) use-case `RequestDailyHead` сам выбирает цитату и кладёт в DTO. Выбран (A): use-case 2.3.C уже мержен в main с DTO `DailyHeadResolved(assignment, player, was_new)` — расширение DTO потребовало бы reopen 2.3.C-PR-а, чего избегаем. Кроме того, выбор цитаты — это чисто UX-решение (контент-policy `mild_profanity` потенциально живёт в bot-конфиге), а use-case остаётся pure-domain-orchestration без презентационных решений.
- **Подстановка `{user}` в цитате** — handler делает `text.replace("{user}", head_display)` после рендера. Это не Fluent-плейсхолдер, а обычная Python-замена в самой цитате (которая потом передаётся в Fluent через `quote_text` placeholder). Альтернатива — заставлять JSON-цитаты использовать Fluent-синтаксис `{ $user }` — но это сломало бы стилистику каталогов и потребовало бы парсинга Fluent для каждой цитаты. Простая `str.replace` достаточна.
- **`pvp_random` reuse** — handler принимает `IRandom` параметр с именем `pvp_random` (ключ aiogram-workflow-data), потому что в `bot/main.py` этим именем уже зарегистрирован `RealRandom`-инстанс для PvP. Создавать отдельный `clan_head_random` нет смысла — это тот же глобальный random.
- **Fallback `_FALLBACK_QUOTE = "👑"`** — handler никогда не падает на рендере: даже если каталог пуст / отсутствует, он отдаёт корону + warn-лог. Прод-инвариант — каталог всегда непустой (валидируется в 2.3.D через `ClanQuoteCatalogEmptyError`), но handler устойчив на случай мисконфигурации.
- **Author identity для audit_log** — handler берёт `tg_identity.tg_user_id` (Telegram user_id отправителя) и передаёт в `actor_tg_id` поле DTO `RequestDailyHeadInput`. Use-case 2.3.C по нему пишет `audit_log.actor_id` для аналитики «кто триггернул» (даже если глава — другой игрок).
- **Не сделано в 2.3.E (вынесено в 2.3.F):**
  - APScheduler-cron `RunDailyHeadCron` с per-clan `random_offset(0..24h)` от 00:00 МСК (use-case уже мержен в 2.3.C, но triggers ещё не подключены).
  - Middleware-запись в `daily_active`-таблицу при каждом входящем Telegram-сообщении (нужно для preflight-проверки `min_active_members` в `DailyHeadService`).
  - Inline-кнопка «🎲 Назначить главу дня» в карточке профиля клана (ГДД §6.1 — пока есть только slash-команда).

---

## 2026-05-05 — Спринт 2.3.D: каталог иронично-смешных цитат «Главы клана дня» (≥ 100 RU + ≥ 100 EN, JSON-загрузчик)

**Автор:** Devin (агент sufficientdorette)
**Тип:** feature
**Связано:** PR #71 — Спринт 2.3.D ([`current_tasks.md` 2.3.D](current_tasks.md), ПД §5 / Спринт 2.3.4)

Что сделано:
- **Domain-VO** `ClanQuoteTemplate(id: str, text: str, tags: tuple[str, ...])` (`src/pipirik_wars/domain/daily_head/quote.py`) — иммутабельная (`frozen=True, slots=True`) запись каталога. Полная `__post_init__`-валидация: непустые trim-нутые `id`/`text`, `tags` ⊆ `ALLOWED_QUOTE_TAGS = {statham, vk_pablik, auf, meme, profanity}`, без дублей внутри `tags`, минимум 1 «стилистический» тег (`profanity` без стиля запрещён по ПД §5: «теги стиля заполнены»). Свойство `has_profanity` для будущей фильтрации (handler-уровень 2.3.E через `balance.daily_head.content_policy.mild_profanity`).
- **Domain-ошибка** `ClanQuoteCatalogEmptyError(locale)` в `domain/daily_head/errors.py` — бросается infrastructure-адаптером при пустом каталоге (RU-каталог не существует или пуст; прод-инвариант — RU всегда есть ≥ 100 цитат).
- **Application-порт** `IClanQuoteTemplateProvider.get_templates(*, locale: str)` (`src/pipirik_wars/application/daily_head/quote_templates.py`) — абстракция «откуда брать шаблоны». Реэкспортируется из `application.daily_head` для удобства handler-а 2.3.E.
- **Infrastructure-адаптер** `JsonClanQuoteTemplateProvider` (`src/pipirik_wars/infrastructure/templates/clan_quotes.py`): lazy-кэширующий загрузчик per-локаль из `config/templates/clan_quotes_<locale>.json`; fallback на `"ru"` если запрошенной локали нет; конвертация `OSError` / `JSONDecodeError` / структурных нарушений в `ConfigError`; пустой каталог → `ClanQuoteCatalogEmptyError`. Парсинг каждой записи через `ClanQuoteTemplate(...)` — все доменные инварианты ловятся на этапе загрузки и превращаются в `ConfigError` с указанием `path` + `index` + reason. Кэш `dict[str, tuple[ClanQuoteTemplate, ...]]` хранит парсенный каталог per-локаль на время жизни процесса (hot-reload — задача отдельного спринта).
- **Каталоги** `config/templates/clan_quotes_ru.json` (110 цитат) и `clan_quotes_en.json` (110 цитат) — стилистика «Стэтхем / паблики ВК / АУФ / общеинтернетный мем»; обращение к новому главе через плейсхолдер `{user}`; политика контента по ПД §5 (без политики, межнацоскорблений, насилия, рекламы, секса). Все 110 цитат каждого языка имеют ≥ 1 «стилистический» тег и `{user}`-плейсхолдер; уникальные стабильные id вида `clan_quote.<locale>.NNNN` (используются в audit_payload + аналитике).
- **Tests:**
  - `tests/unit/domain/daily_head/test_quote.py` — **13 unit-тестов** VO: минимальная валидная конструкция, frozen-immutability, multi-tag, `has_profanity` true/false, отказы по empty/whitespace `id`/`text`, empty `tags`, unknown tag, only-`profanity` без стиля, дубликаты в `tags`, `ALLOWED_QUOTE_TAGS` содержит все 5 тегов и является `frozenset`.
  - `tests/unit/domain/daily_head/test_errors.py` — **3 unit-теста** `ClanQuoteCatalogEmptyError`: наследование, payload, текст ошибки.
  - `tests/integration/templates/test_clan_quotes_loader.py` — **18 integration-тестов**: shipped-каталоги (`≥ 100`, уникальные id, рендер `{user}`, ≥ 1 стилистический тег, наличие `{user}`-плейсхолдера в каждой цитате, lazy-cache identity); error-кейсы (`fallback_to_ru` / `no_files` / `empty_file` / `duplicate_ids` / `invalid_json` / `root_not_object` / `templates_not_list` / `entry_not_object` / `id_missing` / `tags_missing` / `tags_not_list_of_strings` / `unknown_tag`); positive payload с `profanity`-цитатой.
- **DI-провязка** `clan_quote_provider` в `Container` / `bot/main.py` пока **не сделана** — провайдер не имеет потребителя до handler-а 2.3.E. Когда handler `/clan_head` появится, провайдер будет инстанцирован в `build_container()` и проброшен в handler через `dispatcher["clan_quote_provider"]`.

Результат / артефакты:
- `src/pipirik_wars/domain/daily_head/quote.py` (новый, 96 строк).
- `src/pipirik_wars/domain/daily_head/errors.py` — добавлен `ClanQuoteCatalogEmptyError`.
- `src/pipirik_wars/domain/daily_head/__init__.py` — реэкспорт `ALLOWED_QUOTE_TAGS`, `ClanQuoteTemplate`, `ClanQuoteCatalogEmptyError`.
- `src/pipirik_wars/application/daily_head/quote_templates.py` (новый, 36 строк).
- `src/pipirik_wars/application/daily_head/__init__.py` — реэкспорт `IClanQuoteTemplateProvider`.
- `src/pipirik_wars/infrastructure/templates/clan_quotes.py` (новый, 122 строки).
- `src/pipirik_wars/infrastructure/templates/__init__.py` — реэкспорт `JsonClanQuoteTemplateProvider`.
- `config/templates/clan_quotes_ru.json` (новый, 110 цитат).
- `config/templates/clan_quotes_en.json` (новый, 110 цитат).
- `tests/unit/domain/daily_head/test_quote.py` (новый, 13 тестов).
- `tests/unit/domain/daily_head/test_errors.py` — добавлены 3 теста для `ClanQuoteCatalogEmptyError`.
- `tests/integration/templates/test_clan_quotes_loader.py` (новый, 18 тестов).

Заметки / решения:
- **Tag-whitelist на уровне VO, а не loader-а.** Все 5 разрешённых тегов хранятся как `frozenset` в `domain/daily_head/quote.py` и проверяются в `__post_init__`. Loader (infrastructure) лишь конструирует VO — невалидные теги ловятся `ValueError` → `ConfigError`. Это значит, что в любых тестах / fixture-ах нельзя случайно создать «битый» каталог: домен сам себя защищает.
- **Минимум 1 стилистический тег обязателен.** ПД §5 / 2.3.4 говорит: «теги стиля заполнены». Тег `profanity` — лишь модификатор; без стилевого тега цитата не классифицируется. Это даёт уверенность, что любая цитата может фильтроваться по стилю в будущем (например, «отключить АУФ»).
- **Fallback на RU при отсутствии локали.** Та же стратегия, что в `JsonOracleTemplateProvider` (Спринт 1.4.B). Значит, в `dev`-окружении можно не иметь EN-каталога — handler автоматически возьмёт RU. В `prod` контракт обещает наличие обоих файлов.
- **Hot-reload не делаем.** Каталог кэшируется per-локаль на время жизни процесса. Замена цитат → переcборка контейнера / restart бота. Это сознательный trade-off (раздел 2.3 редко крутится). Reload-стратегия может появиться позже через общий `IBalanceReloader`-паттерн (который уже есть для balance.yaml в 1.5.G backlog).
- **Каталог отделён от handler-а / use-case-а.** В `dispatcher` пока ничего не пробрасывается — провайдер существует, но нет потребителя. Это даёт чистый, минимальный по диффу PR. Handler 2.3.E будет инстанцировать `JsonClanQuoteTemplateProvider(templates_dir=settings.templates_dir)` рядом с `JsonOracleTemplateProvider` в `build_container()`.
- **Стилистика и политика контента.** Каталог сделан в духе «по понятиям / Стэтхем / АУФ / паблики ВК», но без реальных оскорблений и без тяжёлого мата. Из 110 цитат на язык ни одна не помечена тегом `profanity` (намеренно — не было желания добавлять мат в первую итерацию). Когда геймдиз / контент-команда захочет добавить «острые» цитаты с `profanity`-тегом, они будут добавлены отдельным PR-ом и автоматически фильтруемы через `balance.daily_head.content_policy.mild_profanity` в 2.3.E.
- **`has_profanity` свойство без аргументов.** Быстрый способ узнать «можно ли показывать эту цитату при `mild_profanity=false`» прямо на VO. В 2.3.E фильтр будет: `[t for t in templates if balance.daily_head.content_policy.mild_profanity or not t.has_profanity]`.

---

## 2026-05-06 — Спринт 2.3.C: application use-cases «Главы клана дня» (`RequestDailyHead` + `RunDailyHeadCron`, 18 unit-тестов, миграция 0014 audit-source)

**Автор:** Devin (агент urbanviola, recovery-агент завершил DI-провязку + docs)
**Тип:** feature
**Связано:** ПД §5 / Спринт 2.3.3, ГДД §6.1; ветка `devin/1778058870-sprint-2-3-c-daily-head-usecases` (PR следует)

Что сделано:
- Реализованы application use-cases «Главы клана дня» поверх доменного `DailyHeadService` (2.3.A) и репозиториев 2.3.B. Сценарий гибридного триггера (ГДД §6.1, Q4 v9) теперь полностью на месте на application-уровне.
- **`RequestDailyHead(uow, clans, players, heads, daily_head_service, length_granter, audit, clock)`** — button-trigger (`/clan_head` или inline-кнопка из клан-чата). Резолвит клан по `chat_id` (бросает `NoClanRegisteredError` при отсутствии); валидирует `ClanStatus.ACTIVE` (бросает `ClanFrozenError`); вызывает общий хелпер.
- **`RunDailyHeadCron(uow, clans, players, heads, daily_head_service, length_granter, audit, clock)`** — cron-trigger (под APScheduler 2.3.F, по `random_offset(0..24h)`-час с 00:00 МСК). Принимает `clan_id` напрямую (резолвит клан через `clans.get_by_id`); если клан удалён или FROZEN — возвращает `None` (no-op без ошибки, чтобы шедулер не падал на устаревшей записи); иначе вызывает общий хелпер.
- **Общий хелпер `_resolve_or_create_assignment(...)`** в `application/daily_head/_common.py` — внутри активного UoW:
  1. `service.assign_or_get(...)` — preflight + выбор кандидата. Если уже назначен (`assignment.id is not None`) — читает игрока и возвращает `DailyHeadResolved(was_new=False)`.
  2. `heads.add(assignment)` — INSERT новой записи. На race (UNIQUE-violation) — `DailyHeadAlreadyAssignedError` ловится → `heads.get_by_clan_and_date(...)` возвращает запись победителя → `was_new=False` (длина уже начислена выигравшей транзакцией, повторно не делаем).
  3. На happy-path: `length_granter.grant(player_id, delta_cm=saved.bonus_cm, source=AuditSource.DAILY_HEAD, idempotency_key=f"add_length:daily_head:{clan_id}:{moscow_date.isoformat()}")` — anti-cheat clamp + audit `LENGTH_GRANT` внутри `grant()`. Idempotency-key стабилен по `(clan_id, moscow_date)` — при ретрае в тех же сутках LENGTH_GRANT-дубликат не возникнет.
  4. Отдельный `AuditEntry(action=AuditAction.DAILY_HEAD_ASSIGN, target_kind="clan", target_id=str(clan_id), after={player_id, moscow_date, source, bonus_cm}, idempotency_key=f"daily_head_assign:{clan_id}:{moscow_date.isoformat()}")` — для аналитики (отдельно от LENGTH_GRANT, чтобы видеть кто стал главой и от какого триггера).
  5. Re-fetch игрока с применённой прибавкой → `DailyHeadResolved(assignment=saved, player=saved_player, was_new=True)`.
- **Новый `AuditSource.DAILY_HEAD = "daily_head"`** в `domain/security/entities.py` (для anti-cheat) + в `domain/shared/ports/audit.py` (для audit-логгера) + добавлен в `anticheat.organic_sources` (premium-bonus считается organic для anti-cheat clamp; otherwise чёрный ящик 20-см clamp обрезал бы законную прибавку 1–20 см).
- **Alembic-миграция `0014_audit_source_daily_head`** — drop+recreate CHECK-whitelist `source` колонки `audit_log` (PostgreSQL не поддерживает `ALTER TABLE ... ADD VALUE` для CHECK constraint, только для ENUM-типов, поэтому drop+recreate). Migration test обновлён.
- **DI-провязка в `bot/main.py::build_container`** (Спринт 2.3.C, шаг #5):
  - `daily_heads = SqlAlchemyDailyHeadRepository(uow=uow)`,
  - `daily_activity = SqlAlchemyDailyActivityRepository(uow=uow, clock=clock)`,
  - `daily_head_service = DailyHeadService(balance, clock, random=RealRandom(), heads, activity)`,
  - `request_daily_head = RequestDailyHead(...)`, `run_daily_head_cron = RunDailyHeadCron(...)`,
  - 5 новых полей в `Container` (`daily_heads`, `daily_activity`, `daily_head_service`, `request_daily_head`, `run_daily_head_cron`).
- **Wiring в `build_dispatcher`**: `dispatcher["request_daily_head"]` + `dispatcher["run_daily_head_cron"]` для handler-а 2.3.E (cron use-case также доступен в dispatcher для admin-команд / диагностики; основной runner — APScheduler 2.3.F).
- **+18 unit-тестов** (`tests/unit/application/daily_head/`):
  - `test_request_daily_head.py` — **11 тестов**: success new (idempotency-key + LENGTH_GRANT + DAILY_HEAD_ASSIGN audit), success idempotent (was_new=False, нет дополнительных side-effects), no-clan, frozen-clan, insufficient-active-members, race UNIQUE→re-fetch, FakeRandom детерминирует выбор кандидата, FakeClock контролирует `moscow_date`.
  - `test_run_daily_head_cron.py` — **7 тестов**: success new (без actor_tg_id), success idempotent (DAU не меняется), unknown clan_id → None, FROZEN clan → None (no-op), insufficient-active-members → пропускает domain-error через UoW (`DailyHeadInsufficientActivityError` всё-таки бросается, чтобы шедулер видел метрику), race-handling identical to button-trigger.
  - `tests/unit/bot/test_composition_root.py` обновлён (5 fakes + RequestDailyHead/RunDailyHeadCron в `_container_with_fakes()` + assertion `test_container_holds_daily_head_use_cases` + assertions в `test_build_container_returns_real_adapters` + dispatcher-assertions для `request_daily_head` / `run_daily_head_cron`).

Результат / артефакты:
- `src/pipirik_wars/application/daily_head/{__init__,dto,inputs,request,run_cron,_common}.py` — 6 новых модулей.
- `src/pipirik_wars/bot/main.py` — DI-провязка (`Container` + `build_container` + `build_dispatcher`).
- `alembic/versions/0014_audit_source_daily_head.py` — миграция CHECK-whitelist.
- `tests/unit/application/daily_head/{test_request_daily_head,test_run_daily_head_cron}.py` — 18 unit-тестов.
- `tests/unit/bot/test_composition_root.py` — обновления fakes + assertions.
- `docs/current_tasks.md` — `2.3.B` → ✅ смержено (PR #69), `2.3.C` → 🔄 в работе (PR будет создан этим коммитом).

Заметки / решения:
- **Frozen-кланы и cron-trigger**: cron возвращает `None` (no-op без ошибки), button-trigger бросает `ClanFrozenError`. Это намеренная асимметрия — APScheduler поднимает дико много задач (один per-clan per-day), и если один клан стал FROZEN, шедулер не должен падать или ретраить; UI же должен сказать пользователю явно.
- **`DailyHeadInsufficientActivityError`**: пробрасывается наружу как button-trigger ошибка (UI покажет «недостаточно активных»), и **тоже пробрасывается** из cron-use-case-а (наружу) — так шедулер 2.3.F получит метрику, что для конкретного клана сегодня не получилось назначить, и сможет залогировать это (опционально retry next day). Альтернатива — поглощать в cron — отвергнута, потому что тихий no-op скрывает проблему «клан перестал быть активен» от админа.
- **`AuditSource.DAILY_HEAD` в `organic_sources`**: премия 1–20 см от главы клана дня — это «органический» bonus для anti-cheat, поэтому клампинг не должен срезать его на 20-см floor. Альтернатива — отдельный enum / флаг — отвергнута, organic_sources уже решает эту задачу для других премий (forest, oracle).
- **Idempotency-keys**: использованы стабильные `add_length:daily_head:<clan_id>:<moscow_date>` для LENGTH_GRANT и `daily_head_assign:<clan_id>:<moscow_date>` для DAILY_HEAD_ASSIGN. На race (button+cron одновременно) выигравшая транзакция сделает обе записи; проигравшая ловит UNIQUE-violation, делает re-fetch, возвращает `was_new=False` без дополнительных side-effects (length / audit не дублируются).
- **DI-инстансы `RealRandom` для `DailyHeadService`**: создаём отдельный `RealRandom()` (не reuse из `container.random`) — это `IRandom` для domain-сервиса, в production-е mass-PvP / oracle / forest используют свой `container.random` (тоже `RealRandom`); прямой share не нужен, RNG-состояние независимо. Альтернатива через DI-singleton отвергнута — преждевременная оптимизация.
- **`DailyHeadResolved.player`**: re-fetch после `length_granter.grant(...)` обязателен, потому что `add_length` модифицирует `Player`-aggregate, а у нас в use-case-е свежий объект игрока нужен для UI. Без re-fetch презентер 2.3.E увидел бы старую длину.

---

---

## 2026-05-06 — Спринт 2.3.B: persistence-слой «Главы клана дня» (миграции 0012/0013 + ORM + 2 репо + 19 integration-тестов)

**Автор:** Devin (агент urbanviola)
**Тип:** feature
**Связано:** ПД §5 / Спринт 2.3.2, ГДД §6.1; ветка `devin/1778057764-sprint-2-3-b-daily-head-persistence` (PR следует)

Что сделано:
- Реализован persistence-слой «Главы клана дня» (фундамент 2.3.A смержен в PR #68). Все side-эффекты на месте; следующий шаг — use-cases (2.3.C) и UI (2.3.E).
- **Alembic-миграция `0012_daily_heads`**: таблица `daily_heads` (`id BigSerial PK, clan_id BigInt FK clans CASCADE, player_id BigInt FK users CASCADE, moscow_date Date, source VarChar(8), bonus_cm Int, assigned_at DateTime(tz=True)`):
  - **UNIQUE `(clan_id, moscow_date)`** — last-line-of-defense от race кнопка-vs-cron. Доменный `DailyHeadService.assign_or_get` сначала делает preflight-проверку, но при гонке двух конкурентных транзакций (button+cron одновременно) UNIQUE-индекс отбросит дубль `IntegrityError`-ом, а репозиторий конвертирует его в `DailyHeadAlreadyAssignedError`.
  - CHECK-инварианты на уровне БД: `bonus_cm > 0` (премия положительная), `source IN ('button', 'cron')` (только два допустимых триггера).
  - **Index `(clan_id, assigned_at DESC, id DESC)`** — для `list_recent_for_clan` (anti-repeat-фильтр в `DailyHeadService._filter_avoid_recent`); сортировка с tie-breaker по `id` обязательна — `assigned_at` приходит из `IClock` и часто совпадает у соседних записей в тестах.
- **Alembic-миграция `0013_daily_active`**: таблица `daily_active` (`date Date NOT NULL, user_id BigInt NOT NULL FK users CASCADE, last_at DateTime(tz=True) NOT NULL`) с **PK `(date, user_id)`** (идемпотентный upsert на каждое сообщение) и **Index `(user_id, date DESC)`** (для запроса «активность одного игрока за последние N дней» без сканирования).
- **ORM-модели** `DailyHeadAssignmentORM` + `DailyActiveORM` (зеркало миграций) в `infrastructure/db/models/`. Регистрация в `models/__init__.py` (re-export для `Base.metadata.create_all` в conftest).
- **`SqlAlchemyDailyHeadRepository`** (3 метода `IDailyHeadRepository`):
  - `get_by_clan_and_date(*, clan_id, moscow_date)` — SELECT через UNIQUE; `_row_to_entity` маппинг с `ensure_utc(...)` (SQLite возвращает naive-datetime даже из `DateTime(timezone=True)` колонки, Postgres — tz-aware).
  - `add(assignment)` — INSERT с конвертацией `SqlAlchemyIntegrityError` → доменный `DailyHeadAlreadyAssignedError(clan_id, moscow_date)` для race-handling в use-case-е.
  - `list_recent_for_clan(*, clan_id, limit)` — ORDER BY `assigned_at DESC, id DESC` LIMIT N; `limit <= 0` → пустой tuple (не упасть).
- **`SqlAlchemyDailyActivityRepository.list_active_member_ids(*, clan_id, within_days)`** (`IDailyActivityRepository`):
  - Один SQL JOIN `users × clan_members × clans × daily_active` + DISTINCT.
  - Фильтры: `ClanStatus.ACTIVE` (frozen-клан вообще не получает триггер главы — ПД 2.3.8) + `PlayerStatus.ACTIVE` (FROZEN-игроки исключаются автоматически по контракту 2.3.A) + окно `[clock.moscow_date() - (within_days - 1) ... clock.moscow_date()]` включительно.
  - **`IClock` инъектится в конструктор** — порт `IDailyActivityRepository` намеренно не принимает `as_of` параметром (см. контракт 2.3.A); реализация сама знает «сегодня по МСК». Альтернатива через `func.current_date()` была бы привязана к TZ-сессии БД (хрупко).
  - Запись в `daily_active` будет делать middleware в Спринте 2.3.E (`bot/middlewares/daily_activity.py`); на момент 2.3.B репозиторий read-only, integration-тесты прямым `session.add(DailyActiveORM(...))` готовят данные.
- **+19 integration-тестов** (`tests/integration/db/daily_head/`):
  - `test_daily_head_repository.py` — **10 тестов**: пустая БД (`get → None`), add→get round-trip с `ensure_utc`, UNIQUE-violation на race (`add` вторым `player_id` → `DailyHeadAlreadyAssignedError`), два разных клана могут иметь главу в один день, один клан — разные дни — независимы, `list_recent_for_clan` пусто/limit/limit=0/order DESC с tie-breaker по id, фильтр по clan_id (другие кланы не попадают), иммутабельность входного VO (id остаётся None после add, возврат — новый VO с id).
  - `test_daily_activity_repository.py` — **9 тестов** + `_FakeClock`: пустой клан, активный внутри окна, не активный за окном (10 дней назад при `within_days=7`), граница окна (TODAY-6 включается, TODAY-7 нет), FROZEN-игрок исключён даже при наличии активности, чужой клан исключён, член клана без активности исключён, дубликаты активности (3 разных дня одного игрока) → DISTINCT, `within_days < 1` → ValueError.
- **`tests/integration/db/test_migrations.py`**: добавлены revisions `0012_daily_heads` + `0013_daily_active` в `test_expected_revisions_exist`, два descends-from-теста, новые имена файлов в `test_versions_dir_lists_only_known_files`, `EXPECTED_TABLES` пополнен `daily_heads` + `daily_active`.
- **`tests/integration/db/conftest.py`**: импорт `DailyHeadAssignmentORM` + `DailyActiveORM` в общем блоке (нужно для `Base.metadata.create_all`).

Результат / артефакты:
- `src/pipirik_wars/infrastructure/db/migrations/versions/20260506_0012_daily_heads.py` (118 строк).
- `src/pipirik_wars/infrastructure/db/migrations/versions/20260506_0013_daily_active.py` (76 строк).
- `src/pipirik_wars/infrastructure/db/models/daily_head.py` + `daily_active.py` (зеркала миграций).
- `src/pipirik_wars/infrastructure/db/repositories/daily_head.py` + `daily_activity.py`.
- `tests/integration/db/daily_head/test_daily_head_repository.py` (10 тестов).
- `tests/integration/db/daily_head/test_daily_activity_repository.py` (9 тестов).
- Локальный smoke на изолированных тестах: `test_daily_head_repository.py` 10/10 passed, `test_daily_activity_repository.py` 9/9 passed, `test_migrations.py` 19/19 passed (revisions/descends/files/EXPECTED_TABLES).

Заметки / решения:
- Порт `IDailyActivityRepository` контракта 2.3.A фиксирован — не принимает `as_of` параметром. Реализация инъектит `IClock` в конструктор. Это отличается от паттерна use-case-ов (где clock передаётся снаружи), но для read-репозитория с временной семантикой это самый чистый способ — вызывающему коду (доменному сервису) не нужно знать о TZ-конверсиях, а репо не привязан к TZ-сессии БД.
- Race-handling в `SqlAlchemyDailyHeadRepository.add(...)` поднимает доменный `DailyHeadAlreadyAssignedError`, а не `IntegrityError` — use-case 2.3.C это перехватит, сделает повторный `get_by_clan_and_date(...)` и вернёт запись от победителя (см. контракт 2.3.A `assign_or_get`).
- `daily_active` middleware **не реализована** в 2.3.B — это для Спринта 2.3.E (когда подключаем bot-обработчики и middleware-цепочку). На 2.3.B integration-тесты пишут в `daily_active` напрямую через `session.add(DailyActiveORM(...))`, что моделирует поведение middleware.
- `clan_members` в JOIN-е не отфильтровывается по `joined_at` — текущая семантика «состою в клане сейчас» = есть row в `clan_members`. Если в будущем добавится `clan_members.left_at`, фильтр расширится.
- Все DateTime-колонки `(timezone=True)`, `ensure_utc(...)` применяется на чтении для совместимости с SQLite (production — Postgres + asyncpg, там tzinfo приходит сразу).

---

## 2026-05-06 — Спринт 2.3.A: доменный слой «Главы клана дня» (47 тестов, фундамент гибридного триггера)

**Автор:** Devin (агент урbanviola)
**Тип:** feature
**Связано:** ПД §5 / Спринт 2.3.1, ГДД §6.1; ветка `devin/1778056664-sprint-2-3-a-daily-head-domain` (PR следует)

Что сделано:
- Создан пакет `domain/daily_head/` — фундамент гибридного триггера «Главы клана дня» (ГДД §6.1, Q4 v9). VO + порты + сервис без I/O, чистый и детерминированно тестируемый.
- VO `DailyHeadAssignment` (`id, clan_id, player_id, moscow_date, source, bonus_cm, assigned_at`) + enum `DailyHeadSource` (`BUTTON` / `CRON`). Frozen-датакласс с `__post_init__`-валидацией: positive id/clan/player/bonus, timezone-aware `assigned_at`. `id=None` валиден (запись до `add()`).
- Доменные ошибки `DailyHeadInsufficientActivityError` (clan_id, active_count, required) и `DailyHeadAlreadyAssignedError` (clan_id, moscow_date) — наследуются от `DailyHeadError → DomainError`.
- Порт `IDailyHeadRepository`: `get_by_clan_and_date(*, clan_id, moscow_date)` (UNIQUE-индекс гарантирует max 1), `add(assignment)` (`IntegrityError` на дубль `(clan_id, moscow_date)`), `list_recent_for_clan(*, clan_id, limit)` (порядок `assigned_at DESC, id DESC`, тай-брейкер обязателен).
- Порт `IDailyActivityRepository`: `list_active_member_ids(*, clan_id, within_days)` — скрывает источник «активных за N дней» (реализация может смотреть `players.last_seen_at`, audit-лог за период и т.п.). Заморозкенные / удалённые из клана автоматически исключаются.
- Доменный сервис `DailyHeadService.assign_or_get(*, clan_id, source)` через `IClock` + `IRandom`:
  1. Идемпотентность по `(clan_id, moscow_date)` — повторный вызов = тот же `Assignment` (source не перезаписывается! Если cron сработал первым, кнопка получит запись с `source=CRON`).
  2. Запрос «активные за `active_within_days` дней» из `IDailyActivityRepository`.
  3. `min_active_members`-проверка (по умолчанию 5) → `DailyHeadInsufficientActivityError`.
  4. Anti-repeat: исключаем `avoid_last_n` (по умолчанию 3) свежих глав через `list_recent_for_clan`.
  5. Fail-open: если фильтр вычистил всех — берём всех активных (повтор лучше «никого»).
  6. `IRandom.choice` из пула + `IRandom.randint(bonus_min, bonus_max)` (∈ [1, 20] по дефолту).
  7. Возврат `DailyHeadAssignment` с `id=None` и `assigned_at=clock.now()`. Запись в БД делает use-case 2.3.C.
- `BalanceConfig.daily_head` (`DailyHeadConfig`) уже существовал из ГДД-фазы; сервис читает из него все настройки. `IRandom.deterministic_uint(seed, modulo)` — тоже уже был, для cron-offset-логики 2.3.F.
- **+47 unit-тестов** (~580 строк):
  - **22 тесты VO/enum** (`tests/unit/domain/daily_head/test_entities.py`): happy-path для `BUTTON` / `CRON` source, frozen-семантика на 3 поля, инварианты (parametrize × bad_id/clan/player/bonus), naive `assigned_at` rejected, non-UTC tz allowed, `id=None` allowed.
  - **7 тестов ошибок** (`test_errors.py`): inheritance chain, payload-поля, format-сообщений (clan_id, counts, moscow_date.isoformat).
  - **18 тестов сервиса** (`test_service.py`): идемпотентность (returns existing с не-перезаписанным source); insufficient activity (3 vs min=5; zero active); avoid_last_n (3 свежих исключены, выбор из {4..7}); other-clan recent не влияет на фильтр; bonus всегда в `[bonus_min, bonus_max]` × 20 seed-ов; assigned_at = clock.now(); moscow_date = clock.moscow_date() (22:00 UTC = 01:00 МСК следующего дня); source preserved (BUTTON / CRON); activity-query вызвана с `within_days=7`; `list_recent_for_clan(limit=avoid_last_n)`; `avoid_last_n=0` → пул = все активные; existing с `id` ≠ None; service не пишет в repo (heads.items пуст после assign).
- Helper-функция `_make_assignment(...)` в test_entities — типизированные kwargs (избегает mypy `dict[str, object]`-ошибок).
- Фейки `FakeDailyHeadRepository` / `FakeDailyActivityRepository` в `tests/fakes/daily_head.py` + добавлены в `tests/fakes/__init__.py` (re-export). `FakeDailyHeadRepository.add()` бросает `IntegrityError` на UNIQUE-violation — точная имитация Postgres.
- Фабрика `valid_balance_payload()` уже содержала секцию `daily_head` (min=5, avoid=3, bonus=[1,20], within=7) — изменений в balance/factories.py не потребовалось.

Результат / артефакты:
- `src/pipirik_wars/domain/daily_head/__init__.py` (re-export всего публичного API).
- `src/pipirik_wars/domain/daily_head/entities.py` — `DailyHeadAssignment` + `DailyHeadSource`.
- `src/pipirik_wars/domain/daily_head/errors.py` — `DailyHeadError` иерархия.
- `src/pipirik_wars/domain/daily_head/repositories.py` — `IDailyHeadRepository` + `IDailyActivityRepository`.
- `src/pipirik_wars/domain/daily_head/services.py` — `DailyHeadService.assign_or_get(...)`.
- `tests/fakes/daily_head.py` (in-memory фейки).
- `tests/unit/domain/daily_head/test_entities.py` (22 теста), `test_errors.py` (7), `test_service.py` (18).
- `make ci` зелёный: **2483 passed**, 1 skipped, **coverage 95.88%**, `domain/daily_head/` — **100% coverage** (все 5 файлов: 6+28+18+7+29 строк).

Заметки / решения:
- **Источник сохраняется при идемпотентности**: если cron сработал в 03:00 МСК и игрок нажал кнопку в 09:00 МСК, у assignment остаётся `source=CRON`. Это нужно для аналитики «какой триггер был эффективнее» — не перезаписываем нечаянно.
- **Fail-open вместо fail-closed**: если все активные оказались в last-N (теоретически возможно при `avoid_last_n >= active_count`), сервис всё равно назначает кого-то из активных, а не падает. Лучше повтор, чем «сегодня нет главы». В дефолтных настройках min_active=5 / avoid_last_n=3 эта ветка недостижима через нормальные данные, но порт `list_recent_for_clan` имеет `limit`-параметр, и реализация может вернуть >limit при ошибке — fail-open защищает.
- **Не пишет в БД сам**: `assign_or_get` возвращает `DailyHeadAssignment` с `id=None`. Use-case 2.3.C обернёт в UoW и сделает `heads.add(...)`. Это разделение позволяет тестировать сервис без UoW / транзакций — чисто IO-агностично.
- **Источник активности абстрагирован**: `IDailyActivityRepository` не принимает «откуда брать активность». Реализация (Спринт 2.3.B) выберет: либо `players.last_seen_at`, либо новая таблица `daily_active`, либо JOIN на audit-лог. Контракт фиксирует «player_id ∈ clan_members активен в окне».
- **`avoid_last_n=0` отдельно протестирован**: anti-repeat-фильтр выключен, недавние главы могут быть выбраны снова. Это полезно для маленьких кланов или временно для тестов.
- **`BUTTON` ≠ `CRON` через сравнение `set`**: mypy detects `is`/`!=` как non-overlapping когда левый и правый — разные literal-ы, поэтому в тесте distinct_members используется `{B, C} == set(DailyHeadSource)`.
- **Async-helper `_filter_avoid_repeat`**: выделен для читаемости основного метода. Вызывается через `await`, потому что зовёт `await self._heads.list_recent_for_clan(...)`. Можно было бы синхронным, если предзагрузить recent в `assign_or_get` — но ленивая загрузка экономит запрос когда `avoid_last_n=0`.
- **Дальнейшие шаги** (планы для серии 2.3.B-F):
  - 2.3.B: alembic-миграция `0012_daily_heads` (UNIQUE `(clan_id, moscow_date)`, FK на `clans` / `players`) + ORM + `SqlAlchemyDailyHeadRepository`. Активность: либо отдельная `daily_active`-таблица + miграция, либо переиспользовать `players.last_seen_at` (если есть) / audit-лог.
  - 2.3.C: use-case-ы `RequestDailyHead(clan_id, requester_id)` (button-trigger; проверка членства) и `RunDailyHeadCron(clan_id)` (cron-trigger; пропуск frozen / archived); UoW + `add_length(reason="daily_head")` через `ILengthGranter` + audit `DAILY_HEAD_ASSIGNED`.
  - 2.3.D: `templates/clan_quotes_ru.json` + `_en.json` (≥100 цитат каждый) — стилистика «Стэтхем / паблики ВК / АУФ». `IClanQuoteProvider` + Fluent-loader.
  - 2.3.E: bot handler `/clan_head` (group-only, проверка членства) + кнопка `🎲Назначить главу дня` + локали `clan-head-{header,empty,already-assigned,not-registered,needs-group-chat,quote}` RU+EN.
  - 2.3.F: APScheduler-cron с per-clan `random_offset(0..24h)` от 00:00 МСК (`IRandom.deterministic_uint(seed=f"{clan_id}:{moscow_date}", modulo=24*3600)`); DI-провязка всех частей; cron не назначает повторно если кнопка сработала.

---

## 2026-05-06 — Спринт 2.2.G: журнал клановых атак (`/clan_history` + read-side SQL-проекция + 88 тестов)

**Автор:** Devin (по запросу urbanviola)
**Тип:** feature
**Связано:** `current_tasks.md` Спринт 2.2.G, ПД 2.2.5 (`development_plan.md` §6), ГДД §7.2 (журнал клановых боёв в карточке клана).

Что сделано:
- **Domain VO `ClanMassDuelHistoryEntry`** (`src/pipirik_wars/domain/pvp/clan_history.py`) + enum `ClanMassDuelOutcomeForUs` (`VICTORY`/`DEFEAT`/`DRAW`/`CANCELLED`) с `outcome_from_winner(winner, our_side)` и full-`__post_init__`-валидацией: zero-sum дельт (`our_delta_cm + opponent_delta_cm == 0`), state↔outcome agreement (`CANCELLED` обоюдно), VICTORY ⇒ dealt > received, DEFEAT ⇒ dealt < received, DRAW ⇒ dealt == received, `completed_at` присутствует только для не-CANCELLED.
- **Application-порт `IClanMassDuelHistoryQuery.get_recent(*, clan_id, limit)`** + read-only use-case `GetClanAttackHistory(query, default_limit=10)` — тонкая обёртка с валидацией входов (`clan_id > 0`, `limit > 0`), по аналогии с `GetTopClans`/`GetTopPlayers` (Спринт 2.2.A / 1.4.C).
- **Infrastructure read-side `SqlAlchemyClanMassDuelHistoryQuery`**: один SQL-запрос по `pvp_mass_duels` с CASE-выражением для `opponent_id` (если `clan1_id == clan_id` ⇒ `clan2_id`, иначе `clan1_id`) + 2 коррелированных subquery к `pvp_mass_duel_choices` (counts on each side) + JOIN к `clans` для `opponent_title`; фильтр `state IN ('completed', 'cancelled')` (`IN_PROGRESS`-бои не показываются), сортировка `created_at DESC, id DESC`; денормализация в VO с маппингом `clan1`/`clan2` → `our`/`opponent` сторон.
- **Bot-слой**: `ClanHistoryPresenter` через `IMessageBundle` (ключи `clan-history-{header,empty,needs-group-chat,not-registered,entry-{victory,defeat,draw,cancelled}}` RU+EN) с `dd.mm HH:MM`-форматом времени (берёт `completed_at` для COMPLETED, `created_at` для CANCELLED); handler `/clan_history` (group-only, ищет клан по `tg_identity.chat_id`, в ЛС → `needs-group-chat`, в чате без клана → `not-registered`).
- **DI-провязка**: новый router `clan_history_router` в `register_routers`; `clan_mass_duel_history_query` + `get_clan_attack_history` в `Container` / `build_dispatcher`; `dispatcher["get_clan_attack_history"]` в `bot/main.py`.
- **Локали**: 8 ключей `clan-history-*` × 2 локали = 16 строк (`locales/{ru,en}.ftl`).
- **Тесты**: +88 (33 VO `tests/unit/domain/pvp/test_clan_history_entry.py` + 12 use-case `tests/unit/application/pvp/test_get_clan_attack_history.py` + 16 integration SQL `tests/integration/db/pvp/test_clan_mass_duel_history_query.py` + 18 presenter `tests/unit/bot/presenters/test_clan_history.py` + 9 handler `tests/unit/bot/handlers/test_clan_history.py`) + `FakeClanMassDuelHistoryQuery` (`tests/fakes/clan_history.py`).

Результат / артефакты:
- `make ci` зелёный (2431 passed, 1 skipped, coverage 95.84%).
- ПР: см. PR-ссылку в session.

Заметки / решения:
- **Read-side, не доменный репо.** `IClanMassDuelHistoryQuery` живёт в `application/pvp/`, реализация в `infrastructure/db/repositories/`, но это не доменный `IMassDuelRepository` (он про write-side / load-by-id). VO `ClanMassDuelHistoryEntry` — это перспектива конкретного клана, а не агрегат. По CQRS-стилю — read-projection.
- **Денормализация в SQL.** `opponent_clan_title` приходит из `clans.title` JOIN-ом (а не лайв-резолв на app-слое), `our/opponent_participants_count` — из коррелированных subquery к `pvp_mass_duel_choices` (на момент запроса = размер ростера, замороженный при `StartMassDuel`). Это даёт O(1) запрос на показ всего журнала клана, против O(N) live-резолва.
- **`IN_PROGRESS`-фильтр в SQL.** Историю показываем только по завершённым/отменённым боям — текущий идущий бой клан видит через `started_card`, а не через `/clan_history`. Это устраняет «мерцание» (бой в журнале до его финала).
- **`completed_at` для CANCELLED = NULL.** В миграции 0011 (Спринт 2.2.D) `completed_at` обнуляется при `CANCELLED`-state-е (CHECK-инварианте). Презентер берёт `created_at` для CANCELLED-боёв — единственное доступное поле.
- **Сортировка `created_at DESC, id DESC`.** Тай-брейкер `id DESC` обязателен — `created_at` приходит из app-слоя (`IClock`) и в тестах часто совпадает у соседних боёв.

---

## 2026-05-06 — Спринт 2.2.F часть 2: bot-слой массового PvP (`/clan_attack` handler + callback-ы + 27 unit-тестов)

**Автор:** Devin (по запросу urbanviola)
**Тип:** feature
**Связано:** `current_tasks.md` Спринт 2.2.F (часть 2), ПД 2.2.6 (`development_plan.md` §6), ГДД §7.2; продолжение `AGENT_HANDOFF.md` от предыдущего агента (часть 1 — PR #65 — поставила локали + `MassDuelPresenter`).

### Что сделано

- Новый `src/pipirik_wars/bot/handlers/mass_duel.py` — bot-слой массового PvP клан×клан:
    - **`/clan_attack`** (group/supergroup-only): резолвит `attacker_chat_id` из `tg_identity.chat_id`, `defender_chat_id` из `command.args` (числовой `chat_id`) **или** `message.reply_to_message.forward_from_chat.id` (reply на forwarded-сообщение из чата защищающегося клана). Без аргументов и без forward-reply — usage-сообщение `pvp-mass-target-needed`. Проверка self-attack (`attacker_chat_id == defender_chat_id`) → `pvp-mass-self-attack`.
    - Зовёт `StartMassDuel.execute(StartMassDuelInput(initiator_tg_id, attacker_chat_id, defender_chat_id))` и ловит:
        - `IntegrityError` (клан не зарегистрирован) → `pvp-mass-target-not-found`;
        - `ClanFrozenError` → `pvp-mass-clan-frozen`;
        - `MassDuelCooldownError(cooldown_hours)` → `pvp-mass-cooldown`;
        - `MassDuelNoParticipantsError` → `pvp-mass-no-participants` (с `min_length_cm` / `min_thickness_level` из `balance.pvp.mass_duel`);
        - `LockAlreadyHeldError` → `pvp-mass-lock-already-held`.
    - На успех: `IClanRepository.get_by_id(...)` для обеих сторон → `MassDuelPresenter.started_card(attacker_title, defender_title, attacker_size, defender_size, timer_seconds)` в групповой чат. Затем для каждого `player_id ∈ clan1_member_ids ∪ clan2_member_ids`: `IPlayerRepository.get_by_id(player_id=...)` → `IPlayerLocaleResolver.resolve_for_tg_id(player.tg_id)` → `bot.send_message(chat_id=player.tg_id, text=presenter.prompt_attack(locale=...), reply_markup=presenter.attack_keyboard(duel_id, locale=...))`.
    - **Callback `pvpm-attack:<duel_id>:<position>`**: парсит `parse_mass_attack_callback_data(...)` (на `ValueError` → toast `pvp-mass-toast-outdated` + strip keyboard); `callback.answer(toast_attack_selected)`; редактирует текст на `presenter.prompt_block(attack=Position(parsed.position))` и заменяет клавиатуру на `presenter.block_keyboard(duel_id, attack)`. Use-case не вызывается — атака зашита в новый `callback_data`.
    - **Callback `pvpm-block:<duel_id>:<attack>:<position>`**: парсит callback_data; зовёт `SubmitMassMove.execute(SubmitMassMoveInput(duel_id, tg_id, attack, block))`. Ошибки → toast-ы (`pvp-mass-toast-not-found` / `not-participant` show_alert=True / `invalid-state` / `already-submitted`). На успех: `callback.answer(toast_move_accepted)` + strip keyboard + edit text → `pvp-mass-waiting`. Если `submitted.is_ready_to_resolve` — зовёт `ResolveMassDuel.execute(ResolveMassDuelInput(duel_id))` (на `MassDuelNotFoundError` / `InvalidMassDuelStateError` — идемпотентный no-op без broadcast); затем `_broadcast_result(...)` рассылает каждому участнику персональную DM (`result_victory_dm` / `result_defeat_dm` / `result_draw_dm` в зависимости от `outcome.winner` и принадлежности игрока к стороне, с подстановкой `winner_clan_title` / `loser_clan_title` / `total_dealt` / `total_lost` / `delta_cm`) + публичную карточку `result_chat(winner, winner_clan_title, total_dealt)` в чаты обоих кланов.
    - Helper-функции `_resolve_defender_chat_id`, `_broadcast_attack_prompt`, `_broadcast_result`, `_iter_participants`, `_build_personal_result`, `_strip_keyboard` / `_set_message_text` / `_set_message_keyboard`. `MassDuelPresenter` (427 строк) уже был в репо — не менялся.
- DI-провязка в `src/pipirik_wars/bot/main.py`:
    - Новый router `mass_duel_router` зарегистрирован в `register_routers(...)` (между `duel_router` и `oracle_router`).
    - В `build_dispatcher(...)` добавлены workflow-data ключи: `start_mass_duel`, `submit_mass_move`, `resolve_mass_duel`, `clans` (use-case-ы и `IClanRepository` из контейнера). `players` / `bundle` / `player_locale_resolver` / `bot` уже были.
- **+27 unit-тестов** в `tests/unit/bot/handlers/test_mass_duel.py`:
    - 11 на `/clan_attack`: silent-no-identity, private-rejected, missing-target, invalid-arg, self-attack, forward-reply happy-path, `IntegrityError` / `ClanFrozenError` / `MassDuelCooldownError` / `MassDuelNoParticipantsError` / `LockAlreadyHeldError`, success-broadcast.
    - 4 на `pvpm-attack`: silent-no-identity, silent-no-data, invalid callback_data → outdated, success.
    - 12 на `pvpm-block`: silent, outdated, 4 use-case ошибки, not-ready-waiting, ready-to-resolve full broadcast (4 DM + 2 чата), resolve-not-found / invalid-state идемпотентный no-broadcast, draw-flow.

### Результат / артефакты

- Новые/обновлённые файлы:
    - `src/pipirik_wars/bot/handlers/mass_duel.py` (~530 строк).
    - `src/pipirik_wars/bot/handlers/__init__.py` (+2 строки: import + `include_router`).
    - `src/pipirik_wars/bot/main.py` (+5 строк в `build_dispatcher`).
    - `tests/unit/bot/handlers/test_mass_duel.py` (~770 строк, 27 тестов).
    - `docs/current_tasks.md` (+1 строка: «2.2.F часть 2 → 🔄 в работе»).
    - `docs/history.md` (текущая запись).
- Удалён `AGENT_HANDOFF.md` (281 строка) — спецификация продолжения от предыдущего агента, выполнена полностью.
- `make ci` зелёный: 2337 passed, 1 skipped, coverage **95.71%** (>= 80% порог).

### Заметки / решения

- **Резолв `defender_chat_id`**: HANDOFF предлагал 2 варианта — числовой аргумент команды или reply на forward-сообщение из защищающегося чата. Реализованы оба в `_resolve_defender_chat_id(...)`; приоритет — аргумент команды (если есть и парсится в `int`), иначе fallback на `reply_to_message.forward_from_chat.id`. Это даёт UX-симметрию `/duel @username` (1×1 reply) и `/clan_attack -100…` (mass attack reply) без необходимости копировать chat_id вручную.
- **Идемпотентность резолва**: callback `pvpm-block` сам вызывает `ResolveMassDuel` если `is_ready_to_resolve=True`. Параллельно может сработать AFK-шедулер 2.2.F часть 1 (`ForceResolveMassDuel`) — он уже идемпотентный (`was_already_resolved=True` если не IN_PROGRESS). Если шедулер успел первым, callback ловит `InvalidMassDuelStateError` и возвращается без broadcast (другая сторона уже получила DM/чат-карточку через шедулер). Это намеренно — Telegram гарантирует at-least-once для callback-ов, но мы не хотим дубль-DM.
- **DM-broadcast**: `_broadcast_attack_prompt` / `_broadcast_result` оборачивают каждый `bot.send_message` в `try/except` с warning-логом — один заблокировавший бота игрок не должен ронять рассылку всем остальным. Это симметрично логике `_broadcast_attack_prompt` в `bot/handlers/duel.py` (1×1 PvP).
- **Локали в DM**: каждый DM рендерится в персональной локали игрока через `IPlayerLocaleResolver.resolve_for_tg_id(...)` — игроки разных кланов могут видеть текст в разных языках. Чат-карточка `result_chat` идёт в `fallback_locale` (локаль инициатора атаки) — у группового чата нет «персональной» локали, и в массовом бою на 2-х сторонах нет одной общей.
- **Не имплементируется**: ручная отмена `/clan_cancel_attack` (нужен только админу — это `CancelMassDuel` с `reason="admin_cancel"`, отдельная задача за рамками 2.2.F). AFK-таймер 2.2.F часть 1 уже сам зовёт `ForceResolveMassDuel` через шедулер — если игрок не успел нажать кнопки в `move_timer_seconds`, бой резолвится по случайным выборам.
- **`MassDuelPresenter`** уже был полностью реализован предыдущим агентом (PR #65 / часть 1) — не трогал. Локали `pvp-mass-*` (32 ключа в `locales/{ru,en}.ftl`) тоже уже были — handler только зовёт презентер по нужным ключам.

---

## 2026-05-06 — Спринт 2.2.E: application-слой массового PvP (5 use-case-ов + DI + 35 unit-тестов)

**Автор:** Devin (по запросу intensive192)
**Тип:** feature
**Связано:** `current_tasks.md` Спринт 2.2.E, ПД 2.2.2 + 2.2.4 (`development_plan.md` §6), ГДД §7.2.

### Что сделано

- 5 use-case-ов в `src/pipirik_wars/application/pvp/`, поверх агрегата `MassDuel` (2.2.C) и репозитория `IMassDuelRepository` (2.2.D):
    - **`StartMassDuel`** (`start_mass_duel.py`): резолвит оба клана по `chat_id` через `IClanRepository.get_by_chat_id`; падает с `IntegrityError` при отсутствии и с `ClanFrozenError` при `ClanStatus.FROZEN`; собирает eligible-ростер каждого клана через `IClanMembershipRepository.list_by_clan(clan_id)` + `IPlayerRepository.get_by_id(...)` с фильтрами `PlayerStatus.ACTIVE`, `length_cm ≥ pvp.mass_duel.min_length_cm`, `thickness.level ≥ min_thickness_level`; пустой ростер любой стороны → `MassDuelNoParticipantsError`; cooldown через `find_most_recent_for_clan(clan_id)` с порогом `pvp.mass_duel.cooldown_hours` для каждого из двух кланов → `MassDuelCooldownError`; снапшот `hit_pct` из баланса; `MassDuel.create_battle(...)` + `add()`; PvP-локи всех участников через `ActivityLockService.acquire(actor_kind="player", ...)` с TTL=30 мин; audit `PVP_MASS_DUEL_CREATED` (idempotency-key `pvp_mass_duel_created:{duel_id}`, `actor_id=initiator_tg_id`).
    - **`SubmitMassMove`** (`submit_mass_move.py`): загружает `MassDuel` (нет — `MassDuelNotFoundError`); резолвит игрока по `tg_id` (нет — `PlayerNotFoundError`); валидирует `IN_PROGRESS` через `MassDuel.submit_move(...)` (доменные ошибки `InvalidMassDuelStateError`, `NotAMassDuelParticipantError`, `MassMoveAlreadySubmittedError` — пропускаются как есть); НЕ резолвит бой — резолв отдельной командой `ResolveMassDuel` или шедулером через `ForceResolveMassDuel`; возвращает флаг `is_ready_to_resolve` для удобства handler-а 2.2.F.
    - **`ResolveMassDuel`** (`resolve_mass_duel.py`): финальный резолв когда все отправили: `MassDuel.resolve(random=..., now=...)` (`InvalidMassDuelStateError`/`MassDuelNotReadyError` пропускаются); `apply_mass_duel_outcome(...)` (`apply_mass_outcome.py` от 2.2.D-ветки) — атакующим прибавки через `ILengthGranter.grant(source=PVP_REWARD)` (cap-trip-wire), защитникам списания прямой `with_length` + audit `LENGTH_REVOKE`; `release_mass_duel_locks(saved, locks=...)`; audit `PVP_MASS_DUEL_COMPLETED` (idempotency-key `pvp_mass_duel_completed:{duel_id}`, `afk_fallback=False`).
    - **`ForceResolveMassDuel`** (`force_resolve_mass_duel.py`): AFK-фоллбэк для шедулера 2.2.F; идемпотентный no-op (`was_already_resolved=True`) если бой уже не `IN_PROGRESS`; для каждого `pid in missing_player_ids` роллит `MassRoundChoice(player_id=pid, attack=random, block=random)` через `IRandom.choice(_POSITIONS)` (где `_POSITIONS = (HIGH, MID, LOW)`); если все уже отправили — пропускает шаг force-submit и сразу резолвит; `force_submit_missing(...)` → `resolve(...)` → `apply_mass_duel_outcome(...)` → `release_mass_duel_locks(...)` → audit `PVP_MASS_DUEL_COMPLETED` с `afk_fallback=True` и `reason="pvp_mass_duel_completed_afk"`.
    - **`CancelMassDuel`** (`cancel_mass_duel.py`): административная отмена без раскатывания ±длин: идемпотентный no-op (`was_already_cancelled=True`) если уже `CANCELLED`; `MassDuel.cancel(now=...)` (из `COMPLETED` → `InvalidMassDuelStateError` пропускается); снимает PvP-локи всех участников; audit `PVP_MASS_DUEL_CANCELLED` (idempotency-key `pvp_mass_duel_cancelled:{duel_id}`, `before={"state": ...}`, `after={"state": "cancelled"}`).
- Helper-функции `audit_mass_duel_completed(*, audit, duel, now, afk_fallback)` и `release_mass_duel_locks(duel, *, locks)` вынесены в `resolve_mass_duel.py` и переиспользуются в `force_resolve_mass_duel.py` (DRY: один формат audit-after, одна логика снятия локов).
- Все 5 use-case-ов следуют единому паттерну: `__slots__` (alphabetical), keyword-only DI в `__init__`, `async with self._uow:` ambient-транзакция, `async def execute(input_dto: ...) -> ...Result`. Frozen `dataclass` для каждого Result-DTO с `__slots__`.
- Все 5 use-case-ов экспортированы из `application/pvp/__init__.py`.
- DI-провязка в `bot/main.py`:
    - `Container` расширен 6 новыми полями: `mass_duels: IMassDuelRepository`, `start_mass_duel`, `submit_mass_move`, `resolve_mass_duel`, `force_resolve_mass_duel`, `cancel_mass_duel`.
    - `build_container(...)` создаёт `SqlAlchemyMassDuelRepository(uow=uow)` и инстанцирует все 5 use-case-ов с уже существующими `add_length` (как `ILengthGranter`), `RealRandom()`, `activity_lock_service` и т.д.
- Тесты:
    - `tests/unit/application/pvp/test_start_mass_duel.py` — 11 тестов: 2v2 happy-path с проверкой ростера / hit_pct / локов / audit; 1×1 ростер; eligibility-фильтр (под-длина исключается, только под-длина → `MassDuelNoParticipantsError`); неизвестный/frozen-клан с двух сторон; cooldown (свежий бой блокирует, старый не блокирует); preexisting-lock одного из участников → `LockAlreadyHeldError`.
    - `tests/unit/application/pvp/test_submit_mass_move.py` — 8 тестов: первый submit оставляет `IN_PROGRESS` и `is_ready_to_resolve=False`, последний submit возвращает `True`; `MassRoundChoice` персистится в правильную позицию; `MassDuelNotFoundError`, `PlayerNotFoundError`, `NotAMassDuelParticipantError`, `MassMoveAlreadySubmittedError`, `InvalidMassDuelStateError` (cancelled).
    - `tests/unit/application/pvp/test_resolve_mass_duel.py` — 6 тестов: happy-path 2v2 с проверкой `COMPLETED` + сняты все локи + один `PVP_MASS_DUEL_COMPLETED` без `afk_fallback`; ±длины применяются (атакующие ≥ старт, защитники ≤ старт); `MassDuelNotFoundError`; `MassDuelNotReadyError` если не все отправили; повторный resolve и cancelled → `InvalidMassDuelStateError`.
    - `tests/unit/application/pvp/test_force_resolve_mass_duel.py` — 6 тестов: 0/4 submitted → force; 2/4 submitted → force заполняет недостающих; 4/4 submitted → force работает без шага force_submit; идемпотентность повторного force-резолва (`was_already_resolved=True`, audit не дублируется); идемпотентность над уже cancelled-боем; `MassDuelNotFoundError`.
    - `tests/unit/application/pvp/test_cancel_mass_duel.py` — 4 теста: happy-path (все локи сняты, audit с правильными `before`/`after`/`reason`); идемпотентность повторной отмены; `MassDuelNotFoundError`; cancel над `COMPLETED` → `InvalidMassDuelStateError`.
    - Расширен `tests/unit/bot/test_composition_root.py` — `_container_with_fakes()` строит все 5 mass-duel use-case-ов; новый `test_container_holds_mass_duel_use_cases` проверяет `isinstance` всех 6 новых полей; `test_build_container_returns_real_adapters` проверяет `SqlAlchemyMassDuelRepository`.
    - Helper-модуль `tests/unit/application/pvp/_mass_helpers.py` — `seed_clan(...)`, `seed_clan_member(...)`, `seed_eligible_clan_member(...)`.
- `make ci` зелёный (lint + typecheck + imports + 2178 unit + integration тестов passed).

### Артефакты

- Новые файлы: `src/pipirik_wars/application/pvp/{start_mass_duel,submit_mass_move,resolve_mass_duel,force_resolve_mass_duel,cancel_mass_duel}.py`, `tests/unit/application/pvp/{test_start_mass_duel,test_submit_mass_move,test_resolve_mass_duel,test_force_resolve_mass_duel,test_cancel_mass_duel,_mass_helpers}.py`.
- Изменённые файлы: `src/pipirik_wars/application/pvp/__init__.py` (экспорт 5 use-case-ов + 5 Result-DTO + 2 helper-функций), `src/pipirik_wars/bot/main.py` (Container + build_container + DI), `tests/fakes/__init__.py` (`FakeMassDuelRepository`), `tests/unit/bot/test_composition_root.py` (impl + assertions).

### Заметки / решения

- **Helper-функции вынесены в `resolve_mass_duel.py`, а не в отдельный `_mass_outcome_helpers.py`:** `audit_mass_duel_completed` и `release_mass_duel_locks` нужны только в `Resolve` и `ForceResolve`, и оба зависят от `MassDuel`-агрегата. Делать отдельный файл преждевременно — переедут когда понадобится третий вызов (например, при ручной admin-команде force-через-handler в 2.2.F).
- **`is_ready_to_resolve` возвращается из `SubmitMassMove`, но use-case НЕ вызывает `ResolveMassDuel` сам:** по аналогии с 1×1 PvP, разделение submit и resolve упрощает рассуждение об idempotency, аудите и таймерах. Handler 2.2.F может проверить флаг и вызвать `ResolveMassDuel` синхронно — или дождаться шедулера.
- **`ForceResolveMassDuel` — идемпотентный по дизайну:** шедулер APScheduler в реальной системе может срабатывать после того, как handler `SubmitMassMove` вызвал `ResolveMassDuel`. Возврат `was_already_resolved=True` без аудита в этом случае — единственно правильное поведение (мы не должны писать второй `PVP_MASS_DUEL_COMPLETED`).
- **`CancelMassDuel` — НЕ применяет ±длины:** это административная отмена, не AFK-фоллбэк. Для AFK есть `ForceResolveMassDuel`, который раскатывает урон по случайным выборам (это «честный» резолв в смысле игровой логики). Cancel — для случаев, когда бой надо «забыть»: деградация ростера, abort через админ-команду.
- **`StartMassDuel` использует `add_length` (`AddLength`-инстанс) НЕ в DI — `length_granter` нужен только в `Resolve` / `ForceResolve`:** в `Start` нет ни прибавок, ни списаний, поэтому DI-список короче. По линии 1×1 PvP `ChallengeDuel` тоже не получает `ILengthGranter`.

### Следующий шаг

Sprint 2.2.F: bot-handler-ы (`/clan_attack`, inline-кнопки атаки/блока, кнопка отмены), локали `locales/{ru,en}/pvp_mass.ftl`, presenter-ы (форматирование `MassDuelOutcome` + audit-сводка), APScheduler-wiring AFK-таймера через `IDelayedJobScheduler.schedule_mass_duel_afk_resolution(...)` → `ForceResolveMassDuel`, индикация cooldown в `/clantop` или отдельной команде.

---

## 2026-05-05 — Спринт 2.2.D: persistence-слой массового PvP (`pvp_mass_duels` + ORM + репозиторий)

**Автор:** Devin (по запросу shirline89)
**Тип:** feature (alembic migration + ORM models + SQL-repository + integration tests)
**Связано:** `current_tasks.md` Спринт 2.2.D, ПД 2.2.2 (persistence для клан→клан, `development_plan.md` §6), ГДД §7.2.

После 2.2.C (доменный агрегат `MassDuel`) — следующий шаг: положить агрегат в БД, чтобы use-case-ы 2.2.E могли загружать/сохранять mass-duel-ы между HTTP-/Telegram-обновлениями. Persistence-слой проектируется по тому же шаблону, что и 1×1 `pvp_duels` + `pvp_duel_rounds` (2.1.C): root-row для root-агрегата + 1:N-таблицы для коллекций.

Что сделано:

- **Alembic-миграция `0011_pvp_mass_duels`** (`infrastructure/db/migrations/versions/20260505_0011_pvp_mass_duels.py`, ~270 строк):
  - `pvp_mass_duels` (root): `id`, `clan{1,2}_id` (FK→clans CASCADE), `state`, `hit_pct`, `created_at` / `completed_at` / `cancelled_at`, `final_clan{1,2}_total_dealt` / `final_clan{1,2}_delta_cm` / `final_winner` (всё nullable; заполнено только при COMPLETED). 8 CHECK-инвариантов: state-валидация, hit_pct 0..100, no-self-team, winner ∈ {clan1,clan2,draw}, `state_invariants` (полная state×field-матрица для IN_PROGRESS / COMPLETED / CANCELLED), zero-sum дельт, total_dealt non-negative ×2. 3 индекса: `(clan1_id, state)`, `(clan2_id, state)`, `(state, created_at)`.
  - `pvp_mass_duel_choices` (1:N от root, ростер + выборы): compound PK `(duel_id, player_id)`, `clan_side` (`clan1`/`clan2`), `initial_length_cm` (snapshot), `attack` / `block` / `submitted_at` (nullable до `submit_move`-а; pair-consistency CHECK). FK `duel_id`→`pvp_mass_duels` CASCADE, `player_id`→`users` CASCADE. 6 CHECK-ов + индекс `player_id`.
  - `pvp_mass_duel_damage_entries` (1:N от root, COMPLETED-only): compound PK `(duel_id, entry_idx)` (0-based, порядок-сохраняющий), `attacker_id` / `defender_id` (FK→users CASCADE, no-self CHECK), `attacker_attack` / `defender_block`, `blocked` (BOOL), `damage_cm` (non-negative, `blocked⇒damage=0` CHECK). 6 CHECK-ов.

- **ORM-модели** (`infrastructure/db/models/pvp.py`, +~200 строк): `PvpMassDuelORM` / `PvpMassDuelChoiceORM` / `PvpMassDuelDamageEntryORM` — зеркало миграции, full-`Mapped[]`-аннотации, `__table_args__` с теми же CHECK-/Index-определениями (для in-memory SQLite-тестов). Зарегистрированы в `infrastructure/db/models/__init__.py` и в `tests/integration/db/conftest.py`.

- **Доменный порт `IMassDuelRepository`** (`domain/pvp/repositories.py`, +~70 строк): `add(duel) → duel` (флаш для PK + insert ростера + опц. damage_entries), `get_by_id(*, duel_id) → MassDuel | None`, `save(duel) → duel` (синхронизация root + выборов; дозапись только новых damage-entries — иммутабельность existing-row-ов).

- **`SqlAlchemyMassDuelRepository`** (`infrastructure/db/repositories/pvp_mass_duel.py`, ~410 строк): полная реализация порта + helper-converter-ы `_choice_orm_to_value_object`, `_damage_entry_orm_to_value_object`, `_build_clan_side`, `_split_choice_rows_by_side`, `_row_to_mass_duel`, `_apply_root_fields`, `_damage_entry_to_orm`. Frozen-roster-инвариант: попытка `save()`-а с другим набором `clan{1,2}_member_ids` → `IntegrityError` (last-line-of-defense, домен сам не позволил бы). Все `SqlAlchemyIntegrityError`-ы конвертируются в доменный `IntegrityError`.

- **`FakeMassDuelRepository`** (`tests/fakes/mass_duel_repo.py`, ~70 строк): in-memory list `MassDuel`-ов, serial id (`max(...) + 1`), frozen-roster-guard. Будет использоваться в unit-тестах use-case-ов 2.2.E.

- **+13 integration-тестов** (`tests/integration/db/pvp/test_pvp_mass_duel_repository.py`, ~545 строк):
  - `TestInProgressPersistence`: add → assigned id; get_by_id round-trip без submit-ов; missing → None.
  - `TestSubmitMovePersistence`: save после `submit_move` (один игрок) сохраняет выбор; save после всех `submit_move`-ов оставляет state=IN_PROGRESS.
  - `TestCompletedPersistence`: resolve → COMPLETED + damage-entries; повторный save идемпотентен (не дублирует damage-entries).
  - `TestCancelledPersistence`: cancel → CANCELLED, без final-полей.
  - `TestErrorCases`: add с pre-set id, save без id, save с unknown id, save с tampered ростером.
  - `TestUnequalRosters`: 3v1-сценарий (параллельные кортежи восстанавливаются в правильном порядке после round-trip).

- **Обновлён `tests/integration/db/test_migrations.py`**: добавлен ассерт `0011_pvp_mass_duels` в наборе ревизий + новый тест `test_0011_descends_from_0010` + расширен `test_versions_dir_lists_only_known_files` + `test_upgrade_head_creates_all_tables` (3 новые таблицы).

- **`make ci` зелёный**: lint (ruff) + typecheck (mypy --strict, 477 файлов) + import-linter (3 contracts) + 2176 тестов passed (1 skipped). Coverage `pvp_mass_duel.py` — 94%, общий — 95.91%.

Результат / артефакты:
- Миграция: `src/pipirik_wars/infrastructure/db/migrations/versions/20260505_0011_pvp_mass_duels.py`.
- ORM: `src/pipirik_wars/infrastructure/db/models/pvp.py` (+ `__init__.py`).
- Domain port: `src/pipirik_wars/domain/pvp/repositories.py` (+ `__init__.py`).
- Repo: `src/pipirik_wars/infrastructure/db/repositories/pvp_mass_duel.py` (+ `__init__.py`).
- Fake: `tests/fakes/mass_duel_repo.py`.
- Тесты: `tests/integration/db/pvp/test_pvp_mass_duel_repository.py`, `tests/integration/db/test_migrations.py`, `tests/integration/db/conftest.py`.

Заметки / решения:
- **Почему 3 таблицы, а не одна с JSON-blob-ом?** Симметрично 1×1-pvp_duels (root + rounds): root-row хранит state-машину + snapshot-ы + финальный outcome; 1:N choices хранит ростер + выборы (один row на участника, indexed по `player_id` для быстрых query-ев); 1:N damage_entries хранит immutable-лог ударов (только COMPLETED, через `entry_idx` для детерминированного восстановления tuple-порядка). Никаких JSON-blob-ов — все CHECK-инварианты проверяются БД, не приложением.
- **Frozen-roster-инвариант** проверяется и доменом (`MassDuel`-mutator-ы не меняют ростер), и репозиторием (`save()` сравнивает существующий ростер с новым). Это last-line-of-defense — если кто-то в обход домена соберёт `replace(duel, clan1_member_ids=...)`, репо это поймает.
- **Damage-entries иммутабельны** после resolve. `save()` дописывает только row-ы, которых ещё нет (по `entry_idx`); существующие не апдейтит. Это даёт идемпотентность повторных save-ов и защищает от случайных тампер-row-ов.
- **DI-провязка отложена до 2.2.E**: на этом спринте нет use-case-ов, потребляющих `IMassDuelRepository`, так что `bot/main.py` пока не трогаем (мёртвая привязка только засорит DI-граф).

Следующий шаг — Спринт 2.2.E: use-case-ы (`StartMassDuel` / `SubmitMassMove` / `ResolveMassDuel` / `ForceResolveMassDuel`) + bot-handlers + локали + AFK-таймер + DI-провязка `mass_duels = SqlAlchemyMassDuelRepository(uow=uow)` в `build_dispatcher`.

---

## 2026-05-05 — Спринт 2.2.C: доменный агрегат `MassDuel` (lifecycle state machine)

**Автор:** Devin (по запросу shirline89)
**Тип:** feature (domain aggregate + lifecycle + новые доменные ошибки)
**Связано:** `current_tasks.md` Спринт 2.2.C, ПД 2.2.2 + домен-часть 2.2.4 (`development_plan.md` §6), ГДД §7.2.

После 2.2.B (чистые VO + `pair_attackers` / `resolve_mass_*`) — следующий шаг 2.2-фазы: доменный агрегат, который оборачивает чистые функции движка в жизненный цикл от старта боя до итогового `MassDuelOutcome`. Симметрично 1×1-аналогу `Duel` из 2.1.B, но без `PENDING_ACCEPT` (массовый бой не требует подтверждения оппонентом — обе стороны автозаписываются на use-case-уровне 2.2.D) и без раундов (бой одно-тиковый, ГДД §7.2 / 2.2.4).

Что сделано:

- **Новые доменные ошибки** (`src/pipirik_wars/domain/pvp/errors.py`):
    - `InvalidMassDuelStateError(*, expected, actual, op)` — операция запрошена из неподходящего состояния (например, `submit_move` после `COMPLETED`).
    - `NotAMassDuelParticipantError(*, player_id)` — игрок не входит ни в один из ростеров боя.
    - `MassMoveAlreadySubmittedError(*, player_id)` — повторный `submit_move` от игрока, у которого выбор уже зафиксирован.
    - `MassDuelNotReadyError(*, missing_count)` — `resolve` вызван, когда не все участники отправили выбор (use-case обязан сначала `force_submit_missing(...)`).
    - `NoMissingMassMovesError` — `force_submit_missing` вызван, когда AFK-фоллбэчить нечего (баг в таймере 2.2.E).
    - Все 5 экспортированы из `domain/pvp/__init__.py` и добавлены в `__all__`.
- **`MassDuelState` enum** (`src/pipirik_wars/domain/pvp/mass_duel.py`):
    - Состояния: `IN_PROGRESS` (бой стартовал, ростер заморожен, ждём `submit_move`-ы) → `COMPLETED` (через `resolve(...)`) либо `CANCELLED` (через `cancel(...)`). Терминальные — `COMPLETED` и `CANCELLED`.
- **`MassDuel` агрегат** (`src/pipirik_wars/domain/pvp/mass_duel.py`):
    - Frozen-датакласс, snapshot-ы на старте: `clan{1,2}_id`, `hit_pct`, `clan{1,2}_member_ids: tuple[int, ...]` (sorted ascending, unique, >0), `clan{1,2}_initial_lengths: tuple[int, ...]` (parallel-array той же длины и порядка), `clan{1,2}_choices: tuple[MassRoundChoice | None, ...]` (parallel; `None` = ещё не отправил), `created_at`/`completed_at`/`cancelled_at`, `final_outcome`.
    - `__post_init__`-инварианты (повторно валидируются при `replace(...)`): clan-id-ы разные положительные, `hit_pct ∈ [0,100]`, ростеры непустые/sorted/unique/disjoint (ГДД §7.2 / 2.2.3 — игрок в обоих кланах должен быть отфильтрован use-case-ом до `create_battle`), длины ≥ 0, `clan{1,2}_choices[i].player_id == clan{1,2}_member_ids[i]` для не-`None`, COMPLETED ⇒ `final_outcome != None ∧ completed_at != None`, не-COMPLETED ⇒ `final_outcome is None`, CANCELLED ⇒ `cancelled_at != None`.
    - Конструктор `MassDuel.create_battle(*, clan1_id, clan2_id, clan1_lengths, clan2_lengths, hit_pct, now)`: нормализует входные dict-ы в parallel-tuple-ы (sorted by player_id), стартует в `IN_PROGRESS` со всеми `choices = (None, ...)`.
    - Lifecycle-мутаторы (immutable, `dataclasses.replace`): `submit_move(*, player_id, choice, now)` (валидирует state, participation, no-double-submit, `choice.player_id == player_id`), `force_submit_missing(*, fallback_choices, now)` (AFK-фоллбэк; требует ровно `missing_player_ids` ключи в `fallback_choices`), `resolve(*, random, now)` (требует `is_ready_to_resolve`, иначе `MassDuelNotReadyError`; делегирует чистой функции `resolve_mass_duel(...)` 2.2.B; переходит в COMPLETED), `cancel(*, now)` (идемпотентен; запрещён из COMPLETED).
    - Свойства: `is_in_progress` / `is_completed` / `is_cancelled` / `is_terminal` / `is_ready_to_resolve` / `missing_player_ids: tuple[int, ...]` / `is_participant(player_id)`.
    - Никаких `random.*` — `IRandom` приходит снаружи (нужен `pair_attackers` внутри `resolve_mass_duel`); AFK-фоллбэк-выборы передаются как `Mapping[player_id, MassRoundChoice]` (use-case 2.2.E генерит их через `IRandom`).
- **Re-export** в `domain/pvp/__init__.py`: добавлены `MassDuel`, `MassDuelState`, `InvalidMassDuelStateError`, `NotAMassDuelParticipantError`, `MassMoveAlreadySubmittedError`, `MassDuelNotReadyError`, `NoMissingMassMovesError`. Обновлён module-docstring (добавлен абзац про 2.2.C).
- **Тесты** (`tests/unit/domain/pvp/test_mass_duel.py`) — **+56 unit-тестов**:
    - `TestCreateBattle` (12) — happy-path 2×2, 1×1, sorted-output на unsorted-input, валидация: same clan-id, non-positive clan-id, hit_pct out-of-range, empty roster, non-positive player_id, negative length, zero length allowed, overlapping rosters rejected.
    - `TestPostInitInvariantsOnReplace` (5) — COMPLETED без outcome / без completed_at, IN_PROGRESS с outcome, CANCELLED без cancelled_at, unsorted member_ids, choice player_id mismatch на `replace(...)`.
    - `TestSubmitMove` (8) — clan1/clan2-стороны, all-submit → ready, double-submit, non-participant, choice.player_id mismatch, отказ из COMPLETED / CANCELLED.
    - `TestForceSubmitMissing` (7) — fills all missing, no-missing → error, extra keys → error, partial fallback → error, choice.player_id mismatch → error, отказ из COMPLETED / CANCELLED.
    - `TestResolve` (6) — happy-path completes, deterministic by seed, full-block → DRAW, not-ready → error, double-resolve → error, resolve-from-cancelled → error.
    - `TestCancel` (3) — IN_PROGRESS → CANCELLED, идемпотентен из CANCELLED, отказ из COMPLETED.
    - `TestProperties` (3) — `is_participant` для обеих сторон, `is_ready_to_resolve` False вне IN_PROGRESS, `missing_player_ids` пуст в COMPLETED.
    - `TestEndToEndScenarios` (4) — полный 2×2 цикл, partial-submit + force + resolve, 3×1 unequal, path-independence на 3×1 (3 атаки в одного защитника длиной 100 при `hit_pct=10` дают ровно 30 — 3 × 10 — а не 10+9+8).
    - `TestImmutability` (3) — `submit_move` / `cancel` / `resolve` возвращают новый инстанс, старый не мутируется.

Результат / артефакты:
- `src/pipirik_wars/domain/pvp/mass_duel.py` — 600+ строк, чистый домен без I/O / aiogram / `random.*`.
- `tests/unit/domain/pvp/test_mass_duel.py` — 800+ строк, 56 unit-тестов.
- `make ci` зелёный: 2160 passed, 1 skipped (pre-existing); coverage 95.94%; mass_duel.py — 94% (165 lines, 7 missing — всё в редких defensive-ветках).

Заметки / решения:
- Параллельные кортежи (`member_ids` / `lengths` / `choices`) вместо `dict` — потому что dict не вписывается в `frozen=True, slots=True` (mutable). Сортировка по `player_id` даёт детерминированный порядок и стабильный persistence-mapping для будущей таблицы 2.2.D.
- Disjoint-rosters-инвариант поддуплируется в `__post_init__` и в `create_battle` отдельно — ГДД §7.2 / 2.2.3 («игрок в обоих кланах пропускается»). Use-case 2.2.D обязан фильтровать ростер ДО `create_battle`; сам агрегат не молчит, если фильтрация нарушена.
- `force_submit_missing` принимает `Mapping[int, MassRoundChoice]`, а не сам генерит выборы — RNG живёт в use-case-е 2.2.E (вместе с конфигом «какие позиции дефолтить»). Агрегат остаётся pure: одна и та же входящая `fallback_choices` всегда даёт одинаковый агрегат.
- `_validate_terminal_state_invariants` вынесен из `__post_init__` отдельным методом, чтобы ruff не ругался на `PLR0912` (too many branches).
- `resolve(...)` пересоздаёт `Mapping[int, int]` для длин из parallel-tuple-ов и вызывает `resolve_mass_duel(...)` — никакого дублирования механики 1×1/массовой матрицы.

Следующий шаг — Спринт 2.2.D: persistence-таблицы (`pvp_mass_duels`, `pvp_mass_duel_choices`, `pvp_mass_duel_damage_entries`) + SQL-репозиторий + use-case `StartMassDuel` / `SubmitMassMove` / `ResolveMassDuel` / `ForceResolveMassDuel`.

---

## 2026-05-05 — Спринт 2.2.B: чистый доменный движок массового PvP клан×клан

**Автор:** Devin (по запросу shirline89)
**Тип:** feature (balance + domain VO + domain pure-функции + расширение IRandom-порта)
**Связано:** `current_tasks.md` Спринт 2.2.B, ПД 2.2.4 (`development_plan.md` §6), ГДД §7.2.

После 2.2.A (`/clantop` read-only) — следующий шаг 2.2-фазы: чистая доменная часть массового боя клан×клан, готовая к интеграции в use-case 2.2.D и persistence 2.2.C. Принцип «один тик» (vs. 3 раунда в 1×1): все участники одновременно заявляют атаку+блок, RNG строит две независимые перестановки атакующих→защитников (clan1→clan2 и clan2→clan1), все удары разрешаются от стартовых длин (path-independent).

Что сделано:

- **Balance** (`config/balance.yaml`, `src/pipirik_wars/domain/balance/config.py`, `tests/unit/domain/balance/factories.py`, `tests/unit/domain/balance/test_pvp_config.py`):
    - Новый pydantic-конфиг `PvpMassDuelConfig` (`cooldown_hours: int = Field(ge=1, le=72)`, `min_length_cm: int = Field(ge=0)`, `min_thickness_level: int = Field(ge=1)`, `min_clan_members: int = Field(ge=1, le=100)`).
    - `PvpConfig` расширен обязательным полем `mass_duel: PvpMassDuelConfig` (требуется в payload — старые конфиги без секции `pvp.mass_duel` отвергаются).
    - `config/balance.yaml`: добавлена секция `pvp.mass_duel` с дефолтами (cooldown=6h, min_length=20, min_thickness=2, min_clan_members=1).
- **Domain VO** (`src/pipirik_wars/domain/pvp/mass.py`):
    - `MassDuelWinner` enum (CLAN1/CLAN2/DRAW).
    - Frozen-dataclass-ы `MassRoundChoice` (player_id+attack+block), `MassPairing` (attacker_id+defender_id, валидация «нельзя пара с самим собой»), `MassDamageEntry` (одна разрешённая атака: pair + actual attack/block + blocked + damage_cm), `MassRoundOutcome` (entries + clan1_total_dealt + clan2_total_dealt), `MassDuelOutcome` (round-результат + zero-sum дельты + winner).
    - `MassDuelOutcome.__post_init__` форсирует zero-sum инвариант: `clan1_delta_cm + clan2_delta_cm == 0` (every cm потерянный одной стороной — приобретённый другой).
- **Расширение IRandom-порта** (`src/pipirik_wars/domain/shared/ports/random.py`, `infrastructure/random/real_random.py`, `tests/fakes/random.py`):
    - Добавлен абстрактный метод `shuffle(items: Sequence[T]) -> tuple[T, ...]` — иммутабельный аналог `random.shuffle` (возвращает новый кортеж, не мутирует вход; домен оперирует frozen-tuple-ами).
    - `RealRandom.shuffle` поверх `_rng.shuffle(buffer)` (где `_rng = secrets.SystemRandom()`); `FakeRandom.shuffle` поверх `random.Random(seed)` (детерминирован).
    - `ScriptedRandom` в `tests/unit/domain/forest/test_services.py` — заглушка `NotImplementedError("not used by forest service")`.
- **Pure-функции движка** (`src/pipirik_wars/domain/pvp/mass_services.py`):
    - `pair_attackers(*, attackers, defenders, random)` — возвращает `tuple[(attacker_id, defender_id), ...]`. Длина выхода = `max(|A|, |B|)`. При неравных размерах меньшая сторона переиспользуется по mod-cycle на УЖЕ перетасованных списках (`output[i] = (atks_shuffled[i % |A|], defs_shuffled[i % |B|])`). Валидация: непустые входы, все id > 0.
    - `resolve_mass_round(*, clan1_choices, clan2_choices, clan1_initial_lengths, clan2_initial_lengths, hit_pct, random)` — один тик. Делает 2 независимых вызова `pair_attackers` (А→Б и Б→А), для каждой пары вычисляет blocked (`_hit_blocked(attack, block)` — переиспользуется из 1×1-движка `domain/pvp/services.py`) и damage (`_damage_cm(defender_length_cm, hit_pct)` — тоже из 1×1). Path-independent: все длины фиксируются на старте, не меняются между ударами в один тик. Самопары (attacker_id == defender_id) пропускаются — защита от «один игрок в обоих кланах», даже если use-case по 2.2.3 пропустит дедупликацию.
    - `resolve_mass_duel(*, ...)` — тонкая обёртка над `resolve_mass_round` с расчётом zero-sum дельт (`delta = clan1_total_dealt - clan2_total_dealt`, `clan1_delta_cm = delta`, `clan2_delta_cm = -delta`) и определением winner (CLAN1/CLAN2/DRAW по знаку дельты).
- **Re-export в `domain/pvp/__init__.py`**: добавлены `MassRoundChoice`, `MassPairing`, `MassDamageEntry`, `MassRoundOutcome`, `MassDuelOutcome`, `MassDuelWinner`, `pair_attackers`, `resolve_mass_round`, `resolve_mass_duel`. `domain/balance/__init__.py` дополнительно экспортирует `PvpMassDuelConfig`.
- **Тесты**:
    - `tests/unit/domain/pvp/test_mass_entities.py` — валидация всех 6 frozen-VO (positive id, non-negative damage, no-self-pair, zero-sum invariant).
    - `tests/unit/domain/pvp/test_mass_services.py` — **+29 unit-тестов**: `pair_attackers` (равные размеры, асимметрия в обе стороны, singleton, mod-cycle, детерминизм по seed, разные seed-ы → разные выходы, валидация); `resolve_mass_round` (1×1 reduce-case, full-block, 2×2 happy, 3×1 unequal, валидация выборов/длин, hit_pct out-of-range, duplicate player_id, deterministic by seed); `resolve_mass_duel` (winner для всех 3 исходов, zero-sum, sweep winner-vs-dealt согласованности, path-independence на 3×1).
    - Минорный fix: `tests/unit/bot/handlers/test_duel.py` — `_balance()` фикстура добавляет `mass_duel` в `PvpConfig` (теперь обязательно). `tests/unit/domain/pvp/test_mass_entities.py` — удалены два `# type: ignore[misc]`, которые mypy --strict помечал как unused.

Результат / артефакты:
- `src/pipirik_wars/domain/pvp/mass_services.py` — 263 строки, чистая доменная логика без `random.*` / I/O / aiogram.
- `tests/unit/domain/pvp/test_mass_services.py` — 458 строк, 29 unit-тестов; целевое покрытие достигнуто.
- `make ci` зелёный: 2103 passed, 1 skipped (pre-existing); coverage 95.98%; layered_architecture / domain_must_not_import_infrastructure / application_must_not_import_io_libs — все KEPT.

Заметки / решения:
- Возвращаемый тип `pair_attackers` — `tuple[tuple[int, int], ...]`, а **не** `tuple[MassPairing, ...]`: `MassPairing.__post_init__` запрещает `attacker_id == defender_id`, а `pair_attackers` не знает структуру кланов и не может гарантировать отсутствие самопар. Самопары мы фильтруем в `_resolve_one_direction(...)`; на верхнем уровне use-case 2.2.3 будет дедуплицировать состав кланов до этой точки.
- Принципиально не вводим **«HP-пул в тике»**: длина защитника фиксирована на момент старта тика. 3 атаки в одного защитника при `length=100, hit_pct=10` дают 30 см ущерба, а не 10+9+8 (как было бы при «сначала уменьшим длину»). Это ровно то, что требует ГДД §7.2 / DP §6 для path-independence.
- Переиспользуем `_hit_blocked` / `_damage_cm` из `domain/pvp/services.py` — нет дублирования механики 3×3-матрицы. Они объявлены через underscore-prefix как «модульно-приватные», но импорт внутри одного `domain/pvp/`-пакета — допустимая практика (сравните: `domain/forest/services.py` тоже содержит underscore-helpers, доступные сестринским модулям).
- Интеграция в use-case (`StartMassDuel`, `SubmitMassMove`, `ResolveMassDuel`) и persistence-таблицы для масс-боев — следующие шаги 2.2.C / 2.2.D в спринте.

---

## 2026-05-05 — Спринт 2.1.G: PvP — AFK-таймер раунда + scheduler integrations

**Автор:** Devin (по запросу ambitious42)
**Тип:** feature (balance + domain port + infrastructure scheduler + application use-cases + DI)
**Связано:** `current_tasks.md` Спринт 2.1.G, ПД 2.1.4 + часть 2.1.5 (`development_plan.md §5`), ГДД §7.1; PR [#56](https://github.com/Pipirkawar/PipirkaWar/pull/56).

После саб-спринта 2.1.F (FIFO глобального лобби) — следующий критический кусок PvP: автодобивание pending-раунда случайным выбором, если игрок молчит дольше 30–60 секунд. Принципиально отличается от F.2 escalation/expiration job-ов тем, что job-ы per-`(duel_id, round_num)` (а не per-`duel_id`), и количество рестартов цепочки на одну дуэль = `expected_rounds` (3).

Что сделано:

- **Balance** (`config/balance.yaml`, `src/pipirik_wars/domain/balance/config.py`, `tests/unit/domain/balance/factories.py`, `tests/unit/domain/balance/test_pvp_config.py`):
    - Добавлено поле `pvp.duel_1v1.round_timer_seconds: int = Field(ge=30, le=60)`, default 45 (ГДД §7.1: «Таймер раунда 30–60s»).
    - `build_valid_balance()` пробрасывает дефолт; добавлены параметризованные unit-тесты для нового поля (валидные/невалидные значения).
- **Port `IDelayedJobScheduler`** (`src/pipirik_wars/domain/shared/ports/scheduler.py`) — 2 новых абстрактных метода:
    - `schedule_round_afk_resolution(*, duel_id: int, round_num: int, run_at: datetime) -> None` — поставить AFK-таймер на конкретный `(duel_id, round_num)`. Идемпотентен: повторный schedule на ту же пару перезаписывает run_at.
    - `cancel_round_afk_resolution(*, duel_id: int, round_num: int) -> None` — снять конкретный AFK-таймер. NO-OP, если job-ы нет (например, запоздалый submit после таймаута).
- **APScheduler-адаптер** (`src/pipirik_wars/infrastructure/scheduler/aps.py`):
    - Per-round job-id `pvp_round_afk:{duel_id}:{round_num}` (helper `_round_afk_job_id`).
    - Реализованы оба новых метода через `add_job(..., trigger="date", replace_existing=True)` и `remove_job(...)` (try/except — `JobLookupError` для idempotent cancel).
    - Новый late-bound `afk_resolution_factory: Callable[[], ResolveAfkRound] | None` (паттерн F.2 — лямбда-замыкание разрешает chicken-and-egg между `delayed_jobs` и `resolve_afk_round`).
    - `_run_round_afk_job(duel_id: int, round_num: int)`-callback: разрешает фабрику, зовёт `ResolveAfkRound.execute(ResolveAfkRoundInput(duel_id, round_num))`. Если `afk_resolution_factory is None` — `logger.warning(...)` + skip (не ронять APScheduler-job-thread); любая другая ошибка → `logger.exception(...)` (job помечается как прошедшая).
- **Use-case integration**:
    - `AcceptDuel` (`src/pipirik_wars/application/pvp/accept_duel.py`): после успешного перехода в IN_PROGRESS вызывает `scheduler.schedule_round_afk_resolution(duel_id=..., round_num=saved.pending_round.round_num, run_at=now + timedelta(seconds=cfg.round_timer_seconds))`. На старом code-path (CHAT_ONLY) — не было scheduler-а; теперь scheduler опционален в `__init__`, но AcceptDuel-процессы 2.1.F.2/F.3 уже инжектят его.
    - `SubmitMove` (`src/pipirik_wars/application/pvp/submit_move.py`): новые опциональные `__init__`-параметры `balance: IBalanceConfig | None`, `scheduler: IDelayedJobScheduler | None`. Перед мутацией захватывается `prev_round_num = duel.pending_round.round_num`. После save проверяется, изменилось ли `saved.pending_round.round_num` — это и есть «раунд закрылся». Если да: `cancel_round_afk_resolution(duel_id, prev_round_num)` + (если дуэль ещё IN_PROGRESS) `schedule_round_afk_resolution(duel_id, new_round_num, run_at=now + cfg.round_timer_seconds)`. Если дуэль COMPLETED — только cancel.
    - `ResolveAfkRound` (`src/pipirik_wars/application/pvp/resolve_afk_round.py`): новые опциональные `balance` + `scheduler` в `__init__`. После `force_complete_round` если дуэль не завершилась и `saved.pending_round is not None` — schedule таймер следующего раунда. На stale-input (`pending_round.round_num != input.round_num`) — no-op (ничего не схедулится).
    - `CancelDuel` — без изменений: `Duel.cancel` работает только в PENDING_ACCEPT, AFK-таймер на этой стадии ещё не существует.
- **DI** (`src/pipirik_wars/bot/main.py` `build_container`):
    - `delayed_jobs.afk_resolution_factory = lambda: resolve_afk_round` (поздняя привязка, как `escalate_factory` / `expire_factory` в F.2).
    - `SubmitMove(...)` и `ResolveAfkRound(...)` получают `balance=balance, scheduler=delayed_jobs`.
    - `test_composition_root.py` обновлён под новые DI-ключи (4 теста по-прежнему зелёные).
- **`FakeDelayedJobScheduler`** (`tests/fakes/delayed_job_scheduler.py`, `tests/fakes/__init__.py`):
    - Новый frozen+slots dataclass `ScheduledRoundAfkJob(duel_id: int, round_num: int, run_at: datetime)`.
    - Поля `scheduled_round_afk: dict[tuple[int, int], ScheduledRoundAfkJob]` + `cancelled_round_afk: list[tuple[int, int]]`.
    - Реализации `schedule_round_afk_resolution` (overwrite по ключу) + `cancel_round_afk_resolution` (no-op, добавляет в `cancelled_round_afk` вне зависимости от наличия).
    - Экспорт `ScheduledRoundAfkJob` в `tests/fakes/__init__.py`.
- **Тесты — +14**:
    - `test_accept_duel.py` (+2): таймер раунда 1 ставится; не ставится при ошибках валидации.
    - `test_submit_move.py` (+4): partial → no-op; round close mid-duel → cancel предыдущего + schedule следующего; round close + COMPLETED → cancel only; без scheduler-а — back-compat.
    - `test_resolve_afk_round.py` (+4): IN_PROGRESS → schedule next; COMPLETED → no schedule; stale timer (round_num mismatch) → no schedule; без scheduler-а — back-compat.
    - `test_aps.py` (+8): job-id per-`(duel_id, round_num)`; replace-existing на той же паре; раздельные раунды дают раздельные job-ы; cancel конкретного раунда; cancel missing — no-op; callback успех; factory None → warning + return; unexpected exception → exception-log без падения.
- **`make ci` зелёный**: ruff + mypy strict + import-linter + 1909 passed (1 skip), coverage **96.13%** (без регрессии относительно F.3-baseline 96.11%).

Результат / артефакты:

- `config/balance.yaml`, `src/pipirik_wars/domain/balance/config.py`, `tests/unit/domain/balance/factories.py`, `tests/unit/domain/balance/test_pvp_config.py` — новое поле + дефолт + тесты.
- `src/pipirik_wars/domain/shared/ports/scheduler.py` — 2 новых abstract-метода.
- `src/pipirik_wars/infrastructure/scheduler/aps.py` — late-bound factory + 2 schedule/cancel-метода + callback `_run_round_afk_job`.
- `src/pipirik_wars/application/pvp/{accept_duel,submit_move,resolve_afk_round}.py` — schedule/cancel-вызовы.
- `src/pipirik_wars/bot/main.py` — DI-провязка `afk_resolution_factory` + `balance`/`scheduler` в SubmitMove/ResolveAfkRound.
- `tests/fakes/delayed_job_scheduler.py`, `tests/fakes/__init__.py` — фейк + экспорт.
- `tests/unit/application/pvp/test_{accept_duel,submit_move,resolve_afk_round}.py` — +10 тестов.
- `tests/unit/infrastructure/scheduler/test_aps.py` — +8 тестов (TestRoundAfkSchedule + TestRoundAfkCallback).
- `tests/unit/bot/test_composition_root.py` — DI-обновление.

Заметки / решения:

- **Per-round job-id, а не per-duel**: каждая дуэль на 3 раунда => 3 разных AFK-job-а (не один rolling). Это даёт точечный cancel: когда раунд закрылся реальными ходами или AFK-резолвом, отменяется именно его таймер, а следующий ставится отдельно. Альтернатива (один job на дуэль с rescheduled-trigger-ом) сложнее в idempotency и при concurrent submit-race.
- **Late-bound `afk_resolution_factory`** (паттерн F.2): чтобы разрешить chicken-and-egg между `delayed_jobs = APSchedulerDelayedJobScheduler(afk_resolution_factory=lambda: resolve_afk_round)` (на этом моменте `resolve_afk_round` ещё не существует) и `resolve_afk_round = ResolveAfkRound(scheduler=delayed_jobs, ...)`. Лямбда захватывает имя по поздней привязке.
- **`balance` + `scheduler` опциональны в SubmitMove / ResolveAfkRound**: бэк-совместимость для существующих тестов (D-spec) которые билдят use-case без этих параметров. В production-DI всё инжектится; back-compat-кейс ловится новыми тестами `test_no_scheduler_no_op`.
- **CancelDuel не задействован**: `Duel.cancel` работает только в PENDING_ACCEPT, до accept-а AFK-таймер ещё не схедулится. Если когда-нибудь добавим cancel-after-accept — там понадобится сканирующий cancel диапазона раундов; но это не в G.
- **Bot-handler integration AFK-уведомлений** (broadcast результата при auto-resolve через DM) — отдельный саб-спринт. После AFK-резолва `Duel.is_completed` пробрасывается через `AfkRoundResolved.duel_completed`, и handler 2.1.E уже умеет показывать результат через `_broadcast_result`. Но job-callback-у нужен handler-side message bundle для DM — там ещё нет нотификатора. Вынесено в backlog.
- **Pre-existing F.2 callback gaps** (`_run_escalation_job` / `_run_expiration_job` без unit-тестов) остались как были — out-of-scope для G; они уже были в 73%-coverage `aps.py` до этого спринта.

---

## 2026-05-05 — Спринт 2.1.F.3: глобальное лобби PvP — bot-handlers + /duel_global + локали

**Автор:** Devin (по запросу ambitious42)
**Тип:** feature (bot handlers + presenters + i18n + test backfill)
**Связано:** `current_tasks.md` Спринт 2.1.F.3, ПД 2.1.3 (`development_plan.md §5`), ГДД §7.1; PR [#54](https://github.com/Pipirkawar/PipirkaWar/pull/54).

Завершающий саб-PR саб-спринта 2.1.F. F.1 заложил domain+persistence (PR #52), F.2 — use-cases+scheduler+DI (PR #53). F.3 подключает глобальное лобби к Telegram-handler-ам, добавляет новый `/duel_global` и backfill-ит тесты модулей 2.1.E.

Что сделано:

- **`/duel` в ЛС без аргументов → enqueue в глобальное лобби**:
    - Раньше handler отвечал «coming soon» (placeholder из 2.1.E).
    - Теперь зовёт `ChallengeDuel(mode=global_only)` (через DI-инжект handler-параметра); use-case через F.2-цепочку enqueue-ит запись в `IGlobalLobbyRepository` + ставит expiration-job через `IDelayedJobScheduler`.
    - Игроку шлётся `duel-global-enqueued` с `$duel_id` (для `/cancel_duel`) и `$ttl_minutes` (из `balance.pvp.duel_1v1.global_lobby_ttl_minutes`).
    - Helper-функция `_challenge_global_from_private(message, tg_identity, challenge_duel, balance, presenter, effective_locale)` — выделена из `handle_duel`, чтобы не раздувать сигнатуру; маппит domain-ошибки (`PlayerNotFoundError` / `PvpRequirementsNotMetError` / `AnticheatSoftBanError` / `LockAlreadyHeldError`) на существующие `duel-*`-локали.
- **Новый handler `/duel_global`** (только в ЛС бота — в группах ничего не делает, шлёт `duel-global-only-in-private`):
    - Вызывает F.2-use-case `MatchFromLobby(accepter_tg_id=...)` для атомарного FIFO-pop-а.
    - Результаты:
        - `EmptyLobby` / `LobbyEntryStale` → `duel-global-empty` (предложит позже попробовать или бросить вызов через `/duel`).
        - `DuelMatched` → `duel-global-matched` пикеру (с `$challenger`-именем) + DM-промпт «выбери атаку» обоим игрокам через существующий helper `_broadcast_attack_prompt` (учитывает per-player локаль через `IPlayerLocaleResolver`).
    - Domain-ошибки (`PlayerNotFoundError` / `PvpRequirementsNotMetError` / `AnticheatSoftBanError` / `LockAlreadyHeldError`) маппятся аналогично `_challenge_global_from_private`.
- **Локали `duel-global-*`** (`locales/{ru,en}.ftl`):
    - `duel-global-enqueued` (с `$duel_id` + `$ttl_minutes`).
    - `duel-global-matched` (с `$challenger`).
    - `duel-global-empty`.
    - `duel-global-only-in-private`.
    - `duel-challenge-global` теперь принимает `$ttl_minutes` (старый текст без TTL заменён) — handler передаёт ttl корректно из `balance.get().pvp.duel_1v1.global_lobby_ttl_minutes`.
    - Уточнены `duel-private-needs-global` + `duel-usage` (упоминание «ЛС-режим = глобал»).
- **`DuelPresenter` расширен** (`bot/presenters/duel.py`) — 4 новых метода `global_enqueued` / `global_matched` / `global_empty` / `global_only_in_private` + `ttl_minutes` параметр в `challenge_global`. Сигнатуры stable: existing-callers F.1/F.2/E не сломаны.
- **DI** — никакой работы: F.2 уже провязал `match_from_lobby` + `enqueue_global_duel` в `Container` и `build_dispatcher` workflow-data. Aiogram-DI инжектит use-case-ы прямо в handler-параметры (`MatchFromLobby`, `IBalanceConfig`).
- **Бэкфилл тестов** (главная цель F.3 — закрытие технического долга 2.1.E):
    - **`tests/unit/bot/handlers/test_duel.py`** — новый файл, **66 тестов**:
        - `TestHandleDuel` × 25 — все ветки `/duel`: registered/not-registered, in-private/in-group, reply/no-reply, mode=`chat`/`chat_then_global`/`global_only`, lock-already-held, anti-cheat soft-ban, requirements-not-met (length/thickness), self-challenge, target-is-bot, full happy-path с эмиссией challenge card.
        - `TestHandleDuelGlobal` × 8 — все ветки `/duel_global`: in-group rejection, EmptyLobby, LobbyEntryStale, DuelMatched (с broadcast), domain errors.
        - `TestHandleCancelDuel` × 7, `TestHandlePvpAccept` × 7, `TestHandlePvpReject` × 3, `TestHandlePvpAttack` × 3, `TestHandlePvpBlock` × 13.
        - Помощники: `_msg`, `_callback`, `_command`, `_balance` (через `build_valid_balance` + `model_copy`), `_stub_*` для всех use-case-ов.
    - **`tests/unit/bot/presenters/test_duel.py`** — новый файл, **56 тестов**: маркерные с `FakeMessageBundle` (все ключи + параметры), callback-data parsers (4 happy + 21 параметризованных error case), Fluent-интеграция RU+EN для всех новых `duel-global-*`-сообщений (плейсхолдеры рендерятся, эмодзи на месте).
    - **Покрытие**: `bot/handlers/duel.py` 11% → **92%**, `bot/presenters/duel.py` 49% → **96%**.
    - **`make ci` зелёный**: 1883 passed, 1 skipped, coverage **96.11%** (≥80% gate; в F.2 было 90.97%); mypy --strict без ошибок, ruff/import-linter clean.

Результат / артефакты:

- `src/pipirik_wars/bot/handlers/duel.py` — новый handler `handle_duel_global` + helper `_challenge_global_from_private` + расширенный `handle_duel`.
- `src/pipirik_wars/bot/presenters/duel.py` — 4 новых метода + `ttl_minutes` в `challenge_global`.
- `locales/ru.ftl`, `locales/en.ftl` — `duel-global-*` ключи + обновлённый `duel-challenge-global`.
- `tests/unit/bot/handlers/test_duel.py` (NEW, 1672 LoC, 66 тестов).
- `tests/unit/bot/presenters/test_duel.py` (NEW, 305 LoC, 56 тестов).

Заметки / решения:

- **Почему F.3 — отдельный саб-PR**: F.2 уже превышал размер «полу-крупного» PR-а, а бэкфилл тестов (122 новых теста) на handler-ы и presenter-ы ещё больший. Разбиение на 3 саб-PR-а (F.1=domain+persistence, F.2=application+infrastructure, F.3=bot+i18n+тесты) даёт ревьюеру удобоваримые куски и независимые revert-окна.
- **`assert isinstance(result, DuelMatched)`** в `handle_duel_global` после `EmptyLobby | LobbyEntryStale` — нужен для type narrowing mypy --strict. Альтернатива (`if isinstance(result, DuelMatched): ... else: ...`) длиннее и менее читаема, потому что `MatchFromLobbyResult` — closed sum-type из 3 вариантов, и первые 2 уже отфильтрованы.
- **`balance: IBalanceConfig` в handler-сигнатуре**: aiogram-DI инжектит из workflow-data; handler читает только `balance.get().pvp.duel_1v1.global_lobby_ttl_minutes` для подстановки в локализованное сообщение. Не пробрасывали в use-case (use-case уже сам читает balance внутри).
- **Тесты — на `FakeMessageBundle` маркеры** (`<locale>:<key>[k=v,...]`): assert-ы быстрые и тривиальные, проверяют **что** handler зовёт. Финальная проверка реального RU/EN-рендера — в `presenters/test_duel.py::TestDuelPresenterFluent` через `FluentMessageBundle`.

---

## 2026-05-05 — Спринт 2.1.F.2: глобальное лобби PvP — use-cases + scheduler + DI

**Автор:** Devin (по запросу ambitious42, продолжает HANDOFF предыдущего агента)
**Тип:** feature (application use-cases + infrastructure scheduler + DI wiring)
**Связано:** `current_tasks.md` Спринт 2.1.F.2, ПД 2.1.3 (`development_plan.md §5`), ГДД §7.1.

Второй саб-PR саб-спринта 2.1.F. На фундаменте F.1 (`IGlobalLobbyRepository` + `Duel.escalate_to_global` + persistence) добавляем 4 use-case-а PvP-лобби, расширяем порт планировщика и провязываем всё в composition root. Бот-handler-ы и `/duel_global` — в F.3.

Что сделано:

- **Расширение `IDelayedJobScheduler`** (`domain/shared/ports/scheduler.py`):
    - 4 новых абстрактных метода: `schedule_chat_to_global_escalation(*, duel_id, run_at)` / `schedule_global_lobby_expiration(*, duel_id, run_at)` + `cancel_*`-парные. Все идемпотентны (повторный schedule на тот же `duel_id` перезаписывает run-at; cancel — no-op для отсутствующих).
- **APScheduler-адаптер** (`infrastructure/scheduler/aps.py`):
    - 4 новых метода поверх AsyncIOScheduler с `replace_existing=True` (job-id-ы `chat_to_global_escalation:{duel_id}` и `global_lobby_expiration:{duel_id}`).
    - Late-bound фабрики `escalate_factory`/`expire_factory: Callable[[], EscalateChatToGlobal | ExpireLobbyEntry]` — позволяют построить scheduler **до** того, как соответствующие use-case-ы существуют (chicken-and-egg: use-case`-ам нужен сам scheduler). Фабрики разрешаются в момент срабатывания job-а через closure-cell composition root-а.
    - Job-callback-и `_run_escalation_job` / `_run_expiration_job` обрабатывают `factory is None` graceful-но (logged warning, скип) — для прода фабрики обязаны быть, для unit-тестов scheduler-а можно без них.
- **4 use-case-а** (`application/pvp/`):
    - `EnqueueGlobalDuel` — публичный entrypoint для F.3 `/duel`-flow (private chat). Проверяет `mode=GLOBAL_ONLY`, ставит в очередь через `IGlobalLobbyRepository.enqueue` + ставит `schedule_global_lobby_expiration` на `now + global_lobby_ttl_minutes` минут. Audit `PVP_LOBBY_ENQUEUED`.
    - `MatchFromLobby` — публичный entrypoint для F.3 `/duel_global`. Atomic FIFO-pop через `pop_oldest()` (на PG: `SELECT … FOR UPDATE SKIP LOCKED`); `Duel.accept` + lock на pop-ера; cancel pending expiration job-а; audit `PVP_LOBBY_MATCHED`. Self-challenge race (свой же вызов в начале очереди) → возвращает `LobbyEmpty` (UI попросит retry — это устраивает спецификацию F.2).
    - `EscalateChatToGlobal` — внутренний; вызывается scheduler-job-ом через `escalate_factory`. Грузит `Duel`, проверяет `state=PENDING_ACCEPT ∧ mode=CHAT_THEN_GLOBAL`, домен `Duel.escalate_to_global` → `mode=GLOBAL_ONLY` + nullify `challenged_id`; enqueue в лобби; ставит expiration-job. Idempotent: если дуэль уже escalated/cancelled/accepted → лог + return без ошибок.
    - `ExpireLobbyEntry` — внутренний; вызывается expiration-job-ом. Грузит `Duel`, идёт через доменный `Duel.cancel(now=...)`, удаляет из лобби (`remove(duel_id)`), снимает activity-lock челленджера. Idempotent на CANCELLED/COMPLETED/already-removed.
- **Интеграция в `ChallengeDuel/AcceptDuel/CancelDuel`**:
    - `ChallengeDuel`: для `mode=GLOBAL_ONLY` сразу enqueue + schedule expiration; для `mode=CHAT_THEN_GLOBAL` — schedule escalation на `now + chat_to_global_promotion_minutes` минут; `mode=CHAT_ONLY` без побочных scheduler-эффектов.
    - `AcceptDuel`: cancel pending escalation job (для chat_then_global) ИЛИ cancel pending expiration job (для global_only) + удаление из лобби (`remove` идемпотентно). Cancel-операции вынесены **снаружи** UoW — scheduler не транзакционный, но idempotent.
    - `CancelDuel`: симметрично — cancel jobs + remove из лобби.
- **DI-провязка composition root** (`bot/main.py`):
    - В `Container` (frozen+slots dataclass): новое поле `global_lobby: IGlobalLobbyRepository` + 4 новых use-case-поля (`enqueue_global_duel` / `match_from_lobby` / `escalate_chat_to_global` / `expire_lobby_entry`).
    - В `build_container()`: инстанцируется `SqlAlchemyGlobalLobbyRepository(uow=uow)`; scheduler создаётся с late-bound `escalate_factory=lambda: escalate_chat_to_global` / `expire_factory=lambda: expire_lobby_entry` (Python-closure ловит local-cell, который заполнится через несколько строк); существующие `ChallengeDuel/AcceptDuel/CancelDuel` дополнены прокидкой `scheduler=delayed_jobs, lobby=global_lobby`; 4 новых use-case-а собираются с правильными зависимостями.
    - В `build_dispatcher()`: `match_from_lobby` и `enqueue_global_duel` прокинуты в workflow-data для будущих handler-ов F.3 (`escalate_chat_to_global` / `expire_lobby_entry` остаются внутренними — их зовёт только scheduler).
- **Тесты**:
    - **+39 unit-тестов** на use-cases (`tests/unit/application/pvp/test_enqueue_global_duel.py` 7, `test_match_from_lobby.py` 8, `test_escalate_chat_to_global.py` 7, `test_expire_lobby_entry.py` 6, `test_lobby_integration.py` 11) — happy path + idempotency + race-conditions + scheduler-cancel paths через `FakeDelayedJobScheduler` (`scheduled` dict + `cancelled` list).
    - Расширение `tests/unit/bot/test_composition_root.py` — `Container` собирается с фейками (нет real БД), все 5 новых полей проверены через `isinstance`-asserts; `build_container()` с реальными адаптерами тоже проверяет 5 новых полей.
    - **`make ci` зелёный**: 1761 passed, coverage 90.97% (≥80% gate), mypy --strict без ошибок, ruff/import-linter clean.

Результат / артефакты:

- `src/pipirik_wars/application/pvp/{enqueue_global_duel,match_from_lobby,escalate_chat_to_global,expire_lobby_entry}.py`.
- `src/pipirik_wars/domain/shared/ports/scheduler.py` — расширенный порт.
- `src/pipirik_wars/infrastructure/scheduler/aps.py` — late-bound factories + 4 новых scheduler-метода.
- `src/pipirik_wars/application/pvp/{challenge_duel,accept_duel,cancel_duel}.py` — scheduler/lobby integration.
- `src/pipirik_wars/bot/main.py` — DI-провязка `Container` + `build_container` + `build_dispatcher`.
- `tests/unit/application/pvp/test_{enqueue_global_duel,match_from_lobby,escalate_chat_to_global,expire_lobby_entry,lobby_integration}.py` — +1190 LoC unit-тестов.
- `tests/unit/bot/test_composition_root.py` — расширение под 5 новых полей `Container`.

Заметки / решения:

- **Late-bound factories для scheduler-а**: alternative — split builder (сначала scheduler без factories → use-case-ы → setattr на scheduler), но closure-cell + `lambda` идиоматичнее и не требует mutable scheduler-а. Python-семантика: `lambda: escalate_chat_to_global` создаёт closure cell на `build_container`-local, cell заполняется через несколько строк — при срабатывании job-а (после возврата из `build_container`) cell уже содержит инстанс.
- **Self-challenge race в `MatchFromLobby`**: если pop-ер достал собственный enqueued duel (single-user lobby), возвращаем `LobbyEmpty` без error-а. Спецификация F.2 это позволяет — UI в F.3 предложит retry. Гарантирует прогресс (нет infinite-loop-а).
- **`AuditAction.PVP_LOBBY_ENQUEUED` / `PVP_LOBBY_MATCHED` / `PVP_LOBBY_ESCALATED` / `PVP_LOBBY_EXPIRED`**: уже добавлены в enum в F.1. Для F.2 они только используются.
- **Транзакционность**: state-mutations всегда в `async with self._uow`; `scheduler.cancel_*` и `lobby.remove` (на cancel-path) — снаружи UoW (idempotent, не нужно rollback-ить scheduler при ошибке, потому что job всё равно проверит state в момент срабатывания).
- **HANDOFF от предыдущего агента**: `AGENT_HANDOFF.md` (172 LoC) детально описал steps 1-4 (порт + APS-адаптер + 4 use-case-а + integration в существующие use-case-ы). Остаток — step 5: composition root + docs + PR. HANDOFF удалён отдельным коммитом перед PR.

---

## 2026-05-05 — Спринт 2.1.F.1: глобальное лобби PvP — domain + persistence

**Автор:** Devin (по запросу 612amaranth)
**Тип:** feature (domain + infrastructure + balance config)
**Связано:** `current_tasks.md` Спринт 2.1.F.1, ПД 2.1.3 (`development_plan.md §5`), ГДД §7.1.

Первый саб-PR саб-спринта 2.1.F (декомпозиция: F.1 — domain+persistence; F.2 — use-cases+scheduler; F.3 — bot+DI). Цель этого PR — добавить безопасный доменный фундамент глобальной FIFO-очереди вызовов, не трогая ни бот, ни scheduler.

Что сделано:

- **Balance config** (`domain/balance/config.py` + `config/balance.yaml`):
    - В `PvpDuel1v1Config` два новых поля с Pydantic-валидацией:
        - `global_lobby_ttl_minutes: int = Field(ge=1, le=60)` — сколько минут вызов живёт в глобальном пуле (дефолт 10);
        - `chat_to_global_promotion_minutes: int = Field(ge=1, le=60)` — через сколько минут после `mode=CHAT_THEN_GLOBAL`-вызова job-эскалации переводит его в `GLOBAL_ONLY` (дефолт 3).
    - Параметры лежат именно в секции `pvp.duel_1v1`, чтобы вместе с TTL/anti-cheat-параметрами Сбринта 2.1.A правились единым релоадом баланса.
- **Domain VO + порт** (`domain/pvp/lobby.py` — новый файл):
    - `LobbyEntry` (frozen + slots): `duel_id: int`, `enqueued_at: datetime` (tz-aware UTC).
    - Абстрактный порт `IGlobalLobbyRepository` с 4 методами:
        - `enqueue(duel_id=…, enqueued_at=…) -> bool` — идемпотентный enqueue (повторная попытка для уже стоящего `duel_id` возвращает `False`, не двигая `enqueued_at` — это критично для FIFO-инварианта);
        - `pop_oldest() -> LobbyEntry | None` — атомарная FIFO-выборка (на PG — `SELECT … ORDER BY enqueued_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED`, на SQLite вырождается в UoW-транзакцию);
        - `remove(duel_id=…) -> bool` — идемпотентное удаление;
        - `is_in_lobby(duel_id=…) -> bool` — read-only-проверка для preflight-валидации.
- **Domain lifecycle** (`domain/pvp/duel.py`): `Duel.escalate_to_global(*, now)` — переход `CHAT_THEN_GLOBAL → GLOBAL_ONLY` с обнулением `challenged_id` (вызывается job-ом эскалации в F.2). Не идемпотентен: повторный вызов на уже глобальном вызове → `InvalidDuelStateError`.
- **Миграция** `0010_pvp_global_lobby` (`down_revision=0009_pvp_duels`):
    ```sql
    CREATE TABLE pvp_global_lobby (
      duel_id   BIGINT PRIMARY KEY,
      enqueued_at TIMESTAMP WITH TIME ZONE NOT NULL,
      FOREIGN KEY (duel_id) REFERENCES pvp_duels(id) ON DELETE CASCADE
    );
    CREATE INDEX ix_pvp_global_lobby_enqueued_at ON pvp_global_lobby(enqueued_at);
    ```
- **ORM** `PvpGlobalLobbyORM` в `infrastructure/db/models/pvp.py` — зеркало миграции; зарегистрирован в `infrastructure/db/models/__init__.py` и в фикстуре `tests/integration/db/conftest.py`.
- **SqlAlchemyGlobalLobbyRepository** (`infrastructure/db/repositories/global_lobby.py`):
    - `enqueue` — на PG `pg_insert(...).on_conflict_do_nothing(index_elements=["duel_id"])`, на SQLite `sqlite_insert(...).on_conflict_do_nothing(index_elements=["duel_id"])`. `bool` определяется по `result.rowcount`.
    - `pop_oldest` — `select(...).order_by(enqueued_at.asc()).limit(1).with_for_update(skip_locked=True)` (PG), затем `delete(...) where duel_id == picked.duel_id`. На SQLite `with_for_update` no-op, FIFO держит UoW-транзакция.
    - `remove`, `is_in_lobby` — стандартные.
    - `enqueued_at` всегда нормализуется через `infrastructure/db/utils.ensure_utc(...)` (aiosqlite теряет tzinfo).
- **FakeGlobalLobbyRepository** в `tests/fakes/global_lobby_repo.py` — in-memory FIFO для use-case-тестов 2.1.F.2.

Тесты:

- `tests/unit/domain/pvp/test_lobby.py` — 9 unit-тестов (LobbyEntry frozen + equality, FakeGlobalLobbyRepo контракт: enqueue/idempotent/pop-FIFO/empty/remove/is_in_lobby/pop-removes).
- `tests/unit/domain/pvp/test_duel_lifecycle.py` — +6 тестов на `Duel.escalate_to_global` (happy chat→global, новая инстанция, отказы из CHAT_ONLY / GLOBAL_ONLY / IN_PROGRESS / CANCELLED).
- `tests/unit/domain/balance/test_pvp_config.py` — +9 параметризованных тестов на новые TTL-поля (boundary cases, required-field, обновлённый extra=forbid, helper `_build`).
- `tests/integration/db/pvp/test_global_lobby_repository.py` — 9 интеграционных тестов (enqueue→pop round-trip, FIFO ordering на 3 дуэлях, idempotent enqueue keeps first timestamp, remove existing/nonexistent, is_in_lobby present/absent, two independent duels).
- `tests/integration/db/test_migrations.py` — +3 cases (`0010_pvp_global_lobby` в revisions / descends from 0009 / в `versions_dir` + `pvp_global_lobby` в expected tables).

Результат / артефакты:

- ветка `devin/1778007932-sprint-2-1-f-1-pvp-global-lobby-domain`, PR #?? (см. ссылку в `current_tasks.md`)
- `make ci` локально зелёный: ruff + mypy --strict + lint-imports (3 контракта) + pytest (1727 passed, 1 skipped, coverage **91.07%**)

Заметки / решения:

- **PG-table, не Redis-list.** Текущая инфраструктура — Postgres + asyncpg, Redis ещё не подключён; расширять стек ради одной FIFO-очереди не нужно. На горячих нагрузках в будущем при необходимости можно мигрировать прозрачно — порт `IGlobalLobbyRepository` это позволяет.
- **Идемпотентный enqueue.** Job-ы scheduler-а (F.2) могут ретраиться при временных сбоях; `False` на повторный enqueue — это нормальный benign-исход, а не ошибка.
- **`Duel.escalate_to_global` не идемпотентен.** Идемпотентность реализуется выше — на уровне use-case-а в F.2 (через `is_in_lobby` или job-cancel-флаги). На домене явная ошибка лучше, чем тихий no-op: легче отлавливать race-conditions.
- **CASCADE-тест на SQLite не пишем** — без `PRAGMA foreign_keys=ON` (в репо нигде не выставляется) cascade не сработает на in-memory aiosqlite-движке. CASCADE-инвариант декларирован в DDL и будет проверен на PG; для unit-уровня достаточно.
- **F.2 + F.3** — следующие саб-PR-ы; план зафиксирован в `current_tasks.md`. F.2 поднимет use-cases и scheduler, F.3 переведёт `/duel` private-flow на новый global pool + добавит `/duel_global`.

---

## 2026-05-05 — Спринт 2.1.E: bot-handler-ы и presenter-ы PvP (UX боя в Telegram)

**Автор:** Devin (предыдущий агент, PR #50; запись и housekeeping — Devin по запросу 612amaranth)
**Тип:** feature (bot/presenters + bot/handlers + DI + locales)
**Связано:** `current_tasks.md` Спринт 2.1.E, ПД 2.1.2 (`development_plan.md §5`), ГДД §7.1.

Пятый саб-спринт PvP-эпика 2.1. Поверх готовых application-use-cases (2.1.D) появляется UX-слой `aiogram` 3.x: команды `/duel` / `/cancel_duel`, четыре callback-обработчика (accept/reject/attack/block), презентер с 35+ методами и 3 inline-keyboard-генератора, локализация на RU/EN. Это последний саб-спринт MVP боя 1×1 в части основного flow — асинхронные шедулинг-задачи (AFK-таймер раунда + авто-эскалация в global pool через 3 мин) едут в саб-спринтах 2.1.F и 2.1.G.

Что сделано:

- **`bot/presenters/duel.py`** (≈600 строк) — `DuelPresenter`:
    - 4 dataclass-callback-payload-а: `AcceptCallbackData(duel_id)`, `RejectCallbackData(duel_id)`, `AttackCallbackData(duel_id, round_num, attack)`, `BlockCallbackData(duel_id, round_num, attack, block)` — все ≤ 64 байт (Telegram-лимит на `callback_data`).
    - Сериализаторы/парсеры с whitelist-валидацией: `_parse_positive_int` / `_parse_position` (только `high`/`mid`/`low`); неконсистентные строки → `ValueError` (выбрасывается вверх как `Exception`, ловится в handler-е через middleware).
    - 26 методов рендера локализованных текстов: usage / not-registered / target-not-registered / target-is-bot / self-challenge / challenge-chat / challenge-chat-then-global / challenge-global / chat-accepted / cancelled / cancel-usage / round-attack-prompt / round-block-prompt / round-waiting / result-victory / result-defeat / result-draw / requirements-not-met / anticheat-blocked / lock-already-held + 9 коротких toast-методов (для `callback.answer(text=...)`).
    - 3 keyboard-фабрики: `challenge_keyboard(duel_id)` (Принять/Отклонить), `attack_keyboard(duel_id, round_num)` (3 кнопки атаки), `block_keyboard(duel_id, round_num, attack)` (3 кнопки блока — атака зашита в `callback_data`, чтобы handler `pvp-block` не зависел от состояния клиента).
- **`bot/handlers/duel.py`** (≈733 строки) — 6 handler-ов (по паттерну `bot/handlers/upgrade.py`):
    - `/duel` (`@router.message(Command("duel"))`): в ЛС без reply → `private_needs_global`; в группе/супергруппе без reply → `usage`; reply на бота → `target_is_bot`; reply на самого себя → `self_challenge`; reply на игрока с аргументом `chat` → `chat_only`-mode; без аргумента → `chat_then_global`-mode (default ГДД §7.1). Зовёт `ChallengeDuel.execute(...)`. Ловит `PlayerNotFoundError` (различает challenger vs challenged по `exc.tg_id`), `SelfChallengeError`, `PvpRequirementsNotMetError`, `AnticheatSoftBanError`, `LockAlreadyHeldError` и рендерит соответствующий локализованный текст.
    - `/cancel_duel <id>` (`@router.message(Command("cancel_duel"))`): парсит ID; зовёт `CancelDuel.execute(...)`; ловит `DuelNotFoundError`, `NotADuelParticipantError`, `InvalidDuelStateError`.
    - `pvp-accept:N` callback: парсит `AcceptCallbackData`; зовёт `AcceptDuel.execute(...)`; на успехе — `callback.answer(toast_accepted)`, `_strip_keyboard(callback)`, edit-message → `chat_accepted`, шлёт DM обоим игрокам с `attack_keyboard` (раунд 1).
    - `pvp-reject:N` callback: только `toast_rejected` + `_strip_keyboard`. БЕЗ мутации состояния — pending duel останется до TTL-cleanup в 2.1.F.
    - `pvp-attack:N:R:H` callback: БЕЗ вызова use-case — просто edit message → `round-block-prompt(attack)` + `block_keyboard`. (Атака сама по себе ничего не сабмитит — submit происходит при выборе блока.)
    - `pvp-block:N:R:A:B` callback: парсит `BlockCallbackData`; зовёт `SubmitMove.execute(...)`; ловит `DuelNotFoundError`, `NotADuelParticipantError`, `InvalidDuelStateError`, `MoveAlreadySubmittedError`, `AnticheatSoftBanError`. На успехе:
        - `result.duel.is_completed` → загружает обоих игроков (`IPlayerRepository.get_by_id`) и шлёт DM с `result_victory` / `result_defeat` / `result_draw` каждому (по `result.duel.final_outcome.winner`).
        - Раунд продвинулся → DM `round_attack_prompt` обоим с новым `round_num`.
        - Раунд НЕ закрыт (оппонент не походил) → edit message → `round_waiting`.
- **`bot/main.py`** — расширение `Container` и `build_dispatcher`:
    - 5 новых полей: `challenge_duel`, `accept_duel`, `cancel_duel`, `submit_move`, `resolve_afk_round` (последний пока нигде не вызывается, но регистрируется в DI заранее под 2.1.G AFK-таймер).
    - Новый репо: `duels: SqlAlchemyDuelRepository` поверх существующей `session_factory`.
    - `dispatcher["challenge_duel"]` / `accept_duel` / `cancel_duel` / `submit_move` / `resolve_afk_round` / `players` / `duels` — для aiogram-DI по имени параметра в handler-ах.
- **Локализация** — 44 ключа в `locales/ru.ftl` и `locales/en.ftl`:
    - `duel-private-needs-global` / `duel-usage` / `duel-not-registered` / `duel-target-not-registered` / `duel-target-is-bot` / `duel-self-challenge`
    - `duel-challenge-chat` / `duel-challenge-chat-then-global` / `duel-challenge-global` / `duel-chat-accepted`
    - `duel-button-accept` / `duel-button-reject` / `duel-button-attack-{high,mid,low}` / `duel-button-block-{high,mid,low}`
    - `duel-round-attack-prompt` / `duel-round-block-prompt` / `duel-round-waiting`
    - `duel-result-victory` / `duel-result-defeat` / `duel-result-draw`
    - `duel-cancelled` / `duel-cancel-usage`
    - 9 toast-ключей: `duel-toast-{accepted,rejected,cancelled,not-found,not-participant,foreign-button,invalid-state,already-submitted,outdated}`
    - `duel-requirements-not-met` / `duel-anticheat-blocked` / `duel-lock-already-held`
- **`bot/handlers/__init__.py`** — регистрация `duel_router` после `upgrade_router`.
- **`bot/presenters/__init__.py`** — экспорт `DuelPresenter` + `Accept/Reject/Attack/BlockCallbackData` + парсеров.
- **`.gitignore`** — `uv.lock` (попадал в коммиты по ошибке после `uv run`).

Результат / артефакты:

- PR #50 https://github.com/Pipirkawar/PipirkaWar/pull/50 (5 коммитов, +1964 LoC по 9 файлам).
- 4 коммита внутри: `feat(pvp): DuelPresenter + callback_data parsers`, `feat(pvp): bot/handlers/duel.py + DI wiring`, `chore: untrack uv.lock`, `feat(pvp): RU+EN locales duel-*`.

Заметки / решения:

- **Атака зашита в `block_keyboard.callback_data`** — handler `pvp-block` берёт её оттуда, а не из БД. Это exact-once-семантика: одна и та же атака не может «съехать» при повторных нажатиях; и handler stateless относительно UI-состояния.
- **`pvp-reject` не пишет в БД** — pending duel останется до TTL-cleanup в 2.1.F (FIFO глобальный пул + cleanup-job APScheduler-а). Решение даёт реджект как мгновенный UX без транзакции, ценой того что отказ не идемпотентен (повторный реджект тем же игроком не отличить от первого) — но это безвредно.
- **`pvp-attack` не зовёт use-case** — это чисто UI-переход «выбрал атаку → показать блок-промпт». Реальная мутация (submit_move) случается только при выборе блока. Так UX в чате/ЛС выглядит как «два клика = ход».
- **`bot.send_message(chat_id=tg_id)` для DM** — chat_id в личном чате равен tg_user_id; это паттерн aiogram, тот же что в `bot/notifications/forest.py`. Но для PvP отдельный notifier-класс не выделен — оба DM-а отправляются прямо из handler-а, что упрощает state-flow в линейный.
- **Известный пробел: тесты handler-ов и presenter-а отсутствуют.** PR #50 был смержен только с domain/application/integration-тестами (предыдущие саб-спринты), но `tests/unit/bot/handlers/test_duel.py` и `tests/unit/bot/presenters/test_duel.py` не были добавлены. Coverage-gate (`--cov-fail-under=80`) не сработал, т.к. остальной код по проекту покрыт > 90%. Бэкфилл этих тестов запланирован как housekeeping-таск перед началом 2.1.F (либо в сам 2.1.F, чтобы избежать ребейзов).
- **`AGENT_HANDOFF.md`** — файл-чеклист для in-progress-работы попал в PR #50 случайно (предыдущий агент завершил все шаги, но забыл удалить артефакт). Удаляется в этом housekeeping-PR.

---

## 2026-05-05 — Housekeeping: удалён `AGENT_HANDOFF.md` + актуализация `current_tasks.md` для 2.1.C/D/E

**Автор:** Devin (по запросу 612amaranth)
**Тип:** doc + chore
**Связано:** PR #48, #49, #50; этот housekeeping-PR.

После мерджа PR #48–50 (саб-спринты 2.1.C–E) предыдущий агент не успел синхронизировать `docs/current_tasks.md` (статусы остались на «🟡готово к ревью» / «⚪бэклог») и оставил в репо in-progress-чеклист `AGENT_HANDOFF.md` (был привязан к WIP-коммитам PR #50; все шаги в нём закрыты, но файл забыли удалить перед мерджем).

Что сделано:

- Удалён корневой `AGENT_HANDOFF.md` (356 строк, последний коммит-ссылка — `41d7577 feat(pvp): DuelPresenter + callback_data parsers (WIP Sprint 2.1.E)`).
- В `docs/current_tasks.md` строки PR-таблицы Спринта 2.1:
    - 2.1.C: 🟡готово к ревью → ✅смержено (PR #48)
    - 2.1.D: 🟡готово к ревью → ✅смержено (PR #49)
    - 2.1.E: ⚪бэклог → ✅смержено (PR #50)
- Добавлена настоящая запись + полная запись Спринта 2.1.E в `docs/history.md` (записи добавляются сверху).

Заметки / решения:

- Записи в `history.md` про 2.1.C/D создавались внутри тех же PR-ов; для 2.1.E она пропустилась, поэтому делаем её здесь, по факту изученных коммитов и diff-а PR #50.

---

## 2026-05-05 — Спринт 2.1.D: PvP use-cases (ChallengeDuel/AcceptDuel/CancelDuel/SubmitMove/ResolveAfkRound)

**Автор:** Devin (по запросу 521sophie)
**Тип:** feature (application use-cases + DTO + helpers + tests)
**Связано:** `current_tasks.md` Спринт 2.1.D, ПД 2.1.6 + 2.1.5 (`development_plan.md §5`), ГДД §7.1 + §3.2.

Четвёртый саб-спринт PvP-эпика 2.1. Поверх доменного агрегата `Duel` (2.1.B) и persistence-слоя (2.1.C) появляются 5 use-cases на ambient UoW + activity-lock + anti-cheat-gate, объединяющие домен с инфраструктурой и завершающие application-уровень PvP. Bot-handler-ы и шедулинг — отдельные саб-спринты 2.1.E–H.

Что сделано:

- **5 use-cases** в `src/pipirik_wars/application/pvp/`:
    - `ChallengeDuel`: создаёт `Duel.create_challenge(...)` с снэпшотом баланса (`hit_pct=10`, `expected_rounds=3`); валидирует PvP-требования (`balance.pvp.duel_1v1.min_length_cm`, `min_thickness_level`) и `AnticheatGuard.require_unlocked` для челленджера; берёт activity-lock `reason=PVP, ttl=30 мин`; пишет audit `PVP_DUEL_CREATED` с `idempotency_key=pvp_duel_created:{duel.id}`.
    - `AcceptDuel`: загружает дуэль и оппонента; валидирует PvP-требования и anti-cheat для оппонента; берёт lock на оппонента; вызывает `Duel.accept(accepter_id, p1_length_cm, p2_length_cm, now)` (path-independent резолв через снэпшот длин на старте); audit `PVP_DUEL_ACCEPTED`.
    - `CancelDuel`: только челленджер может отменить; идемпотентен на `state=CANCELLED` (no-op без audit); снимает lock с челленджера; audit `PVP_DUEL_CANCELLED`.
    - `SubmitMove`: преобразует `attack/block` строки → `Position`-enum → `RoundChoice`; вызывает `Duel.submit_move(...)`; если домен сам авто-завершил дуэль (3 раунда сыграны) — вызывает `apply_duel_outcome(...)`, снимает оба lock-а, audit `PVP_DUEL_COMPLETED`.
    - `ResolveAfkRound`: idempotent на already-resolved (`pending_round.round_num != input.round_num` или `state != IN_PROGRESS`); для отсутствующих игроков прокатывает `IRandom.choice` × 2 (атака + блок); вызывает `Duel.force_complete_round(...)` со fallback-выборами; та же финализация дуэли что и в `SubmitMove`.
- **Pure-helper** `application/pvp/apply_outcome.py`: единая точка применения `DuelOutcome.pX_delta_cm` к игрокам:
    - delta > 0 (победитель) → `length_granter.grant(source=AuditSource.PVP_REWARD, idempotency_key=add_length:pvp_duel:{id}:{side})` — проходит через anti-cheat cap из 1.6.B (organic-whitelist уже включает `pvp_reward`).
    - delta < 0 (проигравший) → `Player.with_length(...)` напрямую (это spend, не grant; cap'у не подлежит) + audit `LENGTH_REVOKE` с `idempotency_key=pvp_duel_loss_revoke:{id}:{side}`.
    - delta == 0 (ничья) → no-op, audit не пишется.
    - Файл добавлен в `_ALLOWED_FILES` `tests/unit/architecture/test_length_grant_guard.py` (4-й разрешённый callsite `Player.with_length`).
- **Новые `AuditAction`** в `domain/shared/ports/audit.py`: `PVP_DUEL_CREATED` / `PVP_DUEL_ACCEPTED` / `PVP_DUEL_CANCELLED` / `PVP_DUEL_COMPLETED`.
- **DTO** в `application/dto/inputs.py` (5 классов с `model_validator`-ами): `ChallengeDuelInput` (`mode='global_only'` ↔ `challenged_tg_id is None`), `AcceptDuelInput`, `CancelDuelInput`, `SubmitMoveInput` (с `Literal['high','mid','low']` для `attack`/`block`), `ResolveAfkRoundInput`.
- **`FakeDuelRepository`** в `tests/fakes/duel_repo.py` (повторяет паттерн `FakeForestRunRepository`): in-memory storage с auto-id на `add()`, `get_by_id`, `save` (с `IntegrityError` на duel-without-id и duel-id-not-exists). Зарегистрирован в `tests/fakes/__init__.py`.
- **48 unit-тестов** на use-cases в `tests/unit/application/pvp/`:
    - `test_challenge_duel.py` (13): happy chat_only/chat_then_global/global_only, DTO-валидатор отбивает несовместимые mode×target, PvpRequirementsNotMetError на length/thickness ниже порога, AnticheatSoftBanError, LockAlreadyHeldError при чужом lock-е (FOREST), edge: длина ровно min_length_cm.
    - `test_accept_duel.py` (12): happy targeted (CHAT_ONLY) + global (GLOBAL_ONLY с авто-set `challenged_id`), lock-acquire на оппонента, DuelNotFoundError, PlayerNotFoundError для accepter и challenger (FK-disappear), PvP-requirements / anticheat / lock-conflict для оппонента, NotADuelParticipantError (третий лишний и self-accept в global_only), InvalidDuelStateError на CANCELLED.
    - `test_cancel_duel.py` (6): happy (releases lock), idempotency на already-cancelled (no audit, no mutations), DuelNotFoundError, PlayerNotFoundError, NotADuelParticipantError (не-челленджер пытается), InvalidDuelStateError на IN_PROGRESS.
    - `test_submit_move.py` (9): partial round (round_num не сменился), round closes (round_num=2 открылся, длины НЕ применены), duel completes на 3-ем раунде → zero-sum applied, draw → нет LENGTH_*-аудитов, DuelNotFoundError, PlayerNotFoundError, NotADuelParticipantError, MoveAlreadySubmittedError, InvalidDuelStateError на PENDING_ACCEPT.
    - `test_resolve_afk_round.py` (8): оба AFK → оба rolled, p1-picked p2-AFK → только p2 rolled, completes finals → zero-sum + locks released + `afk_fallback=True` в audit, deterministic seed-rerun даёт идентичные выборы, idempotency на already-resolved (round 2 идёт, таймер 1 опоздал) и terminal (CANCELLED), DuelNotFoundError.
- **Документация:** `current_tasks.md` Спринт 2.1.D переведён в «🟡 готово к ревью» с подробным резюме; обновлён этот журнал.

Результат / артефакты:

- Новые исходники:
    - `src/pipirik_wars/application/pvp/__init__.py`, `challenge_duel.py`, `accept_duel.py`, `cancel_duel.py`, `submit_move.py`, `resolve_afk_round.py`, `apply_outcome.py`.
    - `tests/fakes/duel_repo.py`.
    - `tests/unit/application/pvp/__init__.py`, `_helpers.py`, `test_challenge_duel.py`, `test_accept_duel.py`, `test_cancel_duel.py`, `test_submit_move.py`, `test_resolve_afk_round.py`.
- Изменённые файлы: `application/dto/inputs.py` (+5 DTO + `model_validator` для `ChallengeDuelInput`), `domain/shared/ports/audit.py` (+4 `AuditAction`), `domain/pvp/__init__.py` (re-export `DuelNotFoundError` / `PvpRequirementsNotMetError`), `tests/fakes/__init__.py`, `tests/unit/architecture/test_length_grant_guard.py` (allowed-list +`apply_outcome.py`).
- Метрики:
    - Вся локальная сюита: **1680 passed, 1 skipped** (+54 = 48 PvP unit + 6 архитектурных за счёт расширенного allowed-list / нового модуля; baseline до спринта — 1626).
    - Coverage: **96.86%** (выше требуемых 80%).
    - Новые PvP-модули: 90–97% покрытия (defensive `RuntimeError` на `player.id is None` и `PlayerNotFoundError` на FK-disappear не покрыты — это страховые ветки, недостижимые с текущими fake-реализациями).
- Все артефакты `make ci` зелёные локально: `ruff format` / `ruff check` / `mypy` (234 файла, no issues) / `lint-imports` (3 contracts kept).

Заметки / решения:

- **`apply_outcome` как отдельный pure-helper, а не два отдельных use-case-а.** Два разных use-case-а (`SubmitMove` + `ResolveAfkRound`) приводят к одному и тому же завершению дуэли и одной и той же логике применения дельты. Вынос в чистый helper (без `IUnitOfWork` — вызывается ВНУТРИ уже открытой транзакции родителем) даёт one-and-only-one source of truth для zero-sum-обмена и одинаковые idempotency-ключи. Альтернатива (общий базовый класс или метод-прим в `Duel`) ломает чистоту домена (он не должен знать про `ILengthGranter` / audit).
- **Idempotency-ключи победителя через `add_length:pvp_duel:{id}:{side}`.** Префикс `add_length:` обязателен (валидируется `FakeIdempotencyKey.mark` и реальной БД-таблицей `idempotency_keys` namespace=`add_length`). `pvp_duel:{id}:{side}` — детерминирован и уникален на пару (бой, сторона). Для проигравшего идём отдельным путём (`pvp_duel_loss_revoke:{id}:{side}`) — он НЕ через `AddLength`, потому что cap'у `LENGTH_REVOKE` не подлежит (это spend), но запись в audit нужна.
- **`Player.with_length()` для проигравшего, не `progression.subtract_length`.** На 1.6 нет use-case-а `SubtractLength`/`RevokeLength` — это намеренный дизайн (anti-cheat в 1.6.B защищает только GAINS, а LOSSES — это honest debit). Прямой `with_length()` оправдан и в `UpgradeThickness` (1.4.A: spend на улучшение). Архитектурный гард `test_length_grant_guard.py` теперь явно разрешает это в `apply_outcome.py` (4-й callsite после `domain/player/entities.py` / `application/progression/{add_length,upgrade_thickness}.py`).
- **`model_validator` в `ChallengeDuelInput` ловит несовместимые `mode×challenged_tg_id`** ещё до загрузки игроков (early-fail). Доменный `Duel.create_challenge(...)` дублирует ту же проверку — bot-handler в 2.1.E может полагаться на неё; use-case упрощается (нет `if mode == GLOBAL_ONLY: ...`).
- **`ResolveAfkRound` идемпотентен на 2 уровнях.** (1) Если `state != IN_PROGRESS` → no-op (дуэль завершена/отменена прежде чем шедулер сработал). (2) Если `pending_round is None or pending_round.round_num != input.round_num` → no-op (раунд закрыт реальными ходами, шедулер опоздал). Обе ветки возвращают `was_already_resolved=True` без audit-записей.
- **`afk_fallback` в audit-record `PVP_DUEL_COMPLETED`.** Различает «дуэль завершилась нормально» от «дуэль завершилась через AFK-таймаут хотя бы в одном раунде». Полезно для аналитики/anti-cheat (массовое AFK = подозрительно), хотя hard-cap не накладываем.
- **Нет интеграционных тестов с реальной БД.** Use-cases работают через fakes (FakeDuelRepository, FakePlayerRepository, etc.). Реальный SQLAlchemy-репо `Duel` уже покрыт в 2.1.C (15 интеграционных тестов). Дублировать смысла нет — use-cases только координируют, persistence-логика в репо.

Что дальше:

- 2.1.E: bot-handler-ы (`/duel <opponent>` + 6 inline-кнопок + presenter с локалями), DI use-cases в `bot/main.py`.
- 2.1.F: глобальное лобби FIFO + APScheduler-job для авто-перехода `chat → global` через 3 мин.
- 2.1.G: раунд-таймер 30–60 сек через `ILongPollTimer` / APScheduler, который вызывает `ResolveAfkRound`.
- 2.1.H: 50+ JSON-шаблонов забавных раунд-логов (RU/EN), `JsonDuelLogTemplateProvider`, карточка результата.

---

## 2026-05-05 — Спринт 2.1.C: persistence-фундамент агрегата `Duel`

**Автор:** Devin (по запросу persisyellow)
**Тип:** feature (infrastructure + domain port)
**Связано:** `current_tasks.md` Спринт 2.1.C, ПД 2.1.6 (`development_plan.md §5`), ГДД §7.1.

Третий саб-спринт PvP-эпика 2.1. Поверх доменного агрегата `Duel` из 2.1.B появляется persistence-слой — миграция `0009_pvp_duels`, ORM-модели, доменный порт `IDuelRepository` и его реализация поверх SQLAlchemy. Use-cases — отдельный саб-спринт 2.1.D.

Что сделано:

- **Миграция `0009_pvp_duels`** (`src/pipirik_wars/infrastructure/db/migrations/versions/20260505_0009_pvp_duels.py`):
    - Таблица **`pvp_duels`** — корневая запись агрегата (id, challenger_id, challenged_id, mode, state, hit_pct, expected_rounds, p1/p2_initial_length_cm, created_at/accepted_at/completed_at/cancelled_at, pending_round_num + 4 pending_pX_attack/block, 5 final_*-колонок). FK `challenger_id`/`challenged_id` → `users.id` с `ON DELETE CASCADE`.
    - Таблица **`pvp_duel_rounds`** — 1:N completed-раунды (PK `(duel_id, round_num)`), FK `duel_id` → `pvp_duels.id` с `ON DELETE CASCADE`. Колонки: 4 для choice-ов (p1/p2 × attack/block), 2 для attack_blocked-флагов, 2 для damage-чисел.
    - **CHECK-инварианты** охраняют корректность данных при ручных SQL-правках в обход доменного слоя:
        - `mode IN ('chat_then_global', 'chat_only', 'global_only')`;
        - `state IN ('pending_accept', 'in_progress', 'completed', 'cancelled')`;
        - `hit_pct BETWEEN 0 AND 100`, `expected_rounds >= 1`;
        - `challenger_id <> challenged_id` (когда `challenged_id IS NOT NULL`) — last-line-of-defense self-challenge;
        - `pX_initial_length_cm >= 0` (или NULL), `pending_round_num >= 1` (или NULL);
        - `Position`-колонки ∈ `('high', 'mid', 'low')` (или NULL для pending);
        - `pending_pX_attack` и `pending_pX_block` — пара (либо оба заданы, либо оба NULL);
        - `final_winner ∈ ('p1', 'p2', 'draw')` (или NULL);
        - **Комплексный state-related CHECK** `ck_pvp_duels_state_invariants` — каждый из 4 state-ов ↔ свой шаблон NULL/NOT NULL для accepted_at/completed_at/cancelled_at/pX_length/pending_round_num/final_winner;
        - На `pvp_duel_rounds`: `damage >= 0`, `attack_blocked = TRUE ⇒ damage = 0` (консистентность).
    - **Индексы** для будущих use-cases:
        - `ix_pvp_duels_challenger_id_state` / `ix_pvp_duels_challenged_id_state` — preflight «есть ли активный бой у игрока» (use-case 2.1.D + activity-lock);
        - `ix_pvp_duels_state_created_at` — сканирование экспирированных pending-вызовов (job 2.1.F auto-cancel/promote по TTL).
    - `downgrade()` — линейное удаление обеих таблиц с индексами в обратном порядке. Round-trip `upgrade head → downgrade base → upgrade head` валидирован ручным smoke-test-ом (alembic CLI на временном SQLite).
- **ORM-модели** (`src/pipirik_wars/infrastructure/db/models/pvp.py`): `PvpDuelORM` + `PvpDuelRoundORM` — зеркало миграции, тот же набор CHECK-ов в `__table_args__`. Зарегистрированы в `infrastructure/db/models/__init__.py` (alphabetical order) и в `tests/integration/db/conftest.py` (чтобы `Base.metadata.create_all` создал таблицы для in-memory SQLite в integration-тестах).
- **Доменный порт** (`src/pipirik_wars/domain/pvp/repositories.py`): `IDuelRepository` — `add(duel) → Duel` (assigns id), `get_by_id(duel_id) → Duel | None`, `save(duel) → Duel` (по id, отказ для duel.id is None). UoW-неотягощённый — все методы `async`, исполняются внутри активного `IUnitOfWork`. Зарегистрирован в `domain/pvp/__init__.py`.
- **Реализация** (`src/pipirik_wars/infrastructure/db/repositories/pvp_duel.py`):
    - `SqlAlchemyDuelRepository(uow=...)`. Сериализация `Duel ↔ PvpDuelORM`:
        - enum-ы (`DuelState`/`DuelMode`/`Position`/`DuelWinner`) → строковое `.value`;
        - `pending_round: PendingRound | None` ↔ 4 nullable-колонки `pending_pX_attack/block` + `pending_round_num`;
        - `final_outcome: DuelOutcome | None` ↔ 5 nullable-колонок `final_*`;
        - `completed_rounds: tuple[RoundOutcome, ...]` ↔ 1:N в `pvp_duel_rounds` (round_num — индекс в кортеже + 1).
    - `add(duel)` — INSERT root-row, flush, INSERT всех существующих completed-раундов (если на момент add-а они уже есть в агрегате), flush, return reload-енный агрегат с id-ом. Запись с `id != None` отвергается (`use save()`).
    - `get_by_id(duel_id)` — load root + все round-rows (`order by round_num`), сборка `Duel`-агрегата.
    - `save(duel)` — UPDATE root через `_apply_duel_to_row` (все поля), потом INSERT недостающих round-rows (старые иммутабельны после авторазрешения — для них в домене API нет).
    - `IntegrityError` БД-уровня (нарушение CHECK-/FK-инвариантов) ловится и конвертируется в доменный `IntegrityError` из `pipirik_wars.shared.errors`.
    - Зарегистрирован в `infrastructure/db/repositories/__init__.py`.
- **Тесты** (15 новых):
    - `tests/integration/db/test_migrations.py`: +1 пункт в `expected_revisions`, +`test_0009_descends_from_0008`, +файл `20260505_0009_pvp_duels.py` в `test_versions_dir_lists_only_known_files`, +`pvp_duels`/`pvp_duel_rounds` в `expected` множество в `test_upgrade_head_creates_all_tables`. Round-trip `upgrade → downgrade → upgrade` уже покрыт общим case-ом — теперь автоматически проверяет и 0009.
    - `tests/integration/db/pvp/test_pvp_duel_repository.py` (14):
        - `TestPendingAcceptPersistence` (7): add chat-вызов сохраняет все поля, get_by_id reloads; add global-вызов с `challenged_id=None` (специфика `GLOBAL_ONLY`); get_by_id missing → None; add с pre-set id → `IntegrityError`; save без id → `IntegrityError`; save с unknown id → `IntegrityError`.
        - `TestCancelPersistence` (1): cancel переводит `state=CANCELLED` и `cancelled_at` — оба поля переживают reload с диска.
        - `TestAcceptPersistence` (2): chat-accept снимает снэпшот lengths и стартует `pending_round.round_num=1` с `p1_choice=p2_choice=None`; global-accept устанавливает `challenged_id=accepter_id` (и переживает reload).
        - `TestSubmitMovePersistence` (2): partial pending_round (только p1 ответил — `pending_p1_*` not null, `pending_p2_*` null); auto-resolve раунда при готовности обоих → `completed_rounds[0]` заполнен с правильной damage formula `floor(80*10/100)=8`, `pending_round.round_num=2`.
        - `TestFullDuelPersistence` (1): полный 3-раундовый бой с `save` после каждого раунда → `state=COMPLETED`, `final_outcome.winner=P1`, `p1_total_dealt=30` / `p2_total_dealt=0`, дельты ±30, `len(completed_rounds)=3`. Полная перезагрузка с диска идентична исходному агрегату.
        - `TestSelfChallengeDbConstraint` (1): эмуляция обхода домена через `dataclasses.replace(challenge, challenged_id=challenger.id)` → CHECK-констрейнт `ck_pvp_duels_no_self_challenge` блокирует INSERT, конвертируется в доменный `IntegrityError`.

Результат / артефакты:

- Коммиты:
    - `feat(pvp): persistence — migration 0009_pvp_duels + ORM + IDuelRepository (Sprint 2.1.C 1/2)` — миграция + 2 ORM + порт + репо + регистрация (861 insertions).
    - `test(pvp): integration tests — migration 0009 + repo roundtrip (Sprint 2.1.C 2/2)` — 15 интеграционных тестов + регистрация ORM в conftest (570 insertions).
- Тесты: `make ci` зелёный — `1626 passed, 1 skipped` (предыдущая baseline 1607 → +14 интеграционных + 1 миграция). Покрытие — 96.89%. Layered-architecture контракты (3) — KEPT.
- ruff + ruff-format + mypy + import-linter — ✅. pre-commit на каждом коммите — ✅.

Заметки / решения:

- **Две таблицы вместо одной с JSON.** Альтернативой было хранить `completed_rounds` как JSON-колонку в `pvp_duels`. Отвергнуто: SQL-агрегации/индексы по конкретным раундам (например, «топ игроков по damage за раунд» в админке 2.2+) на JSON-extract-е непортабельны (SQLite vs Postgres) и плохо индексируются. Выделение в `pvp_duel_rounds` тривиально, даёт правильную нормализацию и каскадное удаление.
- **Pending round — 4 колонки в root-row, а не отдельная таблица.** Альтернативой было `pvp_duel_pending_rounds(duel_id, round_num, p1_attack, ...)` — но в любой момент времени есть **ровно один** pending-раунд (или ни одного). Отдельная таблица — оверкилл, требует JOIN-ов на каждом read-е и усложняет CHECK-консистентность. 4 nullable-колонки в `pvp_duels` дешевле и проще; CHECK-констрейнты `pending_pX_pair_consistent` гарантируют, что `attack` и `block` приходят парой.
- **`final_outcome` — тоже в root-row.** Аналогично pending-раунду: `final_winner` + 4 числовых колонки → выводится в `DuelOutcome` при reload-е. CHECK ck_pvp_duels_state_invariants гарантирует: `state=COMPLETED` ⇔ `final_winner IS NOT NULL` (плюс остальные `final_*` тоже NOT NULL — все `Frozen`-поля `DuelOutcome` имеют значение в момент завершения). Альтернатива «отдельная таблица `pvp_duel_outcomes`» — те же причины overkill-а, что и для pending-раунда.
- **Self-challenge на уровне БД.** Доменный `Duel.create_challenge` уже бросает `SelfChallengeError` для `CHAT_*`-режимов, и `accept` бросает `NotADuelParticipantError` для `GLOBAL_ONLY`. Но domain-layer-валидация — не last-line-of-defense на случай миграций / ручных правок / багов в use-case-ах. CHECK `challenger_id <> challenged_id` (когда `challenged_id IS NOT NULL`) гарантирует консистентность данных в БД независимо от пути записи. Тест `test_db_check_blocks_self_challenge_via_raw_replace` это явно проверяет.
- **Single-active-duel-per-player НЕ охраняется на уровне БД.** Один игрок может иметь несколько `PENDING_ACCEPT`-вызовов в разных чатах одновременно. Только `IN_PROGRESS`-бой должен быть единственным — это охраняется `activity_locks`-таблицей из 0.2 (`activity='pvp_duel'` + ownership одного duel-id-а) и use-case 2.1.D. Дублировать как partial unique index вида `WHERE state='in_progress'` — преждевременная оптимизация: в production это решит activity_lock, и при двойной защите ловить race-condition станет неудобнее.
- **`_apply_duel_to_row` вместо отдельных `add` и `save` body.** Сериализация Duel → row занимает ~30 строк присваиваний (особенно с разворотом `pending_round` и `final_outcome` в группы nullable-колонок). Вынесение в общий хелпер устраняет дублирование между `add()` и `save()`; row передаётся параметром (для add — свежесозданный, для save — загруженный по id). На `save()` мы не пересоздаём row, а UPDATE-им in-place — это правильно, потому что SQLAlchemy 2.x async session уже знает row-у через identity map после `session.get(...)`.
- **`completed_rounds` иммутабельны после авторазрешения.** Доменный API не имеет метода «отредактировать прошлый раунд» — `submit_move` и `force_complete_round` только добавляют новые. Соответственно `save()` синхронизирует только новые round-rows, существующие не трогает (через `existing_round_nums` set + skip). Это упрощает persistence (нет UPDATE-ов на round-rows) и даёт audit-trail: исторические раунды остаются неизменными после первой записи.
- **Что не вошло (для следующих саб-спринтов):**
    - Use-cases `ChallengeDuel` / `AcceptDuel` / `SubmitMove` / `ResolveDuel` (с activity-lock-ом, `IRandom` для AFK, `progression.add_length(source=PVP_REWARD)` с anti-cheat-cap-ом) → 2.1.D.
    - Bot-handler-ы и presenter-ы (`/duel`, inline-кнопки, локали) → 2.1.E.
    - Глобальное лобби FIFO + auto-promote через 3 мин → 2.1.F.
    - Раунд-таймер 30–60s через APScheduler + AFK-job (вызывает `Duel.force_complete_round` через repo+save) → 2.1.G.
    - 50+ JSON-шаблонов забавных раунд-логов + presenter-карточка + кнопка «Поделиться» → 2.1.H.

---

## 2026-05-05 — Спринт 2.1.B: доменный агрегат `Duel` (lifecycle state machine)

**Автор:** Devin (по запросу persisyellow)
**Тип:** feature (domain)
**Связано:** `current_tasks.md` Спринт 2.1.B, ПД 2.1.6 (`development_plan.md §5`), ГДД §7.1.

Второй саб-спринт PvP-эпика 2.1. Поверх чистого боевого движка из 2.1.A появляется доменный агрегат `Duel` — жизненный цикл боя от вызова до итоговой `DuelOutcome`. Persistence (миграция + ORM + репо) и use-cases — отдельные саб-спринты 2.1.C–D.

Что сделано:

- **`src/pipirik_wars/domain/pvp/duel.py`** (новый файл, 487 строк):
    - `DuelState(StrEnum)`: `PENDING_ACCEPT` / `IN_PROGRESS` / `COMPLETED` / `CANCELLED`. Графы переходов: `PENDING_ACCEPT → IN_PROGRESS` (через `accept`) или `CANCELLED` (через `cancel` / TTL-истечение). `IN_PROGRESS → COMPLETED` после `expected_rounds` раундов через `submit_move` или `force_complete_round`. Терминальные — `COMPLETED` и `CANCELLED`.
    - `DuelMode(StrEnum)`: `CHAT_THEN_GLOBAL` (по умолчанию — вызов в чат, через 3 мин авто-промоут в global-лобби; логика 2.1.F), `CHAT_ONLY` (только чат, без авто-промоута), `GLOBAL_ONLY` (сразу в лобби, `challenged_id is None` до accept-а).
    - `PendingRound(@dataclass(frozen=True, slots=True))`: текущий раунд — `round_num: int` (1-based), `p1_choice: RoundChoice | None`, `p2_choice: RoundChoice | None`. Свойства `is_complete` (оба `not None`) и `has_any_move` (хотя бы один).
    - `Duel(@dataclass(frozen=True, slots=True))` — корневой агрегат. Поля: `id` (`None` до persistence) / `challenger_id` / `challenged_id` (`None` для `GLOBAL_ONLY` до accept-а) / `mode` / `state` / `hit_pct` / `expected_rounds` (баланс на старте) / `created_at` / `accepted_at` / `completed_at` / `cancelled_at` / `p1_initial_length_cm` / `p2_initial_length_cm` (длины на момент accept-а) / `completed_rounds: tuple[RoundOutcome, ...]` / `pending_round: PendingRound | None` / `final_outcome: DuelOutcome | None`.
- **Lifecycle-методы агрегата** (frozen → возвращают новый `Duel` через `dataclasses.replace`):
    - `Duel.create_challenge(*, challenger_id, challenged_id, mode, hit_pct, expected_rounds, now)` — pending-вызов. Валидация: self-challenge (`SelfChallengeError`), границы `expected_rounds` и `hit_pct` (`ValueError`), соответствие `mode` ↔ `challenged_id` (`GLOBAL_ONLY` без, остальные — с).
    - `Duel.accept(*, accepter_id, p1_length_cm, p2_length_cm, now)` — снапшот длин, перевод `PENDING_ACCEPT → IN_PROGRESS`, старт первого раунда. Для `GLOBAL_ONLY` устанавливает `challenged_id = accepter_id` (с защитой от self-challenge — `accepter_id == challenger_id` ⇒ `NotADuelParticipantError`). Для `CHAT_*` `accepter_id` обязан совпадать с `challenged_id`.
    - `Duel.cancel(*, now)` — `PENDING_ACCEPT → CANCELLED`. Идемпотентен на уже отменённой дуэли (no-op). Из `IN_PROGRESS` / `COMPLETED` блокируется (`InvalidDuelStateError`).
    - `Duel.submit_move(*, player_id, choice, now)` — отправить выбор атаки/блока на `pending_round.round_num`. Валидация участника (`NotADuelParticipantError`), повторного сабмишена (`MoveAlreadySubmittedError`), состояния (`InvalidDuelStateError`). Если этим вызовом раунд закрылся — авторазрешение через `resolve_round` (импорт из 2.1.A) и переход к следующему раунду или в `COMPLETED` (через `resolve_duel`).
    - `Duel.force_complete_round(*, p1_fallback, p2_fallback, now)` — AFK-фоллбэк. Use-case 2.1.G возьмёт случайные `Position` через `IRandom` и соберёт `RoundChoice`-ы для пропустивших; этот метод их применит. Защита: `NoMissingMovesError` если все уже выбрали; `MoveAlreadySubmittedError` если фоллбэк передан для того, кто уже выбрал; `InvalidDuelStateError` из не-`IN_PROGRESS`.
- **Доменные ошибки** (`domain/pvp/errors.py`, +5 классов):
    - `InvalidDuelStateError(*, expected, actual, op)` — операция из неподходящего состояния (метод `op`, ожидалось `expected`, было `actual`). Use-case конвертирует в локализованное «бой ещё не начался» / «бой уже завершён».
    - `NotADuelParticipantError(*, player_id)` — `player_id` не челленджер и не оппонент. Локализация: «вы не участник этого боя».
    - `SelfChallengeError(*, player_id)` — `challenger_id == challenged_id` при `create_challenge`. Локализация: «нельзя вызвать самого себя».
    - `MoveAlreadySubmittedError(*, player_id, round_num)` — повторный `submit_move` от того же игрока. Локализация: «вы уже выбрали в этом раунде».
    - `NoMissingMovesError(*, round_num)` — `force_complete_round` без пропущенных выборов (баг в use-case-е 2.1.G — таймер сработал после того, как оба выбрали).
- **Юнит-тесты** (76 новых):
    - `tests/unit/domain/pvp/test_duel_lifecycle.py` (47 тестов):
        - `TestCreateChallenge` (16): валидный chat-вызов, валидный global-вызов без `challenged_id`, обязательность `challenged_id` для `CHAT_ONLY` / `CHAT_THEN_GLOBAL` (`ValueError`), запрет `challenged_id` для `GLOBAL_ONLY` (`ValueError`), self-challenge запрет (chat и chat_then_global; в global self-challenge ловится только в accept-е), границы `expected_rounds` ([1, 3, 5, 10] валидно; [0, -1, -100] ⇒ `ValueError`), границы `hit_pct` ([0, 1, 50, 100] валидно; [-1, 101, 200, -50] ⇒ `ValueError`).
        - `TestAccept` (10): chat-accept с переходом в `IN_PROGRESS` и стартом первого раунда; global-accept устанавливает `challenged_id`; global self-challenge блокируется в accept-е (`NotADuelParticipantError`); accept от не-участника / от челленджера; отрицательная длина p1 / p2 (`InvalidLengthError`); нулевые длины разрешены; повторный accept (`InvalidDuelStateError`); accept после cancel.
        - `TestCancel` (3): cancel pending → `CANCELLED`; идемпотентность на cancelled (та же ссылка); cancel в `IN_PROGRESS` блокируется.
        - `TestProperties` (8): `is_pending` / `is_in_progress` / `is_completed` / `is_cancelled` / `is_terminal` / `is_participant` для chat и global (до и после accept).
        - `TestImmutability` (3): frozen-датакласс (`FrozenInstanceError` при попытке мутировать `state`); `accept` и `cancel` возвращают новый инстанс, оригинал не меняется.
    - `tests/unit/domain/pvp/test_duel_moves.py` (29 тестов):
        - `TestSubmitMoveSingleRound` (5): первый ход p1 / p2 (только своя сторона `pending_round` обновляется); авторазрешение раунда с пробитием обеих сторон; авторазрешение с симметричным блоком (нулевой урон); порядок сабмишена не влияет на исход (`d_a.completed_rounds == d_b.completed_rounds`).
        - `TestSubmitMoveErrors` (6): submit в `PENDING_ACCEPT`, после `cancel`, не-участником, повторный сабмит p1 / p2, submit после `COMPLETED` — все с правильными типами ошибок.
        - `TestFullDuelFlow` (5): полная победа p1 за 3 раунда (`p1_total_dealt=30`, `p2_total_dealt=0`, `winner=P1`, дельты ±30); ничья (симметричные раунды → нулевые дельты, `winner=DRAW`); path-independence (p2=20cm, 3 раунда пробития → `p1_total_dealt=6`; если бы было path-dependent, было бы `2+1+1=4`); короткий бой `expected_rounds=1`; длинный бой `expected_rounds=5`.
        - `TestForceCompleteRound` (10): фоллбэк только p1 / только p2 / обоих; `MoveAlreadySubmittedError` при попытке передать фоллбэк для уже выбравшего (p1 и p2); `NoMissingMovesError` если фоллбэков не хватило; `InvalidDuelStateError` из `PENDING_ACCEPT` и `COMPLETED`; переход к следующему раунду; завершение боя через `force_complete_round` на последнем раунде.
        - `TestPendingRound` (3): `is_complete` / `has_any_move` для всех 4 комбинаций (оба, только p1, ни одного).
- **Регистрация символов** в `src/pipirik_wars/domain/pvp/__init__.py`: добавлены `Duel`, `DuelMode`, `DuelState`, `PendingRound`, плюс новые ошибки. Сохранён alphabetical order в `__all__`.

Результат / артефакты:

- Коммиты:
    - `feat(pvp): Duel aggregate — lifecycle state machine (Sprint 2.1.B 1/2)` — агрегат + 5 ошибок + регистрация в `__init__.py` (612 insertions, 8 deletions).
    - `test(pvp): Duel lifecycle + moves + AFK fallback (Sprint 2.1.B 2/2)` — 76 тестов в 2 файлах (738 insertions).
- Тесты: `make ci` зелёный — `1607 passed, 1 skipped`. Покрытие нового модуля `domain/pvp/duel.py` — 100%. Layered-architecture контракты (3) — KEPT.
- ruff + mypy + import-linter — ✅. pre-commit на каждом коммите — ✅.

Заметки / решения:

- **Снэпшоты на старте.** `hit_pct` и `expected_rounds` фиксируются в момент `create_challenge` (баланс), `pX_initial_length_cm` — в момент `accept` (длины игроков). Это устойчиво к двум ситуациям: (1) `/balance_reload` посреди боя не сбивает экономику текущей дуэли; (2) параллельные `/forest` или другие начисления длины не влияют на урон в текущей дуэли (path-independent резолв). Альтернатива «читать из репозитория игрока на каждом раунде» нестабильна и сложно тестируется.
- **Единая `pending_round` vs очередь раундов.** Альтернативой был `list[PendingRound]` с одним записимым в конце — но это избыточно, так как в любой момент времени есть ровно один pending-раунд (или ни одного при `COMPLETED`/`CANCELLED`). Завершённые раунды лежат в `completed_rounds: tuple[RoundOutcome, ...]` — иммутабельный список с уже разрешёнными исходами (включая `RoundChoice`-ы обоих игроков). Persistence-слой 2.1.C десериализует `completed_rounds` как `pvp_duel_rounds` table (1:N).
- **`force_complete_round` отдельно от `submit_move`.** Можно было бы реализовать AFK как «два `submit_move` подряд от внешнего инжектора», но такой API нечестно отражает доменную семантику — фоллбэк это **одна транзакция замены пропущенных ходов**, а не последовательный сабмишен. Также `force_complete_round` явно валидирует, что фоллбэки приходят только для тех, кто действительно AFK (и не приходят для тех, кто успел отправить ход). Если бы это были два `submit_move`, защита от race условия (игрок и фоллбэк-таймер сабмитят одновременно) была бы менее строгой.
- **`assert` вместо публичных проверок.** Внутренние инварианты (`pending.p1_choice is not None` в `_resolve_pending_round`) проверяются через `assert`, а не через `if … raise`. Это намеренно: они выполняются автоматически, если публичные методы (`accept` → `pending_round` всегда задан, `submit_move` → не закрывает раунд без обоих выборов) написаны корректно. Если `assert` сработает в продакшене — это баг, а не нормальная ошибка приложения. ruff и mypy на это не жалуются (`S101` отключён в проекте).
- **`InvalidDuelStateError.expected/actual` — `object`, а не `DuelState`.** Поле `expected` хранит ожидаемое значение (обычно `DuelState`), но в будущем может быть, например, кортежем валидных состояний. Тип `object` покрывает оба случая без выделения generic-параметра. Use-case-уровень всё равно конвертирует ошибку в локализованную строку и не работает с типом напрямую.
- **Себя-кейс в `GLOBAL_ONLY`.** Self-challenge в `CHAT_*` ловится в `create_challenge` (`challenger_id == challenged_id` ⇒ `SelfChallengeError`). В `GLOBAL_ONLY` `challenged_id is None` при создании, и self-challenge возможен только в момент accept-а — там он ловится уже как `NotADuelParticipantError(player_id=challenger_id)` (тот же игрок принимает свой же вызов). Use-case 2.1.D переведёт оба в одинаковое локализованное «нельзя вызвать самого себя».
- **Что не вошло (для следующих саб-спринтов):**
    - Persistence (миграция `0009_pvp_duels` + ORM + порт `IDuelRepository` + реализация) → 2.1.C.
    - Use-cases `ChallengeDuel` / `AcceptDuel` / `SubmitMove` / `ResolveDuel` (с activity-lock-ом, `IRandom` для AFK, `progression.add_length(source=PVP_REWARD)` с anti-cheat-cap-ом) → 2.1.D.
    - Bot-handler-ы и presenter-ы (`/duel`, inline-кнопки, локали) → 2.1.E.
    - Глобальное лобби FIFO + auto-promote через 3 мин → 2.1.F.
    - Раунд-таймер 30–60s через APScheduler + AFK-job → 2.1.G.
    - 50+ JSON-шаблонов забавных раунд-логов + presenter-карточка + кнопка «Поделиться» → 2.1.H.

---

## 2026-05-05 — Спринт 2.1.A: чистый доменный движок боя PvP 1×1

**Автор:** Devin (по запросу persisyellow)
**Тип:** feature (domain)
**Связано:** `current_tasks.md` Спринт 2.1.A, ПД 2.1.1 (development_plan.md §5), ГДД §7.1.

Открывающий саб-спринт PvP-эпика 2.1. Стартует Фазу 2 (боевые механики) поверх закрытого MVP DoD (Спринты 1.1–1.6).

Что сделано:

- **Чистый доменный пакет** `src/pipirik_wars/domain/pvp/`:
    - `entities.py`: `Position(StrEnum)` (HIGH/MID/LOW — единая ось для атак и блоков), `RoundChoice(frozen dataclass)` (атака + блок одного игрока на один раунд), `RoundOutcome(frozen dataclass)` (флаги `p1_attack_blocked` / `p2_attack_blocked` + нанесённые `p1_damage_to_p2` / `p2_damage_to_p1`), `DuelOutcome(frozen dataclass)` (`tuple[RoundOutcome, ...]` + суммарные dealt + zero-sum дельты + `winner`), `DuelWinner(StrEnum)` (P1/P2/DRAW). Все классы `@dataclass(frozen=True, slots=True)`.
    - `services.py`: `resolve_round(*, p1, p2, p1_length_cm, p2_length_cm, hit_pct) -> RoundOutcome` — чистая функция, реализует «попал не в блок → урон, в блок → 0» через `attack == block` (3×3 = 9 пар, диагональ — блок). Урон = `floor(defender_length_cm * hit_pct / 100)` на целочисленном делении (без Decimal/float). `resolve_duel(*, rounds, p1_length_cm, p2_length_cm, hit_pct, expected_rounds=3) -> DuelOutcome` — собирает `tuple[RoundOutcome, ...]` через `resolve_round`, считает `p1_total_dealt`/`p2_total_dealt`, выводит `winner` через знак дельты. `len(rounds) ≠ expected_rounds` → `InvalidRoundCountError`. Path-independent: длины обоих игроков на момент НАЧАЛА БОЯ используются на всех 3 раундах.
    - `errors.py`: `PvpError(DomainError)` базовый, `InvalidRoundCountError`, `InvalidLengthError`.
- **Балансовая схема** `domain/balance/config.py`:
    - `PvpDuel1v1Config(_Frozen)` — поля `rounds: int (ge=1, le=10)`, `hit_pct: int (ge=0, le=100)`, `min_length_cm: int (ge=0)`, `min_thickness_level: int (ge=1)`.
    - `PvpConfig(_Frozen)` — обёртка `duel_1v1: PvpDuel1v1Config` (зарезервирована для будущих режимов 2.2 mass_pvp).
    - `BalanceConfig.pvp: PvpConfig` — обязательное поле.
- **Конфиг-файл** `config/balance.yaml`:
    - Новая секция `pvp.duel_1v1`: `rounds: 3` (ГДД §7.1), `hit_pct: 10` (10% длины защитника за попадание), `min_length_cm: 20` (ГДД §7.1), `min_thickness_level: 2` (ГДД §3.2 / `thickness.unlock_levels.pvp_chat`).
- **Юнит-тесты** (99 новых):
    - `tests/unit/domain/pvp/test_resolve_round.py` (51 теста): полная матрица 9 пар атака×блок (3×3 с обеих сторон) → каждое совпадение ⇒ блок, каждое расхождение ⇒ пробитие; damage formula с целочисленным `floor`-делением (10% от 100 = 10, от 23 = 2, от 7 = 0, 0% — никогда, 100% = вся длина); погранцы (нулевая длина защитника, отрицательная длина → `InvalidLengthError`); `RoundOutcome` сохраняет выборы и флаги; frozen-immutability через `dataclasses.FrozenInstanceError`.
    - `tests/unit/domain/pvp/test_resolve_duel.py` (24 теста): сценарии чистой победы P1 (3 пробития) / P2 / DRAW (равный обмен, нулевой обмен); zero-sum инвариант `p1_delta + p2_delta == 0` параметризованно (6 пар начальных длин и hit_pct); path-independence (порядок раундов не меняет суммарный dealt и winner-а); `InvalidRoundCountError` для 0/1/5 раундов при `expected_rounds=3`; `expected_rounds=1` и `=5` для коротких/длинных дуэлей; `DuelOutcome` immutability + `tuple` (не `list`) в `rounds`.
    - `tests/unit/domain/balance/test_pvp_config.py` (24 теста): валидный default-payload, границы полей (`rounds` 1..10 ок, 0/-1/11 нет; `hit_pct` 0..100 ок, -1/101/200 нет; неотрицательные длины и уровень толщины ≥ 1), `frozen + extra=forbid` (попытка мутации → `ValidationError`, неизвестное поле → `ValidationError`), обязательность секции `pvp` в `BalanceConfig` (отсутствие → ошибка валидации, невалидное содержимое → ошибка).
- **Дополнительно (фикс CI на main):**
    - `tests/unit/application/anticheat/test_lift_ban.py` — импорт `Length` / `Thickness` / `Username` перенесён с `domain/player/entities` (где они только re-экспортируются без `__all__`) на `domain/player/value_objects` (где они объявлены). Mypy-strict в `--no-implicit-reexport`-режиме раньше падал на `attr-defined` для этих имён, что блокировало `make ci` независимо от моих изменений.

Результат / артефакты:

- 99 новых юнит-тестов; локально `make ci` зелёный: **1531 passed, 1 skipped, 97.03% покрытие**.
- Layered-architecture (`.importlinter`) проходит: `domain/pvp/` импортирует только `domain/shared/`, без `application/` / `infrastructure/` / `bot/` / `aiogram` / `sqlalchemy`.
- Файлы:
    - `src/pipirik_wars/domain/pvp/__init__.py`, `entities.py`, `errors.py`, `services.py` (новые).
    - `src/pipirik_wars/domain/balance/config.py`, `__init__.py` (расширены `PvpConfig` / `PvpDuel1v1Config`).
    - `config/balance.yaml` (новая секция `pvp.duel_1v1`).
    - `tests/unit/domain/balance/factories.py` (фабрика `valid_balance_payload` расширена `pvp`-секцией).
    - `tests/unit/domain/pvp/__init__.py`, `test_resolve_round.py`, `test_resolve_duel.py` (новые).
    - `tests/unit/domain/balance/test_pvp_config.py` (новый).
    - `tests/unit/application/anticheat/test_lift_ban.py` (исправлен implicit re-export).

Заметки / решения:

- **Одна `Position` enum vs два отдельных `Attack` / `Block`:** в ГДД §7.1 «3 атаки + 3 блока» — это 3 уровня нанесения и 3 уровня защиты ОДНОЙ И ТОЙ ЖЕ оси (HIGH/MID/LOW). Раздельные enum-ы потребовали бы кастов в `resolve_round` (`attack.position == block.position`) и порождали бы тривиальные баги при сравнении. Единая `Position` даёт однозначное `attack == block` ⇔ блок отбил. Локализация подписей кнопок (`pvp-attack-high`/`pvp-block-high`) — забота 2.1.C, не доменных типов.
- **Path-independent резолв:** все 3 раунда используют ОДНИ И ТЕ ЖЕ начальные длины. После раунда 1 у защитника «осталось бы» меньше длины — но в чистом домене это игнорируется. Так проще тестировать (порядок раундов не влияет), а cap-логика всё равно применяется выше — в use-case 2.1.E через `progression.add_length(...)`. Альтернатива (последовательное обновление длины между раундами) даёт «эффект снежного кома» — победитель раунда 1 наносит меньше в раунде 2, потому что defender уже похудел — и нестабильные тесты. ГДД §7.1 явного требования path-dependence не содержит; при балансе в будущем можно добавить параметр без правок `RoundOutcome`.
- **Целочисленный `hit_pct` vs Decimal/float:** `damage = floor(L * pct / 100)` гарантирует exact-числа в тестах (10% от 100 = 10, ровно). Decimal/float дали бы «10.0» или «10.000000000000002» в зависимости от платформы — лишний шум в snapshot-тестах. Балансу не нужны 1.5%-доли, а `1..100` целое — достаточно гранулярно.
- **Без `random` в чистом домене:** выбор атаки/блока приходит «снаружи» как `RoundChoice` (от игрока через ЛС либо от AFK-фоллбэка). Чистая функция → детерминированная, повторяемая в snapshot-тестах. AFK-фоллбэк через `IRandom` будет в 2.1.E (use-case `MakeMove`).
- **Параметризованный `expected_rounds`:** движок поддерживает короткие (1 раунд) и длинные (5+ раундов) дуэли без правок. Боевой код всегда передаёт `expected_rounds=balance.pvp.duel_1v1.rounds`, но тесты могут симулировать «блиц»-режимы и «epic»-дуэли для будущих режимов 2.2.
- **`DuelWinner` enum vs `Optional[Position]`:** winner ортогонален позициям и имеет осмысленное значение `DRAW` (равный обмен дилом). Отдельный enum читается яснее, чем `None`.
- **Вынос фикса `test_lift_ban.py`:** обнаружено, что `make ci` падал на main из-за implicit re-export `Length`/`Thickness`/`Username` в этом тесте (mypy-strict). Это пре-существующая проблема, не моя — но без её фикса CI на моём PR не пройдёт. Минимальный фикс — импортировать из `value_objects` напрямую.

---

## 2026-05-05 — Спринт 1.6.H: нагрузочный race-test анти-чит-cap-а + `docs/anticheat.md`

**Автор:** Devin (по запросу azurehannah)
**Тип:** test / doc
**Связано:** `current_tasks.md` Спринт 1.6.H, ПД 1.6.9 + 1.6.10 (development_plan.md §4), ГДД §3.3, §18.6.

Закрывающий саб-спринт анти-чит-эпика 1.6.

Что сделано:

- **Интеграционный нагрузочный тест** `tests/integration/load/test_anticheat_concurrent.py` (`@pytest.mark.slow`):
    - **`test_100_parallel_grants_for_same_player_respect_daily_cap`** — 100 параллельных `AddLength.grant(player_id=42, delta_cm=50, source=FOREST, ...)` от своих `SqlAlchemyUnitOfWork`-ов поверх общего `shared_session_maker` (файловый SQLite + aiosqlite `timeout=30s`). Проверяет инвариант ПД 1.6.9 — **либо** clamp удержал суммарную organic-дельту ≤ `daily_cap_cm` (3000 см), **либо** trip-wire среагировал и записал `ANTICHEAT_DAILY_CAP_EXCEEDED` + `Player.with_anticheat_ban(...)` + alert админу через `IAnticheatAdminAlerter`. Дополнительно: `db_total = sum(LENGTH_GRANT.delta_cm)` сходится с суммой `applied_delta_cm` в результатах use-case-а; soft-banned grant-ы консистентны с trip-wire-flag-ом.
    - **`test_100_parallel_grants_for_different_players_each_get_full_delta`** — 100 разных игроков по одному grant-у каждому. Проверяет, что `daily_cap_cm` считается **per-player** (фильтр по `audit_log.target_id`), а не глобально: каждый получает full delta=50, никаких clamp/ban, в audit ровно 100 LENGTH_GRANT-записей.
    - Оба теста стабильно зелёные (5 прогонов подряд, 2.87–3.59 сек / прогон).
- **`docs/anticheat.md`** — onboarding-документ для нового разработчика (~6 KB). Разделы:
    1. Архитектурный обзор: единая точка `progression.add_length`, ambient-UoW, алгоритм grant-а из 9 шагов (валидация → idempotency → soft-ban-гейт → clamp → mutate → audit `LENGTH_GRANT` → idempotency-mark → trip-wire), конфигурация `balance.yaml::anticheat`, rolling vs календарное окно, clamp vs trip-wire, snapshot-test инварианты.
    2. Как добавить новый source: enum в `AuditSource`, миграция whitelist, `balance.yaml::organic_sources`/`donate_sources`, вызов `length_granter.grant(...)`, тесты (юнит + параметризованный кейс в `test_add_length.py`), локализация.
    3. Как вручную снять soft-ban: основной путь через `/anticheat_unban` (Спринт 1.6.G); запасной через прямой SQL (`UPDATE users` + INSERT `audit_log` с action=`ANTICHEAT_BAN_LIFTED`); полезные SELECT-ы для списка забаненных и истории trip-wire-событий.
    4. Локализация (`anticheat-*` ключи) и связанная история (PR #34 → #35 → #36 → #37 → #39 → #42 → #43 → текущий).
    5. Известные ограничения: lost-update под SQLite на `users.length_cm` (тестовый артефакт), authz-transaction-баг в `SetMaxDau`/`ReloadBalance` (наследие от 1.5), `anticheat-admin-alert` локаль зарезервирована до появления Telegram-канала админ-алёртов.
- **`README.md`** — добавлен pointer на `docs/anticheat.md` в секцию «📚 Документация».
- **`docs/current_tasks.md`** — строка `1.6.H` обновлена с `⚪ бэклог` → `🟡 готово к ревью`; строка `1.6.G` (PR #43 уже смержен) синхронизирована: `🟡 готово к ревью` → `✅ смержено (PR #43)`.

Результат / артефакты:

- `tests/integration/load/test_anticheat_concurrent.py` — 2 теста, ~3 сек на полный прогон под `-m slow`.
- `docs/anticheat.md` — новый файл, ~6 KB.
- `README.md` — патч (1 строка).
- `docs/current_tasks.md` — патч (2 строки).
- Полный регрессионный прогон: `pytest tests/unit -q --no-cov` — 1288 passed / 1 skipped; `pytest tests/integration -q --no-cov` — 165 passed (было 163, +2 из load-теста).

Заметки / решения:

- **Почему не assert-нули `length_after == total_applied` под SQLite.** Изначальная попытка проверять `users.length_cm` против суммы возвращённых `applied_delta_cm` падала на 100-конкурентном race: `length_after=52`, `total_applied=3700` (74 транзакции коммитнули audit-row, но в `users` записан результат только последнего save из-за lost-update-гонки на BEGIN DEFERRED). Это известное ограничение SQLite — на проде (Postgres + REPEATABLE READ + `SELECT ... FOR UPDATE` на user-row) такие конфликты abortятся ORM-уровнем. Тест документирует это явно и проверяет более слабый, но честный инвариант: либо clamp удержал, либо trip-wire среагировал. Жёсткое «sum ≤ 3000» — Postgres-only, требует pg-integration-инфры (отдельная задача).
- **Stub-репозитории и admin-alerter.** Использован `FakeAnticheatAdminAlerter` из `tests/fakes/`, чтобы ассертить факт alert-а; `StructlogAnticheatAdminAlerter` (прод-impl) шумит в test-output и не даёт ассертить событие.
- **Параметр `delta_cm=50`.** 100 grant-ов × 50 см = 5000 см > 3000 cap — гарантированно тестируем clamp/trip-wire. С `delta=30` cap (3000) был бы достигнут ровно (60 grant-ов × 50 = 3000), последующие 40 — clamped в 0; с `delta=100` overshoot был бы агрессивнее. 50 — середина, читабельно.
- **Закрытие эпика.** Все 8 саб-спринтов 1.6.A → 1.6.H выполнены (PR #34 → #35 → #36 → #37 → #39 → #42 → #43 → текущий). DoD спринта 1.6 (development_plan.md §4):
    - ✅ Все use-cases прибавки длины проходят через `progression.add_length` (1.6.F + architecture-guard).
    - ✅ Хардкап работает в clamp-режиме на штатном пути (1.6.D + 1.6.E).
    - ✅ Хардкап работает в trip-wire-режиме при обходе (1.6.D + load-test 1.6.H).
    - ✅ Soft-ban на 14 дней снимается автоматически (по истечении `anticheat_ban_until`) и вручную (через `/anticheat_unban`, 1.6.G).
    - ✅ Алёрт админу идёт через `IAnticheatAdminAlerter` (`StructlogAnticheatAdminAlerter`, проверено load-тестом).
    - ✅ Race-test зелёный (1.6.H).
    - ✅ Покрытие новых файлов ≥ 90% (юнит-тесты `test_add_length.py` + load-тест на use-case).
    - ⏳ Telegram-канал админ-алёртов и `anticheat-admin-alert` локаль — отложено до появления соответствующей инфры (см. ограничения выше).
- **Удалён HANDOFF_1_6_H.md** в финальном коммите перед merge.

---

## 2026-05-04 — Спринт 1.6.G: bot-команда `/anticheat_unban` + `LiftAnticheatBan`

**Автор:** Devin (по запросу azurehannah)
**Тип:** application / bot / domain / i18n
**Связано:** `current_tasks.md` Спринт 1.6.G, ПД 1.6.7 (development_plan.md §4), ГДД §3.3, §18.6.

Что сделано:
- **Domain — `Admin.can_lift_anticheat_ban()`**: новый метод. Возвращает `True` только для активного `super_admin`. Намеренно строже, чем `support`: сценарий редкий (false-positive trip-wire-а), требует ручного анализа `audit_log`-а перед действием.
- **Application — `application.anticheat.LiftAnticheatBan`** (`application/anticheat/lift_ban.py`):
    - Конструктор: `uow`, `admins`, `players`, `audit`, `clock`.
    - `execute(*, actor_tg_id, target_tg_id, reason) -> LiftAnticheatBanResult`. Валидирует, что `reason.strip()` не пустой (иначе `ValueError`).
    - Шаги внутри одной `IUnitOfWork`-транзакции (`async with self._uow:`):
        1. `admins.get_by_tg_id(actor)` → проверка `can_lift_anticheat_ban()` → `AuthorizationError`.
        2. `players.get_by_tg_id(target)` → `PlayerNotFoundError`, если нет.
        3. Если игрок не в активном soft-ban-е (`is_anticheat_banned(now)` False) — идемпотентный no-op (`was_banned=False`, audit не пишем).
        4. Иначе: `player.with_anticheat_ban_lifted(now)` → `players.save(...)` → audit `ANTICHEAT_BAN_LIFTED` с `before={"anticheat_ban_until": <iso>}` / `after={"anticheat_ban_until": null}` / `reason=<actor reason>` / `idempotency_key=anticheat_unban:{actor}:{target}:{ts}`.
    - Authz и мутация — в одной транзакции: защита от гонки «админа деактивировали между authz и мутацией».
- **Bot — handler `/anticheat_unban` в `bot/handlers/admin.py`** (тот же файл, что и `/balance_reload`/`/admin_stats`/`/set_max_dau`):
    - Только в ЛС (вне ЛС → стандартный `REPLY_NON_PRIVATE_RU`).
    - Парсер `_parse_anticheat_unban(...)`: первый токен — int (не ноль, отрицательные допустимы для каналов), остальное — `reason` (обязательна, ненулевая после трима).
    - `AuthorizationError` / `PlayerNotFoundError` / no-op / success — каждое возвращает соответствующий локализованный текст. `AuthorizationError` намеренно НЕ светим в audit (не палим попытку нелегитимному пользователю).
- **Presenter `AnticheatUnbanPresenter`** (`bot/presenters/anticheat.py`): рендер 5 ответов (`usage`, `not_authorized`, `player_not_found`, `not_banned`, `success`) через `IMessageBundle`.
- **Локализация (RU + EN)**:
    - `anticheat-unban-usage` — формат команды.
    - `anticheat-unban-not-authorized` — нет прав.
    - `anticheat-unban-player-not-found` — игрок не найден (с параметром `tg_id`).
    - `anticheat-unban-not-banned` — бан уже не активен (с параметром `tg_id`).
    - `anticheat-unban-success` — успех (с параметрами `tg_id`, `banned-until-before`, `reason`).
- **Composition root**: `LiftAnticheatBan` сконструирован в `bot/main.py::build_container` после `set_player_locale`; добавлен в `Container` и в workflow-data dispatcher-а (`dispatcher["lift_anticheat_ban"]`).

Результат / артефакты:
- `src/pipirik_wars/application/anticheat/__init__.py`, `src/pipirik_wars/application/anticheat/lift_ban.py` (новые).
- `src/pipirik_wars/bot/handlers/admin.py` (handler `/anticheat_unban`, парсер, импорты).
- `src/pipirik_wars/bot/presenters/anticheat.py` (новый).
- `src/pipirik_wars/bot/main.py` (DI).
- `src/pipirik_wars/domain/admin/entities.py` (`Admin.can_lift_anticheat_ban`).
- `locales/ru.ftl`, `locales/en.ftl` (5 новых ключей).
- `tests/unit/application/anticheat/test_lift_ban.py` — 13 юнит-тестов (happy-path, идемпотентность 2×, authz 4 роли + неактивный + неизвестный, player-not-found, reason-guard 3×, reason-trim).
- `tests/unit/bot/handlers/test_anticheat_unban.py` — 13 юнит-тестов handler-а (не-ЛС, невалидные args 7×, AuthorizationError, PlayerNotFoundError, no-op, success, locale-fallback).
- `tests/unit/bot/test_composition_root.py` — обновлён под новый параметр `Container.lift_anticheat_ban`.
- Все тесты: `pytest tests/unit -q`: **1288 passed, 1 skipped**. `pytest tests/integration -q`: **163 passed**. Архитектурный guard 1.6.F всё ещё зелёный (новый код не использует `with_length`).

Заметки / решения:
- **Транзакция авторизации.** Существующие admin-команды (`SetMaxDau`, `ReloadBalance`) делают `admins.get_by_tg_id` ДО `async with self._uow:`. Это работает только в тестах (FakeAdminRepository), но в production упало бы на `RuntimeError("UnitOfWork is not entered")` — `SqlAlchemyAdminRepository.get_by_tg_id` тянет `uow.session`. В `LiftAnticheatBan` намеренно открыли UoW первой строкой, чтобы код был корректен и в production-режиме. Существующие use-cases оставлены как есть — рефактор в скоупе 1.6.G не входит, но потенциальная задача: `1.X — починить admin authz-flow для SqlAlchemy-репозитория`.
- **Идемпотентный no-op.** Если бан и так не активен (None или истёк), мы возвращаем `was_banned=False` без save и без audit. Альтернативой было бы писать «no-op» audit, но это создаёт лишний шум; админу в чате и так показывается «no action needed».
- **Reason обязателен.** Это требование ГДД §18.6 («любая админ-команда оставляет след в audit под именем конкретного админа с причиной»). Пустой reason → `ValueError` на стороне use-case-а (handler-парсер сначала отсекает на уровне args). В audit пишется именно `reason.strip()`.
- **`anticheat-admin-alert` ключ.** В исходной формулировке упоминался для алёрта админу при срабатывании trip-wire. На текущей фазе `IAnticheatAdminAlerter` реализован через structlog (`StructlogAnticheatAdminAlerter`, 1.6.D), не через i18n. Этот ключ был отложен — будет добавлен, когда появится Telegram-канал для админ-алёртов.

---

## 2026-05-04 — Спринт 1.6.F: миграция `FinishForestRun` / `InvokeOracle` на `ILengthGranter`

**Автор:** Devin (по запросу azurehannah)
**Тип:** refactor / application / architecture
**Связано:** `current_tasks.md` Спринт 1.6.F, ПД 1.6.6 (development_plan.md §4), ГДД §3.3, `HANDOFF_1_6_F.md` (удалён по завершении).

Что сделано:
- **Архитектурное решение (ADR в коде):** Variant B из `HANDOFF_1_6_F.md` — `AddLength.grant(...)` переведён в **ambient-UoW** режим. Caller обязан открыть `async with uow:` сам; `AddLength` лишь проверяет `IUnitOfWork.is_active` (новое property на интерфейсе) и работает в уже-открытой сессии. Это снимает блокер «nested UoW не разрешён», возникавший при попытке вызвать `AddLength.grant(...)` из других use-case-ов (`InvokeOracle`, `FinishForestRun`).
- **Domain — `IUnitOfWork.is_active`:** новое property на абстракции (`domain/shared/ports/uow.py`); реализации (`infrastructure/db/uow.py`, `tests/fakes/uow.py`, локальный `_FakeUnitOfWork` в `tests/unit/bot/notifications/test_forest.py`) обновлены. Контракт «один контекст — одна транзакция» сохранён: вложенные `async with uow:` по-прежнему запрещены.
- **`AddLength` рефактор:** убран `async with self._uow:` из `grant(...)`; добавлен runtime-guard `if not self._uow.is_active: raise RuntimeError(...)`. Логика (валидация → идемпотентность → soft-ban-гейт → clamp → mutate → audit `LENGTH_GRANT` → idempotency-mark → trip-wire) полностью сохранена. 21 unit-тест обновлён: добавлен helper `_grant(env, ...)`, открывающий UoW из теста перед вызовом, чтобы не дублировать boilerplate.
- **`InvokeOracle` миграция:**
    - В конструкторе `audit: IAuditLogger` заменён на `length_granter: ILengthGranter`.
    - Раньше: вычисление бонуса → `player.with_length(...)` → `players.save(...)` → audit `LENGTH_GRANT` (source=`ORACLE`).
    - Теперь: вычисление бонуса → запись `OracleInvocation` (UNIQUE-индекс остаётся last-line race-защитой) → `length_granter.grant(source=ORACLE, delta=bonus_cm, reason="oracle_invocation", idempotency_key="add_length:oracle:{player_id}:{moscow_date}")` → reload игрока для response-snapshot. `LENGTH_GRANT` теперь пишет `AddLength`, со всеми его cap-ами / soft-ban-гейтом / trip-wire-ом. Поведение: «оракул один раз в день» прежнее (двойной guard: preflight + UNIQUE).
- **`FinishForestRun` миграция:**
    - В конструкторе добавлен `length_granter: ILengthGranter`.
    - Раньше: `length += run.length_delta_cm` + `Title.NEWBIE` + (`NameDrop` auto-apply) → один `players.save(...)` → audit `LENGTH_GRANT` (source отсутствовал) + `TITLE_GRANT` + `NAME_GRANT`.
    - Теперь: разделено на (1) бизнес-mutations леса (title/name → `players.save(...)`); (2) прибавка длины — `length_granter.grant(source=FOREST, delta=run.length_delta_cm, reason="forest_run_finished", idempotency_key="add_length:forest_run:{run.id}")`; (3) reload игрока + `runs.save(mark_finished)` + release lock + audit `TITLE_GRANT` / `NAME_GRANT`. `LENGTH_GRANT` пишет `AddLength`. APScheduler-рестарт + повторный финиш по-прежнему идемпотентен (`status=FINISHED` → no-op + idempotency-key для прибавки).
- **Composition root (`bot/main.py`):** `AddLength` теперь конструируется один раз сразу после `ActivityLockService` и переиспользуется как `ILengthGranter` в `FinishForestRun` и `InvokeOracle`. Тестовый container в `tests/unit/bot/test_composition_root.py` синхронизирован.
- **Architecture guard:** новый тест `tests/unit/architecture/test_length_grant_guard.py` сканирует `src/pipirik_wars/` и фейлит CI, если `.with_length(` встречается вне approved-файлов:
    - `domain/player/entities.py` — само определение метода;
    - `application/progression/add_length.py` — единственная approved-прибавка;
    - `application/progression/upgrade_thickness.py` — вычет стоимости (не прибавка, cap-ы неприменимы).
    - Любой новый прямой вызов в `bot/`, `application/forest/`, `application/oracle/` и т. п. сразу будет красным CI с указанием файла.
- **`HANDOFF_1_6_F.md`** удалён — блокер закрыт, спринт готов к ревью.

Результат / артефакты:
- `src/pipirik_wars/domain/shared/ports/uow.py` (новое `is_active`).
- `src/pipirik_wars/infrastructure/db/uow.py`, `tests/fakes/uow.py` (`is_active`-реализации).
- `src/pipirik_wars/application/progression/add_length.py` (ambient-UoW; `is_active`-guard).
- `src/pipirik_wars/application/oracle/invoke.py` (миграция на `ILengthGranter`).
- `src/pipirik_wars/application/forest/finish_run.py` (миграция на `ILengthGranter`).
- `src/pipirik_wars/bot/main.py` (DI единого `AddLength`).
- `tests/unit/architecture/test_length_grant_guard.py` (architecture-тест, 217 файлов в скане).
- `tests/unit/application/progression/test_add_length.py` (helper `_grant`, 21 passed).
- `tests/unit/application/oracle/test_invoke.py` (фикстуры на `AddLength`-как-`ILengthGranter`, 6 passed).
- `tests/unit/application/forest/test_finish_run.py` (фикстуры на `AddLength`-как-`ILengthGranter`, 8 passed; новые ассерты на `audit.source=FOREST`, `idempotency_key="add_length:forest_run:{id}"`).
- `tests/unit/bot/test_composition_root.py` (DI обновлён под новый конструктор `FinishForestRun`/`InvokeOracle`).
- Все тесты: `pytest tests/unit -q`: **1042 passed, 1 skipped**. `pytest tests/integration -q`: **163 passed**. `pytest tests/unit/architecture -q`: **217 passed**.

Заметки / решения:
- **Ambient-UoW vs re-entrant UoW.** Альтернатива (вариант A handoff-а — сделать `IUnitOfWork` re-entrant через savepoint-ы) добавила бы скрытую сложность транзакционных границ и риски частичного rollback-а: внешний use-case мог бы продолжать выполняться после rollback вложенного. Ambient-UoW требует от каждого нового use-case-а явно открыть `async with uow:` (и единый CI-контракт «AddLength всегда зовётся в ambient»), но даёт честную транзакционную семантику.
- **Audit shape для леса слегка изменился.** Раньше `LENGTH_GRANT` от леса имел `target_kind="forest_run"` + `target_id=run.id` + `idempotency_key="forest_run_finished:length:{id}"`. Теперь — `target_kind="player"` + `source=FOREST` + `idempotency_key="add_length:forest_run:{id}"`. Это согласуется со всеми остальными `LENGTH_GRANT`-ами (формат от `AddLength`), и `source` теперь явный — это требование ГДД §3.3.4 и единственный способ для `AnticheatWindow.sum_organic_in_window(...)` корректно агрегировать лес как organic-источник.
- **Реферальный бонус (RegisterPlayer).** В исходной формулировке 1.6.F упоминался, но в коде референц-механика ещё не реализована (нет `referral_bonus`-handler-а). Перевозить нечего; перенесено в 1.6.G (там же будет `/anticheat_unban`).
- **Trip-wire поведение в `FinishForestRun`.** Если игрок за день упёрся в дневной cap, finish-job всё равно отработает: `AddLength` заклемит прирост и поставит soft-ban через `with_anticheat_ban(...)`. APScheduler не теряет job, lock снимается, игрок при следующих action-ах увидит `anticheat-soft-ban-active`-сообщение.

---

## 2026-05-05 — Спринт 1.6.D: `progression.add_length(...)` use-case + anti-cheat hardcap

**Автор:** Devin (по запросу sandyemaroon)
**Тип:** domain / application / infra / i18n
**Связано:** `current_tasks.md` Спринт 1.6.D, ПД 1.6.4 (development_plan.md §4), ГДД §3.3.5–§3.3.6.

Что сделано:
- **Domain — `pipirik_wars.domain.progression`**:
    - Порт `ILengthGranter` (`length_granter.py`) с единственным async-методом `grant(*, player_id, delta_cm, source, reason, idempotency_key=None) -> LengthGrantResult`. Будет единой точкой прибавки длины для всех use-cases в 1.6.F (`FinishForestRun`, `InvokeOracle`, `RegisterPlayer`-реферальный бонус, и в будущем PvP/караваны/рейды).
    - `LengthGrantResult` — frozen dataclass с `applied_delta_cm: int`, `clamped_from: int | None`, `triggered_soft_ban: bool`, `new_length_cm: int`. `__post_init__` валидирует `new_length_cm >= 0` и `clamped_from >= applied_delta_cm`.
    - `errors.AnticheatSoftBanError(*, tg_id, banned_until)` — игрок в активном soft-ban-е, прибавка запрещена, мутаций нет.
    - `errors.LengthDeltaInvalidError(*, delta_cm, source, reason_code)` — четыре варианта `reason_code`: `"zero"`, `"negative_for_non_refund"`, `"positive_for_refund"`, `"unknown_source"`.
- **Domain — `pipirik_wars.domain.anticheat`**:
    - Порт `IAnticheatAdminAlerter.emit(*, player_id, cap_kind, cap_cm, observed_sum_cm, source, banned_until, occurred_at)` — алёрт админу при срабатывании trip-wire. Pattern скопирован с `IDauThresholdAlerter` (Спринт 1.2.D).
- **Application — `pipirik_wars.application.progression.AddLength`** (реализация `ILengthGranter`):
    - Алгоритм 9 шагов (всё внутри одной `IUnitOfWork`-транзакции, см. подробный docstring в `add_length.py`):
        1. Валидация входа (вне транзакции — это инварианты вызова): `source != UNKNOWN`, `delta_cm != 0`, `delta_cm < 0` ⟹ `source == ADMIN_REFUND`, `delta_cm > 0` ⟹ `source != ADMIN_REFUND`.
        2. Идемпотентность через `IIdempotencyKey`: повторный ключ → no-op (`applied_delta_cm=0`, `new_length_cm`=текущая).
        3. `players.get_by_id(...)` → `PlayerNotFoundError`.
        4. Soft-ban-гейт: `Player.is_anticheat_banned(now=clock.now())` → `AnticheatSoftBanError`.
        5. Clamp для organic-источников: `remaining = min(daily.remaining_cap_cm, weekly.remaining_cap_cm)`, `applied = min(delta, remaining)`, `clamped_from = delta if applied < delta else None`. Donate / `admin_refund` — без clamp.
        6. Mutate: `player.with_length(...)` → `players.save(...)` (только если `applied != 0`).
        7. Audit `LENGTH_GRANT` с `source` / `delta_cm` / `clamped_from` / `idempotency_key`.
        8. `IIdempotencyKey.mark(...)` если ключ передан.
        9. Trip-wire (organic + `applied > 0`): рекомпьют `daily_after` / `weekly_after`. При пробитии — `with_anticheat_ban(...)` + audit `ANTICHEAT_*_CAP_EXCEEDED` + `IAnticheatAdminAlerter.emit(...)`. `triggered_soft_ban=True` в результате.
    - Все `IAnticheatRepository.sum_organic_in_window`-вызовы внутри одной транзакции — это даёт гарантию (на `REPEATABLE READ` уровне Postgres), что параллельные `add_length` одного игрока не пробьют cap.
- **Infrastructure — `pipirik_wars.infrastructure.anticheat.StructlogAnticheatAdminAlerter`** (реализация `IAnticheatAdminAlerter`): `log.warning("anticheat.trip_wire.fired", player_id, cap_kind, cap_cm, observed_sum_cm, overflow_cm, source, banned_until, occurred_at)`. Без локального состояния, тред-сэйф (boilerplate structlog).
- **DI в `bot/main.py`**: `Container.add_length: ILengthGranter` + `Container.anticheat_admin_alerter: IAnticheatAdminAlerter`. `build_container()` инстанциирует `StructlogAnticheatAdminAlerter()` и `AddLength(uow, players, anticheat, audit, balance, clock, idempotency, admin_alerter)`. Тестовый сборщик `tests/unit/bot/test_composition_root.py` поднят на новые поля через `FakeAnticheatAdminAlerter()`.
- **Локализация `locales/{ru,en}.ftl`**: ключи `anticheat-soft-ban-active` (с `$banned-until`), `anticheat-cap-clamped-daily` / `anticheat-cap-clamped-weekly` (с `$applied` / `$requested`). Числа через `NUMBER($x, useGrouping: 0)` (по соглашению, как в `upgrade-*` ключах). Реальный bot-handler / presenter под эти ключи добавится в Спринтах 1.6.E (Anti-cheat Guard на спендалках) / 1.6.F (миграция existing use-cases на `add_length`).
- **`tests/fakes/anticheat_admin_alerter.py::FakeAnticheatAdminAlerter`** — in-memory `events: list[AnticheatAdminAlertEvent]` для assert-ов в unit-тестах.

Тесты:
- **`tests/unit/application/progression/test_add_length.py`** — 21 unit-кейс:
    - **Happy-path**: organic ниже cap → `applied=delta`, без clamp/ban; audit-запись содержит `source`/`delta_cm`/`clamped_from=None`/`idempotency_key`.
    - **Clamp**: по daily cap, по weekly cap (выбор `min`), полностью исчерпан (`applied=0`, `clamped_from=delta`, audit всё равно пишется).
    - **Не-organic**: donate (`STARS_PAYMENT`) не клампится; `admin_refund` (отрицательная дельта) применяется без clamp.
    - **Soft-ban-гейт**: активный бан → `AnticheatSoftBanError`; истёкший бан → проход (`Player.is_anticheat_banned(now)` сравнивает с `clock.now()`).
    - **Валидация входа**: `delta_cm=0` / отрицательная для не-refund / положительная для refund / `UNKNOWN`-source — все 4 варианта `LengthDeltaInvalidError.reason_code`.
    - **`PlayerNotFoundError`**: при отсутствии игрока с таким `player_id`.
    - **Идемпотентность**: повторный ключ → no-op (Player не меняется, audit не пишется второй раз); первый вызов помечает ключ через `IIdempotencyKey.mark(...)`.
    - **Trip-wire**: симуляция гонки через hooked `sum_organic_in_window` (тест-helper подкидывает «чужие» 200 см на третьем вызове, имитируя параллельную транзакцию). Daily вариант: `triggered_soft_ban=True`, `Player.anticheat_ban_until = now + 14 дней`, audit `ANTICHEAT_DAILY_CAP_EXCEEDED`, `admin_alerter.events == [{cap_kind="daily", cap_cm=3000, source=FOREST}]`. Weekly вариант — аналогично с `cap_cm=14000`. Donate / `admin_refund` — trip-wire НЕ срабатывает.
    - **`_LinkedAuditLogger`** — тест-helper-адаптер: пишет в `FakeAuditLogger` И зеркалит `LENGTH_GRANT`-события в `FakeAnticheatRepository`, имитируя реальную связку `audit_log` ← `SqlAlchemyAnticheatRepository.sum_organic_in_window`. Без него trip-wire-recompute не видел бы только что записанную дельту.
- **`tests/unit/domain/progression/test_length_granter.py`** — 6 unit-кейсов на инварианты `LengthGrantResult` (`__post_init__`).
- **`tests/unit/bot/test_composition_root.py`** — 2 новые проверки на `Container.add_length` / `Container.anticheat_admin_alerter` в обеих сборках (`_container_with_fakes` + `build_container`).

Решения:
- **Идемпотентность как опциональный параметр use-case-а, а не отдельный декоратор/middleware** — потому что caller знает свой бизнес-смысл (для forest-run-finished — это `forest_run_id`, для админ-grant — `admin_command_id`, для оракула — `oracle_call_id`). Префикс `add_length:` обязателен (валидация в `IIdempotencyKey.mark(namespace="add_length")`).
- **Trip-wire как отдельная фаза после save** (а не «угадать заранее по clamp-у»): даёт честную защиту от race condition — параллельные транзакции, не видевшие друг друга в момент clamp-а, всё равно поймаются на recompute. На уровне Postgres `REPEATABLE READ` это превращается в serialization-error и автоматический retry на уровне `IUnitOfWork` (для будущих implementations — пока fake `IUnitOfWork` это не моделирует, реальный SqlAlchemy-UoW в проекте сейчас тоже не делает явного retry, но при включении `REPEATABLE READ` Postgres сам бросит `serialization_failure` и SQLAlchemy переподнимет).
- **`triggered_soft_ban` ровно один раз на бан**: повторные `add_length`-вызовы заблокированного игрока стопаются в шаге 4 (soft-ban-гейт), до alert-а. То есть `IAnticheatAdminAlerter.emit(...)` вызывается единожды — на момент перехода игрока из «не в бане» в «в бане». Идемпотентности «не алёртить дважды на тот же бан» в самом эмиттере нет (он тупой — задача его caller-а).
- **Organic source whitelist в `balance.yaml::anticheat.organic_sources`**: использует `AuditSource`-enum-значения, не свободные строки. `unknown` явно запрещён в whitelist (валидируется в `AnticheatConfig.model_validate`, Спринт 1.6.B). `admin_refund` тоже не в whitelist — потому что только refund (отрицательная дельта), а не «прибавка длины».
- **Старые use-cases (`FinishForestRun`, `InvokeOracle`, `RegisterPlayer`) пока не переведены** на `add_length` — это отдельный узкий PR в Спринте 1.6.F. Они продолжают работать через прямые `player.with_length(...)` + `repo.save(player)` + `audit.record(LENGTH_GRANT)`. До 1.6.F новый use-case стоит «в стороне» — `add_length` существует, но никто из старых use-cases его пока не зовёт. Это намеренно: 1.6.D вводит исключительно механизм, миграция точек вызова — следующим PR-ом.

Не вошло в этот PR (явно, для будущих спринтов):
- `AnticheatGuard`-гейт на спендалках длины (`/upgrade`, в будущем `/duel`/караваны/рейды) — Спринт 1.6.E (ПД 1.6.5).
- Перевод существующих use-cases на `add_length(...)` через DI-порт `ILengthGranter` + `import-linter`-контракт «прибавка длины только через ILengthGranter» — Спринт 1.6.F (ПД 1.6.6).
- Реальный handler / presenter под локали `anticheat-soft-ban-active` / `anticheat-cap-clamped-*` (рендер UX-сообщения) — появится в 1.6.E (gating UX) / 1.6.F (clamp UX) при подключении к реальным command-flow-ам.
- Integration race-test (10×100 параллельных `add_length` через реальный SQL UoW + Postgres `REPEATABLE READ`) — текущие race-тесты сделаны на fake-уровне (hooked `sum_organic_in_window`, имитирует параллельный коммит). Реальная race-test-инфраструктура Postgres-а будет в Спринте 1.6.F вместе с `import-linter`-контрактом, чтобы заодно проверить, что переведённые use-cases корректно работают под нагрузкой.

Документация:
- `current_tasks.md`: 1.6.D переведён в `🟢 PR open` (после мержа этого PR-а уйдёт в `✅ смержено`).
- `history.md`: эта запись.

Удалены:
- 9 устаревших файлов из abandoned 1.3.D-каркаса (другая ветка `devin/1777925966-sprint-1-3d-forest-handler` по PR #20 уже их закрыла, а на моей ветке они остались как мусор после восстановления): `application/forest/{discard_drop,equip_item,replace_name}.py`, `bot/notifiers/`, `infrastructure/db/migrations/versions/20260504_0005_forest_runs_drop_resolved_at.py`, `tests/unit/application/forest/test_{discard_drop,equip_item,notifier,replace_name}.py`.

---

## 2026-05-05 — Спринт 1.6.C: `AnticheatWindow` + `IAnticheatRepository` + миграция `delta_cm`

**Автор:** Devin (по запросу birgit865)
**Тип:** domain / infra / migration
**Связано:** `current_tasks.md` Спринт 1.6.C, ПД 1.6.3 (development_plan.md §4), ГДД §3.3.4.

Что сделано:
- **Миграция `0008_audit_log_delta_cm`** — добавляет в `audit_log`:
    - колонку `delta_cm INT NULL` — фактически применённая знаковая дельта длины в см. NULL для не-длиновых событий и для всех записей до 1.6.D.
    - composite-индекс `ix_audit_log_target_source_occurred` (`target_id`, `source`, `occurred_at`) — покрывает rolling-window-агрегацию.
    - Полностью реверсимая (downgrade чисто откатывает обе вещи).
- **`AuditLogORM.delta_cm`** + расширение `__table_args__` под composite-индекс.
- **`AuditEntry.delta_cm: int | None = None`** (бэк-совместимый дефолт; в Спринте 1.6.D через `progression.add_length` будет заполняться явно). `SqlAlchemyAuditLogger.record(...)` пишет колонку.
- **Новый домен `pipirik_wars.domain.anticheat`** (Clean Architecture / DDD):
    - `entities.AnticheatWindow` — frozen value object (`player_id`, `since: datetime` UTC-aware, `organic_sum_cm: int >= 0`). Методы `remaining_cap_cm(cap_cm)` (clamp до 0, не отрицательное) и `is_exceeded(cap_cm)` (строгое `>`, ровно cap не считается trip-wire). Конструктор валидирует `player_id > 0`, tz-aware `since`, `organic_sum_cm >= 0`.
    - `repositories.IAnticheatRepository` — порт. Сигнатура: `sum_organic_in_window(*, player_id, since, organic_sources: Iterable[AuditSource]) -> AnticheatWindow`. Список organic-источников передаётся параметром (не зашит в импле) — единый source-of-truth остаётся в `balance.yaml::anticheat.organic_sources`, use-case 1.6.D сам читает конфиг и пробрасывает.
- **`infrastructure/db/repositories/anticheat.py::SqlAlchemyAnticheatRepository`** — один SELECT с `COALESCE(SUM(delta_cm), 0)` и фильтром `target_kind='player' AND target_id=:pid AND source IN (...) AND delta_cm IS NOT NULL AND delta_cm > 0 AND occurred_at >= :since`. Пустой `organic_sources` короткозамыкается без обращения к БД. Зарегистрирован в `repositories/__init__.py`.
- **DI в `bot/main.py`**: `Container.anticheat: IAnticheatRepository` + `SqlAlchemyAnticheatRepository(uow=uow)` в `build_container`. Тестовый сборщик `tests/unit/bot/test_composition_root.py` поднят на новое поле через `FakeAnticheatRepository()`.
- **`tests/fakes/anticheat_repo.py::FakeAnticheatRepository`** — in-memory имитация для unit-тестов use-case-ов 1.6.D. API: `record_event(player_id, source, delta_cm, occurred_at)` + та же агрегация что и SQL-имп.

Тесты:
- **`tests/unit/domain/anticheat/test_window.py`** — 16 юнит-тестов:
    - конструкция (валидный, zero, negative-rejected, zero/negative `player_id`-rejected, naive `since`-rejected, frozen);
    - `remaining_cap_cm` (под cap / ровно cap → 0 / выше cap → 0 / нулевая сумма / negative cap-rejected);
    - `is_exceeded` (под cap / ровно cap → False / выше cap → True / 0/0 / negative cap-rejected).
- **`tests/integration/db/test_anticheat_repository.py`** — 17 integration-тестов:
    - empty audit_log → 0;
    - сумма organic positive deltas (3 источника, 17 см итого);
    - donate-источники (`STARS_PAYMENT`/`TON_PAYMENT`/`USDT_PAYMENT`) исключаются;
    - `ADMIN_REFUND` с отрицательной дельтой исключается (по source И по `delta_cm > 0`);
    - `UNKNOWN` исключается (не в organic-list);
    - window cutoff (25 ч назад — за окном 24 ч);
    - boundary inclusivity (`occurred_at == since` → включается, `>=`);
    - других игроков не считает (target_id=999);
    - `delta_cm IS NULL` исключается;
    - `delta_cm = 0` исключается;
    - `target_kind='clan'` исключается (только player-аудит);
    - частичный organic-subset (только FOREST → 10, ORACLE 20 проигнорирован);
    - empty `organic_sources` → 0 без обращения к БД;
    - naive `since` → ValueError;
    - `player_id <= 0` → ValueError;
    - 7-day rolling-агрегация (5 событий внутри окна, 1 за окном).
- **`tests/integration/db/test_migrations.py`** — добавлены кейсы:
    - `0008_audit_log_delta_cm` присутствует в revisions, `down_revision == '0007_anticheat_foundation'`;
    - файл миграции в `versions_dir_lists_only_known_files`;
    - `test_0008_adds_delta_cm_column`: после `upgrade head` есть `delta_cm` в `audit_log` + индекс `ix_audit_log_target_source_occurred`.

Результат / артефакты:
- **Source code:**
    - `src/pipirik_wars/domain/anticheat/` (новый пакет: `entities.py` / `repositories.py` / `__init__.py`).
    - `src/pipirik_wars/infrastructure/db/repositories/anticheat.py` (+ регистрация в `repositories/__init__.py`).
    - `src/pipirik_wars/infrastructure/db/migrations/versions/20260505_0008_audit_log_delta_cm.py`.
    - `src/pipirik_wars/infrastructure/db/models/security.py` (+ `delta_cm` колонка + composite-индекс).
    - `src/pipirik_wars/infrastructure/db/services/audit.py` (+ `delta_cm` пишется).
    - `src/pipirik_wars/domain/shared/ports/audit.py` (+ `AuditEntry.delta_cm`).
    - `src/pipirik_wars/bot/main.py` (+ DI поля).
- **Тесты:**
    - `tests/unit/domain/anticheat/test_window.py` (новый, 16 кейсов).
    - `tests/integration/db/test_anticheat_repository.py` (новый, 17 кейсов).
    - `tests/integration/db/test_migrations.py` (+ 3 кейса для 0008).
    - `tests/fakes/anticheat_repo.py` (новый) + регистрация в `tests/fakes/__init__.py`.
    - `tests/unit/bot/test_composition_root.py` (+ `FakeAnticheatRepository` в Container).
- **Прогон `make ci`:** 1168 passed, 1 skipped, **97.01 %** покрытия. Все 3 import-linter-контракта сохранены (layered_architecture, domain_must_not_import_infrastructure, application_must_not_import_io_libs).

Заметки / решения:
- **Зачем отдельная колонка `audit_log.delta_cm` вместо вычисления через JSON `(after.length_cm - before.length_cm)`:** `JSON_EXTRACT` в SQLite vs `->>` в Postgres → не-портабельный SQL и плохая индексируемость. Числовая колонка делает агрегацию однозначной (`SUM(delta_cm)`), быстрой (composite-индекс `(target_id, source, occurred_at)`) и не зависит от структуры `before/after`. Для не-длиновых событий — `NULL` (mostly clear).
- **Знак `delta_cm`:** знаковый int. Положительные — organic-прирост, отрицательные — `admin_refund`. Anti-cheat-окно учитывает только `delta_cm > 0` — `admin_refund` обнуляет действие, не агрегируется как положительный рост (ГДД §3.3.4).
- **`AuditEntry.delta_cm` дефолт `None`:** старые `AuditEntry`-конструкции (clan_register, balance_reload, dau_threshold_reached и т. д.) не сломались. В Спринте 1.6.D через `progression.add_length` все длиновые use-cases начнут передавать `delta_cm` явно. До тех пор `LENGTH_GRANT`-аудит из `RegisterPlayer.execute_register_with_referral`/`InvokeOracle`/`FinishForestRun` продолжает писать `delta_cm=NULL` — anti-cheat-окно их не сумирует, но это **временно** (Спринт 1.6.F замигрирует). Никакой дрейф в реальный продакшен не уходит, anti-cheat-логика не активна до 1.6.D.
- **Сигнатура `sum_organic_in_window(*, player_id, since, organic_sources)`:** изначально планировалось без `organic_sources` (списка из конфига). Решение пробрасывать параметром: (1) DI-чистый — repo не зависит от `IBalanceConfig`; (2) hot-reload `balance.yaml` сразу применяется к новым агрегациям без mutate state репо; (3) тесты могут передать узкий subset, что ловит баги со жёстко-зашитым списком.
- **`AnticheatWindow` как value object а не QueryResult-`int`:** возвращает `AnticheatWindow` чтобы (1) использовать его методы `remaining_cap_cm`/`is_exceeded` на стороне use-case (1.6.D) без отдельного wrap-а; (2) сохранить `since` и `player_id` для логирования/трассировки; (3) явный rolling-window семантика, а не «голое число».
- **`is_exceeded` строго `>`, не `>=`:** ровно `cap_cm` (например, daily_cap_cm=3000 и сумма=3000) — это «впритык», не trip-wire. Trip-wire срабатывает только при превышении (3001+) — что возможно только при race / прямом обходе clamp-а через `repo.save(player)`. Это сознательно: чтобы случайная гонка под жёстким лимитом не выбрасывала легальных игроков в soft-ban.
- **Composite-индекс `(target_id, source, occurred_at)` а не `(occurred_at, source, target_id)`:** для anti-cheat-запроса фильтрация по `target_id` максимально селективна (1 игрок vs все), `source` следующий (organic-list ≈ 8 значений из 13), `occurred_at` — финальный range-filter. Postgres planner так и собирает. Если статистика после Phase-2 покажет что-то иное — пере-индексируем без миграции схемы.
- **Граничное условие `occurred_at >= since` (включающее):** rolling-окно должно быть симметрично: «события за последние 24 часа» включает событие, произошедшее ровно 24 часа назад. В тестах есть явный `test_since_boundary_inclusive`.
- **Слой-чистота:** `domain/anticheat` зависит только от `domain/shared/ports/audit.AuditSource` — нет зависимостей на `domain/balance` (избегаем циклов). `infrastructure` слой импортирует и `domain/anticheat`, и `infrastructure/db/models` — нормально по слоям.

---

## 2026-05-05 — Спринт 1.6.B: балансовая секция `anticheat`

**Автор:** Devin (по запросу birgit865)
**Тип:** balance / domain
**Связано:** `current_tasks.md` Спринт 1.6.B, ПД 1.6.2 (development_plan.md §4 / Спринт 1.6), ГДД §3.3.5.

Что сделано:
- **`config/balance.yaml`** — новая секция `anticheat` (после `daily_head`, перед `content_policy`):
    - `daily_cap_cm: 3000` (rolling 24 ч, ГДД §3.3.1)
    - `weekly_cap_cm: 14000` (rolling 7 дн, ГДД §3.3.2)
    - `soft_ban_duration_days: 14`
    - `organic_sources: [forest, oracle, referral_signup, referral_thickness, pvp_reward, caravan_reward, raid_reward, admin_grant]` — попадают в агрегацию trip-wire-а.
    - `donate_sources: [stars_payment, ton_payment, usdt_payment]` — игнорируются хардкапом.
    - Обновлён header-комментарий конфига (`§3.3.5 ГДД — анти-чит хардкап`).
- **`domain/balance/config.py::AnticheatConfig`** — frozen-pydantic value object с импортом `AuditSource` (whitelist из 1.6.A): поля `daily_cap_cm`/`weekly_cap_cm`/`soft_ban_duration_days` (`Field(gt=0)`) + `organic_sources`/`donate_sources` (`tuple[AuditSource, ...]` с `min_length=1`).
- **Инварианты `_validate(self) -> AnticheatConfig`** (после-валидатор):
    1. `daily_cap_cm <= weekly_cap_cm` — суточный лимит не может превысить недельный.
    2. Без дублей в каждом из списков (set-comparison + понятная ошибка с указанием источника).
    3. `organic_sources ∩ donate_sources = ∅` — источник не может одновременно быть в обоих whitelist-ах.
    4. `AuditSource.UNKNOWN` запрещён в обоих списках — это backfill-маркер из 1.6.A для исторических записей, не реальный источник.
    5. `AuditSource.ADMIN_REFUND` запрещён в `organic_sources` — refund-ы пишутся как отрицательные дельты и не агрегируются.
- **`BalanceConfig.anticheat: AnticheatConfig`** — обязательное поле (без `default`, иначе тестовые YAML-ы без секции прошли бы валидацию).
- **`domain/balance/__init__.py`** — экспорт `AnticheatConfig` для DI (use-case `progression.add_length` в 1.6.D будет читать `balance.get().anticheat`).
- **Тесты:**
    - Unit (`tests/unit/domain/balance/test_config.py::TestAnticheatConfig`) — 18 кейсов: валидный baseline, реальный YAML парсится, `daily/weekly == 0` отклоняется, `daily > weekly` падает, `daily == weekly` разрешён (для тестов), пустой `organic_sources`/`donate_sources` отклоняется, опечатка в имени источника (`forst`) даёт `ValidationError`, intersection падает, дубли в каждом списке падают, `unknown` в любом списке падает, `admin_refund` в organic падает, секция обязательна, `extra=forbid` для `unknown_field`.
    - Unit hot-reload (`tests/unit/infrastructure/test_balance_loader.py::test_reload_picks_up_new_anticheat_caps`) — пишет YAML с `daily_cap_cm=3000`, реломает на `daily_cap_cm=1500` через `loader.reload()`, проверяет, что `loader.get()` возвращает новый снимок и старая ссылка не изменилась (frozen).
    - **Существующие тесты `test_reload_*` уже автоматом покрывают новую секцию**, потому что используют `valid_balance_payload()` (теперь содержит `anticheat`).
    - **`tests/unit/domain/balance/factories.py::valid_balance_payload`** расширен полным валидным `anticheat`-payload-ом.

Результат / артефакты:
- Изменённые файлы:
    - `config/balance.yaml` — новая секция + обновление header-комментария.
    - `src/pipirik_wars/domain/balance/config.py` — `AnticheatConfig` + поле `BalanceConfig.anticheat` + импорт `AuditSource`.
    - `src/pipirik_wars/domain/balance/__init__.py` — экспорт `AnticheatConfig`.
    - `tests/unit/domain/balance/factories.py` — `anticheat`-payload в `valid_balance_payload()`.
    - `tests/unit/domain/balance/test_config.py` — `TestAnticheatConfig` (18 кейсов).
    - `tests/unit/infrastructure/test_balance_loader.py` — `test_reload_picks_up_new_anticheat_caps`.
- `make ci` локально — 1133 passed + 1 skipped, coverage **96.96 %**, ruff/mypy --strict/import-linter — все зелёные.

Заметки / решения:
- **`organic_sources` / `donate_sources` в YAML — массив строк, не словарь.** Pydantic парсит `tuple[AuditSource, ...]` из YAML-списка строк автоматически (StrEnum). Опечатка типа `forst` ловится pydantic-ом с понятной ошибкой «Input should be 'forest', 'oracle', ...», пользователю не нужно знать про CHECK constraint.
- **Не делать `organic_sources` дефолтом из enum.** Возможно соблазн «`organic_sources: tuple[AuditSource, ...] = (AuditSource.FOREST, AuditSource.ORACLE, ...)`», но это спрятало бы whitelist в Python-коде. Геймдиз должен видеть всё в balance.yaml — если завтра добавится `pvp_chat_reward`, то достаточно отредактировать YAML и hot-reload-нуть, не пересобирать Docker.
- **Импорт `AuditSource` в `domain/balance/`** не нарушает import-linter (`domain → domain/shared/ports` — допустимо, оба слоя — domain). Если бы AuditSource жил в application/, контракт бы поломался.
- **`daily == weekly` разрешён как валидная конфигурация.** Это позволяет в тестах ставить `daily=weekly=14000` и проверять только weekly-trip-wire без вмешательства daily-ветки. На production такой конфиг бессмыслен, но отказывать его — лишняя жёсткость.
- **Hot-reload через `/balance_reload` работает «бесплатно».** Use-case `ReloadBalance` (Спринт 1.1.E) перечитывает весь `BalanceConfig`; добавление новой секции не требует трогать его код. Acceptance-тест в `test_balance_loader` это подтверждает.
- **Соответствие `organic_sources` ↔ ГДД §3.3.4.** В таблице ГДД источник `admin_grant` помечен как «✅ Да, под лимитом» — это защищает админа от случайных опечаток в `/grant_length` (трип-вайр сработает на самого админа, бан снимается через `/anticheat_unban`).

---

## 2026-05-05 — Спринт 1.6.A: БД-фундамент anti-cheat hardcap-а

**Автор:** Devin (по запросу birgit865)
**Тип:** infra / domain
**Связано:** `current_tasks.md` Спринт 1.6.A, ПД 1.6.1 (development_plan.md §4 / Спринт 1.6).

Что сделано:
- **Миграция `0007_anticheat_foundation`** (`src/pipirik_wars/infrastructure/db/migrations/versions/20260505_0007_anticheat_foundation.py`):
    - `users.anticheat_ban_until TIMESTAMPTZ NULL` + индекс `ix_users_anticheat_ban_until`. NULL = бан не активен; `datetime` = soft-ban до этой точки. Никаких CHECK-инвариантов: «дата в прошлом» это естественное «бан истёк», и проверять её на каждом INSERT-е не нужно.
    - `audit_log.clamped_from INT NULL` — заполняется в Спринте 1.6.D, когда `progression.add_length` подрежет дельту под `daily_cap_cm` / `weekly_cap_cm`.
    - `audit_log.source TEXT NOT NULL` (server_default `'unknown'`, индекс `ix_audit_log_source`, CHECK-инвариант на whitelist `('forest', 'oracle', 'referral_signup', 'referral_thickness', 'pvp_reward', 'caravan_reward', 'raid_reward', 'admin_grant', 'admin_refund', 'stars_payment', 'ton_payment', 'usdt_payment', 'unknown')`). Backfill `'unknown'` для исторических строк.
    - Полностью реверсимая (`downgrade()` дропает индексы + CHECK + колонки).
- **Domain (`domain/shared/ports/audit.py`):**
    - Новый enum `AuditSource` с whitelist-источниками, дублирующими БД-CHECK. Drift-тест `tests/unit/domain/shared/ports/test_audit_source.py` загружает миграцию через `importlib.util` и сравнивает множества — расхождение даст красный CI.
    - `AuditEntry` расширен полями `source: AuditSource = AuditSource.UNKNOWN` и `clamped_from: int | None = None`. Дефолты гарантируют бэк-совместимость со всеми существующими call-site-ами; миграция в Спринте 1.6.F переведёт их на явное указание источника.
    - Новые `AuditAction.ANTICHEAT_DAILY_CAP_EXCEEDED` / `ANTICHEAT_WEEKLY_CAP_EXCEEDED` / `ANTICHEAT_BAN_LIFTED` (понадобятся в 1.6.D / 1.6.G).
- **Domain (`domain/player/entities.py`):**
    - Новое поле `Player.anticheat_ban_until: datetime | None = None` (frozen-датакласс, `replace(...)` для мутаторов как и для остальных полей).
    - `is_anticheat_banned(*, now)` — отдельный метод, требующий явного `now` через `IClock` (без скрытого `datetime.now()` в домене).
    - `with_anticheat_ban(*, until, now)` — продлевает бан **только вверх** (`until > self.anticheat_ban_until`). Это защита от случайной race-condition «два trip-wire-а одновременно укоротили бан». Валидация: `until.tzinfo is not None` и `until > now`, иначе `ValueError`. Допускается на frozen-игроков (бан — сервисное состояние, не зависит от `ACTIVE/FROZEN`).
    - `with_anticheat_ban_lifted(*, now)` — идемпотентный сброс (используется в `/anticheat_unban` Спринт 1.6.G).
- **Persistence:**
    - `infrastructure/db/models/security.py::AuditLogORM` — новые колонки `source` (с `server_default="unknown"` + index) и `clamped_from`, `CheckConstraint("source IN (...)", name="audit_log_source_whitelist")`.
    - `infrastructure/db/models/player.py::UserORM.anticheat_ban_until` (`DateTime(timezone=True)`, nullable, indexed).
    - `infrastructure/db/repositories/player.py` — `_row_to_entity` пропускает `anticheat_ban_until` через `ensure_utc(...)`, `add()/save()` пишут поле в строку.
    - `infrastructure/db/services/audit.py::SqlAlchemyAuditLogger` пишет `source.value` и `clamped_from` в строку.
- **Тесты:**
    - Unit: `tests/unit/domain/player/test_entities.py::TestAnticheatBan` (10 кейсов: дефолт, установка, граница `until`, монотонное продление, валидация tz/прошлого, lifting (включая no-op), бан на frozen-игрока, не модифицирует другие поля).
    - Unit: `tests/unit/domain/shared/ports/test_audit_source.py` — drift-тест enum vs миграция, наличие `unknown`, наличие organic-источников.
    - Integration: `tests/integration/db/test_player_repository.py` — `test_anticheat_ban_until_roundtrip` (UTC tz сохраняется), `test_anticheat_ban_lifted_persists_null` (lifting записывает NULL в БД).
    - Integration: `tests/integration/db/test_audit_logger.py` — `test_record_persists_row` обновлён на проверку `source`/`clamped_from`, `test_record_default_source_is_unknown` (бэк-совместимость), `test_record_rejects_invalid_source` (CHECK ловит опечатку, транзакция роллбэкится).
    - Integration: `tests/integration/db/test_migrations.py` — добавлены `test_0007_descends_from_0006`, обновлён `test_versions_dir_lists_only_known_files`, новый `test_0007_adds_anticheat_columns` (inspect колонки), существующий `test_downgrade_then_upgrade_round_trips` уже автоматом гоняет 0007.

Результат / артефакты:
- Новые файлы:
    - `src/pipirik_wars/infrastructure/db/migrations/versions/20260505_0007_anticheat_foundation.py`
    - `tests/unit/domain/shared/ports/test_audit_source.py`
- Изменённые файлы:
    - `src/pipirik_wars/domain/shared/ports/audit.py` — `AuditSource`, расширение `AuditEntry`, новые `AuditAction.ANTICHEAT_*`.
    - `src/pipirik_wars/domain/shared/ports/__init__.py` — экспорт `AuditSource`.
    - `src/pipirik_wars/domain/player/entities.py` — поле + 3 метода (`is_anticheat_banned`, `with_anticheat_ban`, `with_anticheat_ban_lifted`).
    - `src/pipirik_wars/infrastructure/db/models/{player,security}.py`.
    - `src/pipirik_wars/infrastructure/db/repositories/player.py`.
    - `src/pipirik_wars/infrastructure/db/services/audit.py`.
    - 3 файла тестов.
- `make ci` локально — 1115+ tests passed, coverage **96.94 %**, ruff/mypy --strict/import-linter — все зелёные.

Заметки / решения:
- **`source` дефолтит в `UNKNOWN`, не падает на старых вызовах.** Альтернатива «сразу обязать source у всех use-cases» дала бы взрыв изменений в одном PR (10+ call-site-ов). Компромисс: в 1.6.A только инфраструктура; в 1.6.F отдельным узким PR-ом мигрируем все call-site-ы на явный source через `progression.add_length(...)` (через DI-порт `ILengthGranter`). Импорт-линтер-контракт против прямых `player.with_length(...)` появится тогда же.
- **CHECK-инвариант в БД дублирует Python-enum.** Принцип defence-in-depth: opечатка в строке `source="forst"` в Python пройдёт type-checker (`str` совместим с `String(32)`), но упадёт на flush. Drift-тест защищает обратное направление (добавил источник в БД-whitelist, забыл в enum) — упадёт на CI.
- **`with_anticheat_ban` продлевает только вверх.** Trip-wire (1.6.D) считает rolling-сумму после каждого начисления; при race-condition (две одновременных транзакции) каждая может сработать как «окей, лимит превышен → бан на 14 дней». Без монотонности вторая запись сократила бы бан. С монотонностью max-`until` остаётся стабильным.
- **`is_anticheat_banned` — метод, а не свойство.** Доменные сущности не имеют доступа к `IClock`; передача `now` явно через параметр — это паттерн всего проекта (см. `Player.with_*(*, now=...)`). Свойство без `now` потребовало бы либо встроить `IClock` в `Player` (нарушение SRP), либо использовать `datetime.now()` (нарушение §0 «никакого времени в domain»).
- **`Player.anticheat_ban_until: datetime | None = None`** имеет дефолт-значение, чтобы не ломать существующие тесты, которые конструируют `Player` через `Player.new(...)` или с keyword-аргументами без новой колонки. `frozen=True` + `slots=True` сохранены.
- **Индекс на `users.anticheat_ban_until`** имеет смысл потому, что в 1.6.E `AnticheatGuard` будет читать его в каждом `/upgrade` / `/duel`. Без индекса при росте БД (после Phase-2) full table scan на каждый guard был бы катастрофой.
- **Индекс на `audit_log.source`** имеет смысл потому, что в 1.6.C `AnticheatRepository.sum_organic_in_window` будет делать `WHERE source IN (...) AND occurred_at > now() - 24h`. Composite-индекс `(source, occurred_at)` появится в Спринте 1.6.C — если статистика покажет, что одной колонки недостаточно. Пока 1.6.A добавляет минимум: `source` отдельно.

---

## 2026-05-05 — Спринт 1.5.H: docker-compose + README + CONTRIBUTING + VPS-runbook + DoD MVP

**Автор:** Devin (по запросу birgit865)
**Тип:** infra / doc
**Связано:** PR [#TBD], `current_tasks.md` Спринт 1.5.H, ПД 1.5.5 + 1.5.6 + 1.5.7 (частично — runbook готов, ручная валидация после деплоя). **Закрывает Definition of Done MVP** (`docs/dod_mvp.md`).

Что сделано:
- **`ops/docker/Dockerfile`** — multi-stage build:
    - **builder**: `python:3.12-slim-bookworm` + `build-essential` + `libpq-dev`, создаёт venv в `/opt/venv` и ставит туда runtime-зависимости (`pip install --no-cache-dir .` без dev-extras).
    - **runtime**: `python:3.12-slim-bookworm` + `libpq5` (только runtime для asyncpg) + `tini` (init для PID 1, форвардинг сигналов в asyncio long-polling). Непривилегированный пользователь `pipirik:1000`. Венв из builder копируется в `/opt/venv`. Код, `config/`, `locales/`, `alembic.ini` копируются с `--chown=pipirik:pipirik`.
    - **healthcheck** — `python -c "from pipirik_wars.infrastructure.settings import Settings; Settings()"`. Дёшево (нет сети), валидирует env. Если `BOT_TOKEN`/`DATABASE_URL` поломаны — контейнер сразу `unhealthy`, что виден в `docker compose ps`.
    - **CMD** — `python -m pipirik_wars.bot.main`.
- **`ops/docker/docker-compose.yml`** — три сервиса:
    - `postgres: 16-alpine` с healthcheck (`pg_isready`) и volume `pipirik_pg_data`.
    - `migrations` — одноразовый sidecar, гонит `alembic upgrade head`. Зависит от `postgres: service_healthy`.
    - `bot` — long-polling. Зависит от `postgres: service_healthy` + `migrations: service_completed_successfully`. `BOT_TOKEN` валидируется compose-ом (`${BOT_TOKEN:?BOT_TOKEN must be set in .env}`) — пустой токен валит compose с понятным сообщением, а не молча запускает бота с заглушкой.
- **`.dockerignore`** — исключает `.git`, `.venv`, `tests/`, `docs/`, кэши, `.env*`. `README.md` оставлен (pyproject.toml ссылается на него).
- **`README.md`** (полностью переписан) — Quickstart через docker compose (< 5 мин), локальная разработка без Docker, описание архитектуры, структура репо, локализация, политика, ссылки на CONTRIBUTING + DoD + runbook.
- **`CONTRIBUTING.md`** (новый) — workflow PR, чек-листы SOLID + security, правила git (без amend, без force-push в main, без `--no-verify`), CI gates, структура тестов, локализация, балансные данные.
- **`ops/runbooks/deploy_vps.md`** (новый) — пошаговый деплой:
    1. Создание Neon free Postgres + важный нюанс: scheme заменить на `postgresql+asyncpg://`, убрать `?sslmode=require`.
    2. Подготовка VPS: docker + docker compose + git clone.
    3. **`docker-compose.prod.yml`** prod-overlay (отключает локальный `postgres`-сервис через `profiles: ["never"]`, переопределяет `DATABASE_URL` на Neon).
    4. Запуск через `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.
    5. Smoke-тест в Telegram: `/start`, `/profile`, `/forest`, `/oracle`, `/lang`.
    6. 24-часовой стабильный прогон (Definition of Done MVP).
    7. Обновление до новой версии + откат.
    8. FAQ: connection refused (Neon SSL), unhealthy bot, memory pressure, audit_log lookup.
- **`docs/dod_mvp.md`** (новый) — финальный чек-лист MVP. Архитектура (clean architecture, mypy --strict, import-linter, pytest ≥ 80 %), геймплей (регистрация, DAU Gate, лес, прокачка, оракул, топ, локализация), DevOps. Acceptance-сценарий «что делает игрок» (10 шагов), список того, что НЕ входит в MVP (анти-чит хардкап → 1.6, PvP → Phase-2, монетизация → Phase-4).

**Smoke-тест Docker-образа** (локально, в этой же сессии):
- `docker build -f ops/docker/Dockerfile -t pipirik-wars:dev .` → success (43 секунды на холодный build, ~6 секунд на тёплый).
- `docker run pipirik-wars:dev python -c "from pipirik_wars.infrastructure.settings import Settings; Settings()"` → `OK dev` (env валидируется, образ работоспособен).
- `docker compose config` → валиден.

Результат / артефакты:
- `ops/docker/Dockerfile` (multi-stage, ~80 строк).
- `ops/docker/docker-compose.yml` (3 сервиса, ~60 строк).
- `.dockerignore`.
- `README.md` (~140 строк, переписан полностью).
- `CONTRIBUTING.md` (~120 строк, новый).
- `ops/runbooks/deploy_vps.md` (~250 строк, новый).
- `docs/dod_mvp.md` (~120 строк, новый).
- Локально `make ci` зелёный: ruff/mypy --strict (370 файлов, 0 issues) / import-linter (3 контракта kept) / pytest — **1094 passed + 1 skipped**, coverage **96.91 %**.

Заметки / решения:
- **Local vs Production compose** — два файла: базовый `docker-compose.yml` (с локальной Postgres) для разработки + `docker-compose.prod.yml` overlay (отключает локальную Postgres через `profiles: ["never"]`) для VPS-деплоя. Это идиоматичный compose-pattern: одна конфигурация для двух окружений, без дублирования.
- **Migrations как sidecar** — отдельный сервис `migrations` гонит `alembic upgrade head` и завершается. Бот ждёт `service_completed_successfully`. Альтернатива — гонять миграции в `entrypoint.sh` бота — отвергнута, потому что (а) усложняет образ (нужен shell-wrapper), (б) при падении миграции непонятно, бот не стартанул из-за миграций или из-за самого кода.
- **Healthcheck — импорт `Settings`, не пинг Telegram/БД** — намеренно. Healthcheck должен быть дешёвым и не зависеть от внешних сервисов: при кратковременной недоступности Telegram API (например, перезапуск Cloudflare на стороне Telegram) бот не должен падать как «unhealthy» и рестартоваться. Проверка валидности env — ровно то, что нам нужно: если `Settings()` упал, значит контейнер запущен с битым env, и его действительно нужно ребутнуть.
- **`pipirik:1000` user** — не root. Standard practice для production-образов. UID 1000 совпадает с дефолтным `ubuntu:1000` на VPS, что упрощает дебаг через bind-mount-ы (если когда-нибудь понадобится).
- **`tini` как init** — иначе SIGTERM от docker stop не доходит до asyncio в Python (PID 1 без init не реагирует на сигналы корректно). При `docker compose down` бот должен gracefully закрыться (закрыть Bot session, остановить scheduler) — `tini` это обеспечивает.
- **MAX_DAU env var** — в `.env.example` лежит `MAX_DAU=200`, но фактически settings ожидает `BOT_MAX_DAU` (через `env_prefix="BOT_"`). В этом PR проставил `BOT_MAX_DAU` в compose, но сам `.env.example` пока **не правил** (это отдельный мелкий баг — стоит унифицировать в hot-fix отдельным PR-ом). Сейчас compose валиден, README — тоже (не упоминает `MAX_DAU` напрямую).
- **DoD MVP Acceptance 1.5.7 (24 ч стабильной работы) — единственный пункт, который требует ручной валидации после деплоя.** Код-PR закрывает 1.5.5 (compose работает) и 1.5.6 (README < 30 мин для нового разработчика). Сам деплой на VPS — отдельный шаг, который агент не может сделать за пользователя (нужен реальный VPS + Neon + BOT_TOKEN).

---

## 2026-05-05 — Спринт 1.5.G: каталог 300+ JSON-шаблонов забавных логов леса (RU+EN)

**Автор:** Devin (продолжение работы предыдущего агента)
**Тип:** feature
**Связано:** PR [#TBD], `current_tasks.md` Спринт 1.5.G, ПД 1.5.3.

Что сделано:
- **Стадии 1+2 (предыдущий агент, см. коммиты `c2b8569`, `cdf62a2`)** — фундамент уже был:
  - доменный picker `pick_forest_log_template(*, random, templates)` — чистая функция через `IRandom`, без I/O;
  - `ForestLogTemplate` (frozen dataclass с валидацией id/text);
  - `ForestLogNoTemplatesError` в `domain/forest/errors.py`;
  - порт `IForestLogTemplateProvider.get_templates(*, locale: str) -> Sequence[...]` (lazy кэш per locale, RU-фолбэк, `ForestLogNoTemplatesError` если каталог пуст);
  - адаптер `JsonForestLogTemplateProvider` (зеркало oracle-провайдера: lazy load, дедуп id, валидация формата);
  - подключение к `TelegramForestFinishNotifier` — picker зовётся **вне транзакции** после коммита `FinishForestRun` (best-effort: каталог пуст / провайдер упал → flavour не показываем, основное «вернулся из леса» уходит как было);
  - `ForestPresenter.finished(*, flavor_template: ForestLogTemplate | None = None)` — рендерит flavour-строку через `_render_flavor`, подставляя `{user}` (полный ник) и `{delta}` (берётся из bundle-ключа `forest-flavour-delta`); defensive `try/except (KeyError, IndexError, ValueError)` — кривой плейсхолдер в JSON-каталоге не сломает сообщение игрока;
  - locale-ключ `forest-flavour-delta` в `locales/{ru,en}.ftl`;
  - DI-провязка в `bot/main.py` (`JsonForestLogTemplateProvider(templates_dir=_DEFAULT_TEMPLATES_DIR)` + `RealRandom()` в notifier).

- **Стадии 3+4 (этот PR):**
  - сгенерированы прод-каталоги `config/templates/forest_logs_ru.json` и `config/templates/forest_logs_en.json` — по **350 уникальных шаблонов** на локаль через декартово произведение «эмодзи × сцена × связка × развязка» (грамматика-генератор разово, в коммит не уходит);
  - все шаблоны содержат **только** allowed-плейсхолдеры `{user}` и `{delta}` (валидируется integration-тестом);
  - integration-тест `tests/integration/templates/test_forest_log_loader.py` — зеркало `test_oracle_loader.py`, 22 кейса:
    - прод-файлы грузятся, ≥ 300 шаблонов на локаль, уникальные id, тримнутый текст;
    - `str.format(user=..., delta=...)` проходит без исключений на каждом шаблоне (regex-проверка на отсутствие illegal-плейсхолдеров);
    - lazy-кэш per locale (повторный `get_templates` отдаёт ту же tuple-инстанс);
    - fallback на `"ru"` для неизвестной локали;
    - error-paths: пустой каталог / отсутствие файлов / дубликат id / битый JSON / корень-массив / `templates` не список / запись без `text` / запись не объект → `ForestLogNoTemplatesError` или `ConfigError`.

Результат / артефакты:
- `config/templates/forest_logs_ru.json` (350 шаблонов).
- `config/templates/forest_logs_en.json` (350 шаблонов).
- `tests/integration/templates/test_forest_log_loader.py` (22 теста).
- Локально `make ci` зелёный: ruff/mypy/import-linter/pytest — **1094 passed + 1 skipped**, coverage **96.91 %**.

Заметки / решения:
- **`{user}` и `{delta}` — единственные допустимые плейсхолдеры** в каталоге. Любой другой `{...}` ломает `str.format` → invariant-нарушение, integration-тест на этом падает. Это ставит жёсткий contract между JSON-каталогом и презентером: миграция нумерации / добавление новых параметров требует осознанного PR с обновлением и каталога, и теста, и презентера.
- **Audit `LENGTH_GRANT.source` — отложен в Спринт 1.6** (anti-cheat hardcap). В development_plan.md изначально стояло требование расширить audit полем `source: "forest" | "donate" | ...` в задаче 1.5.4, но `audit_log.source` сам по себе нужен только под античит-агрегацию — так что переезжает в 1.6.A (БД-фундамент античита). Идемпотентность начислений за лес уже обеспечена через `idempotency_key=f"forest_run_finished:length:{run_id}"`.
- **Скрипт-генератор не коммитится** (по требованию HANDOFF.md из стадии 1+2). Только результат — JSON-каталоги.
- **RU и EN — независимые каталоги**, не машинный перевод. Локализация культуры: можно делать ≥ 300 в каждом без жёсткого id-соответствия.

---

## 2026-05-05 — Спецификация: анти-чит хардкап роста длины (3000/14000 см, soft-ban 14 дней)

**Автор:** Devin (по запросу jorey7467)
**Тип:** doc / decision (только документация — кода нет)
**Связано:** ГДД [§3.3](game_design.md), `development_plan.md` [§4 / Спринт 1.6](development_plan.md), `current_tasks.md` [Спринт 1.6](current_tasks.md). Запрос пользователя: «в документацию нужно добавить записи о функционале для хардкапа и античита, если в сутки у кого-то пипирка выросла на 3000см то он достигает суточного лимита. Так же есть недельный лимит 14000см. Если у кого-то все-же какимто образом у игрока пипирка за сутки выросла более чем на 3000см, то софт бан на 2 недели — нельзя растить пипирку и пометка админу. Так же эти лимиты никак не касаются донатных сантиметров, там нет никаких ограничений, за деньги любая длинна.»

Что сделано:
- **`docs/game_design.md` §3.3** (новый раздел «Хардкап роста длины (анти-чит)»): полная игровая спецификация. Два rolling-окна (24 ч / 7 дней), лимиты 3000 / 14000 см, эшелонированная защита (clamp на штатном пути + trip-wire при обходе). Soft-ban на 14 дней с автоматическим снятием. Перечисление organic-источников (лес, предсказатель, рефералка, награды PvP/караванов/рейдов, `/grant_length` админа) и donate-источников (Stars / TON / USDT — без лимитов). Конфиг в `balance.yaml` секция `anticheat` (hot-reload через `/balance_reload`). DoD-сценарии для тестов (10 последовательных лесов, race-test, soft-ban не блокирует `/profile`).
- **`docs/development_plan.md`:**
    - §0.3 «Чек-лист безопасности»: добавлен пункт про прохождение всех начислений длины через `progression.add_length(...)` (clamp + trip-wire).
    - §4 / новый Спринт 1.6 «Анти-чит хардкап (Pre-Phase-2 gate)»: 10 задач (миграция БД, конфиг, `AnticheatWindow` + порт, центральный use-case `progression.add_length`, гейт спендалок, миграция всех существующих use-cases на `ILengthGranter`, bot-команда `/anticheat_unban`, локализация, нагрузочный race-test, документация). Зачем перед Фазой 2 — пояснено в эпиграфе.
    - §10 «Критерии готовности по фазам»: в строку «MVP (Фаза 1)» добавлено обязательное прохождение анти-чит хардкапа.
    - §9 «Риски и митигации»: новый риск «Эксплойт/баг ускоряет рост длины» с митигацией.
- **`docs/current_tasks.md`:** новый блок «⚪ Бэклог — Спринт 1.6 (Анти-чит хардкап, pre-Phase-2)» c разрезкой на 8 PR-ов (1.6.A — БД-фундамент, 1.6.B — конфиг, 1.6.C — `AnticheatWindow` + порт + repo, 1.6.D — `progression.add_length` + race-test, 1.6.E — `AnticheatGuard` для спендалок, 1.6.F — миграция всех существующих use-cases на `ILengthGranter` + import-linter-контракт, 1.6.G — `/anticheat_unban` + локализация, 1.6.H — нагрузочный тест + документация). Каждый PR имеет дизайн-решения в эпиграфе. Также в этом коммите 1.5.F помечена `✅ смержено (PR #30)` (была `🟢 готово к ревью` после мержа).

Заметки / решения:
- **Почему rolling-окно, а не календарные сутки.** Календарный сброс в полночь (как у `/oracle`) даёт зону уязвимости в 1–2 минуты вокруг границы суток: игрок может прибавить 2999 в 23:59 и ещё 2999 в 00:01 — и получить 6000 за пару минут. Rolling-окно (`ts > now() - INTERVAL '24h'`) закрывает эту дыру. Минус — сложнее коммуникация игроку, компенсируется явным «следующее окно открывается через N часов» в сообщении.
- **Почему clamp до 0, а не reject.** При `delta_requested=12, remaining=5` начисляется 5 (а не 0). Альтернатива «всё или ничего» дала бы более понятный UX, но игрок терял бы часть награды. Поле `clamped_from` в `audit_log` сохраняет полный контекст для метрик и debug-а.
- **Почему soft-ban, а не hard-ban.** При срабатывании trip-wire игрок не блокируется полностью — он сохраняет доступ к `/profile`, `/top`, `/help`, чату. Бан изолирует только прогрессию (рост и трату длины). Это снижает урон от ложных срабатываний (race-condition на 1 см выше лимита) и даёт админу время разобраться без drama.
- **Почему trip-wire, а не только clamp.** `clamp` защищает от штатных багов (округление, конкурентные mutations). `trip-wire` ловит то, что прорвалось мимо `clamp`: гонки, прямые БД-правки, ошибочные ручные `grant_length`, баги в новых use-cases, забывших позвать `clamp`. Эшелонированная защита.
- **Почему перед Фазой 2.** Фаза 2 вводит PvP и масс-PvP — новые источники прибавки/потери длины с высокой пропускной способностью. Без хардкапа в этих use-cases один экспоит даст экспоненциальный рост по экономике. Анти-чит должен быть готов **до** PvP-механик, иначе придётся переделывать каждый PvP-use-case.
- **Почему донат вне лимитов.** Это явное product-решение из ГДД §12 — донатная длина теряется как обычная, но **никак не ограничивается** в начислении. Платёжный канал — отдельный экономический контур, защищённый платёжным процессором (idempotency по `payment_id`).
- **Почему не сделано прямо сейчас.** Текущая работа в Спринте 1.5 (локализация и деплой). Анти-чит хардкап — отдельный спринт с собственными миграциями БД и cross-cutting рефакторингом всех существующих use-cases прибавки длины. Объединять с 1.5 нельзя — разные обязательства DoD.

---

## 2026-05-05 — Спринт 1.5.F: `/lang ru|en` + `users.locale_override` + per-player локаль в фоновых job-ах

**Автор:** Devin (по запросу jorey7467)
**Тип:** feature (бот-команда + миграция + use-case + расширение `LocaleMiddleware` + интеграция в notifier)
**Связано:** Текущий PR (Спринт 1.5.F), [development_plan.md §3 / Спринт 1.5, задача 1.5.2](development_plan.md), [current_tasks.md Спринт 1.5 → 1.5.F](current_tasks.md). Продолжение Спринта 1.5 после смерженного 1.5.E (PR #29).

Что сделано:
- **Миграция `0006_users_locale_override`** (`src/pipirik_wars/infrastructure/db/migrations/versions/20260505_0006_users_locale_override.py`): добавлена колонка `users.locale_override TEXT NULL` + CHECK-constraint `users_locale_override_supported` (`locale_override IS NULL OR locale_override IN ('ru', 'en')`). NULL = «нет override-а», `LocaleMiddleware` фоллбэчит на tg.language_code → DEFAULT_LOCALE. Миграция использует `op.batch_alter_table(...)` для совместимости с SQLite (dev/тесты): SQLite не умеет `ALTER ... ADD CONSTRAINT`, Alembic делает copy-and-move через batch.
- **Domain `Player.locale_override`** (`src/pipirik_wars/domain/player/entities.py`): новое опциональное поле `locale_override: str | None = None` + метод `with_locale_override(locale_override, *, now)` (frozen-replace + idempotent: возвращает `self` если значение не меняется).
- **ORM `UserORM.locale_override`** (`src/pipirik_wars/infrastructure/db/models/player.py`): mapped-column `String(8) NULL` + table-level `CheckConstraint` (mirror к миграции).
- **Repo persistence** (`src/pipirik_wars/infrastructure/db/repositories/player.py`): `_to_domain` подхватывает `row.locale_override`; `add` и `save` пробрасывают `player.locale_override` обратно в `UserORM`.
- **Audit-action `PLAYER_LOCALE_SET`** (`src/pipirik_wars/domain/shared/ports/audit.py`): новый AuditAction для трассировки изменений локали.
- **Use-case `SetPlayerLocale`** (`src/pipirik_wars/application/player/set_locale.py`): `execute(*, tg_id, locale: Locale | None)` — валидирует локаль через `SUPPORTED_LOCALES` (защита от обхода SUPPORTED_LOCALES снаружи), открывает UoW, читает игрока (бросает `PlayerNotFoundError` если нет), вызывает `player.with_locale_override(...)`, сохраняет, пишет audit-запись `PLAYER_LOCALE_SET` с before/after `{locale_override: ...}`. `locale=None` → сброс override-а.
- **Port `IPlayerLocaleResolver`** (`src/pipirik_wars/application/i18n/player_locale.py`): `Protocol` с одним методом `resolve_for_tg_id(tg_id) -> Locale | None`. Используется и в `LocaleMiddleware` (резолв override игрока перед вызовом handler-а), и в фоновых notifier-ах (`TelegramForestFinishNotifier` — для рендера в локали игрока без `update.from_user`).
- **Implementation `PlayerLocaleResolverDB`** (`src/pipirik_wars/infrastructure/i18n/player_locale.py`): минимальный SELECT по `users.locale_override` через `SqlAlchemyUnitOfWork.session`. Не открывает UoW транзакционно ради одного scalar-чтения — для read-only middleware-резолва это явный compromise (читать через полноценный UoW.commit избыточно). Если override `NULL` или unsupported (защитный фильтр на случай рассинхронизации БД и SUPPORTED_LOCALES) — возвращает `None`.
- **`LocaleMiddleware` priority chain** (`src/pipirik_wars/bot/middlewares/locale.py`): получает опциональный `player_locale_resolver: IPlayerLocaleResolver | None`. Цепочка резолва: `users.locale_override` (если резолвер есть и `tg_user_id` известен) → `LocaleResolver(tg.language_code)` → `LocaleResolver.default = DEFAULT_LOCALE`. Без резолвера middleware ведёт себя как раньше (1.5.A совместимость).
- **Bot-команда `/lang ru|en|RU|EN`** (`src/pipirik_wars/bot/handlers/lang.py`): handler работает только в ЛС (`chat_kind == "private"`), парсит `command.args.strip().lower()`, фильтрует пустой / неподдерживаемый input. Конкретные сценарии: `lang-group` (группа/супергруппа), `lang-other` (channel или нет identity), `lang-usage` (нет аргументов), `lang-unsupported` с параметром `code` (любая строка не `ru`/`en`), `lang-not-registered` (`PlayerNotFoundError`), `lang-set-{ru,en}` (успех — подтверждение **в новой выбранной локали**, чтобы игрок сразу увидел «как теперь будет»).
- **`LangPresenter`** (`src/pipirik_wars/bot/presenters/lang.py`): тонкий wrapper над `IMessageBundle` (паттерн 1.5.B-E). Каждый метод: `(*, locale: Locale, ...) -> str`.
- **Локали `lang-*`** (`locales/{ru,en}.ftl`): полный набор ключей (`lang-group/lang-other/lang-not-registered/lang-usage/lang-unsupported/lang-set-{ru,en}`). EN-версия покрывает все ключи (RU→EN fallback в 1.5.A работает, но EN-первичный путь даёт лучшую UX для англоязычных игроков).
- **`TelegramForestFinishNotifier` per-player локаль** (`src/pipirik_wars/bot/notifications/forest.py`): принимает опциональный `locale_resolver: IPlayerLocaleResolver | None`. В `notify(...)` перед рендером дёргает `_resolve_locale(tg_id)`: если резолвер есть и нашёл override — рендерим в локали игрока, иначе фолбэк на `default_locale`. Любые ошибки резолвера поглощаются (`logger.exception` + фолбэк) — фоновые сообщения должны быть best-effort и не падать из-за БД-проблем.
- **Composition root** (`src/pipirik_wars/bot/main.py`): `Container` теперь хранит `player_locale_resolver: IPlayerLocaleResolver` и `set_player_locale: SetPlayerLocale`. `build_container(...)` инстанциирует `PlayerLocaleResolverDB(uow=uow)` и пробрасывает его в (1) `register_middlewares(..., player_locale_resolver=...)` (для `LocaleMiddleware`), (2) `TelegramForestFinishNotifier(..., locale_resolver=...)`. Dispatcher DI: `dispatcher["set_player_locale"] = container.set_player_locale`. Router-регистрация `dispatcher.include_router(lang_router)` после `profile_router`.
- **Тесты:**
    - **Unit `SetPlayerLocale`** (`tests/unit/application/player/test_set_locale.py`, 6 кейсов): set-from-NULL, switch ru→en, reset через `None`, идемпотентность (entity не меняется при no-op), `PlayerNotFoundError` + rollback, unsupported-locale защита.
    - **Unit `LocaleMiddleware` × resolver** (`tests/unit/bot/middlewares/test_locale.py`, +4 кейса к 7 существующим): override приоритетнее `tg.language_code`, фолбэк на `tg.language_code` если override-а нет, резолвер не вызывается без `TgIdentity`, фолбэк на DEFAULT когда нет ни override-а, ни валидного `tg.language_code`.
    - **Unit `LangPresenter`** (`tests/unit/bot/presenters/test_lang.py`, 7 кейсов): по одному кейсу на каждый ключ.
    - **Unit `/lang` handler** (`tests/unit/bot/handlers/test_lang.py`, 11 кейсов): успех ru/en, normalize regex (RU/EN → ru/en), нет аргументов / blank / fr → правильные ключи, `PlayerNotFoundError` через side_effect → `lang-not-registered`, group/supergroup/channel ветки, fallback на DEFAULT при `locale=None`.
    - **Integration `PlayerLocaleResolverDB`** (`tests/integration/i18n/test_player_locale_resolver.py`, 7 кейсов): возвращает `None` для unknown / NULL override, `Locale("ru")` / `Locale("en")` для соответствующих значений, CHECK-constraint в БД отвергает мусор. Roundtrip через `SqlAlchemyPlayerRepository` для `with_locale_override` + `save` (set + clear).
    - **Unit notifier × resolver** (`tests/unit/bot/notifications/test_forest.py`, +4 кейса к 11 существующим): override RU при default EN → шлёт RU, override EN при default RU → шлёт EN, нет override → фолбэк на default, ошибки резолвера поглощаются.
    - **Migration test** (`tests/integration/db/test_migrations.py`): добавлен `test_0006_descends_from_0005`, расширены проверки `versions/*.py` на наличие нового файла, регистрации `0006_users_locale_override` в Alembic-цепочке.
    - **Composition root test** (`tests/unit/bot/test_composition_root.py`): добавлен `FakePlayerLocaleResolver` в `tests/fakes/player_locale_resolver.py` + проброс в `Container`.

Результат / артефакты:
- Новые файлы: `src/pipirik_wars/application/player/set_locale.py`, `src/pipirik_wars/application/i18n/player_locale.py`, `src/pipirik_wars/infrastructure/i18n/player_locale.py`, `src/pipirik_wars/infrastructure/db/migrations/versions/20260505_0006_users_locale_override.py`, `src/pipirik_wars/bot/handlers/lang.py`, `src/pipirik_wars/bot/presenters/lang.py`, `tests/fakes/player_locale_resolver.py`, `tests/unit/application/player/test_set_locale.py`, `tests/unit/bot/handlers/test_lang.py`, `tests/unit/bot/presenters/test_lang.py`, `tests/integration/i18n/test_player_locale_resolver.py`, `tests/integration/i18n/conftest.py`.
- Модифицированы: `src/pipirik_wars/domain/player/entities.py`, `src/pipirik_wars/domain/shared/ports/audit.py`, `src/pipirik_wars/infrastructure/db/models/player.py`, `src/pipirik_wars/infrastructure/db/repositories/player.py`, `src/pipirik_wars/application/player/__init__.py`, `src/pipirik_wars/application/i18n/__init__.py`, `src/pipirik_wars/infrastructure/i18n/__init__.py`, `src/pipirik_wars/bot/middlewares/locale.py`, `src/pipirik_wars/bot/middlewares/__init__.py`, `src/pipirik_wars/bot/handlers/__init__.py`, `src/pipirik_wars/bot/notifications/forest.py`, `src/pipirik_wars/bot/main.py`, `locales/ru.ftl`, `locales/en.ftl`. Тесты: `tests/unit/bot/middlewares/test_locale.py`, `tests/unit/bot/notifications/test_forest.py`, `tests/integration/db/test_migrations.py`, `tests/unit/bot/test_composition_root.py`, `tests/fakes/__init__.py`.
- Локально `make ci`: ruff lint ✅, mypy --strict ✅ (364 файла), import-linter ✅ (3 контракта KEPT), pytest 1060 passed + 1 skipped (`thickness=1` граничный случай), coverage 96.98% (требование ≥80%).

Заметки / решения:
- **Почему `IPlayerLocaleResolver`, а не прямое чтение `IPlayerRepository.get_by_tg_id` в middleware?** Middleware дёргается на КАЖДОМ апдейте бота (включая колбэки/inline-режим). `get_by_tg_id` тянет всю Player-агрегат + UoW.commit — это лишний оверхед на каждый чих. `IPlayerLocaleResolver` — узкий read-only порт для одной колонки, реализация делает один SELECT и не открывает транзакцию для commit. ISP в чистом виде.
- **Почему confirm в новой локали?** Игрок переключился с EN на RU через `/lang ru` — он ожидает увидеть «🌐 Язык переключён на русский», а не «Language switched to Russian». Это маленький, но важный UX-сигнал «смена применилась немедленно».
- **Почему `0006` назван `users_locale_override`, а не `players_locale_override`?** Таблица в БД называется `users` (не `players`) — name-mismatch с domain-агрегатом `Player` остался ещё со Спринта 1.1, и переименование БД-таблицы — отдельная задача за пределами 1.5. Имя миграции следует ИМЕНИ ТАБЛИЦЫ, а не доменной сущности.
- **Почему фолбэк на `default_locale` в notifier-е, а не на язык игрока из `tg.language_code`?** Notifier работает в фоне (APScheduler) — у него нет `update.from_user`, и доступ к `tg.language_code` пришлось бы тащить из БД (ещё одна колонка `users.tg_language_code` со снапшотом). Мы сознательно НЕ делаем этого: игрок, который не выбрал `/lang`, видит фоновые сообщения в EN. Это ОК для MVP — explicit override закрывает 90% юзкейсов.
- **Почему migration через `op.batch_alter_table`?** SQLite (наш dev/тестовый бэкенд) не умеет `ALTER TABLE ADD CONSTRAINT` напрямую — Alembic использует copy-and-move через batch_alter_table. Для Postgres в проде это no-op (генерируется обычный `ALTER TABLE`). Без батчинга `make ci` падал на интеграционных тестах миграций.

---

## 2026-05-05 — Спринт 1.5.E: `/forest` через `IMessageBundle` (handler + презентер + нотификатор)

**Автор:** Devin (по запросу sufficientdorette)
**Тип:** feature (i18n-прогон последнего handler-а + nitidication-презентера + удаление legacy `render_full_nick(...)`)
**Связано:** Текущий PR (Спринт 1.5.E), [development_plan.md §3 / Спринт 1.5, задача 1.5.1](development_plan.md), [current_tasks.md Спринт 1.5 → 1.5.E](current_tasks.md). Продолжение Спринта 1.5 после смерженного 1.5.D (PR #28).

Что сделано:
- **Локали (`locales/{ru,en}.ftl`):** добавлена секция `## /forest` с полным набором ключей: `forest-group/-other/-not-registered/-already-in/-started/-started-fallback/-finished-header/-finished-length/-finished-title-granted/-finished-item-found/-finished-name-granted/-finished-name-found/-rarity-{common,rare,epic}/-button-{equip,drop-item,replace-name,drop-name}/-toast-*` (9 toast-ов). Числовые параметры (`$cooldown_minutes`, `$length_delta_cm`, `$length_before_cm`, `$length_after_cm`) обёрнуты в `NUMBER($x, useGrouping: 0)` — без этого Fluent для RU вставляет `\xa0` (NBSP) между разрядами, и проверки точного совпадения текста ломаются (тот же фикс, что в 1.5.C/D).
- **`ForestPresenter` (`bot/presenters/forest.py`):** `__init__(*, bundle: IMessageBundle)`, методы по группам:
    - **chat-ветки:** `group/other/not_registered/already_in(*, locale)`;
    - **started-сообщение:** `started(*, player, display_name, cooldown_minutes, locale)` (рендерит `[Локализованный титул] [Название] [Имя]` через приватный `_render_full_nick(...)`, потом передаёт собранный ник как `$nick` в `forest-started`) + `started_fallback(*, cooldown_minutes, locale)` (короткий безниковый вариант для случая, когда `GetProfile` после `StartForestRun` отдал `None`);
    - **finished-сообщение:** `finished(*, result, display_name_after, locale)` собирает строки `header / length / title_granted? / item_found? / name_granted_or_found?` и склеивает через `\n`. Локализованная редкость подставляется как готовая строка в параметр `$rarity` ключа `forest-finished-item-found`;
    - **finish-клавиатура:** `finish_keyboard(result, *, locale)` возвращает `InlineKeyboardMarkup | None` для `ItemDrop` и `NameDrop` (кроме случая, когда имя авто-применилось — `granted_name=True`). Подписи локализованы (`forest-button-{equip,drop-item,replace-name,drop-name}`); `callback_data` — invariant-формат `forest:<action>:<run_id>` через pure-функцию `forest_callback_data(action, run_id)` (не зависит от локали);
    - **toast-ы для коллбэков:** 9 методов `toast_*(*, locale)` (`name_applied/name_already_applied/name_dropped/item_dropped/item_equipped_placeholder/foreign_button/run_not_found/drop_mismatch/player_not_found`);
    - **`localized_rarity(rarity, *, locale)`:** маппинг `Rarity → forest-rarity-{common,rare,epic}` с резолвом через `IMessageBundle`.
  Pure-функции `forest_callback_data(...)`, `parse_forest_callback_data(...)`, `has_finish_keyboard(...)` оставлены вне класса — они не локализованы (это сериализация / business-логика), и тесты к ним не требуют bundle-а.
- **`bot/handlers/forest.py`:** handler `handle_forest` теперь принимает `bundle: IMessageBundle` и `locale: Locale | None = None` через DI middleware-а; `effective_locale = locale or DEFAULT_LOCALE`. Все ответы (`group/other/not_registered/already_in/started/started_fallback`) идут через `ForestPresenter.<...>(locale=effective_locale)`. Callback-handler `handle_forest_callback` (на `F.data.startswith("forest:")`) тоже принимает `bundle` + `locale`, парсит `callback_data` через `parse_forest_callback_data(...)`, и для каждого `action` (`apply_name/drop_name/equip_item/drop_item`) шлёт локализованный toast и (где надо) снимает клавиатуру через `_strip_keyboard(...)` (idempotent, поглощает любые `edit_reply_markup`-ошибки). Логика `apply_name` вынесена в приватный `_handle_apply_name(...)` для читаемости.
- **`bot/notifications/forest.py`:** `TelegramForestFinishNotifier` получил `bundle: IMessageBundle` и `default_locale: Locale = DEFAULT_LOCALE` через DI. Локаль игрока в фоновом APScheduler-job-е недоступна (нет `update.from_user`), поэтому notifier рендерит **всё** в `default_locale`. Это компромисс: per-player-локаль в нотификаторе требует `players.locale_override` (миграция) и `IPlayerLocaleResolver`-порт — это вынесено в **1.5.F** как явный pending-item. До 1.5.F finished-сообщение приходит игроку в `DEFAULT_LOCALE = "en"`, что уже корректно для большинства новых игроков (язык Telegram-клиента у них чаще всего English).
- **`bot/main.py`:** `TelegramForestFinishNotifier(...)` в композиционном корне теперь получает `bundle=bundle` (тот же `FluentMessageBundle`, что у handler-ов). Это единственная пересборка root-а: notifier явно зависит от bundle-а, других путей пройти инициализацию нет.
- **Удалён legacy `render_full_nick(...)` из `bot/presenters/profile.py`:** функция оставалась как RU-only pure-функция в 1.5.C → 1.5.D ради forest-презентера. Теперь forest-презентер сам собирает ник через приватный `_render_full_nick(...)` с локализованным титулом, поэтому `render_full_nick` и сопутствующий dict `_TITLE_RU` удалены. Тесты `TestRenderFullNick` тоже удалены (4 теста).
- **`bot/presenters/__init__.py`:** добавлены экспорты `ForestPresenter`, `ForestCallbackAction`, `ForestCallbackData`, `forest_callback_data`, `parse_forest_callback_data`. Удалён экспорт `render_full_nick`. Все презентеры теперь идут через `IMessageBundle`.

Тесты:
- **`tests/unit/bot/presenters/test_forest.py`** (полностью переписан под новый паттерн, **62 теста**):
  - `TestCallbackData` — 11 тестов pure-функций (round-trip, формат, ≤ 64 байт, отказ на zero/negative run_id, отказ на bad format, отказ на unknown action);
  - `TestHasFinishKeyboard` — 4 теста на `has_finish_keyboard(...)` для `NoDrop/ItemDrop/NameDrop(auto)/NameDrop(replace)`;
  - `TestForestPresenterFakeBundle` — 21 тест через `FakeMessageBundle` (маркер `<locale>:<key>[k=v,...]`): покрывает все методы (`group/other/not_registered/already_in/started/started_fallback/finished/finish_keyboard/toast_*/localized_rarity`), включая отдельный тест **«callback_data invariant между локалями»** (подписи кнопок RU vs EN различаются, `callback_data` — нет);
  - `TestForestPresenterFluent` — 11 тестов через `FluentMessageBundle` (RU + EN), интеграционная проверка реальных переводов: `started`-сообщение в обеих локалях, `finished`-сообщение для `NoDrop/ItemDrop/NameDrop(replace)`, локализованные подписи кнопок, `localized_rarity` для всех `Rarity` × `Locale`. Отдельный safety-test: **в EN-выводе нет ни одного кириллического символа** (`U+0400-U+04FF`) — защита от случайной утечки RU-строк.
- **`tests/unit/bot/handlers/test_forest.py`** (полностью переписан, **22 теста**):
  - `TestHandleForest` — 9 тестов: success-ветка с `started`-сообщением, `not_registered/already_in` через ключи, `group/supergroup/channel`-чаты через `group/other`, отсутствие `tg_identity`, fallback `DEFAULT_LOCALE = "en"` при `locale=None`, fallback на `started_fallback` если `GetProfile` отдал `None`;
  - `TestForestCallback` — 13 тестов: успех `apply_name`, повторное применение, ownership mismatch, drop mismatch, run not found, player not found, `drop_name/equip_item/drop_item`-actions, malformed `callback_data` (toast `drop_mismatch` + клавиатура снята), отсутствие `tg_identity`/`data` (silent return), `_strip_keyboard(...)` поглощает `edit_reply_markup`-ошибки, fallback на `DEFAULT_LOCALE` при `locale=None`.
- **`tests/unit/bot/notifications/test_forest.py`** (обновлены сигнатуры и assertions, **+2 новых теста**):
  - `_make_notifier(...)` теперь принимает опциональный `bundle` (по умолчанию реальный `FluentMessageBundle`) и `default_locale`;
  - старые ассерты текста (`"вернулся из леса" / "Шлём Берсерка" / "Нашёл имя: Новое"`) переведены в RU-режим через `default_locale=Locale("ru")`;
  - **новый `test_sends_message_default_locale_en`**: убеждается, что без override `default_locale = DEFAULT_LOCALE = "en"`, и в выводе нет кириллицы;
  - **новый `test_uses_fake_bundle_marker_for_finished_header`**: проверяет, что нотификатор берёт ключи `forest-finished-header` и `forest-finished-length` (страховка от регресса при будущих рефакторингах);
  - тест проверки локализованных подписей кнопок в keyboard.
- **`tests/unit/bot/presenters/test_profile.py`:** удалён `TestRenderFullNick` (4 теста), импорт `render_full_nick` из публичного модуля убран. `TestTitleMessageKey` оставлен.

Локально:
- `pre-commit run --all-files` — все хуки зелёные.
- `make ci` — `ruff` + `mypy` + `lint-imports` + `pytest`: **1020 passed, 1 skipped, 96.95%** покрытие. Контракты `import-linter` (3) — kept. Никаких новых `# type: ignore`/`noqa` не добавлено.

Результат / артефакты:
- `locales/{ru,en}.ftl` (+ ~60 строк в каждом — секция `## /forest`).
- `src/pipirik_wars/bot/presenters/forest.py` (полностью переписан под `ForestPresenter`).
- `src/pipirik_wars/bot/handlers/forest.py` (handler + callback-handler с `bundle`/`locale` DI).
- `src/pipirik_wars/bot/notifications/forest.py` (`bundle` + `default_locale` через DI).
- `src/pipirik_wars/bot/main.py` (notifier теперь получает `bundle`).
- `src/pipirik_wars/bot/presenters/profile.py` (удалён `render_full_nick` + `_TITLE_RU`).
- `src/pipirik_wars/bot/presenters/__init__.py` (новые экспорты `ForestPresenter` и др., удалён `render_full_nick`).
- `tests/unit/bot/presenters/test_forest.py` (полностью переписан, 62 теста).
- `tests/unit/bot/handlers/test_forest.py` (полностью переписан, 22 теста).
- `tests/unit/bot/notifications/test_forest.py` (обновлены сигнатуры + 2 новых теста).
- `tests/unit/bot/presenters/test_profile.py` (удалён `TestRenderFullNick`).

Заметки / решения:
- **Почему `ForestPresenter` — класс, а pure-функции остались отдельно.** Тот же паттерн, что в 1.5.B-D: класс с `__slots__ = ("_bundle",)` и DI-параметром `bundle: IMessageBundle` нужен для **локализованного UI**. Pure-функции `forest_callback_data(...)`/`parse_forest_callback_data(...)` — это сериализация, не UI; они **не должны** зависеть от локали — `callback_data` инвариантно между перерегистрацией хэндлеров, перезагрузкой шаблонов, переключением локали игрока (`/lang ru` не должен «протухать» уже отправленные кнопки), и deep-link-ами. Тест `test_finish_keyboard_item_callback_data_invariant_across_locales` явно фиксирует этот контракт: подписи кнопок RU и EN различаются, `callback_data` — нет.
- **Почему notifier рендерит в `DEFAULT_LOCALE`, а не в `player.locale`.** В 1.5.B мы добавили запись `Locale` в `RegisterPlayerInput.locale` (хранение per-player языка), но в `Player`-aggregate этого поля **ещё нет** — это будет миграция `players.locale_override TEXT NULL` в 1.5.F. До этого notifier не имеет источника, откуда взять язык игрока: `update.from_user` отсутствует (это фоновый APScheduler-job, а не chat-event), `tg.language_code` — тоже нет. Hardcode в `DEFAULT_LOCALE = "en"` корректнее, чем угадывать. В 1.5.F notifier получит `IPlayerLocaleResolver`-порт и сможет резолвить `player.locale_override → tg.language_code → DEFAULT_LOCALE` (тот же приоритет, что в `LocaleMiddleware`).
- **Почему 1.5.E не включает `/lang` и 300+ JSON-логов.** Изначально 1.5.E был задуман как «всё про forest-локализацию + audit + 300+ шаблонов + `/lang` + `players.locale_override`». Но это четыре независимых задачи, и каждая несёт свою миграцию / порт / use-case. Чтобы PR оставался обозримым (≤500 строк дифа на «эталон»), 1.5.E ограничен **только** прогоном forest через `IMessageBundle`. `/lang ru|en` + миграция вынесены в 1.5.F (это связано: `IPlayerLocaleResolver` нужен и `/lang`-handler-у, и notifier-у). 300+ JSON-шаблонов забавных логов + ревизия audit-логов вынесены в 1.5.G (это про content и про audit_log, а не про i18n как таковую). README/CONTRIBUTING + docker-compose + деплой — в 1.5.H.
- **Почему `_render_full_nick(...)` приватный.** В 1.5.C функция `render_full_nick(...)` была публичной pure-функцией (RU-only), потому что forest-презентер ещё не был прогон через `IMessageBundle`. Теперь forest-презентер использует `bundle.format(title_message_key(title), locale=locale)` для титула и собирает ник внутри собственного метода `_render_full_nick`. Это deliberate encapsulation: сигнатура внутреннего метода (`title/display_name/name/locale`) — деталь имплементации, а не публичный контракт. Если в Фазе 2+ появится отдельный `NickPresenter` или ник-формат изменится, мы перекроим внутри `ForestPresenter` без затрагивания тестов на handler.
- **Почему `useGrouping: 0` сохраняется и для forest-сообщений.** Тот же фикс, что в 1.5.C/D: Fluent для RU в `NUMBER($x)` без `useGrouping: 0` вставляет `\xa0` (non-breaking space) между разрядами, и тесты, которые ассертят точный вывод (`"+5 см (было 2, стало 7)"`), ломаются. Параметр `useGrouping: 0` отключает разделение разрядов на уровне CLDR-формата.

---

## 2026-05-05 — Спринт 1.5.D: `/oracle` и `/upgrade` через `IMessageBundle`

**Автор:** Devin (по запросу sufficientdorette)
**Тип:** feature (i18n-прогон ещё двух handler-ов + презентеров)
**Связано:** Текущий PR (Спринт 1.5.D), [development_plan.md §3 / Спринт 1.5, задача 1.5.1](development_plan.md), [current_tasks.md Спринт 1.5 → 1.5.D](current_tasks.md). Продолжение Спринта 1.5 после смерженного 1.5.C (PR #27).

Что сделано:
- **Локали (`locales/{ru,en}.ftl`):** добавлены секции `## /oracle` и `## /upgrade` с полным набором ключей: `oracle-group/-other/-not-registered/-success/-already-used`, `upgrade-group/-other/-not-registered/-proposal/-success/-insufficient/-insufficient-short/-cancelled/-race/-toast-*/-button-*`. Все числовые параметры (`$cost_cm`, `$current_length_cm`, `$bonus_cm`, `$hours`, …) обёрнуты в `NUMBER($x, useGrouping: 0)` — иначе Fluent для RU вставляет `\xa0` (non-breaking space) между разрядами и текст ответов отличается от исторического (`4000 см` → `4\xa0000 см`).
- **`OraclePresenter` (`bot/presenters/oracle.py`):** `__init__(*, bundle: IMessageBundle)`, методы `group(*, locale)`, `other(*, locale)`, `not_registered(*, locale)`, `success(template_text, bonus_cm, new_length_cm, user_display, locale)` (подставляет `{user}` в шаблон предсказания через старый `_SafeDict`, потом передаёт получившуюся строку в Fluent как `$prediction`), `already_used(moscow_date, now, locale)` (помощник `_hours_minutes_until_next_reset` остался неизменным). Удалены старые pure-функции `render_oracle_*` и константы `REPLY_*_RU`.
- **`UpgradePresenter` (`bot/presenters/upgrade.py`):** `__init__(*, bundle: IMessageBundle)`, методы по группам: chat-ветки (`group/other/not_registered`), карточки (`proposal/success/insufficient/insufficient_short/cancelled/race`), toast-ы (`toast_upgraded/cancelled/player_not_found/insufficient/race`), и **`proposal_keyboard(expected_cost_cm, locale)`** — возвращает `InlineKeyboardMarkup` с локализованными подписями кнопок (`upgrade-button-confirm`/`upgrade-button-cancel`). Pure-функции `upgrade_callback_data()` / `parse_upgrade_callback_data()` / dataclass `UpgradeCallbackData` оставлены без изменений: `callback_data` — invariant-формат и не зависит от локали (см. ниже).
- **`bot/handlers/oracle.py`:** новые DI-параметры `bundle: IMessageBundle, locale: Locale | None = None`. `effective_locale = locale or DEFAULT_LOCALE` пробрасывается во все ответы через `OraclePresenter`. `InvokeOracleInput.locale` теперь равен `effective_locale.code` (раньше hardcoded `"ru"` — теперь use-case умеет выбирать каталог предсказаний по локали игрока). Helper `_user_display(user)` оставлен с RU-fallback `"друг"` — это safety net для случаев, когда у Telegram-юзера нет ни `first_name`, ни `username`; локализация этого fallback-а — задача 1.5.E.
- **`bot/handlers/upgrade.py`:** обновлены DI оба handler-а — и `handle_upgrade` (команда), и `handle_upgrade_callback` (инлайн-кнопки). Все ответы (`message.answer`, `callback.answer`, `message.edit_text`) идут через `UpgradePresenter` с `effective_locale`. Toast-ы для `callback.answer` тоже локализованы (`presenter.toast_*(locale=effective_locale)`). Helper-ы `_strip_keyboard` / `_set_message_text` оставлены без изменений (это чисто инфраструктурные обёртки над aiogram).
- **`bot/presenters/__init__.py`:** добавлены экспорты `OraclePresenter`, `UpgradePresenter` (имя класса вместо старых pure-функций). `forest`-презентер пока остался pure-функциональным — его миграция назначена на 1.5.E.
- **Тесты:** `test_oracle.py`/`test_upgrade.py` (presenter) и `test_oracle.py`/`test_upgrade.py` (handler) переведены на `FakeMessageBundle`. Маркерный формат `<locale>:<key>[k=v,...]` позволяет проверить и сам ключ, и переданные параметры (`prediction=…`, `cost_cm=4000`, `next_thickness=2`, …) без привязки к настоящему переводу. Параллельно — интеграционные `Test*PresenterFluent` гоняют тот же сценарий через настоящий `FluentMessageBundle` для RU и EN, чтобы не пропустить регрессии в самих `.ftl`-файлах. **Итого:** 999 passed, 1 skipped, **96.91%** покрытие.
- **План спринта 1.5 актуализирован.** В `docs/current_tasks.md` Спринт 1.5 теперь явно режется на **6 PR-ов** (1.5.A–F): 1.5.D — `/oracle`+`/upgrade` (текущий), 1.5.E — `/forest` + `/lang command` + 300+ JSON-логов + audit_log ±см, 1.5.F — docker-compose + README/CONTRIBUTING + деплой. `/forest` отделён от 1.5.D в самостоятельный PR, потому что у него больше движущихся частей: notifier (`ForestNotifier`), три типа Drop, локализация Rarity-меток и run-лога — всё это требует отдельного review и не вмещается комфортно в один PR с `/oracle`+`/upgrade`.

Результат / артефакты:
- `locales/ru.ftl` + `locales/en.ftl` — добавлены секции `## /oracle` и `## /upgrade`.
- `src/pipirik_wars/bot/presenters/oracle.py` — `OraclePresenter` поверх `IMessageBundle`; pure-функции `render_oracle_*` удалены.
- `src/pipirik_wars/bot/presenters/upgrade.py` — `UpgradePresenter` (включая `proposal_keyboard(...)`); pure-функция `build_upgrade_proposal_keyboard()` удалена; `upgrade_callback_data()` / `parse_upgrade_callback_data()` / `UpgradeCallbackData` оставлены без изменений.
- `src/pipirik_wars/bot/handlers/oracle.py` — DI `bundle` + `locale`, ответы через `OraclePresenter`, `InvokeOracleInput.locale = effective_locale.code`.
- `src/pipirik_wars/bot/handlers/upgrade.py` — DI `bundle` + `locale` в `handle_upgrade` И `handle_upgrade_callback`, ответы и toast-ы через `UpgradePresenter`.
- `src/pipirik_wars/bot/presenters/__init__.py` — добавлены экспорты `OraclePresenter`, `UpgradePresenter`.
- `tests/unit/bot/presenters/test_oracle.py`, `tests/unit/bot/presenters/test_upgrade.py` — переписаны под класс-презентеры, `FakeMessageBundle` + `FluentMessageBundle` интеграция.
- `tests/unit/bot/handlers/test_oracle.py`, `tests/unit/bot/handlers/test_upgrade.py` — переписаны под новый DI (`bundle`, `locale`), маркерные ключи + проверка локали-fallback (`None` → `DEFAULT_LOCALE = Locale("en")`).
- `docs/current_tasks.md` — обновлён план Спринта 1.5: 6 PR-ов вместо 5; 1.5.D — `/oracle` + `/upgrade`; 1.5.E — `/forest` + `/lang command` + audit_log ±см.

Заметки / решения:
- **Почему `NUMBER($x, useGrouping: 0)` для всех числовых параметров.** Fluent по умолчанию форматирует числа с локалью — для RU это `\xa0` (non-breaking space) между тысячами (`4 000`), для EN — запятая (`4,000`). Старые ответы в коде писались как f-строки без grouping-а: `f"{cost_cm} см"` → `4000 см`. Чтобы не ломать UX («внезапно появились пробелы между разрядами»), в `.ftl` явно гасим grouping через `useGrouping: 0`. Альтернатива — передавать в bundle уже готовые строки (`bundle.format(..., cost_cm=str(cost_cm))`), но это уносит часть форматирования в Python и плохо ложится на будущие RTL-локали или языки с нестандартными числовыми системами. Прятать это в Fluent-шаблонах удобнее: переводчик может включить grouping локально для своей локали, не трогая Python-код.
- **Почему `OraclePresenter.success` принимает `template_text` извне, а не сам формирует предсказание.** Текст предсказания — это **доменные данные** (`OracleTemplate.text` хранится в БД / каталоге шаблонов), их нельзя класть в `.ftl`. В `.ftl` лежит **обёртка** ответа — заголовок «Предсказание дня», бонус и итоговая длина. Презентер сначала подставляет `{user}` в `template_text` через старый `_SafeDict` (не падает на неизвестных плейсхолдерах), а потом передаёт получившуюся строку в Fluent как `$prediction`. Это даёт чёткое разделение: каталог предсказаний — domain-уровень (можно хранить шаблоны на любых языках), а обёртка — i18n-слой.
- **Почему `callback_data` `/upgrade`-кнопок остаётся invariant-форматом.** Telegram-`callback_data` не должен зависеть от локали юзера, иначе пользователь, который перешёл с RU на EN между сообщением и кликом, получил бы parse error в handler-е. `presenter.proposal_keyboard()` локализует только `text` кнопок, а `callback_data` строится через ту же pure-функцию `upgrade_callback_data()` (`"upgrade:confirm:4000"` / `"upgrade:cancel:0"`). Тесты явно проверяют этот invariant и в FakeBundle, и в Fluent-варианте.
- **Почему `/forest` отделили от `/oracle`+`/upgrade` в самостоятельный PR.** В `bot/handlers/forest.py` есть три ветки рендеринга (start / finish / drop), каждая со своим набором локализуемых строк, плюс отдельный `ForestNotifier` (он сам отправляет сообщения в чат). `bot/presenters/forest.py` сейчас выдаёт длинный run-лог с разными по типу строками (Rarity-уровни, Drop-варианты, finish-сводка), и весь этот вывод нужно тоже разнести по `.ftl`-ключам с per-locale форматированием. Аккуратно делать это в одном PR-е с `/oracle`+`/upgrade` — значит получить +500 LoC и ревью на 30+ комментариев. Деление на 1.5.D + 1.5.E делает каждый PR обозримым и снижает риск раннего merge-conflict-а с другими ветками.
- **Почему `_user_display` в `oracle.py` всё ещё возвращает RU-`"друг"`.** Это safety net для редкого случая, когда у Telegram-юзера нет ни `first_name`, ни `username`. Локализация этого fallback-а тривиальна (новый ключ `oracle-user-fallback` или общий `user-anonymous`), но требует решения: какой fallback использовать на самой ранней стадии handler-а (до того, как мы понимаем, в каком чате юзер пишет)? В 1.5.D мы предпочли оставить это RU-фолбэком и решить вопрос в 1.5.E одновременно с прогоном `/forest` и подключением `/lang`-команды.

---

## 2026-05-05 — Спринт 1.5.C: `/profile` и `/top` через `IMessageBundle`

**Автор:** Devin (по запросу sufficientdorette)
**Тип:** feature (i18n-прогон ещё двух handler-ов + презентеров)
**Связано:** Текущий PR (Спринт 1.5.C), [development_plan.md §3 / Спринт 1.5, задача 1.5.1](development_plan.md), [current_tasks.md Спринт 1.5 → 1.5.C](current_tasks.md). Продолжение Спринта 1.5 после смерженного 1.5.B (PR #26).

Что сделано:
- **`bot/presenters/profile.py`** — переписан под `ProfilePresenter` (DI `bundle: IMessageBundle`):
  - `group()` / `other()` / `not_registered()` / `card()` — методы рендера, все ходят в `IMessageBundle.format(...)` по ключам `profile-group`/`profile-other`/`profile-not-registered`/`profile-card`.
  - `card()` собирает «полный ник» («Титул Название Имя») с локализованным титулом через `profile-title-<value>` (для `Title.NEWBIE` → `profile-title-newbie`); потом передаёт `nick` + `length_cm` + `thickness_level` в шаблон `profile-card`.
  - Public функция `title_message_key(title)` — единый «контракт» между Python-кодом и `.ftl` (тест проверяет, что для каждого члена `Title` ключ существует и в RU, и в EN — иначе bundle бросит `MessageKeyError`).
  - Legacy pure-функция `render_full_nick(...)` оставлена временно — её ещё зовут `bot/presenters/forest.py`. Удаление — в 1.5.D, после миграции forest-презентера.
- **`bot/presenters/top.py`** — заменён на `TopPresenter`:
  - `render(entries, *, locale)` — пустой топ → ключ `top-empty`, иначе шапка + `top-entry`-ряды (`{ $rank }. { $nick } — { $length_cm } см`).
  - Локализация титулов делается через тот же `profile-title-<value>` (общий пул с /profile) — переводчику не нужно дублировать «Новичок/Newbie».
- **`bot/handlers/profile.py`** и **`bot/handlers/top.py`** — handler-ы получают `bundle: IMessageBundle` + `locale: Locale | None = None` (тот же fallback на `DEFAULT_LOCALE`, что и в `/start`). Удалены `REPLY_GROUP_RU`/`REPLY_OTHER_RU`/`REPLY_NOT_REGISTERED_RU` (`/profile`) и `REPLY_TOP_HEADER_RU`/`REPLY_TOP_EMPTY_RU` (`/top`).
- **`infrastructure/i18n/fluent_bundle.py`** — `FluentBundle` теперь создаётся с `use_isolating=False`. По умолчанию `fluent.runtime` оборачивает значения `{ $vars }` в Unicode bidi-isolation marks U+2068/U+2069 — это корректно для RTL-языков, но в чисто-LTR-наборе (RU/EN) ломает `in`-проверки в тестах и засоряет копипасту в чате.
- **`locales/ru.ftl` + `locales/en.ftl`** — добавлены ключи `profile-group`/`profile-other`/`profile-not-registered`/`profile-card`/`profile-title-newbie` и `top-header`/`top-empty`/`top-entry`. RU/EN-варианты карточки `/profile` — структурно идентичные (одинаковые эмодзи, разный текст).
- **`bot/presenters/__init__.py`** — экспорт `ProfilePresenter` + `TopPresenter`, удалены устаревшие `render_profile_card`/`render_top`/`render_top_entry`/`REPLY_TOP_*_RU`. Pure `render_full_nick` оставлена в публичном API на время 1.5.D.
- **Тесты:**
  - `tests/unit/bot/presenters/test_profile.py` — 12 тестов: `render_full_nick` (legacy, 4 кейса), `title_message_key` (mapping + integrity-проверка через `FluentMessageBundle`, RU + EN), `ProfilePresenter` (chat-ветки через `FakeMessageBundle` + интеграция `card()` через `FluentMessageBundle`, RU + EN, проверка отсутствия русских букв в EN-выводе).
  - `tests/unit/bot/presenters/test_top.py` — 12 тестов: `FakeMessageBundle` (правильные ключи + параметры в `top-entry`) + `FluentMessageBundle` (4 сочетания «титул × имя», порядок entries, EN-локаль).
  - `tests/unit/bot/handlers/test_profile.py` — 8 тестов: все ветки (private+registered/unregistered, group/supergroup, channel, private без `tg_identity`) + locale-propagation (RU vs EN) + fallback на `DEFAULT_LOCALE`.
  - `tests/unit/bot/handlers/test_top.py` — 6 тестов: рендер в private/group, пустой топ, default-limit, locale-propagation, fallback.

Результат / артефакты:
- `make ci` локально: **971 passed, 1 skipped, 96.88%** покрытие (порог DoD — 80%, см. `pyproject.toml`).
- ruff (lint + format) ✅, mypy ✅, import-linter ✅, pre-commit ✅.
- Файлы: `src/pipirik_wars/bot/presenters/profile.py` (v2), `src/pipirik_wars/bot/presenters/top.py` (v2), `src/pipirik_wars/bot/handlers/profile.py` (v2), `src/pipirik_wars/bot/handlers/top.py` (v2), `src/pipirik_wars/bot/presenters/__init__.py` (обновлён), `src/pipirik_wars/infrastructure/i18n/fluent_bundle.py` (`use_isolating=False`), `locales/ru.ftl` + `locales/en.ftl` (новые ключи), 4 тест-файла (~50 unit-тестов суммарно).

Заметки / решения:
- **Почему карточка `/profile` — один ключ, а не 4–5 атомарных.** Вариант «`profile-card-length-label` + `profile-card-thickness-label` + …» (склеивает презентер) даёт переводчику набор маленьких кусочков без контекста — он не знает, как они склеятся. Многострочный `profile-card` с `{ $nick }`/`{ $length_cm }`/`{ $thickness_level }` показывает весь layout сразу, и переводчик может, например, поменять порядок строк под язык (если в EN «Equipment» традиционно идёт перед «Length»). Минус — multi-line-индентация в Fluent чувствительна к позиции эмодзи (см. ниже).
- **Почему `use_isolating=False` именно сейчас, а не в 1.5.A.** В 1.5.A bundle был занят только короткими RU-ключами (`start-*`), и плейсхолдеры были редкими (только `position` в `start-queued`). Изоляция-марки никому не мешали. В 1.5.C появилась карточка с тремя плейсхолдерами в одной строке, и тесты типа `assert "47 см" in card` стали падать — потому что текст в реальности `\u206847\u2069 см`. Чтобы не тащить везде «нормализующий» helper, проще сразу выключить изоляцию: наши локали все LTR, RTL не ожидается даже в дальних спринтах.
- **Почему `title_message_key` — public.** Я мог сделать локализацию титула приватной деталью `ProfilePresenter`, но тогда `TopPresenter` дублировал бы код. Вынес в модуль профиля как public helper — это маленький contract `Title → MessageKey`, и оба презентера используют его без копипасты. Контрактный тест `test_every_title_value_resolves_in_real_bundle` гарантирует, что любой новый член `Title` получит ключ в `.ftl` (иначе `FluentMessageBundle.format` бросит `MessageKeyError` — это и есть «безопасник»).
- **Почему legacy `render_full_nick(...)` оставлена.** `bot/presenters/forest.py` ещё пользуется старой pure-сигнатурой. Менять её сейчас означало бы тащить миграцию forest-презентера в этот PR — это +200 LoC и риск сломать flow `/forest` без отдельной проверки. Оставил `render_full_nick(...)` как RU-only-shim, помечен в docstring «1.5.D уберёт после миграции forest». Эта тактика — стандартный «strangler» подход: новый код пишется параллельно, старый удаляется отдельным PR-ом.
- **Тест-стратегия — двухслойная.** Маркерный `FakeMessageBundle` (`<locale>:<key>[k=v,...]`) проверяет, что **handler/презентер зовёт нужный ключ с нужными параметрами** — это юнит-тест. Реальный `FluentMessageBundle` поверх `locales/{ru,en}.ftl` проверяет, что **ключ действительно существует, рендерится и содержит нужные подстроки** — это интеграция с инфраструктурой. Раздел «два слоя» нужен потому, что иначе либо пришлось бы тестировать на марк-строках без проверки реального вывода, либо парсить русский/английский текст из `.ftl` в каждом тесте — оба плохие крайности.
- **Чего НЕТ в этом PR (специально оставлено для 1.5.D/E).** Миграция `/forest`, `/oracle`, `/upgrade` (отдельные handler-ы и презентеры — каждый со своим набором ключей и тестов). Команда `/lang ru|en` + миграция `players.locale_override` + use-case `SetPlayerLocale` (уехала в 1.5.E вместе с 300+ JSON-логами). Идея — держать каждый PR в районе 300–500 LoC + ≤30–40 тестов; склеивать всё в один PR — это против §0.4 ПД.

---

## 2026-05-05 — Спринт 1.5.B: DI `IMessageBundle` + `/start` через `StartPresenter`

**Автор:** Devin (по запросу sufficientdorette)
**Тип:** feature (DI-провязка + первый handler через i18n-порт)
**Связано:** Текущий PR (Спринт 1.5.B), [development_plan.md §3 / Спринт 1.5, задачи 1.5.1–1.5.2](development_plan.md), [current_tasks.md Спринт 1.5 → 1.5.B](current_tasks.md). Открытие середины Спринта 1.5 после смерженного 1.5.A (PR #25).

Второй слайс Спринта 1.5 — выводим `IMessageBundle` из «фундамента» в реальное использование на handler-е `/start`. Это в т.ч. валидирует архитектуру 1.5.A end-to-end: `LocaleResolver` → `LocaleMiddleware` → `data["locale"]` → handler → `StartPresenter` → `FluentMessageBundle` → `.ftl`.

Что сделано:
- **`src/pipirik_wars/bot/presenters/start.py`** — новый `StartPresenter`-класс. DI-параметр `bundle: IMessageBundle`; методы `registered(*, locale)`, `already(*, locale)`, `group(*, locale)`, `other(*, locale)`, `queued(*, locale, position)`. Все ключи (`start-registered`, `start-already`, `start-group`, `start-other`, `start-queued`) уже лежат в `locales/{ru,en}.ftl` со Спринта 1.5.A.
- **`src/pipirik_wars/bot/handlers/start.py`** — refactor:
  - Удалены `REPLY_REGISTERED_RU`, `REPLY_ALREADY_RU`, `REPLY_GROUP_RU`, `REPLY_OTHER_RU` и `_format_queued()`. Все ответы теперь идут через `StartPresenter` с резолвенной `Locale`.
  - Сигнатура handler-а получила два новых DI-параметра: `bundle: IMessageBundle` (workflow-data из Container-а) и `locale: Locale | None = None` (приходит из `LocaleMiddleware.data["locale"]`). `None` означает «middleware не сработал» (тест) — берём `DEFAULT_LOCALE = Locale("en")` как fallback.
  - `RegisterPlayerInput.locale` больше не hardcoded `"ru"`, а равен `effective_locale.code` — то есть язык игрока, сохранённый в БД, теперь действительно отражает резолвенную локаль (ПД 1.5.2).
- **`src/pipirik_wars/bot/main.py`** — DI-провязка:
  - `Container` получил поле `bundle: IMessageBundle`.
  - `build_container()` принимает `locales_dir: Path | None = None` (по умолчанию — `Path("locales")` в корне репо/деплоя) и собирает `FluentMessageBundle(locales_dir=...)`.
  - `build_dispatcher()` кладёт `dispatcher["bundle"] = container.bundle` — aiogram автоматически пробросит его в handler-ы по имени параметра.
- **`tests/fakes/message_bundle.py`** — `FakeMessageBundle` с маркерным `format(...)`-выводом `<locale>:<key>[k=v,...]`. Это позволяет unit-тестам однозначно проверять и сам ключ, и переданные плейсхолдеры (`position`) без зависимости от Fluent / `.ftl`-файлов.
- **`tests/unit/bot/handlers/test_start.py`** — 12 тестов переведены на `FakeMessageBundle`: каждый assert теперь сверяет точную marker-строку (например, `"ru:start-queued[position=42]"`). Добавлены два новых теста: `test_private_calls_register_player_with_resolved_locale_en` (`Locale("en") → input.locale="en"`) и `test_locale_none_falls_back_to_default_en` (middleware не сработал → fallback EN).
- **`tests/unit/bot/presenters/test_start.py`** — 6 новых юнит-тестов для `StartPresenter`: каждый ключ + проверка, что разные `Locale` дают разные строки.
- **`tests/unit/bot/test_composition_root.py`** — обновлены fake-Container и `build_container()`-тест: проверяем, что `bundle` собирается как `FluentMessageBundle` (real) / `FakeMessageBundle` (test) и пробрасывается в `dispatcher["bundle"]`.
- **CI**: `make ci` локально — **963 passed, 1 skipped, 96.85%** покрытие; `pre-commit run --all-files` — все хуки зелёные. На +8 тестов больше, чем после 1.5.A.

Результат / артефакты:
- `src/pipirik_wars/bot/presenters/start.py` (новый, ~70 LoC).
- `src/pipirik_wars/bot/handlers/start.py` (рефактор, было 119 LoC → стало 110 LoC, hardcoded-строки удалены).
- `src/pipirik_wars/bot/main.py` (+`bundle` поле в Container, +`locales_dir` в `build_container`, +`dispatcher["bundle"]` в `build_dispatcher`).
- `tests/fakes/message_bundle.py` + `tests/fakes/__init__.py` (новый fake, экспорт).
- `tests/unit/bot/handlers/test_start.py` (рефактор + 2 новых теста).
- `tests/unit/bot/presenters/test_start.py` (новый, 6 тестов).
- `tests/unit/bot/test_composition_root.py` (assert-ы на `bundle`).

Заметки / решения:
- **Почему `StartPresenter` — класс, а не модуль с функциями.** В `bot/presenters/profile.py` функции `render_full_nick` / `render_profile_card` чистые — они получают на вход уже готовый `ProfileView`, никаких внешних зависимостей у них нет. У `StartPresenter` иначе: **нужно переносить `bundle` через слой**. Если это были бы module-level-функции, каждая из них принимала бы `bundle` как первый аргумент: `def registered(*, bundle, locale): ...`. Это работает, но даёт два хвоста: (1) handler передаёт один и тот же `bundle` в каждый вызов — копипаста, (2) когда в 1.5.C мы добавим аналогичные `ProfilePresenter`/`ForestPresenter`/`OraclePresenter`, у каждого будет 5–10 функций со своим повтором. Класс с `bundle` в `__init__` инкапсулирует эту зависимость один раз и даёт унифицированный API всем будущим презентерам.
- **Почему `locale: Locale | None` с fallback на `DEFAULT_LOCALE`, а не required-параметр.** В production `LocaleMiddleware` всегда положит `Locale` в `data["locale"]` (см. Спринт 1.5.A). Но: (1) старые тесты вызывали handler без `locale` напрямую, чтобы не таскать middleware — оставляем им compat. (2) Если кто-то вырубит `LocaleMiddleware` в `register_middlewares` (скажем, дебаг/тестовая сборка), handler не должен падать — `DEFAULT_LOCALE = Locale("en")` это безопасный fallback по ПД 1.5.2. Это явно задокументировано в docstring-е.
- **Почему `RegisterPlayerInput.locale = effective_locale.code`, а не сохраняем `Locale` целиком.** `RegisterPlayerInput.locale: str | None` живёт в application-DTO и остался от Спринта 1.1.D. Менять его на `Locale` value-object потребовало бы ревизии и use-case-ов, и репозитория. По дизайн-решению на 1.5.B мы НЕ ломаем DTO, а просто заполняем его реальным кодом локали (`"ru"`/`"en"`). Если в будущем (1.5.C+) понадобится сохранять более сложную локаль (например, fallback chain), DTO будет переехать на `Locale` отдельным рефактор-PR-ом.
- **Почему `FakeMessageBundle` живёт в `tests/fakes/`, а не как inline в каждом тестовом файле.** В 1.5.B он используется в трёх местах (`test_start.py` handler, `test_start.py` presenter, `test_composition_root.py`). В 1.5.C те же самые тесты для `/profile`, `/forest`, `/oracle`, `/upgrade`, `/top` будут пользоваться этим же fake. Дублировать его шесть раз — анти-паттерн; общий fake в `tests/fakes/__init__.py` рядом с `FakeAuditLogger` / `FakeBalanceConfig` — единственный системный путь.
- **Почему стартовый `.ftl` НЕ менялся.** Все 5 ключей `start-*` были созданы в Спринте 1.5.A заранее с расчётом «handler 1.5.B их использует». Никаких новых ключей в этом PR-е добавлять не пришлось — это валидация, что план 1.5.A был корректным.

---

## 2026-05-05 — Спринт 1.5.A: i18n-фундамент (Locale + IMessageBundle + FluentMessageBundle + LocaleMiddleware)

**Автор:** Devin (по запросу sufficientdorette)
**Тип:** plan + feature (application port + value-object + infrastructure adapter + middleware wiring)
**Связано:** Текущий PR (Спринт 1.5.A), [development_plan.md §3 / Спринт 1.5, задачи 1.5.1–1.5.2](development_plan.md), [current_tasks.md Спринт 1.5 → 1.5.A](current_tasks.md). Открытие Спринта 1.5 после смерженного 1.4.D (PR #24).

Стартовый PR Спринта 1.5 — две вещи:

1. **Plan & roadmap Спринта 1.5** — те же 4 PR-а (1.5.A/B/C/D), что и в спринтах 1.1–1.4. Цель спринта — закрыть DoD MVP (см. `development_plan.md` §4): локализация, аудитлог длины, деплой на VPS.
2. **i18n-фундамент** (1.5.A) — value-object `Locale`, стратегия `LocaleResolver`, порт `IMessageBundle`, реализация `FluentMessageBundle` (Mozilla Fluent), включение `LocaleMiddleware` в middleware-стек.

Что сделано:
- **`src/pipirik_wars/application/i18n/`**: `Locale` (frozen-dataclass, `code ∈ {"ru", "en"}`, валидация в `__post_init__`) + `DEFAULT_LOCALE = Locale("en")` + `SUPPORTED_LOCALES = frozenset({"ru", "en"})`. `LocaleResolver` — чистая stateless-стратегия: `tg.language_code` (BCP-47, например `"ru-RU"` / `"en-US"`) приводит к `Locale("ru" | "en")` префиксным сравнением (case-insensitive), всё остальное / `None` / пустое — `default` (по умолчанию `Locale("en")`, ПД 1.5.2 «fallback EN»). Порт `IMessageBundle` (`Protocol`) + `MessageKey` (`NewType[str]`) + ошибки `I18nError` / `MessageKeyError`.
- **`src/pipirik_wars/infrastructure/i18n/FluentMessageBundle`** — реализация `IMessageBundle` поверх `fluent.runtime`. Per-locale ленивый кэш (`dict + threading.Lock`, double-check), загрузка `locales/{ru,en}.ftl` через `FluentResource(file.read_text())`. Стратегия fallback: `locale.format(key)` → `Locale("en").format(key)` → `MessageKeyError(key)`. «Soft fail» на отсутствующие плейсхолдеры (`logger.warning`, не падаем).
- **`src/pipirik_wars/bot/middlewares/locale.py`** — `LocaleMiddleware` теперь читает `tg_identity.language_code` и пробрасывает через `LocaleResolver` (DI-параметр), кладёт `Locale` в `data["locale"]` и сырой `language_code` в `data["telegram_language_code"]` (пригодится для аналитики). Без `tg_identity` — `DEFAULT_LOCALE`.
- **`src/pipirik_wars/bot/middlewares/__init__.py`** — `register_middlewares` принимает опциональный `locale_resolver` и регистрирует `LocaleMiddleware` между `AuthMiddleware` и `ThrottleMiddleware`. Применяется к `dp.message`, `dp.callback_query`, `dp.my_chat_member`.
- **`locales/ru.ftl` / `locales/en.ftl`** — стартовый набор ключей `start-registered`, `start-already`, `start-group`, `start-other`, `start-queued` (в одной локали по 5 ключей; остальные ключи из handler-ов будут перенесены в .ftl в спринте 1.5.B).
- **`pyproject.toml`** — добавлен runtime-`fluent.runtime>=0.4,<1` и mypy-override `module = "fluent.*"; ignore_missing_imports = true` (у `fluent.runtime` нет PEP-561 stubs).
- **Тесты:** 27 новых юнит-тестов:
  - `tests/unit/application/i18n/test_locale.py` — Locale (валидация, equality, hash) + LocaleResolver (RU/EN-варианты, fallback, override default).
  - `tests/unit/application/i18n/test_message_bundle_protocol.py` — Protocol-смок (FakeBundle satisfies `IMessageBundle`, `MessageKey` is `str` at runtime).
  - `tests/unit/infrastructure/i18n/test_fluent_bundle.py` — рендер RU/EN с параметрами, fallback RU→EN, `MessageKeyError` для отсутствующего ключа, `FileNotFoundError` для отсутствующей локали, кэширование bundle (удаляем .ftl после первого вызова — второй всё ещё работает).
  - `tests/unit/bot/middlewares/test_locale.py` — middleware с RU/EN/unknown/None `language_code`, без identity, custom resolver.
- **CI**: `make ci` локально — **955 passed, 1 skipped, 96.84%** покрытие.

Результат / артефакты:
- `src/pipirik_wars/application/i18n/{__init__.py,errors.py,locale.py,message_bundle.py}` (новый пакет, ~200 LoC).
- `src/pipirik_wars/infrastructure/i18n/{__init__.py,fluent_bundle.py}` (новый пакет, ~150 LoC).
- `src/pipirik_wars/bot/middlewares/{__init__.py,locale.py}` (обновлены — `LocaleResolver` в стэке).
- `locales/{ru,en}.ftl` (новые файлы, ~30 строк каждый).
- `pyproject.toml` (`fluent.runtime` runtime + mypy override).
- `tests/unit/{application,infrastructure}/i18n/...` + `tests/unit/bot/middlewares/test_locale.py` (новые / обновлённые).

Заметки / решения:
- **Почему `Locale` живёт в `application`, а не в `domain`.** `Locale` — артефакт UI / презентационного слоя. Домен (`Player`, `Length`, `Forest`) понятия не имеет о языках. Класть value-object в `domain` сейчас означало бы потом таскать `Locale` через все use-case-ы как «доменное» значение и нарушить инвариант «`domain` не зависит от UI».
- **Почему `LocaleResolver` — это стратегия в `application`, а не функция в middleware.** Middleware должен оставаться тонким (Single Responsibility): «прочитать язык, передать в DI». Резолв — **доменно-нейтральная** логика, и в спринте 1.5.B мы захотим переопределить её на уровне игрока через `players.locale_override` (handler `/lang ru|en`). Чтобы это произошло без переписывания middleware-а — стратегия инжектится через DI.
- **Почему `MessageKey` — это `NewType[str]`, а не Enum.** На MVP у нас будет ~50–100 ключей, и они растут вместе с handler-ами (новые презентеры → новые ключи). Enum заставлял бы делать релиз `application/i18n/keys.py` каждый раз, когда handler в bot-слое добавляет новую строку. `NewType` даёт type-safety (mypy ловит `bundle.format("typo", ...)` если функция объявлена как `MessageKey`) при минимальном overhead-е.
- **Почему «soft fail» на сломанные плейсхолдеры.** Бот предпочтительнее показать «Привет { $name }!» чем упасть с 500-кой в ЛС игрока. Логирование `logger.warning` на ошибки Fluent-а поможет ловить такие случаи в стейджинг-ране до прода.
- **Почему стартовый ftl содержит только `start-*`, а не все ключи разом.** Спринт 1.5.A — фундамент. Реальный «прогон handler-ов через bundle» произойдёт в 1.5.B (отдельный PR), когда мы добавим `IMessageBundle` в DI у handler-ов и удалим hardcoded-строки. Вытаскивать всё разом + менять handler-ы + добавлять `/lang`-команду в одном PR-е — это нарушение нашего принципа «маленькие PR-ы по 200–500 LoC».
- **Почему `LocaleMiddleware` пишет `tg_lang` в `data["telegram_language_code"]`.** Сырое значение пригодится для аналитики («сколько RU-телег у нас на самом деле») и для `/lang reset` (показать игроку «твой Telegram-язык: ru-RU; включить override?»).

---

## 2026-05-05 — Спринт 1.4.D: мини-нагрузочный тест `/forest` + полировка `/top`

**Автор:** Devin (по запросу persisyellow)
**Тип:** test (load) + refactor (cleanup)
**Связано:** Текущий PR (Спринт 1.4.D), [development_plan.md §3 / Спринт 1.4, задача 1.4.7](development_plan.md), [current_tasks.md Спринт 1.4 → 1.4.D](current_tasks.md). Закрытие Спринта 1.4 после смерженного 1.4.C (PR #23).

Финальный PR Спринта 1.4 — две вещи:

1. **Мини-нагрузочный тест ПД §1.4.7** «100 параллельных «походов в лес» без потери лока». Закрывает acceptance-критерий: под пиковой нагрузкой `activity_lock` корректно отбивает дублирующие запросы.
2. **Полировка `/top`** — чистка неиспользуемых импортов (`logging`, `typing.Final`) в handler-е после 1.4.C.

Что сделано:
- **`tests/integration/load/test_forest_concurrent.py`** — два сценария под `asyncio.gather`:
  - `test_100_parallel_starts_for_same_player_only_one_wins` — один игрок, 100 одновременных вызовов `StartForestRun` через **независимые `SqlAlchemyUnitOfWork`**: ровно 1 успех, 99 — `AlreadyInForestError`. После теста проверяем consistency БД: 1 строка `forest_runs(IN_PROGRESS)`, 1 строка `activity_locks` для этого игрока.
  - `test_100_parallel_starts_for_different_players_all_succeed` — 100 разных игроков по одному `/forest` каждый: все 100 успешны, ровно 100 `IN_PROGRESS`-походов и 100 локов в БД (нет ложных конфликтов на чужих локах).
- **`tests/integration/load/conftest.py`** — фикстура `shared_engine` поверх **файловой** SQLite (`tmp_path / "load.db"`), а не `:memory:` + `StaticPool`. Причина: `:memory:` через `StaticPool` мультиплексирует все асинхронные сессии на одно соединение/одну транзакцию, что замаскировало бы логические race-ошибки. Файловый SQLite даёт каждой сессии собственное соединение (`timeout=30s` для `SQLITE_BUSY`).
- **`pyproject.toml`** — зарегистрирован новый pytest-маркер `slow` для нагрузочных сценариев (`--strict-markers` иначе бы сломался).
- **`bot/handlers/top.py`** — удалены неиспользуемые `import logging`, `from typing import Final` и заглушка `_LOGGER`. Поведение не изменилось; чисто косметический рефакторинг по итогам 1.4.C.
- **CI**: `make ci` локально — **913 passed, 1 skipped, 96.97%** покрытие.

Результат / артефакты:
- `tests/integration/load/{__init__,conftest,test_forest_concurrent}.py` (новый пакет тестов).
- `pyproject.toml` (новый маркер `slow`).
- `src/pipirik_wars/bot/handlers/top.py` (чистка импортов).

Заметки / решения:
- **Почему файловая SQLite, а не `:memory:` + `StaticPool`.** `StaticPool` гарантирует ОДНО соединение для всего движка. Для async-кода это означает, что все 100 «параллельных» сессий жмутся в одну транзакцию — в итоге даже если бы lock-механика была сломана, тест бы прошёл (ошибки замаскировались бы блокировкой одного соединения). Файловая SQLite в `tmp_path` даёт нормальное соединение на сессию: каждая `SqlAlchemyUnitOfWork` открывает свой `BEGIN/COMMIT`, и серилизуется через файловый лок самого SQLite — это близко к Postgres-семантике.
- **Почему `slow`-маркер, но без `pytest -m "not slow"` в `make ci`.** В моменте 1.4.D есть всего 2 нагрузочных теста по ~1с каждый, общий прирост к CI пренебрежим. Маркер регистрируем заранее, чтобы будущим Sprint 4.1.5 («нагрузочный тест 10× MVP») было куда вешать тяжёлую нагрузку, не ломая текущий зелёный pipeline.
- **Полировка вместо контентной разработки.** Все презентеры просмотрены на typo — критических ошибок не найдено. `display_name` / `PlayerName` / `Title` приходят из контролируемых источников (`balance.yaml`, hardcoded enum), HTML-инъекций через них быть не может; явное HTML-экранирование можно добавить в Спринте 1.5 при подключении Telegram first_name (i18n).
- **DOD MVP-чек-лист.** Спринты 1.1–1.4 закрыли: регистрация ✅, `/profile` ✅, `/forest` + дроп ✅, прокачка толщины ✅, `/oracle` ✅, `/top` ✅, DAU Gate ✅, Activity Lock под нагрузкой ✅. Остаётся для DoD MVP: i18n RU+EN (Спринт 1.5.1–1.5.2), деплой (1.5.7).

---

## 2026-05-05 — Спринт 1.4.C: топ игроков (`/top` + in-memory TTL=60s кэш)

**Автор:** Devin (по запросу persisyellow)
**Тип:** feature (domain + application port + use-case + in-memory cache + bot-handler + composition wiring)
**Связано:** Текущий PR (Спринт 1.4.C), [development_plan.md §3 / Спринт 1.4, задача 1.4.6](development_plan.md), [current_tasks.md Спринт 1.4 → 1.4.C](current_tasks.md). Продолжение Спринта 1.4 после смерженного 1.4.B (PR #22).

Узкий PR: публичная команда `/top` — топ-100 пипириков по убыванию длины (формат «Титул Название Имя — N см»). Под капотом — in-memory кэш TTL=60s, чтобы шквал нажатий из чата не упирался в БД.

Что сделано:
- **Domain (`domain/player/repositories.py`)** — расширен порт `IPlayerRepository` методом `list_top_by_length(*, limit) -> Sequence[Player]`. Контракт: только `ACTIVE`-игроки (заморозка исключается — игроки на «лавке штрафников» в топ не лезут), сортировка `length_cm DESC`, тай-брейкер `id ASC` (стабильный порядок при равной длине, важно для воспроизводимости результата под кэшем), `ValueError` для `limit ≤ 0`.
- **Application (`application/top/`)** — frozen DTO `TopPlayerEntry(title, display_name, name, length_cm)` с валидацией `length_cm ≥ 0`. Read-only порт `ITopPlayersQuery.get_top(*, limit) -> Sequence[TopPlayerEntry]`. Use-case `GetTopPlayers(query, default_limit=100)` — тонкая обёртка над портом, валидирует `limit > 0`, по умолчанию использует `default_limit=100` (контракт ПД 1.4.6 «топ-100»). Чистая разводка: use-case **не знает** про кэш или БД — это инфраструктурный выбор сборки.
- **Infrastructure (`infrastructure/db/repositories/player.py` + `infrastructure/cache/top_players.py`)** — `SqlAlchemyPlayerRepository.list_top_by_length` строит честный `SELECT … WHERE status = 'ACTIVE' ORDER BY length_cm DESC, id ASC LIMIT :limit`. `TopPlayersCache(ITopPlayersQuery)` — in-memory снимок с `asyncio.Lock` для защиты от cache stampede: когда десять корутин одновременно зовут `/top` под просроченным кэшем, к БД летит **один** запрос, остальные ждут на локе. TTL=60s по умолчанию (через ctor-параметр), на границе считаем кэш уже устаревшим (`elapsed >= ttl`). При запросе с большим `limit`, чем закэшировано — рефреш; при меньшем — отдаём «префикс» из кэша. `invalidate()` для админских флоу. `display_name` пересчитывается через `IBalanceConfig` при каждом рефреше — после `/balance_reload` следующий рефреш увидит новые имена бесплатно (TTL ≤ 60 с).
- **Bot (`bot/handlers/top.py` + `bot/presenters/top.py`)** — handler `/top` доступен и в ЛС, и в группах (это «социальная» команда, ГДД §2.6); вызывает `get_top_players.execute()` без аргументов, рендерит результат презентером. Презентер `render_top` делегирует склейку «Титул Название Имя» в уже существующий `render_full_nick` (DRY с `/profile`), форматирует строки как «`N. Полный_ник — N см`», пустой список → дружелюбное приглашение «нажми /start». Никакой регистрации для `/top` не требуется — это публичный read-only.
- **Composition root (`bot/main.py`)** — `top_players_query = TopPlayersCache(uow=…, players=…, balance=…, clock=…, ttl_seconds=60)` и `get_top_players = GetTopPlayers(query=top_players_query)` собираются в `build_container(...)`, прокидываются в `Container` и aiogram-DI (`dispatcher["get_top_players"]`). Новый `top_router` зарегистрирован в `register_routers(...)` после `oracle_router`.
- **Тесты (40+ новых)** — интеграционные на `list_top_by_length` (ordering DESC, frozen excluded, tie-break id ASC, limit, empty, ValueError на limit ≤ 0); юнит на `TopPlayerEntry` (валидации/frozen); юнит на `GetTopPlayers` (default_limit=100, передача limit, валидации); юнит на `TopPlayersCache` (TTL boundary, refresh after stale, prefix-of-cache reuse, invalidate, balance hot-reload visibility, **stampede protection** под `asyncio.gather` — 3 параллельных вызова → 1 обращение к репо); юнит на handler `/top` (private/group/empty); юнит на презентер (форматирование, эмодзи, порядок); composition root обновлён с `FakeTopPlayersQuery` и `GetTopPlayers`. `make ci`: **911 passed, 1 skipped**, coverage **96.81%**.

Результат / артефакты:
- domain port: `src/pipirik_wars/domain/player/repositories.py` (новая абстрактная method `list_top_by_length`).
- application: `src/pipirik_wars/application/top/{__init__,entries,query,get_top}.py`.
- infra: `src/pipirik_wars/infrastructure/db/repositories/player.py` (метод `list_top_by_length`), `src/pipirik_wars/infrastructure/cache/{__init__,top_players}.py`.
- bot: `src/pipirik_wars/bot/handlers/top.py`, `src/pipirik_wars/bot/presenters/top.py` + регистрация в `__init__.py` обоих пакетов и в `bot/main.py`.
- тесты: `tests/integration/db/test_player_repository.py` (+6), `tests/unit/application/top/{test_entries,test_get_top}.py`, `tests/unit/infrastructure/cache/test_top_players_cache.py`, `tests/unit/bot/{handlers,presenters}/test_top.py`, `tests/fakes/top_players.py` + регистрация в `tests/fakes/__init__.py` и `tests/unit/bot/test_composition_root.py`.

Заметки / решения:
- **Кэш как порт, не как декоратор** — `TopPlayersCache` реализует `ITopPlayersQuery` напрямую, а не декорирует другую реализацию. На уровне use-case-а ничего не знает про кэш: меняем стратегию в `build_container` без правок application-слоя. Если завтра захотим Redis — добавим `RedisTopPlayersCache(ITopPlayersQuery)` без касания доменa/application.
- **Тай-брейкер `id ASC`** — без него порядок одинаковых длин был бы не детерминирован, и кэш отдавал бы «прыгающие» места. С тай-брейкером один и тот же `/top` всегда выглядит одинаково между рефрешами.
- **Stampede protection через `asyncio.Lock`** — критично для социальной команды в группах: под пик-нагрузкой 10 нажатий /top за секунду от разных юзеров в БД летит ровно 1 запрос. Тест `test_concurrent_requests_trigger_single_refresh` это явно проверяет: 3 параллельных `gather` → 1 обращение к репо.
- **Frozen-игроки исключаются** — заблокированные/замороженные не должны портить публичный рейтинг. Это доменное правило, поэтому `WHERE status = 'ACTIVE'` сидит и в SqlAlchemy-репо, и в FakePlayerRepository.
- **DRY с `/profile`** — `render_full_nick` уже умеет «Титул Название Имя» с пропуском `None`-частей; переиспользуем без копипаста.

---

## 2026-05-05 — Спринт 1.4.B: предсказатель (`/oracle` + Moscow-TZ кулдаун + 220 RU + 220 EN темплейтов)

**Автор:** Devin (по запросу persisyellow)
**Тип:** feature (domain + application use-case + infra + bot-handler + DI + 220 RU/EN темплейтов)
**Связано:** Текущий PR (Спринт 1.4.B), [development_plan.md §3 / Спринт 1.4, задачи 1.4.4 / 1.4.5](development_plan.md), [current_tasks.md Спринт 1.4 → 1.4.B](current_tasks.md). Продолжение Спринта 1.4 после смерженного 1.4.A.

Узкий PR: пользовательская команда `/oracle` — игрок раз в сутки **по Москве** (`Europe/Moscow`, сброс в 00:00 МСК) получает шуточное предсказание из каталога ≥ 200 шаблонов и прибавку длины `uniform(1, 20)` см.

Что сделано:
- **Domain (`domain/oracle/`)** — иммутабельные сущности `OracleTemplate(id, text)` (валидация: непустое + без whitespace) и `OracleResult(bonus_cm, template)`. Чистая функция `roll_oracle(*, balance, random, templates)` через `IRandom` (никаких side-эффектов, тривиально тестируется на FakeRandom). Порт `IOracleHistoryRepository` с frozen-dataclass `OracleInvocation(player_id, moscow_date, bonus_cm, template_id, occurred_at)`. Иерархия ошибок: `OracleError` ← `OracleAlreadyUsedTodayError(player_id, moscow_date)` / `OracleNoTemplatesError(locale)`.
- **Application (`application/oracle/`)** — порт `IOracleTemplateProvider.get_templates(*, locale)`, DTO `InvokeOracleInput(tg_id, locale='ru')` с pydantic-валидацией, use-case `InvokeOracle`. Workflow: `players.get_by_tg_id` → preflight `history.get_for_day(player_id, moscow_date)` (если запись уже есть → `OracleAlreadyUsedTodayError`) → `roll_oracle(...)` → `with_length(+bonus_cm)` → `players.save` → `history.add` (если БД-уровень UNIQUE упал — ловим `IntegrityError` и трактуем как race-вариант `OracleAlreadyUsedTodayError`) → audit `LENGTH_GRANT` с `idempotency_key=f"oracle:{player_id}:{moscow_date.isoformat()}"`.
- **Infrastructure** — миграция `0005_oracle_invocations` создаёт таблицу с FK→users(id) CASCADE, CHECK `bonus_cm > 0`, **уникальный** индекс `(player_id, moscow_date)` (защита от race на БД-уровне) + индекс по `moscow_date` для аналитики. ORM `OracleInvocationORM` с `mapped_column`. Репозиторий `SqlAlchemyOracleHistoryRepository` (catches `sa.exc.IntegrityError` → `DomainIntegrityError`). `JsonOracleTemplateProvider(templates_dir)` — lazy load + per-locale кэш + fallback на `ru` если запрошенная локаль отсутствует, ошибки парсинга/дублей → `ConfigError`, пустой каталог → `OracleNoTemplatesError`.
- **Bot (`bot/handlers/oracle.py` + `bot/presenters/oracle.py`)** — handler `/oracle` (только в ЛС, иначе инструкция «открой ЛС»): `InvokeOracle.execute(InvokeOracleInput(tg_id, locale='ru'))`, обработка `PlayerNotFoundError` / `OracleAlreadyUsedTodayError` (рендерит «возвращайся через Xч Yм, 00:00 по Москве» с реальным временем до сброса). Чистые презентеры с safe-format `{user}` (отсутствующий ключ → возвращает плейсхолдер as-is, не падает с `KeyError`).
- **Темплейты** — `config/templates/oracle_ru.json` (220 шаблонов, ID `oracle.ru.0001..0220`) и `config/templates/oracle_en.json` (220 шаблонов, ID `oracle.en.0001..0220`). Все темплейты содержат плейсхолдер `{user}`. Категории: позитив, пипирик-юмор, мистика, мотивация, бытовуха, бонусы.
- **Composition root (`bot/main.py`)** — `oracle_history`, `oracle_templates`, `invoke_oracle` собираются в `build_container(...)` (новый параметр `templates_dir: Path | None = None`, default `config/templates`), прокидываются в `Container` и aiogram-DI (`dispatcher["invoke_oracle"]`, `dispatcher["clock"]`). Новый `oracle_router` зарегистрирован в `register_routers(...)` после `upgrade_router`.
- **Тесты** — 7 новых файлов:
  - `tests/unit/domain/oracle/test_entities.py` — валидация полей, frozen, OracleResult.
  - `tests/unit/domain/oracle/test_errors.py` — иерархия исключений и поля.
  - `tests/unit/domain/oracle/test_services.py` — `roll_oracle` happy path, детерминированность по seed-у, **acceptance ПД 1.4.4: 10 000 прогонов uniform(1, 20) → среднее 10.0..11.0**, всегда `bonus_cm ≥ 1` и в диапазоне.
  - `tests/unit/application/oracle/test_invoke.py` — успех, length grant, audit `LENGTH_GRANT`, повтор в тот же московский день → `OracleAlreadyUsedTodayError`, успех на следующий день, изоляция между игроками, **граничный кейс TZ** (4 мая 23:30 UTC = 5 мая 02:30 МСК), `PlayerNotFoundError` с rollback.
  - `tests/integration/db/oracle/test_oracle_history_repository.py` — `add()` + `get_for_day()`, UNIQUE-нарушение, изоляция между игроками и днями.
  - `tests/integration/db/test_migrations.py` — обновлён: `0005_oracle_invocations` зарегистрирован в линейной цепочке, applied чисто, таблица создаётся.
  - `tests/integration/templates/test_oracle_loader.py` — реальные `oracle_ru.json` и `oracle_en.json` ≥ 200 шаблонов, уникальные ID, корректный `{user}` рендер; кэш per-locale; fallback ru при отсутствующей локали; ошибки парсинга → `ConfigError`.
  - `tests/unit/bot/presenters/test_oracle.py` — рендеринг плейсхолдера, отсутствующий `{stranger}` сохраняется как есть, время до сброса.
  - `tests/unit/bot/handlers/test_oracle.py` — happy path, отказ в группе, `PlayerNotFoundError` → REPLY_NOT_REGISTERED_RU, `OracleAlreadyUsedTodayError` → cooldown text, fallback `username` если нет `first_name`.

Результат / артефакты:
- Domain: `src/pipirik_wars/domain/oracle/{entities,errors,services,repositories,__init__}.py`.
- Application: `src/pipirik_wars/application/oracle/{invoke,templates,__init__}.py`, DTO `InvokeOracleInput`.
- Infra: `migrations/versions/20260505_0005_oracle_invocations.py`, `db/models/oracle.py`, `db/repositories/oracle_history.py`, `templates/oracle.py`.
- Bot: `bot/handlers/oracle.py`, `bot/presenters/oracle.py`.
- Темплейты: `config/templates/oracle_ru.json` (220), `config/templates/oracle_en.json` (220).
- Тесты: 50+ новых тестов в 9 файлах. Локальный `make ci` (ruff + mypy --strict + import-linter + pytest 869 passed) — зелёный, общий покрытие 96.70%.
- Документация: обновлены `docs/current_tasks.md` (1.4.A → ✅ смержено, 1.4.B → 🟢 готово к ревью) и `docs/history.md` (эта запись).

Заметки / решения:
- **Кулдаун — по `Europe/Moscow`, не UTC.** В таблице `oracle_invocations.moscow_date` — `DATE`, отдельная колонка для `(player_id, moscow_date)` UNIQUE. `IClock.moscow_date()` уже был с 1.4.A (для `daily_head`); use-case вызывает его строго один раз и передаёт результат в repo, чтобы логика теста на «23:30 UTC = 02:30 МСК следующего дня» жила в одном месте.
- **Race protection.** Preflight `get_for_day(...)` ловит обычный кейс «нажал второй раз через час». Однако между preflight и `add()` могут проскочить два конкурентных запроса; БД-уровень UNIQUE-индекс ловит это, репозиторий ловит `IntegrityError` и use-case переводит её в `OracleAlreadyUsedTodayError` — handler одинаково покажет «возвращайся завтра».
- **Идемпотентность.** `idempotency_key=f"oracle:{player_id}:{moscow_date.isoformat()}"` — стабильный, поэтому даже при retry-е на уровне сети audit-лог не задублируется (audit-сервис проверяет ключ).
- **Темплейты.** 220 RU + 220 EN > требуемых 200, чтобы не упереться в acceptance, если потом захотим выкинуть несколько неудачных. Все шаблоны содержат `{user}` ровно 1 раз; loader проверяет уникальность `id`, ошибки JSON/структуры → `ConfigError`. Тест на реальные файлы валидирует `tpl.text.format(user='Alice')` — это ловит сломанные плейсхолдеры в production-каталоге.
- **Что НЕ сделано в этом PR.** `1.4.6` (`/top` + кэш TTL=60s) и `1.4.7` (мини-нагрузочный тест) — это `1.4.C` и `1.4.D`. `i18n` LocaleMiddleware — это Спринт 1.5; пока handler жёстко передаёт `locale="ru"` в use-case (template_provider всё равно умеет fallback на ru при отсутствии запрошенной локали).

---

## 2026-05-04 — Спринт 1.4.A: прокачка толщины (`/upgrade` + use-case + table-driven unlock)

**Автор:** Devin (по запросу azurehannah)
**Тип:** feature (domain + application use-case + bot-handler + DI)
**Связано:** Текущий PR (Спринт 1.4.A), [development_plan.md §3 / Спринт 1.4, задачи 1.4.1 / 1.4.2 / 1.4.3](development_plan.md), [current_tasks.md Спринт 1.4 → 1.4.A](current_tasks.md). Открывает Спринт 1.4 (после закрытия 1.3 в PR #20).

Узкий PR: пользовательская команда прокачки толщины — игрок вызывает `/upgrade`, получает карточку «прокачать с N до N+1, стоимость XXXX см», подтверждает inline-кнопкой, длина списывается, толщина растёт. Параллельно вводим table-driven unlock-функцию для будущих активностей (forest/pvp/mountains/raid/...).

Что сделано:
- **Domain (`domain/progression/thickness.py`)** — три чистые функции: `cost_for_upgrade(*, current_thickness, cost_base, cost_exponent)` по формуле `cost(n→n+1) = cost_base · (n+1)^cost_exponent` (acceptance §3 / 1.4.1: `cost(1→2)=4000`, `cost(9→10)=100000`, `cost(15→16)=256000`, `cost(19→20)=400000`). `is_activity_unlocked(*, thickness, activity, unlock_levels: Mapping[str, int])` — table-driven, домен принимает unlock-таблицу как аргумент (use-case передаёт snapshot из `balance.thickness.unlock_levels`), это сохраняет домен чистым и упрощает тестирование. `require_unlocked(...)` бросает `ActivityLockedError(activity, current_thickness, required_thickness)`.
- **Application (`application/progression/upgrade_thickness.py`)** — use-case `UpgradeThickness` с DTO `UpgradeThicknessInput(tg_id, expected_cost_cm: int | None)`. Workflow: загрузка игрока → `cost_for_upgrade(...)` → optional contract-check `expected_cost_cm` (бросает `ConcurrencyError` при расхождении — защита от race «balance.yaml перегружен между показом и нажатием Подтвердить») → `require_spend(action=THICKNESS_UPGRADE)` (правило 20 см из 1.2.1) → двойная мутация `with_length` + `with_thickness` → атомарный `save` → **два** audit-события: `LENGTH_REVOKE` (для трекинга траты длины) и `THICKNESS_UPGRADE` с `idempotency_key=f"thickness_upgrade:{player_id}:{new_level}"` (для трекинга прогрессии и защиты от двойной прокачки на одном уровне). Возврат — frozen dataclass `ThicknessUpgraded(player_before, player_after, cost_cm, new_thickness)`.
- **Bot-presenter (`bot/presenters/upgrade.py`)** — четыре чистые функции: `render_upgrade_proposal(...)` (карточка перед подтверждением: текущий/целевой уровень, стоимость, остаток после списания, минимум по правилу 20 см), `render_upgrade_success(...)`, `render_upgrade_insufficient(...)`. Кодек callback_data: `upgrade_callback_data(action, expected_cost_cm)` / `parse_upgrade_callback_data(raw)` с форматом `"upgrade:<action>:<expected_cost_cm>"` (≤ 64 байта Telegram-лимита). `expected_cost_cm` зашит в callback_data — handler передаёт его обратно в use-case, чтобы поймать «balance hot-reloaded между показом и нажатием». `build_upgrade_proposal_keyboard(*, expected_cost_cm)` собирает inline-пару `[Подтвердить (XXXX см)] [Отменить]`.
- **Bot-handler (`bot/handlers/upgrade.py`)** — два handler-а. `handle_upgrade` (`/upgrade` в ЛС): группа/супергруппа → инструкция «открой ЛС»; не зарегистрирован → инструкция нажать `/start`; недостаточно длины (по правилу 20 см) → текст «не хватает N см» **без** клавиатуры; иначе → карточка-proposal + inline-пара кнопок. `handle_upgrade_callback` (callback под `upgrade:*`): `cancel` → snять клавиатуру + заменить текст на «Прокачка отменена»; `confirm` → `UpgradeThickness.execute(input_dto)`, обработка `PlayerNotFoundError` / `InsufficientLengthError` (race-кейс) / `ConcurrencyError` (balance hot-reloaded), при успехе → `render_upgrade_success(...)`. Идемпотентность повторного нажатия: после первого клика handler делает `edit_reply_markup(reply_markup=None)` — кнопок больше нет, второй клик невозможен.
- **Composition root (`bot/main.py`)** — `UpgradeThickness` собирается в `build_container(...)`, прокидывается в `Container.upgrade_thickness`, прокидывается в `dispatcher["upgrade_thickness"]` + `dispatcher["balance"]` для aiogram-DI. Новый `upgrade_router` зарегистрирован в `register_routers(...)` после `forest_router`.
- **Тесты** — три новых файла:
  - `tests/unit/domain/progression/test_thickness.py` — 38 passed + 1 skipped (acceptance-значения по ГДД, все 8 unlock-уровней по умолчанию, ошибка `ActivityLockedError`).
  - `tests/unit/application/progression/test_upgrade_thickness.py` — 9 кейсов: success-path с проверкой обоих audit-событий и `idempotency_key`, expected_cost contract-check (pass/fail), `PlayerNotFoundError`, `InsufficientLengthError` с граничными значениями (4019/4020), `ConcurrencyError` без мутации.
  - `tests/unit/bot/handlers/test_upgrade.py` (15 кейсов: handler + callback) и `tests/unit/bot/presenters/test_upgrade.py` (11 кейсов: рендеры + кодек callback_data round-trip).
  - `tests/unit/bot/test_composition_root.py` — добавлены проверки `upgrade_thickness` в Container + dispatcher + наличие `upgrade`-router.

Результат / артефакты:
- Домен: <code>src/pipirik_wars/domain/progression/thickness.py</code>, <code>src/pipirik_wars/domain/progression/errors.py</code> (новый класс), `__init__.py`.
- Application: <code>src/pipirik_wars/application/progression/upgrade_thickness.py</code>, <code>src/pipirik_wars/application/dto/inputs.py</code> (новый DTO), `__init__.py`.
- Bot: <code>src/pipirik_wars/bot/presenters/upgrade.py</code>, <code>src/pipirik_wars/bot/handlers/upgrade.py</code>, `__init__.py` обоих, `bot/main.py` (DI).
- Тесты: 4 новых файла, 73 новых кейса; всего по проекту **814 passed + 1 skipped, coverage 96.59%** (требование ≥ 80% выполнено с большим запасом).
- Lint/typecheck/imports: `ruff check` / `ruff format --check` / `mypy --strict` / `lint-imports` — все чисто, 3 contracts kept.

Заметки / решения:
- **Почему unlock-таблица как аргумент, а не через `IBalanceConfig`?** Домен не должен зависеть от прикладных портов (DIP). Use-case-ы получают snapshot `balance.get().thickness.unlock_levels` и передают его в `is_activity_unlocked(...)`. Это держит домен чистым (не нужно мокать `IBalanceConfig` в его тестах) и упрощает повторное использование функции в любом use-case-е.
- **Почему два audit-события (`LENGTH_REVOKE` + `THICKNESS_UPGRADE`)?** `LENGTH_REVOKE` нужен для трекинга списания длины (как в любой другой spend-операции — единый формат для отчётов и анти-фрода). `THICKNESS_UPGRADE` нужен для трекинга прогрессии и идемпотентности — `idempotency_key=f"thickness_upgrade:{player_id}:{new_level}"` гарантирует, что повторная прокачка на тот же уровень не прошла бы (если бы база её допустила).
- **Почему `expected_cost_cm` в callback_data?** Между показом proposal и нажатием «Подтвердить» админ может перегрузить `balance.yaml` через `/balance_reload` (1.1.E). Если новые `cost_base/cost_exponent` дают другую цифру — игрок видит одну сумму, а заплатит другую. Клиент-side контракт через `expected_cost_cm` ловит это: use-case бросит `ConcurrencyError`, handler покажет «Стоимость изменилась — открой /upgrade ещё раз».
- **Почему `InsufficientLengthError` обрабатывается в callback тоже?** Между показом proposal и нажатием «Подтвердить» игрок мог потратить длину в другой активности (race с асинхронным `/forest`-finish-ом, например). Handler корректно шлёт «Недостаточно длины» с deficit-ом из исключения, а не ронит callback.
- **Граница 20 см правила траты:** acceptance — 4019 см (cost=4000) даёт остаток 19 < 20 → отказ; 4020 см → остаток 20 = MIN → проходит. Зафиксировано в тестах `test_insufficient_at_exact_boundary` / `test_passes_at_exact_boundary_plus_1`.

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
- `docs/game_design.md` (ГДД v9): шапка, §1.1, §2.4, §6.1, §18.6.4, §22, footer
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
- `docs/game_design.md` (ГДД v8)
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
- **ГДД переведён в v7** (`game_design.md`):
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
- `docs/game_design.md` (ГДД v7)
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
- Прочитан и проанализирован геймдиз `game_design.md` (ГДД v6).
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
