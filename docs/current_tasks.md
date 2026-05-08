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

**На `main`:** последний смерженный PR — **3.2-D** (этот PR; мердж) — bot-handlers `/caravan` + lobby-UI + презентеры + локали + APScheduler factory-wiring. `application/caravans/notifier.py` (порты `ICaravanLobbyCloseNotifier` + `ICaravanBattleFinishNotifier`); `bot/notifications/caravans.py` (`TelegramCaravanLobbyCloseNotifier` + `TelegramCaravanBattleFinishNotifier` — резолвят клан/лидера/Атамана через репо, локаль через `IPlayerLocaleResolver`, рендерят через `CaravanPresenter`, шлют в чаты обоих кланов через `aiogram.Bot.send_message`, best-effort try/except, идемпотентны через `was_already_*`-флаги use-case-результата); `bot/handlers/caravan.py` (`/caravan` + `/caravan_join` + show_lobby/cancel/join_defender/join_raider/leave callbacks); `bot/presenters/caravans.py` (lobby-state + battle-state + finished-state); `application/caravans/cancel_caravan.py` (use-case `CancelCaravan`); локали `caravans-*` (RU+EN parity); APScheduler-callback-и `_run_caravan_lobby_close_job` + `_run_caravan_battle_finish_job` теперь публикуют посты в чат через notifier-ы (был блокер из 3.2-C). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а: 3.2-A → 3.2-D). `make ci`: pytest 4065 passed / 1 skipped, coverage 95.63%.

