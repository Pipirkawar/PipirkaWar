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

## 🟢 В работе — Спринт 1.5 (Локализация, логи, полировка, деплой)

7 задач из §3 / Спринт 1.5 ПД режутся на 6 PR-ов (на два больше, чем в 1.1–1.4: i18n-прогон 5 handler-ов + `/lang` + 300+ шаблонов слишком объёмны для одного PR-а). Цель спринта — закрыть **Definition of Done MVP** (см. `development_plan.md` §4): RU+EN-локализация, аудитлог изменения длины, документация и деплой на VPS.

| PR | Содержимое | Статус | Задачи из `development_plan.md` §3 |
|---|---|---|---|
| **1.5.A** | i18n-фундамент: `application/i18n/` (`Locale` value-object с RU/EN, `LocaleResolver` — strategy «`tg.language_code` → Locale», fallback EN; порт `IMessageBundle` + `MessageKey` NewType + ошибки `I18nError`/`MessageKeyError`); `infrastructure/i18n/FluentMessageBundle` (Mozilla Fluent поверх `locales/{ru,en}.ftl`, ленивый кэш + RU→EN fallback); `LocaleMiddleware` использует `LocaleResolver` и кладёт `Locale` в `data["locale"]`. Стартовый набор ключей `start-*` в `locales/{ru,en}.ftl`. Полные unit-тесты (Locale/LocaleResolver, FluentMessageBundle, LocaleMiddleware, IMessageBundle protocol). | ✅ смержено (PR #25) | 1.5.1 (подключение fluent), 1.5.2 (`language_code` → Locale, fallback EN) — фундамент |
| **1.5.B** | DI-провязка `IMessageBundle` в `Container` / `dispatcher["bundle"]` + первый handler через презентер: `bot/presenters/start.py` (`StartPresenter` поверх `IMessageBundle`), `bot/handlers/start.py` использует резолвенную `Locale` из `LocaleMiddleware` для всех ответов И для `RegisterPlayerInput.locale` (раньше hardcoded `"ru"`). Удалены `REPLY_*_RU`-константы. Тесты handler-а и презентера переведены на `FakeMessageBundle`. | ✅ смержено (PR #26) | 1.5.1 (handler `/start` через `IMessageBundle`), 1.5.2 (`Locale` → `player.locale`) |
| **1.5.C** | `/profile` и `/top` через `IMessageBundle`: `ProfilePresenter` (ключи `profile-group`/`profile-other`/`profile-not-registered`/`profile-card` + локализованный титул через `profile-title-<value>`), `TopPresenter` (`top-header`/`top-empty`/`top-entry`). `FluentMessageBundle` теперь создаётся с `use_isolating=False`, чтобы U+2068/U+2069 (bidi-isolation marks) не засоряли вывод. Тесты на handler-ах и презентерах — через `FakeMessageBundle` (маркерные ключи) + интеграция через `FluentMessageBundle` (RU + EN). | ✅ смержено (PR #27) | 1.5.1 (часть строк из кода → `.ftl`) |
| **1.5.D** | `/oracle` и `/upgrade` через `IMessageBundle`: `OraclePresenter` (`oracle-group`/`oracle-other`/`oracle-not-registered`/`oracle-success`/`oracle-already-used`), `UpgradePresenter` (`upgrade-group`/`upgrade-other`/`upgrade-not-registered`/`upgrade-proposal`/`upgrade-success`/`upgrade-insufficient[-short]`/`upgrade-cancelled`/`upgrade-race`/`upgrade-toast-*`/`upgrade-button-*`). Числовые параметры — через `NUMBER($x, useGrouping: 0)`, чтобы Fluent не вставлял `\xa0` (NBSP) между разрядами. `callback_data` `/upgrade`-кнопок остаётся invariant-форматом и не зависит от локали. Тесты на handler-ах и презентерах — через `FakeMessageBundle` + интеграция через `FluentMessageBundle` (RU + EN). | 🟢 готово к ревью (текущий PR) | 1.5.1 (часть строк из кода → `.ftl`) |
| **1.5.E** | Прогон `/forest` через `IMessageBundle`: notification-презентер + run started/finished, локализация Drop-вариантов и Rarity-меток. Удаление legacy `render_full_nick(...)` после миграции forest-презентера. Команда `/lang ru\|en` — handler в `bot/handlers/lang.py` + миграция `players.locale_override TEXT NULL` + use-case `SetPlayerLocale` + расширение `LocaleMiddleware`-а: приоритет `player.locale_override → tg.language_code → DEFAULT_LOCALE`. Каталог 300+ JSON-шаблонов забавных логов леса (`templates/forest_logs_{ru,en}.json`, рандомайзер с весами по `IRandom`). Подключение к `StartForestRun`/`FinishForestRun`. Ревизия audit-логов: каждая ±см пишется через `AuditLogger` с `LENGTH_DELTA` + причина и `length_before`/`length_after`/`delta_cm`. E2E-тест на двух пользователей разных локалей. | ⚪ бэклог | 1.5.1 (все строки из кода → `.ftl`), 1.5.2 (E2E на двух локалях), 1.5.3 (300+ шаблонов забавных логов), 1.5.4 (audit_log ±см с причиной) |
| **1.5.F** | Базовый `docker-compose.yml` (бот + локальная Postgres + applied migrations). README + CONTRIBUTING + инструкция деплоя на VPS (1 GB RAM + Neon free). Smoke-runbook деплоя в `ops/`. Финальный DoD MVP-чек-лист. | ⚪ бэклог | 1.5.5 (docker-compose), 1.5.6 (README/CONTRIBUTING/deploy), 1.5.7 (деплой MVP на VPS + Neon) |

> **Дизайн-решение по 1.5.A:** `LocaleResolver` стоит в **application** (а не в `domain`), потому что `Locale` — артефакт UI/презентационного слоя: домен (Player/Length/Forest) не должен знать о языках. И не в `bot/middlewares` — middleware должен использовать **порт-стратегию**, чтобы `infrastructure.i18n` (или будущий `/lang`-handler в Спринте 1.5.C) мог переопределять её через DI без переписывания middleware-а. `IMessageBundle` — **port** в application, реализация (`FluentMessageBundle`) — в infrastructure. Это сохраняет однонаправленность зависимостей (см. `.importlinter`).

> **Дизайн-решение по 1.5.B:** Презентер `StartPresenter` — это тонкий класс с DI-параметром `bundle: IMessageBundle`, а не набор module-level-функций. Причины: (1) handler делает один вызов `presenter = StartPresenter(bundle=bundle)` и потом обращается к `presenter.registered(...)/queued(...)` — это сразу читается как «локализованный вид одного экрана», (2) когда в 1.5.C мы добавим аналогичные `ProfilePresenter`/`ForestPresenter`/..., унифицированный класс-API даст одинаковую сигнатуру `__init__(*, bundle)` без копипасты. Параметры plain-методов keyword-only (`locale=`, `position=`) — для type-safety и устойчивости к рефакторингу. Презентер не зависит от `Locale.code` строки — handler и тесты работают через `Locale("ru" | "en")`.

> **Дизайн-решение по 1.5.C:** карточка `/profile` хранится в `.ftl` одним многострочным ключом `profile-card` с `{ $nick }`/`{ $length_cm }`/`{ $thickness_level }` — это удобно переводчику (видит весь layout сразу) и устойчиво к перестановке строк. Локализация титулов сделана через ключи `profile-title-<value>` (`Title.NEWBIE = "newbie"` → `profile-title-newbie`); общий пул для `/profile` и `/top` — чтобы перевод «Новичок/Newbie» не дублировался. Legacy `render_full_nick(...)` *временно* оставлена как pure-функция (RU-only) — ею пользуется `bot/presenters/forest.py`, миграция forest-презентера на `IMessageBundle` идёт в 1.5.D. Параметр `use_isolating=False` у `FluentBundle` важен: по умолчанию Fluent оборачивает `{ $vars }` в Unicode bidi-isolation marks U+2068/U+2069 — корректно для RTL, но в нашем чисто-LTR-наборе (RU/EN) они только засоряют сравнения и копипасту.

> **Дизайн-решение по 1.5.E:** `/lang ru|en` — НЕ доменное правило, а явный override-канал. Хранение per-player локали в `players.locale_override` (миграция). При резолве middleware идёт по приоритету: `player.locale_override` → `LocaleResolver(tg.language_code)` → `DEFAULT_LOCALE = Locale("en")`.

---

## ✅ Завершено (Спринт 1.4 — Прокачка толщины + предсказатель + топ)

7 задач из §3 / Спринт 1.4 ПД, разрезано на 4 PR-а. Спринт закрыт.

| PR | Содержимое | Статус | Задачи из `development_plan.md` §3 |
|---|---|---|---|
| **1.4.A** | Domain `progression/thickness.py`: `cost_for_upgrade(current_thickness, *, cost_base, cost_exponent)` (формула `n²·base`, `n` — целевой уровень) + `is_activity_unlocked(thickness, activity, unlock_levels)` (table-driven, ГДД §3.3) + ошибка `ActivityLockedError`. Use-case `UpgradeThickness` (списание длины через `require_spend(THICKNESS_UPGRADE)`, `with_thickness(level+1)`, audit `THICKNESS_UPGRADE` с `idempotency_key=f"thickness_upgrade:{player_id}:{new_level}"`). Bot-handler `/upgrade` с inline-подтверждением «Подтвердить ХХХХ см / Отменить» + презентер. Композиционный root + полный набор тестов. | ✅ смержено (PR #21) | 1.4.1 (формула n²·base), 1.4.2 (`/upgrade` с подтверждением), 1.4.3 (unlock-таблица для unlock-проверок будущих активностей) |
| **1.4.B** | Domain `oracle/`: иммутабельный `OracleResult` (бонус-cm + темплейт-id) + чистая функция `roll_oracle(*, balance, random, templates)`. Application `IOracleHistoryRepository` (запись «последний `/oracle`-вызов на игрока в Moscow-day»). Миграция `oracle_invocations` (unique по `(player_id, moscow_date)`). Use-case `InvokeOracle` (cooldown_check → roll → длина-grant → audit `LENGTH_GRANT/oracle`). 220 темплейтов в `templates/oracle_ru.json` + 220 в `oracle_en.json` (i18n будет в 1.5). Bot-handler `/oracle`. | ✅ смержено (PR #22) | 1.4.4 (Moscow-TZ кулдаун + uniform(1,20)), 1.4.5 (200+ темплейтов) |
| **1.4.C** | Application `IPlayerRepository.list_top_by_length(limit)` + `SqlAlchemyPlayerRepository.list_top_by_length`. In-memory кэш `TopPlayersCache(ttl=60s)` (порт `ITopPlayersQuery`, реализация поверх IPlayerRepository). Use-case / query `GetTopPlayers(limit=100)`. Bot-handler `/top` + презентер «Титул Название Имя — N см». | ✅ смержено (PR #23) | 1.4.6 (топ-100, кэш 60 с) |
| **1.4.D** | Мини-нагрузочный тест: 100 параллельных `/forest` без потери лока (`asyncio.gather` поверх файлового SQLite). Финальный полировочный round: чистка неиспользуемых импортов в `/top`-хендлере, проверка ПД-чек-листа «всё ли DOD MVP покрыто». | ✅ смержено (PR #24) | 1.4.7 |

> **Дизайн-решение по 1.4.A:** unlock-таблица храним в `balance.yaml::thickness.unlock_levels` (там она и есть с 1.3.A). Но проверка «можно ли войти в активность» — **доменное правило**, поэтому домен принимает её как аргумент (`Mapping[str, int]`), а не лезет в `IBalanceConfig` напрямую. Use-case-ы получают snapshot и зовут `is_activity_unlocked(thickness, activity, unlock_levels=balance.thickness.unlock_levels)`. Это сохраняет чистоту домена и упрощает тесты.

---

## ✅ Завершено (Спринт 1.3 — Поход в лес + дроп шмота)

9 задач из §3 / Спринт 1.3 ПД, разрезано на 4 PR-а. Спринт закрыт.

| PR | Содержимое | Статус | Задачи из `development_plan.md` §3 |
|---|---|---|---|
| **1.3.A** | `balance.yaml`: `forest.drop` (probability/name_share/rarity 70/25/5), `items_catalog` ≥ 30 предметов на 6 слотов, `names_catalog` ≥ 30 имён + pydantic-схемы `ForestDropConfig` / `ForestRarityWeights` / `ItemEntry` (валидация ID-уникальности и покрытия редкостей) + `domain/forest/`: `Slot` / `Rarity` / `Item` / `Name` / `OutcomeBranch` + ADT `Drop = NoDrop \| ItemDrop \| NameDrop` + `compute_forest_outcome(*, balance, random)` (чистая функция через `IRandom`) | ✅ смержено (PR #17) | 1.3.4 (расчёт исхода), 1.3.5 (каталоги предметов/имён, веса редкости) |
| **1.3.B** | Миграция `forest_runs` (partial unique-индекс одна `IN_PROGRESS`-запись на игрока) + `domain/forest/ForestRun` (frozen, `starting()`/`mark_finished()`) + `IForestRunRepository` + `SqlAlchemyForestRunRepository` (`add` / `get_active_by_player` / `save`) + use-case `StartForestRun` (rolled cooldown ∈ [10, 20], `ActivityLockService`, audit `FOREST_RUN_STARTED`) + DI в `bot/main.py::build_container` + полный набор unit/integration-тестов | ✅ смержено (PR #18) | 1.3.9 (activity_lock на /forest) |
| **1.3.C** | Use-case `FinishForestRun` (длина + дроп 0–1, включая имя), титул «Новичок» (идемпотентный, 1.3.8), APScheduler-job (`IDelayedJobScheduler` порт + `APSchedulerDelayedJobScheduler` адаптер), `IPlayerRepository.get_by_id` / `IForestRunRepository.get_by_id`, `StartForestRun` теперь планирует finish-job на `ends_at` | ✅ смержено (PR #19) | 1.3.3, 1.3.7 (смена/дроп имени), 1.3.8 (титул), частично 1.3.5 (применение дропа) |
| **1.3.D** | bot-handler `/forest` (private only, `PlayerNotFoundError`/`AlreadyInForestError` → инструкция/«вы заняты»), `bot/presenters/forest.py` (рендер «ушёл в лес»/«вернулся из леса» + сборка `InlineKeyboardMarkup`), `TelegramForestFinishNotifier` (`IForestFinishNotifier`-порт, отправка post-commit, best-effort), `ApplyForestNameDrop` use-case + callback-handlers `forest:apply_name`/`drop_name`/`equip_item`/`drop_item` | ✅ смержено (PR #20) | 1.3.1, 1.3.2, 1.3.6 (применение/выбрасывание дропа) |

> **Дизайн-решение:** Slot/Rarity вынесены в `domain/balance/config.py` (а не в `domain/forest/`), потому что ими типизирован сам каталог `items_catalog`. `domain/forest/entities.py` реэкспортирует их для удобства. Когда подключим горы / данжон (Спринт 3.x) — те же 6 слотов / 3 редкости останутся источником правды.

> **Долг от 1.3.D:** `equip_item` / `drop_item` / `drop_name` — placeholder-toast. Полная реализация (запись в инвентарь / удаление имени) появится в Спринте 1.5+ после ввода предметов как доменной сущности (`InventoryItem`).

---

## ✅ Завершено (Спринт 1.2 — Правило 20 см и DAU Gate)

Спринт разрезан на 4 PR-а в ту же логику, что и 1.1: маленькие, каждый ~150–500 LoC, без архитектурных слияний. Спринт закрыт.

| PR | Содержимое | Статус | Задачи из `development_plan.md` §3 |
|---|---|---|---|
| **1.2.A** | Domain-сервис `progression.can_spend(length_cm, cost_cm)` + `require_spend(...)` (бросает `InsufficientLengthError`) + константа `MIN_LENGTH_AFTER_SPEND_CM=20` (ГДД §3.1) | ✅ смержено (PR #13) | 1.2.1 |
| **1.2.B** | Domain-`Settings.MAX_DAU` (динамическая) + in-memory `DauCounter` (с ежедневным сбросом) + handler `/admin_stats` + admin-command `/set_max_dau N` + аудит | ✅ смержено (PR #14) | 1.2.3, 1.2.6 |
| **1.2.C** | Миграция `signup_queue` + ветка очереди в `RegisterPlayer` (когда DAU == MAX) + use-case `PromoteFromQueue` (вызывается при `/set_max_dau` на повышение) + сообщение «серверы переполнены» | ✅ смержено (PR #15) | 1.2.4, 1.2.5 |
| **1.2.D** | Уведомление админу при достижении 80 % от `MAX_DAU` (через AuditLogger или structlog алёрт; срабатывает один раз в сутки) | ✅ смержено (PR #16) | 1.2.7 |

> **Заметка по 1.2.2:** `ActivityLock` уже доделан в Спринте 0.2.1 (см. таблицу ниже) — `IActivityLockRepository` + `ActivityLockService` + тест двойного захвата зелёный. В Спринте 1.2 отдельной задачи под него нет; реальное «двойной /forest не проходит» появится в 1.3.9, когда у нас будет /forest handler.

---

## ✅ Завершено (Спринт 1.1 — Регистрация игрока и клана)

5 PR-ов смержено, спринт закрыт. См. [history.md](history.md) (записи 1.1.A → 1.1.E).

| PR | Содержимое | Статус | Задачи из `development_plan.md` §3 |
|---|---|---|---|
| **1.1.A** | Domain layer: `domain/player/` (`Player`, `Length`, `Thickness`, `Title`, `PlayerName`, `DisplayName`, `Username`, `IPlayerRepository`, ошибки) + `domain/clan/` (`Clan`, `ClanMember`, `ChatKind`, `ClanStatus`, `ClanTitle`, `IClanRepository`, `IClanMembershipRepository`, ошибки) | ✅ смержено (PR #8) | 1.1.7 (DisplayName VO), доменная половина 1.1.3/1.1.4/1.1.5/1.1.6/1.1.10 |
| **1.1.B** | `infrastructure/db/migrations/`: alembic-миграция `users`, `clans`, `clan_members` + ORM-модели + `SqlAlchemy{Player,Clan,ClanMembership}Repository` + миграционный smoke-тест | ✅ смержено (PR #9) | 1.1.2 |
| **1.1.C** | `bot/main.py` + `bot/middlewares/`: aiogram 3.x dispatcher, middleware (auth/locale/throttle/error_handler), `/start` stub | ✅ смержено (PR #10) | 1.1.1 |
| **1.1.D** | `application/{player,clan}/`: `RegisterPlayer` (только ЛС), `RegisterClan`/`MigrateClanChatId`/`FreezeClan` (только `my_chat_member`/`migrate_to`), `JoinClan` (только `chat_member`) + handlers `bot/handlers/registration.py` + audit/UoW обёртки + workflow-data DI | ✅ смержено (PR #11) | 1.1.3, 1.1.4, 1.1.5, 1.1.6, 1.1.10 |
| **1.1.E** | `bot/presenters/profile.py` + handler `/profile` + админ-команда `/balance_reload` (live-reload `IBalanceConfig`/`IBalanceReloader`, аудит `BALANCE_RELOAD`) | ✅ смержено (PR #12) | 1.1.8, 1.1.9 |

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
