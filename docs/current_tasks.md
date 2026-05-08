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

**На `main`:** последний смерженный PR — **3.2-C** (PR #110, `2333297`) — боевая механика каравана: доменный сервис `caravan_battle_resolution` (`domain/caravan/services.py`, чистая функция, детерминистично от `random_seed` через `IRandom`), use-case `FinishCaravanBattle` (`application/caravans/finish_caravan_battle.py`), `Title.ATAMAN` (`domain/player/value_objects.py`), 3 новых `AuditAction.CARAVAN_*` (`CARAVAN_BATTLE_FINISHED`/`REWARDS_GRANTED`/`CANCELLED`), `IDelayedJobScheduler.{schedule,cancel}_caravan_battle_finish` (`domain/shared/ports/scheduler.py`) + `APSchedulerDelayedJobScheduler`-callback `_run_caravan_battle_finish_job`, `SeededRandom` (`infrastructure/random/seeded_random.py`), `CloseCaravanLobby` теперь шедулит финиш-job при LOBBY → IN_BATTLE (был TODO в 3.2-B), `InvalidCaravanStateError`. Полное unit + integration-покрытие (1 integration + ~ 30 unit-тестов, 3927 passed / 1 skipped, 95.68% coverage).

Перед ним: **3.2-B** (PR #109, `e27968b`) — use-case-ы `CreateCaravan` / `JoinCaravanLobby` / `LeaveCaravanLobby` / `CloseCaravanLobby`, миграция `0019_caravans`, APScheduler-job на закрытие лобби. Перед ним: **3.2-A** (PR #108, `fe959c6`) — каркас доменов «Караван». Перед ним: **3.1-E** (PR #107, `5c1b26f`) — bot-handlers `/mountains` + `/dungeon` (закрытие Спринта 3.1). Перед ним: **catch-up docs 3.1-D** (PR #106, `76af44a`). Перед ним: **3.1-D** (PR #105, `2208ae6`). Перед ним: **3.1-C** (PR #103). Перед ним: **3.1-B** (PR #101). Перед ним: **3.1-A** (PR #99). Перед ним: PR-ы Спринта 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). Идёт **Спринт 3.2 «Караваны (полная механика)»** — каркас доменов закрыт в 3.2-A, use-cases + persistence + миграция + APScheduler-job на закрытие лобби — в 3.2-B (PR #109, мердж), боевая механика + награды + Атаман-роль — в 3.2-C (этот PR; мердж). Bot-handlers + локали + UI — в следующем **3.2-D**.

**Активная feature-ветка:** `devin/1778231804-sprint-3-2-D-caravan-bot-handlers` — стартовала от `main = 2333297` (мердж 3.2-C). Идёт **Спринт 3.2-D** (bot-handler-ы `/caravan` в личке, lobby-UI с inline-кнопками 3 ролей, `CaravanPresenter`, локали `caravans-*` RU+EN, `CancelCaravan` use-case + `/caravan_cancel`, manual smoke-тест).

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

**Финальный коммит этого 3.2-D PR-а** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.2-D: bot-handlers + локали + UI»), пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния_3.2-D>`, закрыть Спринт 3.2 и расписать чек-лист **первого PR-а Спринта 3.3** (по [`development_plan.md`](development_plan.md) §6.3.3).

---

## 📝 Чек-лист следующего PR (Спринт 3.2-D)

> Этот PR закрывает Спринт 3.2 — добавляет bot-handler `/caravan` в личке, lobby-UI с inline-кнопками 3 ролей, `CaravanPresenter`, локали `caravans-*` (RU+EN parity), `CancelCaravan` use-case + `/caravan_cancel`, manual smoke-тест. Боевая механика и persistence уже есть из 3.2-A/B/C — здесь только UI-слой.

- [x] Дождаться мерджа `main = 2333297` (3.2-C, PR #110).
- [x] `git fetch && git checkout main && git pull`.
- [x] `make ci` локально на свежем `main`: ✅ зелёный (3927 passed / 1 skipped, coverage 95.68%).
- [x] Создать ветку `devin/1778231804-sprint-3-2-D-caravan-bot-handlers` от `main`.
- [x] **D.0 — Обновить `current_tasks.md`** под старт Спринта 3.2-D (этот коммит).
- [x] **D.1 — Use-case `CancelCaravan`** (`application/caravans/cancel_caravan.py`): только лидер может отменить из `LOBBY`; возврат всех контрибьюций (лидер + caravaneers), снятие всех activity-lock-ов, `cancel_caravan_lobby_close` + `cancel_caravan_battle_finish` job-ов, `Caravan.mark_cancelled(cancelled_at)`; audit `CARAVAN_CANCELLED` с idempotency-key. Использует уже существующий `AuditAction.CARAVAN_CANCELLED` (зарезервирован в 3.2-C).
- [x] **D.2 — Bot-handler `/caravan`** (`bot/handlers/caravan.py`): личка-only (как `/forest`/`/mountains`/`/dungeon`), gate lvl ≥ 7 + ≥ 20 см total — реализован через `CreateCaravan` use-case (он сам проверяет lvl ≥ 7 + ≥ 20 см после контрибьюта). Аргументы — `<receiver_chat_id> <contribution_cm>` (инлайн-кнопки выбора клана отложены на D.3 — там же будет lobby-UI). По успеху — приватное подтверждение лидеру + пост в чат-отправитель (`sender_clan.chat_id`) с кнопкой «Показать лобби». Презентер `CaravanPresenter` (минимальный — только под `/caravan`-команду), локали `caravans-*` (минимальные — расширятся в D.4/D.5). DI: `CreateCaravan` + `IClanMembershipRepository` + `IClanRepository` (для резолва `sender_chat_id`). Юнит-тесты — gate `chat_kind`, парсинг аргументов, pre-check (registered/leader), маппинг доменных ошибок use-case-а в локали, happy-path. **Cовместно с D.1 закрывает scope D.2.**
- [x] **D.3 — Lobby-UI** (inline-кнопки): закрыто 6 коммитами `D.3a/b/c/d/e/f` — cancel-button + DI, show_lobby callback + lobby_state presenter, join_defender/join_raider callbacks, leave callback, `/caravan_join` команда. Live-обновление через `edit_message_text` работает.
- [x] **D.4 — `CaravanPresenter`** (`bot/presenters/caravans.py`): рендер lobby-state ✅ (был в D.3) + battle-state (`battle_started_text`) + finished-state (`battle_finished_delivered_text` + `battle_finished_raided_text`) ✅. Локализация через Fluent.
- [x] **D.5 — Локали** (`locales/{ru,en}.ftl`): `caravans-*` сообщения с RU+EN parity — добавлены `caravans-battle-started`, `caravans-battle-finished-delivered`, `caravans-battle-finished-raided` (ключи + `*-leader-line`/`*-clans-line`/`*-time-line`/`*-no-deliveries-line`/`*-rewards-grant-line`/etc). Полностью parity покрыты.
- [x] **D.6 — APScheduler factory-wiring + Telegram-нотификаторы:** введены порты `ICaravanLobbyCloseNotifier` + `ICaravanBattleFinishNotifier` (`application/caravans/notifier.py`); реализованы `TelegramCaravanLobbyCloseNotifier` + `TelegramCaravanBattleFinishNotifier` (`bot/notifications/caravans.py`) — резолвят клан/лидера/Атамана через репо, локаль через `IPlayerLocaleResolver`, рендерят текст через `CaravanPresenter`, шлют в чаты обоих кланов; APScheduler-callback-и `_run_caravan_lobby_close_job` + `_run_caravan_battle_finish_job` вызывают `notifier.notify(result)` после успешного `execute(...)` use-case-а (best-effort, идемпотентны через `was_already_*`-флаги). `bot/main.py::build_container` инстанциирует оба нотификатора при `bot is not None` и пробрасывает их в `APSchedulerDelayedJobScheduler`.
- [x] **D.7 — DI `CancelCaravan`:** уже подключён в `Container` в коммите D.3a/b (`cdc3a7d`).
- [ ] **D.8 — Юнит-тесты:** `tests/unit/application/caravans/test_cancel_caravan.py` (happy-path лидер отменяет; идемпотентность повторного вызова на `CANCELLED`; error-cases — не лидер, не в `LOBBY`, караван не найден); `tests/unit/bot/test_caravan_handler.py` (gate lvl ≥ 7, gate ≥ 20 см, личка-only, успешный флоу через FakeBot).
- [ ] **D.9 — Integration / smoke-тест:** manual smoke с временным локальным TG-инстансом — пройти полный цикл «создать → 2 кана-участника + 1 защитник + 1 рейдер → закрыть лобби → ждать battle finish (или мокнуть time.now) → проверить нагрузки».
- [ ] `make ci` локально: ruff / mypy --strict / import-linter / pytest / coverage gate (≥ 80%).
- [ ] **D.10 — Финальный док-коммит:** `history.md` +запись 3.2-D (закрытие Спринта 3.2), `current_tasks.md` пересборка под старт **первого PR-а Спринта 3.3** (по [`development_plan.md`](development_plan.md) §6.3.3 «Спринт 3.3 — Дуэли II + рейтинг»).
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Закрытый PR — 3.2-C (боевая механика + награды + Атаман):**
- 28 файлов изменено (excl. docs).
- **Domain-слой:** `domain/shared/ports/audit.py` — 3 новых `AuditAction.CARAVAN_*` (`BATTLE_FINISHED`/`REWARDS_GRANTED`/`CANCELLED`); `domain/shared/ports/scheduler.py` — `schedule_caravan_battle_finish` / `cancel_caravan_battle_finish`; `domain/player/value_objects.py` — `Title.ATAMAN`; `domain/caravan/services.py` — `resolve_caravan_battle()` чистая функция; `domain/caravan/errors.py` — `InvalidCaravanStateError`.
- **Application-слой:** `application/dto/inputs.py` +1 input-DTO (`FinishCaravanBattleInput`); `application/caravans/finish_caravan_battle.py` — use-case (loads caravan/participants → resolve → applies length deltas via `ILengthGranter` for positive + `Player.with_length()` for negative; clan bonus +1 cm to each member of both clans via `IClanMembershipRepository.list_by_clan`; `Title.ATAMAN` to one random raider on raid victory; releases activity locks; mark_finished + audit); `application/caravans/close_caravan_lobby.py` теперь шедулит battle-finish job при LOBBY → IN_BATTLE.
- **Infrastructure-слой:** `infrastructure/scheduler/aps.py` — caravan-battle-finish-методы + callback; `infrastructure/random/seeded_random.py` — детерминистичный `IRandom` от int-seed-а.
- **DI:** `bot/main.py` подключил `FinishCaravanBattle` через `Container`; `caravan_battle_finish_factory` wired.
- **Тесты:** `tests/fakes/delayed_job_scheduler.py` дополнен; 3 unit-модуля (`test_battle_resolution.py` 488 lines + `test_finish_caravan_battle.py` 879 lines + 2 modified) + 1 integration-модуль (`test_caravan_battle_finish.py` 519 lines, 3 теста — delivery / idempotency / invalid LOBBY-state); архитектурный гард `test_length_grant_guard.py` whitelist-нул `application/caravans/finish_caravan_battle.py` для отрицательных-дельт `.with_length()`.
- **`CARAVAN_CANCELLED` зарезервирован в audit-whitelist-е, но `CancelCaravan` use-case не реализован** — отложен на 3.2-D, где появится bot-handler `/caravan_cancel`.
- **Bot-handlers и UI отсутствуют.** `/caravan`, lobby-UI, `CaravanPresenter`, локали — Спринт 3.2-D.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **`CancelCaravan` не реализован** — отложен на 3.2-D. В 3.2-C добавлены только `AuditAction.CARAVAN_CANCELLED` (audit-whitelist) и сценарий «сценарий уже `CANCELLED`» обрабатывается в `FinishCaravanBattle` как no-op (`was_already_finished=True`). Это сознательный скоуп-trim — в 3.2-C нет вызывающей стороны (нет UI), поэтому use-case без consumer-а — лишний код.
- **APScheduler не публикует пост в чат при finish-battle.** `_run_caravan_battle_finish_job` в 3.2-C просто вызывает `FinishCaravanBattle.execute()` — не пишет ничего в Telegram. Публикация в чат-отправитель и чат-получатель «караван доставлен» / «караван разграблен» (плюс награды) — задача 3.2-D, где появится TG-сторона. До 3.2-D финиш каравана видим только в логах + audit-table + БД.
- **Use-case-ы караванов работают через 3 разных audit-source-а: `CARAVAN_BATTLE` (для длины-deductions от ударов рейдеров) и `CARAVAN_REWARD` (для всех positive-grants — leader/caravaneer/defender + clan-bonus).** Это даёт чистое разделение «что списали в бою» vs «что выдали в награду» в `audit_log` — удобно для аналитики и debug-а. `CARAVAN_REWARD` используется во всех 6× `LENGTH_GRANT`-ах в integration-тесте.
