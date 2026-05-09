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

**На `main`:** последний смерженный PR будет **3.4-A** (PR #117, мердж после зелёного CI этой ветки) — каркас доменов «Заточка»: пакет `domain/inventory/` (`Item` / `ItemCategory` / `RegularEnchantOutcome` / `BlessedEnchantOutcome` / `pick_enchant_outcome`); 3 domain-errors (`WrongScrollCategoryError` / `MaxLevelReachedError` / `ItemDestroyedError`); pydantic-конфиг `EnchantmentConfig` (+ `RegularLevelWeights` / `BlessedLevelWeights` / `EnchantmentTier`) с 8 инвариантами по ГДД §2.8.6; `config/balance.yaml` секция `enchantment` со всеми 30 уровнями + 6 тиров; новый import-linter контракт `balance_must_not_import_inventory` (4-й kept). 158 новых тестов; total `make ci`: **4622 passed / 2 skipped, coverage 95.46%**. Перед ним — **3.6 design doc** (PR #116, `f7d671f`) — docs-only: виральная мини-механика «Бонус-за-племена в Предсказателе» (ГДД §11.1, ПД §6.3.6) + сквозное переименование «клан → племя» в документации. Перед ним — **3.3-D** (PR #115, `5d6c9a3`) — финальный PR Спринта 3.3 «Рейд-боссы». **Закрыт Спринт 3.3 «Рейд-боссы»**, **открыт Спринт 3.4 «Заточка предметов»** (3.4-A — первый из 4 PR-ов).

**Текущая ветка** — следующая будет создана от `main` после мерджа 3.4-A, **следующий feature-PR** Спринта 3.4-B «Persistence + миграция инвентаря». На `main` после мерджа 3.4-A новых коммитов нет — старт от чистого `main`.

Перед `3.4-A` (PR #117): **3.6 design doc** (PR #116, `f7d671f`) — docs-only. Перед ним: **3.3-D** (PR #115, `5d6c9a3`) — bot-handler `/boss` + lobby-UI + локали + APScheduler-фабрики + 3 нотификатора + use-case `CancelBossFight` + raider-loss length-вычеты + integration-тест scroll-drop частот. Перед ним: **3.3-C** (PR #114, `d08985e`) — доменный сервис `boss_round_resolution` + use-case-ы `RunBossRound` / `FinishBossFight`. Перед ним: **3.3-B** (PR #113, `9c859b7`), **3.3-A** (PR #112, `dbb9b1c`); **3.2-D** (PR #111, `89e4f0a`), **3.2-C** (PR #110, `2333297`), **3.2-B** (PR #109, `e27968b`), **3.2-A** (PR #108, `fe959c6`); **3.1-E** (PR #107, `5c1b26f`) и PR-ы Спринтов 3.1 (#99–#106) и 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а: 3.2-A → 3.2-D). **Закрыт Спринт 3.3 «Рейд-боссы»** (4 PR-а: 3.3-A + 3.3-B + 3.3-C + 3.3-D). **Активен Спринт 3.4 «Заточка предметов»** ([`development_plan.md`](development_plan.md) §6.3.4) — закрыт **3.4-A** (каркас домена + балансовый конфиг), следующий PR — **3.4-B** «Persistence + миграция инвентаря» по чек-листу ниже.

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

## 📝 Чек-лист следующего PR (Спринт 3.4-B — Persistence + миграция инвентаря)

> Этот PR — второй PR Спринта 3.4. Он добавляет persistence-слой для `enchant_level`-а, созданного в 3.4-A: миграция Alembic `add_enchant_level_to_items`, ORM-маппинг `Item.enchant_level: Mapped[int]` с `default=0`, `IItemRepository.update_enchant_level(item_id, new_level)`. Default `0` нужен для legacy-предметов в БД (до миграции `enchant_level` не существовал). Без use-case-а `EnchantItem` — это 3.4-C; без bot-UI — это 3.4-D.

- [ ] Дождаться мерджа `3.4-A` в `main` (PR #117). Затем `main` = новый коммит после мерджа.
- [ ] `git fetch && git checkout main && git pull`.
- [ ] Создать ветку `devin/<timestamp>-sprint-3-4-B-inventory-persistence` от `main`.
- [ ] **B.0 — Обновить `current_tasks.md`** под старт Спринта 3.4-B: пересобрать «Снимок состояния» под новый `main`, передвинуть чек-лист на 3.4-B, секцию «Что ровно сейчас в работе» переписать под старт.
- [ ] **B.1 — ORM-маппинг `Item.enchant_level`** (`infrastructure/db/orm/inventory.py` или соседний файл, см. где сейчас лежат items): `Mapped[int] = mapped_column(default=0, nullable=False, server_default=text("0"))`. Категория предмета (`weapon` / `armor` / `jewelry`) — отдельная колонка `category: Mapped[str]` с тем же default-pattern (см. где это лежит в текущих ORM-файлах; если категория уже хранится как часть `slot`-enum — задокументировать в комментарии и в `Item`-маппере). **Критерий:** `make ci` зелёный, `mypy --strict` 0 issues, integration-тест на `IItemRepository.get(item_id)` отдаёт `Item` с `enchant_level=0` для legacy-записей.
- [ ] **B.2 — Миграция Alembic `add_enchant_level_to_items`**: `alembic revision --autogenerate -m "add enchant_level + category to items"` → ручное ревью миграции (default `0` для существующих строк, NOT NULL constraint, `server_default=text("0")` чтобы Postgres сам заполнил backfill). Если категория добавляется этим же PR-ом — миграция включает обе колонки одним тиком (атомарность). **Критерий:** `pytest tests/integration/db/test_migrations.py` зелёный (там уже есть проверка up→down→up).
- [ ] **B.3 — `IItemRepository.update_enchant_level(*, item_id, new_level)`**: метод порта (в `domain/inventory/ports.py` — создать), реализация в `infrastructure/db/repositories/items.py`. Реализация: `UPDATE items SET enchant_level = :new_level WHERE id = :item_id`; ошибка `ItemNotFound` если 0 rows affected. **Критерий:** Integration-тест round-trip + idempotency двух подряд `update_enchant_level(item_id=X, new_level=5)` → `enchant_level == 5` (без race-conflict).
- [ ] **B.4 — Юнит / integration тесты**: (a) round-trip `Item(id, category, enchant_level=0)` → repo.save → repo.get → equal; (b) legacy-record (вставлен напрямую в SQL без `enchant_level`) → repo.get отдаёт `Item(enchant_level=0)`; (c) `update_enchant_level(item_id=X, new_level=15)` → repo.get отдаёт `Item(enchant_level=15)`; (d) `update_enchant_level(item_id=missing, ...)` → `ItemNotFound`.
- [ ] **B.5 — `make ci` локально:** ruff + mypy --strict + import-linter (4 contracts kept) + pytest зелёный + coverage gate (≥ 80%).
- [ ] **B.6 — Финальный док-коммит:** `history.md` +запись 3.4-B, `current_tasks.md` пересборка под старт **Спринта 3.4-C «Application use-case `EnchantItem` + audit + анти-чит trip-wire»**.
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Следующий PR — Спринт 3.4-B «Persistence + миграция инвентаря»:** persistence-слой для `enchant_level`. ORM-маппинг `Item.enchant_level: Mapped[int]` (default=0); миграция Alembic `add_enchant_level_to_items` (server_default=0 для legacy-предметов); метод `IItemRepository.update_enchant_level(item_id, new_level)` с `ItemNotFound` на 0 rows affected. Integration-тесты round-trip + legacy + miss.
- **Текущий шаг:** ожидание мерджа 3.4-A в `main`. После — старт ветки `devin/<timestamp>-sprint-3-4-B-inventory-persistence`, B.0 (docs snapshot), B.1 (ORM), B.2 (миграция), B.3 (repo-метод), B.4 (тесты), B.5 (make ci), B.6 (финальный docs).
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
