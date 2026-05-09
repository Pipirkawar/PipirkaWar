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

**На `main`:** последний смерженный PR — **3.4-B** (PR `<pending>`, `<merge_commit>`) — persistence-слой инвентаря: новая таблица `items` (`player_id` BIGINT FK→users.id CASCADE, `item_id` VARCHAR(64), `enchant_level` INT default 0, `acquired_at` TIMESTAMPTZ; composite PK `(player_id, item_id)`); миграция `0021_items` (up/down round-trip); ORM `ItemORM` + порт `IItemRepository(Protocol)` + `ItemNotFoundError(InventoryDomainError)` + `ItemCategory.from_slot(Slot)` (ГДД §2.6/§2.8.1: 8 слотов → 3 категории); `SqlAlchemyItemRepository` (get/add/update_enchant_level) с `_category_for_item_id(...)` lookup-ом из `IBalanceConfig.items_catalog` (категория не хранится в БД). 24 новых теста (5 миграционных + 17 репо + 4 unit-теста на `from_slot`/`ItemNotFoundError`); local `make ci`: **4664 passed / 2 skipped, coverage 95.47%**. Перед ним — **3.4-A** (PR #117, `5c21d4e`) — каркас доменов «Заточка»: пакет `domain/inventory/` (`Item` / `ItemCategory` / `pick_enchant_outcome`) + pydantic `EnchantmentConfig` + секция `enchantment` в `balance.yaml`. Перед ним — **3.6 design doc** (PR #116, `f7d671f`) — docs-only. Перед ним — **3.3-D** (PR #115, `5d6c9a3`) — финальный PR Спринта 3.3 «Рейд-боссы». **Закрыт Спринт 3.3 «Рейд-боссы»**, **активен Спринт 3.4 «Заточка предметов»** (закрыты 3.4-A и 3.4-B; в работе **3.4-C**).

**Текущая ветка** — `devin/<timestamp>-sprint-3-4-C-enchant-use-case` от `main = <merge_commit_3.4-B>`, **текущий feature-PR** Спринта 3.4-C «Application use-case `EnchantItem` + audit + анти-чит trip-wire + `ScrollORM`/миграция `0022_scrolls`».

Перед `3.4-A` (PR #117): **3.6 design doc** (PR #116, `f7d671f`) — docs-only. Перед ним: **3.3-D** (PR #115, `5d6c9a3`) — bot-handler `/boss` + lobby-UI + локали + APScheduler-фабрики + 3 нотификатора + use-case `CancelBossFight` + raider-loss length-вычеты + integration-тест scroll-drop частот. Перед ним: **3.3-C** (PR #114, `d08985e`) — доменный сервис `boss_round_resolution` + use-case-ы `RunBossRound` / `FinishBossFight`. Перед ним: **3.3-B** (PR #113, `9c859b7`), **3.3-A** (PR #112, `dbb9b1c`); **3.2-D** (PR #111, `89e4f0a`), **3.2-C** (PR #110, `2333297`), **3.2-B** (PR #109, `e27968b`), **3.2-A** (PR #108, `fe959c6`); **3.1-E** (PR #107, `5c1b26f`) и PR-ы Спринтов 3.1 (#99–#106) и 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а: 3.2-A → 3.2-D). **Закрыт Спринт 3.3 «Рейд-боссы»** (4 PR-а: 3.3-A + 3.3-B + 3.3-C + 3.3-D). **Активен Спринт 3.4 «Заточка предметов»** ([`development_plan.md`](development_plan.md) §6.3.4) — закрыты **3.4-A** (каркас домена + балансовый конфиг) и **3.4-B** (persistence-слой `items`), следующий PR — **3.4-C** «Application use-case `EnchantItem` + audit + анти-чит trip-wire + `ScrollORM`/миграция `0022_scrolls`» по чек-листу ниже.

**Roadmap (после Спринта 3.4 → 3.5):**
- **Спринт 3.4 «Заточка предметов»** ([`development_plan.md`](development_plan.md) §6.3.4) — **активный**, 4 PR-а (3.4-A/B/C/D).
- **Спринт 3.5 «Free-to-play рулетка»** ([`development_plan.md`](development_plan.md) §6.3.5) — после 3.4.
- **Спринт 3.6 «Бонус-за-племена в Предсказателе»** 🎯 ([`development_plan.md`](development_plan.md) §6.3.6, ГДД §11.1) — **новый, добавлен этим docs-PR**. Виральная мини-механика: за каждое активное племя (status='active', участников `>3`, игрок — член) `/predict` начисляет `+1 см` к базовому `uniform(1,20)`, cap `+131 см` (итого `≤ 151 см`). Отдельный лимит anti-cheat (`source = "oracle_tribe_bonus"` НЕ входит в organic 24h/7d). Display: явная строка `+N см за племена` в результате `/predict`. Снапшот — live в момент `/predict`. **Реализация — после 3.5**, 1–2 PR-а (3.6-A: domain + config + use-case + anti-cheat; 3.6-B: bot UI + локали + закрытие).

---

## 🎯 Активный спринт — Спринт 3.4 «Заточка предметов» 🪛

> Цель спринта (по [`development_plan.md`](development_plan.md) §6.3.4 «Спринт 3.4 — Заточка предметов»): sink-механика для лишних СМ. Зависит от 3.1 (источники скроллов из mountain/dungeon) и 3.3 (boss-drop из рейда). Доменный слой инвентаря — расширение агрегата `Item` полем `enchant_level: int (0..30)` + категории `weapon`/`armor`/`jewelry` для слотов (ГДД §2.6, §2.8.1). Бот-UI с warnings/confirmations (ГДД §2.8.7); audit-trail (`ITEM_ENCHANT_ATTEMPT`); анти-чит trip-wire на аномальные серии успехов на высоких тирах. Стартовые дефолты весов исходов всех уровней `0..29` уже зафиксированы в ГДД §2.8.6 (полные таблицы regular/blessed) — копируются в `balance.yaml` как есть.

**Скоуп — 9 задач из плана:**

- **3.4.1** — Domain: расширение `Item`-агрегата полем `enchant_level: int (0..30)` + категории `weapon`/`armor`/`jewelry` (см. ГДД §2.6, §2.8.1). Доменный VO `Scroll(category, blessed: bool)`. Domain errors `WrongScrollCategory`, `MaxLevelReached`, `ItemDestroyed`. **Критерий:** Юнит-тесты на каждое правило; mypy --strict.
- **3.4.2** — Persistence: миграция Alembic `add_enchant_level_to_items` + ORM-маппинг + `IItemRepository.update_enchant_level(...)`. **Критерий:** Integration-тесты: round-trip, default `enchant_level=0` для legacy-предметов.
- **3.4.3** — Application: use-case `EnchantItem(*, player_id, item_id, scroll_id) -> EnchantOutcome`. Внутри: load + check category + roll исход через `IRandom` + audit `ITEM_ENCHANT_ATTEMPT` + idempotency-key. **Критерий:** Юнит: всех 4 (regular) и 5 (blessed) исходов; idempotency повторного применения; категория-mismatch → `WrongScrollCategory`.
- **3.4.4** — Доменный picker `pick_enchant_outcome(*, level, blessed, weights)` — чистая функция. **Критерий:** Юнит-тесты на: (a) safe-zone forced-success, (b) все 4/5 исходов в каждом тире, (c) `clamp(0, 30)` на нижней границе.
- **3.4.5** — Балансовый конфиг: pydantic `EnchantmentConfig` с инвариантами (см. ГДД §2.8.6: сумма весов = 1.0 на каждой группе исходов; safe-zone-zero для drop/destroy; `blessed_outcomes_per_level["29"].success_2 == 0.0`, см. ГДД §2.8.4). Стартовые дефолты — копируются из ГДД §2.8.6. **Критерий:** Юнит-тесты на pydantic-валидаторы; интеграционный тест: дефолтный `balance.yaml` парсится без ошибок и сумма весов на каждом уровне = 1.0 ± ε.
- **3.4.6** — Bot-handler `/enchant <item_id> <scroll_id>` или callback из карточки предмета. UX: предупреждение → подтверждение → ролл → результат с emoji-индикатором тира (ГДД §2.8.7). **Критерий:** Handler-тесты; визуальная проверка предупреждений в RU+EN.
- **3.4.7** — Локализация ключей `enchant-*` (RU+EN): `enchant-warning-regular`, `enchant-warning-blessed`, `enchant-success`, `enchant-no-effect`, `enchant-drop`, `enchant-destroy`, `enchant-tier-{safe,easy,hard,very-hard,extreme,impossible}`, `enchant-wrong-category`. **Критерий:** Все ключи в обоих файлах; e2e-snapshot.
- **3.4.8** — Отображение `+N` рядом с именем предмета во всех местах: `/profile`, инвентарь, нотификации о дропе, audit-лог. **Критерий:** Снэпшот-тесты презентеров.
- **3.4.9** — Trip-wire анти-чита: аномальные серии успехов на высоких тирах → admin alert (event `ENCHANT_ANOMALY` в `audit_log`). **Критерий:** Юнит-тест: 10 подряд успехов на тире `+18→+25` → alert.

**Декомпозиция Спринта 3.4 на фичевые PR-ы (предложение):**

- **3.4-A — Каркас доменов «Заточка» + балансовый конфиг.** Этот PR (открывается следующим). Расширение агрегата `Item` (поле `enchant_level: int (0..30)`, категория `weapon`/`armor`/`jewelry`); VO `Scroll(category, blessed: bool)`; domain errors (`WrongScrollCategory`, `MaxLevelReached`, `ItemDestroyed`); чистый picker `pick_enchant_outcome(*, level, blessed, weights, random)`; pydantic `EnchantmentConfig` с инвариантами + дефолты в `balance.yaml` (стартовые таблицы из ГДД §2.8.6). Юнит-тесты на каждый invariant + статистический тест picker-а на `n=10000` rolls на каждом тире. Покрывает задачи плана **3.4.1, 3.4.4, 3.4.5**. Без миграции и без use-case-а — это 3.4-B/C.
- **3.4-B — Persistence-слой инвентаря (создание `items`-таблицы).** Текущий PR. **Корректировка скоупа на старте 3.4-B:** план §3.4.2 говорил «миграция `add_enchant_level_to_items`» — подразумевалось, что таблица `items` уже существует. Реальность (на `main = 5c21d4e`): **таблицы `items` нет**, последняя миграция — `0020_boss_fights.py`; в `application/bosses/finish_boss_fight.py:35` явный комментарий «реальная инвентарная инфраструктура — 3.4-B и далее». Поэтому 3.4-B **создаёт** `items`-таблицу с нуля (`player_id` BIGINT FK → `users.id`, `item_id` VARCHAR(64) — каталожная ссылка `item.<slot>.<short>`, `enchant_level` INT default 0, `acquired_at` TIMESTAMP). Composite PK `(player_id, item_id)` — каждый каталожный предмет — единственная инстанция на игрока (ГДД §2.6 «Не копится: надеть или выбросить»; владение/equipment-state — отдельный концерн, выйдет в 3.4-C/D). Категория `weapon`/`armor`/`jewelry` **не хранится** в таблице — выводится из `Slot` (как и в `forest_run` репо: `_columns_to_drop` + `IBalanceConfig`). `IItemRepository` порт (`domain/inventory/ports.py`) с методами `get(player_id, item_id) -> Item`, `add(player_id, item_id, now) -> Item`, `update_enchant_level(player_id, item_id, new_level) -> Item`. `ItemNotFoundError` (extends `InventoryDomainError`). SQLAlchemy-импл (`infrastructure/db/repositories/items.py`) с балансом-вытяжкой `slot → category` через `IBalanceConfig.items_catalog`. **Скроллы откладываются в 3.4-C** (вместе с `EnchantItem`-use-case-ом — там и так нужно их грузить). Покрывает **3.4.2**, частично готовит почву под **3.4.3** (порт + ItemNotFoundError).
- **3.4-C — Application use-case `EnchantItem` + audit + анти-чит trip-wire.** `application/inventory/enchant_item.py` с use-case-ом `EnchantItem(*, player_id, item_id, scroll_id) -> EnchantOutcome`: load Item + load Scroll + check category-match (иначе `WrongScrollCategory`) + spend Scroll (consume from inventory) + roll исход через `IRandom` + audit `ITEM_ENCHANT_ATTEMPT` + idempotency-key (`enchant:{player_id}:{scroll_id}`); audit-action `ITEM_ENCHANT_ATTEMPT` whitelist в `domain/shared/ports/audit.py`. Trip-wire `ENCHANT_ANOMALY` (10 подряд успехов на тирах `+18→+25` → admin alert). Юнит-тесты на все 4/5 исходов; idempotency; category-mismatch; trip-wire. Покрывает **3.4.3, 3.4.9**.
- **3.4-D — Bot UI + локали + display + закрытие Спринта 3.4.** Bot-handler `/enchant <item_id> <scroll_id>` + callback из карточки предмета (`/profile` → inventory → item card → «Заточить»); UX: warning → confirmation → roll → result с emoji-тиром. Локали `enchant-*` (RU+EN parity, ~10–12 ключей × 2 языка). Display `+N` рядом с именем предмета во всех местах (`/profile`, инвентарь, нотификации о дропе, audit-лог). Покрывает **3.4.6, 3.4.7, 3.4.8**.

**Финальный коммит каждого PR-а Спринта 3.4** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.4-X: ...») + пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния>`, передвинуть чек-лист на следующий PR (или закрыть Спринт 3.4 на 3.4-D и расписать чек-лист **первого PR-а Спринта 3.5** «Free-to-play рулетка» по [`development_plan.md`](development_plan.md) §6.3.5).

---

## 📝 Чек-лист текущего PR (Спринт 3.4-C — Application use-case `EnchantItem` + audit + анти-чит trip-wire + `ScrollORM`)

> Этот PR — третий PR Спринта 3.4. Поднимает application-слой заточки поверх persistence-а 3.4-B: use-case `EnchantItem(*, player_id, item_id, scroll_id) -> EnchantOutcome` (load Item + load Scroll + check category + roll исход через `IRandom` + audit + idempotency), плюс `ScrollORM` + миграция `0022_scrolls` (стэкаемые скроллы — `(player_id, scroll_id)` PK + `qty INT`), плюс анти-чит trip-wire `ENCHANT_ANOMALY` (10 подряд успехов на тирах `+18→+25` → admin alert). Без bot-UI (3.4-D). Покрывает задачи плана **3.4.3, 3.4.9** + миграцию для `Scroll`-агрегата.

- [ ] Дождаться мерджа `3.4-B` в `main` (этот PR).
- [ ] `git fetch && git checkout main && git pull`.
- [ ] Создать ветку `devin/<timestamp>-sprint-3-4-C-enchant-use-case` от `main`.
- [ ] **C.0 — Обновить `current_tasks.md`** под старт Спринта 3.4-C: пересобрать «Снимок состояния» под `main = <merge_commit_3.4-B>`, перенести чек-лист на C.1–C.X.
- [ ] **C.1 — Доменный VO `Scroll(category, blessed: bool)`** (если ещё не в `domain/inventory/entities.py` после 3.4-A) + `IScrollRepository(Protocol)` (`get(player_id, scroll_id) -> Scroll`, `consume(player_id, scroll_id, qty=1) -> None` (атомарный декремент), `add(player_id, scroll_id, qty, now)`). `ScrollNotFoundError(InventoryDomainError)` + `ScrollOutOfStockError(InventoryDomainError)`.
- [ ] **C.2 — ORM `ScrollORM` + миграция Alembic `0022_scrolls`**: `(player_id BIGINT FK→users.id, scroll_id VARCHAR(64), qty INT NOT NULL CHECK qty >= 0, acquired_at TIMESTAMPTZ)`, composite PK `(player_id, scroll_id)`. `qty=0`-строки можно удалять или оставлять (компромисс на проектирование). Зарегистрировать в `models/__init__.py` + `tests/integration/db/conftest.py`.
- [ ] **C.3 — `SqlAlchemyScrollRepository`**: `get / consume(qty) / add(qty)`. `consume` — `UPDATE qty = qty - :n WHERE player_id = :p AND scroll_id = :s AND qty >= :n`, `rowcount == 0 → ScrollOutOfStockError` (отличает от `NotFound` через предварительный `SELECT EXISTS`).
- [ ] **C.4 — Application use-case `EnchantItem`** (`application/inventory/enchant_item.py`): `__init__(*, item_repo, scroll_repo, balance, random, audit, idempotency, clock)`. `__call__(*, player_id, item_id, scroll_id, idempotency_key) -> EnchantOutcome`: load Item + load Scroll + check `item.matches_scroll(scroll)` (иначе `WrongScrollCategoryError`) + consume Scroll (qty -= 1) + `pick_enchant_outcome(level=item.enchant_level, blessed=scroll.blessed, config=balance.get().enchantment, random=random)` + apply outcome (`+1` / `no_effect` / `drop` / `destroy` / blessed-варианты) + persist через `update_enchant_level` (или `delete` при `destroy`/`drop`) + audit `ITEM_ENCHANT_ATTEMPT`-action + idempotency-key `enchant:{idempotency_key}`. **DTO `EnchantOutcome`** с полями `outcome: RegularEnchantOutcome | BlessedEnchantOutcome`, `old_level: int`, `new_level: int`, `item_destroyed: bool`, `item_dropped: bool`. **`audit_log_source_whitelist`** в `domain/shared/ports/audit.py` пополняется `'item_enchant_attempt'`-action.
- [ ] **C.5 — Trip-wire `ENCHANT_ANOMALY`** (`application/inventory/anti_cheat.py` или интеграция в `EnchantItem`): после каждого успеха ведём rolling-window последних 10 попыток на тирах `+18→+25` (по `enchant_level до попытки`); если все 10 — `success`, пишем `ENCHANT_ANOMALY`-event в `audit_log` (admin alert). Юнит-тест на 10 подряд успехов → событие; на 9 + 1 fail → нет события.
- [ ] **C.6 — Юнит-тесты `EnchantItem`**: все 4 регулярных исхода (`success` / `no_effect` / `drop` / `destroy`) + все 5 blessed (`success_2` / `success_1` / `no_effect` / `drop_1` / `drop_2`); category-mismatch → `WrongScrollCategoryError`; missing item → `ItemNotFoundError`; missing scroll → `ScrollNotFoundError`; out-of-stock scroll → `ScrollOutOfStockError`; idempotency повторного применения с тем же ключом → возвращает кэшированный outcome без побочных эффектов; trip-wire (10 успехов подряд → `ENCHANT_ANOMALY`).
- [ ] **C.7 — Integration-тесты use-case-а** через `SqlAlchemyItemRepository` + `SqlAlchemyScrollRepository`: реальный round-trip успешной заточки `+0 → +1` (item update + scroll qty decrement + audit-row); destroy-исход `level=25` → item удалён из БД; idempotency через realDB.
- [ ] **C.8 — `make ci` локально:** ruff + mypy --strict + import-linter (4 contracts kept) + pytest зелёный + coverage gate (≥ 80%).
- [ ] **C.9 — Финальный док-коммит:** `history.md` + запись 3.4-C, `current_tasks.md` пересборка под старт **Спринта 3.4-D «Bot UI + локали + display + закрытие Спринта 3.4»**.
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

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

**Текущий PR — 3.4-B «Persistence-слой инвентаря (создание `items`-таблицы)» — в ревью** (ждёт зелёный GitHub CI и мердж).
- **Сделано:** доменный порт `IItemRepository` + `ItemNotFoundError` + `ItemCategory.from_slot`; ORM `ItemORM` + миграция `0021_items`; `SqlAlchemyItemRepository` (get/add/update_enchant_level); 24 новых теста. Локальный `make ci`: 4664 passed / 2 skipped, coverage 95.47%.
- **Следующий шаг:** ждём зелёный GitHub CI и мердж. После слияния — старт ветки `devin/<timestamp>-sprint-3-4-C-enchant-use-case` от `main`, C.0–C.9 по чек-листу выше.
- **Открытые блокеры:** нет.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Заточка — финальные `success_probability`** (отложено до Спринта 3.4-A) — стартовые дефолты для всех уровней `0..29` зафиксированы в ГДД §2.8.6 (полные таблицы regular/blessed). После альфа-теста подбираются по метрикам; настройка через `balance.yaml` без релиза кода. Стартовый PR 3.4-A копирует эти дефолты как есть.
- **Заточка — bad-luck protection** (open question, см. ПД п.15 «Открытые вопросы») — нужна ли «гарантированный успех после N подряд провалов» в MVP механики или только в Фазе 4? Сейчас не предусмотрена (ГДД §2.8.8). На 3.4-C/D остаётся как есть; решение по итогам альфа-теста.
- **`AuditAction.SCROLL_DROP` сейчас audit-only** (с 3.3-C/D и 3.1-D) — до Спринта 3.4-B/C дроп-скроллов из рейдов и PvE **только** в `audit_log` пишется (не накапливается в инвентаре игрока). На 3.4-B (миграция инвентаря) + 3.4-C (use-case `EnchantItem`) этот же event начнёт сопровождаться реальной записью в `inventory.scrolls`. Симметрично `PveScrollDrop` из 3.1-D.

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`99dc9b1` — `feat(3.4-B): B.3+B.4 — SqlAlchemyItemRepository + 17 integration tests`. Следующий коммит — B.6 (финальный docs-коммит этой правки), после — PR в `main`.
