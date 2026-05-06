# 🍆 Пипирик Варс — Подробный план разработки

> Документ описывает поэтапный план разработки Telegram-бота **Пипирик Варс** на основе ГДД v7 (`game_design.md`). План разбит на фазы, спринты и конкретные задачи с критериями приёмки.
>
> **Обязательно:** перед чтением этого плана прочитайте раздел §0 ГДД («Политика разработки»: SOLID/ООП/безопасность). Эти требования — приоритетны и применимы к каждой задаче ниже.

---

## 0. Политика проекта (краткая выдержка из ГДД §0)

> Полный текст в `game_design.md` §0. Здесь — рабочий чек-лист для каждого PR.

### 0.1 Архитектура (обязательная)

```
domain/         ← чистая бизнес-логика (сущности, value objects, доменные сервисы)
   ↑ зависит только от себя; ничего не знает про БД/Telegram/HTTP
application/    ← use-cases (Application Services), оркестрация доменных операций
   ↑ зависит только от domain
infrastructure/ ← реализации интерфейсов: PG, Redis, APScheduler, платежи, i18n
   ↑ зависит от application + domain
bot/            ← aiogram handlers (тонкий слой)
admin/          ← FastAPI веб-панель (тонкий слой)
```

Зависимости направлены строго **внутрь**. Нарушение — блокер на ревью.

### 0.2 SOLID-чек-лист на PR

- [ ] **SRP** — у каждого изменённого класса одна причина для изменения.
- [ ] **OCP** — новые сценарии добавлены через расширение, без правок существующих классов.
- [ ] **LSP** — все реализации интерфейсов взаимозаменяемы (тесты для каждого).
- [ ] **ISP** — нет «толстых» интерфейсов; каждый узкий и осмысленный.
- [ ] **DIP** — `core/*` зависит только от абстракций (`Protocol`/`ABC`), конкретики внедряются через DI.
- [ ] Доменные объекты **инкапсулированы** (никаких прямых правок полей снаружи).
- [ ] **`mypy --strict`** проходит, нет `Any`, `getattr`, `setattr` для обхода типов.
- [ ] Покрытие нового кода unit-тестами ≥ 80 %.

### 0.3 Чек-лист безопасности и целостности

- [ ] Все мутации длины/толщины/инвентаря — в транзакциях.
- [ ] Idempotency-key у каждой «опасной» операции.
- [ ] Запись в `audit_log` с причиной и источником.
- [ ] Валидация входов через pydantic.
- [ ] Authz-проверки (уровень, длина, членство в клане, activity-lock) выполнены до операции.
- [ ] Никаких race-conditions (есть тест на параллельный запуск).
- [ ] Секреты только из env, не логируются.
- [ ] Антифрод-проверки применимы (рефералка, мульти-клик, мульти-аккаунт).
- [ ] **Анти-чит хардкап** — все use-cases, начисляющие длину, проходят через `progression.add_length(...)` (clamp + trip-wire). Прямые `repo.save(player.with_length(...))` мимо use-case **запрещены** (см. ГДД §3.3).

### 0.4 CI gates

- `ruff` — стиль и линт.
- `mypy --strict` — типы (строго).
- `pytest -q` + `coverage` — тесты, покрытие ≥ 80 % `core/*`.
- `pip-audit` — уязвимости (high/critical блокируют merge).
- `pre-commit` — единые хуки для всех контрибьюторов.

---

## 1. Резюме проекта

| Параметр | Значение |
|---|---|
| Платформа | Telegram Bot (групповые чаты + ЛС) |
| Язык/фреймворк | Python 3.11+, **aiogram 3.x** |
| БД | Managed PostgreSQL (Neon free → paid) |
| Кэш | In-memory (MVP) → Redis |
| Планировщик | APScheduler |
| Платежи | Telegram Stars → TON Connect → USDT |
| Локализация | RU + EN (MVP), позже PT/ES/TR/ID/FA/UK |
| Хостинг MVP | VPS 1 GB ($3–6/мес) + Neon free |
| Целевой DAU MVP | 200–500 (DAU Gate) |

---

## 2. Архитектура (общая)

### 2.1 Логические модули (clean architecture)

```
pipirik_wars/
├── domain/                  # чистые сущности и доменные сервисы (зависят только от себя)
│   ├── player/              # Player, Length, Thickness (value objects), DisplayName
│   ├── clan/                # Clan, ClanMember, DailyHead
│   ├── pve/                 # ForestRun, MountainRun, DungeonRun (агрегаты)
│   ├── pvp/                 # Duel, MassBattle, Round
│   ├── caravan/             # Caravan, CaravanMember, RaiderParty
│   ├── raid/                # RaidBattle, Boss
│   ├── economy/             # ItemCatalog, ThicknessCost, Drop
│   ├── monetization/        # Payment, Wallet
│   ├── safety/              # ActivityLock (доменная блокировка)
│   └── shared/              # абстракции (IClock, IRandom, IIdempotencyKey)
├── application/             # use-cases (тонкая оркестрация домена)
│   ├── player/              # RegisterPlayer, GetProfile
│   ├── pve/                 # StartForestRun, FinishForestRun
│   ├── progression/         # SpendLength, UpgradeThickness
│   ├── clan/                # AssignDailyHead, GetClanCard
│   ├── pvp/, caravan/, raid/  # use-cases по активностям
│   ├── monetization/        # ProcessStarsPayment, ProcessTonPayment
│   └── ports/               # Protocol-интерфейсы для infrastructure
├── infrastructure/          # реализации портов: PG, Redis, APScheduler, fluent, TG, TON
│   ├── db/                  # SQLAlchemy 2.x async, Unit-of-Work, репозитории
│   │   └── migrations/      # Alembic
│   ├── cache/               # in-memory + Redis adapters
│   ├── scheduler/           # APScheduler jobstore (PG)
│   ├── telegram/            # aiogram client wrapper
│   ├── payments/            # Stars/TON/USDT адаптеры
│   ├── i18n/                # fluent loader
│   └── templates/           # JSON-шаблоны (логи, предсказания, цитаты)
├── bot/                     # тонкий слой aiogram
│   ├── handlers/            # /start, /profile, /forest, /pvp, /caravan, /raid, ...
│   ├── middlewares/         # auth, locale, throttle, dau_gate, error_handler
│   ├── filters/             # фильтры по уровню/длине/клану
│   └── presenters/          # рендер сообщений (карточка, бой, караван)
├── admin/                   # FastAPI веб-панель
│   ├── api/                 # REST-эндпоинты
│   ├── web/                 # Jinja2/HTMX UI
│   ├── auth/                # Telegram Login + 2FA
│   └── rbac/                # роли super_admin/economist/support/read_only
├── shared/                  # кросс-инструменты (logger, metrics, errors)
├── tests/
│   ├── unit/                # домен + application
│   ├── integration/         # repo + use-case с реальной PG (testcontainers)
│   └── e2e/                 # aiogram-моки сценариев
├── config/                  # pydantic-settings, balance.yaml, .env.example
└── ops/                     # docker, deploy, runbooks
```

> Правило: импорты всегда направлены **внутрь** (`infrastructure → application → domain`). Импорт `domain → infrastructure` блокируется CI-проверкой (например, `import-linter`).

### 2.2 Принципы

- **Тонкий слой aiogram** — handlers только парсят апдейт и вызывают use-case из `application`.
- **Чистый домен** — `domain/` не знает про БД, Telegram, HTTP; легко тестируется на pure-функциях.
- **DI-контейнер** — `dependency-injector` или ручной composition root в `bot/main.py` и `admin/main.py`.
- **Конфиг баланса** (`config/balance.yaml`) — все множители вынесены сюда; `BalanceProvider` грузит и валидирует.
- **Idempotency** — каждая мутация принимает `idempotency_key`; репозиторий `audit_log` отвергает дубли.
- **Activity Lock** — доменная сущность + транзакционная реализация в `infrastructure/db`.
- **Unit of Work** — все операции use-case в одной транзакции, либо отказ.

### 2.3 Ключевые БД-сущности (черновик)

| Таблица | Поля (минимум) |
|---|---|
| `users` | id, tg_id, lang, length_cm (default 2), thickness (default 1), active_title (nullable, default NULL), name_id (nullable, default NULL), registered_at, last_seen_at, queue_pos, status (`active`/`queued`/`banned`/`frozen`) |
| `equipment` | user_id, slot, item_id, rarity |
| `items_catalog` | id, slot, base_name, rarity, weights |
| `names_catalog` | id, name |
| `titles_catalog` | id, code, condition_meta |
| `user_titles` | user_id, title_id, earned_at |
| `clans` | id, tg_chat_id, name, total_length, last_attack_at, last_caravan_at, status (`active`/`frozen`/`archived`), frozen_at, frozen_reason |
| `clan_members` | clan_id, user_id, joined_at, last_seen_in_chat_at |
| `clan_daily_head` | clan_id, moscow_date (PK c clan_id), user_id, quote_id, bonus_cm, source (`button`/`cron`), requested_by (nullable), created_at |
| `referral_milestones` | referrer_id, referred_id, milestone (`signup`/`thickness_3`/`thickness_5`), idempotency_key (unique), bonus_cm, created_at |
| `idempotency_keys` | key (PK), namespace, created_at, ttl_at |
| `activity_lock` | user_id, kind, started_at, ends_at, payload_json |
| `pve_runs` | id, user_id, location, start_at, end_at, result_json |
| `pvp_duels` | id, attacker_id, defender_id, mode (chat/global), state, rounds_json |
| `mass_pvp` | id, attacker_clan, defender_clan, started_at, members_json, result_json |
| `caravans` | id, leader_id, src_clan_id, dst_clan_id, contribution, total_length, started_at, ends_at, status |
| `caravan_members` | caravan_id, user_id, role (leader/escort/defender/raider), block_choice, status |
| `raids` | id, summoner_id, boss_user_id, started_at, ends_at, status |
| `raid_members` | raid_id, user_id, role (boss/raider), state |
| `referrals` | referrer_id, referred_id, created_at |
| `daily_active` | date, user_id (unique) — для DAU Gate |
| `signup_queue` | user_id, position, created_at |
| `daily_oracle_uses` | user_id, moscow_date (PK с user_id) — кулдаун считается по `Europe/Moscow`, а не UTC |
| `payments` | id, user_id, provider (stars/ton/usdt), external_id (unique), amount, status, idempotency_key (unique), created_at, applied_at |
| `audit_log` | id, user_id, action, delta_length, delta_thickness, reason, source (system/admin/payment/...), idempotency_key (unique), payload_json, created_at |
| `admins` | id, tg_id, role (super_admin/economist/support/read_only), totp_secret, created_at, last_login_at |
| `admin_audit_log` | id, admin_id, action, target_type, target_id, before_json, after_json, reason, ip, user_agent, created_at |

