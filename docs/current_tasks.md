# 🍆 Пипирик Варс — Текущие задачи

> Этот файл описывает **только то, что в работе сейчас**: активная feature-ветка, активный спринт/PR, чек-лист текущих шагов и их статусы. По мере выполнения шаги отмечаются `[x]`; после мерджа PR-а соответствующая запись переносится в [`history.md`](history.md), а файл обновляется под следующий спринт.
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

**На `main`:** последний смерженный PR — **3.1-B** ([PR #101](https://github.com/Pipirkawar/PipirkaWar/pull/101), коммит `5f25ca0`) — use-cases `Start/Finish{Mountain,Dungeon}Run` + persistence (миграция `0018_pve_runs`, `SqlAlchemy{Mountain,Dungeon}RunRepository`) + DI-wiring в `bot/main.py`. 5 коммитов на feature-ветке: `5a1a411` (infra-фундамент: audit/security/scheduler + миграция) → `70ee23f` (DTOs + ORM) → `9f94951` (mountains use-cases) → `17126c2` (dungeon use-cases) → `46bad85` (Sql repos + integration round-trip) → `5b2f695` (DI). Перед ним: **postmerge 3.1-A** (PR #100, `76c83a0`) — docs-only sync `history.md` (+2 записи: 3.1 docs-prep + 3.1-A) + `current_tasks.md` под `main = 7a37071`. Перед ним: **3.1-A** (PR #99, `7a37071`) — каркас доменов гор и данжона + общий picker `pick_pve_outcome` + **75 unit-тестов** в `tests/unit/domain/{pve,mountains,dungeon}/`. Перед ним: docs-prep Спринта 3.1 (PR #98, `71a667e`) — декомпозиция Спринта 3.1 на 5 фичевых PR-ов (3.1-A…3.1-E) в `development_plan.md` §6.3.1+. До этого — закрытие Спринта 2.5: postmerge 2.5-D.12 (PR #97, `f3c3a86`); 2.5-D.12 (PR #96); postmerge 2.5-D.11 (PR #95); 2.5-D.11 (PR #94); postmerge 2.5-D.10 (PR #93); 2.5-D.10 (PR #92); postmerge 2.5-D.6 (PR #91); 2.5-D.6 (PR #90); postmerge 2.5-D.4 (PR #89); 2.5-D.4 (PR #88); 2.5-D.7 (PR #86); postmerge 2.5-D.7 (PR #87); 2.5-D часть 1 (PR #85); постмердж-доки 2.5-A/B/C (PR #84); 2.5-C (PR #83); 2.5-B (PR #81); 2.5-A (PR #79).

**Активная feature-ветка:** `devin/1778181003-postmerge-3-1-B` (создана от `main = 5f25ca0`; текущий PR — **postmerge 3.1-B** docs-only: `history.md` +1 запись о PR #101 + `current_tasks.md` sync под старт **3.1-C**). Code-/тестовых изменений в этом PR нет.

**Что уже есть в коде на момент старта 3.1-C (`main = 5f25ca0`, после мерджа 3.1-B):**
- **§8 «Походы (PvE)» ГДД — domain-слой полностью готов** (3.1-A):
  - `src/pipirik_wars/domain/pve/` — общие VO + picker:
    - `entities.py`: `PveLocationKind` (mountains/dungeon), `PveOutcomeBranch` (имя + `PveSign` + абсолютная `length_cm`), `PveItemDrop`, `PveRunOutcome` (branch + знаковая `length_delta_cm` + `tuple[PveItemDrop, ...]`) с invariant-проверкой `sign ↔ delta sign` и `|delta| == branch.length_cm`.
    - `services.py::pick_pve_outcome(*, location, balance, random)` — единственный picker, общий для гор и данжона: `weighted_choice` веток + Bernoulli per-slot для дропов + `random.choice` items_catalog по rarity.
  - `src/pipirik_wars/domain/{mountains,dungeon}/`: `MountainRun`/`DungeonRun` (frozen-dataclass + статусы) + `IMountainRunRepository`/`IDungeonRunRepository` ABC ports + ошибки.
- **§8 «Походы (PvE)» ГДД — application-слой готов для гор и данжона** (3.1-B, PR #101):
  - `src/pipirik_wars/application/{mountains,dungeon}/`: use-cases `Start*Run`/`Finish*Run`. +-исходы → `progression.add_length(...)` (hardcap-канон ГДД §3.3); −-исходы → прямая запись `player.with_length(...)` + audit `LENGTH_REVOKE` (whitelist в `length_grant_guard`-тесте). Activity-lock через `LockReason.MOUNTAINS`/`DUNGEON`. Idempotency-keys на старт/финиш/loss-revoke. `scheduler.schedule/cancel_finish_{mountain,dungeon}_run(...)` идемпотентны по `run_id`.
- **§8 «Походы (PvE)» ГДД — лес (forest)** реализован полностью с предыдущих спринтов: `domain/forest/` + `application/forest/` + persistence (миграция `0004_forest_runs`) + `bot/handlers/forest.py` + `bot/presenters/forest.py` + templates `forest_logs_{ru,en}.json`.
- **Persistence гор/данжона** (3.1-B, PR #101):
  - **Миграция `0018_pve_runs`** — таблицы `mountain_runs` и `dungeon_runs` (id, player_id, status, started_at, ends_at, branch_name, branch_sign, length_delta_cm signed, drops JSON, finished_at) с CHECK-инвариантами (status; branch_sign; sign↔delta; finished_at↔status; ends_at>started_at) + индексы (player_id, status), (status, ends_at), partial unique (player_id) WHERE status='in_progress'. `audit_log_source_whitelist` расширен — `mountains`, `dungeon`.
  - SQLAlchemy-модели `MountainRunORM`/`DungeonRunORM` (`infrastructure/db/models/pve_runs.py`).
  - `SqlAlchemy{Mountain,Dungeon}RunRepository` с JSON-сериализацией drops + integration round-trip (`tests/integration/db/test_pve_run_repositories.py`).
- **DI-wiring** (3.1-B): Container в `bot/main.py` получает 6 новых полей — 2 репозитория + 4 use-case-а.
- **`config/balance.yaml`:** есть секции `forest:` (3 ветки исходов все +) **+ `mountains:` и `dungeon:`** (по 5 веток исходов: 3 gain + 2 loss; кулдауны 20–40 мин / 40–60 мин; drop-конфиг с `max_drops=1` / `max_drops=3`). Pydantic-схемы (`MountainsConfig`/`DungeonConfig`/`PveSign` etc) — в `domain/balance/config.py`.
- **`thickness.unlock_levels`** (`config/balance.yaml`): уже содержит `mountains: 3`, `dungeon: 6`, `caravan_raider: 5`, `caravan_create: 7`, `raid_summon: 9` — пороги уровней доступа известны и используются в проверках доступа.
- **`items_catalog`** (`config/balance.yaml`): 6 слотов (`hat`/`body`/`legs`/`boots`/`ring`/`chain`), pydantic-валидатор: ≥30 предметов, уникальные `id`, ≥1 предмет на каждую редкость. **Слотов оружия (`right_hand`/`left_hand`) ещё нет** — расширение в **3.1-C** (текущий следующий PR).
- **Anti-cheat hardcap** (ГДД §3.3): реализован — organic-источники проходят через `progression.add_length(...)` с rolling 24ч / 7д. Все +-исходы гор/данжона/леса идут через тот же канал — закреплено в `tests/unit/architecture/test_length_grant_guard.py` (whitelist прямой записи длины — только revoke-сценарии и стартовые миграции).
- **APScheduler-callback factories для гор и данжона — stub-и.** `APSchedulerDelayedJobScheduler.schedule_finish_{mountain,dungeon}_run` пока логирует `factory not wired`. Полный wiring `mountain_finish_factory`/`dungeon_finish_factory` будет в Спринте **3.1-E** с bot-handler-ами (по образцу `forest_finish_factory`).
- **Bot-handler-ов `/mountains` и `/dungeon` нет** — это **3.1-E** (после 3.1-C, 3.1-D).
- **Тесты RBAC + lint-тест локалей** на месте (2.5-D.11/D.12), не относятся к 3.1, но любые новые локали `mountains-*` / `dungeon-*` будут автоматически проверяться lint-тестом `tests/unit/locales/test_admin_keys_lint.py::TestLocaleParity::test_full_parity` на симметрию RU↔EN (актуально для 3.1-E).

**Скоуп Спринта 3.1 (план PR-ов — детали в `docs/development_plan.md` §6.3.1+):**
- **Цель спринта** (ГДД §8.1 / `development_plan.md` §6.3 Спринт 3.1, задачи 3.1.1–3.1.5): добавить две оставшиеся PvE-локации — `/mountains` (lvl 3+, ≥ 20 см, 20–40 мин, ±длина, 0–1 предмет) и `/dungeon` (lvl 6+, ≥ 20 см, 40–60 мин, ±длина, 0–3 предмета). Дроп оружия в обе локации. Дроп скроллов заточки (skeleton — дроп без use-механики, та переедет в Спринт 3.4). Балансировка через `balance.yaml` (без релиза кода).
- **План PR-ов** (5 фичевых + postmerge у каждого):
  1. **3.1-A** ✅ (PR #99) — Каркас доменов + балансовый конфиг + общий picker.
  2. **3.1-B** ✅ (PR #101) — Use-cases `Start*Run`/`Finish*Run` + persistence + Alembic-миграция + DI.
  3. **3.1-C** ⏳ (следующий) — Дроп оружия (`right_hand`/`left_hand`) — расширение `items_catalog` + pydantic-валидатор + per-location `slot_weights` + множественный дроп `0..N`.
  4. **3.1-D** — Дроп скроллов заточки (skeleton) — domain VO `Scroll`, drop-engine ветки `scroll_drop_regular`/`scroll_drop_blessed`, конфиг `enchantment.scroll_drops_per_location`.
  5. **3.1-E** — Bot-handlers `/mountains`, `/dungeon` + презентеры + локали `mountains-*`/`dungeon-*` (RU+EN). Кнопки «надеть/выбросить» × N для данжона.

**Текущий PR (postmerge 3.1-B):** только доки — `history.md` +1 запись о PR #101 и `current_tasks.md` sync под `main = 5f25ca0` + старт 3.1-C. Без изменений кода / тестов / локалей / миграций.

**`make ci` локально на `main = 5f25ca0` (база этой ветки):** зелёный — **3571 passed / 1 skipped**, coverage **95.88%**, ruff / mypy --strict (725 файлов, 0 issues) / import-linter (3/3 contracts kept) — clean, ~3:26.

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `3.1 — Горы и данжон` (см. `docs/development_plan.md` §6 / Спринт 3.1, задачи 3.1.1–3.1.5; ГДД §8 «Походы (PvE)») |
| **Активный PR / шаг** | **postmerge 3.1-B** (docs-only) — `docs/history.md` +1 запись о PR #101 (3.1-B feature) + полная пересборка `docs/current_tasks.md` под `main = 5f25ca0` и старт **3.1-C**. Следующий фичевый PR — 3.1-C (дроп оружия `right_hand`/`left_hand` + расширение `items_catalog`). |
| **Активная feature-ветка** | `devin/1778181003-postmerge-3-1-B` (создана от `main = 5f25ca0`) |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `5f25ca0` (мерж PR #101 «3.1-B: use-cases `Start/Finish{Mountain,Dungeon}Run` + persistence + миграция `0018_pve_runs` + DI») |
| **Последний коммит на feature-ветке** | _будет проставлен после первого коммита postmerge_ |
| **PR (если открыт)** | _будет открыт сразу после первого пуша и локального зелёного `make ci`_ |
| **CI статус** | на `main = 5f25ca0` зелёный (baseline для docs-only PR-а): `make ci` — 3571 passed / 1 skipped, coverage 95.88% |
| **Связанная задача в `development_plan.md`** | §6 / Спринт 3.1 / задача 3.1.4 (дроп оружия — следующий PR 3.1-C); §6.3.1+ строка 3.1-C («Дроп оружия — drop-engine + items_catalog»). |
| **Связанная спецификация в `game_design.md`** | §2.6 «Экипировка» — слоты `right_hand`/`left_hand` (новые в 3.1-C); §3.1 «Правило 20 см»; §3.3 «Анти-чит хардкап»; §8 «Походы (PvE)» — таблица локаций. |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**Текущий PR — postmerge 3.1-B (docs-only sync `history.md` + `current_tasks.md` под `main = 5f25ca0`):**

- [x] Мердж 3.1-B в `main` (коммит `5f25ca0`, [PR #101](https://github.com/Pipirkawar/PipirkaWar/pull/101)).
- [x] `git fetch && git checkout main && git pull` — получить `main = 5f25ca0`.
- [x] Создать ветку `devin/1778181003-postmerge-3-1-B` от `main`.
- [x] `make ci` локально на `main = 5f25ca0` — зелёный (3571 passed / 1 skipped, coverage 95.88%).
- [x] **`docs/history.md`** — добавить запись сверху: «Спринт 3.1-B: use-cases `Start/Finish{Mountain,Dungeon}Run` + persistence + миграция `0018_pve_runs` + DI» (PR #101, `5f25ca0`); описание скоупа (5 коммитов фичи), артефактов, архитектурных решений (зеркальные модули, hardcap-канон через `add_length`, idempotency-keys, scheduler stub до 3.1-E).
- [x] **`docs/current_tasks.md`** — пересборка: «Снимок состояния» под `main = 5f25ca0`; «Текущая позиция» под текущую feature-ветку postmerge-3-1-B; чек-лист postmerge-PR-а; ссылка на скоуп 3.1-C из `development_plan.md` §6.3.1+.
- [x] `make ci` локально после правок — зелёный (3571 passed / 1 skipped, coverage 95.88%, ~3:39).
- [ ] Закоммитить + запушить на origin одним коммитом `docs(postmerge 3.1-B): history.md +1, current_tasks.md sync под main = 5f25ca0`.
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного CI.

**После мерджа этого postmerge-PR-а — старт 3.1-C (дроп оружия) на новой feature-ветке.**

**Спринт 3.1 — план фичевых PR-ов (референс — детали в `docs/development_plan.md`, под-секция «6.3.1+ Декомпозиция Спринта 3.1 на PR-ы»):**

- [x] **3.1-A — Каркас доменов гор и данжона + балансовый конфиг.** [PR #99, `7a37071`] Реализовано: `domain/pve/` + `domain/{mountains,dungeon}/` + секции `mountains:`/`dungeon:` в `balance.yaml` + **+75 unit-тестов** (1000-rolls stress-тесты на каждую локацию). Покрывает: 3.1.1 (домен), 3.1.2 (домен), 3.1.5 (схемы).
- [x] **3.1-B — Use-cases `Start*Run`/`Finish*Run` + persistence + миграция.** [PR #101, `5f25ca0`] Реализовано: `application/{mountains,dungeon}/` (use-cases с hardcap-каноном и idempotency); миграция `0018_pve_runs`; SQLAlchemy-модели `MountainRunORM`/`DungeonRunORM`; `SqlAlchemy{Mountain,Dungeon}RunRepository` + integration round-trip (446 строк); audit/security/scheduler-фундамент (4 `AuditAction`, 2 `AuditSource`, 2 `LockReason`, 4 `IDelayedJobScheduler`-метода). DI-wiring в `bot/main.py`. **+~290 unit/integration-тестов**. Покрывает: 3.1.1, 3.1.2 (use-case + persistence).
- [ ] **3.1-C — Дроп оружия (`right_hand`/`left_hand`) — drop-engine + items_catalog.** +6 позиций оружия (по 3+ на слот, по редкостям) в `items_catalog`. Расширение pydantic-валидатора (8 слотов вместо 6, инвариант ≥1 предмет на слот). `slot_weights` per-location (forest/mountains/dungeon — у каждой свой расклад) + множественный дроп `0..N` (forest/mountains: 0–1; dungeon: 0–3). Юнит-тесты 1000+ rolls. Покрывает: 3.1.4, 3.1.5 (items_catalog).
- [ ] **3.1-D — Дроп скроллов заточки (skeleton, без use-механики).** Domain VO `Scroll(category, blessed)` (skeleton; полная impl механики применения скролла — Спринт 3.4). Drop-engine ветки `scroll_drop_regular`/`scroll_drop_blessed`. Конфиг `enchantment.scroll_drops_per_location` (mountains: regular only; dungeon: regular + blessed). Юнит-тесты 1000+ rolls. Покрывает: 3.1.3, 3.1.5 (enchantment skeleton).
- [ ] **3.1-E — Bot-handlers `/mountains`, `/dungeon` + презентеры + локализация.** Тонкий aiogram-слой по образцу `bot/handlers/forest.py`. Локали `mountains-*`/`dungeon-*` (RU+EN, parity автомат). Карточка возврата + кнопки «надеть/выбросить» × N. Расширение lint-теста локалей. APScheduler factory-wiring `mountain_finish_factory`/`dungeon_finish_factory`. Manual smoke-тест в боте. Покрывает: 3.1.1 (UX), 3.1.2 (UX).

**После 3.1-E** — закрытие Спринта 3.1: postmerge-PR с финальной записью в `docs/history.md`, обновление `docs/current_tasks.md` под старт Спринта 3.2 (Караваны, см. `development_plan.md` §6 / Спринт 3.2).

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты. Не дублируй ТЗ из `development_plan.md` — пиши только то, что важно для **текущего PR**.

**Текущий PR — postmerge 3.1-B (docs-only sync):**
- **`docs/history.md`** — добавлена запись «Спринт 3.1-B: use-cases `Start/Finish{Mountain,Dungeon}Run` + persistence + миграция `0018_pve_runs` + DI» сверху (после format-блока). Описаны: 5 коммитов фичи, +41 файл / +3609 строк, ключевые архитектурные решения (зеркальные application-модули, hardcap-канон через `progression.add_length`, idempotency-keys, scheduler-stub до 3.1-E, +-исходы organic-source через `ILengthGranter`).
- **`docs/current_tasks.md`** — полная пересборка: «Снимок состояния» под `main = 5f25ca0`, «Текущая позиция» с `devin/1778181003-postmerge-3-1-B`, чек-лист postmerge-PR-а, ссылка на скоуп 3.1-C из `development_plan.md` §6.3.1+. Спринт-план обновлён — 3.1-A и 3.1-B отмечены `[x]` со ссылками на PR-ы и краткими сводками.
- **Без изменений в коде / тестах / локалях / миграциях / `balance.yaml`.** PR docs-only.
- `make ci` ожидаемо без изменений от baseline (3571 passed / 1 skipped, coverage 95.88%).

**Следующий PR (после мерджа этого) — 3.1-C (дроп оружия):**
- Завести ветку `devin/<unix_ts>-sprint-3-1-C-weapon-drops` от `main` (после мерджа postmerge).
- **`config/balance.yaml`:** добавить ≥6 позиций оружия в `items_catalog` (по 3+ на `right_hand` и `left_hand`, по редкостям `common`/`rare`/`epic`); добавить `slot_weights` per-location (forest/mountains/dungeon — каждой свой расклад, см. ГДД §2.6); расширить `drop` per-location до множественного дропа `0..N` (forest/mountains: 0–1; dungeon: 0–3 — может уже есть в `max_drops`, проверить совместимость с per-slot конфигом).
- **`infrastructure/balance/schemas.py`** + `domain/balance/config.py`: pydantic-валидатор `items_catalog` — слот может быть одним из 8 (было 6), инвариант «≥1 предмет на каждый из 8 слотов».
- **Drop-engine** (`domain/economy/` или `domain/pve/services.py`): расширение `pick_pve_outcome` для использования `slot_weights` per-location; для forest — обновить `domain/forest/services.py::pick_forest_outcome` или унифицировать через общий хелпер.
- **Юнит-тесты:** 1000+ rolls per location — проверка частот (gain/loss within ±10%, slot distribution per `slot_weights`); уникальность дроп-ID-шников за один прогон.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **`drop.slots` per-location vs общий `slot_weights`** — решение об архитектуре конфига (одна централизованная таблица в `drop:` vs встроенные в каждую локацию `forest:`/`mountains:`/`dungeon:`) откладывается на 3.1-C, см. `development_plan.md` §6.3.1+ строка 3.1-C. Текущий PR (postmerge) ничего не решает по этому пункту.
- **Унификация `pick_pve_outcome` ↔ `pick_forest_outcome`** — в 3.1-A решено держать модули отдельно. 3.1-C может потребовать общий drop-engine помощник для `slot_weights`/`max_drops` per-location (рассмотреть на старте 3.1-C, не ломая `domain/forest/services.py`).
- **APScheduler factory-wiring для гор/данжона** — stub до 3.1-E (там же придут bot-handler-ы, на которых висят callback-фабрики). Не блокер для 3.1-C/D.
- Для текущего postmerge-PR-а (docs-only) блокеров **нет**.
