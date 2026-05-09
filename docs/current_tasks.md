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

**На `main`:** последний смерженный PR — **3.3-D** (PR #115, `5d6c9a3`) — финальный PR Спринта 3.3 «Рейд-боссы»: bot-handler `/boss` + lobby-UI с inline-кнопками (`boss:show_lobby/join/leave/cancel`) + презентер `BossPresenter` + локали `bosses-*` (RU+EN parity, 39 ключей × 2 языка) + APScheduler-фабрики (`boss_lobby_close_factory` / `boss_round_tick_factory` / `boss_fight_finish_factory`) + 3 Telegram-нотификатора + use-case `CancelBossFight` + raider-loss length-вычеты при поражении + integration-тест частот scroll-drop-а. +153 unit-теста (47 handler / 35 notifiers / 71 presenter+parity); total `make ci`: **4485 passed / 2 skipped, coverage 95.43%**. **Закрыт Спринт 3.3 «Рейд-боссы»**.

**Текущая ветка** — `devin/1778303378-tribe-bonus-design-doc` от `main = 5d6c9a3` — **docs-only side-PR**: оформление новой виральной мини-механики «Бонус-за-племена в Предсказателе» (см. ГДД §11.1) + переименование «клан → племя» в документации (без рефакторинга `domain/clan/`, БД, локалей `clan-*` и команд `/clan*` — это намеренно). Добавляет `Спринт 3.6` в `development_plan.md` (после Спринта 3.5). **Не блокирует и не меняет скоуп Спринта 3.4-A** — следующий feature-PR после мерджа этой docs-ветки остаётся **3.4-A** по чек-листу ниже.

Перед ним: **3.3-C** (PR #114, `d08985e`) — доменный сервис `boss_round_resolution` + use-case-ы `RunBossRound` / `FinishBossFight`. Перед ним: **3.3-B** (PR #113, `9c859b7`) — use-case-ы `SummonBoss` / `JoinBossLobby` / `LeaveBossLobby` / `CloseBossLobby` + миграция `0020_boss_fights` + APScheduler с `factory=None`-заглушками + 8 `AuditAction.BOSS_*`. Перед ним: **3.3-A** (PR #112, `dbb9b1c`) — каркас доменов «Рейд-босс». Перед ним: **3.2-D** (PR #111, `89e4f0a`) — bot-handlers `/caravan` + lobby-UI + закрытие Спринта 3.2. Перед ним: **3.2-C** (PR #110, `2333297`) — боевая механика каравана. Перед ним: **3.2-B** (PR #109, `e27968b`) — use-case-ы каравана + миграция `0019_caravans`. Перед ним: **3.2-A** (PR #108, `fe959c6`) — каркас доменов «Караван». Перед ним: **3.1-E** (PR #107, `5c1b26f`) — закрытие Спринта 3.1. Перед ним: PR-ы Спринта 3.1 (#99–#106) и Спринта 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а: 3.2-A → 3.2-D). **Закрыт Спринт 3.3 «Рейд-боссы»** (4 PR-а: 3.3-A + 3.3-B + 3.3-C + 3.3-D). После мерджа этой docs-ветки активным остаётся **Спринт 3.4 «Заточка предметов»** ([`development_plan.md`](development_plan.md) §6.3.4) — следующий feature-PR — **3.4-A** «Каркас доменов «Заточка» + балансовый конфиг» по чек-листу ниже.

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

- [ ] Дождаться мерджа `3.3-D` в `main`. Получить новый `main = <merge_commit>`.
- [ ] `git fetch && git checkout main && git pull`.
- [ ] `make ci` локально на свежем `main`: ожидается зелёный.
- [ ] Создать ветку `devin/<unix_timestamp>-sprint-3-4-A-enchant-domain-skeleton` от `main`.
- [ ] **A.0 — Обновить `current_tasks.md`** под старт Спринта 3.4-A: пересобрать «Снимок состояния» под `main = <merge_3.3-D>`, передвинуть чек-лист на 3.4-A, секцию «Что ровно сейчас в работе» переписать под старт.
- [ ] **A.1 — Расширение `Item`-агрегата** (если домен `inventory` ещё не существует — создать `domain/inventory/`): поле `enchant_level: int (0..30)` (default=0), `category: ItemCategory` (enum `WEAPON`/`ARMOR`/`JEWELRY`); метод `with_enchant_level(level: int)` (валидирует `0 <= level <= 30`, иначе `MaxLevelReached`); метод `is_destroyed() -> bool` (предмет уничтожен скроллом). + Domain VO `Scroll(category, blessed: bool)` (frozen dataclass; `category: ItemCategory` — для `category-match`-проверки).
- [ ] **A.2 — Domain errors** (`domain/inventory/errors.py`): `WrongScrollCategory(scroll_category, item_category)`, `MaxLevelReached(item_id, current_level)`, `ItemDestroyed(item_id)` — все наследуют общий `DomainError`-базовый класс (или специфичный `InventoryDomainError`-подкласс).
- [ ] **A.3 — Доменный picker `pick_enchant_outcome`** (`domain/inventory/services.py`): чистая функция `pick_enchant_outcome(*, level: int, blessed: bool, weights: EnchantmentWeights, random: IRandom) -> EnchantOutcome` — возвращает один из 4 исходов (regular: `success`/`no_effect`/`drop`/`destroy`) или 5 исходов (blessed: `success_1`/`success_2`/`no_effect`/`drop`/`destroy`). Safe-zone (level < safe_zone_max) → forced `success` (no roll). Иначе — взвешенный roll через `random.uniform(0.0, 1.0)`. + `clamp(0, 30)` на нижней границе при `drop` (новый level `max(0, level - 1)`).
- [ ] **A.4 — Pydantic `EnchantmentConfig`** (`infrastructure/balance/schemas.py` + `config/balance.yaml`): pydantic-схемы `EnchantmentWeights` (`regular: {success, no_effect, drop, destroy}`, `blessed: {success_1, success_2, no_effect, drop, destroy}`) + `EnchantmentConfig.outcomes_per_level: dict[int, EnchantmentLevelWeights]` (на каждый level `0..29`). Инварианты: сумма весов на каждой группе = 1.0 ± ε (validator); `safe_zone_max: int` (level < `safe_zone_max` → forced success); `blessed_outcomes_per_level["29"].success_2 == 0.0` (ГДД §2.8.4); `drop`/`destroy` веса = 0.0 для level < `safe_zone_max`. Стартовые дефолты для всех уровней `0..29` — копируются из ГДД §2.8.6.
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

**Текущий PR — docs-only «Tribe-bonus design doc + клан→племя rename»:** docs-PR с описанием новой виральной мини-механики «Бонус-за-племена в Предсказателе» (см. ГДД §11.1, ПД §6.3.6) + сквозное переименование «клан → племя» во всех doc-файлах (`game_design.md` / `development_plan.md` / `current_tasks.md` / `history.md` / `admin_runbook.md`). **Не блокирует** Спринт 3.4-A: следующий feature-PR после мерджа этой docs-ветки — **3.4-A** «Каркас доменов «Заточка» + балансовый конфиг» по чек-листу выше. **Намеренно НЕ переименовываем** доменные идентификаторы `domain/clan/*`, `application/clan/*`, табличный код `clans`, локальные ключи `clan-*` (RU+EN), команды `/clan*`, `/freeze_clan`, `/clantop` — это сохранение обратной совместимости БД, миграций и команд. Параметры новой механики (cap `+131 см` за вызов, `>3` участников, факт членства, live-снапшот, отдельный anti-cheat-лимит, явный display-row `+N см за племена`) утверждены пользователем.
- **Текущий шаг:** финальный док-коммит → `make ci` → push → PR в `main` → ожидание зелёного GitHub CI.
- **Открытые блокеры:** нет.

После мерджа этого docs-PR — следующий агент стартует **3.4-A** «Каркас доменов «Заточка» + балансовый конфиг» по чек-листу выше (без изменений в скоупе).

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Заточка — финальные `success_probability`** (отложено до Спринта 3.4-A) — стартовые дефолты для всех уровней `0..29` зафиксированы в ГДД §2.8.6 (полные таблицы regular/blessed). После альфа-теста подбираются по метрикам; настройка через `balance.yaml` без релиза кода. Стартовый PR 3.4-A копирует эти дефолты как есть.
- **Заточка — bad-luck protection** (open question, см. ПД п.15 «Открытые вопросы») — нужна ли «гарантированный успех после N подряд провалов» в MVP механики или только в Фазе 4? Сейчас не предусмотрена (ГДД §2.8.8). На 3.4-C/D остаётся как есть; решение по итогам альфа-теста.
- **`AuditAction.SCROLL_DROP` сейчас audit-only** (с 3.3-C/D и 3.1-D) — до Спринта 3.4-B/C дроп-скроллов из рейдов и PvE **только** в `audit_log` пишется (не накапливается в инвентаре игрока). На 3.4-B (миграция инвентаря) + 3.4-C (use-case `EnchantItem`) этот же event начнёт сопровождаться реальной записью в `inventory.scrolls`. Симметрично `PveScrollDrop` из 3.1-D.

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`2bbb9fc` — `test(3.3-D): D.12 integration scroll-drop frequencies (100x5 raids)`. Следующий коммит — D.15 (этот док-коммит).