### 2.4 Сквозные требования

- **Логирование** `structlog` (JSON-формат) + `audit_log` в БД для всех изменений длины/толщины/инвентаря/платежей.
- **Метрики** Prometheus-совместимый `/metrics` (DAU, RPS, средняя длина, активные караваны/рейды, ошибки по категориям).
- **Тесты** покрытие `domain/` + `application/` ≥ **80 %**, e2e сценарии для каждой активности.
- **Антифрод** — детекция накруток рефералов (один IP/устройство), троттлинг команд, проверка дублей `tg_id` при платежах.
- **Безопасность БД** — отдельные роли БД для бота и для админ-панели (минимально необходимые права); `audit_log` доступен только на чтение для всех ролей кроме системного writer.
- **Транзакции** — `SERIALIZABLE` для критичных операций (награды каравана/рейда, платежи); `READ COMMITTED` для остального с явным `SELECT ... FOR UPDATE` где нужно.

---

## 3. Фаза 0 — Фундамент (новая, обязательная)

> Цель: подготовить «эталонный» каркас под SOLID/ООП и безопасность. Без этой фазы любая фича Фазы 1+ — технический долг с первого дня.

**Срок:** 1–1.5 недели.

### Спринт 0.1 — Каркас clean architecture

| # | Задача | Критерий приёмки |
|---|---|---|
| 0.1.1 | Структура папок `domain/application/infrastructure/bot/admin` | Создана и закоммичена; пустые `__init__.py` с docstring о слое |
| 0.1.2 | `import-linter` контракт «слои» | CI падает при попытке импорта `domain → infrastructure` |
| 0.1.3 | Базовые абстракции в `domain/shared/`: `IClock`, `IRandom`, `IUnitOfWork`, `IIdempotencyKey` | Покрыто unit-тестами в виде fakes |
| 0.1.4 | Composition root в `bot/main.py` (DI) | Один центральный сборщик зависимостей, без сервис-локатора |
| 0.1.5 | `pyproject.toml`: `ruff`, `mypy --strict`, `pytest`, `pytest-asyncio`, `pytest-cov`, `pip-audit`, `pre-commit` | `make ci` локально проходит на пустом проекте |
| 0.1.6 | Pre-commit hooks (`ruff`, `ruff-format`, `mypy`, `import-linter`) | `pre-commit run --all-files` зелёный |
| 0.1.7 | GitHub Actions: матрица Python 3.11/3.12, кэш, артефакты | CI проходит на пустом репо |

### Спринт 0.2 — Каркас безопасности

| # | Задача | Критерий приёмки |
|---|---|---|
| 0.2.1 | Доменная сущность `ActivityLock` + интеграция через `IUnitOfWork` | Юнит-тесты на «двойной захват» (второй захват — отказ) |
| 0.2.2 | Сервис `IdempotencyService` (Postgres-таблица + кэш) | Тест: повторный вызов по тому же ключу не дублирует мутации |
| 0.2.3 | `AuditLogger` — запись в `audit_log` для каждой мутации длины/толщины | Тест: для каждой публичной операции есть запись с причиной |
| 0.2.4 | pydantic-схемы валидации входов на границе bot ↔ application | Юнит-тесты на отказы при невалидных данных |
| 0.2.5 | Декораторы/middlewares авторизации (`requires_level`, `requires_length`, `requires_clan_member`) | Покрытие тестами всех путей |
| 0.2.6 | Конфиг секретов через pydantic-settings (env-only). Включает `BOOTSTRAP_ADMIN_IDS` (список `tg_id` через запятую) для bootstrap первого `super_admin`-а при пустой таблице `admins`; значение берётся из Devin Secrets (`PIPIRIK_BOOTSTRAP_ADMIN_TG_ID`, `save_scope: org`). | `.env.example` есть с placeholder для `BOOTSTRAP_ADMIN_IDS`; в коде нет хардкода; bootstrap-логика сработала ровно один раз; повторный запуск с непустой `admins` — env игнорируется (тест) |
| 0.2.7 | Базовый rate-limiter (token bucket) на команды | Тест: 10 команд за секунду — последняя отказана |

**Definition of Done Фазы 0:** проект пустой, но «правильный»: добавление любой новой фичи требует только бизнес-логики, никаких архитектурных решений «по дороге».

---

## 4. Фаза 1 — MVP (Soft Launch)

> Цель: запускаемый бот, который позволяет зарегистрироваться, получить имя/титул/длину, ходить в лес, качать толщину, использовать предсказатель, видеть топ. Только RU + EN.

**Срок (ориентир):** 4–6 недель силами 1 разработчика.

### Спринт 1.1 — Регистрация игрока и клана (1 неделя)

> Каркас (CI, lint, structure) уже сделан в Фазе 0. Этот спринт посвящён бизнес-логике регистрации.

| # | Задача | Критерий приёмки |
|---|---|---|
| 1.1.1 | Подключение aiogram 3.x, dispatcher, middlewares (auth/locale/throttle/error_handler) | `/start` отвечает в ЛС, в группе и в супергруппе |
| 1.1.2 | Подключение PostgreSQL (Neon) + Alembic, первая миграция (`users`, `clans`, `clan_members`, `audit_log`, `activity_lock`, `idempotency_keys`) | Миграция применяется чисто |
| 1.1.3 | Use-case `RegisterPlayer` — **только через ЛС бота** (`chat_type == "private"`). Стартовые параметры: длина=2 см, толщина=1, **титул=null**, **имя=null**, название — расчётное по длине из `balance.yaml`. | Юнит-тесты: попытка регистрации из группы — отказ с подсказкой «напишите в ЛС»; начальные значения соответствуют ГДД §1.1 |
| 1.1.4 | Use-case `RegisterClan` — **только при добавлении бота в группу/супергруппу** (`my_chat_member` событие) | Юнит-тесты: новый чат → запись `clans`; смена `chat_id` (group→supergroup) обрабатывается |
| 1.1.5 | Use-case `JoinClan` — игрок видится в чате клана **И** зарегистрирован в боте → авто-членство | Юнит-тесты: игрок без регистрации в ЛС → `clan_members` не создаётся, бот шлёт инструкцию |
| 1.1.6 | **Заморозка** клана при удалении бота из группы (статус `frozen`, не `archived` и не удаление) | Тест: бот кикнут → `status='frozen'`, история сохранена; повторное добавление → `status='active'` |
| 1.1.7 | Расчёт «Названия» по длине через **редактируемую таблицу** `display_names` в `balance.yaml` (value object `DisplayName`) | Юнит-тесты на границы 10/30/60/100/200/500 см; валидатор отвергает таблицу с дырами/пересечениями |
| 1.1.8 | Reload `display_names` без рестарта бота (через файл-watch или админ-команду `/balance_reload`) | Изменение YAML → `DisplayName` для тех же длин меняется; тест с двумя версиями таблицы |
| 1.1.9 | Команда `/profile` — карточка персонажа из ГДД §2.2 (`presenters/profile.py`). Корректно скрывает отсутствующий титул и/или имя. | Карточка рендерится 1-в-1, ник в формате «Титул Название Имя»; новичок без титула/имени отображается просто как «Пипирик» |
| 1.1.10 | Все мутации обёрнуты в `IUnitOfWork` + `AuditLogger` | Юнит-тесты: `audit_log` содержит запись о регистрации |

> **Удалено vs. предыдущая версия плана:** «Каталог стартовых имён + выдача случайного при регистрации». Согласно ГДД v8 §2.5, имя выбивается дропом из леса, а не выдаётся при регистрации.

### Спринт 1.2 — Правило 20 см и DAU Gate (1 неделя)

| # | Задача | Критерий приёмки |
|---|---|---|
| 1.2.1 | Сервис `progression.can_spend(user, cost)` (порог 20 см после вычета) | Юнит-тесты на: лес (всегда ок), горы (нужно ≥ 20), караван (после взноса ≥ 20), прокачка толщины (после стоимости ≥ 20) |
| 1.2.2 | Activity Lock — таблица + сервис `lock.acquire/release` | Юнит-тесты на конкурентный захват (двойной /forest не проходит) |
| 1.2.3 | DAU-счётчик (in-memory + ежедневный сброс) | `/admin_stats` показывает текущий DAU |
| 1.2.4 | Очередь `signup_queue` + сообщение «Серверы переполнены» | При `MAX_DAU=1` второй игрок попадает в очередь, первый — играет |
| 1.2.5 | Авторазблокировка очереди при падении DAU | Когда DAU < лимит, бот регистрирует и шлёт уведомление |
| 1.2.6 | Команда `/set_max_dau N` (только админ) | Меняет лимит «на горячую», логируется |
| 1.2.7 | Уведомление админа при 80 % от лимита | Срабатывает один раз в сутки |

### Спринт 1.3 — Поход в лес + дроп шмота (1 неделя)

| # | Задача | Критерий приёмки |
|---|---|---|
| 1.3.1 | Команда `/forest` (или кнопка) | Доступна с уровня 1, без порога длины |
| 1.3.2 | Рандом кулдауна 10–20 мин, сообщение «ушёл в лес» | В чате формат из §8.2; ник в формате «Титул Название Имя» |
| 1.3.3 | APScheduler-job на завершение похода | По истечении таймера приходит сообщение «вернулся» |
| 1.3.4 | Расчёт прибавки длины — **3 ветки исходов с весами** (`scarce/normal/abundant`, диапазоны 1–10/5–15/10–20) из `balance.yaml`, секция `forest.outcomes` | Лес **всегда +**; статистика на 10000 прогонов соответствует весам ±2 % |
| 1.3.5 | Дроп предметов 0–1 шт (**включая имя как тип предмета** — это единственный путь получить имя) | В `items_catalog` ≥ 30 предметов на 6 слотов; ≥ 30 имён в каталоге; редкости 70/25/5 % |
| 1.3.6 | Inline-кнопки «Надеть / Выбросить» | Нажатие меняет `equipment` или ничего; повторное нажатие игнорируется |
| 1.3.7 | Замена/выброс имени; **первое получение имени** меняет ник в формате с «Название» на «Название Имя» | При находке имени можно заменить активное или выбросить; новичок без имени → после леса с дропом имени получает имя |
| 1.3.8 | **Выдача титула «Новичок»** при первом успешном возвращении из леса (идемпотентно) | Тест: первый `/forest` → `title=newbie`; второй `/forest` не дублирует выдачу; `audit_log` содержит запись `reason="first_forest_title"` |
| 1.3.9 | Лимит «1 активность» через `activity_lock` | `/forest` во время похода → ошибка «вы заняты» |

