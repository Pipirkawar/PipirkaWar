# 🍆 Пипирик Варс — Текущие задачи

> Активный список задач на **сейчас**. По мере выполнения задачи переносятся в `history.md`. Длинный план — в `development_plan.md`. ГДД — в `pipirik_wars_plan.md`.
>
> **Легенда статусов:** `🟢 в работе` · `🟡 готово к старту` · `🔵 ждёт уточнения` · `⚪ бэклог`
>
> **Приоритеты:** P0 — блокер, P1 — важно сейчас, P2 — желательно в спринт, P3 — потом.
>
> ⚠️ **Перед стартом любой задачи** — прочитать §0 ГДД (SOLID/ООП/безопасность) и §0 `development_plan.md` (чек-лист на PR).

---

## 🎯 Текущая фаза: **Фаза 0 — Фундамент**

**Цель фазы:** «эталонный» каркас под SOLID/ООП и безопасность. После Фазы 0 любая фича Фазы 1+ добавляется только в виде бизнес-логики, без архитектурных решений «по дороге».

---

## 🟢 В работе — Спринт 1.1 (Регистрация игрока и клана)

Спринт разрезан на серию небольших PR-ов вместо одного «недельного» — каждый PR ~250–500 LoC и ревьюится за 10–15 минут.

| PR | Содержимое | Статус | Задачи из `development_plan.md` §3 |
|---|---|---|---|
| **1.1.A** | Domain layer: `domain/player/` (`Player`, `Length`, `Thickness`, `Title`, `PlayerName`, `DisplayName`, `Username`, `IPlayerRepository`, ошибки) + `domain/clan/` (`Clan`, `ClanMember`, `ChatKind`, `ClanStatus`, `ClanTitle`, `IClanRepository`, `IClanMembershipRepository`, ошибки) | ✅ смержено (PR #8) | 1.1.7 (DisplayName VO), доменная половина 1.1.3/1.1.4/1.1.5/1.1.6/1.1.10 |
| **1.1.B** | `infrastructure/db/migrations/`: alembic-миграция `users`, `clans`, `clan_members` + ORM-модели + `SqlAlchemy{Player,Clan,ClanMembership}Repository` + миграционный smoke-тест | ✅ смержено (PR #9) | 1.1.2 |
| **1.1.C** | `bot/main.py` + `bot/middlewares/`: aiogram 3.x dispatcher, middleware (auth/locale/throttle/error_handler), `/start` stub | ✅ смержено (PR #10) | 1.1.1 |
| **1.1.D** | `application/{player,clan}/`: `RegisterPlayer` (только ЛС), `RegisterClan`/`MigrateClanChatId`/`FreezeClan` (только `my_chat_member`/`migrate_to`), `JoinClan` (только `chat_member`) + handlers `bot/handlers/registration.py` + audit/UoW обёртки + workflow-data DI | 🟢 в работе (PR #11) | 1.1.3, 1.1.4, 1.1.5, 1.1.6, 1.1.10 |
| **1.1.E** | `bot/presenters/profile.py` + handler `/profile` + админ-команда `/balance_reload` (live-reload `IBalanceConfig`) | ⚪ ожидает 1.1.A/B/C/D | 1.1.8, 1.1.9 |

---

## ✅ Завершено (Спринт 0.2 «достройка» — BalanceLoader)

См. [history.md → 2026-05-04 — Спринт 0.2 «достройка»](history.md). Обе задачи закрыты.

| ID | Задача | Статус |
|---|---|---|
| 0.2.9 | Pydantic-схема `BalanceConfig` (display_names, forest, oracle, referral, thickness, dau_gate, daily_head, content_policy) с инвариантами целостности | ✅ |
| 0.2.10 | `YamlBalanceLoader` (lazy + кэш + атомарный hot-reload) + порт `IBalanceConfig` в `domain/balance/ports.py` + интеграция в `Container` | ✅ |

50 новых тестов (39 на схему + 11 на loader + smoke-тест реального `config/balance.yaml`). Общая статистика — 188 тестов, покрытие 94.30 %.

---

## ✅ Завершено (Спринт 0.2 — Каркас безопасности)

PR #5 (см. [history.md → 2026-05-04 — Спринт 0.2](history.md)). Все 11 задач закрыты.

| ID | Задача | Статус |
|---|---|---|
| 0.2.0 | Расширение runtime-deps (`SQLAlchemy[asyncio]`, `asyncpg`, `alembic`, `structlog`) и dev-deps (`aiosqlite`, `freezegun`) | ✅ |
| 0.2.0b | Alembic init (`alembic.ini` + `infrastructure/db/migrations/`) + первая миграция (`idempotency_keys`, `audit_log`, `activity_locks`, `admins`) | ✅ |
| 0.2.0c | `SqlAlchemyUnitOfWork` + `RealClock` + `RealRandom` + рабочий `bot/main.py:build_container()` | ✅ |
| 0.2.6 | `pydantic-settings`: `Settings`/`DatabaseSettings`/`BootstrapSettings`; URL — `SecretStr`; CSV-парсинг `BOOTSTRAP_ADMIN_IDS` | ✅ |
| 0.2.6b | Use-case `BootstrapSuperAdmin` (NO-OP при непустой `admins`; audit `bootstrap`; dedup входа) | ✅ |
| 0.2.1 | `ActivityLock` (domain) + `SqlAlchemyActivityLockRepository` + `ActivityLockService` + тест двойного захвата | ✅ |
| 0.2.2 | `SqlAlchemyIdempotencyService` (диалект-специфичный `INSERT ... ON CONFLICT DO NOTHING`) + тест дубля | ✅ |
| 0.2.3 | `SqlAlchemyAuditLogger` (запись в `audit_log` + откат на исключение) | ✅ |
| 0.2.4 | DTO входов `application/dto/inputs.py`: `RegisterPlayerInput`, `RegisterClanInput`, `GrantLengthInput` (`extra=forbid`, `frozen`, `strict`) | ✅ |
| 0.2.5 | Декораторы `requires_level / requires_length / requires_clan_member` + `AuthContext` + `AuthorizationError` | ✅ |
| 0.2.7 | `InMemoryTokenBucketRateLimiter` + тест `10 cmd/s → 11-я отказ` | ✅ |

138 тестов (49 unit Спринта 0.1 + 89 новых: unit + integration на in-memory SQLite). Покрытие 93%.

---

## ✅ Завершено (Спринт 0.1 — Каркас clean architecture)

PR #3 (см. [history.md → 2026-05-04 — Спринт 0.1](history.md)). Все 8 задач закрыты, локальный `make ci` зелёный, GitHub Actions матрица 3.11/3.12 проходит на пустом репо.

| ID | Задача | Статус |
|---|---|---|
| 0.1.1 | Структура папок (`domain/application/infrastructure/bot/admin/shared`, `tests/{unit,integration,e2e,fakes}`) | ✅ |
| 0.1.2 | `.importlinter`: 3 контракта (layered_architecture, domain-purity, application-purity) | ✅ |
| 0.1.3 | Доменные порты `IClock / IRandom / IUnitOfWork / IIdempotencyKey / IAuditLogger` + fakes + 49 unit-тестов | ✅ |
| 0.1.4 | Composition root `bot/main.py:Container` (frozen dataclass, без сервис-локатора) | ✅ |
| 0.1.5 | `pyproject.toml`: ruff / mypy --strict / pytest 9 / pytest-asyncio 1.3 / pytest-cov / pip-audit / pre-commit / import-linter | ✅ |
| 0.1.6 | `.pre-commit-config.yaml`: standard hooks + ruff + ruff-format + mypy + import-linter (`local`) | ✅ |
| 0.1.7 | `.github/workflows/ci.yml`: матрица 3.11/3.12, отдельный job `audit` (pip-audit) | ✅ |
| 0.1.8 | `Makefile`: install / install-dev / lint / format / typecheck / imports / test / cov / audit / pre-commit / ci / clean | ✅ |

---

## 🔵 Ждёт уточнения от геймдиза/PM (блокирует старт некоторых задач)

> Полный список и статусы — в `development_plan.md` §11.

### ✅ Закрыто в ГДД v8 (2026-05-04)

| ID | Вопрос | Ответ |
|---|---|---|
| ~~Q1~~ | Стартовая длина новичка (см) | **2 см** |
| ~~Q2~~ | Стартовая толщина | **1** |
| ~~Q3~~ | Стартовый титул | **нет**; «Новичок» — после первого леса |
| ~~Q5~~ | Прибавка длины в лесу | **3 ветки** (1–10 / 5–15 / 10–20), веса в `balance.yaml` |
| ~~Q7~~ | Кулдаун `/oracle` | **по `Europe/Moscow`** (сброс в 00:00 МСК); +1..+20 см |
| ~~Q8.1~~ | Куда «попадать» в админку | **в Telegram-бот** (`/admin_*`); веб-панель — опционально в Фазе 4.5 |
| ~~Q10~~ | Стиль пацанских цитат | **иронично-смешные** (Стэтхем / ВК-паблик / АУФ), без мата и политики |
| ~~_новый_~~ | Реферальная схема | +5 новичку / +1 рефереру при регистрации; +10 рефереру за тол. 3; +30 за тол. 5 |
| ~~_новый_~~ | Кик бота из чата клана | **`frozen`** (не архив, не удаление) |
| ~~_новый_~~ | Имя при регистрации | **нет**; имя выбивается дропом из леса (тип предмета) |

### ✅ Закрыто в ГДД v9 (2026-05-04, после мержа PR #1)

| ID | Вопрос | Ответ |
|---|---|---|
| ~~Q4~~ | Бонус и время Главы клана дня | **`uniform(1, 20)` см** раз в сутки. Триггер **гибридный**: кнопка `/clan_head` в чате клана **ИЛИ** фоновый cron на случайный offset 0..24 ч per clan от 00:00 МСК. Идемпотентность — по `(clan_id, moscow_date)`. |
| ~~Q6~~ | Финальная таблица `display_names` | **Заглушка из v8 пока остаётся.** Полная пересборка планируется отдельным PR. |
| ~~Q8.2~~ | tg_id первого админа | Через **секрет `BOOTSTRAP_ADMIN_IDS`** (env), `save_scope: org`. В коде/конфиге — никогда. Bootstrap-логика: если таблица `admins` пуста — env вычитывается и создаётся `super_admin`-запись (одноразово). |
| ~~Q8.3~~ | Веса веток леса | **50 / 35 / 15** (`scarce / normal / abundant`) — оставлено по умолчанию. |
| ~~Q9 (цитаты)~~ | Контент-полиси цитат главы клана | **Уместный мат разрешён.** Запреты: политика, межнацоскорбления, насилие, реклама, секс. Цитата с матом помечается тегом `profanity` для будущего фильтра «детский режим клана». |
| ~~Q11~~ | Канал-как-клан | **Отказ полностью.** Канал-анонсы (другая фича) — отдельный спринт **в самом конце Фазы 4** перед маркетинг-релизом. |
| ~~Q12~~ | Титул «Нежный» | **Оставляем «Новичок»** на «первый лес»; **«Нежный»** переедет на другой триггер — TBD геймдизом (зависит от расширенной таблицы титулов). |

### Остаются открытыми

| ID | Вопрос | Кому | Блокирует |
|---|---|---|---|
| Q9b | Доступ к опциональной веб-админ-панели (если будем делать): VPN / IP-whitelist / Cloudflare Access | PM/devops | Спринт 4.5 (Фаза 4, опционально) |
| Q10b | Дополнительные точечные запреты в контент-полиси цитат (алкоголь, азартные игры, гендер) сверх текущего списка | геймдиз / контент | Спринт 2.3 |
| Q12b | Финальный триггер для титула «Нежный» (после v9) | геймдиз | Спринт 1.3 |
| Q13 | Конкретные условия и формулировки **остальных** титулов (расширенная таблица) | геймдиз | Спринт 1.3+ |

> До получения ответов реализовываем **значения по умолчанию из `balance.yaml`**, отмечаем `# TODO(balance):` в коде.

---

## ⚪ Бэклог ближайших спринтов

| Спринт | Содержимое (укрупнённо) |
|---|---|
| **1.1** Регистрация игрока и клана | Регистрация **только через ЛС** (старт: длина 2, толщина 1, без титула, без имени); клан — **только через добавление бота в группу**; кик бота → `frozen`; `display_names` из `balance.yaml`; карточка `/profile` |
| **1.2** Правило 20 см и DAU Gate | `progression.can_spend`, `signup_queue`, `/set_max_dau`, алёрт админу 80 % |
| **1.3** Поход в лес + дроп шмота | `/forest`, рандом-кулдаун 10–20 мин, **3 ветки исходов** (1–10 / 5–15 / 10–20) из `balance.yaml`, APScheduler-job, дроп предметов 0–1 шт (включая имя), **первый лес → титул «Новичок»** |
| **1.4** Прокачка толщины + предсказатель + топ | `/upgrade`, разблокировка по уровню, **`/oracle` по Москве (`Europe/Moscow`), uniform(1, 20) см**, 200+ шаблонов, `/top` |
| **1.5** Локализация, логи, **базовый админ-интерфейс в боте**, деплой | fluent RU/EN, 300+ JSON-логов, `/admin_stats` + `/find_player` + `/freeze` + `/grant_length`, VPS + Neon free |
| **2.1** PvP 1×1 | Бой 3×3, чат → глобал, шеринг |
| **2.2** Масс-PvP и клановые механики | `/clantop`, масс-PvP, журнал атак |
| **2.3** **Глава клана дня 👑** | **гибридный триггер** (кнопка `/clan_head` или фоновый cron с random_offset(0..24h) per clan), ≥ 5 активных, **`uniform(1, 20)` см**, ≥ 100 **иронично-смешных** пацанских цитат (уместный мат разрешён), идемпотентность по `(clan_id, moscow_date)`; пропуск `frozen`/архивных |
| **2.4** Реферальная система и шеринг | `start=ref_<id>`, **3-этапная схема (+5/+1 → +10 за тол. 3 → +30 за тол. 5)**, антифрод, итоги недели |
| **2.5** **Расширенный админ-интерфейс в боте** 🔧 | `application/admin/*` use-cases, RBAC через `admins`, TOTP-подтверждение опасных команд, `/clan_*`, `/balance_*`, `/audit`, `admin_audit_log` |
| **3.x** Контент | горы, данжон, караваны, рейд-боссы |
| **4.1** Монетизация и масштаб | Stars, TON, USDT, Redis, ИИ, доп. языки, метрики |
| **4.5** **Опциональная веб-админ-панель** | FastAPI + Telegram Login + 2FA (тот же `admins.totp_secret`), RBAC из 2.5, редактор `balance.yaml`, поверх готовых use-cases |
| **4.9** **Канал-анонсы перед публичным релизом** 📣 | Отдельный публичный TG-канал бота: автопостинг итогов недели, лидербордов, релиз-нот; настраивается **в самом конце Фазы 4** перед маркетинг-запуском. Идея: бот сам публикует, без участия админов. |

---

## 🛠️ Параллельные направления (всегда актуально)

- **Тесты:** покрытие `domain/` + `application/` ≥ **80 %**; без тестов задача не считается готовой.
- **Балансировка:** все «магические числа» — в `config/balance.yaml`, не в коде; правки через админ-панель (Фаза 2.5).
- **DevOps:** держать `docker-compose`, `Makefile`, `README.md` в актуальном состоянии после каждого спринта.
- **Логирование:** все мутации длины/толщины/инвентаря/платежей — в `audit_log` с причиной и idempotency-key.
- **Безопасность:** `pip-audit` зелёный, секреты только из env, отдельные роли БД для бота/админки.

---

## 📋 Чек-лист «Definition of Done» для любой задачи

- [ ] **SOLID-чек-лист на PR пройден** (см. `development_plan.md` §0.2).
- [ ] **Чек-лист безопасности пройден** (`development_plan.md` §0.3): транзакции, idempotency, audit_log, pydantic, authz, антифрод.
- [ ] Юнит-тесты добавлены и зелёные (`pytest`).
- [ ] Покрытие нового кода ≥ 80 %.
- [ ] Линтеры зелёные (`ruff`, `mypy --strict`, `import-linter`).
- [ ] `pip-audit` без high/critical.
- [ ] Логика бизнеса в `domain/` или `application/`, не в `bot/handlers/*`.
- [ ] Все строки сообщений — в `locales/*` (RU + EN).
- [ ] Балансовые значения — в `balance.yaml`, не зашиты в код.
- [ ] Описание изменения добавлено в `history.md` (новая запись сверху).
- [ ] Если задача завершена — она удалена из этого файла.

---

## 🔗 Связанные документы

- ГДД: `pipirik_wars_plan.md`
- План разработки: `development_plan.md`
- История: `history.md`

---

*Файл обновляется при каждом изменении статусов. Не копите старое — переносите в `history.md`.*
