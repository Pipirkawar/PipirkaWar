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

**На `main`:** последний смерженный PR — **3.1-A** ([PR #99](https://github.com/Pipirkawar/PipirkaWar/pull/99), коммит `7a37071`) — каркас доменов гор и данжона + общий picker `pick_pve_outcome` + **75 unit-тестов** в `tests/unit/domain/{pve,mountains,dungeon}/`. Перед ним: **docs-prep Спринта 3.1** (PR #98, `71a667e`) — декомпозиция Спринта 3.1 на 5 фичевых PR-ов (3.1-A…3.1-E) в `development_plan.md` §6.3.1+ + sync `current_tasks.md`. Перед ним: postmerge 2.5-D.12 (PR #97, `f3c3a86`) — закрытие Спринта 2.5; 2.5-D.12 (PR #96, `e6f7512`) — аудит/дедупликация `admin-*` локалей; postmerge 2.5-D.11 (PR #95, `61b33f1`); 2.5-D.11 (PR #94, `c434b3d`); postmerge 2.5-D.10 (PR #93, `3288fc6`); 2.5-D.10 (PR #92, `a8f26e5`); postmerge 2.5-D.6 (PR #91, `cb40c2e`); 2.5-D.6 (PR #90, `4c2b100`); postmerge 2.5-D.4 (PR #89, `8df66e7`); 2.5-D.4 (PR #88, `774bd7c`). До этого: 2.5-A (PR #79), 2.5-B (PR #81), 2.5-C (PR #83), постмердж-доки (PR #84), 2.5-D часть 1 (PR #85), 2.5-D.7 (PR #86), postmerge 2.5-D.7 (PR #87).

**Активная feature-ветка:** `devin/1778173607-postmerge-3-1-A` (текущий PR — **postmerge 3.1-A**: sync `docs/history.md` (+2 записи: «Спринт 3.1 docs-prep» + «Спринт 3.1-A») + `docs/current_tasks.md` под `main = 7a37071`, фиксация что 3.1-A в main, чек-лист 3.1-A → `[x]`, активная позиция переключена на старт **3.1-B**. Без изменений кода / тестов / локалей / миграций).

**Что уже есть в коде на старте 3.1-B (`main = 7a37071`, после мерджа 3.1-A):**
- **§8 «Походы (PvE)» ГДД — domain-слой полностью готов для гор и данжона** (3.1-A):
  - `src/pipirik_wars/domain/pve/` — общие VO + picker:
    - `entities.py`: `PveLocationKind` (mountains/dungeon), `PveOutcomeBranch` (имя + `PveSign` + абсолютная `length_cm`), `PveItemDrop`, `PveRunOutcome` (branch + знаковая `length_delta_cm` + `tuple[PveItemDrop, ...]`) с invariant-проверкой `sign ↔ delta sign` и `|delta| == branch.length_cm`.
    - `services.py::pick_pve_outcome(*, location, balance, random)` — единственный picker, общий для гор и данжона: `weighted_choice` веток + Bernoulli per-slot для дропов + `random.choice` items_catalog по rarity.
  - `src/pipirik_wars/domain/mountains/`: `MountainRun` (frozen-dataclass с `.starting()`/`.mark_finished()` идемпотентен) + `MountainRunStatus` (IN_PROGRESS, FINISHED) + `IMountainRunRepository` ABC port (add/get_by_id/get_active_by_player/save) + ошибки (`AlreadyInMountainsError`, `MountainRunNotFoundError`, `MountainRunOwnershipError`, `MountainsRequirementError` с `requirement="thickness"|"length"`).
  - `src/pipirik_wars/domain/dungeon/`: зеркало `domain/mountains/` для данжона (отличается только параметрами в `balance.yaml` — `max_drops=3`, больше разброс).
- **§8 «Походы (PvE)» ГДД — лес (forest)** реализован полностью с предыдущих спринтов: `domain/forest/` + `application/forest/` + persistence (миграция `0004_forest_runs`) + `bot/handlers/forest.py` + `bot/presenters/forest.py` + `bot/notifications/forest.py` + templates `forest_logs_{ru,en}.json`.
- **`config/balance.yaml`:** есть секции `forest:` (lines 64–77, 3 ветки исходов все +) **+ новые `mountains:` и `dungeon:`** (lines 93–136, по 5 веток исходов: 3 gain + 2 loss; кулдауны 20–40 мин / 40–60 мин; drop-конфиг с `max_drops=1` / `max_drops=3`). Pydantic-схемы (`MountainsConfig`/`DungeonConfig`/`PveSign` etc) — в `domain/balance/config.py`.
- **`thickness.unlock_levels`** (`config/balance.yaml`): уже содержит `mountains: 3`, `dungeon: 6`, `caravan_raider: 5`, `caravan_create: 7`, `raid_summon: 9` — пороги уровней доступа известны и используются в проверках доступа уже сейчас.
- **`items_catalog`** (`config/balance.yaml`): 6 слотов (`hat`/`body`/`legs`/`boots`/`ring`/`chain`), pydantic-валидатор: ≥30 предметов, уникальные `id`, ≥1 предмет на каждую редкость. **Слотов оружия (`right_hand`/`left_hand`) ещё нет** — расширение в 3.1-C.
- **`src/pipirik_wars/application/pve/`** + **`src/pipirik_wars/application/{mountains,dungeon}/`** — пустые / отсутствуют (зарезервированы под use-cases `Start*Run`/`Finish*Run` в 3.1-B).
- **Persistence гор/данжона** — пока НЕТ: ни Alembic-миграции, ни SQLAlchemy-моделей, ни repo-impl. Это весь скоуп 3.1-B.
- **Anti-cheat hardcap** (ГДД §3.3): реализован — organic-источники проходят через `progression.add_length(...)` с rolling 24ч / 7д. Любые +-исходы гор/данжона **обязаны** идти через тот же канал (как `forest` сейчас) — закладывается в use-case `Finish*Run` в 3.1-B.
- **Тесты RBAC + lint-тест локалей** на месте (Спринт 2.5-D.11/D.12), не относятся к 3.1, но любые новые локали `mountains-*` / `dungeon-*` будут автоматически проверяться lint-тестом `tests/unit/locales/test_admin_keys_lint.py::TestLocaleParity::test_full_parity` на симметрию RU↔EN (актуально для 3.1-E).

**Скоуп Спринта 3.1 (план PR-ов — детали в `docs/development_plan.md` §6.3.1+):**
- **Цель спринта** (ГДД §8.1 / `development_plan.md` §6.3 Спринт 3.1, задачи 3.1.1–3.1.5): добавить две оставшиеся PvE-локации — `/mountains` (lvl 3+, ≥ 20 см, 20–40 мин, ±длина, 0–1 предмет) и `/dungeon` (lvl 6+, ≥ 20 см, 40–60 мин, ±длина, 0–3 предмета). Дроп оружия в обе локации. Дроп скроллов заточки (skeleton — дроп без use-механики, та переедет в Спринт 3.4). Балансировка через `balance.yaml` (без релиза кода).
- **План PR-ов** (5 фичевых + postmerge у каждого):
  1. **3.1-A** — Каркас доменов + балансовый конфиг (`domain/{mountains,dungeon}/`, секции `mountains`/`dungeon` в `balance.yaml`, picker `pick_pve_outcome`, юнит-тесты).
  2. **3.1-B** — Use-cases `Start*Run`/`Finish*Run` + persistence + Alembic-миграция (`application/{mountains,dungeon}/`, SQLAlchemy-модели + миграция `00XX_pve_runs`, integration-тесты).
  3. **3.1-C** — Дроп оружия (`right_hand`/`left_hand`) — расширение `items_catalog` + pydantic-валидатор + per-location `slot_weights` + множественный дроп `0..N` (forest/mountains: 0–1; dungeon: 0–3).
  4. **3.1-D** — Дроп скроллов заточки (skeleton) — domain VO `Scroll`, drop-engine ветки `scroll_drop_regular`/`scroll_drop_blessed`, конфиг `enchantment.scroll_drops_per_location` (mountains: regular only; dungeon: regular + blessed).
  5. **3.1-E** — Bot-handlers `/mountains`, `/dungeon` + презентеры + локали `mountains-*`/`dungeon-*` (RU+EN). Кнопки «надеть/выбросить» × N для данжона.
- **Текущий PR (docs-prep Спринта 3.1):** только доки, без изменений кода / тестов / локалей / миграций. Цель — зафиксировать план в `development_plan.md` и `current_tasks.md`, чтобы каждый из последующих 5 фичевых PR-ов имел чёткие границы скоупа. Реализация начинается **только после мерджа этого PR-а и согласования плана с пользователем**.

**`make ci` локально на `main` (после postmerge 2.5-D.12 = `f3c3a86`):** зелёный — **3417 passed / 1 skipped**, coverage **95.90%**, ruff / mypy / import-linter — clean, ~1:35. На текущей feature-ветке (docs-only) `make ci` идентичен main, будет прогон перед PR-ом.

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `3.1 — Горы и данжон` (см. `docs/development_plan.md` §6 / Спринт 3.1, задачи 3.1.1–3.1.5; ГДД §8 «Походы (PvE)») |
| **Активный PR / шаг** | **postmerge 3.1-A** — sync `docs/history.md` (+2 записи: 3.1 docs-prep + 3.1-A) + `docs/current_tasks.md` под `main = 7a37071`. После мерджа этого PR-а — старт **3.1-B** (use-cases `Start*Run`/`Finish*Run` + persistence + Alembic-миграция) на новой feature-ветке. Без изменений кода / тестов / локалей / миграций. |
| **Активная feature-ветка** | `devin/1778173607-postmerge-3-1-A` (создана от `main = 7a37071`) |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `7a37071` (мерж PR #99 «feat(pve): каркас доменов гор и данжона + общий picker [Спринт 3.1-A]») |
| **Последний коммит на feature-ветке** | будет зафиксирован при первом push-е |
| **PR (если открыт)** | будет открыт после локального зелёного `make ci` |
| **CI статус** | на main зелёный: `make ci` — 3502 passed / 1 skipped, coverage 95.90% (после мерджа 3.1-A; +85 тестов от baseline 3417) |
| **Связанная задача в `development_plan.md`** | §6 / Спринт 3.1 / задачи 3.1.1–3.1.5 (горы, данжон, дроп оружия и скроллов, балансировка). |
| **Связанная спецификация в `game_design.md`** | §8 «Походы (PvE)» — таблица локаций (§8.1) и механика (§8.2); §2.6 «Экипировка» — слоты `right_hand`/`left_hand`; §2.8 «Заточка предметов» (§2.8.5 — источники скроллов: горы — обычный очень-очень-редко; данжон — обычный + blessed); §3.1 «Правило 20 см» — порог входа; §3.3 «Анти-чит хардкап» — канон через `progression.add_length(...)`. |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**Текущий PR — postmerge 3.1-A (только доки, без изменений кода / тестов / локалей / миграций):**

- [x] Мердж PR #99 на `main` (коммит `7a37071`) — Спринт 3.1-A закрыт.
- [x] `git fetch && git checkout main && git pull` — получить `main = 7a37071`.
- [x] Создать ветку `devin/1778173607-postmerge-3-1-A` от `main`.
- [x] Обновить `docs/history.md` — добавлены 2 записи (`2026-05-07 — Спринт 3.1 docs-prep` для PR #98 и `2026-05-07 — Спринт 3.1-A` для PR #99) с подробным описанием скоупа, артефактов, архитектурных решений (отдельные модули `domain/{mountains,dungeon}/` vs унификация, общий picker в `domain/pve/`).
- [x] Обновить `docs/current_tasks.md` — «Снимок состояния» (`main = 7a37071`, что есть в коде после 3.1-A), «Текущая позиция» (postmerge 3.1-A → старт 3.1-B), «Чек-лист текущего PR» (этот список), план 5 PR-ов 3.1-A → `[x]`.
- [ ] **Перед PR:** `make ci` локально зелёный (docs-only — coverage не падает; ожидание: 3502 passed, 95.90%).
- [ ] Открыть PR `docs(postmerge 3.1-A): history.md +2 записи (3.1-prep + 3.1-A), current_tasks.md sync под main = 7a37071`.
- [ ] **После мерджа:** стартовать **3.1-B** (use-cases `Start*Run`/`Finish*Run` + persistence + Alembic-миграция) — на новой feature-ветке от свежего `main`.

**Спринт 3.1 — план фичевых PR-ов (референс — детали в `docs/development_plan.md`, под-секция «6.3.1+ Декомпозиция Спринта 3.1 на PR-ы»):**

- [x] **3.1-A — Каркас доменов гор и данжона + балансовый конфиг.** [PR #99, `7a37071`] Реализовано: `domain/pve/` (общие VO + picker `pick_pve_outcome`) + `domain/mountains/` + `domain/dungeon/` (отдельные модули, не унификация — обоснование в `history.md`). Секции `mountains:` / `dungeon:` в `balance.yaml`. **+75 unit-тестов** (1000-rolls stress-тесты на каждую локацию). Покрывает: 3.1.1 (домен), 3.1.2 (домен), 3.1.5 (схемы).
- [ ] **3.1-B — Use-cases `Start*Run`/`Finish*Run` + persistence + миграция.** `application/{mountains,dungeon}/`, +-исходы через `progression.add_length(...)` (hardcap-канон), −-исходы — прямая запись + audit. Activity-lock + idempotency. Alembic-миграция `00XX_pve_runs_mountain_dungeon`. SQLAlchemy-модели + repo-impl. Integration-тесты round-trip. Покрывает: 3.1.1, 3.1.2 (use-case + persistence).
- [ ] **3.1-C — Дроп оружия (`right_hand`/`left_hand`) — drop-engine + items_catalog.** +6 позиций оружия (по 3+ на слот, по редкостям) в `items_catalog`. Расширение pydantic-валидатора (8 слотов вместо 6). `slot_weights` per-location + множественный дроп `0..N`. Юнит-тесты 1000+ rolls. Покрывает: 3.1.4, 3.1.5 (items_catalog).
- [ ] **3.1-D — Дроп скроллов заточки (skeleton, без use-механики).** Domain VO `Scroll(category, blessed)` (skeleton; полная impl механики применения скролла — Спринт 3.4). Drop-engine ветки `scroll_drop_regular`/`scroll_drop_blessed`. Конфиг `enchantment.scroll_drops_per_location` (mountains: regular only; dungeon: regular + blessed). Юнит-тесты 1000+ rolls. Покрывает: 3.1.3, 3.1.5 (enchantment skeleton).
- [ ] **3.1-E — Bot-handlers `/mountains`, `/dungeon` + презентеры + локализация.** Тонкий aiogram-слой по образцу `bot/handlers/forest.py`. Локали `mountains-*`/`dungeon-*` (RU+EN, parity автомат). Карточка возврата + кнопки «надеть/выбросить» × N. Расширение lint-теста локалей. Manual smoke-тест в боте. Покрывает: 3.1.1 (UX), 3.1.2 (UX).

**После 3.1-E** — закрытие Спринта 3.1: postmerge-PR с финальной записью в `docs/history.md`, обновление `docs/current_tasks.md` под старт Спринта 3.2 (Караваны, см. `development_plan.md` §6 / Спринт 3.2).

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты. Не дублируй ТЗ из `development_plan.md` — пиши только то, что важно для **текущего PR**.

**Текущий PR (postmerge 3.1-A) — только доки, без изменений кода / тестов / локалей / миграций:**
- `docs/history.md` — **+2 записи** в начале (newest-first):
  - `2026-05-07 — Спринт 3.1-A: каркас доменов гор и данжона + общий picker pick_pve_outcome` — описывает PR #99 (`7a37071`): новые модули `domain/{pve,mountains,dungeon}/`, общий picker, секции `mountains:`/`dungeon:` в `balance.yaml`, +75 unit-тестов (1000-rolls на локацию). Зафиксировано архитектурное решение «отдельные модули `domain/mountains/` + `domain/dungeon/`, общий picker в `domain/pve/`» (DRY на picker, отдельные модули на сущности — мотив: своя таблица + свой bot-handler у каждой локации в 3.1-B и 3.1-E).
  - `2026-05-07 — Спринт 3.1 docs-prep: декомпозиция Спринта 3.1 на 5 фичевых PR-ов (3.1-A…3.1-E)` — описывает PR #98 (`71a667e`): расширение `development_plan.md` §6.3.1+ + sync `current_tasks.md`. Запись добавлена ретроактивно (предыдущий агент не успел сделать postmerge-doc PR для docs-prep до начала работы над 3.1-A).
- `docs/current_tasks.md` — sync под `main = 7a37071`:
  - «Снимок состояния» — `main`-цепочка обновлена (3.1-A на верху, 3.1-prep ниже), что есть в коде на старте 3.1-B (полный список domain/pve + domain/{mountains,dungeon} + balance-конфиг + что ещё нет — persistence/use-cases).
  - «Текущая позиция» — Sprint 3.1 / postmerge 3.1-A / ветка `devin/1778173607-postmerge-3-1-A` / `main = 7a37071` / CI 3502 passed.
  - «Чек-лист текущего PR» — постмердж-шаги (3 готовы — мердж/sync history/sync current_tasks; 3 в очереди — make ci / open PR / старт 3.1-B).
  - План 5 PR-ов: `3.1-A → [x]` (с PR-ссылкой и кратким описанием реализации); 3.1-B/C/D/E остаются `[ ]`.
- **Без изменений кода / тестов / локалей / миграций.** `make ci` будет прогон перед открытием PR — ожидание: 3502 passed / 1 skipped, coverage **95.90%** (docs-only — идентично main = `7a37071`).

**Следующий PR (после мерджа этого) — 3.1-B:**
- Use-cases `StartMountainRun` / `FinishMountainRun` / `StartDungeonRun` / `FinishDungeonRun` (по образцу `application/forest/`). +-исходы через `progression.add_length(...)` (anti-cheat hardcap), −-исходы — прямая запись + `audit_log`. Activity-lock + idempotency. Alembic-миграция `00XX_mountain_runs_dungeon_runs` + SQLAlchemy-модели + repo-impl. Integration-тесты round-trip (по аналогии с `tests/integration/db/test_forest_run_repository.py`). На новой feature-ветке от свежего `main`. См. `docs/development_plan.md`, под-секция «6.3.1+ Декомпозиция Спринта 3.1 на PR-ы», строка 3.1-B.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Архитектурное решение из 3.1-A (закрыто):** в PR #99 принято — `domain/forest/` остаётся отдельным (уникальная семантика name-drop), для гор/данжона созданы зеркальные `domain/{mountains,dungeon}/`-модули + общий picker и VO в `domain/pve/`. Мотив: своя таблица в 3.1-B + свой bot-handler в 3.1-E. См. запись в `history.md` для полного обоснования.
- **Решение по скроллам в 3.1-D (адресуется в 3.1-D, не блокирует postmerge 3.1-A):** Domain VO `Scroll` объявляется минимально (`category` + `blessed`); полная инвентарная сущность + use-case применения скролла переезжает в Спринт 3.4 («Заточка предметов»). До тех пор скроллы из дропа пишутся в `audit_log` как `scroll_dropped` (не копятся в инвентаре игрока — иначе придётся параллельно реализовывать инвентарь скроллов, что выходит за скоуп Спринта 3.1).

---

## 🧹 Что делать при передаче работы другому агенту

Если текущий агент не успевает закрыть PR (закончились токены, упал инструментарий, обрыв сессии), **обязательно**:

1. Обнови «Текущая позиция» и чек-лист выше — отметь, что готово, что начато, что не тронуто.
2. Создай `AGENT_HANDOFF.md` в корне репо с расширенным контекстом по шаблону из `CONTRIBUTING.md` («Протокол передачи работы между агентами»).
3. Закоммить + запушь свои текущие наработки на feature-ветку (даже если они не работают — в WIP-коммите явно укажи `WIP:` в заголовке и опиши состояние в теле).
4. Не открывай PR, если ветка в полусломанном состоянии (CI красный, тесты падают): следующий агент откроет PR сам, когда доведёт до зелёного.
