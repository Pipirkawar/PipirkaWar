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

**На `main`:** последний смерженный PR — **3.3-C** (этот PR, открывается следующим коммитом) — доменный сервис `boss_round_resolution` (`domain/bosses/services.py`, чистая `resolve_boss_round` с 3 атаками босса × 2/3-block-coverage рейдеров, deterministic by `SeededRandom(boss_fight.random_seed * 1_000_003 + current_round)`) + use-case-ы `RunBossRound` / `FinishBossFight` (`application/bosses/run_boss_round.py` 376 строк / `finish_boss_fight.py` 507 строк): per-player length-grant + независимый ролл `regular`/`blessed`-скроллов (audit-only — реальный инвентарь в Спринте 3.4), boss victory-clamp до `victory_threshold_cm`, raider-loss-grant боссу при поражении, идемпотентность по детерминистичным `idempotency_key`-ам (`boss_fight_round_resolved:{id}:{round}`, `boss_fight_finished:{id}`, `boss_rewards_granted:{id}`, `add_length:boss_fight_reward:{id}:{player}`, `boss_scroll_drop:{id}:{player}:{kind}`); `AuditAction.SCROLL_DROP` whitelist-нут (`domain/shared/ports/audit.py`); `application/bosses/finish_boss_fight.py` whitelist-нут в `tests/unit/architecture/test_length_grant_guard.py` для `Player.with_length(...)` (refund-к-самому-себе при victory-clamp); +28 строк фикстуры `_container_with_fakes` в `tests/unit/bot/test_composition_root.py`; DI-wiring `RunBossRound` + `FinishBossFight` в `Container` (`bot/main.py`). APScheduler-фабрики `boss_round_tick_factory` + `boss_fight_finish_factory` остаются `None` до 3.3-D (как и `boss_lobby_close_factory` с 3.3-B). Полное unit-покрытие use-case-ов: 11 + 17 unit-тестов (`tests/unit/application/bosses/`) + 23 теста доменного сервиса (`tests/unit/domain/bosses/test_services.py`); total `make ci`: 4308 passed / 2 skipped, coverage 95.60%.