### Спринт 1.4 — Прокачка толщины + предсказатель + топ (1 неделя)

| # | Задача | Критерий приёмки |
|---|---|---|
| 1.4.1 | Таблица стоимости толщины (1–20+, формула n²×1000) в `balance.yaml` | Юнит-тесты на стоимости 2/10/15/16/20 |
| 1.4.2 | Команда `/upgrade` с подтверждением | Проверка: уровень+1, стоимость, остаток ≥ 20 см |
| 1.4.3 | Разблокировка активностей по уровню (table в коде) | Юнит-тесты для каждого уровня (1/2/3/4/5/6/7/9) |
| 1.4.4 | Команда `/oracle` (предсказатель) — 1 раз в сутки **по Москве** (`Europe/Moscow`, сброс в 00:00 локального TZ); прибавка `uniform(1, 20)` см из `balance.yaml` (`oracle.cooldown_tz`, `oracle.bonus_min`, `oracle.bonus_max`) | Юнит-тесты: повторный `/oracle` в тот же московский день — отказ; следующий день — успех; статистика на 10000 прогонов: средняя ≈ 10.5 см ±0.5; всегда + длина |
| 1.4.5 | Каталог из 200+ предсказаний (`templates/oracle_ru.json`, `_en.json`) | Файлы валидны JSON, шаблонизация по `{user}` |
| 1.4.6 | Команда `/top` — топ-100 по длине | Кэш на 60 секунд, формат «Титул Название Имя — N см» |
| 1.4.7 | Юнит-тесты + мини-нагрузочный сценарий | 100 параллельных «походов в лес» без потери лока |

### Спринт 1.5 — Локализация, логи, полировка (1 неделя)

| # | Задача | Критерий приёмки |
|---|---|---|
| 1.5.1 | Подключение fluent/i18n, файлы `locales/ru.ftl`, `locales/en.ftl` | Все сообщения вытащены из кода |
| 1.5.2 | Определение языка по `language_code`, fallback EN | E2E-тест на двух пользователей разных локалей |
| 1.5.3 | 300+ JSON-шаблонов забавных логов (RU/EN) | Файлы валидны, рандомайзер с весами |
| 1.5.4 | Аудитлог изменения длины (`audit_log`) | Каждый ±см пишется с причиной (forest/oracle/upgrade/...) |
| 1.5.5 | Базовый docker-compose (бот + локальная PG) | `docker compose up` поднимает локальный стенд |
| 1.5.6 | README + CONTRIBUTING + инструкция деплоя на VPS | Новый разработчик поднимает локально за < 30 мин |
| 1.5.7 | Деплой MVP на VPS 1 GB + Neon free | Бот стабильно работает 24 ч под закрытым тестом |

**Definition of Done MVP:** Игрок может зарегистрироваться, увидеть карточку, сходить в лес, получить шмот, прокачать толщину до 2, использовать предсказание, увидеть себя в топе. Работает RU + EN. Есть DAU Gate.

#### 4.1.5+ Definition of Done — MVP (Спринт 1.5 завершён)

> Финальный чек-лист закрытого альфа-теста. Каждая строка либо проверена кодом и тестами, либо требует ручной валидации после деплоя.

**Архитектура и фундамент (Фаза 0)**

- [x] **Clean architecture** (`domain` → `application` → `infrastructure` → `bot`) — контракт зашит в `import-linter` (3 контракта kept в CI).
- [x] **`mypy --strict`** на всём `src/` — **0 issues**.
- [x] **`ruff check`** + `ruff format` — без замечаний.
- [x] **`pytest`** — coverage **≥ 80 %** (фактически ~97 %).
- [x] **`pip-audit`** — без known CVE на dev-зависимостях.
- [x] **Pre-commit hooks** — ruff, ruff-format, mypy, import-linter.
- [x] **`IUnitOfWork`**, **`IIdempotencyService`**, **`IAuditLogger`**, **`IActivityLockService`** — все state-mutations через транзакции, idempotency-ключи на write-командах, audit-запись на каждом изменении, конкуренция по игроку защищена.
- [x] **`ThrottleMiddleware`** + **`AuthContext`-middleware** — публичные команды rate-limit-нуты, admin-only handler-ы провалидированы централизованно.

**Геймплей (MVP-фичи)**

- [x] **Регистрация (Спринт 1.1)** — `/start` в группе регистрирует игрока и клан атомарно; `/start` в личке отказывает с подсказкой; миграция `chat_migrate_to`; bootstrap super-admin из `BOOTSTRAP_ADMIN_IDS`.
- [x] **Прогрессия / DAU Gate (Спринт 1.2)** — стартовая длина 20 см (минимальная — те же 20); `signup_queue` (FIFO) при `current_dau >= MAX_DAU`; auto-promote при увеличении лимита или уходе игрока; алерт админу при 80 % MAX_DAU (idempotent по дате UTC).
- [x] **Поход в лес (Спринт 1.3)** — `/forest` ролит outcome (branch + length_delta + drop) сразу на старте, hot-reload не ломает результат; cooldown 10–20 мин (`IRandom.randint`); двойной `/forest` → `AlreadyInForestError`; drop 0–1 предмет (probability + name vs equipment + rarity weights `70/25/5`); inline «Надеть/Выбросить»; audit `FOREST_RUN_*`.
- [x] **Прокачка / предсказатель / топ (Спринт 1.4)** — `/upgrade` с защитой «не спустить ниже 20 см» (`InsufficientLengthError`); `/oracle` идемпотентен по `(player_id, date_msk)`; `/profile` (нік с титулом + длина + толщина + инвентарь + клан); `/top` (топ-10 по длине внутри клана).
- [x] **Локализация и полировка (Спринт 1.5)** — Mozilla Fluent (`locales/{ru,en}.ftl`); числа через `NUMBER($x, useGrouping: 0)`; `use_isolating=False` (без bidi-isolation marks); `/lang ru|en`; `PlayerLocaleResolverDB` пробрасывается в фоновые jobs; ≥ 350 forest-логов и ≥ 200 oracle-предсказаний на локаль (с allowed-плейсхолдерами и integration-тест-валидацией); `/balance_reload` admin-only hot-reload.

**DevOps и деплой (Спринт 1.5.H)**

- [x] **`Dockerfile`** — multi-stage (builder venv + runtime slim), непривилегированный пользователь `pipirik:1000`, healthcheck.
- [x] **`docker-compose.yml`** — 3 сервиса (postgres + migrations sidecar + bot); бот ждёт `migrations: service_completed_successfully`.
- [x] **`.dockerignore`** — исключает `.git`, `.env`, `tests/`, `docs/`, кэши.
- [x] **`README.md`** — полный setup/run-гайд (Docker и без), оценочное время поднятия для нового разработчика — < 5 мин.
- [x] **`CONTRIBUTING.md`** — workflow PR, чек-листы SOLID/security, правила git, структура тестов.
- [x] **`ops/runbooks/deploy_vps.md`** — пошаговая инструкция деплоя на VPS 1 GB + Neon free.
- [ ] **24 часа стабильной работы** под закрытым тестом — проверяется руками после деплоя.

**Acceptance: что делает игрок**

Сценарий, который должен проходить полностью без падений:

1. Игрок добавляется в клан-чат → бот видит `chat_member` update.
2. Игрок пишет `/start` → бот регистрирует, выдаёт стартовую длину 20 см и толщину 1, пишет audit `PLAYER_REGISTERED`.
3. Игрок пишет `/profile` → видит карточку.
4. Игрок пишет `/forest` → бот отвечает «ты ушёл в лес» с рандомным flavour-сообщением. Cooldown 10–20 мин.
5. Через cooldown — finished-сообщение: `+N см`, опциональный drop с inline-кнопками «Надеть/Выбросить».
6. Игрок жмёт «Надеть» → инвентарь обновляется; при name-drop ник меняется на «{name} {nick}».
7. Игрок пишет `/upgrade` → подтверждает → толщина 2.
8. Игрок пишет `/oracle` → получает предсказание; повторный `/oracle` в тот же день — то же предсказание.
9. Игрок пишет `/top` → видит топ-10 кланчата по длине.
10. Игрок пишет `/lang en` → следующие сообщения от бота — на английском.

Все шаги покрыты unit + integration-тестами.

**Что НЕ входит в MVP** — анти-чит хардкап (Спринт 1.6, pre-Phase-2 gate); PvP 1×1 и масс-PvP, клановые механики, Глава клана дня, реферальная система — Фаза 2; полный админ-интерфейс — Спринт 2.5; горы, данжон, караваны, рейды — Фаза 3; монетизация (Stars / TON / USDT), Webhook вместо long-polling, Redis-кэш — Фаза 4.

### Спринт 1.6 — Анти-чит хардкап (Pre-Phase-2 gate)

> **Зачем перед Фазой 2:** Фаза 2 вводит PvP и масс-PvP — новые источники прибавки/потери длины с высокой пропускной способностью. Без хардкапа в этих use-cases экспоит даст экспоненциальный рост. Анти-чит должен быть готов **до** PvP-механик. Полная спецификация — в ГДД §3.3.

