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

**На `main`:** последний смерженный PR — **postmerge 3.1-A** ([PR #100](https://github.com/Pipirkawar/PipirkaWar/pull/100), коммит `76c83a0`) — docs-only sync `history.md` (+2 записи: 3.1 docs-prep + 3.1-A) + `current_tasks.md` под `main = 7a37071`. Перед ним: **3.1-A** ([PR #99](https://github.com/Pipirkawar/PipirkaWar/pull/99), `7a37071`) — каркас доменов гор и данжона + общий picker `pick_pve_outcome` + **75 unit-тестов** в `tests/unit/domain/{pve,mountains,dungeon}/`. Перед ним: **docs-prep Спринта 3.1** (PR #98, `71a667e`) — декомпозиция Спринта 3.1 на 5 фичевых PR-ов (3.1-A…3.1-E) в `development_plan.md` §6.3.1+ + sync `current_tasks.md`. Перед ним: postmerge 2.5-D.12 (PR #97, `f3c3a86`) — закрытие Спринта 2.5; 2.5-D.12 (PR #96, `e6f7512`) — аудит/дедупликация `admin-*` локалей; postmerge 2.5-D.11 (PR #95, `61b33f1`); 2.5-D.11 (PR #94, `c434b3d`); postmerge 2.5-D.10 (PR #93, `3288fc6`); 2.5-D.10 (PR #92, `a8f26e5`); postmerge 2.5-D.6 (PR #91, `cb40c2e`); 2.5-D.6 (PR #90, `4c2b100`); postmerge 2.5-D.4 (PR #89, `8df66e7`); 2.5-D.4 (PR #88, `774bd7c`). До этого: 2.5-A (PR #79), 2.5-B (PR #81), 2.5-C (PR #83), постмердж-доки (PR #84), 2.5-D часть 1 (PR #85), 2.5-D.7 (PR #86), postmerge 2.5-D.7 (PR #87).

**Активная feature-ветка:** `devin/1778174890-sprint-3-1-B-pve-persistence` (создана от `main = 76c83a0`; текущий PR — **3.1-B (mid-flight)**: use-cases `Start*Run`/`Finish*Run` + persistence + миграция). Уже на ветке 2 коммита:
- `5a1a411` — **infra-фундамент**: 4 новых `AuditAction` (`MOUNTAIN/DUNGEON_RUN_STARTED/FINISHED`), 2 `AuditSource` (`MOUNTAINS`, `DUNGEON`), 2 `LockReason`, 4 abstract-метода в `IDelayedJobScheduler` (`schedule/cancel_finish_{mountain,dungeon}_run`) + `Fake` + `APScheduler` stub, `balance.yaml::anticheat.organic_sources` += `mountains`, `dungeon`, **миграция `0018_pve_runs`** (таблицы `mountain_runs` + `dungeon_runs` со всеми CHECK-инвариантами и индексами), CHECK-обновление `AuditLogORM`.
- `70ee23f` — **DTOs + ORM**: 4 DTO (`Start/Finish{Mountain,Dungeon}RunInput`) в `application/dto/inputs.py`, `MountainRunORM` + `DungeonRunORM` в `infrastructure/db/models/pve_runs.py` (общий factory `_pve_run_table_args`, `drops` как JSON), экспорты в `models/__init__.py`.

**Что уже есть в коде на момент старта работы (`main = 76c83a0`, после мерджа postmerge 3.1-A; +2 коммита 3.1-B на feature-ветке):**
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
- **`src/pipirik_wars/application/pve/`** + **`src/pipirik_wars/application/{mountains,dungeon}/`** — пустые / отсутствуют (зарезервированы под use-cases `Start*Run`/`Finish*Run`, остаток скоупа 3.1-B).
- **Persistence гор/данжона** (3.1-B, частично готово на текущей feature-ветке `devin/1778174890-sprint-3-1-B-pve-persistence`):
  - **Готово (commit `5a1a411`+`70ee23f`):** Alembic-миграция `0018_pve_runs` (таблицы `mountain_runs` + `dungeon_runs` с `branch_name`/`branch_sign`/`length_delta_cm`/`drops` (JSON), CHECK-инварианты на статусы, знак ↔ дельта, `finished_at` ↔ статус, `ends_at > started_at`; индексы `(player_id, status)`, `(status, ends_at)`, partial unique `(player_id) WHERE status='in_progress'`). SQLAlchemy-модели `MountainRunORM` + `DungeonRunORM` в `infrastructure/db/models/pve_runs.py`. 4 DTO `Start/Finish{Mountain,Dungeon}RunInput` в `application/dto/inputs.py`. Audit/security/scheduler-фундамент: новые `AuditAction` `MOUNTAIN/DUNGEON_RUN_STARTED/FINISHED`, `AuditSource.MOUNTAINS`/`DUNGEON`, `LockReason.MOUNTAINS`/`DUNGEON`, 4 метода в `IDelayedJobScheduler`.
  - **Осталось:** application/use-cases `Start*Run`/`Finish*Run` (по образцу `application/forest/`); SQL-impl `IMountainRunRepository` / `IDungeonRunRepository` (по образцу `infrastructure/db/repositories/forest_run.py`); fake-репо для unit-тестов; integration-тесты round-trip; DI-wiring в `bot/main.py`.
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

**`make ci` локально на feature-ветке `devin/1778174890-sprint-3-1-B-pve-persistence` (`HEAD = 70ee23f`, +2 коммита над `main = 76c83a0`):** зелёный — **3505 passed / 1 skipped**, coverage **95.83%**, ruff / mypy --strict (716 файлов, 0 issues) / import-linter (3/3 contracts kept) — clean, ~1:38.

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `3.1 — Горы и данжон` (см. `docs/development_plan.md` §6 / Спринт 3.1, задачи 3.1.1–3.1.5; ГДД §8 «Походы (PvE)») |
| **Активный PR / шаг** | **3.1-B (mid-flight)** — Use-cases `StartMountainRun`/`FinishMountainRun`/`StartDungeonRun`/`FinishDungeonRun` + SQLAlchemy-impl `IMountainRunRepository`/`IDungeonRunRepository` + integration-тесты round-trip + DI-wiring в `bot/main.py`. На ветке уже 2 commit-а с infra-фундаментом, ORM, DTOs, миграцией `0018_pve_runs`. Bot-handler-ов `/mountains` `/dungeon` НЕТ — это 3.1-E. |
| **Активная feature-ветка** | `devin/1778174890-sprint-3-1-B-pve-persistence` (создана от `main = 76c83a0`) |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `76c83a0` (мерж PR #100 «docs(postmerge 3.1-A): history.md +2 записи, current_tasks.md sync под main = 7a37071») |
| **Последний коммит на feature-ветке** | `70ee23f` («feat(3.1-B): DTOs Start/Finish{Mountain,Dungeon}RunInput + ORM-модели MountainRunORM/DungeonRunORM») |
| **PR (если открыт)** | пока не открыт; будет открыт после докатывания use-cases + repos + integration-тестов и локально зелёного `make ci` |
| **CI статус** | на feature-ветке зелёный: `make ci` — 3505 passed / 1 skipped, coverage 95.83% |
| **Связанная задача в `development_plan.md`** | §6 / Спринт 3.1 / задачи 3.1.1–3.1.5 (горы, данжон, дроп оружия и скроллов, балансировка). |
| **Связанная спецификация в `game_design.md`** | §8 «Походы (PvE)» — таблица локаций (§8.1) и механика (§8.2); §2.6 «Экипировка» — слоты `right_hand`/`left_hand`; §2.8 «Заточка предметов» (§2.8.5 — источники скроллов: горы — обычный очень-очень-редко; данжон — обычный + blessed); §3.1 «Правило 20 см» — порог входа; §3.3 «Анти-чит хардкап» — канон через `progression.add_length(...)`. |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**Текущий PR — 3.1-B (use-cases `Start*Run`/`Finish*Run` + persistence + integration-тесты + DI-wiring):**

- [x] Мердж postmerge 3.1-A в `main` (коммит `76c83a0`, [PR #100](https://github.com/Pipirkawar/PipirkaWar/pull/100)).
- [x] `git fetch && git checkout main && git pull` — получить `main = 76c83a0`.
- [x] Создать ветку `devin/1778174890-sprint-3-1-B-pve-persistence` от `main`.
- [x] **Commit `5a1a411`** — infra-фундамент: `AuditAction.MOUNTAIN/DUNGEON_RUN_STARTED/FINISHED`, `AuditSource.MOUNTAINS/DUNGEON`, `LockReason.MOUNTAINS/DUNGEON`, `IDelayedJobScheduler.schedule/cancel_finish_{mountain,dungeon}_run`, миграция `0018_pve_runs`, расширение `audit_log_source_whitelist` CHECK.
- [x] **Commit `70ee23f`** — DTOs `Start/Finish{Mountain,Dungeon}RunInput` + ORM `MountainRunORM`/`DungeonRunORM`.
- [x] Sync `docs/current_tasks.md` под mid-flight 3.1-B (этот коммит).
- [ ] **Commit (use-cases mountains)** — `application/mountains/{start_run,finish_run}.py` + `__init__.py`; FakeMountainRunRepository в `tests/fakes/`; unit-тесты `tests/unit/application/mountains/test_{start,finish}_run.py` (FakeUoW/Random/Clock паттерн forest).
- [ ] **Commit (use-cases dungeon)** — зеркало гор: `application/dungeon/{start_run,finish_run}.py` + `__init__.py`; FakeDungeonRunRepository; unit-тесты.
- [ ] **Commit (Sql-impl + integration)** — `infrastructure/db/repositories/{mountain_run,dungeon_run}.py` (impl `IMountainRunRepository`/`IDungeonRunRepository` по образцу `forest_run.py`); integration-тесты `tests/integration/db/test_pve_runs.py` (round-trip add → get_by_id → save).
- [ ] **Commit (DI-wiring)** — `bot/main.py` Container: SqlAlchemy{Mountain,Dungeon}RunRepository + use-cases (без bot-handler-ов — это 3.1-E).
- [ ] **Перед PR:** `make ci` локально зелёный (≥3505 passed, coverage ≥95.83%, lint/mypy/import-linter — clean).
- [ ] Открыть PR `feat(3.1-B): use-cases Start/Finish{Mountain,Dungeon}Run + persistence + integration-тесты`.
- [ ] **После мерджа:** postmerge 3.1-B (sync history.md + current_tasks.md), затем старт 3.1-C (дроп оружия) на новой feature-ветке.

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

**Текущий PR — 3.1-B (mid-flight, use-cases + persistence + integration-тесты + DI-wiring):**
- **Уже на ветке (commits `5a1a411` + `70ee23f`):** infra-фундамент (audit/security/scheduler) + миграция `0018_pve_runs` + ORM-модели + DTOs.
- **Этот коммит (sync docs):** `docs/current_tasks.md` обновлён под mid-flight 3.1-B — переключены «Снимок», «Текущая позиция», чек-лист текущего PR, описана дельта.
- **Дальше — атомарные коммиты по плану:**
  1. `application/mountains/` use-cases (`StartMountainRun`, `FinishMountainRun`) + `tests/fakes/mountain_run_repo.py` + unit-тесты `tests/unit/application/mountains/`. Lock-reason — `LockReason.MOUNTAINS`. +-исходы через `ILengthGranter.grant(source=AuditSource.MOUNTAINS, ...)` (hardcap-канон); −-исходы — прямая `player.with_length(...)` + audit `LENGTH_REVOKE` (по образцу `application/pvp/apply_outcome.py`; файл будет добавлен в whitelist `tests/unit/architecture/test_length_grant_guard.py`).
  2. `application/dungeon/` — зеркало гор (отличается только параметрами в `balance.yaml`).
  3. `infrastructure/db/repositories/{mountain_run,dungeon_run}.py` (по образцу `forest_run.py` — но `drops` сериализуется в JSON-массив `[{"item_id": "..."}]`) + integration-тесты `tests/integration/db/test_pve_runs.py` (round-trip).
  4. DI-wiring в `bot/main.py` (без bot-handler-ов — это 3.1-E).
- `make ci` будет прогон перед открытием PR — ожидание: ≥3505 passed (текущий baseline) + новые unit-тесты + 1-2 integration round-trip; coverage ≥95.83%.

**Следующий PR (после мерджа этого) — postmerge 3.1-B + старт 3.1-C:**
- Postmerge 3.1-B: docs-only (history.md + current_tasks.md sync).
- 3.1-C: дроп оружия — расширение `items_catalog` слотами `right_hand`/`left_hand`, `slot_weights` per-location, множественный дроп `0..N`. См. `docs/development_plan.md` §6.3.1+ строка 3.1-C.

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
