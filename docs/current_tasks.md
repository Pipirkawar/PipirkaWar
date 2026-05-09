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

**На `main`:** последний смерженный PR — **3.4-C** (PR #119, `e490095`) — application-слой заточки: VO `Scroll(category, blessed)` + проперти `scroll_id`/`from_scroll_id`; порт `IScrollRepository` + `ScrollNotFoundError`/`ScrollOutOfStockError` + `IItemRepository.delete`; ORM `ScrollORM` + миграция `0022_scrolls` (composite PK `(player_id, scroll_id)`, `qty INT NOT NULL CHECK qty >= 0`); `SqlAlchemyScrollRepository` (get/consume/add); `AuditAction.ITEM_ENCHANT_ATTEMPT` + `AuditAction.ENCHANT_ANOMALY` (без новых `AuditSource`); доменный порт `IEnchantHistoryReader` + SQL-impl `SqlAlchemyEnchantHistoryReader` (читает `audit_log` с JSON-фильтрацией в Python); use-case `EnchantItem(*, item_repo, scroll_repo, balance, random, audit, idempotency, clock, enchant_history)` → `EnchantAttemptResult` DTO с 10-шаговым flow (idempotency `enchant:{key}` namespace → load Item → parse Scroll → matches_scroll → consume scroll qty=1 → pick_enchant_outcome → apply (update/delete) → audit → mark idempotency → trip-wire); trip-wire `ENCHANT_ANOMALY` (10 подряд success-ов на тирах `+18→+25`). 22 integration-теста на `SqlAlchemyScrollRepository` + 25 unit-тестов `EnchantItem` + 4 integration-теста use-case-а через realDB. local `make ci`: **4762 passed / 2 skipped, coverage 96%**. Перед ним — **3.4-B** (PR #118, `7259fad`) — persistence-слой инвентаря (`items`-таблица + миграция `0021_items` + `IItemRepository` + `SqlAlchemyItemRepository`). Перед ним — **3.4-A** (PR #117, `5c21d4e`) — каркас доменов «Заточка»: пакет `domain/inventory/` (`Item` / `ItemCategory` / `pick_enchant_outcome`) + pydantic `EnchantmentConfig` + секция `enchantment` в `balance.yaml`. Перед ним — **3.6 design doc** (PR #116, `f7d671f`). **Закрыт Спринт 3.3 «Рейд-боссы»**, **активен Спринт 3.4 «Заточка предметов»** (закрыты 3.4-A/B/C; в работе **3.4-D** — бот-UI + локали + display + закрытие Спринта).

**Текущая ветка** — `devin/1778323886-sprint-3-4-D-enchant-bot-ui` от `main = e490095`, **активный feature-PR** Спринта 3.4-D «Bot UI + локали + display + закрытие Спринта 3.4». Скоуп расширен Вариантом A (по решению пользователя): помимо чек-листа D.0–D.9 включает создание `/inventory`-команды + `InventoryPresenter` с нуля и расширение портов `IItemRepository.list_by_player` + `IScrollRepository.list_by_player`, потому что инвентарного UI в боте до 3.4-D вообще не было.

Перед `3.4-A` (PR #117): **3.6 design doc** (PR #116, `f7d671f`) — docs-only. Перед ним: **3.3-D** (PR #115, `5d6c9a3`) — bot-handler `/boss` + lobby-UI + локали + APScheduler-фабрики + 3 нотификатора + use-case `CancelBossFight` + raider-loss length-вычеты + integration-тест scroll-drop частот. Перед ним: **3.3-C** (PR #114, `d08985e`) — доменный сервис `boss_round_resolution` + use-case-ы `RunBossRound` / `FinishBossFight`. Перед ним: **3.3-B** (PR #113, `9c859b7`), **3.3-A** (PR #112, `dbb9b1c`); **3.2-D** (PR #111, `89e4f0a`), **3.2-C** (PR #110, `2333297`), **3.2-B** (PR #109, `e27968b`), **3.2-A** (PR #108, `fe959c6`); **3.1-E** (PR #107, `5c1b26f`) и PR-ы Спринтов 3.1 (#99–#106) и 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а: 3.2-A → 3.2-D). **Закрыт Спринт 3.3 «Рейд-боссы»** (4 PR-а: 3.3-A + 3.3-B + 3.3-C + 3.3-D). **Активен Спринт 3.4 «Заточка предметов»** ([`development_plan.md`](development_plan.md) §6.3.4) — закрыты **3.4-A** (каркас домена + балансовый конфиг), **3.4-B** (persistence-слой `items`) и **3.4-C** (use-case `EnchantItem` + audit + trip-wire + `ScrollORM`), следующий PR — **3.4-D** «Bot UI + локали + display + закрытие Спринта 3.4» по чек-листу ниже.

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

## 📝 Чек-лист текущего PR (Спринт 3.4-D — Bot UI + локали + display + закрытие Спринта 3.4)

> Этот PR — финальный PR Спринта 3.4. Поднимает bot-UI над use-case-ом `EnchantItem` (3.4-C): handler `/enchant <item_id> <scroll_id>` и/или callback из карточки предмета (`/profile` → inventory → item card → «Заточить»); UX warning → confirmation → roll → result с emoji-тиром. Локали `enchant-*` (RU+EN parity, ~10–12 ключей × 2 языка). Display `+N` рядом с именем предмета во всех местах (`/profile`, инвентарь, нотификации о дропе, audit-лог). Покрывает задачи плана **3.4.6, 3.4.7, 3.4.8**.

- [x] Дождаться мерджа `3.4-C` в `main` (PR #119, `e490095`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778323886-sprint-3-4-D-enchant-bot-ui` от `main = e490095`.
- [x] **D.0 — Обновить `current_tasks.md`** под старт Спринта 3.4-D: пересобрать «Снимок состояния» под `main = e490095`, расширить чек-лист (Вариант A: добавлены D.½, D.1a-D.1d).
- [ ] **D.½ — Расширить порты инвентаря**: `IItemRepository.list_by_player(player_id) → tuple[Item, ...]` + `IScrollRepository.list_by_player(player_id) → tuple[ScrollStack, ...]` (где `ScrollStack(scroll: Scroll, qty: int)` — DTO для UI). Реализация в `SqlAlchemyItemRepository` / `SqlAlchemyScrollRepository`. Integration-тесты (round-trip пустой инвентарь, многопредметный инвентарь, изоляция между игроками).
- [ ] **D.1a — Application use-case `GetInventory(player_id)`** → `InventoryView` DTO (`items: tuple[ItemView, ...]`, `scrolls: tuple[ScrollStackView, ...]`). `ItemView` содержит `item_id`, `display_name`, `category`, `enchant_level`. Use-case через `IItemRepository.list_by_player` + `IScrollRepository.list_by_player`, обогащает каталожными данными из `IBalanceConfig.items_catalog` (display_name, slot, rarity).
- [ ] **D.1b — Bot-handler `/inventory` + `InventoryPresenter`**: листинг items с `+N` и стеки скроллов с qty. Карточка предмета — отдельный inline-блок с кнопкой «Заточить» (если есть подходящий скролл) или disabled-hint «нужен скролл». Если инвентарь пуст — показать сообщение «инвентарь пуст, иди в лес/горы/боссы».
- [ ] **D.1c — Bot-handler `/enchant <item_id> <scroll_id>`** + `EnchantPresenter`: warning-карточка с вероятностями исходов (ГДД §2.8.7) → confirm-кнопка → `EnchantItem`-use-case → result-сообщение с итоговым уровнем, emoji-индикатором тира и локализованным исходом. Idempotency-key — `callback_id` или `message_id` confirm-кнопки.
- [ ] **D.1d — Callback-кнопка «Заточить»** в карточке предмета `/inventory`: если у игрока ровно 1 подходящий скролл (regular или blessed) → автоматический выбор; если оба — показать выбор «обычный / благословенный» (две кнопки); если нет — disabled с hint-ом «нет подходящего скролла».
- [ ] **D.2 — Локали `enchant-*` + `inventory-*`** (RU+EN, в `locales/ru.ftl` и `locales/en.ftl`): `enchant-warning-regular`, `enchant-warning-blessed`, `enchant-confirm`, `enchant-cancel`, `enchant-success` (с плейсхолдерами для старого/нового уровня), `enchant-no-effect`, `enchant-drop`, `enchant-destroy`, `enchant-tier-{safe,easy,hard,very-hard,extreme,impossible}`, `enchant-wrong-category`, `enchant-out-of-stock`, `enchant-item-not-found`, `inventory-empty`, `inventory-card`, `inventory-item-line`, `inventory-scroll-line`, `inventory-button-enchant`, `inventory-toast-no-scroll` (всего ~25 ключей × 2 языка = ~50). e2e snapshot-тест на RU/EN parity.
- [ ] **D.3 — Display `+N`**: презентеры `/profile`, `/inventory`, нотификации о дропе предмета (forest), audit-лога — все выводят `<item_name> +N` (или `<item_name>` при `enchant_level=0`). Снэпшот-тесты на каждый презентер.
- [ ] **D.4 — Composition root**: зарегистрировать `EnchantItem` + `GetInventory` use-case-ы + репозитории (`SqlAlchemyItemRepository`, `SqlAlchemyScrollRepository`, `SqlAlchemyEnchantHistoryReader`) в `bot/main.py`. Тест композиции (как `test_main_composition.py`) на резолв.
- [ ] **D.5 — Handler-тесты**: получение warning, confirm → success/no-effect/drop/destroy ответы, cancel-button, обработка всех ошибок (`WrongScrollCategoryError`, `ItemNotFoundError`, `ScrollNotFoundError`, `ScrollOutOfStockError`).
- [ ] **D.6 — Кнопка «Заточить»** входит в **D.1d** (см. выше).
- [ ] **D.7 — e2e snapshot-тесты** всех исходов на RU/EN в стиле `tests/e2e/test_*_flow.py`.
- [ ] **D.8 — `make ci` локально:** ruff + mypy --strict + import-linter (4 contracts kept) + pytest зелёный + coverage gate (≥ 80%).
- [ ] **D.9 — Финальный док-коммит:** `history.md` + запись 3.4-D, `current_tasks.md` пересборка под старт **Спринта 3.5 «Free-to-play рулетка»** (закрытие Спринта 3.4).
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

**Текущий PR — 3.4-C «Application use-case `EnchantItem` + audit + анти-чит trip-wire + `ScrollORM`»** — в работе.
- **На `main`:** 3.4-B смержен (PR #118, `7259fad`). 3.4-C открыт от фреш-`main`.
- **Разведка (важно):** VO `Scroll` уже живёт в `pipirik_wars.domain.enchantment.entities` (Спринт 3.1-D), со своим `ScrollCategory(StrEnum)` и вроде `ScrollCategory.WEAPON.value == "weapon_scroll"` (отличается от `ItemCategory.WEAPON.value == "weapon"` ­— это by design, см. `domain/inventory/__init__.py` docstring). `Item.matches_scroll(scroll)` сравнивает по `Enum.name`. `IItemRepository` + `ItemORM` + `SqlAlchemyItemRepository` уже есть.
- **Надо добавить:** порт `IScrollRepository` + 2 ошибки (`ScrollNotFoundError` / `ScrollOutOfStockError`); стабильный string-id для `Scroll` в persistence (`Scroll.scroll_id` property + classmethod `Scroll.from_scroll_id(...)` — формат `«или weapon_scroll:regular, или armor_scroll:blessed»`); ORM `ScrollORM` + миграцию `0022_scrolls` (`(player_id, scroll_id)` PK, `qty INT CHECK qty >= 0`); `SqlAlchemyScrollRepository` (get/consume/add); 2 новых audit-action (`ITEM_ENCHANT_ATTEMPT`, `ENCHANT_ANOMALY`); use-case `EnchantItem`; trip-wire `ENCHANT_ANOMALY` поиск (в `application/inventory/anti_cheat.py`).
- **Открытые блокеры:** нет.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Заточка — финальные `success_probability`** (отложено до Спринта 3.4-A) — стартовые дефолты для всех уровней `0..29` зафиксированы в ГДД §2.8.6 (полные таблицы regular/blessed). После альфа-теста подбираются по метрикам; настройка через `balance.yaml` без релиза кода. Стартовый PR 3.4-A копирует эти дефолты как есть.
- **Заточка — bad-luck protection** (open question, см. ПД п.15 «Открытые вопросы») — нужна ли «гарантированный успех после N подряд провалов» в MVP механики или только в Фазе 4? Сейчас не предусмотрена (ГДД §2.8.8). На 3.4-C/D остаётся как есть; решение по итогам альфа-теста.
- **`AuditAction.SCROLL_DROP` сейчас audit-only** (с 3.3-C/D и 3.1-D) — до Спринта 3.4-B/C дроп-скроллов из рейдов и PvE **только** в `audit_log` пишется (не накапливается в инвентаре игрока). На 3.4-B (миграция инвентаря) + 3.4-C (use-case `EnchantItem`) этот же event начнёт сопровождаться реальной записью в `inventory.scrolls`. Симметрично `PveScrollDrop` из 3.1-D.

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`7259fad` (на `main`) — мердж PR #118. Следующий коммит на ветке 3.4-C — C.0 (этот docs-snapshot), потом C.1 (`IScrollRepository` + `ScrollNotFoundError` + `ScrollOutOfStockError` + `Scroll.scroll_id`).