Перед ним: **3.3-B** (PR #113, `9c859b7`) — use-case-ы `SummonBoss` / `JoinBossLobby` / `LeaveBossLobby` / `CloseBossLobby` (`application/bosses/`), миграция `0020_boss_fights` + ORM + SQLAlchemy-репо (`infrastructure/db/models/boss.py`, `infrastructure/db/repositories/{boss_fight,boss_participant}.py`), APScheduler (`infrastructure/scheduler/aps.py` — 6 boss-методов через 3 фабрики со `factory=None` до 3.3-D), 8 новых `AuditAction.BOSS_*`, 4 новых input-DTO, DI-wiring. Перед ним: **3.3-A** (PR #112, `dbb9b1c`) — каркас доменов «Рейд-босс». Перед ним: **3.2-D** (PR #111, `89e4f0a`) — bot-handlers `/caravan` + lobby-UI + презентеры + локали + APScheduler factory-wiring (закрытие Спринта 3.2). Перед ним: **3.2-C** (PR #110, `2333297`) — боевая механика каравана. Перед ним: **3.2-B** (PR #109, `e27968b`) — use-case-ы каравана + миграция `0019_caravans`. Перед ним: **3.2-A** (PR #108, `fe959c6`) — каркас доменов «Караван». Перед ним: **3.1-E** (PR #107, `5c1b26f`) — bot-handlers `/mountains` + `/dungeon` (закрытие Спринта 3.1). Перед ним: **catch-up docs 3.1-D** (PR #106, `76af44a`). Перед ним: **3.1-D** (PR #105, `2208ae6`). Перед ним: **3.1-C** (PR #103). Перед ним: **3.1-B** (PR #101). Перед ним: **3.1-A** (PR #99). Перед ним: PR-ы Спринта 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а: 3.2-A → 3.2-D). **Активный — Спринт 3.3 «Рейд-боссы»** ([`development_plan.md`](development_plan.md) §6.3.3); закрыты 3 PR-а из 4 (3.3-A + 3.3-B + 3.3-C — этот PR, открывается следующим коммитом), следующий — 3.3-D (закрытие Спринта 3.3).

**Следующая feature-ветка** (для 3.3-D): `devin/<timestamp>-sprint-3-3-D-boss-handlers-ui` от свежего `main = <коммит-слияния-3.3-C>` (после мерджа этого PR-а).

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
- **3.3-C — Боевая механика + завершение + scroll-drops.** ✅ Этот PR (открывается после докоммита). Чистый доменный сервис `boss_round_resolution` + use-case-ы `RunBossRound` / `FinishBossFight` + per-player ролл скроллов (audit-only до 3.4) + DI-wiring + 51 unit-тест.
- **3.3-D — Bot-handlers `/raid_boss` (или `/boss`) + лобби UI + презентеры + локали + APScheduler factory-wiring + integration-тест частот scroll-drop-а + `CancelBossFight`.** ⏳ Следующий PR (закрытие Спринта 3.3). По образцу 3.1-E / 3.2-D: handler `/boss` в личке (lvl 9+, ≥ 20 см, 1/4 ч cooldown); inline-кнопки «вступить» + пересылаемая кнопка для рейдеров; `BossPresenter`; локали `bosses-*` (RU+EN parity); APScheduler-фабрики `boss_lobby_close_factory` / `boss_round_tick_factory` / `boss_fight_finish_factory` (все три замыкаются здесь); DI-wiring фабрик; нотификаторы для round-tick / fight-finish (по итогам каждого раунда — пуш в чат рейдеров); use-case `CancelBossFight` (саммонер отменяет до начала боя; audit-action `BOSS_FIGHT_CANCELLED` уже whitelist-нут в 3.3-B); use-case `LeaveBossLobby` уже есть в 3.3-B (handler-у только связать); raider-loss length-вычеты (отложены из 3.3-C — реальные `length`-deductions при поражении); integration-тест частот scroll-drop-а на 100 рейдов × 5 игроков (отложен из 3.3-C, требует APScheduler-фабрик); presence-check саммонера (онлайн ли — для перехода `bot_play_chance`-логики из stub в реальную; на 3.3-D можно остаться на stub `is_summoner_online=False` и поднять в более поздний спринт); manual smoke-тест.

**Финальный коммит каждого PR-а Спринта 3.3** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.3-X: ...») + пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния>`, передвинуть чек-лист на следующий PR (или закрыть Спринт 3.3 на 3.3-D и расписать чек-лист **первого PR-а Спринта 3.4** «Заточка предметов» по [`development_plan.md`](development_plan.md) §6.3.4).

---

## 📝 Чек-лист следующего PR (Спринт 3.3-D — Bot-handlers + UI + локали + APScheduler factory-wiring + закрытие Спринта 3.3)

> Этот PR — четвёртый и последний PR Спринта 3.3. Он приземляет UI-слой рейд-боссов на готовые use-case-ы 3.3-A/B/C: handler `/boss` в личке с лобби-UI (inline-кнопки «вступить» + пересылаемая кнопка), `BossPresenter` для рендера состояния боя, локали `bosses-*` (RU+EN parity), APScheduler-фабрики `boss_lobby_close_factory` / `boss_round_tick_factory` / `boss_fight_finish_factory` (все три замыкаются здесь, до этого были `None`), нотификаторы для round-tick / fight-finish, use-case `CancelBossFight` для отмены боя саммонером, raider-loss length-вычеты при поражении (отложены из 3.3-C), integration-тест частот scroll-drop-а на 100 рейдов × 5 игроков (отложен из 3.3-C, теперь доступен через factory-wiring), manual smoke-тест. После мерджа Спринт 3.3 «Рейд-боссы» закрыт; следующий — Спринт 3.4 «Заточка предметов».

- [ ] Дождаться мерджа `main = <коммит-слияния-3.3-C>` (PR `#<номер>`; 3.3-C).
- [ ] `git fetch && git checkout main && git pull`.
- [ ] `make ci` локально на свежем `main`: должен быть зелёный.
- [ ] Создать ветку `devin/<timestamp>-sprint-3-3-D-boss-handlers-ui` от `main`.
- [ ] **D.0 — Обновить `current_tasks.md`** под старт Спринта 3.3-D (этот коммит): пересобрать «Снимок состояния» под `main = <merge-sha-3.3-C>`, передвинуть чек-лист на 3.3-D, заполнить «Что ровно сейчас в работе» под старт.
- [ ] **D.1 — Use-case `CancelBossFight`** (`application/bosses/cancel_boss_fight.py`): идемпотентный путь `LOBBY` → `CANCELLED` саммонером (другие игроки — `NotAuthorizedError`); запретить отмену в `IN_BATTLE` (`InvalidBossFightStateError`); снятие `activity_lock(player, BOSS_FIGHT)` для саммонера + всех рейдеров; cancel-ит pending APScheduler-jobs (`cancel_boss_lobby_close` + `cancel_boss_round_tick` + `cancel_boss_fight_finish`); audit `BOSS_FIGHT_CANCELLED` (idempotency-key `boss_fight_cancelled:{boss_fight_id}`). DTO `CancelBossFightInput(boss_fight_id, player_id)` в `application/dto/inputs.py`. Юнит-тесты (~ 6–8): happy-path (саммонер отменяет в LOBBY → CANCELLED + audit + locks released + jobs cancelled), error-cases (не саммонер → NotAuthorizedError, в `IN_BATTLE` → InvalidBossFightStateError, в `CANCELLED` — идемпотентно), audit-payload-структура.
- [ ] **D.2 — Raider-loss length-вычеты** (`application/bosses/finish_boss_fight.py`, отложено из 3.3-C): при поражении рейдеров — каждому рейдеру `Player.length -= max(0, contributed_cm)` где `contributed_cm = length_at_join_cm - current_length_cm` (рейдеры, у которых `current_length_cm < length_at_join_cm`, т.е. урон уже получен — теряют разницу + extra; для тех, кто остался жив без урона — теряют symbolic фиксированную сумму из `bosses.raider_loss_floor_cm` если такая опция в balance.yaml). Точная формула — согласовать с cyan91 при старте 3.3-D (на 3.3-C вычетов нет вообще; на 3.3-D — нужны). Whitelist `application/bosses/finish_boss_fight.py` для `Player.with_length(...)` уже есть с 3.3-C. + Расширить unit-тесты `test_finish_boss_fight.py` (поражение → boss-grant + raider-loss + audit `LENGTH_REVOKE` каждому рейдеру).
- [ ] **D.3 — APScheduler-фабрики `boss_lobby_close_factory` / `boss_round_tick_factory` / `boss_fight_finish_factory`** (`bot/main.py` + `bot/jobs/boss_jobs.py`-подобный модуль): три фабрики возвращают async-callback-функции, замыкающиеся над `Container` и вызывающие `CloseBossLobby` / `RunBossRound` / `FinishBossFight` use-case-ы. Передаются в `APSchedulerAdapter`-конструктор (вместо `None`). Pattern: симметрично `caravan_lobby_close_factory` (3.2-D), который замыкается над `CloseCaravanLobby`. Передача `IRandom`-фабрики в `RunBossRound`-callback через тот же `Container`.
- [ ] **D.4 — Bot-handlers `/boss`** (`bot/handlers/boss.py`): аналог `bot/handlers/caravan.py` (3.2-D) и `bot/handlers/mountains.py` (3.1-E). `/boss` в личке с проверкой lvl 9+ / ≥ 20 см / 1/4 ч cooldown (валидируется в `SummonBoss` use-case-е, handler только показывает соответствующее сообщение об ошибке); inline-keyboard с двумя кнопками: «🤝 Вступить рейдером» (callback `boss:join:{boss_fight_id}`) + «📤 Переслать в чат» (через ForwardMessage / aiogram inline keyboard `switch_inline_query`); callback `boss:leave:{boss_fight_id}` (для рейдера); callback `boss:cancel:{boss_fight_id}` (для саммонера, до начала боя). Передача `BossPresenter`-инстанса для рендера. Игнорить дубликат-вызовы (`AlreadyInBossLobbyError` / `BossLobbyFullError` / etc.) с graceful answer-callback-query.
- [ ] **D.5 — `BossPresenter`** (`bot/presenters/boss.py`): рендер `BossFightSnapshot` в текст для лобби (имя саммонера + список рейдеров + таймер до начала) + рендер для боя (текущая длина босса / список рейдеров с урон-контрибьюцией / номер раунда / таймер до следующего tick) + рендер исхода (победа: список рейдеров с length-grant-ами + scroll-drop-ами; поражение: длина босса + raider-loss-вычеты).
- [ ] **D.6 — Локали `bosses-*`** (`src/pipirik_wars/i18n/locales/{ru,en}/bosses.ftl`): переводы лобби-UI / round-tick-нотификаций / fight-finish-нотификаций / scroll-drop-уведомлений / cancel-уведомления / error-сообщений (`BossSummonCooldownActive` / `BossPlayerLengthInsufficient` / `BossLevelInsufficient` / `BossLobbyFull` / `AlreadyInBossLobby` / `NotAuthorizedToCancelBoss` / etc.). RU+EN parity (тест `tests/unit/i18n/test_locale_parity.py` на parity ключей).
- [ ] **D.7 — Нотификаторы round-tick / fight-finish** (`bot/notifiers/boss.py` или расширение `boss_jobs.py`-callback-ов): пуш-сообщения в чат рейдеров после каждого `RunBossRound` (BossRoundResolved → текст «Раунд N: босс получил Xcm урона, рейдер K выбит» через `BossPresenter.render_round_result`) + после `FinishBossFight` (BossFightFinished → «🎉 Победа! Каждый получил +Xcm + N скроллов» / «💔 Поражение, босс остался Xcm»). Через `IBotMessenger`-порт (или адаптер aiogram-бота).
- [ ] **D.8 — DI-провязка** (`bot/main.py`): `CancelBossFight` в `Container`; фабрики `boss_*_factory` пересобираются с реальными callback-ами; нотификаторы вшиваются в callback-функции job-ов.
- [ ] **D.9 — Push checkpoint** на `origin` для непрерывности (после D.4 — handler-ы готовы локально; после D.7 — нотификаторы готовы).
- [ ] **D.10 — Юнит-тесты use-case-а `CancelBossFight`** (`tests/unit/application/bosses/test_cancel_boss_fight.py`, ~ 6–8 тестов).
- [ ] **D.11 — Юнит-тесты handler-ов / презентера / локалей** (`tests/unit/bot/handlers/test_boss.py`, `tests/unit/bot/presenters/test_boss_presenter.py`): happy-path рендера для каждого состояния (LOBBY / IN_BATTLE / FINISHED-победа / FINISHED-поражение / CANCELLED) + локали-parity-тест.
- [ ] **D.12 — Integration-тест частот scroll-drop-а** (`tests/integration/application/bosses/test_scroll_drop_frequencies.py`, отложен из 3.3-C): 100 рейдов × 5 игроков, проверка `regular_drop_rate ≈ cfg.regular ± δ` и `blessed_drop_rate ≈ cfg.blessed ± δ` (`δ` ~ 2-3 sigma на бернулли). Использует `FakeRandom` или real `SeededRandom` с разными seed-ами.
- [ ] **D.13 — Manual smoke-тест** в Telegram (через test-token): saммон босса → join 1-2 рейдерами → close lobby → run-rounds → fight-finish → проверить нотификации + scroll-drop-уведомления + audit-log entries. Документация процедуры в `docs/manual_smoke_tests.md` (если такой файл есть; иначе создать или дописать в `docs/development_plan.md`).
- [ ] **D.14 — `make ci` локально:** ruff / mypy --strict / import-linter / pytest / coverage gate (≥ 80%).
- [ ] **D.15 — Финальный док-коммит:** `history.md` +запись 3.3-D + закрытие Спринта 3.3, `current_tasks.md` пересборка под старт **Спринта 3.4 «Заточка предметов»** (полный цикл: `domain/inventory/` + `EnchantedItem`-агрегат + миграция `0021_inventory_scrolls` + use-case `EnchantItem` + handler `/inventory` или `/enchant` + локали; см. [`development_plan.md`](development_plan.md) §6.3.4).
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Текущий PR — 3.3-C (боевая механика + завершение + scroll-drops «Рейд-босс»):** ✅ закрыт (открывается следующим коммитом).
- **Domain-слой:** новый модуль `domain/bosses/services.py` (282 строки) — чистая функция `resolve_boss_round(*, boss_player_length_cm, raiders, base_damage_cm, attack_block_coverage, random) -> BossRoundResolution`. 3 атаки босса × 2/3-block-coverage рейдеров. Deterministic by `random` (`SeededRandom(boss_fight.random_seed * 1_000_003 + boss_fight.current_round)` снаружи). + 23 unit-теста (`tests/unit/domain/bosses/test_services.py`).
- **Application-слой:** новый пакет `application/bosses/` с 2 use-case-ами:
  * `RunBossRound` (376 строк): один раунд боя; идемпотентный no-op на `FINISHED`/`CANCELLED`; деструктивный на `LOBBY`; happy-path → урон + audit `BOSS_FIGHT_ROUND_RESOLVED` (idempotency-key `boss_fight_round_resolved:{id}:{round}`) + следующий tick / immediate finish. + 11 unit-тестов (`tests/unit/application/bosses/test_run_boss_round.py`).
  * `FinishBossFight` (507 строк): rewards-механика с независимым per-player роллом regular/blessed-скроллов (audit-only — реальный инвентарь в Спринте 3.4); победа рейдеров — length-grant + scroll-roll + boss victory-clamp до `victory_threshold_cm`; поражение — boss-grant `+sum(length_at_join_cm)` (raider-loss length-вычеты отложены в 3.3-D); идемпотентность по `is_terminal` + `boss_rewards_granted:{id}` UNIQUE; cancel pending tick/finish-jobs (best-effort cleanup); audit `BOSS_FIGHT_FINISHED` + агрегатный `BOSS_REWARDS_GRANTED`. + 17 unit-тестов (`tests/unit/application/bosses/test_finish_boss_fight.py`).
  * 2 новых input-DTO (`RunBossRoundInput`, `FinishBossFightInput`) в `application/dto/inputs.py`.