| # | Задача | Критерий приёмки |
|---|---|---|
| 1.6.1 | Колонки `users.anticheat_ban_until TIMESTAMPTZ NULL` + `audit_log.clamped_from INT NULL` + `audit_log.source TEXT NOT NULL` (миграция, default `'unknown'` для backfill старых записей; новые записи обязаны указывать source) | `make migrations` зелёный; CHECK `source IN ('forest', 'oracle', 'referral_signup', 'referral_thickness', 'pvp_reward', 'caravan_reward', 'raid_reward', 'admin_grant', 'admin_refund', 'stars_payment', 'ton_payment', 'usdt_payment', 'unknown')` |
| 1.6.2 | Конфиг `balance.yaml` секция `anticheat` (см. ГДД §3.3.5) + pydantic-схема + `IBalanceConfig.anticheat` getter | Юнит-тесты на загрузку, дефолтные значения, валидацию |
| 1.6.3 | Доменная сущность `AnticheatWindow` (rolling-агрегация) + порт `IAnticheatRepository.sum_organic_in_window(player_id, since: datetime)` | Юнит-тесты на сумму с разными `source` (organic vs donate vs admin_refund) |
| 1.6.4 | Use-case `progression.add_length(player_id, delta, *, source, reason)` — единая точка начисления длины. Внутри: загрузка `anticheat_ban_until` → если бан → `AnticheatSoftBanError`. Иначе clamp по `daily_cap_cm` и `weekly_cap_cm`, запись в `audit_log` с фактической дельтой и `clamped_from`. После записи trip-wire рекомпьют — если суммы > лимита → `anticheat_ban_until = now + 14d`, action `ANTICHEAT_*_CAP_EXCEEDED`, INotifier→admin alert | Юнит-тесты: clamp до 0, частичный clamp, без clamp, донат не считается, soft-ban блокирует, trip-wire срабатывает на race-симуляции (10×100 параллельных коллов) |
| 1.6.5 | Гейт `AnticheatGuard` для всех «спендалок» длины (`/upgrade`, `/duel`, ставки в каравану, рейдах) — если `anticheat_ban_until > now()` → ошибка «вы в режиме проверки» | Юнит-тесты на каждый гейт |
| 1.6.6 | Миграция всех существующих use-cases (`FinishForestRun`, `InvokeOracle`, `RegisterPlayer` с реферальным бонусом и т. д.) на вызов `progression.add_length(...)` через DI-порт `ILengthGranter` | После рефакторинга — **0** прямых `player.with_length(...)` + `repo.save(player)` в коде (lint-rule на это или ручной audit; `import-linter`-контракт «прибавка длины только через ILengthGranter») |
| 1.6.7 | Bot-команда `/anticheat_unban <tg_id> <reason>` (только `super_admin`, обязательная причина) — снимает `anticheat_ban_until`, пишет `admin_audit_log` | Юнит-тесты на authz, на запись audit-а, на обнуление поля |
| 1.6.8 | Локализация (`anticheat-soft-ban-active`, `anticheat-cap-clamped`, `anticheat-admin-alert`) в `locales/{ru,en}.ftl` | Через `IMessageBundle` (паттерн 1.5.B-F) |
| 1.6.9 | Интеграционный нагрузочный тест: 100 параллельных лесов одного игрока → суточная сумма ≤ 3000, ни одна транзакция не «прорывает» лимит | `tests/integration/load/test_anticheat_concurrent.py` |
| 1.6.10 | Документация: README + операционное руководство по анти-читу (как добавить новый source, как вручную снять бан) — приложение к этому спринту в `development_plan.md` (см. ниже §4.1.6+) | Готов для нового разработчика |

**DoD спринта:** Все use-cases прибавки длины проходят через `progression.add_length`. Хардкап работает в clamp-режиме на штатном пути и в trip-wire-режиме при обходе. Soft-ban на 14 дней снимается автоматически и вручную. Алёрт админу идёт через `INotifier`. Race-test зелёный. Покрытие новых файлов ≥ 90 %.

#### 4.1.6+ Анти-чит — операционное руководство (Спринт 1.6 завершён)

> Игровая спецификация (что такое hardcap, лимиты, soft-ban) — в [`game_design.md` §3.3](game_design.md). Здесь — операционные процедуры для разработчика, который подключается к проекту и должен уметь: 1) понять, как устроены clamp + trip-wire; 2) добавить новый источник прибавки длины (`AuditSource`); 3) вручную снять soft-ban игроку.

**Архитектурный обзор: единая точка прибавки длины — `progression.add_length`**

Любая прибавка длины игроку проходит через `application/progression/add_length.py` (реализация порта `domain/progression/length_granter.py / ILengthGranter`). Прямые `player.with_length(...)` + `repo.save(player)` вне `AddLength` запрещены — `tests/unit/architecture/test_length_granter_only.py` сканит `src/` и заставляет CI падать на любой обход (architecture-guard 1.6.F).

**Ambient-UoW.** Caller обязан открыть `async with uow:` сам, потом звать `await length_granter.grant(...)`. Без открытого `IUnitOfWork`-контекста — `RuntimeError`. Это нужно, чтобы вся прибавка (mutate + audit + trip-wire) и «бизнес-вставки» вызывающего use-case-а (`oracle_invocations.add(...)`, `forest_runs.save(...)`) были в одной транзакции.

**Алгоритм `AddLength.grant(...)`** (внутри открытой транзакции):

1. **Валидация входа** — `source = UNKNOWN` (backfill-маркер) → `LengthDeltaInvalidError`; `delta_cm = 0` → `LengthDeltaInvalidError`; `delta_cm < 0` для не-`admin_refund` → ошибка; `delta_cm > 0` для `admin_refund` → ошибка (refund — сторно, должно быть отрицательным).
2. **Идемпотентность** — если `idempotency_key` передан и виден `IIdempotencyKey`, возвращается no-op (`applied_delta_cm=0`, `triggered_soft_ban=False`).
3. **Загрузка игрока** — `players.get_by_id(...)` → `PlayerNotFoundError` если нет.
4. **Soft-ban-гейт** — `player.is_anticheat_banned(now)` → `AnticheatSoftBanError`. Транзакция откатывается.
5. **Clamp (только для organic)** — `daily = anticheat.sum_organic_in_window(since=now-24h, ...)`, `weekly = anticheat.sum_organic_in_window(since=now-7d, ...)`, `remaining = min(daily.remaining_cap_cm(daily_cap), weekly.remaining_cap_cm(weekly_cap))`, `applied = min(delta, remaining)`. Donate / `admin_refund` — passthrough.
6. **Mutate** — `player.with_length(length + applied)` → `players.save(...)`.
7. **Audit `LENGTH_GRANT`** — `AuditEntry(action=LENGTH_GRANT, source=source, delta_cm=applied, clamped_from=clamped_from, ...)`.
8. **Idempotency-mark** — если `idempotency_key` есть.
9. **Trip-wire** (только organic + `applied > 0`) — рекомпьют `daily_after` / `weekly_after` (включая только что записанный delta — `SqlAlchemyAuditLogger.flush()` делает это видимым в той же транзакции). Если `is_exceeded(cap)` → `player.with_anticheat_ban(until=now + soft_ban_duration_days)` + `players.save(...)` + audit `ANTICHEAT_DAILY_CAP_EXCEEDED` / `ANTICHEAT_WEEKLY_CAP_EXCEEDED` + alert админу через `IAnticheatAdminAlerter`.

**Конфигурация** (`balance.yaml` секция `anticheat`):

```yaml
anticheat:
  daily_cap_cm: 3000
  weekly_cap_cm: 14000
  soft_ban_duration_days: 14
  organic_sources:
    - forest
    - oracle
    - referral_signup
    - raid_reward
    - admin_grant
  donate_sources:
    - stars_payment
    - ton_payment
    - usdt_payment
```

Инварианты (`AnticheatConfig`-pydantic): `daily_cap_cm ≤ weekly_cap_cm`; `organic_sources ∩ donate_sources = ∅`; нет дублей; `unknown` запрещён в обоих; `admin_refund` запрещён в `organic_sources`. Hot-reload через `/balance_reload` (super_admin) — изменение `daily_cap_cm` без рестарта бота.

**Rolling-окно vs календарный сброс.** `IAnticheatRepository.sum_organic_in_window(player_id, since, organic_sources)` — один `SELECT` по `audit_log` с фильтром `target_kind='player' AND target_id=:pid AND source IN (...) AND delta_cm > 0 AND occurred_at >= since`. Используется rolling-окно (`since = now - 24h` / `now - 7d`), а не календарный сброс в полночь. Это защищает от обхода через границу суток («2999 в 23:59 → 2999 в 00:01 = 6000 за 2 минуты»).

**Trip-wire vs clamp.** *Clamp* — штатный путь: на каждом organic-grant-е читается `sum_organic_in_window`, дельта прижимается к `cap - already_consumed`. Игрок не замечает (получил «N см»). *Trip-wire* — «второй эшелон»: срабатывает, если в trip-wire-recompute суммарная organic-дельта **превысила** cap (например, на гонке нескольких параллельных grant-ов или при clamp-bug-е). Ставит soft-ban на 14 дней + audit `ANTICHEAT_*_CAP_EXCEEDED` + Telegram-alert админу.

Под Postgres + REPEATABLE READ + `SELECT FOR UPDATE` на user-row clamp + trip-wire вместе гарантируют «суточная сумма ≤ 3000» — это и есть acceptance ПД 1.6.9. Под SQLite (test-only) clamp может проиграть гонку lost-update-у, но trip-wire всё равно ставит ban.

##### Как добавить новый source (organic-источник прибавки длины)

Допустим, добавляем `dungeon_reward` (organic-источник из новой активити «подземелье»).

1. **Enum.** Добавь значение в `domain/shared/ports/audit.py / AuditSource`:
   ```python
   class AuditSource(StrEnum):
       ...
       DUNGEON_REWARD = "dungeon_reward"
   ```

2. **Миграция.** Расширь whitelist `audit_log.source` миграцией (см. `0007_anticheat_foundation` как образец). Создай `XXXX_extend_audit_source.py` с `op.execute("ALTER TABLE audit_log DROP CONSTRAINT audit_log_source_check")` + `CREATE CONSTRAINT ... CHECK (source IN (..., 'dungeon_reward'))`. Drift-тест в `tests/integration/db/test_migrations.py` сравнит enum vs whitelist миграции.

3. **Конфиг.** Реши: organic или donate. Для organic — добавь в `balance.yaml` `anticheat.organic_sources`. Pydantic-инварианты не дадут продублировать или добавить в обе списка одновременно.

4. **Use-case.** В новом use-case-е звани `length_granter.grant(...)`:
   ```python
   await self._length_granter.grant(
       player_id=player.id,
       delta_cm=reward_cm,
       source=AuditSource.DUNGEON_REWARD,
       reason=f"dungeon_run:{run_id}",
       idempotency_key=f"dungeon_reward:{run_id}",
   )
   ```
   Architecture-guard (1.6.F) **не разрешит** прямой `player.with_length(...)` + `repo.save(...)` в `src/` — CI упадёт на `tests/unit/architecture/test_length_granter_only.py`.

5. **Тесты.** Юнит-тест на сам use-case (mocked `ILengthGranter`); параметризованный кейс в `tests/unit/application/progression/test_add_length.py` на новый source — clamp для organic или passthrough для donate.

