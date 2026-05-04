# 🍆 Пипирик Варс — История выполнения

> Хронологический журнал выполненных работ по проекту. Каждая запись — это завершённая задача / спринт / решение. Новые записи добавляются **сверху** (свежие — первыми).
>
> Формат записи:
>
> ```
> ## YYYY-MM-DD — Заголовок
> **Автор:** имя
> **Тип:** plan | feature | fix | refactor | infra | balance | doc | decision
> **Связано:** ссылка на задачу из current_tasks.md / PR / коммит
>
> Что сделано:
> - пункт 1
> - пункт 2
>
> Результат / артефакты:
> - ссылки на файлы, миграции, конфиги
>
> Заметки / решения:
> - почему сделано именно так
> ```

---

## 2026-05-04 — Спринт 0.2 «достройка»: BalanceLoader (0.2.9 + 0.2.10)
**Автор:** Devin (по запросу 612amaranth)
**Тип:** infra / config
**Связано:** PR (TBD), [development_plan.md §3 Фаза 0 / Спринт 0.2 «достройка»](development_plan.md), [current_tasks.md Спринт 0.2 «достройка»](current_tasks.md)

Что сделано (2 пункта плана):

1. **Pydantic-схема `BalanceConfig` (0.2.9).** Чистая (domain-only) модель в `src/pipirik_wars/domain/balance/config.py`. Все ноды — `frozen=True, extra="forbid", populate_by_name=True` (двойная защита: иммутабельность + отказ на лишних полях + поддержка как алиаса YAML, так и имени поля в Python). Подмодели:
   - `DisplayNameRange` — полуоткрытый интервал `[from, to)`, `to=null` только для последнего ряда. Алиасы `from`/`to` маппятся на `from_cm`/`to_cm` через `Field(alias=...)` (Python-keyword conflict).
   - `ForestOutcome`/`ForestConfig` — веса > 0, `min ≤ max`, `cooldown_min_minutes ≤ cooldown_max_minutes`, имена веток уникальны.
   - `OracleConfig` — `bonus_min ≤ bonus_max`, оба > 0, `distribution` — `Literal["uniform"]` (на будущее можно расширить до `weighted_buckets`).
   - `ReferralConfig` — `on_thickness_milestones` строго отсортированы по `thickness` без дублей.
   - `ThicknessConfig` — `cost_base > 0`, `cost_exponent ≥ 1`, `unlock_levels` — непустой dict, каждый level ≥ 1.
   - `DauGateConfig` — `0 < alert_threshold ≤ 1`.
   - `DailyHeadConfig` — `bonus_min ≤ bonus_max`, `schedule_mode` ∈ {`button`, `cron`, `hybrid`}, `cron_random_offset_hours ∈ (0, 48]`.
   - `ContentPolicy` / `ContentPolicyClanQuotes` — bool-флаги.
   - **Главный инвариант** на корневом `BalanceConfig`: `display_names` стартуют с 0, ряды примыкают друг к другу без дыр и пересечений (`prev.to == next.from`), последний ряд имеет `to=null`. Любое нарушение → `ValidationError`.
   - Метод `display_name_for(length_cm)` — поиск названия по длине (полуоткрытый интервал, `length_cm < 0` → `ValueError`, недостижимая ветка → `IntegrityError` для защиты от рассинхрона).
2. **`YamlBalanceLoader` + порт `IBalanceConfig` (0.2.10).** Порт `IBalanceConfig` живёт в `domain/balance/ports.py` (`abc.ABC` с одним методом `get() -> BalanceConfig`). Реализация — `infrastructure/balance/loader.py:YamlBalanceLoader`:
   - **Lazy-загрузка**: конструктор не читает файл, чтобы тесты могли создавать loader на несуществующих путях; первый `get()` читает + парсит + валидирует.
   - **Кэш**: повторные `get()` отдают **тот же** объект (тождественность через `is`); подмена файла снаружи без `reload()` не вызывает перечтение.
   - **Hot-reload**: `reload()` перечитывает файл и **атомарно** подменяет внутреннюю ссылку; старый снимок остаётся валидным благодаря `frozen=True`. Если новый YAML невалиден — `ConfigError`, кэш не трогается (тест `test_reload_failure_keeps_old_snapshot`).
   - **Маппинг ошибок**: любая ошибка чтения / парсинга / валидации → `pipirik_wars.shared.errors.ConfigError` с понятным `path` и причиной (для будущего алёрта в админ-чат).
