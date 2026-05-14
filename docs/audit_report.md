# 🔍 Сводный аудит-отчёт проекта Pipirik Wars

**Дата:** 2026-05-14
**Область:** Весь проект (~602 исходных файла, ~564 тестовых файла)
**Аудиторы:** 5 параллельных AI-агентов
**PR-ы с фиксами:** [#165](https://github.com/Pipirkawar/PipirkaWar/pull/165) (infra), [#166](https://github.com/Pipirkawar/PipirkaWar/pull/166) (admin_web), [#167](https://github.com/Pipirkawar/PipirkaWar/pull/167) (application), [#168](https://github.com/Pipirkawar/PipirkaWar/pull/168) (bot), [#169](https://github.com/Pipirkawar/PipirkaWar/pull/169) (domain)

---

## Часть 1 — Исправленные ошибки

Всего найдено и исправлено **4 бага**, из них **2 критических**.

### 🔴 Критические

#### 1.1. Платежи через Telegram Stars не работали (PR #168)

**Файл:** `src/pipirik_wars/bot/main.py:2591–2596`
**Суть:** В кортеже `_ALLOWED_UPDATES` (типы обновлений для long-polling) отсутствовал `"pre_checkout_query"`. Telegram доставляет только перечисленные типы — без этого типа бот не получал запросы предварительной проверки платежа. Все оплаты платной рулетки (Спринт 4.1-A) автоматически отклонялись Telegram через 10 секунд таймаута.

Хэндлер `handle_pre_checkout_query` был зарегистрирован через `@router.pre_checkout_query()`, но никогда не вызывался.

**Исправление:** Добавлен `"pre_checkout_query"` в `_ALLOWED_UPDATES`.

---

#### 1.2. Раздел «Племена» в веб-панели полностью нерабочий (PR #166)

**Файл:** `src/pipirik_wars/admin_web/routes/clans.py`
**Суть:** Все 4 маршрута (`clans_list`, `clan_card`, `freeze_clan`, `unfreeze_clan`) создавали `SqlAlchemyUnitOfWork` без `async with`, что вызывало `RuntimeError("UnitOfWork is not entered")` при каждом обращении. БД-сессии не открывались, не коммитились и не закрывались.

**Исправление:** Обёрнут весь код в `async with uow:` блоки.

---

### 🟡 Средние

#### 1.3. Обход бана через freeze() → unfreeze() (PR #169)

**Файл:** `src/pipirik_wars/domain/player/entities.py`
**Суть:** Метод `freeze()` проверял только `self.is_frozen`, пропуская BANNED-игроков. Это создавало путь обхода необратимого бана: `BANNED → freeze() → FROZEN → unfreeze() → ACTIVE`. Нарушение инварианта «необратимый бан» (ГДД §18.6).

**Исправление:** `if self.status is not PlayerStatus.ACTIVE: return self` — freeze() на забаненном теперь no-op.

---

#### 1.4. Забаненные игроки могли менять игровые параметры (PR #169)

**Файл:** `src/pipirik_wars/domain/player/entities.py`
**Суть:** `_ensure_active()` проверял только `self.is_frozen`, но не `BANNED`. Игроки со статусом BANNED могли вызывать `with_length()`, `with_thickness()`, `with_title()`, `with_name()`, `without_name()`, `with_username()`.

**Исправление:** `if self.status is not PlayerStatus.ACTIVE: raise PlayerFrozenError(...)` — все мутации заблокированы для неактивных игроков.

---

### 🟢 Мелкие (тесты)

#### 1.5. Тесты i18n не синхронизированы с SUPPORTED_LOCALES (PR #167)

**Суть:** После добавления арабской локали (`ar`) в `SUPPORTED_LOCALES` тесты не были обновлены. 4 тест-кейса падали.

**Исправление:** Обновлены 4 теста: добавлен `ar` в ожидаемые значения.

---

## Часть 2 — Требует внимания владельца

Эти пункты — не баги, а архитектурные вопросы и рекомендации, по которым нужно решение.

### Приоритет: ВЫСОКИЙ 🔴

#### 2.1. Хардкоженные русские строки в хэндлерах бота

**Где:** Несколько хэндлеров в `bot/handlers/`
**Суть:** Часть пользовательских сообщений написана прямо в коде на русском, а не через `.ftl`-файлы локализации. При использовании ES/AR/EN-локали эти строки останутся на русском.
**Решение:** Перенести все строки в `locales/*.ftl`. Рекомендуется перед бетой.

#### 2.2. ErrorHandler молча проглатывает ошибки

**Где:** `bot/middlewares/` (ErrorHandler)
**Суть:** При необработанной ошибке ErrorHandler логирует её, но пользователю отвечает заглушкой (или молчит), скрывая проблему.
**Решение:** Для бета-теста рекомендуется добавить callback в ErrorHandler для оповещения админов о необработанных ошибках.

#### 2.3. `ClaimPrize` — нет явного UoW для status-transition после payout

**Где:** `application/monetization/claim_prize.py`
**Суть:** После фактической выплаты (TON/USDT) статус приза обновляется. Если упадёт между выплатой и обновлением статуса — возможна двойная выплата. Сейчас защищает idempotency-key, но архитектурно UoW для этого critical path не лишний.
**Решение:** Оценить, достаточна ли текущая идемпотентность. Если нет — обернуть в UoW.

---

### Приоритет: СРЕДНИЙ 🟡

#### 2.4. AdminGuardMiddleware работает на ВСЕХ обновлениях

**Где:** `bot/main.py`
**Суть:** `AdminGuardMiddleware` проверяет права на каждом update (включая обычные сообщения игроков), а не только на админских маршрутах. Это лишний DB roundtrip на каждое сообщение.
**Решение:** Переместить middleware только на admin-роутеры.

#### 2.5. `register.py` — DAU-операции вне UoW-транзакции

**Где:** `application/player/register.py`
**Суть:** `record_active` и `check_threshold` вызываются вне транзакции UoW. При race condition возможен пропуск DAU-лимита.
**Решение:** Оценить, критичен ли этот race condition. DAU Gate — rate-limiter, а не security-gate, поэтому может быть допустимо.

#### 2.6. `list_clans` без audit-записи

**Где:** `application/admin/list_clans.py`
**Суть:** В отличие от других admin-операций, `list_clans` не пишет audit log. Все мутирующие операции записывают — только read-side пропущен.
**Решение:** Если нужна полная трассируемость кто что смотрел — добавить audit. Если нет — оставить.

#### 2.7. `get_dashboard_stats` / `get_web_audit_log` — RBAC на уровне route, а не use-case

**Где:** `application/admin/`
**Суть:** Эти 2 use-case не проверяют RBAC сами — полагаются на то, что маршрут уже проверил. Если их вызовут из другого контекста — авторизация не проверится.
**Решение:** Добавить RBAC-проверку в use-case для defense-in-depth, или задокументировать что RBAC — только на уровне route.

---

### Приоритет: НИЗКИЙ 🟢

#### 2.8. `YamlBalanceWriter` теряет YAML-комментарии

**Где:** `infrastructure/balance/writer.py`
**Суть:** `yaml.safe_dump` не сохраняет комментарии. При hot-reload через веб-панель комментарии в `balance.yaml` пропадут.
**Решение:** Мигрировать на `ruamel.yaml` если комментарии важны. Можно отложить.

#### 2.9. `InMemoryTokenBucketRateLimiter` не thread-safe

**Где:** `infrastructure/rate_limit/token_bucket.py`
**Суть:** Документировано. При переходе на multi-worker деплой нужен Redis-бэкенд.
**Решение:** OK для single-worker деплоя (текущая конфигурация). Исправить перед масштабированием.

#### 2.10. Константные оценки комиссий (TON: 0.01, USDT: 0.2)

**Где:** `infrastructure/fees/in_memory_fee_estimator.py`
**Суть:** TODO в коде — заменить на `TonRpcFeeEstimator` после сбора 7 дней реальных данных.
**Решение:** После запуска бета-тестирования и сбора данных.

#### 2.11. 2 устаревших TODO

**Где:**
- `application/bosses/run_boss_round.py` — TODO без деталей
- `application/dto/inputs.py` — TODO без деталей
**Решение:** Проверить актуальность и либо реализовать, либо удалить.

#### 2.12. pip 24.3.1 имеет 4 CVE

**Где:** Окружение разработки
**Решение:** Обновить pip до ≥26.1.

#### 2.13. Версия ГДД: development_plan.md ссылается на v7, README — на v9

**Решение:** Синхронизировать ссылки.

---

## Часть 3 — Описание модулей проекта (простым языком)

Проект построен по принципу «чистой архитектуры» — 4 слоя, каждый зависит только от внутренних:

```
domain (ядро) → application (логика) → infrastructure (внешний мир) → bot/admin_web (интерфейс)
```

---

### 🧠 DOMAIN — Ядро игры (правила без внешних зависимостей)

Этот слой описывает «что такое игра» — все сущности, правила и ограничения. Он не знает ни про базу данных, ни про Telegram, ни про Redis. Чистая бизнес-логика.

#### `domain/player/` — Игрок

Главная сущность игры. Игрок — это запись с:
- **Длина** (length_cm) — основной параметр, растёт от действий
- **Толщина** (thickness) — платный апгрейд (1 → 2 → 3...)
- **Статус**: ACTIVE / FROZEN / BANNED
- **Название** (display_name) — автоматическое по длине (см. `display_names` в balance.yaml)
- **Титул** (title) — присваивается за достижения
- **Имя** (name) — выбивается как дроп из леса

Все изменения иммутабельны: `player.with_length(100)` возвращает нового игрока, старый не меняется.

#### `domain/clan/` — Племя

Племя = Telegram-группа, в которую добавлен бот. Имеет:
- **Список участников** (автоматически)
- **Суммарную длину** всех участников
- **Статус**: ACTIVE / FROZEN (если бота кикнули из чата)
- **Не удаляется** — только замораживается

#### `domain/forest/` — Лес

Поход в лес — основной способ роста. Три типа исходов:
- **Скудный** (50%) — маленькая прибавка (1–10 см)
- **Нормальный** (35%) — средняя (5–15 см)
- **Обильный** (15%) — большая (10–20 см)

Также из леса можно принести предметы (шапка, плащ) и имена.

#### `domain/pvp/` — Дуэли 1v1

Два игрока сражаются, победитель забирает часть длины проигравшего:
- Вызов → принятие → бросок кубиков → определение победителя
- Механика модификаторов (экипировка, толщина)
- AFK-таймер (если не ответил — поражение)

#### `domain/pve/` — PvE механики

Боевая система для битв с NPC (боссы, данжон, горы):
- Раунды с HP
- Механика «попал / промахнулся / крит / уклонение»

#### `domain/mountains/` и `domain/dungeon/` — Горы и Данжон

Два PvE-приключения:
- **Горы:** сложнее леса, больше награда, есть боевая механика
- **Данжон:** многоэтажный, прогрессивная сложность, уникальный лут

#### `domain/caravan/` — Караваны

Групповое PvE:
- Лидер создаёт караван → присоединяются участники → начинается поход
- State-machine: FORMING → TRAVELING → BATTLE → FINISHED/FAILED
- Награда делится между участниками

#### `domain/bosses/` и `domain/raid/` — Рейд-боссы

Масс-PvE на всё племя:
- Босс вызывается командой → все участники бьют по очереди
- State-machine: IDLE → SUMMONED → FIGHTING → DEFEATED/ESCAPED
- Награда всем участникам пропорционально урону

#### `domain/daily_head/` — Глава племени дня

Раз в день в каждом племени выбирается «Глава»:
- Гибридный триггер: кнопка `/clan_head` ИЛИ фоновый cron
- Глава получает бонус к длине (1–20 см)
- Произносит случайную смешную цитату

#### `domain/oracle/` — Предсказатель

Раз в день (по Москве) можно сходить к оракулу:
- Всегда даёт положительную прибавку (1–20 см)
- Случайное предсказание из каталога

#### `domain/inventory/` — Инвентарь

Экипировка для бонусов в PvP/PvE:
- Слоты: голова, тело, руки
- Предметы с редкостью (common → legendary)
- Влияют на модификаторы в боях

#### `domain/enchantment/` — Заточка

Усиление предметов:
- Уровни 0 → 29
- Шанс успеха падает с каждым уровнем
- При провале — потеря уровня (или ничего при «благословлённой» заточке)

#### `domain/roulette/` — Рулетка

Два режима:
- **Бесплатная** — раз в N часов, мелкие призы
- **Платная** — за Telegram Stars, шанс на крипто-приз (TON/USDT)

#### `domain/monetization/` — Монетизация

Три платёжных канала:
- **Telegram Stars** — внутриигровые покупки (толщина, платная рулетка)
- **TON** — криптовалюта, используется как приз
- **USDT** — стейблкоин на TON, используется как приз

Крипто-призовой пул: % от платных рулеток идёт в пул → победители разыгрывают его.

#### `domain/referral/` — Реферальная система

- Пригласил друга → +5 см тебе, +1 см другу
- Друг достиг толщины 3 → +10 см тебе
- Друг достиг толщины 5 → +30 см тебе

#### `domain/balance/` — Конфигурация баланса

Все числа игры (урон, награды, шансы) хранятся в `config/balance.yaml`:
- Hot-reload без перезапуска
- Pydantic-валидация (нет дыр в display_names, валидные формулы)
- 1154 записи display_names, 40 предметов, 32 имени

#### `domain/anticheat/` — Античит

Ограничения на рост:
- **Хардкап**: не более 3000 см/сутки, 14000 см/неделю
- **Trip-wire**: при обходе через баг → мягкий бан на 14 дней
- Единая точка проверки — `ILengthGranter`

#### `domain/admin/` — Админские сущности

Роли (super_admin, moderator), разрешения (RBAC), аудит-лог, TOTP-секреты.

#### `domain/shared/` — Общие порты и ошибки

Интерфейсы (UoW, Clock, Random) и базовые типы ошибок.

#### `domain/security/` — Безопасность

TOTP, HMAC, верификация подписей.

#### `domain/dau/` — DAU Gate

Ограничение дневной аудитории: если DAU > MAX_DAU, новые команды отклоняются. Защита от перегрузки VPS.

#### `domain/signup_queue/` — Очередь регистраций

FIFO-очередь для плавной обработки массовых регистраций.

#### `domain/economy/` — Экономика

Типы валют и курсы для конвертаций.

#### `domain/progression/` — Прогрессия

Формулы апгрейда толщины: стоимость = `n² × 1000` длины.

#### `domain/safety/` — Контент-безопасность

Фильтрация контента (мат, политика, etc.) с тегами для модерации.

---

### ⚙️ APPLICATION — Бизнес-логика (use-cases)

Этот слой координирует действия: «что происходит когда пользователь нажал /forest». Вызывает доменные сущности, работает с базой через порты, записывает аудит.

#### `application/player/` — Use-cases игрока

- `register.py` — регистрация нового игрока (длина=2, толщина=1)
- `set_locale.py` — смена языка
- `set_name.py` — назначение имени (из дропа)

#### `application/forest/` — Use-cases леса

- `start_forest_run.py` — начать поход (проверки: не в бане, не заморожен, нет активного похода)
- `finish_forest_run.py` — завершить поход (начисление длины, дропы, античит)

#### `application/pvp/` — Use-cases дуэлей

- `challenge.py` — вызвать на дуэль
- `accept.py` — принять вызов
- `resolve.py` — определить победителя и перераспределить длину

#### `application/admin/` — Админские use-cases

Все операции через RBAC (`ensure_admin_authorized`) + аудит-лог:
- `grant_length.py`, `freeze_player.py`, `ban_player.py`, `unban_player.py`
- `freeze_clan.py`, `unfreeze_clan.py`
- `find_player.py`, `get_dashboard_stats.py`

#### `application/monetization/` — Платежи

- `record_donation.py` — зафиксировать оплату Stars
- `verify_ton_proof.py` — верификация TON Connect
- `claim_prize.py` — выплата крипто-приза победителю

#### `application/caravans/` — Караваны

Полный lifecycle: create → join → start → battle_round → finish.
State-machine с защитой от некорректных переходов.

#### `application/bosses/` — Рейд-боссы

summon → join → round → finish. Аналогично караванам, но для всего племени.

#### `application/i18n/` — Интернационализация

- `locale.py` — `SUPPORTED_LOCALES` (ru, en, pt, es, tr, id, fa, uk, ar)
- `resolve_locale.py` — определение языка пользователя (BCP-47 → наша локаль)

#### `application/anticheat/` — Античит use-case

`check_and_clamp.py` — проверка хардкапа перед начислением длины.

#### `application/balance/` — Загрузка баланса

`reload_balance.py` — hot-reload balance.yaml без перезапуска бота.

#### Другие модули

- `oracle/` — `/oracle` (ежедневное предсказание + бонус)
- `daily_head/` — выбор главы племени дня
- `inventory/` — экипировка/снятие предметов
- `progression/` — апгрейд толщины
- `roulette/` — бесплатная и платная рулетка
- `referral/` — начисление реферальных бонусов
- `top/` — топ игроков и кланов
- `clan/` — регистрация/заморозка племён
- `ai/` — ИИ-генерация текстов
- `dau/` — подсчёт DAU
- `observability/` — метрики
- `security/` — TOTP setup/verify

---

### 🔌 INFRASTRUCTURE — Внешний мир (БД, Redis, Telegram API)

Этот слой реализует интерфейсы из domain/application — подключается к реальным сервисам.

#### `infrastructure/db/` — PostgreSQL

- SQLAlchemy ORM-модели для всех таблиц
- Репозитории (по одному на сущность)
- Unit of Work (транзакции)
- Alembic-миграции
- Нет SQL-инъекций (все через ORM)
- Idempotency-сервис для защиты от двойных операций

#### `infrastructure/redis/` — Redis

- Activity locks (SET NX PX — атомарные блокировки)
- DAU counter (ZSET с TTL)
- PvP lobby (FIFO-очередь на Lua-скриптах)

#### `infrastructure/payments/` — Платежи

- Telegram Stars: HMAC-SHA256 верификация invoice_payload
- TON Connect: Ed25519 верификация proof
- TON RPC: отправка TON/USDT через Bag of Cells

#### `infrastructure/templates/` — JSON-шаблоны

4 загрузчика (oracle, forest, duel, clan_quotes): lazy-загрузка JSON → кэш per-locale → fallback на RU.

#### `infrastructure/settings/` — Конфигурация

Все настройки через pydantic-settings + environment variables. Секреты через `SecretStr`.

#### `infrastructure/ai/` — OpenAI

Генерация текстов через GPT с фолбэком на статические каталоги.

#### `infrastructure/balance/` — balance.yaml

Loader (lazy + cache + hot-reload) + Writer (атомарная запись + file-lock).

#### `infrastructure/scheduler/` — APScheduler

Отложенные задачи: таймеры леса, гор, AFK в дуэлях, караваны, рейды, daily head.

#### `infrastructure/observability/` — Prometheus

Метрики: Redis-операции, DAU, караваны, рейды, дуэли, рулетка. HTTP-эндпоинт `/metrics`.

#### `infrastructure/telegram/` — Telegram API

Отправка сообщений через aiogram с обработкой ошибок (blocked/deactivated/retry).

#### Другие

- `cache/` — in-memory TTL-кэш для топов
- `clock/` — обёртка над datetime (UTC + Moscow)
- `random/` — криптостойкий RNG (secrets.SystemRandom)
- `rate_limit/` — token-bucket rate limiter
- `dau/` — in-memory DAU counter
- `fees/` — константные оценки gas-комиссий
- `i18n/` — Mozilla Fluent бандлы
- `admin/` — TOTP-верификация + confirm store
- `anticheat/` — логирование срабатываний
- `announcements/` — публикация в канал + статистика

---

### 🤖 BOT — Telegram-бот (интерфейс)

#### `bot/main.py` — Composition Root (точка сборки)

Самый большой файл проекта (~2600 строк). Собирает все зависимости:
1. Читает Settings из env-переменных
2. Создаёт DB engine, Redis client
3. Собирает все репозитории, use-cases, хэндлеры
4. Запускает фоновые задачи (DAU poller, AI refresh, metrics, announcements)
5. Стартует long-polling

Graceful shutdown: при SIGTERM/SIGINT останавливает все фоновые задачи, закрывает пул БД, Redis.

#### `bot/handlers/` — Обработчики команд

Каждый файл — один хэндлер или группа связанных:
- `start.py` — `/start` (регистрация + welcome message)
- `forest.py` — `/forest` (начало похода)
- `duel.py` — `/duel @opponent` (вызов на дуэль)
- `oracle.py` — `/oracle` (ежедневное предсказание)
- `upgrade.py` — `/upgrade` (покупка толщины)
- `profile.py` — `/profile` (карточка игрока)
- `top.py` — `/top` (лидерборд)
- `equip.py` — экипировка предметов
- `enchant.py` — заточка
- `roulette_free.py` — бесплатная рулетка
- `roulette_paid.py` — платная рулетка (Stars)
- `admin_*.py` — админские команды
- И другие...

#### `bot/middlewares/` — Промежуточные обработчики

- **AuthMiddleware** — проверяет что пользователь зарегистрирован
- **LocaleMiddleware** — определяет язык и загружает бандл
- **ThrottleMiddleware** — rate-limiting (защита от спама)
- **AdminGuardMiddleware** — проверка прав админа

#### `bot/presenters/` — Форматирование ответов

Превращают данные в красивые Telegram-сообщения: карточки игроков, логи боёв, лидерборды, итоги дуэлей.

#### `bot/notifications/` — Уведомления

Отправка push-уведомлений: результаты дуэлей, окончание походов, реферальные бонусы.

#### `bot/filters/` — Фильтры

Определяют условия срабатывания хэндлеров: тип чата (private/group), наличие регистрации.

---

### 🖥️ ADMIN_WEB — Веб-админ-панель (FastAPI + HTMX)

#### Аутентификация (4 уровня)

1. **IP Allowlist** — только разрешённые IP/подсети
2. **Telegram Login Widget** — HMAC-SHA256 верификация (не OAuth)
3. **Session** — cookie-based, httponly+secure+samesite
4. **TOTP 2FA** — обязательна для всех мутирующих операций

#### Разделы

- **Дашборд** — DAU/MAU, активные караваны, статистика
- **Игроки** — поиск, карточка, бан/разбан/заморозка, начисление
- **Племена** — список, карточка, заморозка
- **Аудит-лог** — фильтрация по типу/дате/исполнителю
- **Редактор баланса** — правка balance.yaml через веб-интерфейс

#### HTMX

Интерактивность без JavaScript-фреймворков: HTMX-атрибуты для асинхронных обновлений частей страницы.

---

### 📦 CONFIG — Конфигурация

- **`config/balance.yaml`** — все числа игры (1154 display_names, предметы, формулы)
- **`config/templates/*.json`** — текстовые шаблоны (RU/EN/ES/AR): оракул (2643), лес (2000), дуэли (330), цитаты клана (1147)
- **`locales/*.ftl`** — Fluent-файлы интерфейса (RU/EN полные, ES/AR добавлены)
- **`pyproject.toml`** — зависимости, ruff, mypy, pytest
- **`.importlinter`** — 5 архитектурных контрактов (domain ⇏ infra, bot ⇏ admin_web, etc.)

---

### 🧪 Тесты

- **Unit** (~420 файлов): domain + application + infrastructure
- **Integration** (~85 файлов): DB-репозитории с реальной PG
- **E2E** (1 файл): end-to-end через aiogram-mocked
- **Smoke** (3 файла): валидация конфигов (JSON, Grafana)
- **Load** (5 файлов): нагрузочные тесты

---

## Итоговая оценка

| Область | Оценка | Комментарий |
|---------|--------|-------------|
| Архитектура | ⭐⭐⭐⭐⭐ | Clean Architecture строго выдержана, import-linter контракты |
| Безопасность | ⭐⭐⭐⭐ | HMAC, TOTP, SecretStr, no SQL injection; 1 баг с UoW исправлен |
| Тесты | ⭐⭐⭐⭐ | 7000+ тестов, покрытие ~95%; нехватка E2E |
| Платежи | ⭐⭐⭐⭐ | Idempotency, HMAC, Ed25519; 1 баг с pre_checkout_query исправлен |
| Код | ⭐⭐⭐⭐⭐ | mypy --strict, ruff, единый стиль, иммутабельность |
| Документация | ⭐⭐⭐⭐ | ГДД v9, development_plan, CONTRIBUTING; мелкие расхождения |