6. **Локализация.** Если нужны новые сообщения игроку, добавь ключи в `locales/{ru,en}.ftl` и используй через `IMessageBundle`-bundle (паттерн 1.5.B).

##### Как вручную снять soft-ban

**Через бот-команду (рекомендованный путь).** `/anticheat_unban <tg_id> <reason>` (Спринт 1.6.G). Только в ЛС, только активный `super_admin`.

```
/anticheat_unban 12345 false-positive: legitimate donate burst
```

Алгоритм `LiftAnticheatBan`:
- Проверяет `Admin.can_lift_anticheat_ban()` (только super_admin) → `AuthorizationError` иначе.
- Грузит игрока по `tg_id` → `PlayerNotFoundError` иначе.
- Если бан уже не активен (None или истёк) — идемпотентный no-op без audit-записи.
- Иначе: `player.with_anticheat_ban_lifted(now)` → `players.save(...)` → audit `ANTICHEAT_BAN_LIFTED` с `before/after.anticheat_ban_until`, `actor_id=admin.id`, `reason=<reason>`, `idempotency_key=anticheat_unban:<actor>:<target>:<ts>`.

`reason` обязателен (требование game_design §18.6 — каждый admin-action оставляет след). Пустой reason → use-case бросит `ValueError`, handler отрисует `anticheat-unban-usage`.

**Через прямой SQL (если бот лежит).**

```sql
-- 1. Снимаем поле.
UPDATE users
SET anticheat_ban_until = NULL,
    updated_at          = NOW()
WHERE tg_id = <target_tg_id>;

-- 2. Записываем audit (НЕ ПРОПУСКАТЬ — game_design §18.6 требует, чтобы любое
-- admin-действие оставляло audit-след).
INSERT INTO audit_log (
    occurred_at, action, actor_id, target_kind, target_id,
    before, after, reason, source, idempotency_key
)
VALUES (
    NOW(),
    'ANTICHEAT_BAN_LIFTED',
    <admin_id>,                                  -- из таблицы admins
    'player',
    (SELECT id::text FROM users WHERE tg_id = <target_tg_id>),
    jsonb_build_object('anticheat_ban_until', '<old_iso_ts>'),
    jsonb_build_object('anticheat_ban_until', NULL),
    '<reason>',
    'unknown',                                   -- backfill-маркер для ручного действия
    'manual_unban:<target_tg_id>:' || EXTRACT(EPOCH FROM NOW())::bigint
);
```

**Список забаненных и история trip-wire-событий** (для разбора):

```sql
-- Все активные soft-ban-ы:
SELECT id, tg_id, username, length_cm, anticheat_ban_until
FROM users
WHERE anticheat_ban_until > NOW()
ORDER BY anticheat_ban_until DESC;

-- История anticheat-событий конкретного игрока:
SELECT occurred_at, action, source, delta_cm, clamped_from, reason
FROM audit_log
WHERE target_kind = 'player'
  AND target_id   = (SELECT id::text FROM users WHERE tg_id = <target_tg_id>)
  AND action IN (
      'ANTICHEAT_DAILY_CAP_EXCEEDED',
      'ANTICHEAT_WEEKLY_CAP_EXCEEDED',
      'ANTICHEAT_BAN_LIFTED'
  )
ORDER BY occurred_at DESC;
```

##### Известные ограничения / TODO

- **Snapshot isolation в SQLite-тестах.** Под SQLite + aiosqlite параллельные `AddLength.grant(...)`-вызовы могут проиграть lost-update-гонку на `users.length_cm` (BEGIN DEFERRED + читают один snapshot). На проде (Postgres + REPEATABLE READ + `SELECT … FOR UPDATE` на `users`-row) это не проблема. Если переключаемся на Postgres-integration-тесты — `SELECT FOR UPDATE` на `players.get_by_id` нужно явно добавить в `SqlAlchemyPlayerRepository`.
- **Authz transaction.** `SetMaxDau` и `ReloadBalance` (Спринт 1.5) делают `admins.get_by_tg_id(...)` ДО `async with self._uow:`. На проде это упадёт на `RuntimeError("UnitOfWork is not entered")` — `SqlAlchemyAdminRepository.get_by_tg_id` тянет `uow.session`. В `LiftAnticheatBan` (1.6.G) UoW открыт первой строкой; существующие use-cases оставлены как есть. Тикет-преемник: «починить admin authz-flow для SqlAlchemy-репозитория».
- **`anticheat-admin-alert` локаль.** Зарезервирована, но пока не используется (`StructlogAnticheatAdminAlerter` не локализуется). Будет добавлена при появлении Telegram-канала админ-алёртов.

---

## 5. Фаза 2 — PvP и социалка (3–4 недели)

### Спринт 2.1 — PvP 1×1

| # | Задача | Критерий приёмки |
|---|---|---|
| 2.1.1 | Движок боя: 3 атаки + 3 блока, 3 раунда | Юнит-тесты на все 9 пар атака×блок |
| 2.1.2 | Режимы вызова: «Чат → Глобал», «Только чат», «Только глобал» | Авто-переход в глобал через 3 мин |
| 2.1.3 | Глобальное лобби (Redis-list или PG) | FIFO, тайм-аут 10 мин |
| 2.1.4 | Выбор атаки/блока через ЛС бота, raunds 30–60 сек | AFK → автовыбор |
| 2.1.5 | Расчёт ±длины, шаблоны логов раундов | После боя — карточка результата + кнопка «Поделиться» |
| 2.1.6 | Кулдаун + activity lock | Нельзя одновременно в PvP и поход |

### Спринт 2.2 — Масс-PvP и клановые механики

> Сама регистрация клана уже сделана в Спринте 1.1 (через добавление бота в группу).

| # | Задача | Критерий приёмки |
|---|---|---|
| 2.2.1 | Команда `/clantop` | Топ кланов по сумме длин активных участников |
| 2.2.2 | Масс-PvP: вызов клан→клан, кулдаун 6 ч | Все участники с длиной ≥ 20 см автозаписываются |
| 2.2.3 | Игрок в обоих кланах — пропускает | Юнит-тест |
| 2.2.4 | Боевая механика N×M: 1 атака + 1 блок, случайные пары | Все удары разрешаются за один тик; ничья при 0 живых |
| 2.2.5 | Журнал клановых атак (история в карточке клана) | Тесты: события не теряются при сбое |

### Спринт 2.3 — Глава клана дня 👑

> ГДД §6.1 (v9). Иронично-смешная мини-фича для атмосферы. **Триггер — гибридный** (кнопка от участника / фоновый cron, что наступит первым).

| # | Задача | Критерий приёмки |
|---|---|---|
| 2.3.1 | Доменный сервис `DailyHeadService.assign_or_get(clan_id, source)` + use-cases `RequestDailyHead` (button) и `RunDailyHeadCron` (cron). Через `IRandom` и `IClock` (`Europe/Moscow`-aware) | Юнит-тесты: при < 5 активных в клане — отказ; алгоритм избегания последних 3 при ≥ 10; повторный вызов в тех же сутках возвращает уже назначенного главу |
| 2.3.2 | Кнопка `🎲 Назначить главу дня` / команда `/clan_head` в чате клана | E2E: первый клик — назначение и публикация; второй в тех же сутках — тихое сообщение «уже назначен» |
| 2.3.3 | Cron APScheduler с **per-clan random_offset(0..24h)** от 00:00 МСК (детерминированный hash от `clan_id + date` для воспроизводимости тестов) | Тест: разные кланы получают разные times; тот же `(clan_id, date)` всегда даёт тот же offset; cron не назначает повторно если кнопка уже сработала |
| 2.3.4 | Каталог **иронично-смешных** пацанских цитат `templates/clan_quotes_ru.json` (≥ 100) и `_en.json`. Стилистика: Стэтхем / паблики ВК / АУФ-цитаты, с самоиронией. **Уместный мат разрешён** (`mild_profanity=true` в `balance.yaml.content_policy.clan_quotes`), запрещены: политика, межнацоскорбления, насилие, реклама, секс. | JSON валиден; ≥ 100 цитат на язык; цитаты прошли модерацию; теги стиля заполнены (`statham`, `vk_pablik`, `auf`, `meme`); цитаты с матом помечены тегом `profanity` |
| 2.3.5 | Сообщение в чат клана с цитатой; начисление **`uniform(1, 20)` см** через `progression.add_length(reason="daily_head")` | E2E: сообщение пришло, длина увеличилась, есть запись в `audit_log` с `bonus_cm` в [1, 20] |
| 2.3.6 | Идемпотентность по `(clan_id, moscow_date)` + `source ∈ {button, cron}` (для аналитики) | Тест на гонку «кнопка + cron одновременно» — назначение происходит ровно один раз |
| 2.3.7 | Учёт активности: «активные за 7 дней» — есть запись в `daily_active` | Тест: неактивные участники не попадают в выбор |
| 2.3.8 | Корректный пропуск **замороженных** (`frozen`) и архивированных кланов | Замороженный клан не получает ни кнопочного, ни cron-триггера; после разморозки — получает |

### Спринт 2.4 — Реферальная система и шеринг

> Полная реферальная схема — в ГДД §13.1: при регистрации +5/+1, при достижении новичком толщины 3 → +10 рефереру, при толщине 5 → +30 рефереру.

| # | Задача | Критерий приёмки |
|---|---|---|
| 2.4.1 | Парсинг `start=ref_<id>` в `/start` (только в ЛС) | Запись в `referrals` (`referrer_id, referred_id` уникальная пара); попытка реферирования из группы — отказ |
| 2.4.2 | Начисление **«on_signup»**: +5 см новичку, +1 см рефереру (через `progression.add_length` с `reason="referral_signup"` и `idempotency_key`) | Тест: при регистрации новичок получил +5, реферер +1; повторный вызов того же idempotency_key — no-op |
| 2.4.3 | Начисление **«on_thickness_milestones»**: +10 см рефереру при толщине 3, +30 см при толщине 5 (балансируемо в `balance.yaml`) | Тест: апгрейд новичка до 3 → реферер +10; до 5 → +30; повторное достижение того же уровня — no-op |
| 2.4.4 | Антифрод: 1 рефералка на пару `(referrer_id, referred_id)`, троттлинг по IP/устройству, проверка «один и тот же tg_id не может рефернуть сам себя» | Тест на двойной клик; самореферал отклоняется |
| 2.4.5 | Кнопка «Поделиться» после боя/похода/каравана/рейда | Формирует сообщение из ГДД §13.2 |
| 2.4.6 | Еженедельные итоги (cron вс. 18:00 UTC) | Бот постит в каждый клан карточку из ГДД §13.3 |

