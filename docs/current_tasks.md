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

**На `main`:** последний смерженный PR — **3.1-D** ([PR #105](https://github.com/Pipirkawar/PipirkaWar/pull/105), коммит `2208ae6`) — дроп скроллов заточки skeleton: domain VO `Scroll(category, blessed)` + `ScrollCategory` enum (WEAPON/ARMOR/JEWELRY), `ScrollDropConfig` (regular+blessed Bernoulli с category_weights), `PveScrollDrop` VO, `PveRunOutcome.scroll_drops` отдельным полем, `_roll_scroll_drops` + `_pick_scroll_category` в `domain/pve/services.py`. `config/balance.yaml`: mountains regular=3% / blessed=0%, dungeon regular=6% / blessed=1%. Скроллы **не persist-ятся** в Спринте 3.1-D (use-cases применения и инвентарь скроллов — Спринт 3.4). 4 коммита на feature-ветке: `7567c10` (D.1) → `732764d` (D.2) → `b04994f` (D.3) → `d47d23a` (D.4).

Перед ним: **3.1-C** (PR #103, `1ae81ab`) — дроп оружия: `items_catalog` +10 позиций, `slot_weights` per-location, общий picker `pick_drop_item_entry` + кросс-валидатор `_validate_drop_slot_rarity_coverage`. Перед ним: **postmerge 3.1-C** (PR #104, `fa0758f`) — последний postmerge-PR старого канона + правка `CONTRIBUTING.md` (упразднение отдельного postmerge-PR на будущее, начиная с 3.1-D). Перед ним: **postmerge 3.1-B** (PR #102), **3.1-B** (PR #101), postmerge 3.1-A (PR #100), 3.1-A (PR #99), docs-prep 3.1 (PR #98). До этого — закрытие Спринта 2.5: PR #97/#96/#95/#94/#93/#92/#91/#90/#89/#88/#86/#87/#85/#84/#83/#81/#79.

**Активная feature-ветка:** `devin/1778185503-postmerge-3-1-D-docs-catchup` (создана от `main = 2208ae6`). Это **разовое исключение** — catch-up docs-PR после того, как PR #105 (3.1-D) был замержен раньше, чем последний docs-коммит успел попасть в ветку. После мерджа этого catch-up-PR-а канон возвращается к норме: docs живут внутри фичевого PR последним коммитом.

**Что уже есть в коде на момент старта 3.1-E (`main = 2208ae6`, после мерджа 3.1-D):**
- **§8 «Походы (PvE)» ГДД — domain-слой полностью готов** (3.1-A + 3.1-C + 3.1-D):
  - `src/pipirik_wars/domain/pve/`: `PveLocationKind`, `PveOutcomeBranch`, `PveItemDrop`, `PveScrollDrop` (новое в 3.1-D), `PveRunOutcome` с invariant-проверками `sign↔delta` и **отдельным полем** `scroll_drops: tuple[PveScrollDrop, ...] = ()`. `services.py::pick_pve_outcome` — общий picker веток + `_roll_drops` (items) + `_roll_scroll_drops` + `_pick_scroll_category`.
  - `src/pipirik_wars/domain/{mountains,dungeon}/`: `MountainRun`/`DungeonRun` + `IMountainRunRepository`/`IDungeonRunRepository` + ошибки. **`MountainRun.starting(outcome=)` / `DungeonRun.starting(outcome=)` копируют только `outcome.drops`, не `outcome.scroll_drops`** (see ниже).
  - `src/pipirik_wars/domain/enchantment/` (новое в 3.1-D): `Scroll(category: ScrollCategory, blessed: bool)` frozen + slots. `ScrollCategory` — WEAPON/ARMOR/JEWELRY с машинными значениями `*_scroll`.
  - `src/pipirik_wars/domain/balance/`:
    - `config.py`: `Slot` (8 слотов), `Rarity`, `ItemEntry`, `BalanceConfig`, `ForestConfig`, `MountainsConfig`, `DungeonConfig`, `ForestDropConfig` (без `scroll_drops` by design), `PveDropConfig` с `slot_weights: SlotWeights` + `scroll_drops: ScrollDropConfig`, новые модели `ScrollCategoryWeights`, `ScrollDropConfig`, кросс-валидаторы (`_validate_drop_slot_rarity_coverage`, `_validate_sum_positive`).
    - `picking.py`: `pick_drop_item_entry(*, balance, slot_weights, rarity_weights, random)` — общий хелпер для forest/pve.
- **§8 «Походы (PvE)» ГДД — application-слой готов для гор и данжона** (3.1-B):
  - `src/pipirik_wars/application/{mountains,dungeon}/`: use-cases `Start*Run`/`Finish*Run` с hardcap-каноном, idempotency, activity-lock, `scheduler.schedule/cancel_finish_*`.
- **§8 «Походы (PvE)» ГДД — лес (forest)** реализован полностью с предыдущих спринтов: `domain/forest/` + `application/forest/` + persistence (миграция `0004_forest_runs`) + `bot/handlers/forest.py` + `bot/presenters/forest.py` + templates `forest_logs_{ru,en}.json`.
- **Persistence гор/данжона** (3.1-B):
  - **Миграция `0018_pve_runs`** — таблицы `mountain_runs` и `dungeon_runs`. JSON-колонка `drops` хранит только items; **scroll_drops не persist-ятся в 3.1-D** (use-cases применения скроллов и persistence — Спринт 3.4).
  - SQLAlchemy-модели `MountainRunORM`/`DungeonRunORM`.
  - `SqlAlchemy{Mountain,Dungeon}RunRepository` с JSON-сериализацией drops + integration round-trip.
- **DI-wiring** (3.1-B): Container в `bot/main.py` получает 6 новых полей (2 репозитория + 4 use-case-а).
- **`config/balance.yaml`:**
  - `forest:` (3 ветки исходов все +) + `mountains:` (5 веток + scroll_drops) + `dungeon:` (5 веток + scroll_drops).
  - `items_catalog`: 40 предметов на 8 слотов.
  - `slot_weights` per-location: forest (right_hand/left_hand = 0), mountains (right_hand/left_hand = 14), dungeon (right_hand/left_hand = 20).
  - **`scroll_drops` per-location** (3.1-D): mountains regular=3% / blessed=0%; dungeon regular=6% / blessed=1%.
  - `thickness.unlock_levels`: `mountains: 3`, `dungeon: 6`, `caravan_raider: 5`, `caravan_create: 7`, `raid_summon: 9`.
- **Anti-cheat hardcap** (ГДД §3.3): organic-источники проходят через `progression.add_length(...)`. Закреплено в `tests/unit/architecture/test_length_grant_guard.py`.
- **APScheduler-callback factories для гор и данжона — stub-и** (factory-wiring `mountain_finish_factory`/`dungeon_finish_factory` будет в **3.1-E** с bot-handler-ами).
- **Bot-handler-ов `/mountains` и `/dungeon` нет** — это **3.1-E**.
- **Use-cases применения скроллов нет** — это **Спринт 3.4** (применение скролла к предмету через `EnchantItem` use-case + UI-выбор «применить/выбросить»).
- **Тесты RBAC + lint-тест локалей** на месте (2.5-D.11/D.12).

**Скоуп Спринта 3.1 (план PR-ов — детали в `docs/development_plan.md` §6.3.1+):**
- **Цель спринта** (ГДД §8.1 / `development_plan.md` §6.3 Спринт 3.1, задачи 3.1.1–3.1.5): добавить две оставшиеся PvE-локации — `/mountains` (lvl 3+, ≥ 20 см, 20–40 мин, ±длина, 0–1 предмет) и `/dungeon` (lvl 6+, ≥ 20 см, 40–60 мин, ±длина, 0–3 предмета). Дроп оружия в обе локации. Дроп скроллов заточки (skeleton — дроп без use-механики, та переедет в Спринт 3.4). Балансировка через `balance.yaml` (без релиза кода).
- **План PR-ов** (5 фичевых):
  1. **3.1-A** ✅ (PR #99, `7a37071`) — Каркас доменов + балансовый конфиг + общий picker.
  2. **3.1-B** ✅ (PR #101, `5f25ca0`) — Use-cases `Start*Run`/`Finish*Run` + persistence + Alembic-миграция + DI.
  3. **3.1-C** ✅ (PR #103, `1ae81ab`) — Дроп оружия (`right_hand`/`left_hand`) — расширение `items_catalog` + pydantic-валидатор + per-location `slot_weights` + общий picker `pick_drop_item_entry`.
  4. **3.1-D** ✅ (PR #105, `2208ae6`) — Дроп скроллов заточки (skeleton) — domain VO `Scroll`, `ScrollDropConfig`, `PveScrollDrop`, `pick_pve_outcome` катит `scroll_drops`, 22 unit-теста. Persistence не входит — будет в Спринте 3.4.
  5. **3.1-E** ⏳ (следующий) — Bot-handlers `/mountains`, `/dungeon` + презентеры + локали + APScheduler factory-wiring.

**Текущий PR (catch-up docs-3.1-D):** docs-only — `history.md` +1 запись о PR #105 + `current_tasks.md` пересборка под `main = 2208ae6` и старт **3.1-E**. Без изменений кода / тестов / локалей / миграций / `balance.yaml`. **Это разовый catch-up** из-за того, что PR #105 был замержен раньше, чем последний docs-коммит попал в ветку. Начиная с 3.1-E — канон возвращается к норме (docs внутри фичевого PR).

**`make ci` локально на `main = 2208ae6` (база этой ветки):** ожидаемо зелёный — **3607 passed / 1 skipped**, coverage **95.88%**, ruff / mypy --strict (740 файлов, 0 issues) / import-linter (3/3 contracts kept) — clean.

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `3.1 — Горы и данжон` (см. `docs/development_plan.md` §6 / Спринт 3.1, задачи 3.1.1–3.1.5; ГДД §8 «Походы (PvE)») |
| **Активный PR / шаг** | **catch-up docs-3.1-D** (docs-only, **разовое исключение**) — `docs/history.md` +1 запись о PR #105 (3.1-D feature) + полная пересборка `docs/current_tasks.md` под `main = 2208ae6` и старт **3.1-E**. Следующий фичевый PR — 3.1-E (bot-handlers `/mountains`/`/dungeon` + APScheduler factory wiring + локали). |
| **Активная feature-ветка** | `devin/1778185503-postmerge-3-1-D-docs-catchup` (создана от `main = 2208ae6`) |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `2208ae6` (мерж PR #105 «3.1-D: дроп скроллов заточки skeleton — domain VO Scroll + ScrollDropConfig + drop-engine + 10000+ rolls тесты») |
| **Последний коммит на feature-ветке** | _будет проставлен после первого коммита catch-up_ |
| **PR (если открыт)** | _будет открыт сразу после первого пуша и локального зелёного `make ci`_ |
| **CI статус** | на `main = 2208ae6` зелёный (baseline для docs-only PR-а): `make ci` — 3607 passed / 1 skipped, coverage 95.88% |
| **Связанная задача в `development_plan.md`** | §6 / Спринт 3.1 / задача 3.1.1 (`/mountains`) + 3.1.2 (`/dungeon` UX, кнопки «надеть/выбросить»); §6.3.1+ строка 3.1-E («Bot-handlers `/mountains`, `/dungeon` + презентеры + локали + APScheduler factory-wiring»). |
| **Связанная спецификация в `game_design.md`** | §8 «Походы (PvE)» — таблица локаций; §8.4 «UX гор» (карточка возврата + кнопки «надеть/выбросить» × N); §8.5 «UX данжона» (то же × до 3 предметов). |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист.

**Текущий PR — catch-up docs-3.1-D (docs-only sync `history.md` + `current_tasks.md` под `main = 2208ae6`):**

- [x] Мердж 3.1-D в `main` (коммит `2208ae6`, [PR #105](https://github.com/Pipirkawar/PipirkaWar/pull/105)).
- [x] `git fetch && git checkout main && git pull` — получить `main = 2208ae6`.
- [x] Создать ветку `devin/1778185503-postmerge-3-1-D-docs-catchup` от `main`.
- [x] **`docs/history.md`** — добавить запись сверху: «Спринт 3.1-D: дроп скроллов заточки — domain VO `Scroll(category, blessed)` + drop-engine + 10000+ rolls тесты» (PR #105, `2208ae6`); описание скоупа (4 чекпоинт-коммита: D.1–D.4), артефактов, архитектурных решений (`scroll_drops` отдельным полем; не persist-ятся в 3.1-D; `ForestDropConfig` без `scroll_drops` by design; 3σ-tolerance), заметка о catch-up-нюансе.
- [x] **`docs/current_tasks.md`** — пересборка: «Снимок состояния» под `main = 2208ae6`; «Текущая позиция» под текущую feature-ветку catch-up; чек-лист catch-up-PR-а; ссылка на скоуп 3.1-E из `development_plan.md` §6.3.1+. Спринт-план обновлён — 3.1-A/B/C/D отмечены `[x]`.
- [ ] `make ci` локально после правок — должен оставаться зелёным (3607 passed / 1 skipped, coverage 95.88%, без изменений в коде).
- [ ] Закоммитить + запушить на origin одним коммитом `docs(catch-up 3.1-D): history.md +1, current_tasks.md sync под main = 2208ae6`.
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного CI.

**После мерджа этого catch-up-PR-а — старт 3.1-E (bot-handlers + APScheduler factory wiring + локали) на новой feature-ветке. Это будет первый PR по новому канону без катч-апов: docs-обновления внутри фичевого PR последним коммитом.**

**Спринт 3.1 — план фичевых PR-ов (референс — детали в `docs/development_plan.md`, под-секция «6.3.1+ Декомпозиция Спринта 3.1 на PR-ы»):**

- [x] **3.1-A — Каркас доменов гор и данжона + балансовый конфиг.** [PR #99, `7a37071`] Реализовано: `domain/pve/` + `domain/{mountains,dungeon}/` + секции `mountains:`/`dungeon:` в `balance.yaml` + **+75 unit-тестов** (1000-rolls stress-тесты на каждую локацию). Покрывает: 3.1.1 (домен), 3.1.2 (домен), 3.1.5 (схемы).
- [x] **3.1-B — Use-cases `Start*Run`/`Finish*Run` + persistence + миграция.** [PR #101, `5f25ca0`] Реализовано: `application/{mountains,dungeon}/` (use-cases с hardcap-каноном и idempotency); миграция `0018_pve_runs`; SQLAlchemy-модели `MountainRunORM`/`DungeonRunORM`; `SqlAlchemy{Mountain,Dungeon}RunRepository` + integration round-trip; audit/security/scheduler-фундамент. DI-wiring в `bot/main.py`. **+~290 unit/integration-тестов**. Покрывает: 3.1.1, 3.1.2 (use-case + persistence).
- [x] **3.1-C — Дроп оружия (`right_hand`/`left_hand`) — drop-engine + items_catalog.** [PR #103, `1ae81ab`] Реализовано: `Slot` enum 6→8; `SlotWeights` model; +10 weapons в `items_catalog` (40 предметов всего); `slot_weights` per-location; новый picker `pick_drop_item_entry` (общий для forest/pve); кросс-валидатор `_validate_drop_slot_rarity_coverage`. **+12 unit-тестов**. Покрывает: 3.1.4, 3.1.5 (items_catalog).
- [x] **3.1-D — Дроп скроллов заточки (skeleton, без use-механики).** [PR #105, `2208ae6`] Реализовано: `domain/enchantment/Scroll(category, blessed)`; `ScrollCategory` enum (WEAPON/ARMOR/JEWELRY); `ScrollCategoryWeights` + `ScrollDropConfig` pydantic-схемы; `PveDropConfig.scroll_drops`; `PveScrollDrop` VO; `PveRunOutcome.scroll_drops` отдельным полем; `_roll_scroll_drops` + `_pick_scroll_category` в picker-е; `config/balance.yaml` mountains regular=3% / blessed=0%, dungeon regular=6% / blessed=1%. **+36 unit-тестов** (10 entities + 22 scroll_drops + 4 минор-апдейтов в pve test_services). Скроллы **не persist-ятся** (3.4 — use-cases применения + инвентарь скроллов). Покрывает: 3.1.3, 3.1.5 (enchantment skeleton).
- [ ] **3.1-E — Bot-handlers `/mountains`, `/dungeon` + презентеры + локализация + APScheduler factory-wiring.** Тонкий aiogram-слой по образцу `bot/handlers/forest.py`. Локали `mountains-*`/`dungeon-*` (RU+EN, parity автомат). Карточка возврата + кнопки «надеть/выбросить» × N для items. APScheduler factory-wiring `mountain_finish_factory`/`dungeon_finish_factory` (`StartMountainRun`/`StartDungeonRun` уже зовут `scheduler.schedule_finish_*` — нужно подключить factory к real APScheduler через `scheduler/factory.py`). Manual smoke-тест в боте. Расширение lint-теста локалей. **Скроллы в UX: нейтральный дисплей в audit-логе и в карточке возврата (без кнопок применения — мехника применения только в 3.4).** Покрывает: 3.1.1 (UX), 3.1.2 (UX).

**После 3.1-E** — закрытие Спринта 3.1: финальная запись в `docs/history.md` + обновление `docs/current_tasks.md` под старт Спринта 3.2 (Караваны) **внутри самого 3.1-E PR-а** (по новому канону).

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Текущий PR — catch-up docs-3.1-D (docs-only sync):**
- **`docs/history.md`** — добавлена запись «Спринт 3.1-D: дроп скроллов заточки — domain VO `Scroll(category, blessed)` + drop-engine + 10000+ rolls тесты» сверху (после format-блока). Описаны: 4 чекпоинт-коммита (`7567c10`, `732764d`, `b04994f`, `d47d23a`), 11 файлов / +688 −15 строк, ключевые архитектурные решения (`scroll_drops` отдельным полем; не persist-ятся в 3.1-D; `ForestDropConfig` без `scroll_drops` by design; 3σ-tolerance вместо ±10%), отдельная заметка про catch-up-PR-нюанс (мердж #105 произошёл раньше docs-коммита).
- **`docs/current_tasks.md`** — полная пересборка: «Снимок состояния» под `main = 2208ae6`, «Текущая позиция» с `devin/1778185503-postmerge-3-1-D-docs-catchup`, чек-лист catch-up-PR-а, ссылка на скоуп 3.1-E из `development_plan.md` §6.3.1+. Спринт-план обновлён — 3.1-A/B/C/D отмечены `[x]` со ссылками на PR-ы.
- **Без изменений в коде / тестах / локалях / миграциях / `balance.yaml`.** PR docs-only.
- `make ci` ожидаемо без изменений от baseline (3607 passed / 1 skipped, coverage 95.88%).

**Следующий PR (после мерджа этого) — 3.1-E (bot-handlers + APScheduler factory wiring + локали, по новому канону без catch-up-ов):**
- Завести ветку `devin/<unix_ts>-sprint-3-1-E-bot-handlers-and-scheduler` от `main` (после мерджа catch-up).
- **Bot-handlers** `src/pipirik_wars/bot/handlers/{mountains,dungeon}.py` — тонкий aiogram-слой по образцу `bot/handlers/forest.py`:
  - `/mountains` (lvl 3+, ≥ 20 см) → `StartMountainRun` use-case, ack-сообщение «вышел в горы, вернёшься через X мин».
  - `/dungeon` (lvl 6+, ≥ 20 см) → `StartDungeonRun` use-case, ack аналогично.
  - Колбэк-кнопки «надеть/выбросить» × N для items (по образцу forest).
- **Презентеры** `src/pipirik_wars/bot/presenters/{mountains,dungeon}.py` — формирование текста ack/return-сообщений, рендер дропов.
- **Локали** `src/pipirik_wars/locales/{ru,en}/`:
  - `mountains-ack.json`, `mountains-return.json` (сценарии gain/loss × ветки × dropов).
  - `dungeon-ack.json`, `dungeon-return.json` (то же).
  - Расширение lint-теста локалей: parity RU↔EN автомат на новые ключи.
  - **Скроллы**: нейтральный дисплей в audit-логе и в карточке возврата — без кнопок применения (механика применения — Спринт 3.4); локали типа `scroll_dropped_log` достаточно.
- **APScheduler factory-wiring** `src/pipirik_wars/scheduler/factory.py`:
  - `mountain_finish_factory` / `dungeon_finish_factory` — фабрики, которые внутри APScheduler-job-а конструируют контейнер DI и вызывают `FinishMountainRun.execute(run_id=...)` / `FinishDungeonRun.execute(run_id=...)`. По образцу `forest_finish_factory`.
  - Регистрация в Container в `bot/main.py`: `scheduler` теперь умеет реально запускать finish-job-ы.
- **DI-wiring** в `bot/main.py`: добавить регистрацию handler-ов через `dispatcher.include_router(mountains_router); ...`. Связать handler-ы с factory-ями через scheduler.
- **Manual smoke-тест в боте**: `/mountains` → ждём cooldown → finish-job → ack-сообщение и карточка возврата с дропами.
- **Тесты**: unit-тесты презентеров (по образцу `tests/unit/bot/presenters/forest`), integration-тесты handler-ов через `aiogram-test-helpers`, smoke-тест factory.
- **`history.md`** + **`current_tasks.md`** — обновить **в этом же фичевом PR** (по новому правилу), последним коммитом перед мерджем (это первый PR без catch-up-овых исключений).

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Catch-up docs-PR — единичное исключение.** Возникло потому, что PR #105 (3.1-D) был замержен раньше, чем последний docs-коммит успел попасть в ветку. Начиная с 3.1-E канон возвращается к норме: docs живут внутри фичевого PR последним коммитом перед мерджем.
- **Скроллы не persist-ятся в 3.1-D** — это **дизайн-решение** (не блокер). Если игрок получит дроп скролла в горах/данжоне в 3.1, он будет залогирован в `audit_log` (когда 3.1-E подключит handler-ы), но не попадёт в инвентарь. Полная mechanic — Спринт **3.4** (`EnchantItem` use-case + `scroll_inventory` таблица + UI применения).
- **APScheduler factory-wiring** — следующий шаг (3.1-E). `StartMountainRun`/`StartDungeonRun` уже зовут `scheduler.schedule_finish_*`, но без real APScheduler-callback-а finish-job не запустится. До 3.1-E `scheduler` — stub.
- Для текущего catch-up-PR-а (docs-only) блокеров **нет**.
