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

**На `main`:** последний смерженный PR — **3.6 design doc** (PR #116, `f7d671f`) — docs-only: новая виральная мини-механика «Бонус-за-племена в Предсказателе» (ГДД §11.1, ПД §6.3.6) + сквозное переименование «клан → племя» в документации (без рефакторинга `domain/clan/`, БД, локалей `clan-*` и команд `/clan*`). Добавил `Спринт 3.6` в `development_plan.md` (после Спринта 3.5). Не меняет код / тесты / БД. Перед ним — **3.3-D** (PR #115, `5d6c9a3`) — финальный PR Спринта 3.3 «Рейд-боссы»: bot-handler `/boss` + lobby-UI + презентер + локали `bosses-*` + APScheduler-фабрики + 3 нотификатора + use-case `CancelBossFight` + raider-loss length-вычеты + integration-тест scroll-drop частот; total `make ci` на `5d6c9a3`: **4485 passed / 2 skipped, coverage 95.43%**. **Закрыт Спринт 3.3 «Рейд-боссы»**.

**Текущая ветка** — `devin/1778305054-sprint-3-4-A-enchant-domain-skeleton` от `main = f7d671f`, **активный feature-PR** Спринта 3.4-A «Каркас доменов «Заточка» + балансовый конфиг». 2 коммита поверх main + 1 fix-коммит этой сессии: (а) `e551cc8` — `feat(3.4-A): inventory package + EnchantmentConfig + balance defaults` (создан пакет `domain/inventory/` — `entities.py` / `errors.py` / `services.py` / `__init__.py`, ~660 строк; pydantic `RegularLevelWeights` / `BlessedLevelWeights` / `EnchantmentTier` / `EnchantmentConfig` в `domain/balance/config.py` с инвариантами; `config/balance.yaml` `enchantment` секция со всеми 30 уровнями regular/blessed-весов из ГДД §2.8.6 + 6 тиров); (б) `dcc2b9c` — `chore(handoff): AGENT_HANDOFF for Sprint 3.4-A`; (в) `1afc19c` — `fix(3.4-A): wire EnchantmentConfig into BalanceConfig (close A.4)` (вбит `enchantment: EnchantmentConfig` в `BalanceConfig`, помощник `_build_valid_enchantment()` в `tests/unit/domain/balance/factories.py`). По чек-листу A.1–A.4 закрыты. Локальный `make ci` после `1afc19c` зелёный (4489 passed / 2 skipped, coverage 94.88%, 3 import-linter contracts kept, mypy 0 issues).

Перед `f7d671f`: **3.3-D** (PR #115, `5d6c9a3`) — bot-handler `/boss` + lobby-UI + локали + APScheduler-фабрики + 3 нотификатора + use-case `CancelBossFight` + raider-loss length-вычеты + integration-тест scroll-drop частот. Перед ним: **3.3-C** (PR #114, `d08985e`) — доменный сервис `boss_round_resolution` + use-case-ы `RunBossRound` / `FinishBossFight`. Перед ним: **3.3-B** (PR #113, `9c859b7`), **3.3-A** (PR #112, `dbb9b1c`); **3.2-D** (PR #111, `89e4f0a`), **3.2-C** (PR #110, `2333297`), **3.2-B** (PR #109, `e27968b`), **3.2-A** (PR #108, `fe959c6`); **3.1-E** (PR #107, `5c1b26f`) и PR-ы Спринтов 3.1 (#99–#106) и 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а: 3.2-A → 3.2-D). **Закрыт Спринт 3.3 «Рейд-боссы»** (4 PR-а: 3.3-A + 3.3-B + 3.3-C + 3.3-D). **Активен Спринт 3.4 «Заточка предметов»** ([`development_plan.md`](development_plan.md) §6.3.4) — текущий PR — **3.4-A** «Каркас доменов «Заточка» + балансовый конфиг» по чек-листу ниже.

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
- **3.4-B — Persistence + миграция инвентаря.** Миграция Alembic `add_enchant_level_to_items` + ORM-маппинг `Item` (через SQLAlchemy `Mapped[int]` с `default=0`) + `IItemRepository.update_enchant_level(...)`. Integration-тесты round-trip + default `enchant_level=0` для legacy-предметов. Покрывает **3.4.2**.
- **3.4-C — Application use-case `EnchantItem` + audit + анти-чит trip-wire.** `application/inventory/enchant_item.py` с use-case-ом `EnchantItem(*, player_id, item_id, scroll_id) -> EnchantOutcome`: load Item + load Scroll + check category-match (иначе `WrongScrollCategory`) + spend Scroll (consume from inventory) + roll исход через `IRandom` + audit `ITEM_ENCHANT_ATTEMPT` + idempotency-key (`enchant:{player_id}:{scroll_id}`); audit-action `ITEM_ENCHANT_ATTEMPT` whitelist в `domain/shared/ports/audit.py`. Trip-wire `ENCHANT_ANOMALY` (10 подряд успехов на тирах `+18→+25` → admin alert). Юнит-тесты на все 4/5 исходов; idempotency; category-mismatch; trip-wire. Покрывает **3.4.3, 3.4.9**.
- **3.4-D — Bot UI + локали + display + закрытие Спринта 3.4.** Bot-handler `/enchant <item_id> <scroll_id>` + callback из карточки предмета (`/profile` → inventory → item card → «Заточить»); UX: warning → confirmation → roll → result с emoji-тиром. Локали `enchant-*` (RU+EN parity, ~10–12 ключей × 2 языка). Display `+N` рядом с именем предмета во всех местах (`/profile`, инвентарь, нотификации о дропе, audit-лог). Покрывает **3.4.6, 3.4.7, 3.4.8**.

**Финальный коммит каждого PR-а Спринта 3.4** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.4-X: ...») + пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния>`, передвинуть чек-лист на следующий PR (или закрыть Спринт 3.4 на 3.4-D и расписать чек-лист **первого PR-а Спринта 3.5** «Free-to-play рулетка» по [`development_plan.md`](development_plan.md) §6.3.5).

---

## 📝 Чек-лист следующего PR (Спринт 3.4-A — Каркас доменов «Заточка» + балансовый конфиг)

> Этот PR — первый PR Спринта 3.4. Он закладывает доменный фундамент заточки: расширение агрегата `Item` (`enchant_level: int (0..30)`, категория слота), VO `Scroll(category, blessed: bool)`, domain errors (`WrongScrollCategory`, `MaxLevelReached`, `ItemDestroyed`), чистый доменный picker `pick_enchant_outcome` (детерминирован относительно `IRandom`), pydantic-конфиг `EnchantmentConfig` с инвариантами по ГДД §2.8.6 (сумма весов = 1.0; safe-zone-zero для drop/destroy; `blessed_outcomes_per_level["29"].success_2 == 0.0`). Стартовые дефолты для всех уровней `0..29` копируются из ГДД §2.8.6 в `balance.yaml`. Без миграции, без application use-case-а — это 3.4-B и 3.4-C.

- [x] Дождаться мерджа `3.3-D` в `main` → `main = 5d6c9a3` (PR #115). Затем мердж `3.6 design doc` (PR #116) → `main = f7d671f`.
- [x] `git fetch && git checkout main && git pull`.
- [x] Создана ветка `devin/1778305054-sprint-3-4-A-enchant-domain-skeleton` от `main`.
- [ ] **A.0 — Обновить `current_tasks.md`** под старт Спринта 3.4-A: пересобрать «Снимок состояния» под `main = f7d671f`, передвинуть чек-лист на 3.4-A, секцию «Что ровно сейчас в работе» переписать под старт. *(в работе)*
- [x] **A.1 — Расширение `Item`-агрегата** (создан пакет `domain/inventory/`): immutable `Item(id, category: ItemCategory, enchant_level: int 0..30)` с `with_enchant_level()`, `is_destroyed()`, `matches_scroll()`; helper `_scroll_to_item_category()`. `MAX_ENCHANT_LEVEL = 30`. VO `Scroll` живёт в существующем пакете `domain/enchantment/` (используется уже в 3.1-D / 3.3-D — ScrollCategory + Scroll dataclass).
- [x] **A.2 — Domain errors** (`domain/inventory/errors.py`): `InventoryDomainError` (база, наследник `DomainError`) + `WrongScrollCategoryError`, `MaxLevelReachedError`, `ItemDestroyedError`. Все с keyword-args, без `super().__init__`-ов message (стиль соседних domain-пакетов).
- [x] **A.3 — Доменный picker `pick_enchant_outcome`** (`domain/inventory/services.py`): чистая функция `pick_enchant_outcome(*, level, blessed, config, random) -> EnchantOutcome` — возвращает `RegularEnchantOutcome` (4) или `BlessedEnchantOutcome` (5). Safe-zone forced-success; weighted_choice через `_T = TypeVar("_T")` (Python 3.11-совместимо), `_WEIGHT_SCALE = 100_000`.
- [x] **A.4 — Pydantic `EnchantmentConfig`** (`domain/balance/config.py` строки ~723–940 + `config/balance.yaml` `enchantment` секция): `RegularLevelWeights`, `BlessedLevelWeights`, `EnchantmentTier`, `EnchantmentConfig` со всеми инвариантами (sum-to-1.0 ± 1e-6; safe-zone drop/destroy = 0.0 на level < safe_zone_max_level; `blessed_outcomes_per_level[max_level - 1].success_2 == 0.0` (ГДД §2.8.4); max_level == 30 хардкод; tiers покрывают [0, max_level] без дыр/пересечений). Стартовые дефолты для всех 30 уровней + 6 тиров скопированы в `balance.yaml`. **Поле `enchantment: EnchantmentConfig` вбито в `BalanceConfig`** (`1afc19c`).
- [ ] **A.5 — Юнит-тесты picker-а** (`tests/unit/domain/inventory/test_enchant_picker.py`): (a) safe-zone forced-success (10 rolls на level 0–`safe_zone_max-1` → все `success`); (b) все 4 (regular) и 5 (blessed) исходов в каждом тире (10000 rolls на каждом из тиров `safe`/`easy`/`hard`/`very-hard`/`extreme`/`impossible` → частоты в 3σ-bounds от заданных `weights`); (c) `clamp(0, 30)` на нижней границе (`drop` на level=0 → level остаётся 0, не уходит в -1). Симметрично `tests/unit/domain/economy/test_scroll_drops.py` (3.1-D) — тот же `_bernoulli_bounds`-приём.
- [ ] **A.6 — Юнит-тесты агрегата `Item` + VO `Scroll` + errors** (`tests/unit/domain/inventory/test_item.py`, `test_scroll.py`, `test_errors.py`): default `enchant_level=0`; `with_enchant_level(31)` → `MaxLevelReached`; `with_enchant_level(-1)` → `MaxLevelReached`; `Scroll(category=WEAPON, blessed=False)` — frozen, equality-by-value; `WrongScrollCategory(scroll_category=WEAPON, item_category=ARMOR)` — error message + attributes.
- [ ] **A.7 — Pydantic-валидатор тесты** (`tests/unit/infrastructure/balance/test_enchantment_config.py`): дефолтный `balance.yaml` парсится без ошибок; сумма весов на каждом уровне = 1.0 ± ε; safe-zone-zero для `drop`/`destroy`; `blessed_outcomes_per_level["29"].success_2 == 0.0`; ошибки парсинга при нарушении инвариантов.
- [ ] **A.8 — Architectural guard** (`tests/unit/architecture/test_dependency_layers.py` или новый `test_inventory_layer_isolation.py`): новый поддомен `domain/inventory/` зависит только от `domain/shared/`, `domain/player/` (для `player_id`) — не от `application/`, `infrastructure/`, `bot/`. import-linter contract в `pyproject.toml::[tool.importlinter]`.
- [ ] **A.9 — `make ci` локально:** ruff format + ruff check, mypy --strict 0 issues, import-linter ≥ 3 contracts kept, pytest все зелёные, coverage gate (≥ 80%).
- [ ] **A.10 — Финальный док-коммит:** `history.md` +запись 3.4-A, `current_tasks.md` пересборка под старт **Спринта 3.4-B «Persistence + миграция инвентаря»**.
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Текущий PR — Спринт 3.4-A «Каркас доменов «Заточка» + балансовый конфиг»:** доменный фундамент заточки. Закрыты A.1–A.4 (предыдущая сессия + fix-коммит этой сессии для A.4-wiring): создан пакет `src/pipirik_wars/domain/inventory/` (`entities.py` — `Item` / `ItemCategory` / outcome enums; `errors.py` — `InventoryDomainError` + 3 domain-errors; `services.py` — чистый picker `pick_enchant_outcome`); добавлены pydantic-классы `RegularLevelWeights` / `BlessedLevelWeights` / `EnchantmentTier` / `EnchantmentConfig` в `domain/balance/config.py` со всеми инвариантами по ГДД §2.8.6; `config/balance.yaml` обогащён секцией `enchantment` со всеми 30 уровнями + 6 тиров; `EnchantmentConfig` вбит в `BalanceConfig`. Локальный `make ci` зелёный (4489 passed / 2 skipped, coverage 94.88%).
- **Текущий шаг:** A.5 — юнит-тесты picker-а; затем A.6 (Item + errors) → A.7 (`EnchantmentConfig` invariants) → A.8 (import-linter) → A.9 (`make ci` зелёный, coverage ≥ 80%) → A.10 (финальный docs-коммит) → удалить `AGENT_HANDOFF.md` → push → PR в `main` → ожидание зелёного GitHub CI.
- **Открытые блокеры:** нет.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Заточка — финальные `success_probability`** (отложено до Спринта 3.4-A) — стартовые дефолты для всех уровней `0..29` зафиксированы в ГДД §2.8.6 (полные таблицы regular/blessed). После альфа-теста подбираются по метрикам; настройка через `balance.yaml` без релиза кода. Стартовый PR 3.4-A копирует эти дефолты как есть.
- **Заточка — bad-luck protection** (open question, см. ПД п.15 «Открытые вопросы») — нужна ли «гарантированный успех после N подряд провалов» в MVP механики или только в Фазе 4? Сейчас не предусмотрена (ГДД §2.8.8). На 3.4-C/D остаётся как есть; решение по итогам альфа-теста.
- **`AuditAction.SCROLL_DROP` сейчас audit-only** (с 3.3-C/D и 3.1-D) — до Спринта 3.4-B/C дроп-скроллов из рейдов и PvE **только** в `audit_log` пишется (не накапливается в инвентаре игрока). На 3.4-B (миграция инвентаря) + 3.4-C (use-case `EnchantItem`) этот же event начнёт сопровождаться реальной записью в `inventory.scrolls`. Симметрично `PveScrollDrop` из 3.1-D.

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`1afc19c` — `fix(3.4-A): wire EnchantmentConfig into BalanceConfig (close A.4)`. Следующие коммиты — A.0 (этот док-апдейт), потом A.5/A.6/A.7 (тесты).
