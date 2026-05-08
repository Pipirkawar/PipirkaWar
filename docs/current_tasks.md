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

**На `main`:** последний смерженный PR — **3.3-A** (PR #112, `dbb9b1c`) — каркас доменов «Рейд-босс». `domain/bosses/` (entities `BossFight`/`BossParticipant`, enums `BossKind`/`BossFightStatus`, VO `BossDamage`, ошибки `BossError`+8 subclasses, порты `IBossFightRepository`/`IBossParticipantRepository`). `BossesConfig` + `BossScrollDropConfig` в pydantic-схеме баланса. Секция `bosses:` в `config/balance.yaml` (12 параметров). Юнит-тесты по entities/VO/errors/ports + balance-config. **6 балансовых решений зафиксированы с `cyan91`.** Use-case-ы / persistence / миграция / bot-handlers / UI — следующие PR-ы (3.3-B/C/D).

**В работе (этот PR; ветка `devin/1778248645-sprint-3-3-B-boss-usecases-persistence`)** — **Спринт 3.3-B: use-cases + persistence + миграция «Рейд-босс»**. По образцу 3.2-B (караван): расширяем `application/dto/inputs.py` под DTO-ы рейд-босса (`SummonBossInput`/`JoinBossLobbyInput`/`LeaveBossLobbyInput`/`CloseBossLobbyInput`); расширяем `domain/shared/ports/audit.py` под `BOSS_FIGHT_*` audit-actions; расширяем `domain/shared/ports/scheduler.py` под `schedule_boss_lobby_close`/`cancel_boss_lobby_close`/`schedule_boss_fight_finish`/`cancel_boss_fight_finish`/`schedule_boss_round_tick`/`cancel_boss_round_tick`. Реализуем use-case-ы `application/bosses/{summon_boss,join_boss_lobby,leave_boss_lobby,close_boss_lobby}.py` (по 3.2-B-паттерну: ambient-UoW, валидации gate-ов, activity-lock, audit-запись, scheduler-постановка). Миграция `0020_boss_fights` (таблицы `boss_fights` + `boss_participants`). SQLAlchemy-репо `SqlAlchemyBossFightRepository` + `SqlAlchemyBossParticipantRepository`. APScheduler-фабрики `boss_lobby_close_factory`/`boss_round_tick_factory`/`boss_fight_finish_factory` (с `factory=None` дефолтами до 3.3-D). DI-провязка в `bot/main.py`. Юнит-тесты use-case-ов + integration-тест миграции/репо. Боевая механика (raund resolve, scroll-drops, награды) — следующий PR (3.3-C); bot-handlers + UI + локали — 3.3-D.

Перед ним: **3.3-A** (PR #112, `dbb9b1c`) — каркас доменов «Рейд-босс». Перед ним: **3.2-D** (PR #111, `89e4f0a`) — bot-handlers `/caravan` + lobby-UI + презентеры + локали + APScheduler factory-wiring (закрытие Спринта 3.2). Перед ним: **3.2-C** (PR #110, `2333297`) — боевая механика каравана. Перед ним: **3.2-B** (PR #109, `e27968b`) — use-case-ы каравана + миграция `0019_caravans`. Перед ним: **3.2-A** (PR #108, `fe959c6`) — каркас доменов «Караван». Перед ним: **3.1-E** (PR #107, `5c1b26f`) — bot-handlers `/mountains` + `/dungeon` (закрытие Спринта 3.1). Перед ним: **catch-up docs 3.1-D** (PR #106, `76af44a`). Перед ним: **3.1-D** (PR #105, `2208ae6`). Перед ним: **3.1-C** (PR #103). Перед ним: **3.1-B** (PR #101). Перед ним: **3.1-A** (PR #99). Перед ним: PR-ы Спринта 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а: 3.2-A → 3.2-D). **Активный — Спринт 3.3 «Рейд-боссы»** ([`development_plan.md`](development_plan.md) §6.3.3); этот PR — второй из 4 (3.3-A → 3.3-D).

**Активная feature-ветка:** `devin/1778248645-sprint-3-3-B-boss-usecases-persistence` — use-cases + persistence + миграция (этот PR). После мерджа этого PR-а следующий агент создаст ветку под **3.3-C** (боевая механика + завершение + scroll-drops).

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
- **3.3-B — Use-cases + persistence + миграция.** ⏳ Этот PR. `application/bosses/`: `SummonBoss` (lvl 9+ gate, ≥ 20 см gate, глобальный кулдаун 4 ч через `IBossFightRepository.get_last_global_started_at`, выбор случайного из топ-30 через `IPlayerRepository.list_top_by_length`, activity-lock саммонера), `JoinBossLobby` (lvl 4+, ≥ 20 см, проверка «не саммонер/босс»), `LeaveBossLobby` (освобождение activity-lock рейдера), `CloseBossLobby` (LOBBY → IN_BATTLE, идемпотентен, шедулит `boss_round_tick` + `boss_fight_finish`). Миграция `0020_boss_fights` (таблицы `boss_fights` + `boss_participants`). SQLAlchemy-репо. APScheduler-job-ы `boss_lobby_close_factory` + `boss_round_tick_factory` + `boss_fight_finish_factory` (фабрики `None` до 3.3-D).
- **3.3-C — Боевая механика + завершение + scroll-drops.** Чистый доменный сервис `boss_round_resolution` (boss attacks vs raider blocks, deterministic by seed). Use-case `RunBossRound` интегрирует с `IRandom`. Use-case `FinishBossFight` распределяет награды + per-player ролл скроллов через `IRandom` (обычный + blessed; idempotency-key `(boss_fight_id, player_id, scroll_kind)`). Audit-actions `BOSS_FIGHT_*`. Архитектурный гард `test_length_grant_guard.py` whitelist-нёт нужные модули. **Критично:** интеграционный тест на 100 рейдов × 5 игроков с проверкой частот скролл-дропа в границах толерантности.
- **3.3-D — Bot-handlers `/raid_boss` (или `/boss`) + лобби UI + презентеры + локали + APScheduler factory-wiring.** По образцу 3.1-E / 3.2-D: handler `/boss` в личке (lvl 9+, ≥ 20 см, 1/4 ч cooldown); inline-кнопки «вступить» + пересылаемая кнопка; `BossPresenter`; локали `bosses-*` (RU+EN parity); APScheduler-фабрики; DI-wiring; нотификаторы для round-tick / fight-finish; manual smoke-тест.

**Финальный коммит каждого PR-а Спринта 3.3** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.3-X: ...») + пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния>`, передвинуть чек-лист на следующий PR (или закрыть Спринт 3.3 на 3.3-D и расписать чек-лист **первого PR-а Спринта 3.4** «Заточка предметов» по [`development_plan.md`](development_plan.md) §6.3.4).

---

## 📝 Чек-лист следующего PR (Спринт 3.3-B — Use-cases + persistence + миграция)

> Этот PR — второй PR Спринта 3.3. Он приземляет use-case-ы стадии «лобби» (`SummonBoss`/`JoinBossLobby`/`LeaveBossLobby`/`CloseBossLobby`), миграцию `0020_boss_fights` + persistence + APScheduler-фабрики (без notifier-ов до 3.3-D). Боевой resolve + награды + scroll-drops — следующий PR (3.3-C).

- [x] Дождаться мерджа `main = dbb9b1c` (PR #112; 3.3-A).
- [x] `git fetch && git checkout main && git pull`.
- [x] `make ci` локально на свежем `main`: ✅ зелёный (4162 passed / 1 skipped, coverage 95.66%).
- [x] Создать ветку `devin/1778248645-sprint-3-3-B-boss-usecases-persistence` от `main`.
- [x] **B.0 — Обновить `current_tasks.md`** под старт Спринта 3.3-B (этот коммит).
- [ ] **B.1 — DTO inputs** (`application/dto/inputs.py`): `SummonBossInput`, `JoinBossLobbyInput`, `LeaveBossLobbyInput`, `CloseBossLobbyInput`. Pydantic-валидаторы — strict, frozen, extra=forbid.
- [ ] **B.2 — Audit-actions** (`domain/shared/ports/audit.py`): добавить `BOSS_FIGHT_SUMMONED`, `BOSS_FIGHT_STARTED`, `BOSS_FIGHT_ROUND_RESOLVED`, `BOSS_FIGHT_FINISHED`, `BOSS_REWARDS_GRANTED`, `BOSS_FIGHT_CANCELLED`, `BOSS_RAIDER_JOINED`, `BOSS_RAIDER_LEFT`. Whitelist `audit_log.action`.
- [ ] **B.3 — Scheduler ports** (`domain/shared/ports/scheduler.py`): расширить `IDelayedJobScheduler` методами `schedule_boss_lobby_close`/`cancel_boss_lobby_close`/`schedule_boss_fight_finish`/`cancel_boss_fight_finish`/`schedule_boss_round_tick`/`cancel_boss_round_tick`.
- [ ] **B.4 — Use-case `SummonBoss`** (`application/bosses/summon_boss.py`): lvl 9+ gate, ≥ 20 см gate, глобальный 4-часовой cooldown через `IBossFightRepository.get_last_global_started_at`, выбор `boss_player_id` случайно из `IPlayerRepository.list_top_by_length(limit=top_n_pool)` (исключая саммонера; `BossPlayerPoolEmptyError` если пул пуст), activity-lock саммонера, audit `BOSS_FIGHT_SUMMONED`, шедул `schedule_boss_lobby_close`.
- [ ] **B.5 — Use-case `JoinBossLobby`** (`application/bosses/join_boss_lobby.py`): lvl 4+, ≥ 20 см, проверка `not in (summoner, boss)`, проверка `BossFightLobbyClosedError` (only LOBBY), идемпотентен на повторный join, activity-lock рейдера, audit `BOSS_RAIDER_JOINED`.
- [ ] **B.6 — Use-case `LeaveBossLobby`** (`application/bosses/leave_boss_lobby.py`): только из LOBBY, снятие activity-lock рейдера. Идемпотентно если игрок уже не в лобби (NO-OP). Audit `BOSS_RAIDER_LEFT`.
- [ ] **B.7 — Use-case `CloseBossLobby`** (`application/bosses/close_boss_lobby.py`): LOBBY → IN_BATTLE, идемпотентен (NO-OP если уже не LOBBY); шедулит `schedule_boss_round_tick` + `schedule_boss_fight_finish` после успешного перехода; audit `BOSS_FIGHT_STARTED`.
- [ ] **B.8 — SQLAlchemy ORM** (`infrastructure/db/models/boss.py`): `BossFightORM` + `BossParticipantORM`, CHECK-инварианты status / temporal-monotonicity / finished_at-consistency, indices для cooldown-сканирования (`status`, `started_at`), partial-unique «один активный fight глобально».
- [ ] **B.9 — Alembic migration `0020_boss_fights`**: `down_revision='0019_caravans'`, upgrade/downgrade, FK, CHECK + indices аналогичные ORM-модели.
- [ ] **B.10 — SQLAlchemy-репо** (`infrastructure/db/repositories/boss_fight.py` + `boss_participant.py`): реализация `IBossFightRepository` + `IBossParticipantRepository`. `_row_to_entity`-helper-ы. `IntegrityError`-конверсия из SQLAlchemy в доменный `IntegrityError`.
- [ ] **B.11 — APScheduler factories** (`infrastructure/scheduler/aps.py`): `boss_lobby_close_factory` + `boss_round_tick_factory` + `boss_fight_finish_factory` (фабрики `None` до 3.3-D), методы `schedule_boss_lobby_close`/`cancel_*`/`schedule_boss_fight_finish`/`cancel_*`/`schedule_boss_round_tick`/`cancel_*`.
- [ ] **B.12 — DI-провязка** (`bot/main.py`): добавить `IBossFightRepository`/`IBossParticipantRepository` в контейнер; `SummonBoss`/`JoinBossLobby`/`LeaveBossLobby`/`CloseBossLobby` в контейнер (без bot-handler-ов; те — 3.3-D).
- [ ] **B.13 — Push checkpoint** на `origin` для непрерывности.
- [ ] **B.14 — Юнит-тесты use-case-ов** (`tests/unit/application/bosses/test_*.py`): happy-path + 1 кейс на каждую гейт-ошибку. Fakes `tests/fakes/boss_fight_repo.py` + расширения `delayed_job_scheduler.py`.
- [ ] **B.15 — Integration-тест миграции** (`tests/integration/db/test_boss_fights_migration.py`): миграция up/down + CRUD + UNIQUE-инварианты.
- [ ] **B.16 — `make ci` локально:** ruff / mypy --strict / import-linter / pytest / coverage gate (≥ 80%).
- [ ] **B.17 — Финальный док-коммит:** `history.md` +запись 3.3-B, `current_tasks.md` пересборка под старт Спринта 3.3-C (боевая механика + завершение + scroll-drops).
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Текущий PR — 3.3-B (use-cases + persistence + миграция «Рейд-босс»):**
- В работе. На момент создания ветки изменён только этот файл (`docs/current_tasks.md`).
- **Дальше идёт:** расширение портов (audit + scheduler), DTO, четыре use-case-а (`SummonBoss`/`JoinBossLobby`/`LeaveBossLobby`/`CloseBossLobby`), ORM-модели + миграция + репо, APScheduler-адаптер, DI-провязка, юнит- и integration-тесты.
- **Бизнес-логика боя отсутствует.** Resolve рейда + награды + scroll-drops — Спринт 3.3-C; bot-handlers и UI — 3.3-D.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Глобальный 4-часовой кулдаун — реализация.** В 3.3-A зафиксировали, что кулдаун — глобальный per-server. В 3.3-B реализуется простым SQL-запросом `MAX(started_at)` по `boss_fights` (без распределённого Redis-lock-а — пока MVP-уровень и единственный инстанс воркера). Если в будущем поедем на multi-worker, нужен distributed lock с retry-логикой.
- **Выбор «боса из топ-30».** Используем существующий `IPlayerRepository.list_top_by_length(limit=cfg.top_n_pool)`. Исключаем саммонера из выборки в use-case-е. Если пул < 1 (только саммонер в топе) → `BossPlayerPoolEmptyError`. Никаких новых query-портов не вводим.

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`dbb9b1c` — `Merge pull request #112 from Pipirkawar/devin/1778246149-sprint-3-3-A-boss-domain` (старт ветки 3.3-B; будет обновлён первым коммитом B.0).