3. **Composition root.** В `bot/main.py:Container` добавлено поле `balance: IBalanceConfig`; `build_container()` принимает опциональный `balance_yaml_path` (default — `Path("config/balance.yaml")`). Loader не блокирует импорт — `create_async_engine`-стиль lazy.

Покрытие порта в тестах:

- 39 новых тестов в `tests/unit/domain/balance/test_config.py` (валидация + boundary checks + `display_name_for`).
- 11 новых тестов в `tests/unit/infrastructure/test_balance_loader.py` (lazy, кэш, reload, ошибки, smoke-тест на реальном `config/balance.yaml`).
- Существующие тесты `test_composition_root.py` обновлены под новое поле `balance` в `Container`; добавлен `tests/fakes/balance.py:FakeBalanceConfig` для тестов use-case-ов в Спринтах 1.1+.
- Общая статистика: **188 тестов** (138 предыдущих + 50 новых), покрытие **94.30 %** (порог 80%). `make ci` зелёный (lint + format + mypy --strict + import-linter + pytest + pre-commit).

Результат / артефакты:

- `src/pipirik_wars/domain/balance/{__init__,config,ports}.py` — domain-схема и порт.
- `src/pipirik_wars/infrastructure/balance/{__init__,loader}.py` — YAML-loader.
- `tests/fakes/balance.py` + регистрация в `tests/fakes/__init__.py`.
- `tests/unit/domain/balance/{__init__,factories,test_config}.py` + `tests/unit/infrastructure/test_balance_loader.py`.
- `bot/main.py:Container` обогащён полем `balance`.
- 3 контракта import-linter сохранены: `domain.balance` импортирует только stdlib и pydantic; `infrastructure.balance` зависит от domain (через интерфейсы) и pyyaml/pydantic.

Заметки / решения:

- **Алиасы `from`/`to`.** YAML использует ключи `from`/`to` (как в ГДД §2.3), но это — Python keywords. Pydantic `Field(alias="from")` + `populate_by_name=True` даёт «и YAML, и Python field-name» работать одновременно. В тестах конструируем через `model_validate(dict)` — это не зависит от типов `__init__` (без pydantic.mypy plugin static-сигнатура `**data: Any`).
- **Единый `ConfigError`.** Все три класса ошибок (OSError при чтении, `yaml.YAMLError` при парсинге, `pydantic.ValidationError` при валидации) маппятся в один `ConfigError` из `shared.errors` — это даст единое место для алёрта/логирования в Спринте 1.5 (админ-команды).
- **Lazy + cache + atomic reload.** Эти три свойства в одном loader-е делают возможным hot-reload без перезапуска процесса (план Спринта 2.5: админ-команда `/balance_reload`). Старые `BalanceConfig`-снимки остаются валидными ровно потому, что `frozen=True` запрещает мутации — клиенты, схватившие ссылку до `reload()`, не увидят неконсистентного состояния.
- **`__slots__` отсортированы.** Ruff `RUF023` требует сортировки имён в `__slots__` — учли (`("_cached", "_path")`).

---

## 2026-05-04 — Спринт 0.2: каркас безопасности
**Автор:** Devin (по запросу 144keri)
**Тип:** infra / security
**Связано:** PR #5, [development_plan.md §3 Фаза 0 / Спринт 0.2](development_plan.md), [current_tasks.md Спринт 0.2](current_tasks.md)

Что сделано (11 пунктов плана):

