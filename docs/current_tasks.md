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

**На `main`:** последний смерженный PR — **fix(load-tests)** (PR #124, `4baca4b`) — `poolclass=NullPool` в `tests/integration/load/conftest.py::shared_engine` (test-only фикс flaky-падения `test_100_parallel_grants_for_same_player_respect_daily_cap` на py3.11; см. PR #124 description). Не относится к скоупу Спринта 3.5 — отдельный test-fix PR. Перед ним: **3.5-C** (PR #123, `7085e51`) — application use-case `SpinFreeRoulette(*, command: SpinFreeRouletteCommand) -> SpinResult` (`application/roulette/spin_free_roulette.py`, ~340 строк) с 8-шаговым flow: idempotency-check (namespace `roulette_free`) → load Player → gate `thickness_level >= config.roulette.free.min_thickness_level=2` (иначе `RouletteThicknessGateError`) → check `length_cm >= cost_cm=100` (иначе `InsufficientLengthForRouletteError`) → `add_length(delta=-100, source=ROULETTE_FREE_COST, idempotency_key="add_length:{root}:cost")` → `pick_roulette_outcome(config, random, crypto_pool_empty=True)` (Фаза 3 — crypto-пул всегда пуст) → `RouletteSpinRepository.record(spin)` (idempotent через DO NOTHING) → audit `ROULETTE_SPIN(payload={kind, length_cm | None})` → mark idempotency. LENGTH-исход: дополнительно `add_length(delta=+spin.length_cm, source=ROULETTE_FREE_REWARD, idempotency_key="add_length:{root}:reward")` ДО финального audit. Domain-errors `RouletteThicknessGateError` + `InsufficientLengthForRouletteError` (`domain/roulette/errors.py`). `AuditAction.ROULETTE_SPIN` + `AuditSource.ROULETTE_FREE_COST/REWARD` (`domain/shared/ports/audit.py`) — оба source-а **НЕ** входят в organic 24h/7d-окна anti-cheat. Миграция Alembic `0024_audit_source_roulette_free` (`down_revision=0023_roulette_spins`) расширяет CHECK constraint `audit_log_source_whitelist` на `roulette_free_cost`/`roulette_free_reward`; зеркало в ORM `AuditLogORM.audit_log_source_whitelist` (`infrastructure/db/models/security.py`). 13 unit-тестов `tests/unit/application/roulette/test_spin_free_roulette.py` + 7 integration-тестов `tests/integration/db/test_spin_free_roulette_use_case.py` (round-trip LENGTH/ITEM/SCROLL_REGULAR/SCROLL_BLESSED + idempotency + gate-fails). Without bot-UI — это 3.5-D. local: ruff + mypy --strict (0 issues, 891 source files) + import-linter (4 contracts KEPT) + pytest unit **4529 passed / 2 skipped** + integration db/admin/balance/i18n/templates/application **515 passed**. Перед ним — **3.5-B** (PR #122, `3505e83`) — persistence-слой рулетки (`IRouletteSpinRepository` + ORM + миграция `0023_roulette_spins`); **3.5-A** (PR #121, `792a366`) — каркас домена + балансовый конфиг; **3.4-D** (PR #120, `9ebbf15`); **3.4-C** (PR #119, `e490095`); **3.4-B** (PR #118, `7259fad`); **3.4-A** (PR #117, `5c21d4e`). **Закрыт Спринт 3.3 «Рейд-боссы»**, **закрыт Спринт 3.4 «Заточка предметов»**, **в работе Спринт 3.5 «Free-to-play рулетка»** ([`development_plan.md`](development_plan.md) §6.3.5) — A+B+C смержены, активный PR — **3.5-D** «Bot UI + локали + display + закрытие Спринта 3.5».

**Текущая ветка** — `devin/1778361483-sprint-3-5-D-roulette-bot-ui` — открыта от свежего `main = 4baca4b` (после PR #124, тривиальный test-only фикс поверх PR #123 = 3.5-C) под **Спринт 3.5-D «Bot UI + локали + display + закрытие Спринта 3.5»**.

Перед `3.5-C` (PR #123, `7085e51`): **3.5-B** (PR #122, `3505e83`); **3.5-A** (PR #121, `792a366`); **3.4-D** (PR #120, `9ebbf15`); **3.4-C** (PR #119, `e490095`); **3.4-B** (PR #118, `7259fad`); **3.4-A** (PR #117, `5c21d4e`); **3.6 design doc** (PR #116, `f7d671f`); **3.3-D** (PR #115, `5d6c9a3`); **3.3-C** (PR #114, `d08985e`); **3.3-B** (PR #113, `9c859b7`), **3.3-A** (PR #112, `dbb9b1c`); **3.2-A→D** (#108–#111); **3.1-E** (PR #107, `5c1b26f`) и PR-ы Спринтов 3.1 (#99–#106) и 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а). **Закрыт Спринт 3.3 «Рейд-боссы»** (4 PR-а). **Закрыт Спринт 3.4 «Заточка предметов»** (4 PR-а: 3.4-A/B/C/D). **В работе Спринт 3.5 «Free-to-play рулетка»** — **3.5-A+B+C смержены**, идёт **3.5-D «Bot UI + локали + display + закрытие Спринта 3.5»** ([`development_plan.md`](development_plan.md) §6.3.5).

**Roadmap (после Спринта 3.5 → далее):**
- **Спринт 3.5 «Free-to-play рулетка»** ([`development_plan.md`](development_plan.md) §6.3.5) — **активный**, 3.5-A+B+C смержены; осталось 3.5-D (см. ниже).
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
- **3.5-B ✅ — Persistence-слой.** `IRouletteSpinRepository` + ORM `RouletteSpinORM` + миграция Alembic `0023_roulette_spins` + SQL-impl. Integration-тесты на round-trip. **Смержен** (PR #122, `3505e83`).
- **3.5-C ✅ — Application use-case `SpinFreeRoulette` + audit + spend-100см.** `application/roulette/spin_free_roulette.py`; audit-action `ROULETTE_SPIN` + `AuditSource.ROULETTE_FREE_{COST,REWARD}` + миграция `0024`; gate `min_thickness_level=2`; spend-100см sink. 13 unit + 7 integration-тестов. **Смержен** (PR #123, `7085e51`).
- **3.5-D — Bot UI + локали + display + закрытие Спринта 3.5.** Команда `/roulette_free` + warning/spin/result-карточки + локали `roulette-free-*` (RU/EN parity) + composition root wiring. Закрытие Спринта.

**Финальный коммит каждого PR-а Спринта 3.5** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.5-X: ...») + пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния>`, передвинуть чек-лист на следующий PR (или закрыть Спринт 3.5 на 3.5-D и расписать чек-лист **первого PR-а Спринта 3.6** «Бонус-за-племена в Предсказателе»).

---

## 📝 Чек-лист следующего PR (Спринт 3.5-D — Bot UI + локали + display + закрытие Спринта 3.5)

> Этот PR — четвёртый и финальный PR Спринта 3.5. Создаёт bot-UI free-to-play рулетки: команда `/roulette_free` + warning-карточка (длина < 100 см / толщина < 2) + result-карточка (LENGTH/ITEM/SCROLL_REGULAR/SCROLL_BLESSED) + анимация-крутилка + локали `roulette-free-*` (RU/EN parity) + DI-провязка в `bot/main.py`. Закрывает Спринт 3.5.

- [x] Дождаться мерджа `3.5-C` в `main` (PR #123, `7085e51`).
- [x] `git fetch && git checkout main && git pull` (после PR #124 fix-flaky → `main = 4baca4b`).
- [x] Создать ветку `devin/1778361483-sprint-3-5-D-roulette-bot-ui` от свежего `main = 4baca4b`.
- [x] **D.0 — Обновить `current_tasks.md`** под старт Спринта 3.5-D: пересобрать «Снимок состояния» под актуальный `main = 4baca4b`, расписать чек-лист 3.5-D, заархивировать чек-лист 3.5-C (этот коммит — Checkpoint 1).
- [ ] **D.1 — Bot-handler `/roulette_free`** (`bot/handlers/roulette.py`, новый):
  - Команда `/roulette_free` в личке-only (по аналогии с `caravan.py`/`boss.py`/`enchant.py`).
  - **Pre-spin gate-проверка:** если `player.thickness_level < 2` → warning-карточка `roulette-free-warn-thickness` (с подсказкой «Прокачай толщину до 2 уровня»); если `player.length_cm < 100` → warning-карточка `roulette-free-warn-length` (с подсказкой «Накопи 100 см длины»).
  - **Spin-кнопка:** `«Крутить за 100 см»` → callback `roulette_free:spin`.
  - **Анимация-крутилка:** 3-5 промежуточных сообщений с задержкой (1-2 сек между ними) — например `🎰 …` → `🎰 🍆 …` → `🎰 🍆 ⏳ …` → final result. Реализация через `bot.send_message` + `asyncio.sleep` + `bot.edit_message_text` или последовательные сообщения.
  - **Result-карточка:** разная для каждого `RouletteOutcomeKind` — `roulette-free-result-length-{small|medium|good|big}`, `roulette-free-result-item`, `roulette-free-result-scroll-regular`, `roulette-free-result-scroll-blessed`, `roulette-free-result-crypto-lot` (Фаза 4 — заглушка).
  - DI: `SpinFreeRoulette` use-case через `Container.spin_free_roulette` (D.4); `bot/handlers/roulette.py` зарегистрирован в `bot/handlers/__init__.py`.
  - Error-маппинг: `RouletteThicknessGateError` / `InsufficientLengthForRouletteError` → toast с локализованным сообщением (через `RoulettePresenter` D.3).
  - **Критерий:** `mypy --strict` 0 issues; handler-тесты (mock `Container` + `bot` через `aiogram-tests` или ручной mock).
- [ ] **D.2 — Локали `roulette-free-*`** (`bot/i18n/locales/ru/roulette-free.ftl` + `en/roulette-free.ftl`):
  - Стартовая команда (`/roulette_free`-help, intro), warnings (thickness/length), spin-button label, результат-карточки на все `RouletteOutcomeKind` × `length_buckets` (small/medium/good/big).
  - **Локали-parity тест:** все ключи в RU есть в EN и vice versa (как `bosses-*` / `enchant-*` / `caravan-*`).
  - **Критерий:** `mypy --strict` 0 issues; locale-parity-тест зелёный.
- [ ] **D.3 — `RoulettePresenter`** (`bot/presenters/roulette.py`, новый):
  - Locale-driven рендер всех роулетка-карточек (warnings, spin-prompt, results).
  - Маппинг `SpinResult` → result-карточка (выбор шаблона по `outcome.kind` + для LENGTH — выбор bucket по `length_cm`).
  - Snapshot-тесты RU/EN parity (как `BossPresenter` / `EnchantPresenter`).
  - **Критерий:** `mypy --strict` 0 issues; snapshot-тесты зелёные.
- [ ] **D.4 — DI-провязка** в `bot/main.py`:
  - Добавить `spin_free_roulette: SpinFreeRoulette` в `Container` + конструктор `build_container(...)` с реальными SQL-репо/audit-сервисами.
  - `bot/handlers/__init__.py`: импорт + регистрация `roulette_router`.
  - `bot/presenters/__init__.py`: экспорт `RoulettePresenter`.
  - **Критерий:** composition-тесты (`tests/unit/bot/test_composition_root.py`) обновлены под новый use-case.
- [x] **D.5 — `make ci` локально:** ruff + mypy --strict + import-linter (4 contracts kept) + pytest зелёный + coverage gate (≥ 80%) — **5132 passed / 2 skipped, coverage 95.63%** на `c4a7289`.
- [ ] **D.6 — Финальный док-коммит:** `history.md` + запись 3.5-D, `current_tasks.md` пересборка под старт **Спринта 3.6 «Бонус-за-племена в Предсказателе»** (закрытие Спринта 3.5).
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 📦 Архив чек-листа (Спринт 3.5-C — Application use-case `SpinFreeRoulette` + audit + spend-100см) ✅

> Этот PR закрыт, чек-лист сохранён для истории.

- [x] Дождаться мерджа `3.5-B` в `main` (PR #122, `3505e83`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778350327-sprint-3-5-C-roulette-use-case` от свежего `main = 3505e83`.
- [x] PR #123 → merged → `7085e51`. После merge на main отдельным PR #124 поверх (`4baca4b`) — test-only NullPool-fix flaky load-теста (вне скоупа 3.5-C).
- [x] **C.0 — Обновить `current_tasks.md`** под старт Спринта 3.5-C: пересобрать «Снимок состояния» под актуальный `main`, расписать чек-лист 3.5-C. Коммит `902119e`.
- [x] **C.1 — Audit-action `ROULETTE_SPIN` + `AuditSource.ROULETTE_FREE_{COST,REWARD}` + миграция `0024_audit_source_roulette_free`**: добавлены в `domain/shared/ports/audit.py`; миграция расширяет CHECK whitelist `audit_log_source_whitelist`; обновлён parity-тест `test_audit_source.py`. Коммит `478d242`.
- [x] **C.2 — Application use-case `SpinFreeRoulette`** (`application/roulette/spin_free_roulette.py`, ~340 строк): DTO `SpinFreeRouletteCommand` + `SpinResult`; 8-шаговый flow (idempotency → load → thickness-gate → length-check → spend-100 → pick-outcome → record-spin → audit → mark-idempotency); domain-errors `RouletteThicknessGateError` / `InsufficientLengthForRouletteError`; для LENGTH-исхода — дополнительный `add_length(delta=+roll, source=ROULETTE_FREE_REWARD)`. 13 unit-тестов. Коммит `6330100` (checkpoint #1).
- [x] **C.3 — Integration-тесты use-case** (`tests/integration/db/test_spin_free_roulette_use_case.py`, ~440 строк, 7 тестов): real-DB round-trip для LENGTH-исхода (3 audit-записи: cost + ROULETTE_SPIN + reward); 3 параметризованных не-LENGTH (ITEM/SCROLL_REGULAR/SCROLL_BLESSED, 2 audit-записи); idempotent replay (тот же `idempotency_key` → no-op); gate-fail × 2 (thickness < 2, length < 100) без DB-записей. Bug fix: `AuditLogORM.audit_log_source_whitelist` (`infrastructure/db/models/security.py`) синхронизирован с миграцией 0024. Коммит `2c24ad7` (checkpoint #2).
- [x] **C.4 — `make ci` локально:** ruff (clean), `mypy --strict` (0 issues, 891 source files), import-linter (4 contracts KEPT), pytest unit **4529 passed / 2 skipped** (5017 baseline 3.5-B → +13 unit-тестов SpinFreeRoulette − дедупликация length_grant_guard whitelist), integration db/admin/balance/i18n/templates/application **515 passed**. Load-тесты `tests/integration/load/` flaky при параллельном прогоне (известный flake из 3.5-B), not related to 3.5-C.
- [x] **C.5 — Финальный док-коммит:** `history.md` (запись 3.5-C) + `current_tasks.md` пересборка под старт **Спринта 3.5-D «Bot UI + локали + display + закрытие Спринта 3.5»**.
- [x] Открыть PR в `main` по шаблону `.github/pull_request_template.md` — PR #123.
- [x] Дождаться зелёного GitHub CI — PR #123 смержен в `7085e51`.

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
- [x] **B.6 — Финальный док-коммит:** `history.md` (запись 3.5-B) + `current_tasks.md` пересборка под старт **Спринта 3.5-C «Application use-case `SpinFreeRoulette` + audit + spend-100см»**.
- [x] Открыть PR в `main` по шаблону `.github/pull_request_template.md` — PR #122.
- [x] Дождаться зелёного GitHub CI — PR #122 смержен в `3505e83`.

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

**Текущий PR — 3.5-C «Application use-case `SpinFreeRoulette` + audit + spend-100см»** — C.0/C.1/C.2/C.3/C.4/C.5 закрыты, осталось открыть PR в `main` и дождаться зелёного CI.
- **На `main`:** 3.5-B смержен (PR #122, `3505e83`). 3.5-C открыт от фреш-`main`.
- **Что закрыли в 3.5-C:** см. архив чек-листа выше — 6 шагов (C.0–C.5) полностью покрыты. **Активный спринт 3.5 «Free-to-play рулетка»**: 3.5-C смержится этим PR-ом, дальше — 3.5-D «Bot UI + локали + display + закрытие Спринта 3.5».
- **Открытые блокеры:** нет.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **`crypto_lot` — реальный розыгрыш отложен до Фазы 4 (Спринт 4.1).** На 3.5-C использован `crypto_pool_empty=True` (всегда) — вес `CRYPTO_LOT` перетекает на `LENGTH` в picker-е. До запуска Фазы 4 `crypto_lot` никогда не выпадет в продакшне, но code-path покрыт unit-тестом через явный `crypto_pool_empty=False`-сценарий.
- **Не-LENGTH исходы (ITEM/SCROLL_REGULAR/SCROLL_BLESSED) — стабы на 3.5-C.** `RouletteSpinRepository.record(spin)` пишет `kind` + `length_cm=NULL`, audit-payload не содержит `target_id`. Реальный выбор предмета/скролла + INSERT в инвентарь — задача 3.5-D / отдельный спринт «инвентарь + рулетка интеграция».
- **Bot UI / команда `/roulette_free` — задача 3.5-D.** На 3.5-C use-case вызывается только из тестов. Композишн-root (`bot/main.py`) ещё не пробрасывает `SpinFreeRoulette` — это задача 3.5-D вместе с handler-ом.
- **Баланс рулетки — стартовые веса (LENGTH 0.85 / ITEM 0.10 / SCROLL_REGULAR 0.04 / SCROLL_BLESSED 0.005 / CRYPTO_LOT 0.005)** — копия ГДД §12.4.2. После альфа-теста подбираются по метрикам; настройка через `balance.yaml` без релиза кода.
- **`AuditAction.SCROLL_DROP` всё ещё audit-only без write-through в инвентарь** — наследие предыдущих спринтов. Рейды и PvE дропают скроллы только в `audit_log`, без `INSERT` в `scrolls`-таблицу. Запланировано как отдельная задача после 3.5 (инвентарь готов с 3.4-B/C; нужен только wire-up в use-case-ах `FinishBossFight` / `FinishMountainRun` / `FinishDungeonRun`).

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`2c24ad7` — `feat(3.5-C): C.3 — integration tests SpinFreeRoulette (real-DB) + audit_log whitelist parity` (последний коммит перед docs-коммитом C.5).
