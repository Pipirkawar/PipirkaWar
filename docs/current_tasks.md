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

**На `main`:** последний смерженный PR — **3.1-C** ([PR #103](https://github.com/Pipirkawar/PipirkaWar/pull/103), коммит `1ae81ab`) — дроп оружия: `items_catalog` +10 позиций (по 5 на `right_hand` и `left_hand`), `slot_weights` per-location (forest: оружие=0; mountains/dungeon: оружие активно), общий picker `pick_drop_item_entry` в `domain/balance/picking.py`, +кросс-валидатор `_validate_drop_slot_rarity_coverage`. 3 коммита на feature-ветке: `803ab4e` (C.1+C.2+C.3 — schema +10 weapons +slot_weights) → `463b512` (C.4+C.5 — drop-engine refactor через общий хелпер) → `9255e08` (C.6 — 1000+ rolls тесты per location).

Перед ним: **postmerge 3.1-B** (PR #102, `1f7fc1e`) — docs-only sync `history.md` + `current_tasks.md`. Перед ним: **3.1-B** (PR #101, `5f25ca0`) — use-cases `Start/Finish{Mountain,Dungeon}Run` + persistence (миграция `0018_pve_runs`, `SqlAlchemy{Mountain,Dungeon}RunRepository`) + DI-wiring. Перед ним: postmerge 3.1-A (PR #100, `76c83a0`); 3.1-A (PR #99, `7a37071`) — каркас доменов гор и данжона + общий picker `pick_pve_outcome` + 75 unit-тестов; docs-prep 3.1 (PR #98, `71a667e`) — декомпозиция Спринта 3.1 на 5 фичевых PR-ов. До этого — закрытие Спринта 2.5: PR #97/#96/#95/#94/#93/#92/#91/#90/#89/#88/#86/#87/#85/#84/#83/#81/#79.

**Активная feature-ветка:** `devin/1778183461-postmerge-3-1-C` (создана от `main = 1ae81ab`). Это **последний** postmerge-PR по старому канону. После его мерджа все будущие spринты будут синхронизировать docs внутри фичевого PR (см. правило в `CONTRIBUTING.md`).

**Что уже есть в коде на момент старта 3.1-D (`main = 1ae81ab`, после мерджа 3.1-C):**
- **§8 «Походы (PvE)» ГДД — domain-слой полностью готов** (3.1-A + 3.1-C):
  - `src/pipirik_wars/domain/pve/`: `PveLocationKind` (mountains/dungeon), `PveOutcomeBranch`, `PveItemDrop`, `PveRunOutcome` с invariant-проверками `sign↔delta`. `services.py::pick_pve_outcome` — общий picker веток + Bernoulli per-slot для дропов + теперь использует `pick_drop_item_entry` для выбора конкретного предмета.
  - `src/pipirik_wars/domain/{mountains,dungeon}/`: `MountainRun`/`DungeonRun` + `IMountainRunRepository`/`IDungeonRunRepository` + ошибки.
  - `src/pipirik_wars/domain/balance/`:
    - `config.py`: `Slot` enum (8 слотов), `Rarity`, `ItemEntry`, `BalanceConfig`, `ForestConfig`, `MountainsConfig`, `DungeonConfig`, `ForestDropConfig`/`PveDropConfig` с `slot_weights: SlotWeights`, кросс-валидаторы (включая `_validate_drop_slot_rarity_coverage`).
    - `picking.py` (новое в 3.1-C): `pick_drop_item_entry(*, balance, slot_weights, rarity_weights, random)` — общий хелпер для forest и pve, шаги «slot → rarity → item» с фильтрацией нулевых весов.
- **§8 «Походы (PvE)» ГДД — application-слой готов для гор и данжона** (3.1-B):
  - `src/pipirik_wars/application/{mountains,dungeon}/`: use-cases `Start*Run`/`Finish*Run` с hardcap-каноном через `progression.add_length(...)`, `LENGTH_REVOKE` для отрицательных исходов, activity-lock через `LockReason.MOUNTAINS`/`DUNGEON`, idempotency-keys, `scheduler.schedule/cancel_finish_{mountain,dungeon}_run(...)`.
- **§8 «Походы (PvE)» ГДД — лес (forest)** реализован полностью с предыдущих спринтов: `domain/forest/` + `application/forest/` + persistence (миграция `0004_forest_runs`) + `bot/handlers/forest.py` + `bot/presenters/forest.py` + templates `forest_logs_{ru,en}.json`.
- **Persistence гор/данжона** (3.1-B):
  - **Миграция `0018_pve_runs`** — таблицы `mountain_runs` и `dungeon_runs` с CHECK-инвариантами (`audit_log_source_whitelist` расширен — `mountains`, `dungeon`).
  - SQLAlchemy-модели `MountainRunORM`/`DungeonRunORM` (`infrastructure/db/models/pve_runs.py`).
  - `SqlAlchemy{Mountain,Dungeon}RunRepository` с JSON-сериализацией drops + integration round-trip.
- **DI-wiring** (3.1-B): Container в `bot/main.py` получает 6 новых полей (2 репозитория + 4 use-case-а).
- **`config/balance.yaml`:**
  - `forest:` (3 ветки исходов все +) + `mountains:` (5 веток) + `dungeon:` (5 веток).
  - `items_catalog`: 40 предметов на 8 слотов (3.1-C добавил 10 weapons).
  - `slot_weights` per-location: forest (right_hand/left_hand = 0), mountains (right_hand/left_hand = 14), dungeon (right_hand/left_hand = 20).
  - `thickness.unlock_levels`: `mountains: 3`, `dungeon: 6`, `caravan_raider: 5`, `caravan_create: 7`, `raid_summon: 9`.
- **Anti-cheat hardcap** (ГДД §3.3): organic-источники проходят через `progression.add_length(...)`. Закреплено в `tests/unit/architecture/test_length_grant_guard.py`.
- **APScheduler-callback factories для гор и данжона — stub-и** (factory-wiring `mountain_finish_factory`/`dungeon_finish_factory` будет в 3.1-E с bot-handler-ами).
- **Bot-handler-ов `/mountains` и `/dungeon` нет** — это **3.1-E**.
- **Тесты RBAC + lint-тест локалей** на месте (2.5-D.11/D.12).
- **Скроллов заточки в коде ещё нет** — это **3.1-D** (текущий следующий PR).

**Скоуп Спринта 3.1 (план PR-ов — детали в `docs/development_plan.md` §6.3.1+):**
- **Цель спринта** (ГДД §8.1 / `development_plan.md` §6.3 Спринт 3.1, задачи 3.1.1–3.1.5): добавить две оставшиеся PvE-локации — `/mountains` (lvl 3+, ≥ 20 см, 20–40 мин, ±длина, 0–1 предмет) и `/dungeon` (lvl 6+, ≥ 20 см, 40–60 мин, ±длина, 0–3 предмета). Дроп оружия в обе локации. Дроп скроллов заточки (skeleton — дроп без use-механики, та переедет в Спринт 3.4). Балансировка через `balance.yaml` (без релиза кода).
- **План PR-ов** (5 фичевых):
  1. **3.1-A** ✅ (PR #99, `7a37071`) — Каркас доменов + балансовый конфиг + общий picker.
  2. **3.1-B** ✅ (PR #101, `5f25ca0`) — Use-cases `Start*Run`/`Finish*Run` + persistence + Alembic-миграция + DI.
  3. **3.1-C** ✅ (PR #103, `1ae81ab`) — Дроп оружия (`right_hand`/`left_hand`) — расширение `items_catalog` + pydantic-валидатор + per-location `slot_weights` + общий picker `pick_drop_item_entry`.
  4. **3.1-D** ⏳ (следующий) — Дроп скроллов заточки (skeleton, без use-механики).
  5. **3.1-E** — Bot-handlers `/mountains`, `/dungeon` + презентеры + локали + APScheduler factory-wiring.

**Текущий PR (postmerge 3.1-C):** docs-only — `history.md` +1 запись о PR #103 + `current_tasks.md` sync под `main = 1ae81ab` и старт 3.1-D + правка `CONTRIBUTING.md` (упразднение отдельного postmerge-PR на будущее). Без изменений кода / тестов / локалей / миграций / `balance.yaml`. **Это последний postmerge-PR такого типа.**

**`make ci` локально на `main = 1ae81ab` (база этой ветки):** ожидаемо зелёный — **3583 passed / 1 skipped**, coverage **95.87%**, ruff / mypy --strict (735 файлов, 0 issues) / import-linter (3/3 contracts kept) — clean, ~3:02.

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `3.1 — Горы и данжон` (см. `docs/development_plan.md` §6 / Спринт 3.1, задачи 3.1.1–3.1.5; ГДД §8 «Походы (PvE)») |
| **Активный PR / шаг** | **postmerge 3.1-C** (docs-only, **последний postmerge-PR**) — `docs/history.md` +1 запись о PR #103 (3.1-C feature) + полная пересборка `docs/current_tasks.md` под `main = 1ae81ab` и старт **3.1-D** + правка `CONTRIBUTING.md` (новое правило: history.md/current_tasks.md обновляются внутри фичевого PR). Следующий фичевый PR — 3.1-D (дроп скроллов заточки skeleton). |
| **Активная feature-ветка** | `devin/1778183461-postmerge-3-1-C` (создана от `main = 1ae81ab`) |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `1ae81ab` (мерж PR #103 «3.1-C: дроп оружия — items_catalog +10 позиций, slot_weights per-location, 0..N drops») |
| **Последний коммит на feature-ветке** | _будет проставлен после первого коммита postmerge_ |
| **PR (если открыт)** | _будет открыт сразу после первого пуша и локального зелёного `make ci`_ |
| **CI статус** | на `main = 1ae81ab` зелёный (baseline для docs-only PR-а): `make ci` — 3583 passed / 1 skipped, coverage 95.87% |
| **Связанная задача в `development_plan.md`** | §6 / Спринт 3.1 / задача 3.1.3 (дроп скроллов заточки — следующий PR 3.1-D); §6.3.1+ строка 3.1-D («Дроп скроллов — domain VO `Scroll` skeleton + drop-engine»). |
| **Связанная спецификация в `game_design.md`** | §2.7 «Заточка экипировки» — категории скроллов (regular/blessed); §3.4 «Скроллы как механика» — full impl будет в Спринт 3.4; §8 «Походы (PvE)» — таблица локаций. |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист.

**Текущий PR — postmerge 3.1-C (docs-only sync `history.md` + `current_tasks.md` под `main = 1ae81ab` + правка `CONTRIBUTING.md`):**

- [x] Мердж 3.1-C в `main` (коммит `1ae81ab`, [PR #103](https://github.com/Pipirkawar/PipirkaWar/pull/103)).
- [x] `git fetch && git checkout main && git pull` — получить `main = 1ae81ab`.
- [x] Создать ветку `devin/1778183461-postmerge-3-1-C` от `main`.
- [x] **`docs/history.md`** — добавить запись сверху: «Спринт 3.1-C: дроп оружия — `items_catalog` +10 позиций, `slot_weights` per-location, 0..N drops» (PR #103, `1ae81ab`); описание скоупа (3 чекпоинт-коммита), артефактов, архитектурных решений (общий picker, фильтрация нулевых весов, кросс-валидатор coverage).
- [x] **`docs/current_tasks.md`** — пересборка: «Снимок состояния» под `main = 1ae81ab`; «Текущая позиция» под текущую feature-ветку postmerge-3-1-C; чек-лист postmerge-PR-а; ссылка на скоуп 3.1-D из `development_plan.md` §6.3.1+. Спринт-план обновлён — 3.1-A/B/C отмечены `[x]`.
- [x] **`CONTRIBUTING.md`** — новое правило: `history.md` и `current_tasks.md` обновляются внутри фичевого PR последним коммитом; отдельный postmerge-PR упразднён. Соответствующие правки: таблица «Какие документы живые», «Жёсткие правила», «Перед мерджем PR-а» (новая секция), Workflow PR-а (шаг 7), «После мерджа PR-а» (упрощено).
- [ ] `make ci` локально после правок — должен оставаться зелёным (3583 passed / 1 skipped, coverage 95.87%, без изменений в коде).
- [ ] Закоммитить + запушить на origin одним коммитом `docs(postmerge 3.1-C): history.md +1, current_tasks.md sync под main = 1ae81ab; CONTRIBUTING: упразднить отдельный postmerge-PR`.
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного CI.

**После мерджа этого postmerge-PR-а — старт 3.1-D (дроп скроллов заточки) на новой feature-ветке. Это будет первый PR по новому канону: docs-обновления внутри фичевого PR последним коммитом.**

**Спринт 3.1 — план фичевых PR-ов (референс — детали в `docs/development_plan.md`, под-секция «6.3.1+ Декомпозиция Спринта 3.1 на PR-ы»):**

- [x] **3.1-A — Каркас доменов гор и данжона + балансовый конфиг.** [PR #99, `7a37071`] Реализовано: `domain/pve/` + `domain/{mountains,dungeon}/` + секции `mountains:`/`dungeon:` в `balance.yaml` + **+75 unit-тестов** (1000-rolls stress-тесты на каждую локацию). Покрывает: 3.1.1 (домен), 3.1.2 (домен), 3.1.5 (схемы).
- [x] **3.1-B — Use-cases `Start*Run`/`Finish*Run` + persistence + миграция.** [PR #101, `5f25ca0`] Реализовано: `application/{mountains,dungeon}/` (use-cases с hardcap-каноном и idempotency); миграция `0018_pve_runs`; SQLAlchemy-модели `MountainRunORM`/`DungeonRunORM`; `SqlAlchemy{Mountain,Dungeon}RunRepository` + integration round-trip; audit/security/scheduler-фундамент. DI-wiring в `bot/main.py`. **+~290 unit/integration-тестов**. Покрывает: 3.1.1, 3.1.2 (use-case + persistence).
- [x] **3.1-C — Дроп оружия (`right_hand`/`left_hand`) — drop-engine + items_catalog.** [PR #103, `1ae81ab`] Реализовано: `Slot` enum 6→8; `SlotWeights` model; +10 weapons в `items_catalog` (40 предметов всего); `slot_weights` per-location; новый picker `pick_drop_item_entry` (общий для forest/pve); кросс-валидатор `_validate_drop_slot_rarity_coverage`. **+12 unit-тестов** (10 в `test_picking.py` + 2 обновлённых в forest/pve). Покрывает: 3.1.4, 3.1.5 (items_catalog).
- [ ] **3.1-D — Дроп скроллов заточки (skeleton, без use-механики).** Domain VO `Scroll(category, blessed)` (skeleton; полная impl механики применения скролла — Спринт 3.4). Drop-engine ветки `scroll_drop_regular`/`scroll_drop_blessed` (или интеграция в `pick_pve_outcome` через расширение `PveDropConfig`). Конфиг `enchantment.scroll_drops_per_location` (mountains: regular only; dungeon: regular + blessed). Юнит-тесты 1000+ rolls. Покрывает: 3.1.3, 3.1.5 (enchantment skeleton).
- [ ] **3.1-E — Bot-handlers `/mountains`, `/dungeon` + презентеры + локализация.** Тонкий aiogram-слой по образцу `bot/handlers/forest.py`. Локали `mountains-*`/`dungeon-*` (RU+EN, parity автомат). Карточка возврата + кнопки «надеть/выбросить» × N. Расширение lint-теста локалей. APScheduler factory-wiring `mountain_finish_factory`/`dungeon_finish_factory`. Manual smoke-тест в боте. Покрывает: 3.1.1 (UX), 3.1.2 (UX).

**После 3.1-E** — закрытие Спринта 3.1: финальная запись в `docs/history.md` + обновление `docs/current_tasks.md` под старт Спринта 3.2 (Караваны) **внутри самого 3.1-E PR-а** (по новому канону).

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Текущий PR — postmerge 3.1-C (docs-only sync + правка протокола):**
- **`docs/history.md`** — добавлена запись «Спринт 3.1-C: дроп оружия — `items_catalog` +10 позиций, `slot_weights` per-location, 0..N drops» сверху (после format-блока). Описаны: 3 чекпоинт-коммита (`803ab4e`, `463b512`, `9255e08`), 10 файлов / +688 −52 строки, ключевые архитектурные решения (общий picker `pick_drop_item_entry`, фильтрация нулевых весов в `weighted_choice`, кросс-валидатор `_validate_drop_slot_rarity_coverage`, расширение Slot enum 6→8).
- **`docs/current_tasks.md`** — полная пересборка: «Снимок состояния» под `main = 1ae81ab`, «Текущая позиция» с `devin/1778183461-postmerge-3-1-C`, чек-лист postmerge-PR-а, ссылка на скоуп 3.1-D из `development_plan.md` §6.3.1+. Спринт-план обновлён — 3.1-A/B/C отмечены `[x]` со ссылками на PR-ы.
- **`CONTRIBUTING.md`** — новое правило (4 правки): `history.md` и `current_tasks.md` обновляются **внутри фичевого PR** последним коммитом перед мерджем; отдельный postmerge-PR **не открывается** начиная с 3.1-D. Это сэкономит по 1 PR на каждый спринт.
- **Без изменений в коде / тестах / локалях / миграциях / `balance.yaml`.** PR docs-only.
- `make ci` ожидаемо без изменений от baseline (3583 passed / 1 skipped, coverage 95.87%).

**Следующий PR (после мерджа этого) — 3.1-D (дроп скроллов заточки skeleton, по новому канону):**
- Завести ветку `devin/<unix_ts>-sprint-3-1-D-scroll-drops` от `main` (после мерджа postmerge).
- **Domain `Scroll`** (skeleton, без use-механики): `src/pipirik_wars/domain/enchantment/entities.py` — VO `Scroll(category: ScrollCategory, blessed: bool)`. `ScrollCategory` enum (для 3.1.3 — `regular`/`blessed`; полный набор категорий — спринт 3.4). Frozen, hash, equality.
- **`config/balance.yaml`** — секция `enchantment:` с `scroll_drops_per_location`:
  - `mountains: { regular_chance_percent: <X>, blessed_chance_percent: 0 }` (только regular).
  - `dungeon: { regular_chance_percent: <Y>, blessed_chance_percent: <Z> }` (regular + blessed).
  - `forest: { regular_chance_percent: 0, blessed_chance_percent: 0 }` (по дизайну — лес скроллы не дропает).
- **Pydantic-схема** `ScrollDropConfig` в `domain/balance/config.py` + поле `enchantment.scroll_drops_per_location` в `BalanceConfig`. Валидаторы: 0 ≤ chance ≤ 100; sum ≤ 100 (или независимые Bernoulli — решить на старте 3.1-D).
- **Drop-engine расширение** — добавить ScrollDrop как вариант в `PveOutcome.drops` или отдельным полем `scroll_drops`. Решение: расширить existing `tuple[PveItemDrop, ...]` или ввести `PveDropOutcome = ItemDrop | ScrollDrop` union — выбрать на старте 3.1-D в зависимости от того, как будет use-mehаника в 3.4. Поведение: после Bernoulli per-slot для предметов — ещё Bernoulli per-категория-скролла.
- **Persistence** — НЕ требуется (скроллы пока в JSON-выгрузке drops, как и предметы).
- **Юнит-тесты:** 1000+ rolls per location — частоты regular/blessed within ±10% от config; контр-проверка «forest scrolls = 0»; smoke-тест на real `balance.yaml`.
- **`history.md`** + **`current_tasks.md`** — обновить **в этом же фичевом PR** (по новому правилу), последним коммитом перед мерджем.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Архитектура `ScrollDrop` vs `ItemDrop`** — open question для 3.1-D: расширить существующий `tuple[PveItemDrop, ...]` через union-тип или ввести отдельное поле `PveRunOutcome.scroll_drops: tuple[ScrollDrop, ...]`. Текущий postmerge-PR ничего не решает — выбор делается на старте 3.1-D. Связано с импортным графом (если ScrollDrop живёт в `domain/enchantment/`, то `domain/pve` начнёт от него зависеть — приемлемо, оба под `domain/`).
- **Расположение `ScrollCategory`** — `domain/enchantment/entities.py` (рекомендуется, парный к будущему домену enchantment в 3.4) vs `domain/balance/config.py` (если только конфиг). Решение — на старте 3.1-D.
- **APScheduler factory-wiring для гор/данжона** — stub до 3.1-E (там же придут bot-handler-ы). Не блокер для 3.1-D.
- Для текущего postmerge-PR-а (docs-only) блокеров **нет**.
