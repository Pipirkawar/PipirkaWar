# 🍆 Пипирик Варс — Текущие задачи

> Этот файл описывает **только то, что в работе сейчас**: активная feature-ветка, активный спринт/PR, чек-лист текущих шагов и их статусы. По мере выполнения шаги отмечаются `[x]`.
>
> **С 2026-05-08:** обновления `history.md` и `current_tasks.md` под следующий PR делаются **внутри самого фичевого PR** (последним коммитом перед мерджем). Отдельный postmerge-PR больше не открывается — см. [`../CONTRIBUTING.md`](../CONTRIBUTING.md) «Перед мерджем PR-а».
>
> **Длинный план** (фазы / спринты A→Z) — в [`development_plan.md`](development_plan.md).
> **Игровая спецификация** (механики, формулы, баланс) — в [`game_design.md`](game_design.md).
> **Журнал завершённых работ** — в [`history.md`](history.md).
> **Правила работы с документацией + протокол передачи задач между агентами** — в [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
>
> ⚠️ **Перед каждым коммитом** обнови чек-лист ниже (отметь готовые шаги, обнови «текущая позиция»). Это нужно для непрерывности при смене агентов — следующий агент должен знать, где ты остановился.

---

## 📸 Снимок состояния проекта

> Эта секция отражает состояние проекта **на момент последнего обновления этого файла**. Она нужна для того, чтобы новый агент за 30 секунд понял, что происходит. Обновляй её при старте/завершении каждого PR-а.

**На `main`:** последний смерженный PR — **3.2-A** (PR #108, `fe959c6`) — каркас доменов «Караван» (entities `Caravan`/`CaravanParticipant`, enums `CaravanRole`/`CaravanStatus`, VO `CaravanContribution`, 8 доменных ошибок, порты `ICaravanRepository`/`ICaravanParticipantRepository`), `CaravansConfig` + `CaravanRewardMultipliers` в pydantic-схеме баланса + секция `caravans:` в `config/balance.yaml`.

Перед ним: **3.1-E** (PR #107, `5c1b26f`) — bot-handlers `/mountains` + `/dungeon` + презентеры + локали + Telegram-нотификаторы + APScheduler factory-wiring (закрытие Спринта 3.1). Перед ним: **catch-up docs 3.1-D** (PR #106, `76af44a`). Перед ним: **3.1-D** (PR #105, `2208ae6`). Перед ним: **3.1-C** (PR #103). Перед ним: **3.1-B** (PR #101). Перед ним: **3.1-A** (PR #99). Перед ним: PR-ы Спринта 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). Идёт **Спринт 3.2 «Караваны (полная механика)»** — каркас доменов закрыт в 3.2-A; этот PR (3.2-B) приземляет use-case-ы `CreateCaravan` / `JoinCaravanLobby` / `LeaveCaravanLobby` + `CloseCaravanLobby`, миграцию `0019_caravans` + persistence + APScheduler `caravan_lobby_close_factory`. Боевая механика + награды — в **3.2-C**, bot-handlers + локали — в **3.2-D**.

**Активная feature-ветка:** `devin/1778217612-sprint-3-2-B-caravan-usecases-persistence` — стартовала от `main = fe959c6` (мердж 3.2-A).

---

## 🎯 Активный спринт — Спринт 3.2 «Караваны (полная механика)»

> Цель спринта (по [`development_plan.md`](development_plan.md) §6.3.2 «Спринт 3.2 — Караваны (полная механика)»): полная механика караванов — создание, лобби с тремя ролями, боевая система, награды + Атаман-роль за лидерство.

**Скоуп — 7 задач из плана:**

- **3.2.1** — Создание каравана (lvl 7+), задание вклада + клан-получателя. **Критерий:** Юнит-тесты на правило «после взноса ≥ 20 см».
- **3.2.2** — Лобби 20 мин, кулдаун клана 12 ч. **Критерий:** E2E с ≥1 караванщиками + ≤ 4× рейдеров + ≤ 2× защитников.
- **3.2.3** — Роли при двойном членстве (см. ГДД §9.4). **Критерий:** Юнит-таблица всех 5 случаев.
- **3.2.4** — Запрет рейдерства членам обоих кланов. **Критерий:** Юнит-тест.
- **3.2.5** — Боевая механика. **Критерий:** Симуляция 100 караванов; распределение в норме.
- **3.2.6** — Завершение: победа/проигрыш, награды (×4 / ×3 / ×1 / +1 см клану), Атаман. **Критерий:** Все множители из `balance.yaml`.
- **3.2.7** — Идемпотентность начислений, аудит-лог. **Критерий:** Повторный обработчик не выдаёт награды дважды.

**Декомпозиция Спринта 3.2 на фичевые PR-ы:**

- **3.2-A — Каркас доменов (PR #108, мердж).** Domain entities `Caravan`/`CaravanParticipant`, enums `CaravanRole`/`CaravanStatus`, VO `CaravanContribution`, 8 доменных ошибок, порты `ICaravanRepository`/`ICaravanParticipantRepository`. `CaravansConfig` + `CaravanRewardMultipliers` в pydantic-схеме баланса. Секция `caravans:` в `config/balance.yaml` (lobby_minutes=20, battle_minutes=60, clan_cooldown_hours=12, min_thickness_level_leader=7, min_thickness_level_raider=5, min_length_cm=20, min_length_after_contribution_cm=20, max_raiders_per_caravaneer=4, max_defenders_per_caravaneer=2, base_reward_cm=5 × multipliers leader=4/caravaneer=3/defender=1/raider=0, clan_bonus_cm=1).
- **3.2-B — Use-cases + persistence + миграция (этот PR).** `application/caravans/`: `CreateCaravan` (lvl 7+ gate, ≥ 20 см после контрибьюта, выбор target-клана, проверка кулдауна 12 ч, activity-lock), `JoinCaravanLobby` (двойное членство по таблице ГДД §9.4 — 5 кейсов; capacity-чекер по ролям через `list_by_caravan_and_role`; activity-lock), `LeaveCaravanLobby` (возврат `contribution_cm` в длину, освобождение activity-lock-а), `CloseCaravanLobby` (LOBBY → IN_BATTLE, идемпотентен; вызывается шедулером — резолв и `caravan_battle_finish` job-а в 3.2-C). Миграция `0019_caravans` (таблицы `caravans` + `caravan_participants` с `UNIQUE (caravan_id, player_id)` + partial unique index «один активный караван на sender_clan_id»). SQLAlchemy-репо `ICaravanRepository` / `ICaravanParticipantRepository`. APScheduler-job `caravan_lobby_close_factory` через тот же паттерн, что mountain/dungeon.
- **3.2-C — Боевая механика + завершение.** `application/caravans/StartCaravanBattle` + `FinishCaravanBattle` use-cases. Доменный сервис `caravan_battle_resolution`: каждый рейдер — 1 удар, караванщики — 2 блока, защитники — 1 блок (ГДД §9.5). Resolve по `random_seed` (детерминистично). Награды через ленгт-дельту + clan +1 см. **Атаман-роль** (расширение `Title` enum) — выдаётся за лидерство в успешном караване. Идемпотентность `(caravan_id, action)` через `IIdempotencyService`.
- **3.2-D — Bot-handlers `/caravan` + лобби UI + презентеры + локали + APScheduler factory-wiring.** По образцу 3.1-E: handler `/caravan` в личке (lvl 7+, ≥ 20 см); inline-кнопки «вступить как X» × 3 ролей; передача роли при двойном членстве; `CaravanPresenter`; локали `caravans-*` (RU+EN parity); `caravan_lobby_close_factory` + `caravan_battle_finish_factory` в APScheduler; DI-wiring; Manual smoke-тест.

**Решения, принятые на старте 3.2 (по умолчанию, можно крутить через YAML без релиза):**
1. **Двойное членство (ГДД §9.4) — 5 кейсов** распишутся в таблице юнит-тестов в Спринте 3.2-B (когда появится `JoinCaravanLobby`):
   - Только в клане-отправителе → `CARAVANEER` ✅, `DEFENDER`/`RAIDER` ❌.
   - Только в клане-получателе → `DEFENDER` ✅, `CARAVANEER`/`RAIDER` ❌.
   - В обоих кланах → `CARAVANEER` ИЛИ `DEFENDER` (одна роль за раз через activity-lock), `RAIDER` ❌.
   - Ни в одном из кланов → `RAIDER` ✅, остальные ❌.
   - В одном из двух (кейс 1+2 объединённо) → `RAIDER` ❌.
2. **`/caravan` стартует в личке** (как `/forest`/`/mountains`/`/dungeon`).
3. **Два APScheduler-job-а на караван:** `caravan_lobby_close_factory` (через 20 мин закрывает лобби и стартует бой) + `caravan_battle_finish_factory` (через 60 мин финиширует бой). **Resolve боя — синхронный** в callback-е `caravan_battle_finish` (детерминистично по `random_seed`). Без раунд-tick-ов.
4. **Атаман — расширение `Title` enum** в `domain/player/`. Не отдельный VO, не поле в кланах.
5. **Capacity-предели:** `max_raiders ≤ 4 × caravaneers`, `max_defenders ≤ 2 × caravaneers` (ГДД §9.5). При `caravaneers=0` (только лидер) — `raiders ≤ 4`, `defenders ≤ 2`.

**Финальный коммит этого 3.2-B PR-а** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.2-B: use-cases + persistence + миграция»), пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит-слияния-3.2-B>`, расписать чек-лист 3.2-C.

---

## 📝 Чек-лист текущего PR (Спринт 3.2-B)

> Этот PR закрывает «движущуюся часть» каравана: создание, вход/выход из лобби, persistence + APScheduler-job на закрытие лобби. Боевая механика и награды — в 3.2-C. Bot-handlers и UI — в 3.2-D.

- [x] Мердж `main = fe959c6` (3.2-A, PR #108).
- [x] `git fetch && git checkout main && git pull`.
- [x] `make ci` локально на свежем `main`: ✅ зелёный (pytest 3794 passed / 1 skipped, coverage 95.95%, gate 80%).
- [x] Создать ветку `devin/1778217612-sprint-3-2-B-caravan-usecases-persistence` от `main`.
- [x] **B.0 — Обновить `current_tasks.md`** под старт Спринта 3.2-B (этот коммит).
- [ ] **B.1 — Расширить `domain/shared/ports/audit.py`:** добавить `AuditAction.CARAVAN_CREATED`, `CARAVAN_PLAYER_JOINED`, `CARAVAN_PLAYER_LEFT`, `CARAVAN_LOBBY_CLOSED`.
- [ ] **B.2 — Расширить `domain/shared/ports/scheduler.py`:** `schedule_caravan_lobby_close(caravan_id, run_at)` + `cancel_caravan_lobby_close(caravan_id)`.
- [ ] **B.3 — DTO `application/dto/inputs.py`:** `CreateCaravanInput` (sender/receiver `chat_id`, `tg_id` лидера, `contribution_cm`), `JoinCaravanLobbyInput` (`tg_id`, `caravan_id`, `role`, опц. `contribution_cm`), `LeaveCaravanLobbyInput` (`tg_id`, `caravan_id`), `CloseCaravanLobbyInput` (`caravan_id`).
- [ ] **B.4 — Use-case `CreateCaravan`** (`application/caravans/create_caravan.py`): проверка lvl ≥ 7, lender-clan через `chat_id` отправителя, target-clan через `chat_id` получателя; ≥ 20 см после взноса; кулдаун 12 ч от `started_at` последнего активного/завершённого каравана клана-отправителя; activity-lock на `(player, CARAVAN)` ttl=80 мин (lobby+battle); в той же транзакции — `Caravan.starting(...)`, `CaravanParticipant.caravaneer(is_leader=True)`, `IDelayedJobScheduler.schedule_caravan_lobby_close(caravan_id, lobby_ends_at)`, `IAuditLogger.record(CARAVAN_CREATED)`. Возвращает `CaravanCreated(caravan, leader_participant)`.
- [ ] **B.5 — Use-case `JoinCaravanLobby`** (`application/caravans/join_caravan_lobby.py`): проверка `Caravan.status=LOBBY` (иначе `CaravanLobbyClosedError`); резолв роли по таблице ГДД §9.4 (5 кейсов) через `IClanMembershipRepository.get_by_player(player.id)` + сравнение с `caravan.sender_clan_id` / `caravan.receiver_clan_id`; для `RAIDER` — lvl ≥ 5 и НЕ член обоих кланов; для `CARAVANEER` — член sender-clan-а, ≥ 20 см total и ≥ 20 см после взноса; для `DEFENDER` — член receiver-clan-а, ≥ 20 см total; capacity по ролям (`raiders ≤ 4 × caravaneers`, `defenders ≤ 2 × caravaneers`); activity-lock; в той же транзакции — `CaravanParticipant.{caravaneer/defender/raider}(...)`, audit `CARAVAN_PLAYER_JOINED`. Возвращает `CaravanJoined(caravan, participant)`.
- [ ] **B.6 — Use-case `LeaveCaravanLobby`** (`application/caravans/leave_caravan_lobby.py`): только `status=LOBBY` (после закрытия лобби — `CaravanLobbyClosedError`); `is_leader=True` запрещено (лидер закрывает караван через `CancelCaravan`, который придёт в 3.2-C); удалить участника, вернуть `contribution_cm` в `Length` для `CARAVANEER`; снять activity-lock; audit `CARAVAN_PLAYER_LEFT`.
- [ ] **B.7 — Use-case `CloseCaravanLobby`** (`application/caravans/close_caravan_lobby.py`): идемпотентен (повторный вызов на `IN_BATTLE`/`FINISHED`/`CANCELLED` — no-op с `was_already_closed=True`); из `LOBBY` — `Caravan.mark_in_battle()`, audit `CARAVAN_LOBBY_CLOSED`. Резолв и `caravan_battle_finish_factory`-job — в 3.2-C.
- [ ] **B.8 — Persistence:** `infrastructure/db/models/caravan.py` (`CaravanORM` + `CaravanParticipantORM` с CHECK-инвариантами и индексами; зеркал миграции 0019), миграция `infrastructure/db/migrations/versions/20260508_0019_caravans.py` (создание двух таблиц + partial unique index «один активный караван на sender_clan_id WHERE status IN ('lobby', 'in_battle')»), репо `infrastructure/db/repositories/caravan.py` + `caravan_participant.py`.
- [ ] **B.9 — APScheduler:** `infrastructure/scheduler/aps.py` — расширить `IDelayedJobScheduler` адаптер: `schedule_caravan_lobby_close` / `cancel_caravan_lobby_close` + callback `_run_caravan_lobby_close_job` (через `caravan_lobby_close_factory`); расширить `tests/fakes/delayed_job_scheduler.py` соответственно.
- [ ] **B.10 — DI:** в `bot/bootstrap` (или там, где провязывается `Container`) подключить новые репо и use-case-ы; APScheduler — `caravan_lobby_close_factory` (фабрика остаётся `None` до 3.2-D, как у mountain/dungeon).
- [ ] **B.11 — Юнит-тесты:** `tests/unit/application/caravans/test_create_caravan.py`, `test_join_caravan_lobby.py` (5 кейсов §9.4 + capacity), `test_leave_caravan_lobby.py`, `test_close_caravan_lobby.py`. + integration-тест `tests/integration/db/test_caravan_repository.py` (миграция up/down + CRUD + UNIQUE-инварианты).
- [ ] `make ci` локально: ruff / mypy --strict / import-linter / pytest / coverage gate.
- [ ] **B.12 — Финальный док-коммит:** `history.md` +запись 3.2-B, `current_tasks.md` пересборка под старт Спринта 3.2-C.
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Текущий PR — 3.2-B (use-cases + persistence + миграция):**
- В работе. На момент создания ветки изменён только этот файл (`docs/current_tasks.md`).
- **Дальше идёт:** расширение портов (audit + scheduler), DTO, четыре use-case-а (`CreateCaravan`/`JoinCaravanLobby`/`LeaveCaravanLobby`/`CloseCaravanLobby`), ORM-модели + миграция + репо, APScheduler-адаптер, DI-провязка, юнит- и integration-тесты.
- **Бизнес-логика боя отсутствует.** Resolve каравана — Спринт 3.2-C; bot-handlers и UI — 3.2-D.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Кулдаун клана 12 ч — от `started_at` или от `finished_at`?** Решение, принятое в 3.2-A: кулдаун начинается от `started_at` создания каравана (и сохраняется при `CANCELLED`), не от `finished_at`. **Решено в 3.2-B:** `ICaravanRepository.get_last_started_at_for_clan(clan_id)` (новый метод; `get_last_finished_at_for_clan` сохраняем — пригодится в 3.2-C для аналитики).
- **`AlreadyInCaravanError` vs `CaravanRoleConflictError` — кто бросает что.** **Решено в 3.2-B:** `AlreadyInCaravanError` — конфликт с `activity_lock` (актор уже в любой активности `CARAVAN`); `CaravanRoleConflictError` — конкретно нарушение правила §9.4 (роль не подходит по членству в кланах).
- **Атаман-титул** — расширение `Title` enum приходит в 3.2-C (когда появится `FinishCaravanBattle` use-case). В 3.2-B `domain/player/` не трогаем.