### Спринт 2.5 — Админ-интерфейс в боте (основной) 🔧

> ГДД §18.6 (обновлено): **основной канал администрирования — Telegram-бот**. Веб-панель — отдельный опциональный спринт в Фазе 4 (см. §7).
>
> Все use-cases администрирования живут в `application/admin/*` и вызываются как из бот-хэндлеров, так и (потом) из веб-панели — общая бизнес-логика.

| # | Задача | Критерий приёмки |
|---|---|---|
| 2.5.1 | Таблица `admins` (`tg_id`, `role`, `totp_secret`, `created_at`, `created_by`) + миграция | RBAC-роли: `super_admin`, `economist`, `support`, `read_only`; список первых админов берётся из переменной окружения `BOOTSTRAP_ADMIN_IDS` |
| 2.5.2 | Middleware `AdminGuard` для бота: пропускает только `tg_id` из `admins`, проверяет роль, кладёт в context; на чужих — тихо игнорирует | Юнит-тесты на каждое разрешение; неадмин не получает namespace `/admin_*` даже в `getMyCommands` |
| 2.5.3 | Команды поддержки: `/admin_stats`, `/find_player`, `/player`, `/freeze`, `/unfreeze`, `/ban` | Все вызовы пишутся в `admin_audit_log` с `source="bot"`; ответ — карточка/подтверждение |
| 2.5.4 | Команды экономики: `/grant_length`, `/grant_thickness`, `/balance_get`, `/balance_set` | Тесты: некорректные значения отклоняются; idempotency_key вычисляется из `(admin_id, command, target, minute)`; повторная команда в ту же минуту — no-op с предупреждением |
| 2.5.5 | TOTP-подтверждение опасных команд: после `/grant_*`, `/balance_set`, `/ban` бот шлёт «отправь /confirm <6 цифр>»; FSM хранит pending-команду 60 секунд | E2E: команда без `/confirm` — отклоняется; правильный TOTP — выполняет; неправильный — отказ + audit-запись о попытке |
| 2.5.6 | Команды по кланам: `/clan`, `/freeze_clan`, `/unfreeze_clan`, `/clan_daily_head_history` | Поиск работает по `chat_id` и подстроке названия |
| 2.5.7 | Глобальные: `/set_max_dau`, `/announce`, `/audit` | `/announce` рассылается батчами с throttle ≤ 30 msg/sec; `/audit <tg_id|@admin>` отдаёт последние 50 записей |
| 2.5.8 | Таблица `admin_audit_log` (`admin_id`, `action`, `target`, `before`, `after`, `reason`, `source`, `idempotency_key`, `ip`/`tg_chat_id`, `ts`) + миграция | Все мутации (как из бота, так и из веба позже) пишутся атомарно вместе с самой мутацией |
| 2.5.9 | Каркас `application/admin/*` use-cases (один use-case = одна команда). Тонкий бот-handler делает только парсинг и вызов use-case. | Юнит-тесты use-case-ов без бота; будущая веб-панель использует те же use-case-ы |
| 2.5.10 | Документация в `docs/admin_runbook.md`: список команд, права, примеры, порядок реакции на инциденты | Доступна в репо; ссылка из `/admin_help` |

> **Что НЕ в этом спринте:** веб-интерфейс. Он — отдельный спринт 4.5 в Фазе 4 (§7), и он строится поверх готовых use-cases этого спринта.

---

## 6. Фаза 3 — Контент: горы, данжон, караваны, рейды (5–7 недель)

### Спринт 3.1 — Горы и данжон

| # | Задача | Критерий приёмки |
|---|---|---|
| 3.1.1 | `/mountains` (lvl 3+, ≥ 20 см, 20–40 мин, ±длина, 0–1 предмет) | Е2Е сценарии на + и − исход |
| 3.1.2 | `/dungeon` (lvl 6+, ≥ 20 см, 40–60 мин, ±длина, 0–3 предмета) | Дроп до 3 предметов; UI выбора «надеть/выбросить» по каждому |
| 3.1.3 | Дроп **скроллов заточки** в обоих локациях (см. ГДД §2.8): обычные скроллы — горы (очень-очень редко) + данжон (очень редко); blessed-скроллы — только данжон (очень-очень редко). | Юнит-тесты на доменный picker; integration: 1000 прогонов горы + 1000 данжон, частоты в ожидаемых границах |
| 3.1.4 | Дроп **оружия** (`right_hand`, `left_hand`) в обоих локациях, см. ГДД §2.6 | Тот же drop-engine, что и для остального шмота; новые слоты появляются в выдаче «надеть/выбросить» |
| 3.1.5 | Балансировка (`balance.yaml`: вероятности и величины) | Можно крутить ручки без релиза кода |

### Спринт 3.2 — Караваны (полная механика)

| # | Задача | Критерий приёмки |
|---|---|---|
| 3.2.1 | Создание каравана (lvl 7+), задание вклада + клан-получателя (5 рандомных или ручной ввод) | Юнит-тесты на правило «после взноса ≥ 20 см» |
| 3.2.2 | Лобби 20 мин, кулдаун клана 12 ч | E2E: 5 караванщиков + ≤ 4× рейдеров + ≤ 2× защитников |
| 3.2.3 | Роли при двойном членстве (см. ГДД §9.4) | Юнит-таблица всех 5 случаев |
| 3.2.4 | Запрет рейдерства членам обоих кланов | Юнит-тест |
| 3.2.5 | Боевая механика: каждый рейдер — 1 удар, караванщики — 2 блока, защитники — 1 блок | Симуляция 100 караванов; распределение результатов в норме |
| 3.2.6 | Завершение: победа/проигрыш, награды (×4 лидеру, ×3 караванщикам, ×1 защитникам, +1 см клану), Атаман | Все множители из `balance.yaml` |
| 3.2.7 | Идемпотентность начислений, аудит-лог | Повторный обработчик не выдаёт награды дважды |

### Спринт 3.3 — Рейд-боссы

| # | Задача | Критерий приёмки |
|---|---|---|
| 3.3.1 | Вызов босса (lvl 9+, ≥ 20 см, 1/4 ч глобально) | Босс = случайный из топ-30 |
| 3.3.2 | Управление боссом: игрок (если онлайн) → бот (auto) | E2E: AFK босс → бот рандомит |
| 3.3.3 | Лобби 20 мин, пересылаемая кнопка | Минимум 1 рейдер |
| 3.3.4 | Боевая механика: босс — 3 атаки, рейдер — 3 блока | Раунды 20 сек–1 мин |
| 3.3.5 | Завершение: < 10 см у босса = победа рейдеров; иначе босс | Награды и % от системы — из `balance.yaml` |
| 3.3.6 | Per-player ролл скроллов заточки на победу (см. ГДД §2.8.5): обычный скролл — малый шанс; blessed — очень малый. Идемпотентно по `(boss_fight_id, player_id, scroll_kind)`. | Юнит-тесты per-player ролла; integration: 100 рейдов × 5 игроков, частоты в границах |

### Спринт 3.4 — Заточка предметов 🪛

> Sink-механика для лишних СМ. Зависит от 3.1 (источники скроллов) и 3.3 (boss-drop). Реализуется отдельным спринтом, потому что затрагивает доменный слой инвентаря (новый агрегат `EnchantedItem`), бот-UI с warnings/confirmations, и audit-trail.

| # | Задача | Критерий приёмки |
|---|---|---|
| 3.4.1 | Domain: расширение `Item`-агрегата полем `enchant_level: int` (0..30) + категории `weapon`/`armor`/`jewelry` для слотов (см. ГДД §2.6, §2.8.1). Доменный VO `Scroll(category, blessed: bool)`. Domain errors `WrongScrollCategory`, `MaxLevelReached`, `ItemDestroyed`. | Юнит-тесты на каждое правило; mypy --strict |
| 3.4.2 | Persistence: миграция Alembic `add_enchant_level_to_items` + ORM-маппинг + `IItemRepository.update_enchant_level(...)`. | Integration-тесты: round-trip, default `enchant_level=0` для legacy-предметов |
| 3.4.3 | Application: use-case `EnchantItem(*, player_id, item_id, scroll_id) -> EnchantOutcome`. Внутри: load + check category + roll исход через `IRandom` + audit `ITEM_ENCHANT_ATTEMPT` + idempotency-key. Отдельный use-case для blessed (или enum-флаг). | Юнит: всех 4 (regular) и 5 (blessed) исходов; idempotency повторного применения; категория-mismatch → `WrongScrollCategory` |
| 3.4.4 | Доменный picker `pick_enchant_outcome(*, level, blessed, weights)` — чистая функция. | Юнит-тесты на: (a) safe-zone forced-success, (b) все 4/5 исходов в каждом тире, (c) `clamp(0, 30)` на нижней границе |
| 3.4.5 | Балансовый конфиг: pydantic `EnchantmentConfig` с инвариантами (см. ГДД §2.8.6: сумма весов = 1.0; safe-zone-zero для drop/destroy; `blessed_outcomes_per_level["29"].success_2 == 0.0`, см. ГДД §2.8.4). Стартовые дефолты для всех уровней `0..29` уже зафиксированы в ГДД §2.8.6 — копируются в `balance.yaml` как есть. | Юнит-тесты на pydantic-валидаторы; интеграционный тест: дефолтный `balance.yaml` парсится без ошибок и сумма весов на каждом уровне = 1.0 ± ε |
| 3.4.6 | Bot-handler `/enchant <item_id> <scroll_id>` или callback из карточки предмета. UX: предупреждение → подтверждение → ролл → результат с emoji-индикатором тира (см. ГДД §2.8.7). | Handler-тесты; визуальная проверка предупреждений в RU+EN |
| 3.4.7 | Локализация ключей `enchant-*` (RU+EN): `enchant-warning-regular`, `enchant-warning-blessed`, `enchant-success`, `enchant-no-effect`, `enchant-drop`, `enchant-destroy`, `enchant-tier-{safe,easy,hard,very-hard,extreme,impossible}`, `enchant-wrong-category`. | Все ключи присутствуют в обоих файлах; e2e-snapshot |
| 3.4.8 | Отображение `+N` рядом с именем предмета во всех местах: `/profile`, инвентарь, нотификации о дропе, audit-лог. | Снэпшот-тесты презентеров |
| 3.4.9 | Trip-wire анти-чита: аномальные серии успехов на высоких тирах → admin alert (event `ENCHANT_ANOMALY` в `audit_log`). | Юнит-тест: 10 подряд успехов на тире `+18→+25` → alert |