Перед ним: **3.2-C** (PR #110, `2333297`) — боевая механика каравана (доменный сервис `caravan_battle_resolution`, use-case `FinishCaravanBattle`, `Title.ATAMAN`, `SeededRandom`). Перед ним: **3.2-B** (PR #109, `e27968b`) — use-case-ы `CreateCaravan` / `JoinCaravanLobby` / `LeaveCaravanLobby` / `CloseCaravanLobby`, миграция `0019_caravans`. Перед ним: **3.2-A** (PR #108, `fe959c6`) — каркас доменов «Караван». Перед ним: **3.1-E** (PR #107, `5c1b26f`) — bot-handlers `/mountains` + `/dungeon` (закрытие Спринта 3.1). Перед ним: **catch-up docs 3.1-D** (PR #106, `76af44a`). Перед ним: **3.1-D** (PR #105, `2208ae6`). Перед ним: **3.1-C** (PR #103). Перед ним: **3.1-B** (PR #101). Перед ним: **3.1-A** (PR #99). Перед ним: PR-ы Спринта 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а: 3.2-A → 3.2-D). Следующий — **Спринт 3.3 «Рейд-боссы»** ([`development_plan.md`](development_plan.md) §6.3.3). До старта 3.3 — нет активной feature-ветки.

**Активная feature-ветка:** *(нет)* — после мерджа 3.2-D ветка `devin/1778231804-sprint-3-2-D-caravan-bot-handlers` закрыта. Следующий агент должен fetch-нуть свежий `main`, прочитать чек-лист «Спринт 3.3-A» ниже и создать новую feature-ветку от `main`.

---

## 🎯 Активный спринт — Спринт 3.3 «Рейд-боссы» (старт)

> Цель спринта (по [`development_plan.md`](development_plan.md) §6.3.3 «Спринт 3.3 — Рейд-боссы»): механика рейд-боссов как PvE-сценарий — вызов босса (lvl 9+, ≥ 20 см, 1/4 ч глобально), управление AFK-боссом ботом, лобби 20 мин с пересылаемой кнопкой, боевая механика (босс — 3 атаки, рейдер — 3 блока, раунды 20 сек–1 мин), завершение: < 10 см у босса = победа рейдеров, иначе босс. Per-player ролл скроллов заточки на победу (см. ГДД §2.8.5).

**Скоуп — 6 задач из плана:**

- **3.3.1** — Вызов босса (lvl 9+, ≥ 20 см, 1/4 ч глобально). **Критерий:** Босс = случайный из топ-30.
- **3.3.2** — Управление боссом: игрок (если онлайн) → бот (auto). **Критерий:** E2E: AFK босс → бот рандомит.
- **3.3.3** — Лобби 20 мин, пересылаемая кнопка. **Критерий:** Минимум 1 рейдер.
- **3.3.4** — Боевая механика: босс — 3 атаки, рейдер — 3 блока. **Критерий:** Раунды 20 сек–1 мин.
- **3.3.5** — Завершение: < 10 см у босса = победа рейдеров; иначе босс. **Критерий:** Награды и % от системы — из `balance.yaml`.
- **3.3.6** — Per-player ролл скроллов заточки на победу (см. ГДД §2.8.5): обычный скролл — малый шанс; blessed — очень малый. Идемпотентно по `(boss_fight_id, player_id, scroll_kind)`. **Критерий:** Юнит-тесты per-player ролла; integration: 100 рейдов × 5 игроков, частоты в границах.

**Декомпозиция Спринта 3.3 на фичевые PR-ы (предварительно — уточняется при старте каждого PR-а):**

- **3.3-A — Каркас доменов «Рейд-босс».** Domain entities `BossFight`/`BossParticipant` (агрегаты), enums `BossKind`/`BossFightStatus`, VO `BossDamage`, доменные ошибки (`BossFightNotFound`, `BossFightAlreadyStarted`, `BossFightAlreadyFinished`, `NotEligibleForBossSummon`, `NotInBossLobby`, и т.п.), порты `IBossFightRepository`/`IBossParticipantRepository`. `BossesConfig` + `BossRoundConfig` + `BossScrollDropConfig` в pydantic-схеме баланса. Секция `bosses:` в `config/balance.yaml` (lobby_minutes=20, summon_cooldown_hours=4 — глобальный, min_thickness_level=9, min_length_cm=20, base_hp_cm, victory_threshold_cm=10, round_min_seconds=20, round_max_seconds=60, base_damage_cm, scroll_drop_chance_regular, scroll_drop_chance_blessed). Принципиальные решения по умолчанию: запросить у `cyan91` на старте 3.3-A (см. блок «Решения, которые нужно зафиксировать» ниже).
- **3.3-B — Use-cases + persistence + миграция.** `application/bosses/`: `SummonBoss` (lvl 9+ gate, ≥ 20 см gate, глобальный кулдаун 1/4 ч через распределённый lock, выбор случайного из топ-30 через `IClanQuery`-расширение, activity-lock саммонера), `JoinBossLobby`, `LeaveBossLobby`, `CloseBossLobby` (LOBBY → IN_BATTLE, идемпотентен), `RunBossRound` (per-round resolve, raider blocks vs boss attacks), `FinishBossFight` (распределение наград, per-player скролл-ролл). Миграция `0020_boss_fights` (таблицы `boss_fights` + `boss_participants`). SQLAlchemy-репо. APScheduler-job-ы `boss_lobby_close_factory` + `boss_round_tick_factory` + `boss_fight_finish_factory` (фабрики `None` до 3.3-D).
- **3.3-C — Боевая механика + завершение + scroll-drops.** Чистый доменный сервис `boss_round_resolution` (boss attacks vs raider blocks, deterministic by seed). Use-case `RunBossRound` интегрирует с `IRandom`. Use-case `FinishBossFight` распределяет награды + per-player ролл скроллов через `IRandom` (обычный + blessed; idempotency-key `(boss_fight_id, player_id, scroll_kind)`). Audit-actions `BOSS_FIGHT_*`. Архитектурный гард `test_length_grant_guard.py` whitelist-нёт нужные модули. **Критично:** интеграционный тест на 100 рейдов × 5 игроков с проверкой частот скролл-дропа в границах толерантности.
- **3.3-D — Bot-handlers `/raid_boss` (или `/boss`) + лобби UI + презентеры + локали + APScheduler factory-wiring.** По образцу 3.1-E / 3.2-D: handler `/boss` в личке (lvl 9+, ≥ 20 см, 1/4 ч cooldown); inline-кнопки «вступить» + пересылаемая кнопка; `BossPresenter`; локали `bosses-*` (RU+EN parity); APScheduler-фабрики; DI-wiring; нотификаторы для round-tick / fight-finish; manual smoke-тест.

**Решения, которые нужно зафиксировать на старте 3.3-A** (запросить у `cyan91`, прежде чем брать домен):
1. **«Случайный из топ-30» (3.3.1)** — топ-30 *кланов* (по `length_cm`)? Или топ-30 *игроков* (по `length_cm`)? В ГДД §10 формулировка двусмысленная — нужен вердикт, иначе домен не спроектируешь.
2. **«1/4 ч глобально» (3.3.1)** — кулдаун применяется глобально на проект (один босс в 4 часа на всех игроков сервера) или per-clan / per-player? ГДД §10 говорит «глобально» — но это технически означает распределённый lock с retry-логикой; нужно подтверждение, что это intent (а не per-player rate-limit).
3. **«Управление боссом игроком» (3.3.2)** — какая UI-форма? Inline-кнопки в личке у саммонера? Полу-автоматический выбор атак с timeout-ом → fallback на бот? Нужен mockup-ish-описание UX перед домен-проектированием.
4. **«Раунды 20 сек–1 мин» (3.3.4)** — это длина раунда (timer), внутри которого происходит resolve, или интервал между раундами? И сколько всего раундов в бою (фиксированный N или до победы/поражения)?
5. **`scroll_drop_chance_*` дефолты** — конкретные числа из ГДД §2.8.5 или через формулу?
6. **`base_damage_cm` per-round** — фиксированное число или зависит от уровня босса/толщины рейдеров?

Эти 6 пунктов **должны быть закрыты до начала 3.3-A** (через chat с `cyan91` или PR в `docs/game_design.md`-clarifications) — иначе доменный слой выйдет некомплитный, и 3.3-B/C будут упираться в «а что у нас тут балансовый параметр?».

**Финальный коммит каждого PR-а Спринта 3.3** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.3-X: ...») + пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния>`, передвинуть чек-лист на следующий PR (или закрыть Спринт 3.3 на 3.3-D и расписать чек-лист **первого PR-а Спринта 3.4** «Заточка предметов» по [`development_plan.md`](development_plan.md) §6.3.4).

---

## 📝 Чек-лист следующего PR (Спринт 3.3-A — Каркас доменов «Рейд-босс»)

> Этот PR — первый PR Спринта 3.3. Он только проектирует и приземляет доменный слой `domain/bosses/` + расширяет `config/balance.yaml` + `domain/balance/config.py` под `bosses:`. Use-case-ы / persistence / миграция / bot-handlers / UI — следующие PR-ы (3.3-B/C/D).

- [ ] Дождаться мерджа `main = <коммит_3.2-D>` (этот PR; мердж).
- [ ] `git fetch && git checkout main && git pull`.
- [ ] `make ci` локально на свежем `main`: убедиться, что зелёный.
- [ ] **Запросить у `cyan91` ответы на 6 пунктов из «Решения, которые нужно зафиксировать на старте 3.3-A»** (см. секцию выше). Без них не начинать домен — иначе придётся переделывать.
- [ ] Создать ветку `devin/{timestamp}-sprint-3-3-A-boss-domain` от `main`.
- [ ] **A.0 — Обновить `current_tasks.md`** под старт Спринта 3.3-A (этот коммит): «Активная feature-ветка», «Что ровно сейчас в работе».
- [ ] **A.1 — Domain entities** (`domain/bosses/entities.py`): `BossFight` (агрегат, lifecycle LOBBY → IN_BATTLE → FINISHED|CANCELLED, методы `start_battle`/`mark_finished`/`mark_cancelled`), `BossParticipant` (роль рейдера, `damage_dealt_cm`, `is_alive`).
- [ ] **A.2 — Domain enums + VO** (`domain/bosses/value_objects.py`): `BossKind` (если нужно различать типы боссов), `BossFightStatus` (`LOBBY`/`IN_BATTLE`/`FINISHED`/`CANCELLED`), `BossDamage` (или `BossDamageDelta` — в зависимости от того, как именно мы считаем урон в раунде).
- [ ] **A.3 — Domain errors** (`domain/bosses/errors.py`): `BossFightNotFound`, `BossFightAlreadyStarted`, `BossFightAlreadyFinished`, `BossFightAlreadyCancelled`, `NotEligibleForBossSummon` (lvl/length/cooldown), `NotInBossLobby`, `BossLobbyClosed`, `InvalidBossFightStateError`.
- [ ] **A.4 — Domain ports** (`domain/shared/ports/`): `IBossFightRepository`, `IBossParticipantRepository` — методы `get_by_id`, `add`, `save`, `list_by_boss`, `list_active_in_window` (для глобального cooldown-чекера).
- [ ] **A.5 — Audit-actions** (`domain/shared/ports/audit.py`): `BOSS_FIGHT_SUMMONED`, `BOSS_FIGHT_STARTED`, `BOSS_FIGHT_ROUND_RESOLVED` (если нужно отдельно), `BOSS_FIGHT_FINISHED`, `BOSS_REWARDS_GRANTED`, `BOSS_SCROLL_DROPPED` (если важно фиксировать в audit), `BOSS_FIGHT_CANCELLED`. Whitelist для `audit_log.action`.
- [ ] **A.6 — Scheduler ports** (`domain/shared/ports/scheduler.py`): `IDelayedJobScheduler.schedule_boss_lobby_close` / `cancel_boss_lobby_close` / `schedule_boss_fight_finish` / `cancel_boss_fight_finish`. (Раунд-tick-и — отдельный API в зависимости от ответа на пункт 4 «Решения».)
- [ ] **A.7 — Balance config** (`domain/balance/config.py`): pydantic `BossesConfig` с полями `lobby_minutes`, `summon_cooldown_hours`, `min_thickness_level`, `min_length_cm`, `base_hp_cm`, `victory_threshold_cm`, `round_min_seconds`, `round_max_seconds`, `base_damage_cm`, `top_pool_size` (обычно 30), `BossRewardConfig` (множители), `BossScrollDropConfig` (chance_regular, chance_blessed). Pydantic-валидаторы.
- [ ] **A.8 — Balance YAML** (`config/balance.yaml`): секция `bosses:` со стартовыми дефолтами (по результатам пункта «Решения»).
- [ ] **A.9 — Юнит-тесты:**
  - `tests/unit/domain/bosses/test_entities.py` — lifecycle-переходы `BossFight`, валидация полей, идемпотентность `mark_finished`/`mark_cancelled`.
  - `tests/unit/domain/bosses/test_errors.py` — message-форматирование ошибок.
  - `tests/unit/domain/balance/test_bosses_config.py` — pydantic-валидаторы (минимумы, монотонность round_min ≤ round_max, etc.).
  - `tests/unit/domain/balance/factories.py::build_valid_balance` — добавить дефолтную секцию `bosses:`.
- [ ] **A.10 — Финальный док-коммит этого PR-а:** `history.md` +запись 3.3-A (старт Спринта 3.3), `current_tasks.md` пересобрать под старт 3.3-B (use-cases + persistence + миграция).
- [ ] `make ci` локально: ruff / mypy --strict / import-linter / pytest / coverage gate (≥ 80%).
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Закрытый PR — 3.2-D (bot-handlers `/caravan` + лобби UI + презентеры + локали + APScheduler factory-wiring):**
- 11 файлов изменено (excl. docs).
- **Application-слой:** `application/caravans/notifier.py` — порты `ICaravanLobbyCloseNotifier` + `ICaravanBattleFinishNotifier`; `application/caravans/__init__.py` — экспорт; `application/caravans/cancel_caravan.py` — use-case `CancelCaravan` (D.1).
- **Bot-слой:** `bot/handlers/caravan.py` — `/caravan` + `/caravan_join` + show_lobby/cancel/join_defender/join_raider/leave callbacks (D.2/D.3); `bot/presenters/caravans.py` — lobby-state + battle-state + finished-state (873 строк, D.4); `bot/notifications/caravans.py` — Telegram-нотификаторы (364 строк, D.6); `bot/notifications/__init__.py` — экспорт; `bot/main.py` — DI-wiring `CancelCaravan` + нотификаторов в `APSchedulerDelayedJobScheduler`.
- **Infrastructure-слой:** `infrastructure/scheduler/aps.py` — APScheduler-callback-и `_run_caravan_lobby_close_job` + `_run_caravan_battle_finish_job` теперь вызывают `notifier.notify(result)` после успешного `execute(...)` (D.6, закрытие блокера из 3.2-C).
- **Локали:** `locales/{ru,en}.ftl` — добавлены ключи `caravans-battle-started`, `caravans-battle-finished-delivered`, `caravans-battle-finished-raided` + line-ключи (D.5).
- **Тесты:** `tests/unit/application/caravans/test_cancel_caravan.py` (D.1), `tests/unit/bot/handlers/test_caravan.py` (D.2), `tests/unit/bot/notifications/test_caravans.py` (709 строк, D.8) — обширное покрытие нотификаторов: idempotency, happy-path, локаль-резолюция, edge-cases, swallow `TelegramAPIError`/`RuntimeError`, marker-bundle для проверки i18n-ключей.
- `make ci` локально: ruff / mypy --strict / import-linter / pytest 4065 passed / 1 skipped, coverage 95.63%.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Нет открытых блокеров на момент закрытия 3.2-D.** Все доменные/application/infrastructure/UI-слои каравана закрыты. APScheduler публикует посты в чат через `aiogram` (был блокер из 3.2-C — закрыт в D.6).
- **На старте 3.3-A нужно зафиксировать 6 пунктов «Решения, которые нужно зафиксировать»** (см. секцию «Активный спринт» выше) — без них доменный слой `domain/bosses/` выйдет некомплитный, и 3.3-B/C будут упираться в недоопределённые балансовые параметры. Запросить у `cyan91` перед началом ветки `devin/{timestamp}-sprint-3-3-A-boss-domain`.

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`4b9b658` — `test(3.2-D): unit tests for caravan notifiers (D.8)` — будет обновлён после D.10 docs-коммита.
