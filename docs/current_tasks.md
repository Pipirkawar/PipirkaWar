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

**На `main`:** последний смерженный PR — **3.2-A** (этот PR; `<коммит_слияния>`) — каркас доменов «Караван» (entities `Caravan`/`CaravanParticipant`, enums `CaravanRole`/`CaravanStatus`, VO `CaravanContribution`, 8 доменных ошибок, порты `ICaravanRepository`/`ICaravanParticipantRepository`), `CaravansConfig` в pydantic-схеме баланса + секция `caravans:` в `config/balance.yaml`.

Перед ним: **3.1-E** (PR #107, `5c1b26f`) — bot-handlers `/mountains` + `/dungeon` + презентеры + локали + Telegram-нотификаторы + APScheduler factory-wiring (закрытие Спринта 3.1). Перед ним: **catch-up docs 3.1-D** (PR #106, `76af44a`). Перед ним: **3.1-D** (PR #105, `2208ae6`). Перед ним: **3.1-C** (PR #103). Перед ним: **3.1-B** (PR #101). Перед ним: **3.1-A** (PR #99). Перед ним: PR-ы Спринта 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). Стартовал **Спринт 3.2 «Караваны (полная механика)»** — этот PR (3.2-A) закладывает доменный фундамент. Use-case-ы (`CreateCaravan`, `JoinCaravanLobby`, `LeaveCaravanLobby`) приходят в **3.2-B**, боевая механика + награды — в **3.2-C**, bot-handlers + локали — в **3.2-D**.

**Активная feature-ветка:** ещё не создана. После мерджа этого 3.2-A PR-а в `main` следующий агент создаёт `devin/<unix_ts>-sprint-3-2-B-caravan-usecases-persistence` от свежего `main` и стартует **Спринт 3.2-B** (use-cases + миграция `0019_caravans` + persistence + APScheduler `lobby_close_factory`).

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

- **3.2-A — Каркас доменов (этот PR).** Domain entities `Caravan`/`CaravanParticipant`, enums `CaravanRole`/`CaravanStatus`, VO `CaravanContribution`, 8 доменных ошибок, порты `ICaravanRepository`/`ICaravanParticipantRepository`. `CaravansConfig` + `CaravanRewardMultipliers` в pydantic-схеме баланса. Секция `caravans:` в `config/balance.yaml` (lobby_minutes=20, battle_minutes=60, clan_cooldown_hours=12, min_thickness_level_leader=7, min_thickness_level_raider=5, min_length_cm=20, min_length_after_contribution_cm=20, max_raiders_per_caravaneer=4, max_defenders_per_caravaneer=2, base_reward_cm=5 × multipliers leader=4/caravaneer=3/defender=1/raider=0, clan_bonus_cm=1).
- **3.2-B — Use-cases `CreateCaravan` + `JoinCaravanLobby` + `LeaveCaravanLobby` + persistence + миграция.** `application/caravans/`: `CreateCaravan` (lvl 7+ gate, ≥ 20 см после контрибьюта, выбор target-клана, проверка кулдауна 12 ч, activity-lock), `JoinCaravanLobby` (двойное членство по таблице ГДД §9.4 — 5 кейсов; capacity-чекер по ролям через `list_by_caravan_and_role`; activity-lock), `LeaveCaravanLobby` (возврат `contribution_cm` в длину, освобождение activity-lock-а). Миграция `0019_caravans` (таблицы `caravans` + `caravan_participants` с `UNIQUE (caravan_id, player_id)` + partial unique index on active caravan per sender clan). SQLAlchemy-репо. APScheduler-job `caravan_lobby_close_factory` через тот же паттерн, что mountain/dungeon.
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

**Финальный коммит этого 3.2-A PR-а** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.2-A: каркас доменов каравана»), пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит-слияния-3.2-A>`, расписать чек-лист 3.2-B.

---

## 📝 Чек-лист текущего PR (Спринт 3.2-A)

> Это первый PR Спринта 3.2. Domain skeleton для каравана; use-case-ы и persistence — 3.2-B; боевая механика — 3.2-C; bot UX — 3.2-D.

- [x] Мердж `main = 5c1b26f` (3.1-E, PR #107).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778188720-sprint-3-2-A-caravan-domain-skeleton` от `main`.
- [x] **A.1 — `domain/caravan/value_objects.py`:** `CaravanRole` (LEADER/CARAVANEER/DEFENDER/RAIDER), `CaravanStatus` (LOBBY/IN_BATTLE/FINISHED/CANCELLED), `CaravanContribution(cm: int > 0)` VO frozen+slots.
- [x] **A.2 — `domain/caravan/entities.py`:** `Caravan` агрегат (двухфазный лайфцикл с `lobby_ends_at` + `battle_ends_at`, `mark_in_battle`/`mark_finished`/`mark_cancelled` с idempotency и terminal-status guard); `CaravanParticipant` (`caravaneer`/`defender`/`raider` class-методы; инвариант leader→CARAVANEER; инвариант contribution только у CARAVANEER).
- [x] **A.3 — `domain/caravan/errors.py`:** `CaravanError` + 7 подклассов (`CaravanNotFoundError`, `AlreadyInCaravanError`, `CaravanCooldownError`, `CaravanRoleConflictError`, `CaravanRequirementError`, `CaravanLobbyClosedError`, `CaravanCapacityExceededError`).
- [x] **A.4 — `domain/caravan/repositories.py`:** `ICaravanRepository` (5 async-методов) + `ICaravanParticipantRepository` (4 async-метода).
- [x] **A.5 — `domain/caravan/__init__.py`:** публичный API всех VO/entity/error/port.
- [x] **A.6 — Балансовый конфиг:** `CaravansConfig` + `CaravanRewardMultipliers` в `domain/balance/config.py`; +поле `caravans` в `BalanceConfig`. Секция `caravans:` в `config/balance.yaml` со всеми параметрами по умолчанию.
- [x] **A.7 — Тесты unit:** `tests/unit/domain/caravan/test_value_objects.py` (enum smoke + `CaravanContribution` валидация); `test_entities.py` (factories + transitions + invariants); `test_errors.py` (hierarchy + payloads); `test_repositories.py` (ABC smoke). `tests/unit/domain/balance/test_caravans_config.py` (pydantic-валидация + `BalanceConfig` integration + smoke реального `config/balance.yaml`). `tests/unit/domain/balance/factories.py` обновлена: добавлен `caravans`-блок в `valid_balance_payload()`.
- [x] `make ci` локально: ruff ✅, mypy --strict 764 файла ✅, import-linter 3 contracts kept ✅, **pytest 3794 passed / 1 skipped, coverage 95.95%** (gate 80%).
- [ ] **A.8 — Финальный док-коммит:** `history.md` +запись 3.2-A (старт Спринта 3.2), `current_tasks.md` пересборка под старт Спринта 3.2-B.
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Текущий PR — 3.2-A (старт Спринта 3.2):**
- 13 файлов изменено (excl. docs).
- **Domain-слой:** новый пакет `domain/caravan/` с пятью модулями (`value_objects`, `entities`, `errors`, `repositories`, `__init__`).
- **Balance-слой:** `domain/balance/config.py` — добавлены `CaravansConfig` + `CaravanRewardMultipliers`, поле `caravans` в `BalanceConfig`. `config/balance.yaml` — секция `caravans:`.
- **Тесты:** новые модули `tests/unit/domain/caravan/{test_value_objects,test_entities,test_errors,test_repositories}.py` (~ 80 тестов); `tests/unit/domain/balance/test_caravans_config.py` (~ 20 тестов); `tests/unit/domain/balance/factories.py` дополнена `caravans`-блоком (без него `BalanceConfig.model_validate` упадёт после добавления поля).
- **Бизнес-логика отсутствует.** Use-case-ы (`CreateCaravan`, `JoinCaravanLobby`, `LeaveCaravanLobby`) приходят в Спринте 3.2-B; resolve боя — в 3.2-C; bot-handlers — в 3.2-D.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Кулдаун клана 12 ч — от `started_at` или от `finished_at`?** В `ICaravanRepository.get_last_finished_at_for_clan` оставлен docstring-уточнение: «по решению на старте 3.2 кулдаун начинается с `started_at` создания каравана, не с `finished_at`». Реализация уточнится в Спринте 3.2-B при написании `CreateCaravan` use-case-а.
- **`AlreadyInCaravanError` vs `CaravanRoleConflictError` — кто бросает что.** В 3.2-A определены оба класса, но границы между ними — на уровне use-case в 3.2-B. Предположительно: `AlreadyInCaravanError` — конфликт с `activity_lock` (в любом караване / другой активности); `CaravanRoleConflictError` — конкретно нарушение правила §9.4 (роль не подходит по членству в кланах).
- **Атаман-титул** — расширение `Title` enum приходит в 3.2-C (когда появится `FinishCaravanBattle` use-case). В 3.2-A `domain/player/` не трогаем.