### Спринт 3.5 — Free-to-play рулетка (без крипто-лотов) 🎰

> Минимальная версия рулетки — без крипто-приза. Запускается в Фазе 3, как только готовы скроллы (3.4) и шмот-эксклюзивы. Крипто-интеграция — в Фазе 4 / Спринт 4.1.

| # | Задача | Критерий приёмки |
|---|---|---|
| 3.5.1 | Domain: порт `IRouletteEngine.spin(*, player, kind: RouletteKind) -> SpinResult`. Доменные исходы: `LengthGain`, `ItemDrop`, `ScrollDrop`, `BlessedScrollDrop`. (Крипто-исход добавится в 4.1.) | Юнит-тесты picker-а; mypy strict |
| 3.5.2 | Application: use-case `SpinFreeRoulette(*, player_id) -> SpinResult`. Внутри: `progression.spend_length(player, 100, reason="roulette_spin")` → `engine.spin(...)` → применение исхода. Audit-trail. | Юнит-тесты + integration: спин с балансом 100 и 99 см |
| 3.5.3 | Конфиг рулетки в `balance.yaml` (стартовые дефолты — в ГДД §12.4.2): `roulette.free.cost_cm`, `roulette.free.outcomes` (5 исходов: length / item / scroll_regular / scroll_blessed / crypto_lot), `roulette.free.length_buckets` (4 бакета СМ для скоса к малым). Доп. инвариант: при пустом крипто-пуле вес `crypto_lot` перетекает на `length`. | Pydantic-валидаторы; сумма весов = 1.0 на каждой группе; интеграционный тест 10000 спинов: `E[CM | spin]` ≈ 50 ± 5 см (sink работает) |
| 3.5.4 | Эксклюзивный шмот `roulette_only: true` в каталоге предметов (минимум 5 предметов на каждую категорию слотов на старте). | Catalogue smoke-test: для каждого слота есть ≥ 1 roulette_only-предмет |
| 3.5.5 | Bot-handler `/roulette_free` + кнопка из `/profile` + анимация-крутилка (3-5 промежуточных сообщений с задержкой) + финальная карточка результата. | Handler-тесты + manual smoke в RU+EN |
| 3.5.6 | Локализация `roulette-free-*` (RU+EN). | Все ключи в обоих файлах |
| 3.5.7 | Доступ — с уровня толщины 2 (см. ГДД §12.4.1). | Юнит-тест: lvl 1 → отказ с подсказкой |

---

## 7. Фаза 4 — Монетизация и масштаб (3–4 недели)

### Спринт 4.1 — Монетизация и масштаб (основное)

| # | Задача | Критерий приёмки |
|---|---|---|
| 4.1.1 | Telegram Stars: **платная рулетка** за 1 ⭐ (1 спин) и 9 ⭐ (10 спинов, 10-pack). См. ГДД §12.5; стартовые веса призов и бакеты СМ — §12.5.2. | Расчёт случайного выигрыша; чек-лог транзакций; 10-pack идёт одной транзакцией; integration 10000 спинов: `E[CM | spin]` ≈ 27 см (баланс смещён к не-CM призам и blessed-скроллам) |
| 4.1.2 | TON Connect: фикс длина за TON | Sandbox + продакшн-сеть; webhook/poll платежей |
| 4.1.3 | USDT (через TON-сеть/процессор) | Параметризованные суммы → длина |
| 4.1.4 | Антифрод платежей, проверка двойных зачислений | Idempotency-key на платёж |
| 4.1.5 | **10 % от каждого донат-зачисления → крипто-призовой пул** (см. ГДД §12.6). `RecordDonation` use-case при подтверждении платежа делает второй проводкой `IncreasePrizePool(currency, amount=donation*0.10)`. Идемпотентно. | Юнит-тесты на all 3 валюты; integration: подтверждённый донат 100 ⭐ → пул вырос на 10 ⭐ |
| 4.1.6 | **Призовой пул** — domain-агрегат `PrizePool(stars, ton_nano, usdt_decimal)`. Persistence + миграция. Audit-лог любого изменения. | Юнит-тесты на инкременты/декременты; round-trip persistence |
| 4.1.7 | **Лот-генератор** (`PrizePoolService.regenerate_lots`, см. ГДД §12.6.3). Cron 1×/час + триггер после крупного донат-зачисления. Учёт комиссии: `IFeeEstimator` с P95 за 7 дней. Минимум лота = 1 USD-эквивалент + комиссия; максимум = 10 USD-эквивалент. | Юнит-тесты: пул 3 USDT → 3 лота × 1 USDT; пул 15 USDT → 1 лот × 10 USDT (5 USDT остаются); комиссия > buffer → лот возвращается |
| 4.1.8 | **Крипто-приз** в результат-пуле платной + free-рулеток (см. ГДД §12.4.2, §12.5.2). Если активных лотов в данной валюте нет — слот криптоприза занимает СМ-приз. | Юнит-тесты picker-а: пул пуст → крипто-приз не появляется |
| 4.1.9 | **Выплата выигрыша**: handler «Привязать кошелёк» + use-case `ClaimPrize(player, lot_id, recipient_address)` + транзакция через TON SDK. Жёсткая защита: `actual_fee > fee_buffer` → лот возвращается в пул, выплата откладывается. | Юнит-тесты на все ветки; integration в TON sandbox |
| 4.1.10 | Админ-команды `/prize_pool`, `/refund_lot <lot_id>`, `/freeze_payouts` (super_admin + TOTP, см. ГДД §12.6.6) | RBAC-тесты; audit-записи `ADMIN_PRIZE_*` |
| 4.1.11 | Лимиты выплат на игрока: `max 50 USDT-экв за 30 дней` (TODO(balance): финальное число). Сверх лимита — выплата ставится в очередь. | Юнит-тесты на rolling 30 day window |
| 4.1.12 | Переход на Redis (лобби, очереди, DAU, locks) | Нагрузочный тест 10× от MVP |
| 4.1.13 | Перевод предсказаний/логов на ИИ (опционально) | Кэш на сгенерированных ответах |
| 4.1.14 | Доп. языки: PT, ES, TR, ID, FA, UK | Файлы переводов, тест fallback |
| 4.1.15 | Метрики и дашборд (Prometheus + Grafana) | Графики DAU/RPS/караваны/рейды + крипто-пул per currency |

### Спринт 4.5 — Веб-админ-панель (опционально) 🌐

> Опциональный спринт. Делается после того, как бот-админка из Спринта 2.5 показала, какие операции упираются в неудобство Telegram (длинные таблицы, массовые выборки, редактор YAML, редактор `display_names`). Use-cases уже готовы из 2.5 — этот спринт только добавляет HTTP-фронт.

| # | Задача | Критерий приёмки |
|---|---|---|
| 4.5.1 | FastAPI-проект `admin/web/` с auth через **Telegram Login Widget** | E2E: вход через TG, выход; неавторизованный — 401 |
| 4.5.2 | Тот же RBAC из таблицы `admins` (Спринт 2.5) | Тесты на каждое разрешение; нет отдельной системы пользователей |
| 4.5.3 | 2FA (TOTP) — тот же секрет, что в боте (`admins.totp_secret`) | Включается обязательно при первом входе; QR показывается, если не настроен |
| 4.5.4 | Дашборд: DAU/MAU/concurrent, очередь регистраций, активные караваны/рейды, ошибки | Реальные данные из PG/метрик |
| 4.5.5 | Раздел «Игроки»: поиск, карточка, журнал активности | Поиск отзывчивый (< 200 мс на тестовых 10k записей); действия идут через те же use-case-ы из `application/admin/*` |
| 4.5.6 | Раздел «Кланы»: карточка, история «Главы клана дня», заморозка/разморозка | Замороженный клан виден отдельным фильтром; история не теряется |
| 4.5.7 | Раздел «Аудит-лог»: фильтрация по `audit_log` и `admin_audit_log` | Поиск по дате/пользователю/действию/source (`bot`/`web`) |
| 4.5.8 | Редактор `display_names` и других секций `balance.yaml` | Валидация → сохранение с версией → hot-reload в боте |
| 4.5.9 | Сетевой доступ к панели — белый список IP / VPN / SSH-tunnel | Деплой на отдельный поддомен; никаких публичных дёргалок |
| 4.5.10 | Все действия параллельно вызывают use-cases — поведение и `admin_audit_log` идентичны бот-команде | Юнит-тесты use-case-ов и интеграционные на оба источника (`source="bot"` vs `source="web"`) |

---

## 8. Кросс-функциональные направления (идут параллельно)

### 8.1 Тестирование
- **Юнит** — `domain/*` + `application/*` ≥ **80 %** (политика проекта).
- **Интеграционные** — repos + use-case с реальной PG (testcontainers/Neon-бранч).
- **E2E** — pytest-asyncio + мок Telegram (`aiogram-tests`/`aiogram-mocked`).
- **Симуляция** — отдельный CLI `python -m pipirik.simulate caravan --n 1000` для балансировки.
- **Антирегресс** — снапшот-тесты сообщений (карточка, лог боя, итоги недели).

### 8.2 Балансировка
- Файл `config/balance.yaml`, hot-reload (через бот-команду `/balance_reload` или file-watcher; в Спринте 4.5 — также через веб-редактор).
- Ключевые секции (минимум на MVP):
  - `display_names` — таблица «Длина → Название» с границами (см. ГДД §2.3 v8). **Полностью редактируемая**, валидируется на отсутствие дыр и пересечений.
  - `forest.outcomes` — 3 ветки исходов леса (`scarce/normal/abundant` с весами и диапазонами min/max).
  - `oracle` — `cooldown_tz: "Europe/Moscow"`, `bonus_min: 1`, `bonus_max: 20`, `distribution: "uniform"`.
  - `referral` — `on_signup: { newbie: 5, referrer: 1 }`, `on_thickness_milestones: [{ thickness: 3, bonus: 10 }, { thickness: 5, bonus: 30 }]`.
  - `thickness.cost_formula`, `daily_head.bonus_cm`, `dau_gate.max_dau` и т. д.
- Регулярная ревизия после каждой фазы.
- История версий `balance.yaml` хранится в БД (`balance_versions`: id, yaml_text, applied_at, applied_by, source) — для rollback и аудита.

