# Definition of Done — MVP (Спринт 1.5 завершён)

> Источник: `development_plan.md` §4 «Definition of Done MVP» (Спринт 1.5):
> _«Игрок может зарегистрироваться, увидеть карточку, сходить в лес, получить шмот, прокачать толщину до 2, использовать предсказание, увидеть себя в топе. Работает RU + EN. Есть DAU Gate.»_

Этот документ — финальный чек-лист, по которому MVP считается готовым к закрытому альфа-тесту. Каждая строка либо проверена кодом и тестами, либо требует ручной валидации после деплоя.

---

## ⚙️ Архитектура и фундамент (Фаза 0)

- [x] **Clean architecture** (`domain` → `application` → `infrastructure` → `bot`) — контракт зашит в `import-linter` (3 контракта kept в CI).
- [x] **`mypy --strict`** на всём `src/` — **0 issues** на 370+ файлах.
- [x] **`ruff check`** + `ruff format` — без замечаний.
- [x] **`pytest`** — **1094+ тестов** проходят, coverage **≥ 80 %** (фактически ~97 %).
- [x] **`pip-audit`** — отдельная CI-job-а, без known CVE на dev-зависимостях.
- [x] **Pre-commit hooks** — ruff, ruff-format, mypy, import-linter (см. `.pre-commit-config.yaml`).
- [x] **`IUnitOfWork`** — все state-mutations идут через транзакции.
- [x] **`IIdempotencyService`** — defensive ключи на write-командах (`forest_run_finished:length:{run_id}`, `dau_threshold_alert:{date}`, ...).
- [x] **`IAuditLogger`** — каждое изменение состояния пишет audit-запись.
- [x] **`IActivityLockService`** — конкуренция по игроку (повторный `/forest`) защищена.
- [x] **`ThrottleMiddleware`** (`InMemoryTokenBucketRateLimiter`) — публичные команды rate-limit-нуты.
- [x] **`AuthContext` + middleware** — admin-only handler-ы провалидированы централизованно.

## 🎮 Геймплей (MVP-фичи)

### Регистрация и идентификация (Спринт 1.1)

- [x] **`/start`** в группе — регистрирует игрока и клан (если первый из клан-чата). Транзакция атомарна.
- [x] **`/start` в личке** — отказ с подсказкой «зарегистрируйся в клан-чате».
- [x] **Миграция clan_chat_id** — handler `chat_migrate_to` обновляет clan по `migrate_to_chat_id`.
- [x] **Bootstrap super_admin** — список из `BOOTSTRAP_ADMIN_IDS` записывается в `admins` при первом запуске (если таблица пуста). Идемпотентно: повторный старт с уже заполненной таблицей — no-op.

### Прогрессия / правило 20 см / DAU Gate (Спринт 1.2)

- [x] **Длина** — стартовая 20 см, минимальная 20 см (нельзя «спустить» ниже через upgrade).
- [x] **DAU Gate** — при `current_dau >= MAX_DAU` новые регистрации идут в `signup_queue` (FIFO).
- [x] **Auto-promote** — при увеличении `MAX_DAU` через `/set_max_dau` и при «уходе» игрока (TTL DAU) хвост очереди автоматически промоутится.
- [x] **Алёрт админу при 80% MAX_DAU** — пишется в audit + structlog ровно один раз в сутки (idempotency-ключ — дата UTC).

### Поход в лес (Спринт 1.3)

- [x] **`/forest`** — стартует поход; outcome (branch + length_delta + drop) ролится **сразу на старте** и сохраняется в `forest_runs`. Hot-reload баланса посреди похода не ломает результат.
- [x] **Cooldown 10–20 мин** — рандомизированный, через `IRandom.randint`. Двойной `/forest` → «вы уже в лесу» (`AlreadyInForestError`).
- [x] **Drop** — 0–1 предмет за поход (probability + name vs equipment + rarity weights `70/25/5`). Имена и предметы — независимые каталоги в `balance.yaml`.
- [x] **Inline «Надеть/Выбросить»** — переключает inventory; смена ника при первом «Надеть» нового имени.
- [x] **Audit** — `FOREST_RUN_STARTED` + `FOREST_RUN_FINISHED` (с payload-ом branch/length_delta/drop_kind).

### Прокачка / предсказатель / топ (Спринт 1.4)

- [x] **`/upgrade`** — повышение толщины. Стоимость в см, защита «не спустить ниже 20 см» (`InsufficientLengthError`).
- [x] **`/oracle`** — предсказание дня. Идемпотентно по `(player_id, date_msk)` — повторный вызов в тот же день отдаёт ту же запись из `oracle_history`.
- [x] **`/profile`** — карточка игрока (полный ник с титулом, длина, толщина, инвентарь, клан).
- [x] **`/top`** — топ-10 по длине внутри клана.

### Локализация и полировка (Спринт 1.5)