1. **Расширение зависимостей (0.2.0).** В `pyproject.toml` добавлены: `SQLAlchemy[asyncio]>=2.0.30`, `asyncpg>=0.29`, `alembic>=1.13`, `structlog>=24.1`, `aiosqlite` и `freezegun` в dev-deps (тесты адаптеров на in-memory SQLite, мокирование времени).
2. **pydantic-settings (0.2.6).** `infrastructure/settings/`: `Settings` + `DatabaseSettings` + `BootstrapSettings`. URL хранится как `SecretStr` (не утекает в repr/log). `BootstrapSettings.admin_ids` парсит CSV из env (`"100, 200, 300"` → `(100, 200, 300)`). Никаких хардкод-секретов в коде.
3. **Alembic (0.2.0b).** `alembic.ini` + `infrastructure/db/migrations/` (env.py async-режим + URL из pydantic-settings). Первая миграция `0001_initial` создаёт `idempotency_keys`, `audit_log`, `activity_locks`, `admins`. `BigInteger.with_variant(Integer, "sqlite")` для autoincrement, `with constraint naming convention` (детерминированный rename в alembic autogenerate).
4. **`SqlAlchemyUnitOfWork` (0.2.0c).** Async-CM с `auto-rollback` на исключение, защита от nested-context, явные `commit()`/`rollback()` методы. Реализует `IUnitOfWork`.
5. **`SqlAlchemyIdempotencyService` (0.2.2).** `INSERT ... ON CONFLICT DO NOTHING` (диалект-специфично для PG/SQLite). Повторный `mark()` — NO-OP, не портит транзакцию.
6. **`SqlAlchemyAuditLogger` (0.2.3).** Запись в `audit_log` через сессию UoW. Откатывается с транзакцией. JSON-поля `before`/`after` для diff-снимков.
7. **`SqlAlchemyActivityLockRepository` (0.2.1) + `ActivityLockService`.** PK `(actor_kind, actor_id)`. Истёкшие блоки удаляются перед попыткой `try_acquire`. `LockAlreadyHeldError` бросается из application-сервиса при отказе. Тест «двойной захват» зелёный.
8. **`SqlAlchemyAdminRepository` + bootstrap.** Use-case `BootstrapSuperAdmin` (из `BOOTSTRAP_ADMIN_IDS`): при пустой `admins` выдаёт каждому `tg_id` роль `super_admin` + audit-запись `bootstrap`; при непустой — NO-OP. Дубли в списке dedupe-ятся, неактивные админы не считаются.
9. **DTO входов (0.2.4).** `application/dto/inputs.py`: `RegisterPlayerInput`, `RegisterClanInput`, `GrantLengthInput`. `model_config = {extra="forbid", strict=True, frozen=True}` — никаких неявных конверсий и лишних полей.
10. **Декораторы авторизации (0.2.5).** `application/auth/`: `AuthContext` (DTO), `requires_level(min)`, `requires_length(min_cm)`, `requires_clan_member`. Ошибка → `AuthorizationError(requirement=…, detail=…)`. Все 5 путей покрыты тестами.
11. **`InMemoryTokenBucketRateLimiter` (0.2.7).** Реализует `IRateLimiter`. Тест `10 cmd/s` → 11-й отказ. Per-key bucket (отдельный лимит на игрока). Refill — линейный по `IClock.now().timestamp()`.

Реальный composition root (`bot/main.py:build_container()`): собирает `RealClock` + `RealRandom` + `SqlAlchemyUnitOfWork` + `SqlAlchemyIdempotencyService` + `SqlAlchemyAuditLogger` + `Settings`. `main()` остаётся `NotImplementedError("1.1")` — entry point с aiogram появится в Спринте 1.1.

Результат / артефакты:

- Локально: 138 тестов (49 unit Спринта 0.1 + 89 новых: unit + integration на in-memory SQLite). Покрытие 93% (порог 80%). `make ci` зелёный (lint + format + mypy --strict + import-linter + pytest + pip-audit).
- Alembic: `alembic upgrade head && alembic downgrade base` отрабатывают чисто на SQLite (в Postgres проверим в Спринте 1.1).
- 3 контракта import-linter сохранены: `domain` и `application` не зависят от `sqlalchemy/asyncpg/aiogram/httpx/infrastructure`.

Заметки / решения:

- **SQLite в integration-тестах.** Использован `aiosqlite` через `Base.metadata.create_all()` — даёт быстрый smoke-test адаптеров без поднятия Postgres. Production будет на asyncpg/Postgres; миграции тестируем на обоих диалектах (Spring 1.1 поднимет docker-compose с Postgres в CI).
- **`with_variant(Integer, "sqlite")`.** SQLite не умеет AUTOINCREMENT на BigInteger. Используем `Integer` (32-битный) на SQLite — для тестов хватит, в Postgres — нативный `bigserial`.
- **Нет повсеместного `Any`/`getattr`.** В двух местах с диалект-специфичным `Insert`-стейтментом введены типизированные ветки `PgInsert`/`SqliteInsert` с присваиванием в общий `DialectInsert`. Mypy `--strict` зелёный.
- **`build_container()` теперь работает.** Раньше (Спринт 0.1) бросал `NotImplementedError("0.2")`. В Спринте 1.1 будет добавлен `aiogram.Dispatcher` поверх контейнера в `main()`.

---

## 2026-05-04 — Спринт 0.1: каркас clean architecture
**Автор:** Devin (по запросу 144keri)
**Тип:** infra / refactor
**Связано:** PR #3, [development_plan.md §3 Фаза 0 / Спринт 0.1](development_plan.md), [current_tasks.md Спринт 0.1](current_tasks.md)

