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

**На `main`:** последний смерженный PR — **3.2-B** (PR #109, `e27968b`) — use-case-ы `CreateCaravan` / `JoinCaravanLobby` / `LeaveCaravanLobby` / `CloseCaravanLobby` (`application/caravans/`), миграция `0019_caravans` + ORM + SQLAlchemy-репо (`infrastructure/db/models/caravan.py`, `infrastructure/db/repositories/{caravan,caravan_participant}.py`), APScheduler `schedule_caravan_lobby_close` / `cancel_caravan_lobby_close` (`infrastructure/scheduler/aps.py` + `tests/fakes/delayed_job_scheduler.py`), 4 новых `AuditAction.CARAVAN_*` (`domain/shared/ports/audit.py`), 4 новых input-DTO (`application/dto/inputs.py`), DI-wiring в `bot/main.py`. Полное unit + integration-покрытие (28 integration + ~ 67 unit-тестов, 95.93% coverage).

Перед ним: **3.2-A** (PR #108, `fe959c6`) — каркас доменов «Караван». Перед ним: **3.1-E** (PR #107, `5c1b26f`) — bot-handlers `/mountains` + `/dungeon` (закрытие Спринта 3.1). Перед ним: **catch-up docs 3.1-D** (PR #106, `76af44a`). Перед ним: **3.1-D** (PR #105, `2208ae6`). Перед ним: **3.1-C** (PR #103). Перед ним: **3.1-B** (PR #101). Перед ним: **3.1-A** (PR #99). Перед ним: PR-ы Спринта 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). Идёт **Спринт 3.2 «Караваны (полная механика)»** — каркас доменов закрыт в 3.2-A, use-cases + persistence + миграция + APScheduler-job на закрытие лобби — в 3.2-B (PR #109, мердж). Боевая механика + награды + Атаман-роль — в **этом 3.2-C PR-е**, bot-handlers + локали + UI — в **3.2-D**.

**Активная feature-ветка:** `devin/1778223350-sprint-3-2-C-caravan-battle-resolution` — стартовала от `main = e27968b` (мердж 3.2-B).

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
- **3.2-B — Use-cases + persistence + миграция (этот PR; мердж).** `application/caravans/`: `CreateCaravan` (lvl 7+ gate, ≥ 20 см после контрибьюта, выбор target-клана, проверка кулдауна 12 ч, activity-lock), `JoinCaravanLobby` (двойное членство по таблице ГДД §9.4 — 5 кейсов; capacity-чекер по ролям через `list_by_caravan_and_role`; activity-lock), `LeaveCaravanLobby` (возврат `contribution_cm` в длину, освобождение activity-lock-а), `CloseCaravanLobby` (LOBBY → IN_BATTLE, идемпотентен). Миграция `0019_caravans` (таблицы `caravans` + `caravan_participants` с `UNIQUE (caravan_id, player_id)` + partial-unique «один активный караван на sender_clan_id» + partial-unique «один лидер на караван»). SQLAlchemy-репо. APScheduler-job `caravan_lobby_close_factory` через тот же паттерн, что mountain/dungeon (фабрика остаётся `None` до 3.2-D).
- **3.2-C — Боевая механика + завершение (следующий PR).** `application/caravans/StartCaravanBattle` + `FinishCaravanBattle` use-cases. Доменный сервис `caravan_battle_resolution`: каждый рейдер — 1 удар, караванщики — 2 блока, защитники — 1 блок (ГДД §9.5). Resolve по `random_seed` (детерминистично). Награды через ленгт-дельту + clan +1 см. **Атаман-роль** (расширение `Title` enum) — выдаётся за лидерство в успешном караване. Идемпотентность `(caravan_id, action)` через `IIdempotencyService`. APScheduler — `caravan_battle_finish_factory` (фабрика `None` до 3.2-D, как mountain/dungeon).
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

**Финальный коммит этого 3.2-C PR-а** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.2-C: боевая механика + награды + Атаман»), пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит-слияния-3.2-C>`, расписать чек-лист 3.2-D.

---

## 📝 Чек-лист следующего PR (Спринт 3.2-C)

> Этот PR закрывает боевую механику каравана: resolve битвы по `random_seed`, начисление наград (lengths + clan +1 см), Атаман-роль, идемпотентность через `IIdempotencyService`. Bot-handlers и UI — в 3.2-D.

- [x] Дождаться мерджа `main = e27968b` (3.2-B, PR #109).
- [x] `git fetch && git checkout main && git pull`.
- [x] `make ci` локально на свежем `main`: ✅ зелёный (3889 passed / 1 skipped, coverage 95.93%).
- [x] Создать ветку `devin/1778223350-sprint-3-2-C-caravan-battle-resolution` от `main`.
- [x] **C.0 — Обновить `current_tasks.md`** под старт Спринта 3.2-C (этот коммит).
- [ ] **C.1 — Расширить `domain/shared/ports/audit.py`:** добавить `AuditAction.CARAVAN_BATTLE_FINISHED`, `CARAVAN_REWARDS_GRANTED`, `CARAVAN_CANCELLED` (если cancel-flow появится в этом же PR).
- [ ] **C.2 — Расширить `domain/shared/ports/scheduler.py`:** `schedule_caravan_battle_finish(caravan_id, run_at)` + `cancel_caravan_battle_finish(caravan_id)`.
- [ ] **C.3 — Расширить `Title` enum** (`domain/player/value_objects.py`): добавить значение `ATAMAN` («Атаман»). Обновить миграцию или CHECK-constraint на `users.title` если есть.
- [ ] **C.4 — Доменный сервис `caravan_battle_resolution`** (`domain/caravan/services.py` или `domain/caravan/battle.py`): чистая функция `resolve(caravan, participants, random_seed) -> CaravanBattleResult` (победа/проигрыш + per-player damage + per-player reward delta + clan_bonus). Логика по ГДД §9.5: каждый рейдер — 1 удар, караванщики — 2 блока, защитники — 1 блок. Детерминистично от `random_seed`. Результат содержит side-effects-плеценхолдеры — НЕ применяет их.
- [ ] **C.5 — Use-case `FinishCaravanBattle`** (`application/caravans/finish_caravan_battle.py`): принимает `caravan_id`; идемпотентен (через `IIdempotencyService`-ключ `caravan_battle_finished:{caravan_id}` или повторный вызов на `FINISHED` — no-op с `was_already_finished=True`); вызывается из APScheduler-job-а через `caravan_battle_finish_factory`. Загружает `caravan` (status=`IN_BATTLE`), участников; вызывает `caravan_battle_resolution`; применяет результат — обновляет `Length` каждого участника, `Clan` +1 см если победа, выдаёт `Title.ATAMAN` лидеру если победа; снимает activity-lock-и всех участников; `Caravan.mark_finished(finished_at)`; audit `CARAVAN_BATTLE_FINISHED` + `CARAVAN_REWARDS_GRANTED`.
- [ ] **C.6 — Use-case `CancelCaravan`** (опционально, если решим включать в 3.2-C): только лидер может отменить из `LOBBY`; возврат всех контрибьюций, снятие всех activity-lock-ов, `cancel_caravan_lobby_close` job-а, `Caravan.mark_cancelled`; audit `CARAVAN_CANCELLED`.
- [ ] **C.7 — APScheduler:** `infrastructure/scheduler/aps.py` — расширить `IDelayedJobScheduler` адаптер: `schedule_caravan_battle_finish` / `cancel_caravan_battle_finish` + callback `_run_caravan_battle_finish_job` (через `caravan_battle_finish_factory`); расширить `CloseCaravanLobby` use-case в `application/caravans/close_caravan_lobby.py` так, чтобы при переходе LOBBY → IN_BATTLE он шедулил `caravan_battle_finish` job на `caravan.battle_ends_at` (сейчас не шедулит — это TODO для 3.2-C).
- [ ] **C.8 — DI:** в `bot/main.py` подключить `FinishCaravanBattle` (+ `CancelCaravan` если включаем) через `Container`. APScheduler — `caravan_battle_finish_factory=None` до 3.2-D.
- [ ] **C.9 — Юнит-тесты:** `tests/unit/domain/caravan/test_battle_resolution.py` (детерминистичность по seed-у; 100-симуляций распределение в норме — критерий 3.2.5; capacity-edge-cases — 0 рейдеров, 0 защитников, минимум 1 караванщик); `tests/unit/application/caravans/test_finish_caravan_battle.py` (happy-path победа/проигрыш + Атаман выдан/не выдан + clan_bonus применён/не применён; идемпотентность повторного вызова; activity-lock-и сняты; audit-записи; error-cases — caravan не найден / не в IN_BATTLE).
- [ ] **C.10 — Integration-тест:** `tests/integration/db/test_caravan_battle_finish.py` (e2e через UoW: создать караван в IN_BATTLE-статусе с участниками → вызвать `FinishCaravanBattle` → проверить итоговые `Length` + `Clan.length` + `Title.ATAMAN` через настоящие SQL-репо).
- [ ] `make ci` локально: ruff / mypy --strict / import-linter / pytest / coverage gate.
- [ ] **C.11 — Финальный док-коммит:** `history.md` +запись 3.2-C, `current_tasks.md` пересборка под старт Спринта 3.2-D.
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Закрытый PR — 3.2-B (use-cases + persistence + миграция):**
- ~ 20 файлов изменено (excl. docs).
- **Domain-слой:** `domain/shared/ports/audit.py` — 4 новых `AuditAction.CARAVAN_*`; `domain/shared/ports/scheduler.py` — `schedule_caravan_lobby_close` / `cancel_caravan_lobby_close`.
- **Application-слой:** `application/dto/inputs.py` +4 input-DTO; новый пакет `application/caravans/` с 4 use-case-ами (`CreateCaravan`, `JoinCaravanLobby` с резолвом 5 кейсов §9.4, `LeaveCaravanLobby` с возвратом контрибьюции, `CloseCaravanLobby` идемпотентный LOBBY → IN_BATTLE).
- **Infrastructure-слой:** миграция `0019_caravans` + ORM `CaravanORM`/`CaravanParticipantORM` + репо `SqlAlchemyCaravanRepository` / `SqlAlchemyCaravanParticipantRepository` (с конверсией БД-`IntegrityError` в доменный); APScheduler-адаптер `_run_caravan_lobby_close_job` через `caravan_lobby_close_factory`. БД-инварианты: `uq_caravans_one_active_per_sender` (partial-unique) + composite-PK `(caravan_id, player_id)` + `uq_caravan_participants_one_leader_per_caravan` (partial-unique) + ON DELETE CASCADE.
- **DI:** `bot/main.py` подключил репо + 4 use-case в `Container`.
- **Тесты:** `tests/fakes/caravan_repo.py` (in-memory `FakeCaravanRepository` + `FakeCaravanParticipantRepository`), 4 unit-модуля в `tests/unit/application/caravans/` (~ 67 тестов: happy-path/audit/idempotency/errors), integration-тест `tests/integration/db/test_caravan_repository.py` (~ 28 тестов: CRUD + UNIQUE-инварианты + CHECK + ON DELETE CASCADE).
- **Бизнес-логика боя отсутствует.** Resolve каравана и `FinishCaravanBattle` — Спринт 3.2-C; bot-handlers и UI — 3.2-D.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Атаман-титул** — расширение `Title` enum приходит в 3.2-C (когда появится `FinishCaravanBattle` use-case). В 3.2-B `domain/player/` не трогаем.
- **`CloseCaravanLobby` не шедулит `caravan_battle_finish` job.** В 3.2-B use-case делает только переход LOBBY → IN_BATTLE — TODO для 3.2-C: после mark_in_battle вызывать `IDelayedJobScheduler.schedule_caravan_battle_finish(caravan_id, caravan.battle_ends_at)`. Сейчас APScheduler-job на финиш битвы вообще не создаётся, поэтому в 3.2-C нужен миграционный backfill для уже стартовавших боёв (хотя на момент 3.2-B ни одного такого нет в проде).
- **`get_active_by_clan` ищет только по `sender_clan_id`.** Это сознательный выбор: `caravans` таблица имеет partial-unique только на `sender_clan_id`, поэтому «активный караван клана» = «который клан отправил». Для клана-получателя «активный караван» — это тот, в котором его игроки могут защищаться, и таких может быть несколько одновременно (если 3+ кланов отправили караваны в один). В 3.2-D handler `/caravan` для DEFENDER-роли будет искать караваны по `receiver_clan_id` отдельным методом — добавим в репо при необходимости.
