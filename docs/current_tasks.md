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

**На `main`:** последний смерженный PR — **3.3-B** (PR #113, `9c859b7`) — use-case-ы `SummonBoss` / `JoinBossLobby` / `LeaveBossLobby` / `CloseBossLobby` (`application/bosses/`), миграция `0020_boss_fights` + ORM + SQLAlchemy-репо (`infrastructure/db/models/boss.py`, `infrastructure/db/repositories/{boss_fight,boss_participant}.py`), APScheduler (`infrastructure/scheduler/aps.py` — 6 boss-методов через 3 фабрики `boss_lobby_close_factory` / `boss_round_tick_factory` / `boss_fight_finish_factory` со `factory=None` до 3.3-D), 8 новых `AuditAction.BOSS_*` (`domain/shared/ports/audit.py`), 4 новых input-DTO (`application/dto/inputs.py`), DI-wiring в `bot/main.py`. Полное unit + integration-покрытие (27 integration + ~ 46 unit-тестов; total `make ci`: 4246 passed / 1 skipped, coverage 95.56%).

**В работе (этот PR; ветка `devin/1778255195-sprint-3-3-C-boss-battle-resolution`)** — **Спринт 3.3-C: боевая механика + завершение + scroll-drops «Рейд-босс»**. По образцу 3.2-C (караванов): чистый доменный сервис `boss_round_resolution` (boss attacks vs raider blocks, deterministic by seed через `SeededRandom(boss_fight.random_seed)`); use-case `RunBossRound` интегрирует с `IRandom`; use-case `FinishBossFight` распределяет награды + per-player ролл скроллов через `IRandom` (обычный + blessed; idempotency-key `(boss_fight_id, player_id, scroll_kind)`); audit-actions `BOSS_FIGHT_ROUND_RESOLVED` / `BOSS_FIGHT_FINISHED` / `BOSS_REWARDS_GRANTED` / `BOSS_FIGHT_CANCELLED` уже whitelist-нуты в 3.3-B; новый audit-action `SCROLL_DROP` добавляется здесь; архитектурный гард `test_length_grant_guard.py` whitelist-нёт `application/bosses/finish_boss_fight.py`; **критично:** интеграционный тест на 100 рейдов × 5 игроков с проверкой частот scroll-drop-а в границах толерантности. Bot-handlers + UI + локали + APScheduler factory-wiring — следующий PR (3.3-D).

Перед ним: **3.3-A** (PR #112, `dbb9b1c`) — каркас доменов «Рейд-босс». Перед ним: **3.2-D** (PR #111, `89e4f0a`) — bot-handlers `/caravan` + lobby-UI + презентеры + локали + APScheduler factory-wiring (закрытие Спринта 3.2). Перед ним: **3.2-C** (PR #110, `2333297`) — боевая механика каравана. Перед ним: **3.2-B** (PR #109, `e27968b`) — use-case-ы каравана + миграция `0019_caravans`. Перед ним: **3.2-A** (PR #108, `fe959c6`) — каркас доменов «Караван». Перед ним: **3.1-E** (PR #107, `5c1b26f`) — bot-handlers `/mountains` + `/dungeon` (закрытие Спринта 3.1). Перед ним: **catch-up docs 3.1-D** (PR #106, `76af44a`). Перед ним: **3.1-D** (PR #105, `2208ae6`). Перед ним: **3.1-C** (PR #103). Перед ним: **3.1-B** (PR #101). Перед ним: **3.1-A** (PR #99). Перед ним: PR-ы Спринта 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а: 3.2-A → 3.2-D). **Активный — Спринт 3.3 «Рейд-боссы»** ([`development_plan.md`](development_plan.md) §6.3.3); этот PR — третий из 4 (3.3-A → 3.3-D).

**Активная feature-ветка:** `devin/1778255195-sprint-3-3-C-boss-battle-resolution` (создана от свежего `main = 9c859b7` после мерджа 3.3-B; шаги C.0–C.13).

---

## 🎯 Активный спринт — Спринт 3.3 «Рейд-боссы» (продолжение)

> Цель спринта (по [`development_plan.md`](development_plan.md) §6.3.3 «Спринт 3.3 — Рейд-боссы»): механика рейд-боссов как PvE-сценарий — вызов босса (lvl 9+, ≥ 20 см, 1/4 ч глобально), управление AFK-боссом ботом, лобби 20 мин с пересылаемой кнопкой, боевая механика (босс — 3 атаки, рейдер — 3 блока, раунды 20 сек–1 мин), завершение: < 10 см у босса = победа рейдеров, иначе босс. Per-player ролл скроллов заточки на победу (см. ГДД §2.8.5).

**Скоуп — 6 задач из плана:**

- **3.3.1** — Вызов босса (lvl 9+, ≥ 20 см, 1/4 ч глобально). **Критерий:** Босс = случайный из топ-30.
- **3.3.2** — Управление боссом: игрок (если онлайн) → бот (auto). **Критерий:** E2E: AFK босс → бот рандомит.
- **3.3.3** — Лобби 20 мин, пересылаемая кнопка. **Критерий:** Минимум 1 рейдер.
- **3.3.4** — Боевая механика: босс — 3 атаки, рейдер — 3 блока. **Критерий:** Раунды 20 сек–1 мин.
- **3.3.5** — Завершение: < 10 см у босса = победа рейдеров; иначе босс. **Критерий:** Награды и % от системы — из `balance.yaml`.
- **3.3.6** — Per-player ролл скроллов заточки на победу (см. ГДД §2.8.5): обычный скролл — малый шанс; blessed — очень малый. Идемпотентно по `(boss_fight_id, player_id, scroll_kind)`. **Критерий:** Юнит-тесты per-player ролла; integration: 100 рейдов × 5 игроков, частоты в границах.

**Декомпозиция Спринта 3.3 на фичевые PR-ы:**

- **3.3-A — Каркас доменов «Рейд-босс».** ✅ Закрыт PR #112.
- **3.3-B — Use-cases + persistence + миграция.** ✅ Закрыт PR #113.
- **3.3-C — Боевая механика + завершение + scroll-drops.** ⏳ Этот PR. Чистый доменный сервис `boss_round_resolution` (boss attacks vs raider blocks, deterministic by seed через `SeededRandom(boss_fight.random_seed)`). Use-case `RunBossRound` интегрирует с `IRandom`. Use-case `FinishBossFight` распределяет награды + per-player ролл скроллов через `IRandom` (обычный + blessed; idempotency-key `(boss_fight_id, player_id, scroll_kind)`). Audit-actions `BOSS_FIGHT_ROUND_RESOLVED` / `BOSS_FIGHT_FINISHED` / `BOSS_REWARDS_GRANTED` / `BOSS_FIGHT_CANCELLED` уже whitelist-нуты в 3.3-B. Архитектурный гард `test_length_grant_guard.py` whitelist-нёт нужные модули. **Критично:** интеграционный тест на 100 рейдов × 5 игроков с проверкой частот скролл-дропа в границах толерантности.
- **3.3-D — Bot-handlers `/raid_boss` (или `/boss`) + лобби UI + презентеры + локали + APScheduler factory-wiring.** По образцу 3.1-E / 3.2-D: handler `/boss` в личке (lvl 9+, ≥ 20 см, 1/4 ч cooldown); inline-кнопки «вступить» + пересылаемая кнопка; `BossPresenter`; локали `bosses-*` (RU+EN parity); APScheduler-фабрики; DI-wiring; нотификаторы для round-tick / fight-finish; manual smoke-тест.

**Финальный коммит каждого PR-а Спринта 3.3** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.3-X: ...») + пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния>`, передвинуть чек-лист на следующий PR (или закрыть Спринт 3.3 на 3.3-D и расписать чек-лист **первого PR-а Спринта 3.4** «Заточка предметов» по [`development_plan.md`](development_plan.md) §6.3.4).

---

## 📝 Чек-лист следующего PR (Спринт 3.3-C — Боевая механика + завершение + scroll-drops)

> Этот PR — третий PR Спринта 3.3. Он приземляет резолв раундов рейда (atk vs block через `SeededRandom`), завершение боя (победа рейдеров если босс < 10 см / поражение если время вышло), распределение наград (length-grants через `ILengthGranter` + ataman/clan-bonus аналогии), per-player ролл скроллов заточки (обычный + blessed). Bot-handlers + UI + локали + APScheduler factory-wiring — следующий PR (3.3-D).

- [x] Дождаться мерджа `main = 9c859b7` (PR #113; 3.3-B).
- [x] `git fetch && git checkout main && git pull`.
- [x] `make ci` локально на свежем `main`: ✅ зелёный (4246 passed / 1 skipped, coverage 95.56%).
- [x] Создать ветку `devin/1778255195-sprint-3-3-C-boss-battle-resolution` от `main`.
- [x] **C.0 — Обновить `current_tasks.md`** под старт Спринта 3.3-C (этот коммит).
- [ ] **C.1 — Доменный сервис `boss_round_resolution`** (`domain/bosses/services.py`): чистая функция `resolve_round(*, boss_player_length_cm, raiders, boss_attack_targets, raider_blocks, base_damage_cm, rng) -> RoundOutcome`. RoundOutcome: damage_per_raider (dict), survivors (list), boss_damage_taken (int). Симметрично `domain/caravan/services.py`. Юнит-тесты: deterministic by seed; full-block escape-кейс; full-hit kill-кейс; partial-block fractional damage.
- [x] **C.2 — Use-case `RunBossRound`** (`application/bosses/run_boss_round.py`): загрузка boss_fight + всех participants + summoner-моды (если AFK — бот ролит атаку через `IRandom`); резолв через `boss_round_resolution`; обновление participant.damage_dealt_cm + boss_fight.current_boss_length_cm; `mark_finished` если `< victory_threshold_cm`; audit `BOSS_FIGHT_ROUND_RESOLVED` (idempotency-key `boss_fight_round_resolved:{boss_fight_id}:{round_number}`); шедул следующего `boss_round_tick` если бой продолжается. + DTO `RunBossRoundInput` (часть C.4) + 11 unit-тестов (`test_run_boss_round.py`).
- [ ] **C.3 — Use-case `FinishBossFight`** (`application/bosses/finish_boss_fight.py`): rewards-механика. Победа рейдеров (`current_boss_length_cm < victory_threshold_cm`) — length-grant каждому живому рейдеру через `ILengthGranter` + per-player ролл скроллов заточки (обычный + blessed) через `IRandom` с idempotency-key `boss_scroll_drop:{boss_fight_id}:{player_id}:{scroll_kind}`; босс получает refund (если применимо). Поражение (timeout) — рейдеры теряют контрибьюцию, босс получает grant. Audit-actions `BOSS_FIGHT_FINISHED` + `BOSS_REWARDS_GRANTED` + N× `LENGTH_GRANT` + N× `SCROLL_DROP` (action добавится в C.0). Идемпотентность повторного вызова (повторный шедул APScheduler).
- [ ] **C.4 — `application/dto/inputs.py`:** `RunBossRoundInput`, `FinishBossFightInput`.
- [ ] **C.5 — Inventory/scroll-drop путь** — проверить наличие порта добавления скроллов в `domain/inventory/`; если есть, переиспользовать; если нет, создать минимальный `IScrollDropper.add_scroll(player_id, scroll_kind: ScrollKind)`. Полная инфраструктура инвентаря — Спринт 3.4 «Заточка предметов».
- [ ] **C.6 — Audit-action `SCROLL_DROP`** (`domain/shared/ports/audit.py`) — если ещё не whitelist-нут.
- [ ] **C.7 — Архитектурный гард** (`tests/unit/architecture/test_length_grant_guard.py`): добавить `application/bosses/finish_boss_fight.py` в whitelist для `Player.with_length()` (deductions для босса при поражении рейдеров; `ILengthGranter` для positive-grant-ов).
- [ ] **C.8 — DI-провязка** (`bot/main.py`): добавить `RunBossRound` + `FinishBossFight` в `Container`. APScheduler-фабрики `boss_round_tick_factory` + `boss_fight_finish_factory` остаются `None` до 3.3-D.
- [ ] **C.9 — Push checkpoint** на `origin` для непрерывности.
- [ ] **C.10 — Юнит-тесты use-case-ов** (`tests/unit/application/bosses/test_run_boss_round.py` + `test_finish_boss_fight.py`): happy-path (победа рейдеров / поражение / next-round-scheduled) + error-cases (boss_fight не найден, в `LOBBY` — нельзя запустить раунд, в `FINISHED` — идемпотентно). Integration-тест: 100 рейдов × 5 игроков с проверкой частот scroll-drop-а в границах толерантности (`scroll_drop.regular=0.05 ± δ`, `blessed=0.005 ± δ`).
- [ ] **C.11 — Integration-тест scroll-drop-репо** (если новый): миграция up/down + CRUD + UNIQUE-инвариант на idempotency-ключ.
- [ ] **C.12 — `make ci` локально:** ruff / mypy --strict / import-linter / pytest / coverage gate (≥ 80%).
- [ ] **C.13 — Финальный док-коммит:** `history.md` +запись 3.3-C, `current_tasks.md` пересборка под старт Спринта 3.3-D (bot-handlers + UI).
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Предыдущий PR — 3.3-B (use-cases + persistence + миграция «Рейд-босс»):** ✅ закрыт PR #113.

**Текущий PR — 3.3-C (боевая механика + завершение + scroll-drops):** в работе на ветке `devin/1778255195-sprint-3-3-C-boss-battle-resolution`. C.0 — обновление `current_tasks.md` (этот коммит); далее по чек-листу C.1–C.13.

**Что было закрыто в 3.3-B:**
- **Application-слой:** `application/dto/inputs.py` +4 input-DTO (`SummonBossInput`, `JoinBossLobbyInput`, `LeaveBossLobbyInput`, `CloseBossLobbyInput`); новый пакет `application/bosses/` с 4 use-case-ами (`SummonBoss` с lvl 9+ / ≥ 20 см / 4ч-кулдаун / выбор boss_player_id из топ-30 через `IRandom.choice`, `JoinBossLobby` с проверкой не-summoner/не-boss, `LeaveBossLobby` с запретом для summoner-а, `CloseBossLobby` идемпотентный LOBBY → IN_BATTLE с шедулингом `boss_round_tick` + `boss_fight_finish`).
- **Domain-слой (расширения):** `domain/shared/ports/audit.py` +8 `BOSS_*`-actions (whitelist для `audit_log.action`); `domain/shared/ports/scheduler.py` +6 `schedule_boss_*` / `cancel_boss_*` методов.
- **Infrastructure-слой:** миграция `0020_boss_fights` + ORM `BossFightORM`/`BossParticipantORM` + репо `SqlAlchemyBossFightRepository` / `SqlAlchemyBossParticipantRepository` (с `get_active_for_player` через JOIN с `boss_participants` для саммонера/рейдера и прямой WHERE по `boss_player_id`); APScheduler-адаптер `_run_boss_lobby_close_job` / `_run_boss_round_tick_job` / `_run_boss_fight_finish_job` через 3 фабрики (`None` до 3.3-D). БД-инварианты: composite-PK `(boss_fight_id, player_id)` + partial-unique `uq_boss_participants_one_summoner_per_boss_fight` + CHECK `summoner_player_id <> boss_player_id` + ON DELETE CASCADE.
- **DI:** `bot/main.py` подключил репо + 4 use-case в `Container`.
- **Тесты:** `tests/fakes/boss_fight_repo.py` (in-memory `FakeBossFightRepository` + `FakeBossParticipantRepository`), 4 unit-модуля в `tests/unit/application/bosses/` (~ 46 тестов: happy-path/audit/idempotency/errors), integration-тест `tests/integration/db/test_boss_fight_repository.py` (27 тестов: CRUD + UNIQUE-инварианты + CHECK + ON DELETE CASCADE).
- **Боевая логика боя отсутствует.** Resolve рейда + награды + scroll-drops — Спринт 3.3-C; bot-handlers и UI — 3.3-D.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **`SCROLL_DROP`-инвентарный путь** (C.5/C.6). В 3.3-A/B нет существующего порта `IInventoryRepository.add_scroll`-варианта; нужно проверить в 3.3-C — либо создать port, либо переиспользовать инвентарный grant если он уже есть в `domain/inventory/` (3.4 «Заточка предметов» создаст полную инфраструктуру; в 3.3-C — минимально).
- **`SeededRandom` для `boss_fight.random_seed`.** Уже есть в `infrastructure/random/seeded_random.py` (3.2-C). Переиспользуется в 3.3-C для `boss_round_resolution`.
- **`bot_play_chance=1.0`** (config, по `cyan91`-решению) — в 3.3-C summoner-AFK = бот ролит. Логика «summoner online» — это presence-check; в 3.3-C можно сделать stub `is_summoner_online=False` (всегда AFK), реальная presence-логика — в 3.3-D с bot-handler-ами.
- **`CancelBossFight`** — отмена boss_fight саммонером. Audit-action `BOSS_FIGHT_CANCELLED` уже whitelist-нут в 3.3-B; use-case будет в 3.3-D (одновременно с handler-ом отмены).

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`9c859b7` — `Merge pull request #113 from Pipirkawar/devin/1778248645-sprint-3-3-B-boss-usecases-persistence` (старт ветки 3.3-C; будет обновлён первым коммитом C.0).