Что сделано (8 пунктов плана):

1. **Структура папок (0.1.1).** Доукомплектован каркас: добавлены `src/pipirik_wars/domain/shared/ports/`, `src/pipirik_wars/shared/errors.py`, `tests/fakes/`, `tests/unit/{domain/shared/ports,fakes,bot}/`. Все слои на месте, в каждом — `__init__.py` с docstring о роли слоя и правилах импортов.
2. **import-linter (0.1.2).** Создан `.importlinter` с 3 контрактами:
   - `layered_architecture` — порядок слоёв `bot/admin → infrastructure → application → domain → shared`.
   - `domain_must_not_import_infrastructure` — `domain/` не имеет права тянуть `infrastructure`, `bot`, `admin`, `aiogram`, `sqlalchemy`, `asyncpg`, `httpx`.
   - `application_must_not_import_io_libs` — то же ограничение для `application/` (use-cases не знают про БД и Telegram).
3. **Доменные порты (0.1.3).** В `pipirik_wars.domain.shared.ports`:
   - `IClock` (`now()`, `moscow_date()`).
   - `IRandom` (`randint`, `uniform`, `choice`, `weighted_choice`, `deterministic_uint(seed, modulo)` — последний для per-clan offset Главы клана дня).
   - `IUnitOfWork` (async-context-manager: `commit/rollback`, авто-rollback на исключении).
   - `IIdempotencyKey` (`build`, `is_seen`, `mark`).
   - `IAuditLogger` (`record(AuditEntry)` + `AuditAction` enum + `AuditEntry` dataclass).
   - Все порты — абстрактные (`abc.ABC`), любая попытка прямой инстанциации падает `TypeError`.
   - В `tests/fakes/` пять in-memory реализаций: `FakeClock`, `FakeRandom`, `FakeUnitOfWork`, `FakeIdempotencyKey`, `FakeAuditLogger`. На них уже сейчас 49 unit-тестов, покрытие 100%.
4. **Composition root (0.1.4).** В `pipirik_wars.bot.main` создан `Container` (frozen `dataclass(slots=True)` с пятью портами) и `build_container()/main()` — пока заглушки, бросающие `NotImplementedError` с указанием спринта, в котором они появятся. Никакого сервис-локатора, никаких глобальных DI-контейнеров.
5. **`pyproject.toml` (0.1.5).** Полный конфиг: Python ≥ 3.11, runtime-deps минимальны (pydantic, pydantic-settings, PyYAML), dev-deps — ruff, mypy, pytest+pytest-asyncio+pytest-cov, pip-audit, pre-commit, import-linter, types-PyYAML.
   - `ruff.lint` = `E/W/F/I/B/UP/SIM/N/PL/RUF`, `RUF001/2/3` отключены (проект на русском).
   - `mypy --strict` со строгими `disallow_*` и `mypy_path = src`.
   - `pytest` с `--cov-fail-under=80`, `asyncio_mode = auto`.
6. **Pre-commit (0.1.6).** `.pre-commit-config.yaml`: pre-commit-hooks v4.6 (whitespace, EOF, yaml/toml, large-files, merge-conflict, private-key), `ruff` + `ruff-format`, `mypy` (с `additional_dependencies`), `import-linter` через `repo: local` (чтобы видеть проектный venv).
7. **GitHub Actions CI (0.1.7).** `.github/workflows/ci.yml`: матрица Python 3.11/3.12, кеш pip, шаги ruff lint + ruff format check + mypy --strict + lint-imports + pytest + coverage artifact. Отдельный job `audit` для `pip-audit --skip-editable`.
8. **Makefile (0.1.8 бонус).** Таргеты `install`, `install-dev`, `lint`, `format`, `typecheck`, `imports`, `test`, `cov`, `audit`, `pre-commit`, `ci`, `clean`. `make ci` локально прогоняет lint+types+imports+test (audit отдельно — он сетевой).