- [x] **Mozilla Fluent** — все user-facing строки в `locales/{ru,en}.ftl`. Числа — через `NUMBER($x, useGrouping: 0)`.
- [x] **`use_isolating=False`** в `FluentMessageBundle` — bidi-isolation marks (`U+2068/U+2069`) не засоряют вывод.
- [x] **`/lang ru|en`** — переопределение локали игрока через `users.locale_override`. Приоритет: `locale_override → tg.language_code → DEFAULT_LOCALE`.
- [x] **`PlayerLocaleResolverDB`** — пробрасывается в `LocaleMiddleware` и в `TelegramForestFinishNotifier`, чтобы фоновые jobs рендерились в локали игрока.
- [x] **Каталог forest-логов** — 350 шаблонов на локаль RU+EN (`config/templates/forest_logs_{ru,en}.json`). Allowed-плейсхолдеры — только `{user}` и `{delta}` (валидируется integration-тестом).
- [x] **Каталог oracle-предсказаний** — ≥ 200 шаблонов на локаль (Спринт 1.4.B).
- [x] **`/balance_reload`** — admin-only hot-reload `balance.yaml` (без перезапуска бота).

## 🛠 DevOps и деплой (Спринт 1.5.H)

- [x] **`Dockerfile`** — multi-stage (builder venv + runtime slim), непривилегированный пользователь `pipirik:1000`, healthcheck через импорт `Settings`. Расположение — `ops/docker/Dockerfile`.
- [x] **`docker-compose.yml`** — 3 сервиса (postgres + migrations sidecar + bot). Бот ждёт `migrations: service_completed_successfully`. Расположение — `ops/docker/docker-compose.yml`.
- [x] **`.dockerignore`** — исключает `.git`, `.env`, `tests/`, `docs/`, кэши.
- [x] **`README.md`** — полный setup/run гайд (Docker и без Docker), оценочное время поднятия для нового разработчика — < 5 мин.
- [x] **`CONTRIBUTING.md`** — workflow PR, чек-листы SOLID/security, правила git, структура тестов.
- [x] **`ops/runbooks/deploy_vps.md`** — пошаговая инструкция деплоя на VPS 1 GB + Neon free Postgres.
- [x] **`docs/dod_mvp.md`** (этот файл).
- [ ] **24 часа стабильной работы** под закрытым тестом — проверяется **руками после деплоя** (см. `ops/runbooks/deploy_vps.md` §6).

## 📋 Acceptance: что делает игрок

Сценарий, который должен проходить полностью без падений:

1. Игрок добавляется в клан-чат → бот видит `chat_member` update.
2. Игрок пишет `/start` → бот регистрирует, выдаёт стартовую длину 20 см и толщину 1, пишет audit `PLAYER_REGISTERED`.
3. Игрок пишет `/profile` → видит карточку.
4. Игрок пишет `/forest` → бот отвечает «ты ушёл в лес» с рандомным flavour-сообщением. Cooldown 10–20 мин.
5. Через cooldown игрок получает finished-сообщение: `+N см`, опциональный drop (item или name) с inline-кнопками «Надеть/Выбросить».
6. Игрок жмёт «Надеть» → инвентарь обновляется, при name-drop — ник меняется на «{name} {nick}».
7. Игрок пишет `/upgrade` → бот предлагает повысить толщину за N см. Игрок подтверждает → толщина 2.
8. Игрок пишет `/oracle` → получает предсказание. Повторный `/oracle` в тот же день → то же предсказание (идемпотентность).
9. Игрок пишет `/top` → видит топ-10 кланчата по длине.
10. Игрок пишет `/lang en` → следующие сообщения от бота — на английском.

**Все шаги покрыты unit + integration-тестами.** Конкретные тесты для каждого шага — см. `tests/unit/application/` и `tests/unit/bot/handlers/`.

## ❌ Что НЕ входит в MVP

Эти фичи переезжают в Фазу 1.6 / Фазу 2:

- **Анти-чит хардкап** (rolling-окна 24 ч / 7 дней, soft-ban) — Спринт 1.6 (`development_plan.md` §4 / новый раздел «Анти-чит хардкап (Pre-Phase-2 gate)»). Это обязательный pre-Phase-2 gate.
- **PvP 1×1, масс-PvP, клановые механики** — Фаза 2.
- **Глава клана дня (👑)** — Фаза 2.
- **Реферальная система** — Фаза 2.
- **Админ-интерфейс в боте (полный)** — Фаза 2 (есть базовый: `/dau_stats`, `/set_max_dau`, `/balance_reload`).
- **Горы, данжон, караваны, рейды** — Фаза 3.
- **Монетизация (Stars / TON / USDT)** — Фаза 4.
- **Webhook вместо long-polling** — Фаза 4 (для масштаба).
- **Redis-кэш** — Фаза 4 (заменит `InMemoryTokenBucketRateLimiter`).

## ✅ Sign-off

MVP считается готовым к закрытому альфа-тесту, когда:

1. Все checkbox-ы выше отмечены ✅, включая 24 часа стабильной работы.
2. PR Спринта 1.5.H смержен в `main`.
3. CI зелёный на `main` (lint + types + tests + audit).

После этого — открываем альфа-тест по приглашениям и собираем feedback для Phase-2.

> **Что после MVP:** обязательный pre-gate перед Phase-2 — Спринт 1.6 (анти-чит хардкап). Без него открытый тест с реальными деньгами / общей лидербордой не запускаем — игроки могут эксплойтить рост длины.