### 8.3 DevOps
- VPS 1 GB → 2 GB → 4 GB по таблице из ГДД §19.
- Бэкапы Neon (point-in-time) + еженедельный дамп.
- Алёрты: бот не отвечает > 1 мин, очередь > N, DAU > 80 % от лимита, ошибки платежей.
- Деплой: GitHub Actions → Docker image → VPS (Watchtower / простой `docker compose pull`).

### 8.4 Безопасность и приватность
- Не хранить PII сверх `tg_id`, `language_code`.
- TOS/Privacy в `/help` + ссылка в `/start`.
- Ограничение команд в группах (анти-спам).
- **Отдельные роли БД** для бота и админ-панели (минимально необходимые права).
- Все админские действия — через 2FA + `admin_audit_log`.
- `pip-audit` в CI; high/critical уязвимости блокируют merge.
- Ежеквартальное ручное ревью всего `audit_log` на предмет аномалий.

### 8.5 Поддержка
- Команда `/feedback <text>` → отдельная админ-группа.
- FAQ (RU/EN) в боте.
- Раздел «Игроки» в админ-панели — основной инструмент саппорта.

---

## 9. Риски и митигации

| Риск | Митигация |
|---|---|
| Telegram rate limits на массовые рассылки | Очереди отправки, exponential backoff, батчи |
| Накрутка рефералов | Привязка к tg_id + поведенческий антифрод |
| Перегрузка VPS до апгрейда | DAU Gate + алёрт на 80 % |
| Несбалансированная экономика | Ежетижневая ревизия `balance.yaml` + симулятор |
| Потеря состояния (perezagruzka) | Persistence в PG для всех таймеров (APScheduler jobstore) |
| Двойные начисления длины | Idempotency-keys + audit_log + транзакции `SERIALIZABLE` для критичных мест |
| Эксплойт/баг ускоряет рост длины | Анти-чит хардкап 3000 см/сутки + 14000 см/неделя (clamp на штатном пути + trip-wire с soft-ban-ом 14 дней при обходе); единая точка `progression.add_length(...)`; см. ГДД §3.3, Спринт 1.6 |
| Игроки «застряли» < 20 см | Гарантирован лес и предсказатель «всегда +» (в ГДД); юнит-тесты на это правило |
| Юридические требования к платежам (Stars/TON) | Использовать только официальные API, хранить чеки |

---

## 10. Критерии готовности по фазам

| Фаза | Готовность |
|---|---|
| Фаза 0 | Каркас clean architecture, CI gates (`ruff`/`mypy --strict`/`pytest`/`pip-audit`), `IUnitOfWork`/`IdempotencyService`/`AuditLogger`/`ActivityLock` |
| MVP (Фаза 1) | Регистрация (юзер через ЛС с длиной 2 / толщиной 1 / без титула и имени, клан через добавление в группу с заморозкой при кике), лес (3 ветки исходов + автотитул «Новичок»), толщина, предсказатель (по Москве, +1..+20 см), топ, RU+EN, DAU Gate, рефералка (+5/+1 / +10 за тол. 3 / +30 за тол. 5), бот-админ-команды (`/admin_stats`, `/find_player`, `/freeze`, `/grant_length`), **анти-чит хардкап (3000/14000 см organic, soft-ban 14 дней при превышении, см. ГДД §3.3 и Спринт 1.6)**, деплой |
| Фаза 2 | Полноценный PvP 1×1, масс-PvP, **Глава клана дня** (иронично-смешные цитаты), шеринг, итоги недели, **расширенный бот-админ-интерфейс** (`/clan_*`, `/balance_*`, `/audit`) |
| Фаза 3 | Горы, данжон, караваны, рейд-боссы (по ГДД §9, §10) |
| Фаза 4 | Stars + TON + USDT, Redis, ИИ-генерация, доп. языки, метрики; **опциональная веб-админ-панель** (поверх готовых use-cases) |

---

## 11. Открытые вопросы (требуют уточнения)

### Закрытые в v8 ГДД (зафиксированы)
- ✅ **Базовая длина новичка** = 2 см.
- ✅ **Базовая толщина** = 1.
- ✅ **Стартовый титул** — нет; «Новичок» выдаётся при первом возвращении из леса.
- ✅ **Стартовое имя** — нет; имя выбивается дропом из леса (тип предмета).
- ✅ **Реферальная схема** — +5/+1 при регистрации, +10 рефереру за тол. 3, +30 за тол. 5.
- ✅ **Лес — диапазоны прибавки** — 3 ветки исходов с весами (1–10 / 5–15 / 10–20). Точные веса — балансировать.
- ✅ **Кулдаун `/oracle`** — по `Europe/Moscow` (UTC+3), сброс в 00:00 локального TZ.
- ✅ **Прибавка `/oracle`** — `uniform(1, 20)` см.
- ✅ **Кик бота из чата клана** — клан в статус `frozen` (не `archived` и не удаление).
- ✅ **Канал админки** — основной интерфейс через бот; веб-панель — опциональный спринт 4.5.
- ✅ **Стиль пацанских цитат** — иронично-смешные (с самоиронией), без мата/политики.

### Закрытые в v9 ГДД (после мержа PR #1)
- ✅ **Бонус Главы клана дня** — `uniform(1, 20)` см (`balance.yaml: daily_head.bonus_min/bonus_max`).
- ✅ **Время Главы клана дня** — гибридный триггер (кнопка `/clan_head` ИЛИ фоновый cron с per-clan `random_offset(0..24h)` от 00:00 МСК). Распределяет нагрузку и добавляет элемент «кто первый дёрнет».
- ✅ **Веса веток леса** — 50 / 35 / 15 (по умолчанию, балансировать).
- ✅ **`BOOTSTRAP_ADMIN_IDS`** — берётся из env-переменной (секрет в Devin Secrets, `save_scope: org`); таблица `admins` пуста → bootstrap; таблица не пуста → переменная игнорируется.
- ✅ **Каналы как кланы** — отказ полностью; **канал-анонсы** — отдельный спринт **4.9** в самом конце Фазы 4 перед маркетинг-релизом.
- ✅ **Стиль цитат, доп. правила** — уместный мат разрешён (`mild_profanity=true`); запрещены: политика, межнацоскорбления, насилие, реклама, секс. Цитаты с матом помечаются тегом `profanity` для фильтра «детский режим клана» в будущем.
- ✅ **Конфликт «Нежный» vs «Новичок»** — оставляем «Новичок» на «первый лес»; «Нежный» переедет на другой триггер (открытый вопрос Q12b).
- ✅ **Финальная таблица `display_names`** — заглушка из v8 пока остаётся; финальную таблицу геймдиз пришлёт отдельным PR.

### Остаются открытыми
1. **Финальные значения `display_names`** — заглушка остаётся, ждём список от геймдиза.
2. **Точные веса веток леса** — 50/35/15 — балансировать после альфа-теста.
3. **Цена «бесконечной» толщины** — после 20 уровня формула `n²×1000` OK или ужесточаем?
4. **Точные распределения**: `uniform` vs `weighted_buckets` для `/oracle` и `daily_head` (сейчас uniform).
5. **GDPR / полное удаление** — `frozen` для кланов и заморозка для игроков фиксируют состояние, но не удаляют PII. Нужна ли GDPR-функция «удалить полностью» в MVP?
6. **Перенос длины при бане** — длина замораживается или сжигается?
7. **Глобальные ивенты** (праздники, x2 дроп) — нужны ли в MVP?
8. **Антифрод рефералов** — насколько строгий (один-IP-блок vs поведенческий)?
9. **VPN / whitelisted IP для опциональной веб-панели** (Спринт 4.5) — Cloudflare Access / WireGuard / SSH-tunnel — какой механизм? Можно отложить до начала Фазы 4.
10. **Дополнительные точечные запреты в контент-полиси цитат** — есть ли темы/слова сверх текущего списка? (Например: алкоголь, азартные игры, гендерные стереотипы?)
11. **Финальный триггер титула «Нежный»** — после v9 он стал TBD (открытый вопрос геймдизу).
12. **Расширенная таблица титулов** — формулировки и условия остальных титулов (в v9 фиксирован только «Новичок»).
13. **Канал-анонсы (Спринт 4.9)** — какой именно контент туда автопостится (итоги недели / лидерборды / релиз-ноты / всё)? Можно решить позже, ближе к Фазе 4.
14. **Заточка — финальные `success_probability`** — стартовые дефолты для всех уровней `0..29` зафиксированы в ГДД §2.8.6 (полные таблицы regular/blessed). После альфа-теста подбираются по метрикам; настройка через `balance.yaml` без релиза кода.
15. **Заточка — bad-luck protection** — нужна ли «гарантированный успех после N подряд провалов» в MVP механики или только в Фазе 4? (Сейчас не предусмотрена, см. ГДД §2.8.8.)
16. **Эксклюзивный шмот рулетки** — сколько и каких именно `roulette_only` предметов готовить на старте (минимум 5 на категорию слотов в Спринте 3.5.4)? Финальный список — от геймдиза.
17. **Лимит выплат по крипто-пулу** — `max 50 USDT-экв за 30 дней` (Спринт 4.1.11) — это разумный потолок? Нужно посмотреть на регуляторные ограничения и средний AOV.
18. **`IFeeEstimator` стратегия** — P95 за 7 дней vs более агрессивный (P99 / max за 24 часа) — какой кончик оптимизировать: запас или эффективность пула? (Спринт 4.1.7.)
19. **Bad-luck protection для крипто-приза** — после скольких сотен спинов без крипто-приза гарантировать выплату? (Сейчас не предусмотрено; решение по метрикам.)
20. **Переход поля `equipment.kind` enum при добавлении `right_hand`/`left_hand`** — когда именно ввести миграцию: вместе со Спринтом 3.1 (тогда же дроп оружия) или раньше как «зарезервировать слоты»? Решается на старте Фазы 3.
21. **Веса призов рулеток** — стартовые дефолты для free и paid зафиксированы в ГДД §12.4.2 / §12.5.2 (включая бакеты СМ). Подтвердить после альфа-теста: `E[CM | spin]` free ≈ 50 см (sink ~50/спин при цене 100), paid ≈ 27 см.

---

*План синхронизирован с ГДД v9. Любые изменения баланса — через `config/balance.yaml`. Все пункты могут уточняться по мере реализации; правки фиксируются в `history.md`, активные пункты — в `current_tasks.md`. Принципы §0 ГДД (SOLID/ООП/безопасность) — обязательны для каждого PR.*
