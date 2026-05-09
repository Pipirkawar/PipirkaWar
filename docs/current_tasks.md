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

**На `main`:** последний смерженный PR — **3.4-D** (PR #<TBD>, `<merge_3_4_D>`) — bot-UI заточки: команда `/inventory` + `InventoryPresenter` (карточка предметов с `+N` суффиксом + стэки скроллов + inline-кнопка «Заточить»); команда `/enchant <item_id> <scroll_id>` + `EnchantPresenter` (warning-карточка с emoji-индикатором тира + confirm/cancel-кнопки + result-сообщение для всех 4+5 исходов); use-case `GetInventory(player_id) → InventoryView` (`application/inventory/get_inventory.py`); расширение портов `IItemRepository.list_by_player` + `IScrollRepository.list_by_player` + `ScrollStack` DTO; локали `enchant-*` + `inventory-*` (~40 ключей × RU/EN); inline-кнопки `inv:enchant`/`inv:pick`/`inv:pickcancel` в карточке `/inventory` с picker-flow (0/1/2 подходящих скролла); composition root wiring `EnchantItem` + `GetInventory` + 3 репозитория в `bot/main.py`. Хелпер `enchant_suffix(level: int) -> str` — `" +N"` для `level > 0`, `""` для `level=0`. Идемпотентность confirm-кнопки через `idempotency_key = f"{tg_user_id}:{message_id}"`. local `make ci`: **4941 passed / 2 skipped, coverage 95.59%**. Перед ним — **3.4-C** (PR #119, `e490095`) — application-слой заточки (`EnchantItem` + `IScrollRepository` + audit + trip-wire + `ScrollORM`); **3.4-B** (PR #118, `7259fad`) — persistence-слой инвентаря; **3.4-A** (PR #117, `5c21d4e`) — каркас доменов; **3.6 design doc** (PR #116, `f7d671f`). **Закрыт Спринт 3.3 «Рейд-боссы»**, **закрыт Спринт 3.4 «Заточка предметов»** (4 PR-а: 3.4-A/B/C/D). **Активен Спринт 3.5 «Free-to-play рулетка»** ([`development_plan.md`](development_plan.md) §6.3.5).

**Текущая ветка** — старт **Спринта 3.5 «Free-to-play рулетка»** будет открыт от свежего `main = <merge_3_4_D>` после мерджа PR #<TBD> (3.4-D). Имя ветки следующего PR-а: `devin/<unix_ts>-sprint-3-5-A-roulette-domain` (или аналог по декомпозиции — см. ниже).

Перед `3.4-D`: **3.4-C** (PR #119, `e490095`) — application-слой заточки. Перед ним: **3.4-B** (PR #118, `7259fad`), **3.4-A** (PR #117, `5c21d4e`); **3.6 design doc** (PR #116, `f7d671f`); **3.3-D** (PR #115, `5d6c9a3`); **3.3-C** (PR #114, `d08985e`); **3.3-B** (PR #113, `9c859b7`), **3.3-A** (PR #112, `dbb9b1c`); **3.2-A→D** (#108–#111); **3.1-E** (PR #107, `5c1b26f`) и PR-ы Спринтов 3.1 (#99–#106) и 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а). **Закрыт Спринт 3.3 «Рейд-боссы»** (4 PR-а). **Закрыт Спринт 3.4 «Заточка предметов»** (4 PR-а: 3.4-A/B/C/D). **Активен Спринт 3.5 «Free-to-play рулетка»** ([`development_plan.md`](development_plan.md) §6.3.5).

**Roadmap (после Спринта 3.5 → далее):**
- **Спринт 3.5 «Free-to-play рулетка»** ([`development_plan.md`](development_plan.md) §6.3.5) — **активный**, ожидаемая декомпозиция 3–4 PR-а (см. ниже).
- **Спринт 3.6 «Бонус-за-племена в Предсказателе»** 🎯 ([`development_plan.md`](development_plan.md) §6.3.6, ГДД §11.1) — после 3.5. Виральная мини-механика: за каждое активное племя `/predict` начисляет `+1 см` к базовому `uniform(1,20)`, cap `+131 см` (итого `≤ 151 см`). Отдельный лимит anti-cheat (`source = "oracle_tribe_bonus"` НЕ входит в organic 24h/7d). 1–2 PR-а (3.6-A: domain + config + use-case + anti-cheat; 3.6-B: bot UI + локали + закрытие).

---

## 🎯 Активный спринт — Спринт 3.5 «Free-to-play рулетка» 🎰

> Цель спринта (по [`development_plan.md`](development_plan.md) §6.3.5 «Спринт 3.5 — Free-to-play рулетка»): монетизация-альтернатива через free-to-play-рулетку. Игрок раскручивает рулетку (1× / день бесплатно + N× за внутреннюю валюту); рулетка выпадает с одним из тиров (common/uncommon/rare/epic/legendary), внутри тира — пул призов (длина / скроллы / предметы / boost-эффекты). См. ГДД §11 «Монетизация» (если соответствующий раздел есть) и ПД §6.3.5.

**Скоуп — задачи плана 3.5.* (детали — в [`development_plan.md`](development_plan.md)):**

- Domain: каталог тиров + пулов призов; weighted_choice по тирам; pydantic `RouletteConfig` с инвариантами (сумма весов = 1.0 на каждом уровне).
- Persistence: таблица `roulette_spins` (player_id, occurred_at, tier, prize_id, source); ORM + миграция Alembic `0023_roulette_spins`.
- Application: use-case `SpinRoulette(*, player_id, source) -> SpinResult` с idempotency и аудитом `ROULETTE_SPIN`.
- Bot UI: команда `/roulette` + warning/result-карточки + локали `roulette-*` (RU/EN parity).
- Anti-cheat: лимит 1× free spin/день (или согласно ГДД); audit-source НЕ входит в organic-окно.

**Декомпозиция Спринта 3.5 на фичевые PR-ы (предложение, уточняется на C.0):**

- **3.5-A — Каркас домена + балансовый конфиг.** `domain/roulette/` с `Tier` / `Prize` / `pick_roulette_prize(...)`; pydantic `RouletteConfig` с инвариантами; стартовые дефолты в `balance.yaml`. Юнит-тесты на picker + конфиг.
- **3.5-B — Persistence-слой.** `IRouletteSpinRepository` + ORM `RouletteSpinORM` + миграция Alembic `0023_roulette_spins` + SQL-impl. Integration-тесты на round-trip.
- **3.5-C — Application use-case `SpinRoulette` + audit + ограничение 1× free/день.** `application/roulette/spin_roulette.py`; audit-action `ROULETTE_SPIN` whitelist; daily-cooldown-проверка через `IRouletteSpinRepository.last_free_spin_at(...)`. Юнит + integration-тесты.
- **3.5-D — Bot UI + локали + display + закрытие Спринта 3.5.** Команда `/roulette` + warning/spin/result-карточки + локали `roulette-*` (RU/EN parity) + composition root wiring. Закрытие Спринта.

**Финальный коммит каждого PR-а Спринта 3.5** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.5-X: ...») + пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния>`, передвинуть чек-лист на следующий PR (или закрыть Спринт 3.5 на 3.5-D и расписать чек-лист **первого PR-а Спринта 3.6** «Бонус-за-племена в Предсказателе»).

---

## 📝 Чек-лист следующего PR (Спринт 3.5-A — Каркас домена «Рулетка» + балансовый конфиг)

> Этот PR — первый PR Спринта 3.5. Создаёт каркас домена `domain/roulette/` (`Tier`, `Prize`, чистая `pick_roulette_prize(...)`), pydantic `RouletteConfig` с инвариантами и стартовые дефолты в `balance.yaml`. Без use-case-а и без миграции — это 3.5-B/C.

- [ ] Дождаться мерджа `3.4-D` в `main` (PR #<TBD>, `<merge_3_4_D>`).
- [ ] `git fetch && git checkout main && git pull`.
- [ ] Создать ветку `devin/<unix_ts>-sprint-3-5-A-roulette-domain` от свежего `main`.
- [ ] **A.0 — Обновить `current_tasks.md`** под старт Спринта 3.5-A: пересобрать «Снимок состояния» под актуальный `main`, расписать чек-лист 3.5-A.
- [ ] **A.1 — Доменный пакет `domain/roulette/`**:
  - `entities.py` — `Tier(StrEnum)` (`COMMON`/`UNCOMMON`/`RARE`/`EPIC`/`LEGENDARY`), `Prize(frozen=True, slots=True)` с `prize_id`/`prize_kind`/`magnitude`.
  - `services.py` — чистая `pick_roulette_prize(*, config, random) -> tuple[Tier, Prize]` (weighted_choice по тирам → внутри тира — weighted_choice по призам).
  - `errors.py` — `RouletteDomainError(DomainError)` + `InvalidRouletteConfigError`.
  - `__init__.py` — экспорт всех публичных символов.
  - **Критерий:** `mypy --strict` 0 issues; юнит-тесты на picker (safe-branch, weighted distribution на `n=10000` rolls, edge-cases).
- [ ] **A.2 — Балансовый конфиг `RouletteConfig`** (`domain/balance/config.py`):
  - pydantic-модель с двумя уровнями: `tier_weights: dict[Tier, float]` (сумма = 1.0 ± ε) + `prizes_per_tier: dict[Tier, dict[str, float]]` (сумма весов внутри тира = 1.0 ± ε).
  - Стартовые дефолты — копировать из ГДД §11.x (или ПД §6.3.5; уточняется на C.0).
  - Секция `roulette` в `balance.yaml`.
  - **Критерий:** pydantic-валидаторы; integration-тест: дефолтный `balance.yaml` парсится без ошибок и сумма весов = 1.0 ± ε на каждом уровне.
- [ ] **A.3 — `make ci` локально:** ruff + mypy --strict + import-linter (4 contracts kept) + pytest зелёный + coverage gate (≥ 80%).
- [ ] **A.4 — Финальный док-коммит:** `history.md` + запись 3.5-A, `current_tasks.md` пересборка под старт **Спринта 3.5-B «Persistence-слой рулетки»**.
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

**Текущий PR — 3.4-D «Bot UI заточки + локали + display + закрытие Спринта 3.4»** — D.1d/D.4/D.3/D.5/D.7/D.8/D.9 закрыты, осталось открыть PR в `main` и дождаться зелёного CI.
- **На `main`:** 3.4-C смержен (PR #119, `e490095`). 3.4-D открыт от фреш-`main`.
- **Что закрыли в 3.4-D:** см. архив чек-листа выше — 9 шагов (D.0–D.9 + D.½ + D.1a–D.1d) полностью покрыты. Спринт 3.4 «Заточка предметов» закрывается этим PR.
- **Открытые блокеры:** нет.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Заточка — финальные `success_probability`** — стартовые дефолты для всех уровней `0..29` зафиксированы в ГДД §2.8.6 (полные таблицы regular/blessed). После альфа-теста подбираются по метрикам; настройка через `balance.yaml` без релиза кода.
- **Заточка — bad-luck protection** (open question, см. ПД п.15 «Открытые вопросы») — нужна ли «гарантированный успех после N подряд провалов» в MVP механики или только в Фазе 4? Сейчас не предусмотрена (ГДД §2.8.8); решение по итогам альфа-теста.
- **`AuditAction.SCROLL_DROP` всё ещё audit-only без write-trough в инвентарь** — рейды и PvE дропают скроллы только в `audit_log`, без `INSERT` в `scrolls`-таблицу. Это запланировано как отдельная задача в Спринте 3.4-E или после 3.5 (инвентарь готов с 3.4-B/C; нужен только wire-up в use-case-ах `FinishBossFight` / `FinishMountainRun` / `FinishDungeonRun`). Пока остаётся как есть.
- **`/profile` Equipment skeleton** — секция «экипировка» в `/profile` ещё не реализована (отложена до Спринта 1.3+ или равноуровневого с реализацией equipment-state). Когда поднимется, использует `enchant_suffix(...)` хелпер из 3.4-D.

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`5b77f06` — `feat(3.4-D): D.1d — inv: callback handler (enchant/pick/pickcancel) + tests` (последний коммит перед docs-коммитом D.9).
