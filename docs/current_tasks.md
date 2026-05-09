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

**На `main`:** последний смерженный PR — **3.5-B** (PR #<TBD>, `<merge_3_5_B>`) — persistence-слой free-to-play рулетки: доменный порт `IRouletteSpinRepository(Protocol)` (`record(*, spin)` идемпотентный + `last_free_spin_at(*, player_id) -> datetime | None`); entity `RouletteSpin(frozen=True, slots=True)` с полями `player_id`, `occurred_at` (TZ-aware), `outcome: RouletteOutcome`, `idempotency_key` + valdiation-правила (`player_id > 0`, TZ-aware, non-empty key) + convenience-properties `.kind`/`.length_cm`. ORM `RouletteSpinORM` (`roulette_spins` таблица: `id BIGINT PK autoincrement`, `player_id BIGINT FK→users.id ondelete=CASCADE`, `occurred_at TIMESTAMPTZ`, `kind VARCHAR(32)`, `length_cm INT NULL`, `idempotency_key VARCHAR(128) UNIQUE`; UNIQUE-constraint по `idempotency_key` + composite-индекс `(player_id, occurred_at)` для `last_free_spin_at`-запроса; CheckConstraint `(kind='length' AND length_cm IS NOT NULL) OR (kind != 'length' AND length_cm IS NULL)` зеркалит инвариант `RouletteOutcome`). Миграция Alembic `0023_roulette_spins` (down_revision=`0022_scrolls`). `SqlAlchemyRouletteSpinRepository` использует dialect-specific `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING` через `pg_insert` / `sqlite_insert`. **29 новых тестов**: 11 entity-валидаций (`RouletteSpin`), 15 integration-тестов репо (round-trip всех 5 RouletteOutcomeKind, idempotency, isolation, DB-CHECK invariants), 3 migration-теста (chain `0023→0022`, dir-list registry, table-structure). Без use-case-а — это 3.5-C. local `make ci`: **5017 passed / 2 skipped, coverage 95.56%**. Перед ним — **3.5-A** (PR #121, `792a366`) — каркас домена «Рулетка» + балансовый конфиг; **3.4-D** (PR #120, `9ebbf15`); **3.4-C** (PR #119, `e490095`); **3.4-B** (PR #118, `7259fad`); **3.4-A** (PR #117, `5c21d4e`). **Закрыт Спринт 3.3 «Рейд-боссы»**, **закрыт Спринт 3.4 «Заточка предметов»**, **в работе Спринт 3.5 «Free-to-play рулетка»** ([`development_plan.md`](development_plan.md) §6.3.5) — A+B смержены, активный PR — **3.5-C** «Application use-case `SpinFreeRoulette` + audit + spend-100см».

**Текущая ветка** — старт **Спринта 3.5-C «Application use-case `SpinFreeRoulette` + audit + spend-100см»** будет открыт от свежего `main = <merge_3_5_B>` после мерджа PR #<TBD> (3.5-B). Имя ветки следующего PR-а: `devin/<unix_ts>-sprint-3-5-C-roulette-use-case`.

Перед `3.5-B`: **3.5-A** (PR #121, `792a366`); **3.4-D** (PR #120, `9ebbf15`); **3.4-C** (PR #119, `e490095`); **3.4-B** (PR #118, `7259fad`); **3.4-A** (PR #117, `5c21d4e`); **3.6 design doc** (PR #116, `f7d671f`); **3.3-D** (PR #115, `5d6c9a3`); **3.3-C** (PR #114, `d08985e`); **3.3-B** (PR #113, `9c859b7`), **3.3-A** (PR #112, `dbb9b1c`); **3.2-A→D** (#108–#111); **3.1-E** (PR #107, `5c1b26f`) и PR-ы Спринтов 3.1 (#99–#106) и 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а). **Закрыт Спринт 3.3 «Рейд-боссы»** (4 PR-а). **Закрыт Спринт 3.4 «Заточка предметов»** (4 PR-а: 3.4-A/B/C/D). **В работе Спринт 3.5 «Free-to-play рулетка»** — **3.5-A+B смержены**, идёт **3.5-C «Application use-case `SpinFreeRoulette` + audit + spend-100см»** ([`development_plan.md`](development_plan.md) §6.3.5).

**Roadmap (после Спринта 3.5 → далее):**
- **Спринт 3.5 «Free-to-play рулетка»** ([`development_plan.md`](development_plan.md) §6.3.5) — **активный**, 3.5-A+B смержены; осталось 3.5-C/D (см. ниже).
- **Спринт 3.6 «Бонус-за-племена в Предсказателе»** 🎯 ([`development_plan.md`](development_plan.md) §6.3.6, ГДД §11.1) — после 3.5. Виральная мини-механика: за каждое активное племя `/predict` начисляет `+1 см` к базовому `uniform(1,20)`, cap `+131 см` (итого `≤ 151 см`). Отдельный лимит anti-cheat (`source = "oracle_tribe_bonus"` НЕ входит в organic 24h/7d). 1–2 PR-а (3.6-A: domain + config + use-case + anti-cheat; 3.6-B: bot UI + локали + закрытие).

---

## 🎯 Активный спринт — Спринт 3.5 «Free-to-play рулетка» 🎰

> Цель спринта (по [`development_plan.md`](development_plan.md) §6.3.5 «Спринт 3.5 — Free-to-play рулетка», ГДД §12.4 «Free-to-play рулетка»): free-to-play рулетка с 5 типами исходов (`length` / `item` / `scroll_regular` / `scroll_blessed` / `crypto_lot`). Игрок платит 100 см для прокрутки (открыта от уровня толщины ≥ 2). Внутри `length`-исхода — 4 length-bucket-а (`small[10..50]` / `medium[50..150]` / `good[150..300]` / `big[300..500]` см). Если crypto-пул пуст — вес `crypto_lot` перетекает на `length`. См. ГДД §12.4 и ПД §6.3.5.

**Скоуп — задачи плана 3.5.* (детали — в [`development_plan.md`](development_plan.md)):**

- Domain: pure-picker `pick_roulette_outcome(*, config, random, crypto_pool_empty)`; pydantic `RouletteFreeConfig` с инвариантами (сумма весов = 1.0 на каждом уровне).
- Persistence: таблица `roulette_spins` (player_id, occurred_at, kind, length_cm | item_id | scroll_id | crypto_lot_id, idempotency_key); ORM + миграция Alembic `0023_roulette_spins`.
- Application: use-case `SpinFreeRoulette(*, player_id, idempotency_key) -> SpinResult` с проверкой стоимости (100 см), gate-ом `min_thickness_level=2` и аудитом `ROULETTE_SPIN`.
- Bot UI: команда `/roulette_free` + warning/spin/result-карточки + локали `roulette-free-*` (RU/EN parity).
- Anti-cheat: spend-длины через `progression.add_length(delta=-100, source="roulette_free_cost")`; награда `length` исход через `add_length(delta=+roll, source="roulette_free_reward")` — обе строки **НЕ** идут в organic-окно (audit-only sources).

**Декомпозиция Спринта 3.5 на фичевые PR-ы:**

- **3.5-A ✅ — Каркас домена + балансовый конфиг.** `domain/roulette/` с `RouletteOutcomeKind` / `RouletteOutcome` / `pick_roulette_outcome(...)`; pydantic `RouletteFreeConfig` с инвариантами; стартовые дефолты в `balance.yaml`. **Смержен** (PR #121, `792a366`).
- **3.5-B ✅ — Persistence-слой.** `IRouletteSpinRepository` + ORM `RouletteSpinORM` + миграция Alembic `0023_roulette_spins` + SQL-impl. Integration-тесты на round-trip. **Смержен** (PR #<TBD>, `<merge_3_5_B>`).
- **3.5-C — Application use-case `SpinFreeRoulette` + audit + spend-100см.** `application/roulette/spin_free_roulette.py`; audit-action `ROULETTE_SPIN` whitelist; gate `min_thickness_level=2`; spend-100см sink. Юнит + integration-тесты.
- **3.5-D — Bot UI + локали + display + закрытие Спринта 3.5.** Команда `/roulette_free` + warning/spin/result-карточки + локали `roulette-free-*` (RU/EN parity) + composition root wiring. Закрытие Спринта.

**Финальный коммит каждого PR-а Спринта 3.5** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.5-X: ...») + пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния>`, передвинуть чек-лист на следующий PR (или закрыть Спринт 3.5 на 3.5-D и расписать чек-лист **первого PR-а Спринта 3.6** «Бонус-за-племена в Предсказателе»).

---

## 📝 Чек-лист следующего PR (Спринт 3.5-C — Application use-case `SpinFreeRoulette` + audit + spend-100см)

> Этот PR — третий PR Спринта 3.5. Создаёт application-use-case прокрутки free-to-play рулетки: `SpinFreeRoulette(*, player_id, idempotency_key) -> SpinResult` с gate-ом `min_thickness_level=2`, проверкой стоимости (100 см), записью audit-события `ROULETTE_SPIN` и расходом 100 см через `progression.add_length(delta=-100, source="roulette_free_cost")`. Без bot-UI — это 3.5-D.

- [ ] Дождаться мерджа `3.5-B` в `main` (PR #<TBD>, `<merge_3_5_B>`).
- [ ] `git fetch && git checkout main && git pull`.
- [ ] Создать ветку `devin/<unix_ts>-sprint-3-5-C-roulette-use-case` от свежего `main = <merge_3_5_B>`.
- [ ] **C.0 — Обновить `current_tasks.md`** под старт Спринта 3.5-C: пересобрать «Снимок состояния» под актуальный `main`, расписать чек-лист 3.5-C.
- [ ] **C.1 — Audit-action `ROULETTE_SPIN`** в `domain/shared/ports/audit.py`:
  - Добавить `ROULETTE_SPIN = "roulette_spin"` в `AuditAction(StrEnum)`.
  - Whitelist в anti-cheat: `roulette_free_cost` (sink, delta=-100) и `roulette_free_reward` (LENGTH-исход, delta=+roll) **НЕ** входят в organic 24h/7d-окна.
  - **Критерий:** `mypy --strict` 0 issues; обновлены existing-тесты `AuditAction` enum + anti-cheat-source whitelist.
- [ ] **C.2 — Application use-case `SpinFreeRoulette`** (`application/roulette/spin_free_roulette.py`, новый):
  - DTO `SpinFreeRouletteCommand(player_id, idempotency_key)` + `SpinResult(outcome: RouletteOutcome, spent_cm: int, idempotent: bool)`.
  - 8-шаговый flow: idempotency check (namespace `roulette_free`) → load Player → gate `thickness_level >= 2` (иначе `RouletteThicknessGateError`) → check `length_cm >= 100` (иначе `InsufficientLengthForRouletteError`) → `add_length(delta=-100, source="roulette_free_cost", idempotency_key="<root>:cost")` → `pick_roulette_outcome(config, random, crypto_pool_empty=True)` → `RouletteSpinRepository.record(spin)` → audit `ROULETTE_SPIN` → mark idempotency → return `SpinResult`.
  - **LENGTH-исход:** дополнительно `add_length(delta=+spin.length_cm, source="roulette_free_reward", idempotency_key="<root>:reward")` ДО финального audit.
  - **Не-LENGTH исходы (ITEM/SCROLL_REGULAR/SCROLL_BLESSED/CRYPTO_LOT):** на C.1 оставляем заглушки — выбор конкретного предмета/скролла/лота — это задача 3.5-D (bot-UI) или Фазы 4 (для CRYPTO_LOT). Audit-payload включает `kind` без `target_id`.
  - **Критерий:** `mypy --strict` 0 issues; 12-15 unit-тестов (idempotency × 2, gate-fail, insufficient-length, LENGTH-spin happy path, не-LENGTH-spin × 4 параметризованных, audit-payload, CRYPTO_LOT drain через `crypto_pool_empty=True`, anomaly).
- [ ] **C.3 — Integration-тесты use-case** (`tests/integration/application/test_spin_free_roulette.py`):
  - Real DB round-trip (через `engine` фикстуру): успешный спин с LENGTH-исходом → `roulette_spins` содержит запись + `users.length_cm` уменьшилась на 100 + увеличилась на reward + `audit_log` содержит 3 записи (`length_change` -100 + `length_change` +reward + `roulette_spin`).
  - Idempotent повтор `SpinFreeRoulette(...)` с тем же `idempotency_key` → возвращается тот же `SpinResult` без двойного списания.
  - Gate-fail: игрок с `thickness_level=1` → `RouletteThicknessGateError` без записи в `roulette_spins`.
  - **Критерий:** `mypy --strict` 0 issues; все integration-тесты зелёные.
- [ ] **C.4 — `make ci` локально:** ruff + mypy --strict + import-linter (4 contracts kept) + pytest зелёный + coverage gate (≥ 80%).
- [ ] **C.5 — Финальный док-коммит:** `history.md` + запись 3.5-C, `current_tasks.md` пересборка под старт **Спринта 3.5-D «Bot UI + локали + display + закрытие Спринта 3.5»**.
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 📦 Архив чек-листа (Спринт 3.5-B — Persistence-слой рулетки) ✅

> Этот PR закрыт, чек-лист сохранён для истории.

- [x] Дождаться мерджа `3.5-A` в `main` (PR #121, `792a366`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778347640-sprint-3-5-B-roulette-persistence` от свежего `main = 792a366`.
- [x] **B.0 — Обновить `current_tasks.md`** под старт Спринта 3.5-B: пересобрать «Снимок состояния» под актуальный `main`, расписать чек-лист 3.5-B.
- [x] **B.1 — Доменный порт `IRouletteSpinRepository` + `RouletteSpin` entity** (`domain/roulette/ports.py` + `domain/roulette/entities.py`): Protocol с `record(*, spin)` + `last_free_spin_at(*, player_id)`; entity с TZ-aware `occurred_at`, `__post_init__`-валидация (`player_id > 0`, TZ-aware, non-empty key), convenience-properties `.kind`/`.length_cm`. 11 unit-тестов в `test_entities.py`. Закоммичено в `9d67af2` (checkpoint #1).
- [x] **B.2 — ORM `RouletteSpinORM` + миграция `0023_roulette_spins`**: ORM с `id BIGINT PK autoincrement`, `player_id` FK→users.id CASCADE, `occurred_at TIMESTAMPTZ`, `kind VARCHAR(32)`, `length_cm INT NULL`, `idempotency_key VARCHAR(128) UNIQUE`; CheckConstraint `(kind='length' AND length_cm IS NOT NULL) OR (kind != 'length' AND length_cm IS NULL)`; composite-индекс `(player_id, occurred_at)`. Миграция `down_revision="0022_scrolls"`. Зарегистрирована в `models/__init__.py` + `tests/integration/db/conftest.py`. Закоммичено в `e2b28ec` (checkpoint #2).
- [x] **B.3 — `SqlAlchemyRouletteSpinRepository`**: dialect-specific `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING` через `pg_insert` / `sqlite_insert`; `last_free_spin_at` через `SELECT MAX(occurred_at) WHERE player_id=:p`. Зарегистрировано в `repositories/__init__.py`. Закоммичено в `e2b28ec` (checkpoint #2).
- [x] **B.4 — Integration-тесты** (15 тестов в `test_roulette_spin_repository.py`): round-trip для всех 5 `RouletteOutcomeKind`, idempotency (повтор + DO NOTHING semantics), isolation (per-player), DB-CHECK invariants (отказ на нарушении `kind ↔ length_cm`). Также обновлён `test_migrations.py` (chain-test 0023, dir-list, table-structure). Закоммичено в `e2b28ec` (checkpoint #2) + `13a1b58` (test_migrations.py).
- [x] **B.5 — `make ci` локально:** ruff (clean), `mypy --strict` (0 issues), import-linter (4 contracts KEPT), pytest **5017 passed / 2 skipped** (4988 baseline 3.5-A → +29 новых тестов: 11 entity + 15 repo + 3 migration), **coverage 95.56%** (gate ≥ 80%). Load-тесты flaky при параллельном прогоне в `make ci`, проходят при изолированном запуске; not related to 3.5-B changes.
- [x] **B.6 — Финальный док-коммит:** `history.md` (запись 3.5-B) + `current_tasks.md` пересборка под старт **Спринта 3.5-C «Application use-case `SpinFreeRoulette` + audit + spend-100см»** (этот коммит).
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 📦 Архив чек-листа (Спринт 3.5-A — Каркас домена «Рулетка» + балансовый конфиг) ✅

> Этот PR закрыт, чек-лист сохранён для истории.

- [x] Дождаться мерджа `3.4-D` в `main` (PR #120, `9ebbf15`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778345019-sprint-3-5-A-roulette-domain` от `main = 9ebbf15`.
- [x] **A.0 — Обновить `current_tasks.md`** под старт Спринта 3.5-A.
- [x] **A.1 — Доменный пакет `domain/roulette/`**: `entities.py` (`RouletteOutcomeKind` ре-экспорт + `RouletteOutcome` frozen-VO с инвариантом `kind ↔ length_cm`); `services.py` (pure picker `pick_roulette_outcome(*, config, random, crypto_pool_empty)` с двухуровневым weighted_choice + crypto-pool-drain percolation rule); `errors.py` (`RouletteDomainError` + `InvalidRouletteConfigError`); `__init__.py` (экспорт публичных символов). Коммит `7757a6a`.
- [x] **A.2 — Балансовый конфиг `RouletteFreeConfig`** (`domain/balance/config.py`): `RouletteOutcomeKind` (StrEnum, единое место хранения); `RouletteOutcomeWeight` + `RouletteLengthBucket` + `RouletteFreeConfig` + `RouletteConfig` pydantic-модели с 5 валидаторами (outcome-веса в Σ=1.0±ε, уникальность kind, полнота 5-ти kind, bucket-веса в Σ=1.0±ε, уникальность имён бакетов) + `RouletteLengthBucket.min_cm <= max_cm`-валидатор + `extra="forbid"`. Поле `BalanceConfig.roulette: RouletteConfig`. Дефолты в `config/balance.yaml` (5 outcomes + 4 length_buckets из ГДД §12.4.2). Коммит `7757a6a`.
- [x] **A.3 — Юнит-тесты picker-а + integration-тест парсинга `balance.yaml`**: 47 новых тестов — 11 entity-инвариантов (`tests/unit/domain/roulette/test_entities.py`); 14 picker-сценариев (`tests/unit/domain/roulette/test_picker.py`) с Bernoulli-распределениями на 10 000 ролов с 3σ-границами + crypto-pool drain percolation; 18 config-валидатор-тестов + 4 `BalanceConfig` integration-тестов (`tests/unit/domain/balance/test_roulette_config.py`); обновлены `tests/unit/domain/balance/factories.py` для подхвата дефолтного `roulette`-блока. Коммит `0dc408a` (включая mypy-фиксы test_roulette_config.py + удаление неиспользуемого `# type: ignore[misc]` в test_entities.py).
- [x] **A.4 — `make ci` локально:** ruff (clean), `mypy --strict` (0 issues, 882 source files), import-linter (4 contracts KEPT), pytest **4988 passed / 2 skipped** (4941 baseline 3.4-D → +47 новых тестов), **coverage 95.56%** (gate ≥ 80%).
- [x] **A.5 — Финальный док-коммит:** `history.md` (запись 3.5-A) + `current_tasks.md` пересборка под старт **Спринта 3.5-B «Persistence-слой рулетки»** (этот коммит).
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 📦 Архив чек-листа (Спринт 3.4-D — Bot UI заточки + локали + display + закрытие Спринта 3.4) ✅

> Этот PR закрыт, чек-лист сохранён для истории.

- [x] Дождаться мерджа `3.4-C` в `main` (PR #119, `e490095`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778323886-sprint-3-4-D-enchant-bot-ui` от `main = e490095`.
- [x] **D.0 — Обновить `current_tasks.md`** под старт Спринта 3.4-D (Вариант A: добавлены D.½, D.1a-D.1d). Коммит `3c09d0e`.
- [x] **D.½ — Расширить порты инвентаря**: `IItemRepository.list_by_player` + `IScrollRepository.list_by_player` + `ScrollStack` DTO. Коммит `d78e100`.
- [x] **D.1a — Application use-case `GetInventory(player_id) → InventoryView`** + `ItemView`/`ScrollView` DTO. Коммит `5f0312d`.
- [x] **fix(3.4-D)** — реализация `list_by_player` в InMemory-fakes + удаление 4 неиспользуемых `# type: ignore[misc]`. Коммит `0f2ac00`.
- [x] **D.1b — Bot-handler `/inventory` + `InventoryPresenter`** + хелпер `enchant_suffix(level)` + snapshot-тесты RU/EN. Коммит `740e61e`.
- [x] **D.1c — Bot-handler `/enchant <item_id> <scroll_id>` + `EnchantPresenter`** + warning/result-карточки + handler-тесты + snapshot-тесты RU/EN. Коммиты `f3f7972` + `4cf503a`.
- [x] **D.1d — Inline-кнопка «Заточить»** в карточке `/inventory` + picker (0/1/2 скролла) + handler-тесты. Коммит `5b77f06`.
- [x] **D.2 — Локали `enchant-*` + `inventory-*`** (~40 ключей × RU/EN). Коммит `5f0312d`.
- [x] **D.3 — Display `+N`** — реализовано через хелпер `enchant_suffix(level)` в `/inventory` (D.1b) + `/enchant` warning/result (D.1c). `/profile` Equipment skeleton (отложено до Спринта 1.3+); forest/PvE/dungeon-`Item` не имеют `enchant_level` (всегда дроп `level=0`); audit-лог в TG не отображается. Все актуальные display-точки покрыты.
- [x] **D.4 — Composition root**: `EnchantItem` + `GetInventory` + `SqlAlchemyEnchantHistoryReader` зарегистрированы в `bot/main.py` + composition-тесты. Коммит `225987c`.
- [x] **D.5 — Handler-тесты** — покрыто в `test_enchant.py` (D.1c): параметризованный `test_use_case_domain_error_maps_to_toast` по 5 ошибкам (`ItemNotFoundError`/`WrongScrollCategoryError`/`ScrollNotFoundError`/`ScrollOutOfStockError` + `ValueError`).
- [x] **D.6 — Кнопка «Заточить»** — реализована в D.1d.
- [x] **D.7 — e2e snapshot-тесты** — покрыто в `test_inventory.py` + `test_enchant.py` презентер-тестах (D.1b + D.1c) RU/EN parity.
- [x] **D.8 — `make ci` локально зелёный**: 4941 passed / 2 skipped, coverage 95.59%, mypy --strict 0 issues, import-linter 4 contracts KEPT.
- [x] **D.9 — Финальный док-коммит:** `history.md` (запись 3.4-D) + `current_tasks.md` пересборка под старт Спринта 3.5 (этот коммит).
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 📦 Архив чек-листа (Спринт 3.4-C — Application use-case `EnchantItem` + audit + анти-чит trip-wire + `ScrollORM`) ✅

> Этот PR закрыт, чек-лист сохранён для истории.

- [x] Дождаться мерджа `3.4-B` в `main` (PR #118, `7259fad`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778313165-sprint-3-4-C-enchant-use-case` от `main`.
- [x] **C.0 — Обновить `current_tasks.md`** под старт Спринта 3.4-C.
- [x] **C.1 — Доменный VO `Scroll`** расширен проперти `scroll_id` + classmethod `from_scroll_id`; `IScrollRepository(Protocol)` с `get`/`consume(qty)`/`add`; `ScrollNotFoundError` + `ScrollOutOfStockError`; `IItemRepository.delete` (для DESTROY-исхода).
- [x] **C.2 — ORM `ScrollORM` + миграция `0022_scrolls`** (composite PK `(player_id, scroll_id)`, `qty INT NOT NULL CHECK qty >= 0`, `acquired_at TIMESTAMPTZ`).
- [x] **C.3 — `SqlAlchemyScrollRepository`** (get/consume/add) + 22 integration-теста (round-trip 6 вариантов, stacking, изоляция, error кейсы).
- [x] **C.4 — `AuditAction.ITEM_ENCHANT_ATTEMPT` + `AuditAction.ENCHANT_ANOMALY`** в `domain/shared/ports/audit.py` (без новых `AuditSource`).
- [x] **C.5 — Application use-case `EnchantItem`** (`application/inventory/enchant_item.py`) с 10-шаговым flow: idempotency check (namespace `enchant`) → load Item → parse `Scroll.from_scroll_id` → `matches_scroll`-check → consume scroll qty=1 → `pick_enchant_outcome` → apply outcome (update_enchant_level / delete) → audit `ITEM_ENCHANT_ATTEMPT` → mark idempotency → trip-wire. DTO `EnchantAttemptResult` (outcome, old_level, new_level, item_destroyed, item_dropped, idempotent, anomaly_detected). Доменный порт `IEnchantHistoryReader` + SQL-impl `SqlAlchemyEnchantHistoryReader` (читает `audit_log` с JSON-фильтрацией в Python для портабельности SQLite/PG).
- [x] **C.6 — Trip-wire `ENCHANT_ANOMALY`** интегрирован в `EnchantItem`: после успеха на тире `old_level ∈ [18, 25]` читаем последние 10 high-tier outcomes через `IEnchantHistoryReader`; все 10 — успехи → пишем `ENCHANT_ANOMALY`.
- [x] **C.7 — 25 unit-тестов `EnchantItem`** (`tests/unit/application/inventory/test_enchant_item.py`): 2 safe-zone успеха + 4 regular outcomes + 4 blessed non-trivial outcomes + 5 error кейсов + 2 idempotency + 1 audit-payload + 6 trip-wire сценариев + 1 ambient-UoW guard + 1 clamp. + 4 integration-теста через realDB (`tests/integration/db/test_enchant_item_use_case.py`): round-trip success, destroy-исход, idempotency через realDB, trip-wire после 10 засеянных audit-записей.
- [x] **C.8 — `make ci` локально:** ruff + mypy --strict (864 source files) + import-linter (4 contracts KEPT) + pytest **4762 passed / 2 skipped**, coverage **96%**.
- [x] **C.9 — Финальный док-коммит:** `history.md` + запись 3.4-C (этот коммит), `current_tasks.md` пересборка под старт Спринта 3.4-D.
- [x] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [x] Дождаться зелёного GitHub CI.

---

## 📦 Архив чек-листа (Спринт 3.4-B — Persistence-слой инвентаря) ✅

> Этот PR закрыт, чек-лист сохранён для истории.

- [x] Дождаться мерджа `3.4-A` в `main` (PR #117, `5c21d4e`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778309826-sprint-3-4-B-inventory-persistence` от `main`.
- [x] **B.0 — Обновить `current_tasks.md`** под старт Спринта 3.4-B: пересобрать «Снимок состояния» под `main = 5c21d4e`, переписать секцию «Декомпозиция» / чек-лист под скоуп Варианта 2 (создание таблицы вместо add-column).
- [x] **B.1 — Доменный порт `IItemRepository` + `ItemNotFoundError` + `ItemCategory.from_slot`**:
  - `domain/inventory/ports.py` (новый) — `IItemRepository(Protocol)` с `async get(*, player_id, item_id) -> Item`, `async add(*, player_id, item_id, now) -> Item`, `async update_enchant_level(*, player_id, item_id, new_level) -> Item`.
  - `domain/inventory/errors.py` — добавить `ItemNotFoundError(InventoryDomainError)` (kw-only `player_id: int, item_id: str`).
  - `domain/inventory/entities.py` — добавить `ItemCategory.from_slot(slot: Slot) -> ItemCategory` (мapping ГДД §2.6 / §2.8.1: `right_hand|left_hand → WEAPON`, `hat|body|legs|feet → ARMOR`, `ring|chain → JEWELRY`).
  - **Критерий:** `mypy --strict` 0 issues; юнит-тесты на `from_slot` (8 слотов × 1 категория) + `ItemNotFoundError.__init__` kw-only + наследование от `InventoryDomainError`.
- [x] **B.2 — ORM-модель `ItemORM` + миграция Alembic `0021_items`**:
  - `infrastructure/db/models/items.py` (новый) — `ItemORM(Base)`, `__tablename__ = "items"`. Колонки: `player_id BIGINT FK→users.id ondelete=CASCADE` (PK#1), `item_id VARCHAR(64)` (PK#2), `enchant_level INT NOT NULL server_default text("0")`, `acquired_at TIMESTAMP(timezone=True) NOT NULL`. CheckConstraint `enchant_level >= 0 AND enchant_level <= 30` (`ck_items_enchant_level_range`). Composite PK `pk_items` `(player_id, item_id)`.
  - `infrastructure/db/migrations/versions/20260509_0021_items.py` — `revision="0021_items"`, `down_revision="0020_boss_fights"`. `op.create_table("items", ...)` зеркалит ORM. `downgrade()` — `op.drop_table("items")`. `default=0` через `server_default=sa.text("0")` (Postgres backfill при `INSERT` без явного значения).
  - Зарегистрировать `ItemORM` в `infrastructure/db/models/__init__.py` (export + `__all__`) и в `tests/integration/db/conftest.py` (импорт для `Base.metadata.create_all`).
  - **Критерий:** `mypy --strict` 0 issues; `pytest tests/integration/db/test_migrations.py` зелёный (up→down→up).
- [x] **B.3 — `SqlAlchemyItemRepository`**:
  - `infrastructure/db/repositories/items.py` (новый). Зависимости: `uow: SqlAlchemyUnitOfWork`, `balance: IBalanceConfig` (для `Slot → ItemCategory`). Хелпер `_row_to_entity(row, *, balance) -> Item`: lookup `row.item_id` в `balance.get().items_catalog`, derive `category = ItemCategory.from_slot(entry.slot)`, return `Item(id=row.item_id, category=category, enchant_level=row.enchant_level)`.
  - `add(*, player_id, item_id, now)`: validate `item_id` в каталоге (иначе `DomainIntegrityError`), `INSERT items (player_id, item_id, enchant_level=0, acquired_at=now)`, return `Item`.
  - `get(*, player_id, item_id) -> Item`: `SELECT WHERE player_id=:player_id AND item_id=:item_id`, если 0 строк — `ItemNotFoundError(player_id, item_id)`.
  - `update_enchant_level(*, player_id, item_id, new_level) -> Item`: `UPDATE ... SET enchant_level = :new_level WHERE ...`, `result.rowcount == 0 → ItemNotFoundError`. Возвращает свежий `Item` (re-`get`).
  - Зарегистрировать в `infrastructure/db/repositories/__init__.py`.
  - **Критерий:** `mypy --strict` 0 issues; integration-тест на `add → get → update → get` round-trip зелёный.
- [x] **B.4 — Integration-тесты `tests/integration/db/test_item_repository.py`**:
  (a) `add → get` round-trip для всех 8 слотов × 3 категорий (`weapon`/`armor`/`jewelry`) с `enchant_level=0`;
  (b) `update_enchant_level(player, item, level=15)` → `get(...).enchant_level == 15`;
  (c) `update_enchant_level(player, item=missing, level=...)` → `ItemNotFoundError`;
  (d) `get(player, item=missing)` → `ItemNotFoundError`;
  (e) legacy-record: прямой SQL `INSERT INTO items (player_id, item_id, acquired_at) VALUES (...)` без `enchant_level` → `get` отдаёт `Item(enchant_level=0)` (доказывает `server_default`-backfill);
  (f) idempotency повторного `update_enchant_level(player, item, level=5)` × 2 → `enchant_level == 5` (без race-conflict).
  - **Критерий:** все тесты зелёные на in-memory SQLite (`engine` фикстура из `conftest.py`).
- [x] **B.5 — `make ci` локально:** ruff + mypy --strict + import-linter (4 contracts kept) + pytest зелёный + coverage gate (≥ 80%). Отчёт локального прогона: **4664 passed / 2 skipped, coverage 95.47%**, mypy 0 issues на 854 source files, 4 import-linter contracts kept.
- [x] **B.6 — Финальный док-коммит:** `history.md` +запись 3.4-B, `current_tasks.md` пересборка под старт **Спринта 3.4-C «Application use-case `EnchantItem` + audit + анти-чит trip-wire»** (включая `ScrollORM` + миграцию `0022_scrolls` — переезжает из 3.4-B в 3.4-C).
- [x] Открыт PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Текущий PR — 3.5-A «Каркас домена «Рулетка» + балансовый конфиг»** — A.0/A.1/A.2/A.3/A.4/A.5 закрыты, осталось открыть PR в `main` и дождаться зелёного CI.
- **На `main`:** 3.4-D смержен (PR #120, `9ebbf15`). 3.5-A открыт от фреш-`main`.
- **Что закрыли в 3.5-A:** см. архив чек-листа выше — 6 шагов (A.0–A.5) полностью покрыты. **Активный спринт 3.5 «Free-to-play рулетка»**: 3.5-A смержится этим PR-ом, дальше — 3.5-B «Persistence-слой рулетки».
- **Открытые блокеры:** нет.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **`crypto_lot` — реальный розыгрыш отложен до Фазы 4 (Спринт 4.1).** На 3.5-A исход `crypto_lot` присутствует только в конфиге (вес `0.005` в дефолтах). На picker-уровне реализовано правило ГДД §12.4.2: «если crypto-пул пуст → вес `crypto_lot` перетекает на `length`». Use-case 3.5-C будет вызывать picker с `crypto_pool_empty=True` (всегда) до запуска Фазы 4 — фактически `crypto_lot` никогда не выпадет до Фазы 4, но сам код-путь покрыт unit-тестами.
- **`min_thickness_level=2` — gate-проверка на application-уровне в 3.5-C.** На 3.5-A это только конфиг-поле без enforcement. Use-case `SpinFreeRoulette` в 3.5-C будет проверять `player.thickness_level >= config.roulette.free.min_thickness_level` перед спином.
- **`cost_cm=100` — spend-длины через `progression.add_length(delta=-100)` в 3.5-C.** Sink-source — `roulette_free_cost`, **НЕ** входит в organic-окно anti-cheat (как и `roulette_free_reward` для `length`-исхода). Whitelist в `audit-source` для anti-cheat — задача 3.5-C.
- **Баланс рулетки — стартовые веса (LENGTH 0.85 / ITEM 0.10 / SCROLL_REGULAR 0.04 / SCROLL_BLESSED 0.005 / CRYPTO_LOT 0.005)** — копия ГДД §12.4.2. После альфа-теста подбираются по метрикам; настройка через `balance.yaml` без релиза кода.
- **`AuditAction.SCROLL_DROP` всё ещё audit-only без write-through в инвентарь** — наследие предыдущих спринтов. Рейды и PvE дропают скроллы только в `audit_log`, без `INSERT` в `scrolls`-таблицу. Запланировано как отдельная задача после 3.5 (инвентарь готов с 3.4-B/C; нужен только wire-up в use-case-ах `FinishBossFight` / `FinishMountainRun` / `FinishDungeonRun`).

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`0dc408a` — `test(3.5-A): A.3 — RouletteFreeConfig validators + mypy fixes` (последний коммит перед docs-коммитом A.5).