- **Domain-слой (расширения):** `domain/shared/ports/audit.py` +1 `AuditAction.SCROLL_DROP` (whitelist) — комментарий явно фиксирует что это audit-only до Спринта 3.4 «Заточка предметов».
- **Архитектурный гард:** `tests/unit/architecture/test_length_grant_guard.py` +`application/bosses/finish_boss_fight.py` в `_ALLOWED_FILES` для прямого `Player.with_length(...)` (refund-к-самому-себе при victory-clamp; обоснование симметрично `pvp/apply_mass_outcome.py` и `caravans/finish_caravan_battle.py`).
- **DI:** `bot/main.py` подключил `RunBossRound` + `FinishBossFight` в `Container` (фикстура `_container_with_fakes()` в `tests/unit/bot/test_composition_root.py` тоже расширена). APScheduler-фабрики `boss_round_tick_factory` + `boss_fight_finish_factory` остаются `None` до 3.3-D.
- **Тесты:** total `make ci` — **4308 passed / 2 skipped, coverage 95.60%** (gate 80%). +28 unit-тестов use-case-ов (11 + 17) + 23 unit-теста доменного сервиса.
- **UI / handler-ы / локали / APScheduler factory-wiring / `CancelBossFight` / raider-loss-вычеты / integration-тест частот scroll-drop-а — отсутствуют, перенесены в 3.3-D** (закрытие Спринта 3.3).

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Raider-loss length-вычеты — отложены в 3.3-D.** При поражении рейдеров на 3.3-C их `Player.length` не уменьшается (только босс получает grant `+sum(length_at_join_cm)`). UI «вы проиграли» с раскрытием убытков и реальные length-вычеты — в 3.3-D вместе с handler-ами и локалями. Решение cyan91 при ревью 3.3-C-сетапа.
- **Integration-тест частот scroll-drop-а — отложен в 3.3-D.** Критерий ПД §3.3.6 («integration: 100 рейдов × 5 игроков, частоты в границах») требует APScheduler-фабрик с реальными callback-ами, которые на 3.3-C ещё `None`. На 3.3-C критерий частично покрыт unit-тестами через `FakeRandom` с известным seed-ом (deterministic frequencies).
- **`AuditAction.SCROLL_DROP` сейчас audit-only.** До Спринта 3.4 «Заточка предметов» дроп-скроллов **только** в `audit_log` пишется (не накапливается в инвентаре игрока). После 3.4 этот же event начнёт сопровождаться реальной записью в `inventory.scrolls`. Симметрично `PveScrollDrop` из 3.1-D.
- **`bot_play_chance=1.0`** (config, по `cyan91`-решению) — в 3.3-C summoner-AFK = бот ролит. Реальная presence-логика «summoner online» — в 3.3-D вместе с bot-handler-ами (или может остаться stub до более позднего спринта).
- **`CancelBossFight`** — отмена boss_fight саммонером. Audit-action `BOSS_FIGHT_CANCELLED` уже whitelist-нут в 3.3-B; use-case будет в 3.3-D (одновременно с handler-ом отмены).

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`a140048` — `feat(3.3-C): DI-wire RunBossRound + FinishBossFight in Container (C.8)` (последний коммит перед docs-коммитом C.13).