Результат / артефакты:
- `pyproject.toml`, `Makefile`, `.importlinter`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`.
- 73 файла Python в проекте; 49 unit-тестов; покрытие 100%.
- Локальный `make ci` зелёный; pip-audit без CVE; pre-commit без замечаний.

Заметки / решения:
- Pytest подняли с `>=8.2,<9` до `>=9.0.3,<10` (CVE-2025-71176 в 8.x). Соответственно pytest-asyncio — до `>=1.3,<2`.
- `pip-audit` не умеет аудитить editable-пакеты — везде используем `--skip-editable`, чтобы не сообщать о собственном `pipirik-wars` как «не найден на PyPI».
- Production-зависимостей (aiogram, sqlalchemy, asyncpg, structlog, apscheduler) пока нет — они появятся в Спринте 1.1+. Это снижает площадь pip-audit и держит CI быстрым.
- Никакого бизнес-кода ещё нет — только инфраструктурный каркас. ГДД-баланс заморожен в `config/balance.yaml` v2.

---

## 2026-05-04 — ГДД v9: уточнения после мержа PR #1
**Автор:** Devin (по запросу 144keri)
**Тип:** doc / decision / balance
**Связано:** PR #2 (пост-мерж правки)

После мержа PR #1 заказчик ответил на 6 из 8 открытых вопросов. Внесены правки в ГДД v8 → v9.

Что сделано:

1. **Глава клана дня — гибридный триггер.** §6.1 ГДД переписан:
   - Бонус: было `+3` см → стало **`uniform(1, 20)` см** (`balance.yaml: daily_head.bonus_min/bonus_max`).
   - Триггер: было «cron 12:00 UTC всем сразу» → стало **гибрид «кнопка `/clan_head` ИЛИ фоновый cron с per-clan `random_offset(0..24h)` от 00:00 МСК»**. Что наступит первым — то и побеждает. Идемпотентность по `(clan_id, moscow_date)`. Распределяет нагрузку по суткам и добавляет элемент «кто первый дёрнет рулетку».
   - Добавлены use-cases `RequestDailyHead` (button-driven) и `RunDailyHeadCron` (cron) поверх единого доменного сервиса `DailyHeadService.assign_or_get`.
   - В Спринте 2.3 теперь 8 задач (было 7) с новыми пунктами на кнопочный триггер и детерминированный per-clan offset.
2. **Контент-полиси цитат — уместный мат разрешён.** §6.1 ГДД и `balance.yaml: content_policy.clan_quotes`:
   - `mild_profanity: true` (Q9 v9).
   - Запрещены: политика, межнацоскорбления, насилие, реклама, секс.
   - Цитаты с матом помечаются тегом `profanity` для будущего фильтра «детский режим клана».
3. **Bootstrap первого `super_admin`-а.** §18.6.4 ГДД дополнен:
   - Первый `super_admin` берётся из env-переменной `BOOTSTRAP_ADMIN_IDS` (список `tg_id` через запятую).
   - Bootstrap-логика срабатывает **только один раз** (если таблица `admins` пуста).
   - Значение хранится в Devin Secrets (`PIPIRIK_BOOTSTRAP_ADMIN_TG_ID`, `save_scope: org`), в git/конфиг/логи никогда не попадает.
   - Спринт 0.2.6 расширен: добавлен критерий приёмки «bootstrap-логика сработала ровно один раз; повторный запуск с непустой `admins` — env игнорируется».
   - `.env.example` добавлен placeholder `BOOTSTRAP_ADMIN_IDS=` с комментарием.
4. **«Нежный» переедет на другой триггер.** §2.4 ГДД: «Новичок» = первый лес (как в v8), «Нежный» — TBD (открытый вопрос Q12b). Это не блокирует разработку Спринта 1.3.
5. **Каналы как кланы — отказ полностью; канал-анонсы — отдельный спринт.**
   - §1.1 ГДД переписан: «канал = клан» НЕ ПОДДЕРЖИВАЕТСЯ, отказ.
   - §22 (приоритеты) и `current_tasks.md` (бэклог): добавлен **Спринт 4.9 «Канал-анонсы перед публичным релизом»** — отдельный публичный TG-канал бота с автопостингом итогов недели / лидербордов / релиз-нот, настраивается **в самом конце Фазы 4** перед маркетинг-релизом.
6. **Веса веток леса 50/35/15 утверждены по умолчанию** (объяснил среднюю прибавку: ≈ 8.5 см/поход; разные распределения дают разный игровой эффект). Балансироваться будут после альфа-теста.
7. **Финальная таблица `display_names`** — заглушка из v8 остаётся; финальную таблицу геймдиз пришлёт отдельным PR.

Результат / артефакты:
- `docs/pipirik_wars_plan.md` (ГДД v9): шапка, §1.1, §2.4, §6.1, §18.6.4, §22, footer
- `docs/development_plan.md`: Спринт 0.2.6, Спринт 2.3, §2.3 БД-схема (`clan_daily_head`), §11 (открытые вопросы)
- `docs/current_tasks.md`: «Закрыто в v9» секция, обновлён бэклог (Спринт 2.3, Спринт 4.9)
- `config/balance.yaml`: версия 1 → 2; `daily_head` (1–20, hybrid); `content_policy.clan_quotes`
- `.env.example`: `BOOTSTRAP_ADMIN_IDS`
- Devin Secrets: `PIPIRIK_BOOTSTRAP_ADMIN_TG_ID` (org-scope, sensitive)

Заметки / решения:
- **Гибридный триггер** — это не просто «оптимизация нагрузки». Это улучшение игрового опыта: фиксированный 12:00 UTC создаёт «дежурный» статус (все знают что в полдень будет назначение, никто не интересуется); рандомный offset + кнопка возвращают непредсказуемость и повод заглянуть в чат клана.
- **`uniform(1, 20)`** вместо `+3` фиксированного — повторяет паттерн `/oracle` (тот же диапазон, та же распределённая природа). Игрок получает «вау, мне выпало 18!» моменты вместо предсказуемой выдачи.
- **`BOOTSTRAP_ADMIN_IDS` в env, не в `balance.yaml`** — намеренно. Список админов не должен попадать в git (это PII + риск). Хранить в Devin Secrets, прокидывать в env при деплое.
- **«Нежный» на TBD-триггере** — лучше иметь явный TBD в открытых вопросах, чем тихо переименовать в коде. Геймдиз увидит и решит позже.
- **Канал-анонсы как Спринт 4.9** — это «закладка» в самом конце Фазы 4. Обоснование: нет смысла настраивать публичный канал, пока нет публичного релиза; до релиза итоги недели и лидерборды живут в чатах кланов.

---

## 2026-05-04 — ГДД v8: уточнения от заказчика (перед мержем PR #1)
**Автор:** Devin (по запросу 144keri)
**Тип:** doc / decision / balance
**Связано:** PR #1 (поправки до мержа)

Что сделано (11 правок ГДД v7 → v8):

1. **Имя при регистрации убрано.** §1.1 и §2.5: новичок при регистрации **не получает имени**. Имя — это тип предмета, выбивается дропом из леса. До первого дропа карточка показывает «Титул Название», без имени.
2. **Название по длине вынесено в `balance.yaml`.** §2.3 переписан: вместо хардкода в ГДД — редактируемая таблица `display_names` в `config/balance.yaml`. ГДД содержит только заглушку и ссылку. Валидация: без дыр и пересечений.
3. **Стартовые параметры зафиксированы.** §1.1 / §2 / §22: длина = **2 см**, толщина = **1**, **титул = нет**, **имя = нет**. Титул «Новичок» выдаётся автоматически при первом возвращении из леса (§8.2, идемпотентно).
4. **Реферальная схема — 3-этапная.** §13.1: при регистрации новичок +5 см, реферер +1 см. При достижении новичком толщины 3 → реферер +10 см. При толщине 5 → реферер +30 см. Все начисления — после регистрации, через `progression.add_length` с уникальным `idempotency_key` вида `referral:{milestone}:{referrer_id}:{referred_id}`.
5. **Лес — 3 ветки исходов.** §8.2: `scarce` (1–10 см, вес 50), `normal` (5–15 см, вес 35), `abundant` (10–20 см, вес 15). Все ветки положительные. Веса и диапазоны — в `balance.yaml`.
6. **`/oracle` — по Москве, +1..+20 см.** §11: `cooldown_tz = "Europe/Moscow"`, сброс в 00:00 МСК; `bonus = uniform(1, 20)` см.
7. **Кик бота из чата клана → `frozen` (не `archived`).** §1.1 + БД: статус `clans.status` теперь `active|frozen|archived`. Заморозка не удаляет данные; повторное добавление бота → `active`.
8. **Основной интерфейс админки — Telegram-бот.** §18.6 переписан: бот = первый класс (Спринт 1.5/2.5, `/admin_*` команды + TOTP-подтверждение опасных действий). Веб-панель опциональна и переехала в Спринт **4.5** Фазы 4 (поверх готовых use-cases).
9. **Пацанские цитаты — иронично-смешные.** §6.1: стилистика Стэтхем / ВК-паблик / АУФ, с самоиронией. Без мата и политики. Каталог цитат тегируется (`statham`, `vk_pablik`, `auf`, `meme`) для будущего A/B.
10. **План разработки и текущие задачи синхронизированы:**
    - Спринт 1.1 — пересмотрен под старт без имени/титула + frozen вместо archived.
    - Спринт 1.3 — добавлены 3 ветки леса + автотитул «Новичок».
    - Спринт 1.4 — `/oracle` по `Europe/Moscow`, `uniform(1, 20)`.
    - Спринт 2.3 — иронично-смешные цитаты, пропуск `frozen` кланов.
    - Спринт 2.4 — расписана 3-этапная реферальная схема с idempotency.
    - Спринт 2.5 — переименован в «Админ-интерфейс в боте (основной)»; веб-панель — Спринт 4.5.
    - Добавлен Спринт 0.2.9–0.2.10 — скелет `balance.yaml` + `BalanceLoader`.
    - В §11 раздел «Открытые вопросы» 11 пунктов закрыто, 7 остаются актуальными.
11. **Создан `config/balance.yaml`** со стартовыми секциями (`display_names`, `forest.outcomes`, `oracle`, `referral`, `thickness`, `dau_gate`, `daily_head`).

Результат / артефакты:
- `docs/pipirik_wars_plan.md` (ГДД v8)
- `docs/development_plan.md` (синхронизирован с v8)
- `docs/current_tasks.md` (открытые вопросы пересортированы)
- `config/balance.yaml` (новый файл)

Заметки / решения:
- **Имя как предмет** — это намеренно ограничивает контент-политику: новичок без имени не отображается с «странным» дефолтным ником в чате клана (только «Пипирик» по длине). Имя нужно ещё «заработать».
- **Реферальная схема многоэтапная** — это усиливает удержание реферера: одного клика мало, нужно «довести» нового игрока хотя бы до толщины 3, что само по себе требует ~14000 см длины. Это естественный антифрод.
- **TZ Москвы для `/oracle`** упрощает прогноз поведения пользователей (в РФ-аудитории — большинство), но потребует учёта при расчёте «сегодня» в БД. Решено хранить `moscow_date` отдельно от UTC `created_at`.
- **Бот-админка вместо веб-панели** меняет философию проекта: не «отдельное приложение для команды», а «расширение бота для уполномоченных пользователей». Это упрощает запуск (один процесс, один деплой) и аутентификацию (только Telegram-сторона). Веб-панель остаётся как позднее улучшение для операций, неудобных в чате.
- **`balance.yaml` с pydantic-валидацией** заменяет хардкод. Это позволит горячо менять баланс без релиза кода (через `/balance_reload` или веб-редактор) и хранить историю версий для rollback.
- **Конфликт титула «Нежный»** (выдаётся за «первый поход в лес») с автоматическим «Новичок» — открытый вопрос Q12, требует решения геймдиза.

---

## 2026-05-04 — ГДД v7 + Фаза 0 + админ-панель + Глава клана дня + git-репозиторий
**Автор:** Devin (по запросу 144keri)
**Тип:** doc / plan / decision
**Связано:** PR #1 в `Pipirkawar/PipirkaWar`

Что сделано:
- **ГДД переведён в v7** (`pipirik_wars_plan.md`):
  - Добавлен §0 «Политика разработки» — SOLID/ООП-принципы и безопасность/целостность данных как обязательные требования.
  - Добавлен §1.1 «Регистрация игрока и клана» — игрок только через ЛС бота, клан только через добавление бота в группу/супергруппу. Каналы как кланы — не поддерживаются на MVP.
  - Добавлен §6.1 «Глава клана дня» — ежедневный розыгрыш в кланах ≥ 5 человек, +N см и иронично-пацанская цитата.
  - Добавлен §18.6 «Админ-панель» — отдельное FastAPI-приложение, RBAC, 2FA, аудит-лог админских действий.
  - Обновлён §22 «Приоритеты разработки» — добавлена Фаза 0 (Фундамент), уточнены задачи Фаз 1–4.
- **План разработки переведён под v7** (`development_plan.md`):
  - Добавлен §0 — рабочий чек-лист SOLID и безопасности, требуемый на каждом PR.
  - Архитектура переведена на clean architecture: `domain → application → infrastructure → bot/admin`.
  - Добавлена **Фаза 0 — Фундамент** (Спринты 0.1 и 0.2) с конкретными задачами под каркас и безопасность.
  - Спринт 1.1 переписан под «регистрация только через ЛС / клан только через группу».
  - Добавлены спринты **2.3 «Глава клана дня»** и **2.5 «Админ-панель v1»**.
  - Покрытие тестов поднято с 70 % до 80 % (`domain/` + `application/`).
  - Расширена БД-схема (`clan_daily_head`, `payments`, `admins`, `admin_audit_log`).
  - Список открытых вопросов расширен (баланс «Главы клана дня», список админов, доступ к панели, контент-политика цитат).
- **Список текущих задач переведён на Фазу 0** (`current_tasks.md`): 8 задач Спринта 0.1 + 8 задач Спринта 0.2 с приоритетами и оценками.
- **Заведён git-репозиторий** `Pipirkawar/PipirkaWar`:
  - Клонирован пустой репо в `/home/ubuntu/PipirkaWar`.
  - Добавлены документы в `docs/`.
  - Добавлен `.gitignore` под Python-проект.
  - Подготовлена структура папок будущего проекта (`domain/`, `application/`, `infrastructure/`, `bot/`, `admin/`, `tests/`, `config/`, `ops/`) с пустыми `__init__.py` и README в каждой папке, описывающим её назначение.
  - Сделан коммит и открыт PR `devin/<ts>-initial-setup` → `main`.

Результат / артефакты:
- `Pipirkawar/PipirkaWar` (репозиторий)
- `docs/pipirik_wars_plan.md` (ГДД v7)
- `docs/development_plan.md`
- `docs/history.md`
- `docs/current_tasks.md`
- `.gitignore`
- Каркас директорий проекта

Заметки / решения:
- **SOLID/ООП и безопасность подняты до уровня политики компании** (раздел §0 ГДД). Это значит, что ни одна фича Фазы 1+ не принимается без прохождения чек-листа из `development_plan.md` §0.
- **Введена Фаза 0** — её задача в том, чтобы инфраструктурные решения (clean architecture, idempotency, audit log, activity lock, RBAC-каркас, CI gates) были приняты до старта геймплея, а не ретроспективно. Это снижает технический долг и предотвращает классические race-conditions с двойным начислением длины.
- **Регистрация клана** реализуется через `my_chat_member`-событие aiogram при добавлении бота в группу. Это исключает возможность «фейковых» кланов через ЛС бота.
- **Админ-панель** вынесена в отдельный FastAPI-процесс с собственным DB-юзером (минимально необходимые права). Это разделяет blast-radius между ботом и инструментами поддержки.
- **«Глава клана дня»** — лёгкая фича, но требует idempotency (повторный запуск джобы за тот же день — no-op), `IRandom` (для тестируемости) и контент-политики для цитат. Все эти моменты зафиксированы в плане.
- Структура папок отражает clean architecture с самого начала, чтобы избежать рефакторинга на полпути.

---

## 2026-05-04 — Создание стартовой документации проекта
**Автор:** Devin (по запросу 144keri)
**Тип:** doc / plan
**Связано:** —

Что сделано:
- Прочитан и проанализирован геймдиз `pipirik_wars_plan.md` (ГДД v6).
- Создан подробный план разработки `development_plan.md` с разбивкой на 4 фазы и спринты.
- Заведён файл истории выполнения `history.md` (этот файл).
- Заведён файл текущих задач `current_tasks.md` со списком задач на ближайший спринт (Спринт 1.1 — Каркас и регистрация).

Результат / артефакты:
- `pipirik_wars/development_plan.md`
- `pipirik_wars/history.md`
- `pipirik_wars/current_tasks.md`

Заметки / решения:
- План разработки разбит на 4 фазы согласно ГДД §22, но с детализацией до спринтов и конкретных задач с критериями приёмки.
- В план вынесен список из 10 открытых вопросов к ГДД (стартовая длина/толщина, диапазон прибавки в лесу, названия для 501+ см и т. д.) — требуется уточнение у геймдизайнера до старта реализации.
- Все балансовые числа (множители каравана, цены толщины, кулдауны) предложено хранить в отдельном `config/balance.yaml` — чтобы менять баланс без релиза кода.
- Стек зафиксирован по ГДД §17: Python 3.11+ / aiogram 3.x / managed PostgreSQL (Neon) / APScheduler / fluent-i18n. Redis — отложен до Фазы 4.

---

<!-- Шаблон для новой записи (копируйте и заполняйте сверху):

## YYYY-MM-DD — Заголовок
**Автор:**
**Тип:** plan | feature | fix | refactor | infra | balance | doc | decision
**Связано:**

Что сделано:
-

Результат / артефакты:
-

Заметки / решения:
-

---
-->
