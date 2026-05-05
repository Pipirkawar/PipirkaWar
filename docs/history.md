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

## 2026-05-05 — Спринт 1.5.G: каталог 300+ JSON-шаблонов забавных логов леса (RU+EN)

**Автор:** Devin (продолжение работы предыдущего агента)
**Тип:** feature
**Связано:** PR [#TBD], `current_tasks.md` Спринт 1.5.G, ПД 1.5.3.

Что сделано:
- **Стадии 1+2 (предыдущий агент, см. коммиты `c2b8569`, `cdf62a2`)** — фундамент уже был:
  - доменный picker `pick_forest_log_template(*, random, templates)` — чистая функция через `IRandom`, без I/O;
  - `ForestLogTemplate` (frozen dataclass с валидацией id/text);
  - `ForestLogNoTemplatesError` в `domain/forest/errors.py`;
  - порт `IForestLogTemplateProvider.get_templates(*, locale: str) -> Sequence[...]` (lazy кэш per locale, RU-фолбэк, `ForestLogNoTemplatesError` если каталог пуст);
  - адаптер `JsonForestLogTemplateProvider` (зеркало oracle-провайдера: lazy load, дедуп id, валидация формата);
  - подключение к `TelegramForestFinishNotifier` — picker зовётся **вне транзакции** после коммита `FinishForestRun` (best-effort: каталог пуст / провайдер упал → flavour не показываем, основное «вернулся из леса» уходит как было);
  - `ForestPresenter.finished(*, flavor_template: ForestLogTemplate | None = None)` — рендерит flavour-строку через `_render_flavor`, подставляя `{user}` (полный ник) и `{delta}` (берётся из bundle-ключа `forest-flavour-delta`); defensive `try/except (KeyError, IndexError, ValueError)` — кривой плейсхолдер в JSON-каталоге не сломает сообщение игрока;
  - locale-ключ `forest-flavour-delta` в `locales/{ru,en}.ftl`;
  - DI-провязка в `bot/main.py` (`JsonForestLogTemplateProvider(templates_dir=_DEFAULT_TEMPLATES_DIR)` + `RealRandom()` в notifier).

- **Стадии 3+4 (этот PR):**
  - сгенерированы прод-каталоги `config/templates/forest_logs_ru.json` и `config/templates/forest_logs_en.json` — по **350 уникальных шаблонов** на локаль через декартово произведение «эмодзи × сцена × связка × развязка» (грамматика-генератор разово, в коммит не уходит);
  - все шаблоны содержат **только** allowed-плейсхолдеры `{user}` и `{delta}` (валидируется integration-тестом);
  - integration-тест `tests/integration/templates/test_forest_log_loader.py` — зеркало `test_oracle_loader.py`, 22 кейса:
    - прод-файлы грузятся, ≥ 300 шаблонов на локаль, уникальные id, тримнутый текст;
    - `str.format(user=..., delta=...)` проходит без исключений на каждом шаблоне (regex-проверка на отсутствие illegal-плейсхолдеров);
    - lazy-кэш per locale (повторный `get_templates` отдаёт ту же tuple-инстанс);
    - fallback на `"ru"` для неизвестной локали;
    - error-paths: пустой каталог / отсутствие файлов / дубликат id / битый JSON / корень-массив / `templates` не список / запись без `text` / запись не объект → `ForestLogNoTemplatesError` или `ConfigError`.

Результат / артефакты:
- `config/templates/forest_logs_ru.json` (350 шаблонов).
- `config/templates/forest_logs_en.json` (350 шаблонов).
- `tests/integration/templates/test_forest_log_loader.py` (22 теста).
- Локально `make ci` зелёный: ruff/mypy/import-linter/pytest — **1094 passed + 1 skipped**, coverage **96.91 %**.

Заметки / решения:
- **`{user}` и `{delta}` — единственные допустимые плейсхолдеры** в каталоге. Любой другой `{...}` ломает `str.format` → invariant-нарушение, integration-тест на этом падает. Это ставит жёсткий contract между JSON-каталогом и презентером: миграция нумерации / добавление новых параметров требует осознанного PR с обновлением и каталога, и теста, и презентера.
- **Audit `LENGTH_GRANT.source` — отложен в Спринт 1.6** (anti-cheat hardcap). В development_plan.md изначально стояло требование расширить audit полем `source: "forest" | "donate" | ...` в задаче 1.5.4, но `audit_log.source` сам по себе нужен только под античит-агрегацию — так что переезжает в 1.6.A (БД-фундамент античита). Идемпотентность начислений за лес уже обеспечена через `idempotency_key=f"forest_run_finished:length:{run_id}"`.
- **Скрипт-генератор не коммитится** (по требованию HANDOFF.md из стадии 1+2). Только результат — JSON-каталоги.
- **RU и EN — независимые каталоги**, не машинный перевод. Локализация культуры: можно делать ≥ 300 в каждом без жёсткого id-соответствия.

---

## 2026-05-05 — Спецификация: анти-чит хардкап роста длины (3000/14000 см, soft-ban 14 дней)

**Автор:** Devin (по запросу jorey7467)
**Тип:** doc / decision (только документация — кода нет)
**Связано:** ГДД [§3.3](pipirik_wars_plan.md), `development_plan.md` [§4 / Спринт 1.6](development_plan.md), `current_tasks.md` [Спринт 1.6](current_tasks.md). Запрос пользователя: «в документацию нужно добавить записи о функционале для хардкапа и античита, если в сутки у кого-то пипирка выросла на 3000см то он достигает суточного лимита. Так же есть недельный лимит 14000см. Если у кого-то все-же какимто образом у игрока пипирка за сутки выросла более чем на 3000см, то софт бан на 2 недели — нельзя растить пипирку и пометка админу. Так же эти лимиты никак не касаются донатных сантиметров, там нет никаких ограничений, за деньги любая длинна.»

Что сделано:
- **`docs/pipirik_wars_plan.md` §3.3** (новый раздел «Хардкап роста длины (анти-чит)»): полная игровая спецификация. Два rolling-окна (24 ч / 7 дней), лимиты 3000 / 14000 см, эшелонированная защита (clamp на штатном пути + trip-wire при обходе). Soft-ban на 14 дней с автоматическим снятием. Перечисление organic-источников (лес, предсказатель, рефералка, награды PvP/караванов/рейдов, `/grant_length` админа) и donate-источников (Stars / TON / USDT — без лимитов). Конфиг в `balance.yaml` секция `anticheat` (hot-reload через `/balance_reload`). DoD-сценарии для тестов (10 последовательных лесов, race-test, soft-ban не блокирует `/profile`).
- **`docs/development_plan.md`:**
    - §0.3 «Чек-лист безопасности»: добавлен пункт про прохождение всех начислений длины через `progression.add_length(...)` (clamp + trip-wire).
    - §4 / новый Спринт 1.6 «Анти-чит хардкап (Pre-Phase-2 gate)»: 10 задач (миграция БД, конфиг, `AnticheatWindow` + порт, центральный use-case `progression.add_length`, гейт спендалок, миграция всех существующих use-cases на `ILengthGranter`, bot-команда `/anticheat_unban`, локализация, нагрузочный race-test, документация). Зачем перед Фазой 2 — пояснено в эпиграфе.
    - §10 «Критерии готовности по фазам»: в строку «MVP (Фаза 1)» добавлено обязательное прохождение анти-чит хардкапа.
    - §9 «Риски и митигации»: новый риск «Эксплойт/баг ускоряет рост длины» с митигацией.
- **`docs/current_tasks.md`:** новый блок «⚪ Бэклог — Спринт 1.6 (Анти-чит хардкап, pre-Phase-2)» c разрезкой на 8 PR-ов (1.6.A — БД-фундамент, 1.6.B — конфиг, 1.6.C — `AnticheatWindow` + порт + repo, 1.6.D — `progression.add_length` + race-test, 1.6.E — `AnticheatGuard` для спендалок, 1.6.F — миграция всех существующих use-cases на `ILengthGranter` + import-linter-контракт, 1.6.G — `/anticheat_unban` + локализация, 1.6.H — нагрузочный тест + документация). Каждый PR имеет дизайн-решения в эпиграфе. Также в этом коммите 1.5.F помечена `✅ смержено (PR #30)` (была `🟢 готово к ревью` после мержа).

Заметки / решения:
- **Почему rolling-окно, а не календарные сутки.** Календарный сброс в полночь (как у `/oracle`) даёт зону уязвимости в 1–2 минуты вокруг границы суток: игрок может прибавить 2999 в 23:59 и ещё 2999 в 00:01 — и получить 6000 за пару минут. Rolling-окно (`ts > now() - INTERVAL '24h'`) закрывает эту дыру. Минус — сложнее коммуникация игроку, компенсируется явным «следующее окно открывается через N часов» в сообщении.
- **Почему clamp до 0, а не reject.** При `delta_requested=12, remaining=5` начисляется 5 (а не 0). Альтернатива «всё или ничего» дала бы более понятный UX, но игрок терял бы часть награды. Поле `clamped_from` в `audit_log` сохраняет полный контекст для метрик и debug-а.
- **Почему soft-ban, а не hard-ban.** При срабатывании trip-wire игрок не блокируется полностью — он сохраняет доступ к `/profile`, `/top`, `/help`, чату. Бан изолирует только прогрессию (рост и трату длины). Это снижает урон от ложных срабатываний (race-condition на 1 см выше лимита) и даёт админу время разобраться без drama.
- **Почему trip-wire, а не только clamp.** `clamp` защищает от штатных багов (округление, конкурентные mutations). `trip-wire` ловит то, что прорвалось мимо `clamp`: гонки, прямые БД-правки, ошибочные ручные `grant_length`, баги в новых use-cases, забывших позвать `clamp`. Эшелонированная защита.
- **Почему перед Фазой 2.** Фаза 2 вводит PvP и масс-PvP — новые источники прибавки/потери длины с высокой пропускной способностью. Без хардкапа в этих use-cases один экспоит даст экспоненциальный рост по экономике. Анти-чит должен быть готов **до** PvP-механик, иначе придётся переделывать каждый PvP-use-case.
- **Почему донат вне лимитов.** Это явное product-решение из ГДД §12 — донатная длина теряется как обычная, но **никак не ограничивается** в начислении. Платёжный канал — отдельный экономический контур, защищённый платёжным процессором (idempotency по `payment_id`).
- **Почему не сделано прямо сейчас.** Текущая работа в Спринте 1.5 (локализация и деплой). Анти-чит хардкап — отдельный спринт с собственными миграциями БД и cross-cutting рефакторингом всех существующих use-cases прибавки длины. Объединять с 1.5 нельзя — разные обязательства DoD.

---

## 2026-05-05 — Спринт 1.5.F: `/lang ru|en` + `users.locale_override` + per-player локаль в фоновых job-ах

**Автор:** Devin (по запросу jorey7467)
**Тип:** feature (бот-команда + миграция + use-case + расширение `LocaleMiddleware` + интеграция в notifier)
**Связано:** Текущий PR (Спринт 1.5.F), [development_plan.md §3 / Спринт 1.5, задача 1.5.2](development_plan.md), [current_tasks.md Спринт 1.5 → 1.5.F](current_tasks.md). Продолжение Спринта 1.5 после смерженного 1.5.E (PR #29).

Что сделано:
- **Миграция `0006_users_locale_override`** (`src/pipirik_wars/infrastructure/db/migrations/versions/20260505_0006_users_locale_override.py`): добавлена колонка `users.locale_override TEXT NULL` + CHECK-constraint `users_locale_override_supported` (`locale_override IS NULL OR locale_override IN ('ru', 'en')`). NULL = «нет override-а», `LocaleMiddleware` фоллбэчит на tg.language_code → DEFAULT_LOCALE. Миграция использует `op.batch_alter_table(...)` для совместимости с SQLite (dev/тесты): SQLite не умеет `ALTER ... ADD CONSTRAINT`, Alembic делает copy-and-move через batch.
- **Domain `Player.locale_override`** (`src/pipirik_wars/domain/player/entities.py`): новое опциональное поле `locale_override: str | None = None` + метод `with_locale_override(locale_override, *, now)` (frozen-replace + idempotent: возвращает `self` если значение не меняется).
- **ORM `UserORM.locale_override`** (`src/pipirik_wars/infrastructure/db/models/player.py`): mapped-column `String(8) NULL` + table-level `CheckConstraint` (mirror к миграции).
- **Repo persistence** (`src/pipirik_wars/infrastructure/db/repositories/player.py`): `_to_domain` подхватывает `row.locale_override`; `add` и `save` пробрасывают `player.locale_override` обратно в `UserORM`.
- **Audit-action `PLAYER_LOCALE_SET`** (`src/pipirik_wars/domain/shared/ports/audit.py`): новый AuditAction для трассировки изменений локали.
- **Use-case `SetPlayerLocale`** (`src/pipirik_wars/application/player/set_locale.py`): `execute(*, tg_id, locale: Locale | None)` — валидирует локаль через `SUPPORTED_LOCALES` (защита от обхода SUPPORTED_LOCALES снаружи), открывает UoW, читает игрока (бросает `PlayerNotFoundError` если нет), вызывает `player.with_locale_override(...)`, сохраняет, пишет audit-запись `PLAYER_LOCALE_SET` с before/after `{locale_override: ...}`. `locale=None` → сброс override-а.
- **Port `IPlayerLocaleResolver`** (`src/pipirik_wars/application/i18n/player_locale.py`): `Protocol` с одним методом `resolve_for_tg_id(tg_id) -> Locale | None`. Используется и в `LocaleMiddleware` (резолв override игрока перед вызовом handler-а), и в фоновых notifier-ах (`TelegramForestFinishNotifier` — для рендера в локали игрока без `update.from_user`).
- **Implementation `PlayerLocaleResolverDB`** (`src/pipirik_wars/infrastructure/i18n/player_locale.py`): минимальный SELECT по `users.locale_override` через `SqlAlchemyUnitOfWork.session`. Не открывает UoW транзакционно ради одного scalar-чтения — для read-only middleware-резолва это явный compromise (читать через полноценный UoW.commit избыточно). Если override `NULL` или unsupported (защитный фильтр на случай рассинхронизации БД и SUPPORTED_LOCALES) — возвращает `None`.
- **`LocaleMiddleware` priority chain** (`src/pipirik_wars/bot/middlewares/locale.py`): получает опциональный `player_locale_resolver: IPlayerLocaleResolver | None`. Цепочка резолва: `users.locale_override` (если резолвер есть и `tg_user_id` известен) → `LocaleResolver(tg.language_code)` → `LocaleResolver.default = DEFAULT_LOCALE`. Без резолвера middleware ведёт себя как раньше (1.5.A совместимость).
- **Bot-команда `/lang ru|en|RU|EN`** (`src/pipirik_wars/bot/handlers/lang.py`): handler работает только в ЛС (`chat_kind == "private"`), парсит `command.args.strip().lower()`, фильтрует пустой / неподдерживаемый input. Конкретные сценарии: `lang-group` (группа/супергруппа), `lang-other` (channel или нет identity), `lang-usage` (нет аргументов), `lang-unsupported` с параметром `code` (любая строка не `ru`/`en`), `lang-not-registered` (`PlayerNotFoundError`), `lang-set-{ru,en}` (успех — подтверждение **в новой выбранной локали**, чтобы игрок сразу увидел «как теперь будет»).
- **`LangPresenter`** (`src/pipirik_wars/bot/presenters/lang.py`): тонкий wrapper над `IMessageBundle` (паттерн 1.5.B-E). Каждый метод: `(*, locale: Locale, ...) -> str`.
- **Локали `lang-*`** (`locales/{ru,en}.ftl`): полный набор ключей (`lang-group/lang-other/lang-not-registered/lang-usage/lang-unsupported/lang-set-{ru,en}`). EN-версия покрывает все ключи (RU→EN fallback в 1.5.A работает, но EN-первичный путь даёт лучшую UX для англоязычных игроков).
- **`TelegramForestFinishNotifier` per-player локаль** (`src/pipirik_wars/bot/notifications/forest.py`): принимает опциональный `locale_resolver: IPlayerLocaleResolver | None`. В `notify(...)` перед рендером дёргает `_resolve_locale(tg_id)`: если резолвер есть и нашёл override — рендерим в локали игрока, иначе фолбэк на `default_locale`. Любые ошибки резолвера поглощаются (`logger.exception` + фолбэк) — фоновые сообщения должны быть best-effort и не падать из-за БД-проблем.
- **Composition root** (`src/pipirik_wars/bot/main.py`): `Container` теперь хранит `player_locale_resolver: IPlayerLocaleResolver` и `set_player_locale: SetPlayerLocale`. `build_container(...)` инстанциирует `PlayerLocaleResolverDB(uow=uow)` и пробрасывает его в (1) `register_middlewares(..., player_locale_resolver=...)` (для `LocaleMiddleware`), (2) `TelegramForestFinishNotifier(..., locale_resolver=...)`. Dispatcher DI: `dispatcher["set_player_locale"] = container.set_player_locale`. Router-регистрация `dispatcher.include_router(lang_router)` после `profile_router`.
- **Тесты:**
    - **Unit `SetPlayerLocale`** (`tests/unit/application/player/test_set_locale.py`, 6 кейсов): set-from-NULL, switch ru→en, reset через `None`, идемпотентность (entity не меняется при no-op), `PlayerNotFoundError` + rollback, unsupported-locale защита.
    - **Unit `LocaleMiddleware` × resolver** (`tests/unit/bot/middlewares/test_locale.py`, +4 кейса к 7 существующим): override приоритетнее `tg.language_code`, фолбэк на `tg.language_code` если override-а нет, резолвер не вызывается без `TgIdentity`, фолбэк на DEFAULT когда нет ни override-а, ни валидного `tg.language_code`.
    - **Unit `LangPresenter`** (`tests/unit/bot/presenters/test_lang.py`, 7 кейсов): по одному кейсу на каждый ключ.
    - **Unit `/lang` handler** (`tests/unit/bot/handlers/test_lang.py`, 11 кейсов): успех ru/en, normalize regex (RU/EN → ru/en), нет аргументов / blank / fr → правильные ключи, `PlayerNotFoundError` через side_effect → `lang-not-registered`, group/supergroup/channel ветки, fallback на DEFAULT при `locale=None`.
    - **Integration `PlayerLocaleResolverDB`** (`tests/integration/i18n/test_player_locale_resolver.py`, 7 кейсов): возвращает `None` для unknown / NULL override, `Locale("ru")` / `Locale("en")` для соответствующих значений, CHECK-constraint в БД отвергает мусор. Roundtrip через `SqlAlchemyPlayerRepository` для `with_locale_override` + `save` (set + clear).
    - **Unit notifier × resolver** (`tests/unit/bot/notifications/test_forest.py`, +4 кейса к 11 существующим): override RU при default EN → шлёт RU, override EN при default RU → шлёт EN, нет override → фолбэк на default, ошибки резолвера поглощаются.
    - **Migration test** (`tests/integration/db/test_migrations.py`): добавлен `test_0006_descends_from_0005`, расширены проверки `versions/*.py` на наличие нового файла, регистрации `0006_users_locale_override` в Alembic-цепочке.
    - **Composition root test** (`tests/unit/bot/test_composition_root.py`): добавлен `FakePlayerLocaleResolver` в `tests/fakes/player_locale_resolver.py` + проброс в `Container`.

Результат / артефакты:
- Новые файлы: `src/pipirik_wars/application/player/set_locale.py`, `src/pipirik_wars/application/i18n/player_locale.py`, `src/pipirik_wars/infrastructure/i18n/player_locale.py`, `src/pipirik_wars/infrastructure/db/migrations/versions/20260505_0006_users_locale_override.py`, `src/pipirik_wars/bot/handlers/lang.py`, `src/pipirik_wars/bot/presenters/lang.py`, `tests/fakes/player_locale_resolver.py`, `tests/unit/application/player/test_set_locale.py`, `tests/unit/bot/handlers/test_lang.py`, `tests/unit/bot/presenters/test_lang.py`, `tests/integration/i18n/test_player_locale_resolver.py`, `tests/integration/i18n/conftest.py`.
- Модифицированы: `src/pipirik_wars/domain/player/entities.py`, `src/pipirik_wars/domain/shared/ports/audit.py`, `src/pipirik_wars/infrastructure/db/models/player.py`, `src/pipirik_wars/infrastructure/db/repositories/player.py`, `src/pipirik_wars/application/player/__init__.py`, `src/pipirik_wars/application/i18n/__init__.py`, `src/pipirik_wars/infrastructure/i18n/__init__.py`, `src/pipirik_wars/bot/middlewares/locale.py`, `src/pipirik_wars/bot/middlewares/__init__.py`, `src/pipirik_wars/bot/handlers/__init__.py`, `src/pipirik_wars/bot/notifications/forest.py`, `src/pipirik_wars/bot/main.py`, `locales/ru.ftl`, `locales/en.ftl`. Тесты: `tests/unit/bot/middlewares/test_locale.py`, `tests/unit/bot/notifications/test_forest.py`, `tests/integration/db/test_migrations.py`, `tests/unit/bot/test_composition_root.py`, `tests/fakes/__init__.py`.
- Локально `make ci`: ruff lint ✅, mypy --strict ✅ (364 файла), import-linter ✅ (3 контракта KEPT), pytest 1060 passed + 1 skipped (`thickness=1` граничный случай), coverage 96.98% (требование ≥80%).

Заметки / решения:
- **Почему `IPlayerLocaleResolver`, а не прямое чтение `IPlayerRepository.get_by_tg_id` в middleware?** Middleware дёргается на КАЖДОМ апдейте бота (включая колбэки/inline-режим). `get_by_tg_id` тянет всю Player-агрегат + UoW.commit — это лишний оверхед на каждый чих. `IPlayerLocaleResolver` — узкий read-only порт для одной колонки, реализация делает один SELECT и не открывает транзакцию для commit. ISP в чистом виде.
- **Почему confirm в новой локали?** Игрок переключился с EN на RU через `/lang ru` — он ожидает увидеть «🌐 Язык переключён на русский», а не «Language switched to Russian». Это маленький, но важный UX-сигнал «смена применилась немедленно».
- **Почему `0006` назван `users_locale_override`, а не `players_locale_override`?** Таблица в БД называется `users` (не `players`) — name-mismatch с domain-агрегатом `Player` остался ещё со Спринта 1.1, и переименование БД-таблицы — отдельная задача за пределами 1.5. Имя миграции следует ИМЕНИ ТАБЛИЦЫ, а не доменной сущности.
- **Почему фолбэк на `default_locale` в notifier-е, а не на язык игрока из `tg.language_code`?** Notifier работает в фоне (APScheduler) — у него нет `update.from_user`, и доступ к `tg.language_code` пришлось бы тащить из БД (ещё одна колонка `users.tg_language_code` со снапшотом). Мы сознательно НЕ делаем этого: игрок, который не выбрал `/lang`, видит фоновые сообщения в EN. Это ОК для MVP — explicit override закрывает 90% юзкейсов.
- **Почему migration через `op.batch_alter_table`?** SQLite (наш dev/тестовый бэкенд) не умеет `ALTER TABLE ADD CONSTRAINT` напрямую — Alembic использует copy-and-move через batch_alter_table. Для Postgres в проде это no-op (генерируется обычный `ALTER TABLE`). Без батчинга `make ci` падал на интеграционных тестах миграций.

---

## 2026-05-05 — Спринт 1.5.E: `/forest` через `IMessageBundle` (handler + презентер + нотификатор)

**Автор:** Devin (по запросу sufficientdorette)
**Тип:** feature (i18n-прогон последнего handler-а + nitidication-презентера + удаление legacy `render_full_nick(...)`)
**Связано:** Текущий PR (Спринт 1.5.E), [development_plan.md §3 / Спринт 1.5, задача 1.5.1](development_plan.md), [current_tasks.md Спринт 1.5 → 1.5.E](current_tasks.md). Продолжение Спринта 1.5 после смерженного 1.5.D (PR #28).

Что сделано:
- **Локали (`locales/{ru,en}.ftl`):** добавлена секция `## /forest` с полным набором ключей: `forest-group/-other/-not-registered/-already-in/-started/-started-fallback/-finished-header/-finished-length/-finished-title-granted/-finished-item-found/-finished-name-granted/-finished-name-found/-rarity-{common,rare,epic}/-button-{equip,drop-item,replace-name,drop-name}/-toast-*` (9 toast-ов). Числовые параметры (`$cooldown_minutes`, `$length_delta_cm`, `$length_before_cm`, `$length_after_cm`) обёрнуты в `NUMBER($x, useGrouping: 0)` — без этого Fluent для RU вставляет `\xa0` (NBSP) между разрядами, и проверки точного совпадения текста ломаются (тот же фикс, что в 1.5.C/D).
- **`ForestPresenter` (`bot/presenters/forest.py`):** `__init__(*, bundle: IMessageBundle)`, методы по группам:
    - **chat-ветки:** `group/other/not_registered/already_in(*, locale)`;
    - **started-сообщение:** `started(*, player, display_name, cooldown_minutes, locale)` (рендерит `[Локализованный титул] [Название] [Имя]` через приватный `_render_full_nick(...)`, потом передаёт собранный ник как `$nick` в `forest-started`) + `started_fallback(*, cooldown_minutes, locale)` (короткий безниковый вариант для случая, когда `GetProfile` после `StartForestRun` отдал `None`);
    - **finished-сообщение:** `finished(*, result, display_name_after, locale)` собирает строки `header / length / title_granted? / item_found? / name_granted_or_found?` и склеивает через `\n`. Локализованная редкость подставляется как готовая строка в параметр `$rarity` ключа `forest-finished-item-found`;
    - **finish-клавиатура:** `finish_keyboard(result, *, locale)` возвращает `InlineKeyboardMarkup | None` для `ItemDrop` и `NameDrop` (кроме случая, когда имя авто-применилось — `granted_name=True`). Подписи локализованы (`forest-button-{equip,drop-item,replace-name,drop-name}`); `callback_data` — invariant-формат `forest:<action>:<run_id>` через pure-функцию `forest_callback_data(action, run_id)` (не зависит от локали);
    - **toast-ы для коллбэков:** 9 методов `toast_*(*, locale)` (`name_applied/name_already_applied/name_dropped/item_dropped/item_equipped_placeholder/foreign_button/run_not_found/drop_mismatch/player_not_found`);
    - **`localized_rarity(rarity, *, locale)`:** маппинг `Rarity → forest-rarity-{common,rare,epic}` с резолвом через `IMessageBundle`.
  Pure-функции `forest_callback_data(...)`, `parse_forest_callback_data(...)`, `has_finish_keyboard(...)` оставлены вне класса — они не локализованы (это сериализация / business-логика), и тесты к ним не требуют bundle-а.
- **`bot/handlers/forest.py`:** handler `handle_forest` теперь принимает `bundle: IMessageBundle` и `locale: Locale | None = None` через DI middleware-а; `effective_locale = locale or DEFAULT_LOCALE`. Все ответы (`group/other/not_registered/already_in/started/started_fallback`) идут через `ForestPresenter.<...>(locale=effective_locale)`. Callback-handler `handle_forest_callback` (на `F.data.startswith("forest:")`) тоже принимает `bundle` + `locale`, парсит `callback_data` через `parse_forest_callback_data(...)`, и для каждого `action` (`apply_name/drop_name/equip_item/drop_item`) шлёт локализованный toast и (где надо) снимает клавиатуру через `_strip_keyboard(...)` (idempotent, поглощает любые `edit_reply_markup`-ошибки). Логика `apply_name` вынесена в приватный `_handle_apply_name(...)` для читаемости.
- **`bot/notifications/forest.py`:** `TelegramForestFinishNotifier` получил `bundle: IMessageBundle` и `default_locale: Locale = DEFAULT_LOCALE` через DI. Локаль игрока в фоновом APScheduler-job-е недоступна (нет `update.from_user`), поэтому notifier рендерит **всё** в `default_locale`. Это компромисс: per-player-локаль в нотификаторе требует `players.locale_override` (миграция) и `IPlayerLocaleResolver`-порт — это вынесено в **1.5.F** как явный pending-item. До 1.5.F finished-сообщение приходит игроку в `DEFAULT_LOCALE = "en"`, что уже корректно для большинства новых игроков (язык Telegram-клиента у них чаще всего English).
- **`bot/main.py`:** `TelegramForestFinishNotifier(...)` в композиционном корне теперь получает `bundle=bundle` (тот же `FluentMessageBundle`, что у handler-ов). Это единственная пересборка root-а: notifier явно зависит от bundle-а, других путей пройти инициализацию нет.
- **Удалён legacy `render_full_nick(...)` из `bot/presenters/profile.py`:** функция оставалась как RU-only pure-функция в 1.5.C → 1.5.D ради forest-презентера. Теперь forest-презентер сам собирает ник через приватный `_render_full_nick(...)` с локализованным титулом, поэтому `render_full_nick` и сопутствующий dict `_TITLE_RU` удалены. Тесты `TestRenderFullNick` тоже удалены (4 теста).
- **`bot/presenters/__init__.py`:** добавлены экспорты `ForestPresenter`, `ForestCallbackAction`, `ForestCallbackData`, `forest_callback_data`, `parse_forest_callback_data`. Удалён экспорт `render_full_nick`. Все презентеры теперь идут через `IMessageBundle`.

Тесты:
- **`tests/unit/bot/presenters/test_forest.py`** (полностью переписан под новый паттерн, **62 теста**):
  - `TestCallbackData` — 11 тестов pure-функций (round-trip, формат, ≤ 64 байт, отказ на zero/negative run_id, отказ на bad format, отказ на unknown action);
  - `TestHasFinishKeyboard` — 4 теста на `has_finish_keyboard(...)` для `NoDrop/ItemDrop/NameDrop(auto)/NameDrop(replace)`;
  - `TestForestPresenterFakeBundle` — 21 тест через `FakeMessageBundle` (маркер `<locale>:<key>[k=v,...]`): покрывает все методы (`group/other/not_registered/already_in/started/started_fallback/finished/finish_keyboard/toast_*/localized_rarity`), включая отдельный тест **«callback_data invariant между локалями»** (подписи кнопок RU vs EN различаются, `callback_data` — нет);
  - `TestForestPresenterFluent` — 11 тестов через `FluentMessageBundle` (RU + EN), интеграционная проверка реальных переводов: `started`-сообщение в обеих локалях, `finished`-сообщение для `NoDrop/ItemDrop/NameDrop(replace)`, локализованные подписи кнопок, `localized_rarity` для всех `Rarity` × `Locale`. Отдельный safety-test: **в EN-выводе нет ни одного кириллического символа** (`U+0400-U+04FF`) — защита от случайной утечки RU-строк.
- **`tests/unit/bot/handlers/test_forest.py`** (полностью переписан, **22 теста**):
  - `TestHandleForest` — 9 тестов: success-ветка с `started`-сообщением, `not_registered/already_in` через ключи, `group/supergroup/channel`-чаты через `group/other`, отсутствие `tg_identity`, fallback `DEFAULT_LOCALE = "en"` при `locale=None`, fallback на `started_fallback` если `GetProfile` отдал `None`;
  - `TestForestCallback` — 13 тестов: успех `apply_name`, повторное применение, ownership mismatch, drop mismatch, run not found, player not found, `drop_name/equip_item/drop_item`-actions, malformed `callback_data` (toast `drop_mismatch` + клавиатура снята), отсутствие `tg_identity`/`data` (silent return), `_strip_keyboard(...)` поглощает `edit_reply_markup`-ошибки, fallback на `DEFAULT_LOCALE` при `locale=None`.
- **`tests/unit/bot/notifications/test_forest.py`** (обновлены сигнатуры и assertions, **+2 новых теста**):
  - `_make_notifier(...)` теперь принимает опциональный `bundle` (по умолчанию реальный `FluentMessageBundle`) и `default_locale`;
  - старые ассерты текста (`"вернулся из леса" / "Шлём Берсерка" / "Нашёл имя: Новое"`) переведены в RU-режим через `default_locale=Locale("ru")`;
  - **новый `test_sends_message_default_locale_en`**: убеждается, что без override `default_locale = DEFAULT_LOCALE = "en"`, и в выводе нет кириллицы;
  - **новый `test_uses_fake_bundle_marker_for_finished_header`**: проверяет, что нотификатор берёт ключи `forest-finished-header` и `forest-finished-length` (страховка от регресса при будущих рефакторингах);
  - тест проверки локализованных подписей кнопок в keyboard.
- **`tests/unit/bot/presenters/test_profile.py`:** удалён `TestRenderFullNick` (4 теста), импорт `render_full_nick` из публичного модуля убран. `TestTitleMessageKey` оставлен.

Локально:
- `pre-commit run --all-files` — все хуки зелёные.
- `make ci` — `ruff` + `mypy` + `lint-imports` + `pytest`: **1020 passed, 1 skipped, 96.95%** покрытие. Контракты `import-linter` (3) — kept. Никаких новых `# type: ignore`/`noqa` не добавлено.

Результат / артефакты:
- `locales/{ru,en}.ftl` (+ ~60 строк в каждом — секция `## /forest`).
- `src/pipirik_wars/bot/presenters/forest.py` (полностью переписан под `ForestPresenter`).
- `src/pipirik_wars/bot/handlers/forest.py` (handler + callback-handler с `bundle`/`locale` DI).
- `src/pipirik_wars/bot/notifications/forest.py` (`bundle` + `default_locale` через DI).
- `src/pipirik_wars/bot/main.py` (notifier теперь получает `bundle`).
- `src/pipirik_wars/bot/presenters/profile.py` (удалён `render_full_nick` + `_TITLE_RU`).
- `src/pipirik_wars/bot/presenters/__init__.py` (новые экспорты `ForestPresenter` и др., удалён `render_full_nick`).
- `tests/unit/bot/presenters/test_forest.py` (полностью переписан, 62 теста).
- `tests/unit/bot/handlers/test_forest.py` (полностью переписан, 22 теста).
- `tests/unit/bot/notifications/test_forest.py` (обновлены сигнатуры + 2 новых теста).
- `tests/unit/bot/presenters/test_profile.py` (удалён `TestRenderFullNick`).

Заметки / решения:
- **Почему `ForestPresenter` — класс, а pure-функции остались отдельно.** Тот же паттерн, что в 1.5.B-D: класс с `__slots__ = ("_bundle",)` и DI-параметром `bundle: IMessageBundle` нужен для **локализованного UI**. Pure-функции `forest_callback_data(...)`/`parse_forest_callback_data(...)` — это сериализация, не UI; они **не должны** зависеть от локали — `callback_data` инвариантно между перерегистрацией хэндлеров, перезагрузкой шаблонов, переключением локали игрока (`/lang ru` не должен «протухать» уже отправленные кнопки), и deep-link-ами. Тест `test_finish_keyboard_item_callback_data_invariant_across_locales` явно фиксирует этот контракт: подписи кнопок RU и EN различаются, `callback_data` — нет.
- **Почему notifier рендерит в `DEFAULT_LOCALE`, а не в `player.locale`.** В 1.5.B мы добавили запись `Locale` в `RegisterPlayerInput.locale` (хранение per-player языка), но в `Player`-aggregate этого поля **ещё нет** — это будет миграция `players.locale_override TEXT NULL` в 1.5.F. До этого notifier не имеет источника, откуда взять язык игрока: `update.from_user` отсутствует (это фоновый APScheduler-job, а не chat-event), `tg.language_code` — тоже нет. Hardcode в `DEFAULT_LOCALE = "en"` корректнее, чем угадывать. В 1.5.F notifier получит `IPlayerLocaleResolver`-порт и сможет резолвить `player.locale_override → tg.language_code → DEFAULT_LOCALE` (тот же приоритет, что в `LocaleMiddleware`).
- **Почему 1.5.E не включает `/lang` и 300+ JSON-логов.** Изначально 1.5.E был задуман как «всё про forest-локализацию + audit + 300+ шаблонов + `/lang` + `players.locale_override`». Но это четыре независимых задачи, и каждая несёт свою миграцию / порт / use-case. Чтобы PR оставался обозримым (≤500 строк дифа на «эталон»), 1.5.E ограничен **только** прогоном forest через `IMessageBundle`. `/lang ru|en` + миграция вынесены в 1.5.F (это связано: `IPlayerLocaleResolver` нужен и `/lang`-handler-у, и notifier-у). 300+ JSON-шаблонов забавных логов + ревизия audit-логов вынесены в 1.5.G (это про content и про audit_log, а не про i18n как таковую). README/CONTRIBUTING + docker-compose + деплой — в 1.5.H.
- **Почему `_render_full_nick(...)` приватный.** В 1.5.C функция `render_full_nick(...)` была публичной pure-функцией (RU-only), потому что forest-презентер ещё не был прогон через `IMessageBundle`. Теперь forest-презентер использует `bundle.format(title_message_key(title), locale=locale)` для титула и собирает ник внутри собственного метода `_render_full_nick`. Это deliberate encapsulation: сигнатура внутреннего метода (`title/display_name/name/locale`) — деталь имплементации, а не публичный контракт. Если в Фазе 2+ появится отдельный `NickPresenter` или ник-формат изменится, мы перекроим внутри `ForestPresenter` без затрагивания тестов на handler.
- **Почему `useGrouping: 0` сохраняется и для forest-сообщений.** Тот же фикс, что в 1.5.C/D: Fluent для RU в `NUMBER($x)` без `useGrouping: 0` вставляет `\xa0` (non-breaking space) между разрядами, и тесты, которые ассертят точный вывод (`"+5 см (было 2, стало 7)"`), ломаются. Параметр `useGrouping: 0` отключает разделение разрядов на уровне CLDR-формата.

---

## 2026-05-05 — Спринт 1.5.D: `/oracle` и `/upgrade` через `IMessageBundle`

**Автор:** Devin (по запросу sufficientdorette)
**Тип:** feature (i18n-прогон ещё двух handler-ов + презентеров)
**Связано:** Текущий PR (Спринт 1.5.D), [development_plan.md §3 / Спринт 1.5, задача 1.5.1](development_plan.md), [current_tasks.md Спринт 1.5 → 1.5.D](current_tasks.md). Продолжение Спринта 1.5 после смерженного 1.5.C (PR #27).

Что сделано:
- **Локали (`locales/{ru,en}.ftl`):** добавлены секции `## /oracle` и `## /upgrade` с полным набором ключей: `oracle-group/-other/-not-registered/-success/-already-used`, `upgrade-group/-other/-not-registered/-proposal/-success/-insufficient/-insufficient-short/-cancelled/-race/-toast-*/-button-*`. Все числовые параметры (`$cost_cm`, `$current_length_cm`, `$bonus_cm`, `$hours`, …) обёрнуты в `NUMBER($x, useGrouping: 0)` — иначе Fluent для RU вставляет `\xa0` (non-breaking space) между разрядами и текст ответов отличается от исторического (`4000 см` → `4\xa0000 см`).
- **`OraclePresenter` (`bot/presenters/oracle.py`):** `__init__(*, bundle: IMessageBundle)`, методы `group(*, locale)`, `other(*, locale)`, `not_registered(*, locale)`, `success(template_text, bonus_cm, new_length_cm, user_display, locale)` (подставляет `{user}` в шаблон предсказания через старый `_SafeDict`, потом передаёт получившуюся строку в Fluent как `$prediction`), `already_used(moscow_date, now, locale)` (помощник `_hours_minutes_until_next_reset` остался неизменным). Удалены старые pure-функции `render_oracle_*` и константы `REPLY_*_RU`.
- **`UpgradePresenter` (`bot/presenters/upgrade.py`):** `__init__(*, bundle: IMessageBundle)`, методы по группам: chat-ветки (`group/other/not_registered`), карточки (`proposal/success/insufficient/insufficient_short/cancelled/race`), toast-ы (`toast_upgraded/cancelled/player_not_found/insufficient/race`), и **`proposal_keyboard(expected_cost_cm, locale)`** — возвращает `InlineKeyboardMarkup` с локализованными подписями кнопок (`upgrade-button-confirm`/`upgrade-button-cancel`). Pure-функции `upgrade_callback_data()` / `parse_upgrade_callback_data()` / dataclass `UpgradeCallbackData` оставлены без изменений: `callback_data` — invariant-формат и не зависит от локали (см. ниже).
- **`bot/handlers/oracle.py`:** новые DI-параметры `bundle: IMessageBundle, locale: Locale | None = None`. `effective_locale = locale or DEFAULT_LOCALE` пробрасывается во все ответы через `OraclePresenter`. `InvokeOracleInput.locale` теперь равен `effective_locale.code` (раньше hardcoded `"ru"` — теперь use-case умеет выбирать каталог предсказаний по локали игрока). Helper `_user_display(user)` оставлен с RU-fallback `"друг"` — это safety net для случаев, когда у Telegram-юзера нет ни `first_name`, ни `username`; локализация этого fallback-а — задача 1.5.E.
- **`bot/handlers/upgrade.py`:** обновлены DI оба handler-а — и `handle_upgrade` (команда), и `handle_upgrade_callback` (инлайн-кнопки). Все ответы (`message.answer`, `callback.answer`, `message.edit_text`) идут через `UpgradePresenter` с `effective_locale`. Toast-ы для `callback.answer` тоже локализованы (`presenter.toast_*(locale=effective_locale)`). Helper-ы `_strip_keyboard` / `_set_message_text` оставлены без изменений (это чисто инфраструктурные обёртки над aiogram).
- **`bot/presenters/__init__.py`:** добавлены экспорты `OraclePresenter`, `UpgradePresenter` (имя класса вместо старых pure-функций). `forest`-презентер пока остался pure-функциональным — его миграция назначена на 1.5.E.
- **Тесты:** `test_oracle.py`/`test_upgrade.py` (presenter) и `test_oracle.py`/`test_upgrade.py` (handler) переведены на `FakeMessageBundle`. Маркерный формат `<locale>:<key>[k=v,...]` позволяет проверить и сам ключ, и переданные параметры (`prediction=…`, `cost_cm=4000`, `next_thickness=2`, …) без привязки к настоящему переводу. Параллельно — интеграционные `Test*PresenterFluent` гоняют тот же сценарий через настоящий `FluentMessageBundle` для RU и EN, чтобы не пропустить регрессии в самих `.ftl`-файлах. **Итого:** 999 passed, 1 skipped, **96.91%** покрытие.
- **План спринта 1.5 актуализирован.** В `docs/current_tasks.md` Спринт 1.5 теперь явно режется на **6 PR-ов** (1.5.A–F): 1.5.D — `/oracle`+`/upgrade` (текущий), 1.5.E — `/forest` + `/lang command` + 300+ JSON-логов + audit_log ±см, 1.5.F — docker-compose + README/CONTRIBUTING + деплой. `/forest` отделён от 1.5.D в самостоятельный PR, потому что у него больше движущихся частей: notifier (`ForestNotifier`), три типа Drop, локализация Rarity-меток и run-лога — всё это требует отдельного review и не вмещается комфортно в один PR с `/oracle`+`/upgrade`.

Результат / артефакты:
- `locales/ru.ftl` + `locales/en.ftl` — добавлены секции `## /oracle` и `## /upgrade`.
- `src/pipirik_wars/bot/presenters/oracle.py` — `OraclePresenter` поверх `IMessageBundle`; pure-функции `render_oracle_*` удалены.
- `src/pipirik_wars/bot/presenters/upgrade.py` — `UpgradePresenter` (включая `proposal_keyboard(...)`); pure-функция `build_upgrade_proposal_keyboard()` удалена; `upgrade_callback_data()` / `parse_upgrade_callback_data()` / `UpgradeCallbackData` оставлены без изменений.
- `src/pipirik_wars/bot/handlers/oracle.py` — DI `bundle` + `locale`, ответы через `OraclePresenter`, `InvokeOracleInput.locale = effective_locale.code`.
- `src/pipirik_wars/bot/handlers/upgrade.py` — DI `bundle` + `locale` в `handle_upgrade` И `handle_upgrade_callback`, ответы и toast-ы через `UpgradePresenter`.
- `src/pipirik_wars/bot/presenters/__init__.py` — добавлены экспорты `OraclePresenter`, `UpgradePresenter`.
- `tests/unit/bot/presenters/test_oracle.py`, `tests/unit/bot/presenters/test_upgrade.py` — переписаны под класс-презентеры, `FakeMessageBundle` + `FluentMessageBundle` интеграция.
- `tests/unit/bot/handlers/test_oracle.py`, `tests/unit/bot/handlers/test_upgrade.py` — переписаны под новый DI (`bundle`, `locale`), маркерные ключи + проверка локали-fallback (`None` → `DEFAULT_LOCALE = Locale("en")`).
- `docs/current_tasks.md` — обновлён план Спринта 1.5: 6 PR-ов вместо 5; 1.5.D — `/oracle` + `/upgrade`; 1.5.E — `/forest` + `/lang command` + audit_log ±см.

Заметки / решения:
- **Почему `NUMBER($x, useGrouping: 0)` для всех числовых параметров.** Fluent по умолчанию форматирует числа с локалью — для RU это `\xa0` (non-breaking space) между тысячами (`4 000`), для EN — запятая (`4,000`). Старые ответы в коде писались как f-строки без grouping-а: `f"{cost_cm} см"` → `4000 см`. Чтобы не ломать UX («внезапно появились пробелы между разрядами»), в `.ftl` явно гасим grouping через `useGrouping: 0`. Альтернатива — передавать в bundle уже готовые строки (`bundle.format(..., cost_cm=str(cost_cm))`), но это уносит часть форматирования в Python и плохо ложится на будущие RTL-локали или языки с нестандартными числовыми системами. Прятать это в Fluent-шаблонах удобнее: переводчик может включить grouping локально для своей локали, не трогая Python-код.
- **Почему `OraclePresenter.success` принимает `template_text` извне, а не сам формирует предсказание.** Текст предсказания — это **доменные данные** (`OracleTemplate.text` хранится в БД / каталоге шаблонов), их нельзя класть в `.ftl`. В `.ftl` лежит **обёртка** ответа — заголовок «Предсказание дня», бонус и итоговая длина. Презентер сначала подставляет `{user}` в `template_text` через старый `_SafeDict` (не падает на неизвестных плейсхолдерах), а потом передаёт получившуюся строку в Fluent как `$prediction`. Это даёт чёткое разделение: каталог предсказаний — domain-уровень (можно хранить шаблоны на любых языках), а обёртка — i18n-слой.
- **Почему `callback_data` `/upgrade`-кнопок остаётся invariant-форматом.** Telegram-`callback_data` не должен зависеть от локали юзера, иначе пользователь, который перешёл с RU на EN между сообщением и кликом, получил бы parse error в handler-е. `presenter.proposal_keyboard()` локализует только `text` кнопок, а `callback_data` строится через ту же pure-функцию `upgrade_callback_data()` (`"upgrade:confirm:4000"` / `"upgrade:cancel:0"`). Тесты явно проверяют этот invariant и в FakeBundle, и в Fluent-варианте.
- **Почему `/forest` отделили от `/oracle`+`/upgrade` в самостоятельный PR.** В `bot/handlers/forest.py` есть три ветки рендеринга (start / finish / drop), каждая со своим набором локализуемых строк, плюс отдельный `ForestNotifier` (он сам отправляет сообщения в чат). `bot/presenters/forest.py` сейчас выдаёт длинный run-лог с разными по типу строками (Rarity-уровни, Drop-варианты, finish-сводка), и весь этот вывод нужно тоже разнести по `.ftl`-ключам с per-locale форматированием. Аккуратно делать это в одном PR-е с `/oracle`+`/upgrade` — значит получить +500 LoC и ревью на 30+ комментариев. Деление на 1.5.D + 1.5.E делает каждый PR обозримым и снижает риск раннего merge-conflict-а с другими ветками.
- **Почему `_user_display` в `oracle.py` всё ещё возвращает RU-`"друг"`.** Это safety net для редкого случая, когда у Telegram-юзера нет ни `first_name`, ни `username`. Локализация этого fallback-а тривиальна (новый ключ `oracle-user-fallback` или общий `user-anonymous`), но требует решения: какой fallback использовать на самой ранней стадии handler-а (до того, как мы понимаем, в каком чате юзер пишет)? В 1.5.D мы предпочли оставить это RU-фолбэком и решить вопрос в 1.5.E одновременно с прогоном `/forest` и подключением `/lang`-команды.

---

## 2026-05-05 — Спринт 1.5.C: `/profile` и `/top` через `IMessageBundle`

**Автор:** Devin (по запросу sufficientdorette)
**Тип:** feature (i18n-прогон ещё двух handler-ов + презентеров)
**Связано:** Текущий PR (Спринт 1.5.C), [development_plan.md §3 / Спринт 1.5, задача 1.5.1](development_plan.md), [current_tasks.md Спринт 1.5 → 1.5.C](current_tasks.md). Продолжение Спринта 1.5 после смерженного 1.5.B (PR #26).

Что сделано:
- **`bot/presenters/profile.py`** — переписан под `ProfilePresenter` (DI `bundle: IMessageBundle`):
  - `group()` / `other()` / `not_registered()` / `card()` — методы рендера, все ходят в `IMessageBundle.format(...)` по ключам `profile-group`/`profile-other`/`profile-not-registered`/`profile-card`.
  - `card()` собирает «полный ник» («Титул Название Имя») с локализованным титулом через `profile-title-<value>` (для `Title.NEWBIE` → `profile-title-newbie`); потом передаёт `nick` + `length_cm` + `thickness_level` в шаблон `profile-card`.
  - Public функция `title_message_key(title)` — единый «контракт» между Python-кодом и `.ftl` (тест проверяет, что для каждого члена `Title` ключ существует и в RU, и в EN — иначе bundle бросит `MessageKeyError`).
  - Legacy pure-функция `render_full_nick(...)` оставлена временно — её ещё зовут `bot/presenters/forest.py`. Удаление — в 1.5.D, после миграции forest-презентера.
- **`bot/presenters/top.py`** — заменён на `TopPresenter`:
  - `render(entries, *, locale)` — пустой топ → ключ `top-empty`, иначе шапка + `top-entry`-ряды (`{ $rank }. { $nick } — { $length_cm } см`).
  - Локализация титулов делается через тот же `profile-title-<value>` (общий пул с /profile) — переводчику не нужно дублировать «Новичок/Newbie».
- **`bot/handlers/profile.py`** и **`bot/handlers/top.py`** — handler-ы получают `bundle: IMessageBundle` + `locale: Locale | None = None` (тот же fallback на `DEFAULT_LOCALE`, что и в `/start`). Удалены `REPLY_GROUP_RU`/`REPLY_OTHER_RU`/`REPLY_NOT_REGISTERED_RU` (`/profile`) и `REPLY_TOP_HEADER_RU`/`REPLY_TOP_EMPTY_RU` (`/top`).
- **`infrastructure/i18n/fluent_bundle.py`** — `FluentBundle` теперь создаётся с `use_isolating=False`. По умолчанию `fluent.runtime` оборачивает значения `{ $vars }` в Unicode bidi-isolation marks U+2068/U+2069 — это корректно для RTL-языков, но в чисто-LTR-наборе (RU/EN) ломает `in`-проверки в тестах и засоряет копипасту в чате.
- **`locales/ru.ftl` + `locales/en.ftl`** — добавлены ключи `profile-group`/`profile-other`/`profile-not-registered`/`profile-card`/`profile-title-newbie` и `top-header`/`top-empty`/`top-entry`. RU/EN-варианты карточки `/profile` — структурно идентичные (одинаковые эмодзи, разный текст).
- **`bot/presenters/__init__.py`** — экспорт `ProfilePresenter` + `TopPresenter`, удалены устаревшие `render_profile_card`/`render_top`/`render_top_entry`/`REPLY_TOP_*_RU`. Pure `render_full_nick` оставлена в публичном API на время 1.5.D.
- **Тесты:**
  - `tests/unit/bot/presenters/test_profile.py` — 12 тестов: `render_full_nick` (legacy, 4 кейса), `title_message_key` (mapping + integrity-проверка через `FluentMessageBundle`, RU + EN), `ProfilePresenter` (chat-ветки через `FakeMessageBundle` + интеграция `card()` через `FluentMessageBundle`, RU + EN, проверка отсутствия русских букв в EN-выводе).
  - `tests/unit/bot/presenters/test_top.py` — 12 тестов: `FakeMessageBundle` (правильные ключи + параметры в `top-entry`) + `FluentMessageBundle` (4 сочетания «титул × имя», порядок entries, EN-локаль).
  - `tests/unit/bot/handlers/test_profile.py` — 8 тестов: все ветки (private+registered/unregistered, group/supergroup, channel, private без `tg_identity`) + locale-propagation (RU vs EN) + fallback на `DEFAULT_LOCALE`.
  - `tests/unit/bot/handlers/test_top.py` — 6 тестов: рендер в private/group, пустой топ, default-limit, locale-propagation, fallback.

Результат / артефакты:
- `make ci` локально: **971 passed, 1 skipped, 96.88%** покрытие (порог DoD — 80%, см. `pyproject.toml`).
- ruff (lint + format) ✅, mypy ✅, import-linter ✅, pre-commit ✅.
- Файлы: `src/pipirik_wars/bot/presenters/profile.py` (v2), `src/pipirik_wars/bot/presenters/top.py` (v2), `src/pipirik_wars/bot/handlers/profile.py` (v2), `src/pipirik_wars/bot/handlers/top.py` (v2), `src/pipirik_wars/bot/presenters/__init__.py` (обновлён), `src/pipirik_wars/infrastructure/i18n/fluent_bundle.py` (`use_isolating=False`), `locales/ru.ftl` + `locales/en.ftl` (новые ключи), 4 тест-файла (~50 unit-тестов суммарно).

Заметки / решения:
- **Почему карточка `/profile` — один ключ, а не 4–5 атомарных.** Вариант «`profile-card-length-label` + `profile-card-thickness-label` + …» (склеивает презентер) даёт переводчику набор маленьких кусочков без контекста — он не знает, как они склеятся. Многострочный `profile-card` с `{ $nick }`/`{ $length_cm }`/`{ $thickness_level }` показывает весь layout сразу, и переводчик может, например, поменять порядок строк под язык (если в EN «Equipment» традиционно идёт перед «Length»). Минус — multi-line-индентация в Fluent чувствительна к позиции эмодзи (см. ниже).
- **Почему `use_isolating=False` именно сейчас, а не в 1.5.A.** В 1.5.A bundle был занят только короткими RU-ключами (`start-*`), и плейсхолдеры были редкими (только `position` в `start-queued`). Изоляция-марки никому не мешали. В 1.5.C появилась карточка с тремя плейсхолдерами в одной строке, и тесты типа `assert "47 см" in card` стали падать — потому что текст в реальности `\u206847\u2069 см`. Чтобы не тащить везде «нормализующий» helper, проще сразу выключить изоляцию: наши локали все LTR, RTL не ожидается даже в дальних спринтах.
- **Почему `title_message_key` — public.** Я мог сделать локализацию титула приватной деталью `ProfilePresenter`, но тогда `TopPresenter` дублировал бы код. Вынес в модуль профиля как public helper — это маленький contract `Title → MessageKey`, и оба презентера используют его без копипасты. Контрактный тест `test_every_title_value_resolves_in_real_bundle` гарантирует, что любой новый член `Title` получит ключ в `.ftl` (иначе `FluentMessageBundle.format` бросит `MessageKeyError` — это и есть «безопасник»).
- **Почему legacy `render_full_nick(...)` оставлена.** `bot/presenters/forest.py` ещё пользуется старой pure-сигнатурой. Менять её сейчас означало бы тащить миграцию forest-презентера в этот PR — это +200 LoC и риск сломать flow `/forest` без отдельной проверки. Оставил `render_full_nick(...)` как RU-only-shim, помечен в docstring «1.5.D уберёт после миграции forest». Эта тактика — стандартный «strangler» подход: новый код пишется параллельно, старый удаляется отдельным PR-ом.
- **Тест-стратегия — двухслойная.** Маркерный `FakeMessageBundle` (`<locale>:<key>[k=v,...]`) проверяет, что **handler/презентер зовёт нужный ключ с нужными параметрами** — это юнит-тест. Реальный `FluentMessageBundle` поверх `locales/{ru,en}.ftl` проверяет, что **ключ действительно существует, рендерится и содержит нужные подстроки** — это интеграция с инфраструктурой. Раздел «два слоя» нужен потому, что иначе либо пришлось бы тестировать на марк-строках без проверки реального вывода, либо парсить русский/английский текст из `.ftl` в каждом тесте — оба плохие крайности.
- **Чего НЕТ в этом PR (специально оставлено для 1.5.D/E).** Миграция `/forest`, `/oracle`, `/upgrade` (отдельные handler-ы и презентеры — каждый со своим набором ключей и тестов). Команда `/lang ru|en` + миграция `players.locale_override` + use-case `SetPlayerLocale` (уехала в 1.5.E вместе с 300+ JSON-логами). Идея — держать каждый PR в районе 300–500 LoC + ≤30–40 тестов; склеивать всё в один PR — это против §0.4 ПД.

---

## 2026-05-05 — Спринт 1.5.B: DI `IMessageBundle` + `/start` через `StartPresenter`

**Автор:** Devin (по запросу sufficientdorette)
**Тип:** feature (DI-провязка + первый handler через i18n-порт)
**Связано:** Текущий PR (Спринт 1.5.B), [development_plan.md §3 / Спринт 1.5, задачи 1.5.1–1.5.2](development_plan.md), [current_tasks.md Спринт 1.5 → 1.5.B](current_tasks.md). Открытие середины Спринта 1.5 после смерженного 1.5.A (PR #25).

Второй слайс Спринта 1.5 — выводим `IMessageBundle` из «фундамента» в реальное использование на handler-е `/start`. Это в т.ч. валидирует архитектуру 1.5.A end-to-end: `LocaleResolver` → `LocaleMiddleware` → `data["locale"]` → handler → `StartPresenter` → `FluentMessageBundle` → `.ftl`.

Что сделано:
- **`src/pipirik_wars/bot/presenters/start.py`** — новый `StartPresenter`-класс. DI-параметр `bundle: IMessageBundle`; методы `registered(*, locale)`, `already(*, locale)`, `group(*, locale)`, `other(*, locale)`, `queued(*, locale, position)`. Все ключи (`start-registered`, `start-already`, `start-group`, `start-other`, `start-queued`) уже лежат в `locales/{ru,en}.ftl` со Спринта 1.5.A.
- **`src/pipirik_wars/bot/handlers/start.py`** — refactor:
  - Удалены `REPLY_REGISTERED_RU`, `REPLY_ALREADY_RU`, `REPLY_GROUP_RU`, `REPLY_OTHER_RU` и `_format_queued()`. Все ответы теперь идут через `StartPresenter` с резолвенной `Locale`.
  - Сигнатура handler-а получила два новых DI-параметра: `bundle: IMessageBundle` (workflow-data из Container-а) и `locale: Locale | None = None` (приходит из `LocaleMiddleware.data["locale"]`). `None` означает «middleware не сработал» (тест) — берём `DEFAULT_LOCALE = Locale("en")` как fallback.
  - `RegisterPlayerInput.locale` больше не hardcoded `"ru"`, а равен `effective_locale.code` — то есть язык игрока, сохранённый в БД, теперь действительно отражает резолвенную локаль (ПД 1.5.2).
- **`src/pipirik_wars/bot/main.py`** — DI-провязка:
  - `Container` получил поле `bundle: IMessageBundle`.
  - `build_container()` принимает `locales_dir: Path | None = None` (по умолчанию — `Path("locales")` в корне репо/деплоя) и собирает `FluentMessageBundle(locales_dir=...)`.
  - `build_dispatcher()` кладёт `dispatcher["bundle"] = container.bundle` — aiogram автоматически пробросит его в handler-ы по имени параметра.
- **`tests/fakes/message_bundle.py`** — `FakeMessageBundle` с маркерным `format(...)`-выводом `<locale>:<key>[k=v,...]`. Это позволяет unit-тестам однозначно проверять и сам ключ, и переданные плейсхолдеры (`position`) без зависимости от Fluent / `.ftl`-файлов.
- **`tests/unit/bot/handlers/test_start.py`** — 12 тестов переведены на `FakeMessageBundle`: каждый assert теперь сверяет точную marker-строку (например, `"ru:start-queued[position=42]"`). Добавлены два новых теста: `test_private_calls_register_player_with_resolved_locale_en` (`Locale("en") → input.locale="en"`) и `test_locale_none_falls_back_to_default_en` (middleware не сработал → fallback EN).
- **`tests/unit/bot/presenters/test_start.py`** — 6 новых юнит-тестов для `StartPresenter`: каждый ключ + проверка, что разные `Locale` дают разные строки.
- **`tests/unit/bot/test_composition_root.py`** — обновлены fake-Container и `build_container()`-тест: проверяем, что `bundle` собирается как `FluentMessageBundle` (real) / `FakeMessageBundle` (test) и пробрасывается в `dispatcher["bundle"]`.
- **CI**: `make ci` локально — **963 passed, 1 skipped, 96.85%** покрытие; `pre-commit run --all-files` — все хуки зелёные. На +8 тестов больше, чем после 1.5.A.

Результат / артефакты:
- `src/pipirik_wars/bot/presenters/start.py` (новый, ~70 LoC).
- `src/pipirik_wars/bot/handlers/start.py` (рефактор, было 119 LoC → стало 110 LoC, hardcoded-строки удалены).
- `src/pipirik_wars/bot/main.py` (+`bundle` поле в Container, +`locales_dir` в `build_container`, +`dispatcher["bundle"]` в `build_dispatcher`).
- `tests/fakes/message_bundle.py` + `tests/fakes/__init__.py` (новый fake, экспорт).
- `tests/unit/bot/handlers/test_start.py` (рефактор + 2 новых теста).
- `tests/unit/bot/presenters/test_start.py` (новый, 6 тестов).
- `tests/unit/bot/test_composition_root.py` (assert-ы на `bundle`).

Заметки / решения:
- **Почему `StartPresenter` — класс, а не модуль с функциями.** В `bot/presenters/profile.py` функции `render_full_nick` / `render_profile_card` чистые — они получают на вход уже готовый `ProfileView`, никаких внешних зависимостей у них нет. У `StartPresenter` иначе: **нужно переносить `bundle` через слой**. Если это были бы module-level-функции, каждая из них принимала бы `bundle` как первый аргумент: `def registered(*, bundle, locale): ...`. Это работает, но даёт два хвоста: (1) handler передаёт один и тот же `bundle` в каждый вызов — копипаста, (2) когда в 1.5.C мы добавим аналогичные `ProfilePresenter`/`ForestPresenter`/`OraclePresenter`, у каждого будет 5–10 функций со своим повтором. Класс с `bundle` в `__init__` инкапсулирует эту зависимость один раз и даёт унифицированный API всем будущим презентерам.
- **Почему `locale: Locale | None` с fallback на `DEFAULT_LOCALE`, а не required-параметр.** В production `LocaleMiddleware` всегда положит `Locale` в `data["locale"]` (см. Спринт 1.5.A). Но: (1) старые тесты вызывали handler без `locale` напрямую, чтобы не таскать middleware — оставляем им compat. (2) Если кто-то вырубит `LocaleMiddleware` в `register_middlewares` (скажем, дебаг/тестовая сборка), handler не должен падать — `DEFAULT_LOCALE = Locale("en")` это безопасный fallback по ПД 1.5.2. Это явно задокументировано в docstring-е.
- **Почему `RegisterPlayerInput.locale = effective_locale.code`, а не сохраняем `Locale` целиком.** `RegisterPlayerInput.locale: str | None` живёт в application-DTO и остался от Спринта 1.1.D. Менять его на `Locale` value-object потребовало бы ревизии и use-case-ов, и репозитория. По дизайн-решению на 1.5.B мы НЕ ломаем DTO, а просто заполняем его реальным кодом локали (`"ru"`/`"en"`). Если в будущем (1.5.C+) понадобится сохранять более сложную локаль (например, fallback chain), DTO будет переехать на `Locale` отдельным рефактор-PR-ом.
- **Почему `FakeMessageBundle` живёт в `tests/fakes/`, а не как inline в каждом тестовом файле.** В 1.5.B он используется в трёх местах (`test_start.py` handler, `test_start.py` presenter, `test_composition_root.py`). В 1.5.C те же самые тесты для `/profile`, `/forest`, `/oracle`, `/upgrade`, `/top` будут пользоваться этим же fake. Дублировать его шесть раз — анти-паттерн; общий fake в `tests/fakes/__init__.py` рядом с `FakeAuditLogger` / `FakeBalanceConfig` — единственный системный путь.
- **Почему стартовый `.ftl` НЕ менялся.** Все 5 ключей `start-*` были созданы в Спринте 1.5.A заранее с расчётом «handler 1.5.B их использует». Никаких новых ключей в этом PR-е добавлять не пришлось — это валидация, что план 1.5.A был корректным.

---

## 2026-05-05 — Спринт 1.5.A: i18n-фундамент (Locale + IMessageBundle + FluentMessageBundle + LocaleMiddleware)

**Автор:** Devin (по запросу sufficientdorette)
**Тип:** plan + feature (application port + value-object + infrastructure adapter + middleware wiring)
**Связано:** Текущий PR (Спринт 1.5.A), [development_plan.md §3 / Спринт 1.5, задачи 1.5.1–1.5.2](development_plan.md), [current_tasks.md Спринт 1.5 → 1.5.A](current_tasks.md). Открытие Спринта 1.5 после смерженного 1.4.D (PR #24).

Стартовый PR Спринта 1.5 — две вещи:

1. **Plan & roadmap Спринта 1.5** — те же 4 PR-а (1.5.A/B/C/D), что и в спринтах 1.1–1.4. Цель спринта — закрыть DoD MVP (см. `development_plan.md` §4): локализация, аудитлог длины, деплой на VPS.
2. **i18n-фундамент** (1.5.A) — value-object `Locale`, стратегия `LocaleResolver`, порт `IMessageBundle`, реализация `FluentMessageBundle` (Mozilla Fluent), включение `LocaleMiddleware` в middleware-стек.

Что сделано:
- **`src/pipirik_wars/application/i18n/`**: `Locale` (frozen-dataclass, `code ∈ {"ru", "en"}`, валидация в `__post_init__`) + `DEFAULT_LOCALE = Locale("en")` + `SUPPORTED_LOCALES = frozenset({"ru", "en"})`. `LocaleResolver` — чистая stateless-стратегия: `tg.language_code` (BCP-47, например `"ru-RU"` / `"en-US"`) приводит к `Locale("ru" | "en")` префиксным сравнением (case-insensitive), всё остальное / `None` / пустое — `default` (по умолчанию `Locale("en")`, ПД 1.5.2 «fallback EN»). Порт `IMessageBundle` (`Protocol`) + `MessageKey` (`NewType[str]`) + ошибки `I18nError` / `MessageKeyError`.
- **`src/pipirik_wars/infrastructure/i18n/FluentMessageBundle`** — реализация `IMessageBundle` поверх `fluent.runtime`. Per-locale ленивый кэш (`dict + threading.Lock`, double-check), загрузка `locales/{ru,en}.ftl` через `FluentResource(file.read_text())`. Стратегия fallback: `locale.format(key)` → `Locale("en").format(key)` → `MessageKeyError(key)`. «Soft fail» на отсутствующие плейсхолдеры (`logger.warning`, не падаем).
- **`src/pipirik_wars/bot/middlewares/locale.py`** — `LocaleMiddleware` теперь читает `tg_identity.language_code` и пробрасывает через `LocaleResolver` (DI-параметр), кладёт `Locale` в `data["locale"]` и сырой `language_code` в `data["telegram_language_code"]` (пригодится для аналитики). Без `tg_identity` — `DEFAULT_LOCALE`.
- **`src/pipirik_wars/bot/middlewares/__init__.py`** — `register_middlewares` принимает опциональный `locale_resolver` и регистрирует `LocaleMiddleware` между `AuthMiddleware` и `ThrottleMiddleware`. Применяется к `dp.message`, `dp.callback_query`, `dp.my_chat_member`.
- **`locales/ru.ftl` / `locales/en.ftl`** — стартовый набор ключей `start-registered`, `start-already`, `start-group`, `start-other`, `start-queued` (в одной локали по 5 ключей; остальные ключи из handler-ов будут перенесены в .ftl в спринте 1.5.B).
- **`pyproject.toml`** — добавлен runtime-`fluent.runtime>=0.4,<1` и mypy-override `module = "fluent.*"; ignore_missing_imports = true` (у `fluent.runtime` нет PEP-561 stubs).
- **Тесты:** 27 новых юнит-тестов:
  - `tests/unit/application/i18n/test_locale.py` — Locale (валидация, equality, hash) + LocaleResolver (RU/EN-варианты, fallback, override default).
  - `tests/unit/application/i18n/test_message_bundle_protocol.py` — Protocol-смок (FakeBundle satisfies `IMessageBundle`, `MessageKey` is `str` at runtime).
  - `tests/unit/infrastructure/i18n/test_fluent_bundle.py` — рендер RU/EN с параметрами, fallback RU→EN, `MessageKeyError` для отсутствующего ключа, `FileNotFoundError` для отсутствующей локали, кэширование bundle (удаляем .ftl после первого вызова — второй всё ещё работает).
  - `tests/unit/bot/middlewares/test_locale.py` — middleware с RU/EN/unknown/None `language_code`, без identity, custom resolver.
- **CI**: `make ci` локально — **955 passed, 1 skipped, 96.84%** покрытие.

Результат / артефакты:
- `src/pipirik_wars/application/i18n/{__init__.py,errors.py,locale.py,message_bundle.py}` (новый пакет, ~200 LoC).
- `src/pipirik_wars/infrastructure/i18n/{__init__.py,fluent_bundle.py}` (новый пакет, ~150 LoC).
- `src/pipirik_wars/bot/middlewares/{__init__.py,locale.py}` (обновлены — `LocaleResolver` в стэке).
- `locales/{ru,en}.ftl` (новые файлы, ~30 строк каждый).
- `pyproject.toml` (`fluent.runtime` runtime + mypy override).
- `tests/unit/{application,infrastructure}/i18n/...` + `tests/unit/bot/middlewares/test_locale.py` (новые / обновлённые).

Заметки / решения:
- **Почему `Locale` живёт в `application`, а не в `domain`.** `Locale` — артефакт UI / презентационного слоя. Домен (`Player`, `Length`, `Forest`) понятия не имеет о языках. Класть value-object в `domain` сейчас означало бы потом таскать `Locale` через все use-case-ы как «доменное» значение и нарушить инвариант «`domain` не зависит от UI».
- **Почему `LocaleResolver` — это стратегия в `application`, а не функция в middleware.** Middleware должен оставаться тонким (Single Responsibility): «прочитать язык, передать в DI». Резолв — **доменно-нейтральная** логика, и в спринте 1.5.B мы захотим переопределить её на уровне игрока через `players.locale_override` (handler `/lang ru|en`). Чтобы это произошло без переписывания middleware-а — стратегия инжектится через DI.
- **Почему `MessageKey` — это `NewType[str]`, а не Enum.** На MVP у нас будет ~50–100 ключей, и они растут вместе с handler-ами (новые презентеры → новые ключи). Enum заставлял бы делать релиз `application/i18n/keys.py` каждый раз, когда handler в bot-слое добавляет новую строку. `NewType` даёт type-safety (mypy ловит `bundle.format("typo", ...)` если функция объявлена как `MessageKey`) при минимальном overhead-е.
- **Почему «soft fail» на сломанные плейсхолдеры.** Бот предпочтительнее показать «Привет { $name }!» чем упасть с 500-кой в ЛС игрока. Логирование `logger.warning` на ошибки Fluent-а поможет ловить такие случаи в стейджинг-ране до прода.
- **Почему стартовый ftl содержит только `start-*`, а не все ключи разом.** Спринт 1.5.A — фундамент. Реальный «прогон handler-ов через bundle» произойдёт в 1.5.B (отдельный PR), когда мы добавим `IMessageBundle` в DI у handler-ов и удалим hardcoded-строки. Вытаскивать всё разом + менять handler-ы + добавлять `/lang`-команду в одном PR-е — это нарушение нашего принципа «маленькие PR-ы по 200–500 LoC».
- **Почему `LocaleMiddleware` пишет `tg_lang` в `data["telegram_language_code"]`.** Сырое значение пригодится для аналитики («сколько RU-телег у нас на самом деле») и для `/lang reset` (показать игроку «твой Telegram-язык: ru-RU; включить override?»).

---

## 2026-05-05 — Спринт 1.4.D: мини-нагрузочный тест `/forest` + полировка `/top`

**Автор:** Devin (по запросу persisyellow)
**Тип:** test (load) + refactor (cleanup)
**Связано:** Текущий PR (Спринт 1.4.D), [development_plan.md §3 / Спринт 1.4, задача 1.4.7](development_plan.md), [current_tasks.md Спринт 1.4 → 1.4.D](current_tasks.md). Закрытие Спринта 1.4 после смерженного 1.4.C (PR #23).

Финальный PR Спринта 1.4 — две вещи:

1. **Мини-нагрузочный тест ПД §1.4.7** «100 параллельных «походов в лес» без потери лока». Закрывает acceptance-критерий: под пиковой нагрузкой `activity_lock` корректно отбивает дублирующие запросы.
2. **Полировка `/top`** — чистка неиспользуемых импортов (`logging`, `typing.Final`) в handler-е после 1.4.C.

Что сделано:
- **`tests/integration/load/test_forest_concurrent.py`** — два сценария под `asyncio.gather`:
  - `test_100_parallel_starts_for_same_player_only_one_wins` — один игрок, 100 одновременных вызовов `StartForestRun` через **независимые `SqlAlchemyUnitOfWork`**: ровно 1 успех, 99 — `AlreadyInForestError`. После теста проверяем consistency БД: 1 строка `forest_runs(IN_PROGRESS)`, 1 строка `activity_locks` для этого игрока.
  - `test_100_parallel_starts_for_different_players_all_succeed` — 100 разных игроков по одному `/forest` каждый: все 100 успешны, ровно 100 `IN_PROGRESS`-походов и 100 локов в БД (нет ложных конфликтов на чужих локах).
- **`tests/integration/load/conftest.py`** — фикстура `shared_engine` поверх **файловой** SQLite (`tmp_path / "load.db"`), а не `:memory:` + `StaticPool`. Причина: `:memory:` через `StaticPool` мультиплексирует все асинхронные сессии на одно соединение/одну транзакцию, что замаскировало бы логические race-ошибки. Файловый SQLite даёт каждой сессии собственное соединение (`timeout=30s` для `SQLITE_BUSY`).
- **`pyproject.toml`** — зарегистрирован новый pytest-маркер `slow` для нагрузочных сценариев (`--strict-markers` иначе бы сломался).
- **`bot/handlers/top.py`** — удалены неиспользуемые `import logging`, `from typing import Final` и заглушка `_LOGGER`. Поведение не изменилось; чисто косметический рефакторинг по итогам 1.4.C.
- **CI**: `make ci` локально — **913 passed, 1 skipped, 96.97%** покрытие.

Результат / артефакты:
- `tests/integration/load/{__init__,conftest,test_forest_concurrent}.py` (новый пакет тестов).
- `pyproject.toml` (новый маркер `slow`).
- `src/pipirik_wars/bot/handlers/top.py` (чистка импортов).

Заметки / решения:
- **Почему файловая SQLite, а не `:memory:` + `StaticPool`.** `StaticPool` гарантирует ОДНО соединение для всего движка. Для async-кода это означает, что все 100 «параллельных» сессий жмутся в одну транзакцию — в итоге даже если бы lock-механика была сломана, тест бы прошёл (ошибки замаскировались бы блокировкой одного соединения). Файловая SQLite в `tmp_path` даёт нормальное соединение на сессию: каждая `SqlAlchemyUnitOfWork` открывает свой `BEGIN/COMMIT`, и серилизуется через файловый лок самого SQLite — это близко к Postgres-семантике.
- **Почему `slow`-маркер, но без `pytest -m "not slow"` в `make ci`.** В моменте 1.4.D есть всего 2 нагрузочных теста по ~1с каждый, общий прирост к CI пренебрежим. Маркер регистрируем заранее, чтобы будущим Sprint 4.1.5 («нагрузочный тест 10× MVP») было куда вешать тяжёлую нагрузку, не ломая текущий зелёный pipeline.
- **Полировка вместо контентной разработки.** Все презентеры просмотрены на typo — критических ошибок не найдено. `display_name` / `PlayerName` / `Title` приходят из контролируемых источников (`balance.yaml`, hardcoded enum), HTML-инъекций через них быть не может; явное HTML-экранирование можно добавить в Спринте 1.5 при подключении Telegram first_name (i18n).
- **DOD MVP-чек-лист.** Спринты 1.1–1.4 закрыли: регистрация ✅, `/profile` ✅, `/forest` + дроп ✅, прокачка толщины ✅, `/oracle` ✅, `/top` ✅, DAU Gate ✅, Activity Lock под нагрузкой ✅. Остаётся для DoD MVP: i18n RU+EN (Спринт 1.5.1–1.5.2), деплой (1.5.7).

---

## 2026-05-05 — Спринт 1.4.C: топ игроков (`/top` + in-memory TTL=60s кэш)

**Автор:** Devin (по запросу persisyellow)
**Тип:** feature (domain + application port + use-case + in-memory cache + bot-handler + composition wiring)
**Связано:** Текущий PR (Спринт 1.4.C), [development_plan.md §3 / Спринт 1.4, задача 1.4.6](development_plan.md), [current_tasks.md Спринт 1.4 → 1.4.C](current_tasks.md). Продолжение Спринта 1.4 после смерженного 1.4.B (PR #22).

Узкий PR: публичная команда `/top` — топ-100 пипириков по убыванию длины (формат «Титул Название Имя — N см»). Под капотом — in-memory кэш TTL=60s, чтобы шквал нажатий из чата не упирался в БД.

Что сделано:
- **Domain (`domain/player/repositories.py`)** — расширен порт `IPlayerRepository` методом `list_top_by_length(*, limit) -> Sequence[Player]`. Контракт: только `ACTIVE`-игроки (заморозка исключается — игроки на «лавке штрафников» в топ не лезут), сортировка `length_cm DESC`, тай-брейкер `id ASC` (стабильный порядок при равной длине, важно для воспроизводимости результата под кэшем), `ValueError` для `limit ≤ 0`.
- **Application (`application/top/`)** — frozen DTO `TopPlayerEntry(title, display_name, name, length_cm)` с валидацией `length_cm ≥ 0`. Read-only порт `ITopPlayersQuery.get_top(*, limit) -> Sequence[TopPlayerEntry]`. Use-case `GetTopPlayers(query, default_limit=100)` — тонкая обёртка над портом, валидирует `limit > 0`, по умолчанию использует `default_limit=100` (контракт ПД 1.4.6 «топ-100»). Чистая разводка: use-case **не знает** про кэш или БД — это инфраструктурный выбор сборки.
- **Infrastructure (`infrastructure/db/repositories/player.py` + `infrastructure/cache/top_players.py`)** — `SqlAlchemyPlayerRepository.list_top_by_length` строит честный `SELECT … WHERE status = 'ACTIVE' ORDER BY length_cm DESC, id ASC LIMIT :limit`. `TopPlayersCache(ITopPlayersQuery)` — in-memory снимок с `asyncio.Lock` для защиты от cache stampede: когда десять корутин одновременно зовут `/top` под просроченным кэшем, к БД летит **один** запрос, остальные ждут на локе. TTL=60s по умолчанию (через ctor-параметр), на границе считаем кэш уже устаревшим (`elapsed >= ttl`). При запросе с большим `limit`, чем закэшировано — рефреш; при меньшем — отдаём «префикс» из кэша. `invalidate()` для админских флоу. `display_name` пересчитывается через `IBalanceConfig` при каждом рефреше — после `/balance_reload` следующий рефреш увидит новые имена бесплатно (TTL ≤ 60 с).
- **Bot (`bot/handlers/top.py` + `bot/presenters/top.py`)** — handler `/top` доступен и в ЛС, и в группах (это «социальная» команда, ГДД §2.6); вызывает `get_top_players.execute()` без аргументов, рендерит результат презентером. Презентер `render_top` делегирует склейку «Титул Название Имя» в уже существующий `render_full_nick` (DRY с `/profile`), форматирует строки как «`N. Полный_ник — N см`», пустой список → дружелюбное приглашение «нажми /start». Никакой регистрации для `/top` не требуется — это публичный read-only.
- **Composition root (`bot/main.py`)** — `top_players_query = TopPlayersCache(uow=…, players=…, balance=…, clock=…, ttl_seconds=60)` и `get_top_players = GetTopPlayers(query=top_players_query)` собираются в `build_container(...)`, прокидываются в `Container` и aiogram-DI (`dispatcher["get_top_players"]`). Новый `top_router` зарегистрирован в `register_routers(...)` после `oracle_router`.
- **Тесты (40+ новых)** — интеграционные на `list_top_by_length` (ordering DESC, frozen excluded, tie-break id ASC, limit, empty, ValueError на limit ≤ 0); юнит на `TopPlayerEntry` (валидации/frozen); юнит на `GetTopPlayers` (default_limit=100, передача limit, валидации); юнит на `TopPlayersCache` (TTL boundary, refresh after stale, prefix-of-cache reuse, invalidate, balance hot-reload visibility, **stampede protection** под `asyncio.gather` — 3 параллельных вызова → 1 обращение к репо); юнит на handler `/top` (private/group/empty); юнит на презентер (форматирование, эмодзи, порядок); composition root обновлён с `FakeTopPlayersQuery` и `GetTopPlayers`. `make ci`: **911 passed, 1 skipped**, coverage **96.81%**.

Результат / артефакты:
- domain port: `src/pipirik_wars/domain/player/repositories.py` (новая абстрактная method `list_top_by_length`).
- application: `src/pipirik_wars/application/top/{__init__,entries,query,get_top}.py`.
- infra: `src/pipirik_wars/infrastructure/db/repositories/player.py` (метод `list_top_by_length`), `src/pipirik_wars/infrastructure/cache/{__init__,top_players}.py`.
- bot: `src/pipirik_wars/bot/handlers/top.py`, `src/pipirik_wars/bot/presenters/top.py` + регистрация в `__init__.py` обоих пакетов и в `bot/main.py`.
- тесты: `tests/integration/db/test_player_repository.py` (+6), `tests/unit/application/top/{test_entries,test_get_top}.py`, `tests/unit/infrastructure/cache/test_top_players_cache.py`, `tests/unit/bot/{handlers,presenters}/test_top.py`, `tests/fakes/top_players.py` + регистрация в `tests/fakes/__init__.py` и `tests/unit/bot/test_composition_root.py`.

Заметки / решения:
- **Кэш как порт, не как декоратор** — `TopPlayersCache` реализует `ITopPlayersQuery` напрямую, а не декорирует другую реализацию. На уровне use-case-а ничего не знает про кэш: меняем стратегию в `build_container` без правок application-слоя. Если завтра захотим Redis — добавим `RedisTopPlayersCache(ITopPlayersQuery)` без касания доменa/application.
- **Тай-брейкер `id ASC`** — без него порядок одинаковых длин был бы не детерминирован, и кэш отдавал бы «прыгающие» места. С тай-брейкером один и тот же `/top` всегда выглядит одинаково между рефрешами.
- **Stampede protection через `asyncio.Lock`** — критично для социальной команды в группах: под пик-нагрузкой 10 нажатий /top за секунду от разных юзеров в БД летит ровно 1 запрос. Тест `test_concurrent_requests_trigger_single_refresh` это явно проверяет: 3 параллельных `gather` → 1 обращение к репо.
- **Frozen-игроки исключаются** — заблокированные/замороженные не должны портить публичный рейтинг. Это доменное правило, поэтому `WHERE status = 'ACTIVE'` сидит и в SqlAlchemy-репо, и в FakePlayerRepository.
- **DRY с `/profile`** — `render_full_nick` уже умеет «Титул Название Имя» с пропуском `None`-частей; переиспользуем без копипаста.

---

## 2026-05-05 — Спринт 1.4.B: предсказатель (`/oracle` + Moscow-TZ кулдаун + 220 RU + 220 EN темплейтов)

**Автор:** Devin (по запросу persisyellow)
**Тип:** feature (domain + application use-case + infra + bot-handler + DI + 220 RU/EN темплейтов)
**Связано:** Текущий PR (Спринт 1.4.B), [development_plan.md §3 / Спринт 1.4, задачи 1.4.4 / 1.4.5](development_plan.md), [current_tasks.md Спринт 1.4 → 1.4.B](current_tasks.md). Продолжение Спринта 1.4 после смерженного 1.4.A.

Узкий PR: пользовательская команда `/oracle` — игрок раз в сутки **по Москве** (`Europe/Moscow`, сброс в 00:00 МСК) получает шуточное предсказание из каталога ≥ 200 шаблонов и прибавку длины `uniform(1, 20)` см.

Что сделано:
- **Domain (`domain/oracle/`)** — иммутабельные сущности `OracleTemplate(id, text)` (валидация: непустое + без whitespace) и `OracleResult(bonus_cm, template)`. Чистая функция `roll_oracle(*, balance, random, templates)` через `IRandom` (никаких side-эффектов, тривиально тестируется на FakeRandom). Порт `IOracleHistoryRepository` с frozen-dataclass `OracleInvocation(player_id, moscow_date, bonus_cm, template_id, occurred_at)`. Иерархия ошибок: `OracleError` ← `OracleAlreadyUsedTodayError(player_id, moscow_date)` / `OracleNoTemplatesError(locale)`.
- **Application (`application/oracle/`)** — порт `IOracleTemplateProvider.get_templates(*, locale)`, DTO `InvokeOracleInput(tg_id, locale='ru')` с pydantic-валидацией, use-case `InvokeOracle`. Workflow: `players.get_by_tg_id` → preflight `history.get_for_day(player_id, moscow_date)` (если запись уже есть → `OracleAlreadyUsedTodayError`) → `roll_oracle(...)` → `with_length(+bonus_cm)` → `players.save` → `history.add` (если БД-уровень UNIQUE упал — ловим `IntegrityError` и трактуем как race-вариант `OracleAlreadyUsedTodayError`) → audit `LENGTH_GRANT` с `idempotency_key=f"oracle:{player_id}:{moscow_date.isoformat()}"`.
- **Infrastructure** — миграция `0005_oracle_invocations` создаёт таблицу с FK→users(id) CASCADE, CHECK `bonus_cm > 0`, **уникальный** индекс `(player_id, moscow_date)` (защита от race на БД-уровне) + индекс по `moscow_date` для аналитики. ORM `OracleInvocationORM` с `mapped_column`. Репозиторий `SqlAlchemyOracleHistoryRepository` (catches `sa.exc.IntegrityError` → `DomainIntegrityError`). `JsonOracleTemplateProvider(templates_dir)` — lazy load + per-locale кэш + fallback на `ru` если запрошенная локаль отсутствует, ошибки парсинга/дублей → `ConfigError`, пустой каталог → `OracleNoTemplatesError`.
- **Bot (`bot/handlers/oracle.py` + `bot/presenters/oracle.py`)** — handler `/oracle` (только в ЛС, иначе инструкция «открой ЛС»): `InvokeOracle.execute(InvokeOracleInput(tg_id, locale='ru'))`, обработка `PlayerNotFoundError` / `OracleAlreadyUsedTodayError` (рендерит «возвращайся через Xч Yм, 00:00 по Москве» с реальным временем до сброса). Чистые презентеры с safe-format `{user}` (отсутствующий ключ → возвращает плейсхолдер as-is, не падает с `KeyError`).
- **Темплейты** — `config/templates/oracle_ru.json` (220 шаблонов, ID `oracle.ru.0001..0220`) и `config/templates/oracle_en.json` (220 шаблонов, ID `oracle.en.0001..0220`). Все темплейты содержат плейсхолдер `{user}`. Категории: позитив, пипирик-юмор, мистика, мотивация, бытовуха, бонусы.
- **Composition root (`bot/main.py`)** — `oracle_history`, `oracle_templates`, `invoke_oracle` собираются в `build_container(...)` (новый параметр `templates_dir: Path | None = None`, default `config/templates`), прокидываются в `Container` и aiogram-DI (`dispatcher["invoke_oracle"]`, `dispatcher["clock"]`). Новый `oracle_router` зарегистрирован в `register_routers(...)` после `upgrade_router`.
- **Тесты** — 7 новых файлов:
  - `tests/unit/domain/oracle/test_entities.py` — валидация полей, frozen, OracleResult.
  - `tests/unit/domain/oracle/test_errors.py` — иерархия исключений и поля.
  - `tests/unit/domain/oracle/test_services.py` — `roll_oracle` happy path, детерминированность по seed-у, **acceptance ПД 1.4.4: 10 000 прогонов uniform(1, 20) → среднее 10.0..11.0**, всегда `bonus_cm ≥ 1` и в диапазоне.
  - `tests/unit/application/oracle/test_invoke.py` — успех, length grant, audit `LENGTH_GRANT`, повтор в тот же московский день → `OracleAlreadyUsedTodayError`, успех на следующий день, изоляция между игроками, **граничный кейс TZ** (4 мая 23:30 UTC = 5 мая 02:30 МСК), `PlayerNotFoundError` с rollback.
  - `tests/integration/db/oracle/test_oracle_history_repository.py` — `add()` + `get_for_day()`, UNIQUE-нарушение, изоляция между игроками и днями.
  - `tests/integration/db/test_migrations.py` — обновлён: `0005_oracle_invocations` зарегистрирован в линейной цепочке, applied чисто, таблица создаётся.
  - `tests/integration/templates/test_oracle_loader.py` — реальные `oracle_ru.json` и `oracle_en.json` ≥ 200 шаблонов, уникальные ID, корректный `{user}` рендер; кэш per-locale; fallback ru при отсутствующей локали; ошибки парсинга → `ConfigError`.
  - `tests/unit/bot/presenters/test_oracle.py` — рендеринг плейсхолдера, отсутствующий `{stranger}` сохраняется как есть, время до сброса.
  - `tests/unit/bot/handlers/test_oracle.py` — happy path, отказ в группе, `PlayerNotFoundError` → REPLY_NOT_REGISTERED_RU, `OracleAlreadyUsedTodayError` → cooldown text, fallback `username` если нет `first_name`.

Результат / артефакты:
- Domain: `src/pipirik_wars/domain/oracle/{entities,errors,services,repositories,__init__}.py`.
- Application: `src/pipirik_wars/application/oracle/{invoke,templates,__init__}.py`, DTO `InvokeOracleInput`.
- Infra: `migrations/versions/20260505_0005_oracle_invocations.py`, `db/models/oracle.py`, `db/repositories/oracle_history.py`, `templates/oracle.py`.
- Bot: `bot/handlers/oracle.py`, `bot/presenters/oracle.py`.
- Темплейты: `config/templates/oracle_ru.json` (220), `config/templates/oracle_en.json` (220).
- Тесты: 50+ новых тестов в 9 файлах. Локальный `make ci` (ruff + mypy --strict + import-linter + pytest 869 passed) — зелёный, общий покрытие 96.70%.
- Документация: обновлены `docs/current_tasks.md` (1.4.A → ✅ смержено, 1.4.B → 🟢 готово к ревью) и `docs/history.md` (эта запись).

Заметки / решения:
- **Кулдаун — по `Europe/Moscow`, не UTC.** В таблице `oracle_invocations.moscow_date` — `DATE`, отдельная колонка для `(player_id, moscow_date)` UNIQUE. `IClock.moscow_date()` уже был с 1.4.A (для `daily_head`); use-case вызывает его строго один раз и передаёт результат в repo, чтобы логика теста на «23:30 UTC = 02:30 МСК следующего дня» жила в одном месте.
- **Race protection.** Preflight `get_for_day(...)` ловит обычный кейс «нажал второй раз через час». Однако между preflight и `add()` могут проскочить два конкурентных запроса; БД-уровень UNIQUE-индекс ловит это, репозиторий ловит `IntegrityError` и use-case переводит её в `OracleAlreadyUsedTodayError` — handler одинаково покажет «возвращайся завтра».
- **Идемпотентность.** `idempotency_key=f"oracle:{player_id}:{moscow_date.isoformat()}"` — стабильный, поэтому даже при retry-е на уровне сети audit-лог не задублируется (audit-сервис проверяет ключ).
- **Темплейты.** 220 RU + 220 EN > требуемых 200, чтобы не упереться в acceptance, если потом захотим выкинуть несколько неудачных. Все шаблоны содержат `{user}` ровно 1 раз; loader проверяет уникальность `id`, ошибки JSON/структуры → `ConfigError`. Тест на реальные файлы валидирует `tpl.text.format(user='Alice')` — это ловит сломанные плейсхолдеры в production-каталоге.
- **Что НЕ сделано в этом PR.** `1.4.6` (`/top` + кэш TTL=60s) и `1.4.7` (мини-нагрузочный тест) — это `1.4.C` и `1.4.D`. `i18n` LocaleMiddleware — это Спринт 1.5; пока handler жёстко передаёт `locale="ru"` в use-case (template_provider всё равно умеет fallback на ru при отсутствии запрошенной локали).

---

## 2026-05-04 — Спринт 1.4.A: прокачка толщины (`/upgrade` + use-case + table-driven unlock)

**Автор:** Devin (по запросу azurehannah)
**Тип:** feature (domain + application use-case + bot-handler + DI)
**Связано:** Текущий PR (Спринт 1.4.A), [development_plan.md §3 / Спринт 1.4, задачи 1.4.1 / 1.4.2 / 1.4.3](development_plan.md), [current_tasks.md Спринт 1.4 → 1.4.A](current_tasks.md). Открывает Спринт 1.4 (после закрытия 1.3 в PR #20).

Узкий PR: пользовательская команда прокачки толщины — игрок вызывает `/upgrade`, получает карточку «прокачать с N до N+1, стоимость XXXX см», подтверждает inline-кнопкой, длина списывается, толщина растёт. Параллельно вводим table-driven unlock-функцию для будущих активностей (forest/pvp/mountains/raid/...).

Что сделано:
- **Domain (`domain/progression/thickness.py`)** — три чистые функции: `cost_for_upgrade(*, current_thickness, cost_base, cost_exponent)` по формуле `cost(n→n+1) = cost_base · (n+1)^cost_exponent` (acceptance §3 / 1.4.1: `cost(1→2)=4000`, `cost(9→10)=100000`, `cost(15→16)=256000`, `cost(19→20)=400000`). `is_activity_unlocked(*, thickness, activity, unlock_levels: Mapping[str, int])` — table-driven, домен принимает unlock-таблицу как аргумент (use-case передаёт snapshot из `balance.thickness.unlock_levels`), это сохраняет домен чистым и упрощает тестирование. `require_unlocked(...)` бросает `ActivityLockedError(activity, current_thickness, required_thickness)`.
- **Application (`application/progression/upgrade_thickness.py`)** — use-case `UpgradeThickness` с DTO `UpgradeThicknessInput(tg_id, expected_cost_cm: int | None)`. Workflow: загрузка игрока → `cost_for_upgrade(...)` → optional contract-check `expected_cost_cm` (бросает `ConcurrencyError` при расхождении — защита от race «balance.yaml перегружен между показом и нажатием Подтвердить») → `require_spend(action=THICKNESS_UPGRADE)` (правило 20 см из 1.2.1) → двойная мутация `with_length` + `with_thickness` → атомарный `save` → **два** audit-события: `LENGTH_REVOKE` (для трекинга траты длины) и `THICKNESS_UPGRADE` с `idempotency_key=f"thickness_upgrade:{player_id}:{new_level}"` (для трекинга прогрессии и защиты от двойной прокачки на одном уровне). Возврат — frozen dataclass `ThicknessUpgraded(player_before, player_after, cost_cm, new_thickness)`.
- **Bot-presenter (`bot/presenters/upgrade.py`)** — четыре чистые функции: `render_upgrade_proposal(...)` (карточка перед подтверждением: текущий/целевой уровень, стоимость, остаток после списания, минимум по правилу 20 см), `render_upgrade_success(...)`, `render_upgrade_insufficient(...)`. Кодек callback_data: `upgrade_callback_data(action, expected_cost_cm)` / `parse_upgrade_callback_data(raw)` с форматом `"upgrade:<action>:<expected_cost_cm>"` (≤ 64 байта Telegram-лимита). `expected_cost_cm` зашит в callback_data — handler передаёт его обратно в use-case, чтобы поймать «balance hot-reloaded между показом и нажатием». `build_upgrade_proposal_keyboard(*, expected_cost_cm)` собирает inline-пару `[Подтвердить (XXXX см)] [Отменить]`.
- **Bot-handler (`bot/handlers/upgrade.py`)** — два handler-а. `handle_upgrade` (`/upgrade` в ЛС): группа/супергруппа → инструкция «открой ЛС»; не зарегистрирован → инструкция нажать `/start`; недостаточно длины (по правилу 20 см) → текст «не хватает N см» **без** клавиатуры; иначе → карточка-proposal + inline-пара кнопок. `handle_upgrade_callback` (callback под `upgrade:*`): `cancel` → snять клавиатуру + заменить текст на «Прокачка отменена»; `confirm` → `UpgradeThickness.execute(input_dto)`, обработка `PlayerNotFoundError` / `InsufficientLengthError` (race-кейс) / `ConcurrencyError` (balance hot-reloaded), при успехе → `render_upgrade_success(...)`. Идемпотентность повторного нажатия: после первого клика handler делает `edit_reply_markup(reply_markup=None)` — кнопок больше нет, второй клик невозможен.
- **Composition root (`bot/main.py`)** — `UpgradeThickness` собирается в `build_container(...)`, прокидывается в `Container.upgrade_thickness`, прокидывается в `dispatcher["upgrade_thickness"]` + `dispatcher["balance"]` для aiogram-DI. Новый `upgrade_router` зарегистрирован в `register_routers(...)` после `forest_router`.
- **Тесты** — три новых файла:
  - `tests/unit/domain/progression/test_thickness.py` — 38 passed + 1 skipped (acceptance-значения по ГДД, все 8 unlock-уровней по умолчанию, ошибка `ActivityLockedError`).
  - `tests/unit/application/progression/test_upgrade_thickness.py` — 9 кейсов: success-path с проверкой обоих audit-событий и `idempotency_key`, expected_cost contract-check (pass/fail), `PlayerNotFoundError`, `InsufficientLengthError` с граничными значениями (4019/4020), `ConcurrencyError` без мутации.
  - `tests/unit/bot/handlers/test_upgrade.py` (15 кейсов: handler + callback) и `tests/unit/bot/presenters/test_upgrade.py` (11 кейсов: рендеры + кодек callback_data round-trip).
  - `tests/unit/bot/test_composition_root.py` — добавлены проверки `upgrade_thickness` в Container + dispatcher + наличие `upgrade`-router.

Результат / артефакты:
- Домен: <code>src/pipirik_wars/domain/progression/thickness.py</code>, <code>src/pipirik_wars/domain/progression/errors.py</code> (новый класс), `__init__.py`.
- Application: <code>src/pipirik_wars/application/progression/upgrade_thickness.py</code>, <code>src/pipirik_wars/application/dto/inputs.py</code> (новый DTO), `__init__.py`.
- Bot: <code>src/pipirik_wars/bot/presenters/upgrade.py</code>, <code>src/pipirik_wars/bot/handlers/upgrade.py</code>, `__init__.py` обоих, `bot/main.py` (DI).
- Тесты: 4 новых файла, 73 новых кейса; всего по проекту **814 passed + 1 skipped, coverage 96.59%** (требование ≥ 80% выполнено с большим запасом).
- Lint/typecheck/imports: `ruff check` / `ruff format --check` / `mypy --strict` / `lint-imports` — все чисто, 3 contracts kept.

Заметки / решения:
- **Почему unlock-таблица как аргумент, а не через `IBalanceConfig`?** Домен не должен зависеть от прикладных портов (DIP). Use-case-ы получают snapshot `balance.get().thickness.unlock_levels` и передают его в `is_activity_unlocked(...)`. Это держит домен чистым (не нужно мокать `IBalanceConfig` в его тестах) и упрощает повторное использование функции в любом use-case-е.
- **Почему два audit-события (`LENGTH_REVOKE` + `THICKNESS_UPGRADE`)?** `LENGTH_REVOKE` нужен для трекинга списания длины (как в любой другой spend-операции — единый формат для отчётов и анти-фрода). `THICKNESS_UPGRADE` нужен для трекинга прогрессии и идемпотентности — `idempotency_key=f"thickness_upgrade:{player_id}:{new_level}"` гарантирует, что повторная прокачка на тот же уровень не прошла бы (если бы база её допустила).
- **Почему `expected_cost_cm` в callback_data?** Между показом proposal и нажатием «Подтвердить» админ может перегрузить `balance.yaml` через `/balance_reload` (1.1.E). Если новые `cost_base/cost_exponent` дают другую цифру — игрок видит одну сумму, а заплатит другую. Клиент-side контракт через `expected_cost_cm` ловит это: use-case бросит `ConcurrencyError`, handler покажет «Стоимость изменилась — открой /upgrade ещё раз».
- **Почему `InsufficientLengthError` обрабатывается в callback тоже?** Между показом proposal и нажатием «Подтвердить» игрок мог потратить длину в другой активности (race с асинхронным `/forest`-finish-ом, например). Handler корректно шлёт «Недостаточно длины» с deficit-ом из исключения, а не ронит callback.
- **Граница 20 см правила траты:** acceptance — 4019 см (cost=4000) даёт остаток 19 < 20 → отказ; 4020 см → остаток 20 = MIN → проходит. Зафиксировано в тестах `test_insufficient_at_exact_boundary` / `test_passes_at_exact_boundary_plus_1`.

---

## 2026-05-04 — Спринт 1.3.D: bot-handler `/forest` + finish-нотификация + inline-кнопки

**Автор:** Devin (по запросу azurehannah)
**Тип:** feature (bot/handlers + bot/presenters + bot/notifications + application use-case + DI)
**Связано:** Текущий PR (Спринт 1.3.D), [development_plan.md §3 / Спринт 1.3, задачи 1.3.1 / 1.3.2 / 1.3.6](development_plan.md), [current_tasks.md Спринт 1.3 → 1.3.D](current_tasks.md). Закрывает Спринт 1.3 (после смерженных 1.3.A–C).

Узкий PR: пользовательская петля «лес» — игрок вызывает `/forest` и получает «ушёл в лес», по истечении кулдауна получает «вернулся из леса» с inline-кнопками. Ровно три фичи в одном PR: command-handler, finish-нотификатор и callback-handler `apply_name`. Применение item-дропа / drop_name / drop_item — placeholder-toast, чтобы не блокировать выпуск; полная реализация инвентаря — Спринт 1.4.

Что сделано:
- **Application (`application/forest/notifier.py`)** — порт `IForestFinishNotifier.notify(result: ForestRunFinished) -> None`. Контракт «best-effort, не бросает наружу»: реализация ловит ошибки сама. Используется APScheduler-адаптером после успешного `FinishForestRun.execute()` — пост-коммитный сайд-эффект, который не должен ронять job-у.
- **Application (`application/forest/apply_name_drop.py`)** — use-case `ApplyForestNameDrop(uow, players, runs, audit, clock)`. Срабатывает при нажатии «Заменить» под сообщением «вернулся из леса», когда у игрока **уже есть имя** и из леса выпал `NameDrop` (auto-apply невозможен). Защита: `ForestRunOwnershipError` (защита от форварда чужой кнопки), `ForestDropMismatchError` (run.drop ≠ NameDrop), идемпотентный no-op если `player.name == run.drop.name`. Audit: `NAME_GRANT` с `reason="forest_name_replacement"` и `idempotency_key=f"forest_name_replace:{run_id}"`.
- **Application DTO** — `ApplyForestNameDropInput(run_id, tg_id)` с pydantic-валидацией.
- **Domain (`domain/forest/errors.py`)** — добавлены `ForestRunOwnershipError(run_id, run_player_id, actor_player_id)` и `ForestDropMismatchError(run_id, expected, got)` для callback-сценариев.
- **Bot/presenters (`bot/presenters/forest.py`)** — чистые функции рендера + сборки `InlineKeyboardMarkup`. `render_forest_started(player, display_name, cooldown_minutes)`, `render_forest_finished(result, display_name_after)`, `build_finish_keyboard(result)`, `forest_callback_data(action, run_id)` / `parse_forest_callback_data(raw)` (формат `forest:<action>:<run_id>` ≤ 33 байт, под Telegram-лимит 64). Полный ник `[Титул] [Название] [Имя]` через существующий `render_full_nick(...)` из 1.1.E.
- **Bot/handlers (`bot/handlers/forest.py`)** — handler `/forest` (private only) и единый `handle_forest_callback` для всех `forest:*`-кнопок. Перехватывает `PlayerNotFoundError` / `AlreadyInForestError` / `ForestRunNotFoundError` / `ForestRunOwnershipError` / `ForestDropMismatchError` и шлёт toast / инструкцию. После успешного callback-а `edit_reply_markup(reply_markup=None)` снимает клавиатуру, чтобы повторные клики не проходили.
- **Bot/notifications (`bot/notifications/forest.py`)** — `TelegramForestFinishNotifier(IForestFinishNotifier)` рендерит сообщение и шлёт через `bot.send_message`. Catch `TelegramAPIError` / general `Exception` → лог + `return` (ни одной exc не пропускается в APScheduler-callback). Имя нотификатора живёт в `bot/`, а не в `infrastructure/telegram/`, потому что нужно `bot/presenters/forest.py` (`InlineKeyboardMarkup`), а `infrastructure → bot` запрещён import-linter-ом.
- **Infrastructure (`infrastructure/scheduler/aps.py`)** — `APSchedulerDelayedJobScheduler` теперь принимает опциональный `notifier: IForestFinishNotifier | None`. После успешного `FinishForestRun.execute()` зовёт `notifier.notify(result)`; ошибка нотификатора логируется через `logger.exception(...)`, но не пробрасывается (контракт notifier-а — «не бросать»; защита по второму уровню).
- **Composition root (`bot/main.py`)** — `build_container(settings, *, balance_yaml_path, bot=None)`. Если `bot is not None` — создаётся `TelegramForestFinishNotifier` и передаётся в scheduler. `ApplyForestNameDrop` добавлен в `Container` и в `build_dispatcher` workflow-data (`apply_forest_name_drop`). `run()` создаёт Settings → Bot → `build_container(settings, ..., bot=bot)`, чтобы нотификатор всегда был сконфигурирован в production.
- **Тесты** (всего +70 кейсов, общее число 736, покрытие 96.60 %):
  - `tests/unit/bot/presenters/test_forest.py` — 29 кейсов: `render_forest_started` (новичок без титула / титул+имя / минимальный кулдаун), `render_forest_finished` (`NoDrop`+титул, `ItemDrop`+редкость, `NameDrop` auto-apply, `NameDrop` с уже имеющимся именем), `build_finish_keyboard` (4 ветки), сериализация/парсинг callback-data (round-trip, malformed, негативный run_id, длина под 64 байта), хелперы.
  - `tests/unit/bot/handlers/test_forest.py` — 21 кейс: `/forest` happy / not-registered / already-in-forest / group / supergroup / channel / no-identity / профиль вернул None; callback `apply_name` (success / already-applied / run-not-found / player-not-found / ownership-mismatch / drop-mismatch); placeholder-toast для `drop_name`/`equip_item`/`drop_item`; malformed callback_data; `edit_reply_markup` swallow при ошибке.
  - `tests/unit/bot/notifications/test_forest.py` — 9 кейсов: `was_already_finished` → no-op; happy paths для `NoDrop` / `ItemDrop` / `NameDrop`-replacement; `TelegramAPIError` / `RuntimeError` / падение баланса все swallow-ятся; `display_name_for(after.length)` пересчитывается; работает без logger.
  - `tests/unit/application/forest/test_apply_name_drop.py` — 7 кейсов: happy (audit-запись с `NAME_GRANT`/`forest_name_replacement`), идемпотентность при том же имени, ошибки run-not-found / player-not-found / ownership-mismatch / drop-mismatch (NoDrop / ItemDrop), отсутствие commit-а при ошибках.
  - `tests/unit/infrastructure/scheduler/test_aps.py` — +4 кейса: notifier зовётся после успешного finish-а; не зовётся при доменной ошибке; ошибка notifier-а не ронит job-у; работает без notifier-а (обратная совместимость).
  - `tests/unit/bot/test_composition_root.py` — обновлён `_container_with_fakes()` для нового поля `apply_forest_name_drop`.

Результат / артефакты:
- `src/pipirik_wars/application/forest/notifier.py` (порт)
- `src/pipirik_wars/application/forest/apply_name_drop.py` (use-case)
- `src/pipirik_wars/application/dto/inputs.py` (DTO `ApplyForestNameDropInput`)
- `src/pipirik_wars/domain/forest/errors.py` (новые ошибки)
- `src/pipirik_wars/bot/handlers/forest.py` (новый handler + callback-router)
- `src/pipirik_wars/bot/presenters/forest.py` (новый презентер)
- `src/pipirik_wars/bot/notifications/forest.py` (`TelegramForestFinishNotifier`)
- `src/pipirik_wars/infrastructure/scheduler/aps.py` (notifier wiring)
- `src/pipirik_wars/bot/main.py` (composition root, build_container получает Bot)
- `tests/unit/bot/presenters/test_forest.py`, `tests/unit/bot/handlers/test_forest.py`, `tests/unit/bot/notifications/test_forest.py`, `tests/unit/application/forest/test_apply_name_drop.py`, `tests/unit/infrastructure/scheduler/test_aps.py`

Заметки / решения:
- **Нотификатор живёт в `bot/`, не в `infrastructure/telegram/`.** Ему нужны `InlineKeyboardMarkup` и `render_forest_finished` из `bot/presenters/forest.py`. Импорт `infrastructure → bot` запрещён import-linter-ом (это и правильно — инфраструктура не должна знать про презентационный слой). Поэтому нотификатор «телеграмный по реализации, бот-овый по слою»: presenter зависит от aiogram-типов, а нотификатор использует presenter. Это согласовано с layered_architecture-контрактом и не ломает направление зависимостей.
- **APScheduler не должен пометить job-у failed из-за нотификатора.** `_run_finish_job` сначала зовёт `FinishForestRun.execute()` (если падает — глотает); затем вызывает `notifier.notify(result)`. Сам нотификатор не бросает, но даже если бросит — APScheduler-адаптер ловит и логирует через `logger.exception`. Это «оборона в глубину»: ни логи telegram-API, ни внутренние баги не должны откатывать job-у.
- **Callback-handler делает `edit_reply_markup(None)` для всех завершающих действий.** Это снимает кнопки сразу после клика, чтобы пользователь не мог нажать повторно (даже если идемпотентный use-case это переживёт). При `ForestRunOwnershipError` (форвард в чужой чат) клавиатуру **не** трогаем — это чужое сообщение.
- **`drop_name` / `equip_item` / `drop_item` пока placeholder.** Они шлют toast «выбросил имя» / «надевание предмета — Спринт 1.4» и снимают клавиатуру, но НЕ зовут use-case. Применение `ItemDrop` (надеть/положить в инвентарь) и `drop_name` (запись `NAME_DROP`-аудита, потеря имени из инвентаря) появятся в Спринте 1.4 (предметы и инвентарь). Это сознательный компромисс: текущий PR закрывает 1.3.1 / 1.3.2 / 1.3.6 в части UX «вышел в лес → вернулся → видит дроп», но полное применение item-дропа отложено.
- **`ApplyForestNameDrop` идемпотентен через ownership-проверку и сравнение `player.name == drop.name`.** Аудит-`idempotency_key` (`forest_name_replace:{run_id}`) предотвращает race-condition при двойном клике быстрее, чем edit_reply_markup.
- **Composition root: `build_container(bot=...)`.** Чтобы создать notifier, нужен `Bot`. Сделали `bot` опциональным kwarg-ом `build_container`-а: tests могут вызывать без него (notifier остаётся `None`, scheduler работает без нотификации); production `run()` создаёт сначала Settings → Bot → передаёт его в build_container. Обратная совместимость сохранена для всех существующих тестов.

---

## 2026-05-04 — Спринт 1.3.C: `FinishForestRun` + APScheduler-job + титул «Новичок»

**Автор:** Devin (по запросу sandyemaroon)
**Тип:** feature (application + infra adapter + DI)
**Связано:** Текущий PR (Спринт 1.3.C), [development_plan.md §3 / Спринт 1.3, задачи 1.3.3 / 1.3.7 / 1.3.8](development_plan.md), [current_tasks.md Спринт 1.3 → 1.3.C](current_tasks.md). Продолжает Спринт 1.3 после смерженного 1.3.B (PR #18).

Узкий PR: завершение похода в лес (применение исхода + автовыдача титула «Новичок» + auto-apply имени), плюс `IDelayedJobScheduler` порт и его APScheduler-адаптер. Bot-handler `/forest` и inline-кнопки «Надеть/Выбросить» / «Заменить/Выбросить» остаются на 1.3.D.

Что сделано:
- **Domain** — добавлен порт `IDelayedJobScheduler` (`schedule_finish_forest_run` + `cancel_finish_forest_run`, оба идемпотентны), ошибка `ForestRunNotFoundError(run_id)`, методы `IPlayerRepository.get_by_id` и `IForestRunRepository.get_by_id`. Реализации `SqlAlchemyPlayerRepository.get_by_id` / `SqlAlchemyForestRunRepository.get_by_id` отзеркалены `tests/fakes/`.
- **Application (`application/forest/finish_run.py`)** — use-case `FinishForestRun(uow, players, runs, locks, audit, clock)`:
  1. `runs.get_by_id(run_id)` → `ForestRunNotFoundError` если запись отсутствует.
  2. `players.get_by_id(run.player_id)` → `PlayerNotFoundError` если ссылка «висит».
  3. Если `run.status is FINISHED` — идемпотентный no-op (`was_already_finished=True`).
  4. `player.with_length(...)` — `length += run.length_delta_cm` (всегда `>0`).
  5. Если `player.title is None` — выдать `Title.NEWBIE` (ПД §1.3.8 / ГДД §8.2 «первый успешный лес»). Идемпотентно по `player.title is None`.
  6. Если `run.drop is NameDrop` и `player.name is None` — auto-apply имя (ГДД §2.5).
  7. `runs.save(run.mark_finished(now))`, `locks.release(player, FOREST)`.
  8. Audit: `LENGTH_GRANT` всегда; `TITLE_GRANT` (`reason="first_forest_title"`) при `granted_title=True`; `NAME_GRANT` (`reason="forest_name_drop_auto_apply"`) при `granted_name=True`. `idempotency_key` строится по `forest_run_id`.
  9. Возвращает `ForestRunFinished(run, player_before, player_after, granted_title, granted_name, was_already_finished)`.
- **Application (`StartForestRun`)** — теперь принимает `IDelayedJobScheduler` и после `runs.add(...)` вызывает `scheduler.schedule_finish_forest_run(run_id, run_at=run.ends_at)`. Идемпотентно (`replace_existing=True` на адаптере); если бот рестартнётся — повторный `start` перезапишет job-у.
- **Infrastructure (`infrastructure/scheduler/aps.py`)** — `APSchedulerDelayedJobScheduler` поверх `AsyncIOScheduler`. `schedule_*` использует `replace_existing=True` и `misfire_grace_time=None` (job стрельнёт даже если бот пропустил `run_at`). `cancel_*` — best-effort (поглощает `JobLookupError`). Lifecycle: `start()` / `shutdown(wait=False)` идемпотентны. Callback `_run_finish_job` через `finish_factory: Callable[[], FinishForestRun]` (свежая ссылка на use-case) — поглощает `ForestRunNotFoundError` / `PlayerNotFoundError` (с `logger.warning`) и любую другую ошибку (с `logger.exception`), чтобы APScheduler не пометил job-у «failed» и не оставил её в job-store-е.
- **Composition root (`bot/main.py::build_container`)** — зарегистрированы `IDelayedJobScheduler` (реальный `APSchedulerDelayedJobScheduler` с `AsyncIOScheduler()`) и `FinishForestRun`. `StartForestRun` теперь получает scheduler. В `run()` вызывается `scheduler.start()` после `build_container` и `scheduler.shutdown(wait=False)` в `finally`-блоке.
- **Тесты** (всего +47 кейсов, общее количество 666, покрытие 96.65 %):
  - `tests/unit/domain/forest/test_errors.py` — `AlreadyInForestError` / `ForestRunNotFoundError` (наследование от `ForestError`, payload).
  - `tests/fakes/delayed_job_scheduler.py` (`FakeDelayedJobScheduler`) + `tests/unit/fakes/test_delayed_job_scheduler.py` — 4 кейса (schedule, overwrite, cancel, missing).
  - `tests/unit/application/forest/test_finish_run.py` — 9 кейсов: happy path с грантом титула, идемпотентность на уже-`FINISHED`, не-перевыдача титула, auto-apply имени, не-перетирание имени, `ItemDrop` без auto-apply имени, `ForestRunNotFoundError`, `PlayerNotFoundError`, проверка rollback UoW.
  - `tests/unit/application/forest/test_start_run.py` — обновлены все 8 тестов (новый параметр `scheduler`); добавлена проверка, что `scheduler.scheduled[run.id].run_at == run.ends_at`.
  - `tests/unit/infrastructure/scheduler/test_aps.py` — 10 кейсов: schedule добавляет job-у, schedule перезаписывает, cancel удаляет, cancel-missing — no-op, lifecycle идемпотентен, callback вызывает use-case, callback поглощает `ForestRunNotFoundError` / `PlayerNotFoundError` / `RuntimeError`, дефолтный logger подхватывается.
  - `tests/integration/db/test_player_repository.py` / `test_forest_run_repository.py` — добавлены `get_by_id_returns_*` и `get_by_id_missing_returns_none`.
  - `tests/unit/bot/test_composition_root.py` — обновлён `_container_with_fakes()` (передача `delayed_jobs` и `finish_forest_run`); добавлены проверки, что в `Container` и в `build_dispatcher`-workflow-data зарегистрированы оба новых компонента, и в реальном контейнере `delayed_jobs is APSchedulerDelayedJobScheduler`.

Результат / артефакты:
- Domain / app / infra: `src/pipirik_wars/domain/shared/ports/scheduler.py`, `src/pipirik_wars/domain/forest/errors.py` (+`ForestRunNotFoundError`), `src/pipirik_wars/domain/forest/repositories.py` (`get_by_id`), `src/pipirik_wars/domain/player/repositories.py` (`get_by_id`), `src/pipirik_wars/application/forest/finish_run.py`, `src/pipirik_wars/application/forest/start_run.py` (планирование finish-job-а), `src/pipirik_wars/application/dto/inputs.py` (`FinishForestRunInput`), `src/pipirik_wars/infrastructure/scheduler/aps.py`, `src/pipirik_wars/infrastructure/db/repositories/forest_run.py` (`get_by_id`), `src/pipirik_wars/infrastructure/db/repositories/player.py` (`get_by_id`).
- DI: `src/pipirik_wars/bot/main.py` (Container + build_container + build_dispatcher + run-lifecycle).
- Тесты: `tests/fakes/delayed_job_scheduler.py`, `tests/unit/application/forest/test_finish_run.py`, `tests/unit/infrastructure/scheduler/test_aps.py`, `tests/unit/fakes/test_delayed_job_scheduler.py`, `tests/unit/domain/forest/test_errors.py` + обновления `test_start_run.py`, `test_composition_root.py`, `test_player_repository.py`, `test_forest_run_repository.py`.
- Зависимости: `apscheduler>=3.10,<4` в `pyproject.toml`; mypy-override `apscheduler.* → ignore_missing_imports`; `.pre-commit-config.yaml` обновлён на ту же версию.

Заметки / решения:
- **Idempotency at scheduler layer** — `schedule_finish_forest_run` использует `replace_existing=True`, поэтому `StartForestRun` может вызываться повторно (например, после рестарта бота с retry-логикой) без побочных эффектов на сторону scheduler-а. На стороне БД защищает partial unique-индекс из 1.3.B.
- **Idempotency at use-case layer** — `FinishForestRun` сам поглощает повторные вызовы на уже-`FINISHED`-записи (без mutations / audit). Это защищает от misfire / двойного scheduler-а / ручного re-run-а.
- **Title auto-grant** — выдаём `NEWBIE`, только если `player.title is None`. Если игрок уже носит другой титул (например, из админ-панели в будущих спринтах) — не перетираем.
- **Name auto-apply** — только если `player.name is None`. Иначе drop остаётся в очереди handler-а 1.3.D, который даст inline «Заменить / Выбросить» (как в ГДД §2.5).
- **`ItemDrop` не применяется автоматически** — handler 1.3.D даст «Надеть / Выбросить»; авто-надевание не делаем, чтобы игрок мог осознанно решать, что лучше.
- **APScheduler error-handling** — три уровня: (а) `_run_finish_job` ловит `ForestRunNotFoundError` / `PlayerNotFoundError` и логирует `warning` (это не ошибка системы, а ситуация «запись съели вручную из БД» / «игрок удалён» / «cancel + повторный schedule»); (б) catch-all `Exception` логирует `exception` (полный traceback); (в) APScheduler сам не падает, потому что callback ничего не пробрасывает наружу — job помечается «успешно завершённой» и удаляется из job-store-а.
- **`finish_factory: Callable[[], FinishForestRun]`** — ленивая фабрика, чтобы можно было поменять реализацию use-case-а без переинициализации scheduler-а; в production используется `lambda: container.finish_forest_run`.
- **Зачем `IPlayerRepository.get_by_id`?** — `forest_runs.player_id` хранит внутренний `players.id`, а не `tg_id`. До 1.3.C use-case-ы леса работали только со старт-точкой (где есть `Player`), а в `FinishForestRun` есть только `run.player_id`. Поэтому добавили парный метод (фейк, ORM-репозиторий, integration-тесты).
- **Покрытие** — `make ci` локально: 666 тестов, 96.65 % (`fail_under=80 %`), все слои pre-commit-чисты (ruff/black/mypy/import-linter).

---

## 2026-05-04 — Спринт 1.3.B: persistence леса + use-case `StartForestRun`

**Автор:** Devin (по запросу sandyemaroon)
**Тип:** feature (persistence + application + infra DI)
**Связано:** Текущий PR (Спринт 1.3.B), [development_plan.md §3 / Спринт 1.3, задача 1.3.9](development_plan.md), [current_tasks.md Спринт 1.3 → 1.3.B](current_tasks.md). Продолжает Спринт 1.3 после смерженного 1.3.A (PR #17).

Узкий PR: persistence-слой леса + один use-case `StartForestRun`. Активная запись охраняется и `ActivityLockService` (in-memory защита от двойного `/forest`), и DB partial unique-индексом (last-line-of-defense на случай ручных SQL / миграций мимо доменного слоя). Bot-handler и `FinishForestRun` остаются на 1.3.D / 1.3.C.

Что сделано:
- **Domain (`domain/forest/`)** — добавлены `ForestRun` (frozen-dataclass со статусом `IN_PROGRESS / FINISHED`, фабрикой `starting()` и идемпотентным `mark_finished()`), `IForestRunRepository` (`add` / `get_active_by_player` / `save`) и `AlreadyInForestError(player_id)`. Инвариант `ends_at > started_at` охраняется в `starting()`.
- **Application (`application/forest/start_run.py`)** — use-case `StartForestRun(uow, players, runs, locks, balance, random, audit, clock)`:
  1. `players.get_by_tg_id(...)` → `PlayerNotFoundError` если нет.
  2. `random.randint(forest.cooldown_min_minutes, forest.cooldown_max_minutes)` → `cooldown_minutes`.
  3. `locks.acquire(actor_kind="player", actor_id=player.id, reason=FOREST, ttl=cooldown)` → `AlreadyInForestError` при `LockAlreadyHeldError`.
  4. `compute_forest_outcome(balance, random)` → `ForestRunOutcome`.
  5. `runs.add(ForestRun.starting(...))` → запись `IN_PROGRESS`.
  6. `audit.record(FOREST_RUN_STARTED, before=None, after={player_id, branch_name, length_delta_cm, drop_kind, cooldown_minutes, ends_at})`.
  7. Возвращает `ForestRunStarted(run, cooldown_minutes)`.
- **Infrastructure (`infrastructure/db/`)** — миграция `0004_forest_runs` (таблица `forest_runs` + 6 CHECK-constraint-ов на статусы / payload / временные интервалы + два index-а + partial unique `(player_id) WHERE status='in_progress'`); `ForestRunORM` с теми же CHECK-ами на ORM-уровне; `SqlAlchemyForestRunRepository` (`add` / `get_active_by_player` / `save`, сериализация `Drop` ADT в три колонки `drop_kind` / `drop_item_id` / `drop_name`; восстановление `Item` из текущего `IBalanceConfig`).
- **Composition root (`bot/main.py::build_container`)** — зарегистрированы `IActivityLockRepository`, `IForestRunRepository` и `StartForestRun` (в `Container` + `build_dispatcher` workflow-data). Use-case готов к подключению `/forest` handler-а в 1.3.D.
- **Тесты** — все четыре уровня покрытия:
  - `tests/unit/domain/forest/test_run.py` — 9 кейсов на `ForestRun.starting()` (статусы, копирование outcome, инвариант `ends_at > started_at`) и `mark_finished()` (идемпотентность, иммутабельность).
  - `tests/fakes/forest_run_repo.py` (`FakeForestRunRepository`) и `tests/fakes/lock_repo.py` (`FakeActivityLockRepository`) — общие in-memory фейки.
  - `tests/unit/application/forest/test_start_run.py` — happy path, audit-payload, `AlreadyInForestError`, `PlayerNotFoundError`, детерминизм при фиксированном seed.
  - `tests/integration/db/test_forest_run_repository.py` — 8 кейсов на real-SQLAlchemy + aiosqlite: serial id, partial unique, post-finish добавление новой активной записи, round-trip всех трёх вариантов `Drop` (`NoDrop` / `ItemDrop` / `NameDrop`).
  - `tests/integration/db/test_migrations.py` — добавлены `0004_forest_runs` к smoke-тестам (revisions, descend chain, files, expected tables).

Результат / артефакты:
- Domain / app / infra: `src/pipirik_wars/domain/forest/run.py`, `src/pipirik_wars/domain/forest/repositories.py`, `src/pipirik_wars/domain/forest/errors.py`, `src/pipirik_wars/application/forest/start_run.py`, `src/pipirik_wars/infrastructure/db/models/forest.py`, `src/pipirik_wars/infrastructure/db/repositories/forest_run.py`, `src/pipirik_wars/infrastructure/db/migrations/versions/20260504_0004_forest_runs.py`.
- DI: `src/pipirik_wars/bot/main.py` (Container + build_container + build_dispatcher).
- Тесты: `tests/unit/domain/forest/test_run.py`, `tests/unit/application/forest/test_start_run.py`, `tests/integration/db/test_forest_run_repository.py`, `tests/integration/db/test_migrations.py`, `tests/fakes/forest_run_repo.py`, `tests/fakes/lock_repo.py`, `tests/unit/bot/test_composition_root.py` (расширен).
- Доки: запись здесь + текущая задача 1.3.B → 🟢 PR open в `current_tasks.md`.

Заметки / решения:
- Двухуровневая защита от двойного `/forest`: `ActivityLockService` (короткий TTL = cooldown) — основной путь, partial unique-индекс `(player_id) WHERE status='in_progress'` — last-line-of-defense на случай прямого SQL / миграций. Это объясняет, почему integration-тест `test_partial_unique_blocks_second_active_run` обходит ActivityLock (он не задействован в репозитории напрямую).
- Сериализация `Drop` в три колонки (`drop_kind` / `drop_item_id` / `drop_name`) выбрана вместо JSONB по двум причинам: (а) каждая колонка проверяется CHECK-constraint-ами; (б) при `FinishForestRun` (1.3.C) нужно сделать FK-проверку `drop_item_id` против текущего `items_catalog` — JSONB здесь скрыл бы инвариант.
- `ForestRun.mark_finished()` идемпотентен (повторный вызов на уже финишированной записи возвращает `self`). Это упрощает APScheduler-job из 1.3.C: при перезапуске воркера джоб может дёрнуть `mark_finished` повторно — никаких двойных side-эффектов.
- Локально: `make ci` (lint / typecheck / imports / pytest --cov) — 637 тестов, покрытие **97 %** (≥80 % требование `pyproject.toml`).

---

## 2026-05-04 — Спринт 1.3.A: `balance.yaml` + `domain/forest/` (фундамент леса)

**Автор:** Devin (по запросу birgit865)
**Тип:** feature (balance + domain)
**Связано:** Текущий PR (Спринт 1.3.A), [development_plan.md §3 / Спринт 1.3, задачи 1.3.4 + 1.3.5](development_plan.md), [current_tasks.md Спринт 1.3 → 1.3.A](current_tasks.md). Открывает Спринт 1.3 после закрытого 1.2 (PR #13/14/15/16).

Узкий PR: только конфиг и чистый домен леса, без bot / persistence / use-case-ов. Шмот, имена и расчёт исхода теперь живут в одном месте, и любая последующая работа (1.3.B/C/D) ставит свою бизнес-логику поверх уже валидированных каталогов и детерминированной чистой функции.

Что сделано:
- **`config/balance.yaml`** — `version: 3`.
  - `forest.drop`: `probability_percent: 50` (общий шанс любого дропа), `name_share_percent: 5` (внутри дропов — доля имён vs предметов; ГДД §2.5 — единственный путь получить имя), `rarity_weights: {common: 70, rare: 25, epic: 5}` (ГДД §1.3.5).
  - `items_catalog`: 30 предметов на 6 слотов (`hat / body / legs / boots / ring / chain`), у каждого `id` (стабильный, формата `item.<slot>.<short>`) / `slot` / `display_name` / `rarity` (ГДД §2.6, тематика — «майка-алкоголичка», «лапти скорохода», «голда с рынка», и т. п.).
  - `names_catalog`: 32 имени из ГДД §2.5 (Колян, Толик, Жорик, Эдгар, Бананчик-Коляндр, …) — все уникальные, без редкости.
- **`domain/balance/config.py`** — расширили pydantic-схему.
  - Новые типы (StrEnum): `Slot` (6 значений) и `Rarity` (3 значения). Живут именно здесь, потому что ими типизирован сам каталог; `domain/forest/entities.py` реэкспортирует их для коротких импортов.
  - `ForestRarityWeights` — `common / rare / epic > 0`, все три обязательны (иначе rarity-roll получил бы недостижимую ветку).
  - `ForestDropConfig` — `probability_percent ∈ [0, 100]`, `name_share_percent ∈ [0, 100]`, `rarity_weights: ForestRarityWeights`. 0 % — валидное состояние «лес временно без дропа» под админ-панель.
  - `ForestConfig.drop: ForestDropConfig` — обязательное поле.
  - `ItemEntry` — frozen pydantic-модель (`id 1..64` non-empty, `slot: Slot`, `display_name 1..64`, `rarity: Rarity`).
  - `BalanceConfig.items_catalog: tuple[ItemEntry, ...]` (`min_length=30`) + `BalanceConfig.names_catalog: tuple[str, ...]` (`min_length=30`).
  - Два новых валидатора `BalanceConfig`: ID предметов уникальны + каждая редкость покрыта ≥ 1 предметом; имена — non-empty, не whitespace-only, уникальны.
- **`domain/forest/`** (новый пакет) — чистая модель леса (ГДД §8.2, §1.3.4-§1.3.5).
  - `entities.py`: реэкспорт `Slot` / `Rarity`; frozen-dataclass-ы `Item` / `Name` / `OutcomeBranch`. ADT `Drop = NoDrop | ItemDrop | NameDrop` (`NoDrop` — пустой dataclass для pattern-match). Корневой результат — `ForestRunOutcome(branch, length_cm, drop)`.
  - `errors.py`: пустой пока `ForestError` для будущих use-case-ных ошибок (1.3.B/C).
  - `services.py::compute_forest_outcome(*, balance, random)` — ровно один публичный API. Алгоритм:
    1. `random.weighted_choice([0..n-1], [outcome.weight])` → ветка.
    2. `random.randint(branch.min, branch.max)` → длина.
    3. `random.randint(1, 100) > probability_percent` → `NoDrop`. Иначе — `random.randint(1, 100) <= name_share_percent` → имя (`random.choice(names_catalog)`), иначе — предмет: `weighted_choice` по rarity_weights → `random.choice(pool)` среди предметов выбранной редкости.
  - Все 5 шагов идут через инжектируемый `IRandom` — никаких прямых обращений к `random.*`. Side-эффектов нет.
- **`tests/`** — 35 новых тестов.
  - `tests/unit/domain/balance/test_config.py`: 19 новых кейсов на `ForestRarityWeights` / `ForestDropConfig` / `ItemEntry` / items_catalog (size, duplicate ids, missing rarity) / names_catalog (size, empty, whitespace, duplicate). Все существующие forest-кейсы дополнены валидным `_VALID_DROP_PAYLOAD`.
  - `tests/unit/domain/forest/test_entities.py`: 8 кейсов на frozen-инвариант + полное покрытие pattern-match по ADT `Drop`.
  - `tests/unit/domain/forest/test_services.py`: 11 кейсов на `compute_forest_outcome`. Использует локальный `ScriptedRandom` (FIFO-очереди по каждому методу `IRandom`) для покапилярных проверок — какая ветка / длина / дроп. Стресс-сэмплинг 5 000 прогонов на `FakeRandom(seed=12345)` проверяет инварианты (длина в `[branch.min, branch.max]`, item.id принадлежит каталогу, name — каталогу). Smoke на реальном `config/balance.yaml` отдельным тестом.
  - `tests/unit/domain/balance/factories.py::valid_balance_payload` — теперь генерирует валидный 30-предметный каталог (5 на каждый слот, по паттерну `common/common/rare/rare/epic` = 12/12/6) и `[ИмяТест-01..30]`.

Результат / артефакты:
- `config/balance.yaml` (расширен на ~120 строк).
- `src/pipirik_wars/domain/forest/` (4 файла, ~150 LoC чистого домена).
- `src/pipirik_wars/domain/balance/config.py` (+ Slot/Rarity/ItemEntry/ForestDropConfig/ForestRarityWeights + 2 model_validator).
- `src/pipirik_wars/domain/balance/__init__.py` — обновлён публичный экспорт.
- `tests/unit/domain/balance/test_config.py` + `tests/unit/domain/balance/factories.py` — обновлены под новый schema.
- `tests/unit/domain/forest/test_entities.py` + `tests/unit/domain/forest/test_services.py` — новые.
- Локальный `make ci`: lint / typecheck / imports / 610 тестов, покрытие **97.52 %**.

Заметки / решения:
- **Slot/Rarity в `domain/balance/config.py`, а не в `domain/forest/`**. Изначально хотелось хранить их рядом с forest-сущностями, но `domain/balance/config.py` импортирует их в `ItemEntry`, а `domain/forest/services.py` импортирует `BalanceConfig` — получался цикл. Перенос Slot/Rarity в balance/config.py — правильный также архитектурно: ими типизирован сам каталог. `domain/forest/entities.py` реэкспортирует их для удобного `from pipirik_wars.domain.forest import Slot`.
- **`probability_percent`, а не `probability` (float)**. Целое число `[0, 100]` устойчивее к 0-tolerance багам с 0.01 при правках админ-панелью + удобнее раздавать пользователям («50 %», «5 %»).
- **`ScriptedRandom`, а не `MagicMock(side_effect=...)`**. FIFO-очереди по каждому методу `IRandom` дают тесту явный список значений: видно, что именно проверяется, и при добавлении нового `randint` в `compute_forest_outcome` ScriptedRandom падает с осмысленным `IndexError`/`AssertionError`, а не молчаливо подставляет `None`.
- **Никаких side-эффектов в `compute_forest_outcome`** — это домен. Применение исхода (запись в `forest_runs`, начисление длины, добавление в инвентарь, смена имени, аудит) уйдёт в `application/forest/finish_run.py` в Спринте 1.3.C. Так удержим domain покрытым 100 % unit-тестами без БД.
- **`NoDrop` — пустой frozen-dataclass, а не `None`**. Pattern-match на `Drop = NoDrop | ItemDrop | NameDrop` короче и устойчивее к будущему расширению (например, гипотетический `BonusDrop` для горы — без ломки сигнатур).
- **Поле `branch.length_cm` дублирует `ForestRunOutcome.length_cm`** — намеренно. У ветки в проде будет своя «история» (для аудита: какой именно был broadcasted к игроку диапазон). Сейчас это просто синоним, но, чтобы не переписывать сигнатуры в 1.3.C, оставили оба.
- **Покрытие на 30 предметов / 30 имён** — это нижний порог из ПД. Реальный YAML уже идёт с 30 предметами и 32 именами, чтобы было пространство добавить пару тематических без правки тестов.

---

## 2026-05-04 — Спринт 1.2.D: алёрт админу при достижении 80 % от `MAX_DAU`

**Автор:** Devin (по запросу birgit865)
**Тип:** feature (domain + application + infrastructure)
**Связано:** Текущий PR (Спринт 1.2.D), [development_plan.md §3 / Спринт 1.2, задача 1.2.7](development_plan.md), [current_tasks.md Спринт 1.2 → 1.2.D](current_tasks.md), завершает Спринт 1.2 после PR #13/14/15.

Финальный PR Спринта 1.2 — алёртинг по DAU. Когда суммарный DAU дошёл до 80 % от `MAX_DAU`, system один раз в сутки пишет audit-запись и structlog-warning, чтобы у админов было время заранее повысить лимит/докинуть мощности до того, как игроки начнут попадать в очередь регистраций.

Что сделано:
- **`domain/dau/`** — добавлен новый порт.
  - `ports.py::IDauThresholdAlerter` — абстрактный эмиттер алёрта (`emit(*, current_dau, max_dau, percent, occurred_at)`). Идемпотентность «1 раз в сутки» в порт **не** заложена: его задача — отправить событие. За «слать или нет» отвечает use-case через `IIdempotencyKey`. Это даст потом без правки `CheckDauThreshold` подключить второй адаптер (например, Telegram-уведомление админам или Slack) и собрать `CompositeDauThresholdAlerter`.
  - `shared/ports/audit.py::AuditAction.DAU_THRESHOLD_REACHED` — новое значение, чтобы фильтровать алёрты в audit-логе.
- **`infrastructure/dau/alert.py::StructlogDauThresholdAlerter`** — реализация поверх `structlog.get_logger("pipirik_wars.dau.threshold").warning("dau.threshold.reached", ...)`. Полей четыре: `current_dau`, `max_dau`, `percent`, `occurred_at` (ISO-строка). Stdout/JSON-формат настраивается на уровне приложения (в `bot/main.py` уже сконфигурирован).
- **`application/dau/check_threshold.py::CheckDauThreshold`** — новый use-case (use-case-name выбран синхронным с остальной кодовой базой).
  - Константы: `DAU_THRESHOLD_PERCENT = 80`, `DAU_THRESHOLD_NAMESPACE = "dau_threshold_alert"`.
  - Проверка порога — целочисленная: `5 * current >= 4 * max_dau` (без float-погрешностей; для `max_dau = 1` алёрт сработает на первом игроке, что соответствует семантике «80 % исчерпано»).
  - Алгоритм: `current = dau_counter.current()` → если ниже порога → `triggered=False` без транзакции. Иначе строится idempotency-ключ `dau_threshold_alert:{moscow_date}`, открывается UoW, проверяется `idempotency.is_seen(key)` — если уже видели сегодня, `triggered=False`. Иначе `idempotency.mark(key)` + `audit.write(AuditAction.DAU_THRESHOLD_REACHED, target_kind="dau", target_id=moscow_date.isoformat(), after={current_dau, max_dau, percent}, idempotency_key=key)` → коммит → **после коммита** `alerter.emit(...)`. Эмит вне транзакции, чтобы откат не оставлял после себя «висячих» алёртов.
  - Дата привязана к `clock.moscow_date()` — той же, что использует `IDauCounter` для ежедневного сброса.
- **Точки вызова** — `CheckDauThreshold.execute()` дёргается **после** `dau_counter.record_active(...)`:
  - `application/player/register.py::RegisterPlayer` — после успешной регистрации (только в активной ветке, не в `PlayerQueued`).
  - `application/signup_queue/promote.py::PromoteFromQueue` — после loop-а промоута, если хоть кто-то поднят (`if promoted: await check_threshold.execute()`).
- **`bot/main.py::Container`** — расширен `dau_threshold_alerter: IDauThresholdAlerter` и `check_dau_threshold: CheckDauThreshold`. В `build_container()` алертер собирается до прочих use-case-ов, чтобы прокинуть его в `RegisterPlayer` и `PromoteFromQueue`.
- **`tests/fakes/dau.py`** — `FakeDauThresholdAlerter` (накапливает `events: list[DauAlertEvent]`).

Тесты (новые):
- **Application (19)**: `_is_threshold_reached` — таблица из 11 параметризованных кейсов (включая граничные `4/5`, `4/6`, `5/6`, `1/1`); `CheckDauThreshold` — ниже порога (без транзакции и аудита), первое пересечение (audit + commit + alerter), второй вызов того же дня (no-op, но UoW открывается на `is_seen`), переход через сутки (новый ключ → новый алёрт), `MAX=1` (алёрт на первом игроке), pre-seeded ключ (idempotency пропускает алёрт), `current > max_dau` (overshoot — алёрт всё равно ровно один).
- **Application — `RegisterPlayer` (4 новых)**: алёрт после регистрации, пересекающей 80 %; нет алёрта при низкой загрузке; нет алёрта, когда игрок ушёл в очередь; ровно 1 алёрт за сутки даже при подряд идущих регистрациях после порога.
- **Application — `PromoteFromQueue` (3 новых)**: алёрт срабатывает, когда промоут довёл DAU до ≥ 80 %; без промоута alerter не зовётся; при низкой загрузке нет алёрта.
- **Infrastructure (2)**: `StructlogDauThresholdAlerter` — `structlog.testing.LogCapture` ловит warning-событие со всеми полями; default-logger используется при отсутствии явного.
- **Composition root**: добавлены проверки на `dau_threshold_alerter`/`check_dau_threshold` в обеих вариантах (фейковый Container и `build_container()` с реальным `StructlogDauThresholdAlerter`).
- Все существующие тесты `RegisterPlayer` / `PromoteFromQueue` / `JoinClan` / composition-root приведены к новой сигнатуре конструкторов (через общий `_build`-helper, использующий `FakeDauThresholdAlerter`).

Контракты `import-linter` не нарушены: `application` не импортирует `structlog`, доступ к нему — только через `IDauThresholdAlerter`.

CI: `make ci` локально проходит — ruff (lint+format), mypy --strict, pytest с покрытием 97.40 % (565 тестов), import-linter (3/3 контракта), pip-audit отдельным шагом в CI workflow.

---

## 2026-05-04 — Спринт 1.2.C: `signup_queue` + DAU Gate в `RegisterPlayer` + auto-promote

**Автор:** Devin (по запросу birgit865)
**Тип:** feature (domain + application + infrastructure + bot)
**Связано:** Текущий PR (Спринт 1.2.C), [development_plan.md §3 / Спринт 1.2, задачи 1.2.4 / 1.2.5](development_plan.md), [current_tasks.md Спринт 1.2 → 1.2.C](current_tasks.md), предшествуют — PR #13 (1.2.A) и PR #14 (1.2.B).

Третий PR Спринта 1.2 — закрытие FIFO-очереди регистраций для случая «DAU достиг MAX_DAU». До этого PR попытка `/start` при заполненном лимите просто возвращала ошибку; теперь игрок ставится в очередь, а при повышении `MAX_DAU` через `/set_max_dau` система сама поднимает первых из очереди обратно в активные.

Что сделано:
- **`domain/signup_queue/`** — новый под-домен.
  - `entities.py::SignupQueueEntry` — frozen+slots dataclass (`id`, `tg_id`, `username`, `locale`, `position`, `enqueued_at`).
  - `entities.py::SignupQueueStatus` — `WAITING` / `PROMOTED` (на текущий момент колонкой не сохраняется, оставлен для будущих расширений).
  - `errors.py::SignupQueueError` (база) + `AlreadyQueuedError(tg_id=...)` (наследник `DomainError`).
  - `ports.py::ISignupQueueRepository` — 4 метода: `enqueue` (бросает `AlreadyQueuedError` на дубль), `get_by_tg_id`, `size`, `pop_front(limit)`.
- **`infrastructure/db/`** — реализация порта.
  - Новая alembic-миграция `0003_signup_queue` — таблица `signup_queue` (BIGINT autoincrement `id`, UNIQUE `tg_id`, индекс на `enqueued_at`, поля `username VARCHAR(32)`, `locale VARCHAR(16)`).
  - `infrastructure/db/models/signup_queue.py::SignupQueueORM` — ORM в едином стиле с другими (`Base.metadata`, `Mapped[…]`, `_AutoIncBigInt` для портабельности SQLite ↔ Postgres).
  - `infrastructure/db/repositories/signup_queue.py::SqlAlchemySignupQueueRepository` — реализация. Ключевые решения:
    - `position` **не хранится в таблице**: считается «на лету» (`COUNT(*) WHERE enqueued_at < x` + tie-break `tg_id < y`), чтобы избежать O(N)-обновлений при `pop_front`. Это держит таблицу маленькой и не плодит конкурирующие UPDATE-ы.
    - `enqueue` ловит `IntegrityError` от UNIQUE-нарушения и преобразует в доменный `AlreadyQueuedError` — слой выше не знает про SQL.
    - `pop_front(limit)` — ORDER BY `enqueued_at, id` + DELETE WHERE `id IN (...)` за одну операцию.
- **`application/signup_queue/`** — use-case для авто-разблокировки.
  - `application/signup_queue/promote.py::PromoteFromQueue` — поднимает первых из очереди на освободившиеся места: `slots = max(0, MAX_DAU - DAU)` → `pop_front(limit=slots)` → для каждого вызывает `players.add(...)` (с обработкой `PlayerAlreadyRegisteredError` → `skipped_already_registered`) → пишет audit-запись `PLAYER_PROMOTED` с `idempotency_key="promote_player:{tg_id}"` и `before={'queued_at', 'queued_position'}` → вне транзакции вызывает `dau_counter.record_active(...)`.
  - DTO `PromoteFromQueueResult` (`promoted: tuple[Player, ...]`, `skipped_already_registered: tuple[int, ...]`, `available_slots: int`).
- **`application/player/register.py::RegisterPlayer`** — расширен DAU-гейтом.
  - Перед добавлением игрока проверяет `current_dau >= max_dau`. Если да — ставит в `signup_queue` и возвращает `PlayerQueued(entry=...)`. Если нет — обычная ветка с `PlayerRegistered(player=...)`. Тип результата — union `PlayerRegistered | PlayerQueued`.
  - Ошибка `AlreadyQueuedError` пробрасывается наружу (handler покажет дружелюбное сообщение).
  - `idempotency_key` для запроса в очередь — `queue_player:{tg_id}`.
- **`bot/handlers/admin.py`** — два изменения.
  - `handle_admin_stats` теперь принимает `signup_queue: ISignupQueueRepository` и в ответе показывает `«Очередь регистраций: N»`.
  - `handle_set_max_dau` теперь принимает `promote_from_queue: PromoteFromQueue`. После успешного `set_max_dau.execute(...)` он вызывает `promote_from_queue.execute()` **только** если `result.changed and result.new_max_dau > result.previous_max_dau` (повышение). При понижении или равенстве промоут не запускается. Если кто-то поднят — в ответе появляется строка `«↑ Из очереди поднято: N»`.
- **`bot/main.py::Container`** — расширен `signup_queue: ISignupQueueRepository` и `promote_from_queue: PromoteFromQueue`. В `build_container()`: `signup_queue = SqlAlchemySignupQueueRepository(uow)`, `promote_from_queue` собирается из uow + players + signup_queue + dau_counter + dau_limit + audit + clock. В `build_dispatcher()`: workflow-data DI обоих в роутер.
- **`tests/fakes/signup_queue.py::FakeSignupQueueRepository`** — in-memory FIFO с автонумерацией `id` и пересчётом `position` при `pop_front`.

Тесты (новые):
- **Domain (12)**: `SignupQueueEntry` — frozen, slots, optional-поля, эквивалентность; `AlreadyQueuedError` — наследование, `tg_id`, формат `str()`.
- **Application `PromoteFromQueue` (9)**: пустая очередь / нулевые слоты, частичный/полный slot range, audit-записи с idempotency-ключами `promote_player:*`, `before` содержит `queued_position`, propagate `PlayerAlreadyRegisteredError` в `skipped_already_registered`, корректный rollback uow при неожиданной ошибке репо.
- **Integration `SqlAlchemySignupQueueRepository` (11)**: enqueue → id + position=1, последовательные позиции, AlreadyQueuedError, защита от pre-set id, get_by_tg_id с актуальной позицией, size, pop_front(0/-N) — no-op, FIFO ordering, drain, повторная постановка после pop_front, tie-break по `tg_id` при равном `enqueued_at`.
- **Bot handler `test_admin.py`**: добавлен тест-кейс для отображения непустой очереди в `/admin_stats`; для `/set_max_dau` — три новых кейса (нулевая очередь → промоут вызывается, но строки нет; повышение с непустой очередью → строка «↑ Из очереди поднято: N»; понижение → промоут НЕ вызывается).
- **Migrations**: новый тест `test_0003_descends_from_0002` + `signup_queue` добавлен в expected-таблицы и в whitelist файлов миграций.

Результат:
- Полный `make ci` зелёный (lint + format + mypy --strict + import-linter + 537 тестов с покрытием 97.35 %).
- DAU Gate работает в полном цикле: переполнение → постановка в очередь → `/admin_stats` показывает текущую очередь → админ повышает `MAX_DAU` → автопромоут первых N в активные игроки.

Заметки / решения:
- **Почему не storage-side `position`:** хранение `position` колонкой требовало бы O(N) UPDATE при каждом `pop_front`. Поскольку запросы «сколько передо мной» относительно редки (только в ответе пользователю «вы №X»), дешевле считать через `COUNT(*)`.
- **Почему промоут только при повышении:** понижение `MAX_DAU` — административное «закрытие двери», очередь должна оставаться нетронутой, а текущие игроки — продолжать играть. Равенство — no-op.
- **Tie-break в `_position_of`:** при одинаковом `enqueued_at` (теоретически возможно при «массовом наплыве в одну миллисекунду») мы добиваем порядок сравнением по `tg_id`, чтобы исключить коллизию «два первых места».

---

## 2026-05-04 — Спринт 1.1.E: `/profile` + `/balance_reload`

**Автор:** Devin (по запросу jorey7467)
**Тип:** feature (domain + application + bot)
**Связано:** PR #12, [development_plan.md §3 / Спринт 1.1, задачи 1.1.8 / 1.1.9](development_plan.md), [current_tasks.md Спринт 1.1 → 1.1.E](current_tasks.md), предшествуют — PR #8/#9/#10/#11 (1.1.A–D).

Финальный PR серии Спринта 1.1: закрывает «карточку игрока» (read-side) и инструмент геймдиза «hot-reload `display_names`» (write-side). После этого PR Спринт 1.1 закрыт целиком — следующий заход (Спринт 1.2) уже про экономику и DAU Gate.

Что сделано:
- **`domain/balance/ports.py::IBalanceReloader`** — отдельный порт для `reload()` (по ISP отделён от `IBalanceConfig.get()`). `YamlBalanceLoader` теперь реализует **оба** интерфейса. В DI это один и тот же объект, но use-case-ам разрешено зависеть только от того подмножества capabilities, которое им реально нужно: `GetProfile` берёт только `IBalanceConfig`, `ReloadBalance` — оба.
- **`domain/shared/ports/audit.py::AuditAction.BALANCE_RELOAD`** — новый action для аудита `/balance_reload`.
- **`application/player/get_profile.py::GetProfile`** — use-case-обёртка вокруг `IPlayerRepository.get_by_tg_id(...)` + `IBalanceConfig.display_name_for(length_cm)`. Возвращает `ProfileView | None`. Транзакция читающая (commit без записи), `None` для незарегистрированного — handler сам решит, что показать.
- **`application/balance/reload.py::ReloadBalance`** — use-case с гейтом `Admin.can_write_balance()` (`super_admin` / `economist`). При отказе бросает `AuthorizationError` ДО вызова `reloader.reload()` — никаких side-эффектов на неавторизованных. Аудит `BALANCE_RELOAD` пишется только после успешного reload, с `before={'version': N}` / `after={'version': M}` и `idempotency_key="balance_reload:{tg_id}:{ts}"`.
- **`bot/presenters/profile.py`** — чистые функции `render_full_nick(...)` и `render_profile_card(...)`. Формат ника по ГДД §2.1 — «`Титул Название Имя`», `None`-поля просто пропускаются (новичок без титула/имени → ровно «Пипирик»). Карточка по §2.2: `🏷 ник` / `📏 длина` / `📐 толщина` / `🎽 экипировка` (последняя — пока заглушка «пока пусто», в Спринте 1.3 добавим реальные слоты). Локализация `Title` живёт в `_TITLE_RU` — добавление нового члена `Title` без правки маппинга роняет тест `test_only_known_titles_supported`.
- **`bot/handlers/profile.py::handle_profile`** — `/profile`. Только `chat_kind == "private"` → `GetProfile` → presenter. Группа/супергруппа → инструкция «зайди в ЛС». Канал/прочие → нейтральный fallback. Без `tg_identity` (теоретически невозможно) — тоже fallback.
- **`bot/handlers/admin.py::handle_balance_reload`** — `/balance_reload`. Только в private. Ловит `AuthorizationError` → `«⛔️ только админам»`, `ConfigError` → `«❌ некорректный YAML»`. Успех → `«✅ перечитан (v1 → v2)»` или `«✅ … версия не изменилась»`, если файл не правили.
- **`bot/main.py::Container`** — расширен 4 полями: `balance_reloader`, `admins`, `get_profile`, `reload_balance`. В `build_container()`: `admins = SqlAlchemyAdminRepository(uow)`, оба порта баланса инжектятся одним и тем же `YamlBalanceLoader`. В `build_dispatcher()`: workflow-data DI для двух новых use-case-ов.
- **`tests/fakes/admin_repo.py::FakeAdminRepository`** — in-memory `IAdminRepository` с `seed(...)` и `deactivate(...)` для удобного arrange. `FakeBalanceConfig` теперь реализует и `IBalanceConfig`, и `IBalanceReloader` — паритет с `YamlBalanceLoader` в production. Метод `queue_next_reload(snapshot)` позволяет имитировать «после reload-а — другой YAML».

Тесты (45 новых):
- **Presenter**: 8 кейсов (`render_full_nick` ×4 для всех сочетаний title/name + три инвариантных + один на `_TITLE_RU` coverage) + 3 на `render_profile_card`.
- **`GetProfile`**: 4 кейса — найден / не найден / полный игрок / hot-reload меняет название.
- **`ReloadBalance`**: 10 кейсов — авторизация (super_admin ✅, economist ✅, неизвестный ❌, support ❌, read_only ❌, деактивированный ❌) + reload (аудит-запись с версиями, без изменения версии, `ConfigError` пропагируется без аудита).
- **Handler `/profile`**: 6 кейсов — private+зарегистрирован (вызов use-case + правильный текст), private+не зарегистрирован, group, supergroup, channel, без identity.
- **Handler `/balance_reload`**: 6 кейсов — успех с версиями, успех без изменений, AuthorizationError → friendly text, ConfigError → friendly text, group → не вызывается use-case, без identity → не вызывается.
- **Integration на `YamlBalanceLoader`**: новый `test_display_name_for_same_length_changes_after_reload` — пишем YAML v1, читаем, меняем YAML на v2, `loader.reload()`, и проверяем `display_name_for(15)` = новое название. Старый снимок остаётся валидным (immutability).
- **Composition root**: расширены ассерты — все 4 новые поля Container присутствуют в обоих режимах (фейк и реальный), `c.balance_reloader is c.balance` (DI-инвариант), оба новых router-а (`profile`, `admin`) подключены, оба use-case-а в workflow-data.

Метрики:
- **411 тестов** (+45 к 1.1.D), **96.88 %** покрытия. Локальный `make ci` зелёный, GitHub Actions матрица 3.11/3.12 — зелёная.
- **27 файлов изменено**, +1608 / −27 строк.

Заметки / решения:
1. **ISP по `IBalanceConfig` / `IBalanceReloader`.** В production `YamlBalanceLoader` — один объект, реализующий обе capabilities. Но в use-case-ах **зависимость от `IBalanceReloader` — это уже capability «писать»**, и она нужна одному use-case (`ReloadBalance`). Все остальные (`GetProfile` сейчас, `ForestService` в 1.3, `OracleService` в 1.4) зависят только от read-side. Это позволяет в тестах «писательских» use-case-ов мокать reload отдельно, не тащась через файловую систему, и оставляет архитектурный signal: «hot-reload — административная операция, не часть нормального workflow».
2. **Authorization до reload.** Альтернатива «сначала reload, потом проверка прав» хуже: пробрасывает side-эффект в неуполномоченного актора. `ReloadBalance` сначала зовёт `IAdminRepository.get_by_tg_id(tg_id)` + `Admin.can_write_balance()`, и только при `True` вызывает `reloader.reload()`. Аудит — после reload (нет state change → нет записи).
3. **Презентер — чистые функции, не классы.** `bot/presenters/profile.py` намеренно без классов: ввод/выход явные, нет состояния, юнит-тестирование тривиальное (`assert render_X(...) == "..."`). Локализация `Title.NEWBIE → "Новичок"` хранится в module-level `_TITLE_RU` — когда добавится Title.SCOUT/SAGE/etc, тест `test_only_known_titles_supported` упадёт и напомнит локализовать.
4. **Карточка в Спринте 1.1.E без слотов экипировки.** ГДД §2.2 описывает 6 слотов экипировки, но самих предметов нет до Спринта 1.3 (дроп из леса). Поэтому секция «🎽 Экипировка» в карточке — стабильный заголовок и плейсхолдер «пока пусто». Это **не** TODO в коде — это намеренный stub, который заменится в 1.3.5 без изменения сигнатур handler/presenter.
5. **Hot-reload — атомарный.** `loader.reload()` сначала **полностью** парсит и валидирует новый YAML; только после успешной валидации меняет `_snapshot`. При `ConfigError` старый снимок сохраняется. Тест `test_invalid_yaml_propagates_config_error_no_audit` фиксирует это поведение.

---

## 2026-05-04 — Спринт 1.1.D: use-case-ы + handler-ы регистрации игрока и клана

**Автор:** Devin (по запросу 612amaranth)
**Тип:** feature (application + bot)
**Связано:** PR #11 (TBD), [development_plan.md §3 / Спринт 1.1, задачи 1.1.3 / 1.1.4 / 1.1.5 / 1.1.6](development_plan.md), [current_tasks.md Спринт 1.1 → 1.1.D](current_tasks.md), предшествуют — PR #8 (1.1.A domain), PR #9 (1.1.B db+repos), PR #10 (1.1.C aiogram).

Четвёртый PR серии Спринта 1.1: до этого `/start` отвечал в чате, но **никаких сущностей** в БД не создавал. Теперь handler-ы реально дёргают use-case-ы, а use-case-ы — пишут в БД и аудит. Это первый «живой» цикл пользовательских взаимодействий: «`/start` в ЛС → запись в `users`», «бота добавили в группу → запись в `clans`», «игрок зашёл в чат-клан → запись в `clan_members`».

Что сделано:
- **`application/player/register.py`** — `RegisterPlayer(uow, players, audit, clock).execute(input_dto)` — создаёт игрока со стартерами по ГДД §1.1 (`length=2cm`, `thickness=1`, `title=None`, `name=None`), пишет audit `PLAYER_REGISTER` с `idempotency_key="register_player:{tg_id}"`. Если игрок уже зарегистрирован — `PlayerAlreadyRegisteredError` пробрасывается дальше (handler ловит).
- **`application/clan/register.py`** — `RegisterClan` с тремя ветвями: `created` (новый клан + audit `CLAN_REGISTER`), `unfrozen` (бот вернулся в чат, который ранее замораживали — клан расконсервируется и audit `CLAN_UNFREEZE`), `already_active` (no-op без аудита, идемпотентно).
- **`application/clan/migrate.py`** — `MigrateClanChatId` для группы → супергруппы. Идемпотентен: `migrated` (есть старый id), `already_migrated` (старого нет, но новый — есть; либо вызвали с одинаковым id), `not_found` (бросает `ClanNotFoundError`). Сохраняет внутренний `id` клана при переходе.
- **`application/clan/join.py`** — `JoinClan` для чат-апдейтов. Три исхода: `joined` (новый членский запрос + audit `CLAN_MEMBER_JOIN`), `already_member` (no-op без аудита), `not_registered` (игрока нет в `users` — handler шлёт DM-инструкцию). Респектирует БД-инвариант UNIQUE(player_id) (один игрок ↔ один клан).
- **`application/clan/freeze.py`** — `FreezeClan` для бот-`left/kicked`. `frozen` (audit `CLAN_FREEZE` с `before/after`/`reason`), `already_frozen` (idempotent), `not_found` (тихо возвращает outcome — бот мог быть удалён до регистрации).
- **`bot/handlers/start.py`** — переписан под use-case `RegisterPlayer`. В ЛС зовёт `register_player.execute(...)`, ловит `PlayerAlreadyRegisteredError` → разные тексты «зарегистрированы»/«уже зарегистрированы». В группе/супергруппе — текст-инструкция «напишите в ЛС». Прочие типы — нейтральный fallback.
- **`bot/handlers/registration.py`** — три новых handler-а: `my_chat_member` (бот добавлен → `RegisterClan`; бот удалён → `FreezeClan`; пропускает private), `chat_member` (не-бот зашёл в группу/супергруппу → `JoinClan`; outcome=`not_registered` → `bot.send_message(chat_id=user.id, text=JOIN_NOT_REGISTERED_RU)`), `migrate_to_chat_id` на `Message`-апдейте (group→supergroup → `MigrateClanChatId`).
- **`bot/main.py`** — `Container` расширен 3 репозиториями (`players/clans/clan_members`) и 5 use-case-ами (`register_player/register_clan/migrate_clan/join_clan/freeze_clan`). `build_container()` инстанцирует SQLAlchemy-репо и use-case-ы. `build_dispatcher()` прокидывает все 5 use-case-ов в `dispatcher["..."]` — это аналог DI через aiogram workflow-data, handler-ы получают их по имени параметра.
- **`bot/main.py::run()`** — добавлен `_ALLOWED_UPDATES = ("message", "callback_query", "my_chat_member", "chat_member")` и передаётся в `start_polling(allowed_updates=...)`. По умолчанию aiogram **не** запрашивает `chat_member` — без явного списка JoinClan не будет триггериться.
- **`application/dto/inputs.py`** — добавлены `MigrateClanChatIdInput / JoinClanInput / FreezeClanInput`, в `RegisterClanInput` теперь обязательное поле `chat_kind: Literal["group", "supergroup"]`. Валидация через pydantic-strict (extra=forbid, нелитеральные значения отклоняются).
- **`domain/shared/ports/audit.py::AuditAction`** — добавлены 4 enum-а: `PLAYER_REGISTER`, `CLAN_REGISTER`, `CLAN_MIGRATE`, `CLAN_MEMBER_JOIN` (всё ещё в порядке возрастания «энтропии»: ADMIN_COMMAND по-прежнему последний).

Тесты:
- **Unit (use-cases, fakes)**: 16 новых тестов — `test_register_player.py`, `test_register_clan.py`, `test_migrate_clan.py`, `test_join_clan.py`, `test_freeze_clan.py`. Используют `FakeUnitOfWork / FakeAuditLogger / FakeClock` + новые `FakePlayerRepository / FakeClanRepository / FakeClanMembershipRepository`. Покрывают все исходы (created/unfrozen/already_active/migrated/already_migrated/joined/already_member/not_registered/frozen/already_frozen/not_found) + аудит-инварианты + ГДД §4 «один игрок — один клан».
- **Unit (handlers)**: 12 новых тестов — `test_registration.py`. Моки aiogram-апдейтов, проверка корректного маппинга на DTO-input-ы, ветвление по `chat_type`/`new_status`/`is_bot`. `test_start.py` переписан под новую сигнатуру (`register_player` вместо `_reply_text_for`).
- **Composition root**: тесты `test_composition_root.py` обновлены — Container теперь требует 8 новых полей, `build_dispatcher()` проверен на наличие 5 use-case-ов в workflow-data.
- **Итого:** 373 теста (было 341), покрытие 96.56%, все 3 import-linter-контракта на месте.

Результат / артефакты:
- Use-cases: `src/pipirik_wars/application/player/register.py`, `src/pipirik_wars/application/clan/{register,migrate,join,freeze}.py`.
- Handlers: `src/pipirik_wars/bot/handlers/{start,registration}.py`.
- Composition root: `src/pipirik_wars/bot/main.py`.
- DTO/audit: `src/pipirik_wars/application/dto/inputs.py`, `src/pipirik_wars/domain/shared/ports/audit.py`.
- Тесты: `tests/unit/application/{player,clan}/`, `tests/unit/bot/handlers/test_registration.py`.
- Fakes: `tests/fakes/{player_repo,clan_repo}.py`.

Заметки / решения:
- **Workflow-data DI**: использован idiom aiogram — `dispatcher["register_player"] = container.register_player`. aiogram автоматически прокидывает значение в handler по имени параметра (`async def handle_start(..., register_player: RegisterPlayer)`). Без глобального state, без factory-pattern на каждом апдейте.
- **`allowed_updates`**: явный список — критично. По умолчанию aiogram не подписан на `chat_member`, и `JoinClan` не сработал бы. Это был бы тихий баг, легко не заметить в QA.
- **Идемпотентность по умолчанию**: все 5 use-case-ов «толерантны» к повторам (созданный → no-op, удалённый → no-op-not-found, замороженный → no-op-already-frozen и т.д.). Это нужно для устойчивости в условиях «лагающих» апдейтов от Telegram-а и потенциальных ретраев.
- **БД-инвариант UNIQUE(player_id)**: `JoinClan` опирается на DB-уровень, fake-репозиторий тоже его моделирует, чтобы тесты ловили нарушение ГДД §4 раньше боевого CHECK-constraint-а.
- **Routers — singleton-ы**: `start_router` и `registration_router` создаются на уровне модуля и не могут быть переиспользованы между Dispatcher-ами. Поэтому в `test_composition_root.py` теперь только **один** тест с `build_dispatcher()` (раньше было 2).
- **Migration handler**: `migrate_to_chat_id` приходит **до** `my_chat_member` от Telegram-а при group→supergroup. Если поменять порядок — будет дубликат регистрации. Логика обрабатывает оба порядка через идемпотентные исходы.

---

## 2026-05-04 — Спринт 1.1.C: aiogram 3.x bootstrap (dispatcher + middleware-стек + `/start` stub)

**Автор:** Devin (по запросу 612amaranth)
**Тип:** feature (bot / scaffold)
**Связано:** PR #N (TBD), [development_plan.md §3 / Спринт 1.1, задача 1.1.1](development_plan.md), [current_tasks.md Спринт 1.1 → 1.1.C](current_tasks.md), предшествуют — PR #8 (1.1.A domain), PR #9 (1.1.B db+repos)

Третий PR серии Спринта 1.1: первый «живой» bot-слой. До этого `bot/main.py:main()` был `NotImplementedError`-stub-ом; теперь — реальный entry-point поллинга с aiogram 3.x, middleware-стеком и `/start`-handler-ом, отвечающим во всех трёх типах чатов (acceptance criteria 1.1.1).

Что сделано:
- **Зависимость:** `aiogram>=3.13,<4` добавлена в runtime-deps `pyproject.toml`. Притянулись транзитивно `aiohttp / aiofiles / magic-filter / pydantic-core 2.41` (последний — апгрейд, прошёл совместимо).
- **`infrastructure/settings/settings.py`** — новая под-секция `BotSettings` с полями: `token: SecretStr` (env `BOT_TOKEN`, плейсхолдер по умолчанию), `default_throttle_per_second: float = 5.0`, `default_throttle_capacity: int = 10`. Притянута в корневой `Settings` как `bot: BotSettings`. Devin Secret для production: `PIPIRIK_BOT_TOKEN` (`save_scope: org`).
- **`bot/middlewares/auth.py`** — `AuthMiddleware` извлекает Telegram-идентичность из апдейта (`Message`, `CallbackQuery`, `ChatMemberUpdated`) в неизменяемый `TgIdentity(tg_user_id, chat_id, chat_kind, language_code)` и кладёт в `data["tg_identity"]`. Если апдейт без user-а (например, сервисное `my_chat_member` без инициатора) — пишем `None`, не падаем. **Не делает проверку прав** — это работа `requires_*`-декораторов из `application.auth` (Спринт 0.2.5).
- **`bot/middlewares/locale.py`** — `LocaleMiddleware` пока всегда выставляет `data["locale"] = "ru"`. Telegram-овский `language_code` сохраняется в `data["telegram_language_code"]` для будущего i18n-пайплайна (fluent — Фаза 2). Зарезервирован, чтобы handler-ы не «прибивали» язык по месту.
- **`bot/middlewares/throttle.py`** — `ThrottleMiddleware(IRateLimiter)`. Ключ бакета `f"{tg_user_id}:{chat_id}"` — лимит на пару (пользователь × чат). На `try_acquire()=False` для `Message` отвечает «⏳ Слишком быстро…», для прочих апдейтов молча проглатывает. Без `tg_identity` (системные апдейты) — пропускает throttle вовсе.
- **`bot/middlewares/error_handler.py`** — `ErrorHandlerMiddleware`, последний рубеж. `DomainError` превращает в дружелюбное сообщение пользователю (`❌ {message}`), **не пробрасывает дальше** (это «ожидаемая» ошибка). Любое другое исключение логирует через `structlog` (`unexpected_handler_error`) с traceback-ом, отвечает пользователю «⚠️ Что-то пошло не так…», и **прокидывает** дальше — пусть видит aiogram/observability.
- **`bot/middlewares/__init__.py::register_middlewares()`** — регистрирует все 4 middleware-а в порядке `error → auth → locale → throttle` на трёх observer-ах: `dp.message`, `dp.callback_query`, `dp.my_chat_member` (последний — для регистрации клана через `bot_added_to_chat` в 1.1.D).
- **`bot/handlers/start.py`** — `Router(name="start")` с `@router.message(CommandStart())`. Handler `handle_start(message, tg_identity)` вычисляет ответ через чистую функцию `_reply_text_for(chat_kind)` — три варианта текста (private / group+supergroup / channel-fallback). Pытается читать `tg_identity.chat_kind`, но если его нет — fallback на `message.chat.type` (страховка для апдейтов без `from_user`).
- **`bot/main.py`**:
  - `Container` теперь содержит `rate_limiter: IRateLimiter` (нужен `ThrottleMiddleware`).
  - `build_container()` собирает `InMemoryTokenBucketRateLimiter` поверх `RealClock` с параметрами из `settings.bot.default_throttle_*`.
  - Новая функция `build_dispatcher(container) -> Dispatcher` — собирает `Dispatcher`, регистрирует middleware-стек и роутеры.
  - `run()` — реальный entry-point: создаёт `Bot` с `parse_mode="HTML"`, поднимает long-polling, корректно закрывает сессию в `finally`.
  - `main()` теперь — sync-обёртка `asyncio.run(run())`, не `NotImplementedError`.

Тесты:
- 31 новый тест:
  - `tests/unit/bot/middlewares/test_auth.py` (6 тестов): извлечение из `Message`, `Message` без user-а, `CallbackQuery`, callback без msg/user, `ChatMemberUpdated`, неизвестный тип события.
  - `tests/unit/bot/middlewares/test_locale.py` (2 теста): дефолт `"ru"` + сохранение `tg_lang`, отсутствие identity не ломает.
  - `tests/unit/bot/middlewares/test_throttle.py` (4 теста): пропуск при acquire, ответ «слишком быстро» при reject для `Message`, тихий drop для не-`Message`, отсутствие identity → пропуск throttle.
  - `tests/unit/bot/middlewares/test_error_handler.py` (4 теста): passthrough, `DomainError` → reply (не пробрасывается), `DomainError` без `Message` тихо проглатывается, неожиданное исключение → reply + reraise.
  - `tests/unit/bot/handlers/test_start.py` (9 тестов): `_reply_text_for` для всех типов чата + handler в private/group/supergroup/без identity.
  - `tests/unit/bot/test_composition_root.py` обновлён: `Container` теперь содержит `rate_limiter`; новый класс `TestBuildDispatcher` — проверка регистрации 4 middleware-ов на 3 observer-ах + наличия router-а `start`.
  - `tests/unit/infrastructure/test_settings.py` — добавлен `TestBotSettings` (5 тестов: дефолтный плейсхолдер-токен, маскирование repr-ом, валидация `> 0` для throttle-настроек, явные значения).

Результат:
- **341 тест** (311 + 30 новых), покрытие **95.96%**, локальный `make ci` зелёный (lint + format + mypy --strict + import-linter + pytest).
- 3 import-linter-контракта по-прежнему на месте: `bot.middlewares` зависит только от `aiogram + bot.middlewares` + `pipirik_wars.infrastructure.rate_limit / pipirik_wars.shared.errors`. Никаких импортов из `application` или `domain` в bot-слой не утекло.

Заметки / решения:
- **Почему `_reply_text_for` — отдельная чистая функция.** Чтобы не привязывать тесты к `Message`-моку и aiogram-у целиком: чистая функция тестируется тривиально (`assert _reply_text_for("private") == REPLY_PRIVATE_RU`), а handler-тест ограничивается проверкой делегирования. Дешёвая декомпозиция, по которой потом будет жить весь bot/handlers — логика выносится в чистые функции, а `@router.message` — тонкий адаптер.
- **Почему throttle-key — `user_id:chat_id`, а не только `user_id`.** Пользователь может одновременно играть в нескольких чатах (личка + группа клана + супергруппа); общий per-user лимит создал бы ложные срабатывания. Per-chat per-user — строгий минимум, который ловит спам в одном чате и не мешает параллельной активности.
- **Почему `ErrorHandlerMiddleware` пробрасывает неожиданные ошибки, а доменные — нет.** Доменные ошибки — ожидаемая часть бизнес-логики (например, «уже зарегистрирован», «клан заморожен»). Пробрасывать их в aiogram = шуметь в логе при штатной работе. Неожиданные исключения, наоборот, — bug, и observability должна их видеть.
- **Тестовая помесь `MagicMock(spec=Message)` + ручной `AsyncMock` для `answer`.** `spec=Message` нужен, чтобы прошёл `isinstance(event, Message)` в production-коде middleware-ов; `MagicMock` отдаёт `answer` как sync-метод, поэтому переопределяем на `AsyncMock`. mypy --strict устраивает: helper типизирован как `MagicMock`, а в `await mw(handler, cast(Message, event), data)` мы явно кастуем для соответствия сигнатуре middleware.
- **`structlog` уже в deps с 0.2** — доменно-агностичный structured-logger; здесь использован впервые, не тянем новые runtime-зависимости.

Дальше: PR 1.1.D — `application/use_cases/RegisterPlayer / RegisterClan / JoinClan / FreezeClan` + `bot/handlers/registration.py` (включит сюда первого реального потребителя репозиториев из 1.1.B).

---

## 2026-05-04 — Спринт 1.1.B: alembic-миграция, ORM-модели и SQLAlchemy-репозитории игрока/клана

**Автор:** Devin (по запросу 612amaranth)
**Тип:** feature (infrastructure)
**Связано:** PR #N (TBD), [development_plan.md §3 / Спринт 1.1, задача 1.1.2](development_plan.md), [current_tasks.md Спринт 1.1 → 1.1.B](current_tasks.md), предшествует — PR #8 (1.1.A domain layer)

Второй PR серии Спринта 1.1: материализация доменных портов 1.1.A в адаптеры поверх SQLAlchemy 2.x async. Новые таблицы — `users`, `clans`, `clan_members` — добавлены alembic-миграцией `0002_player_clan`, продолжающей `0001_initial` из Спринта 0.2.

Что сделано:
- **ORM-модели (`infrastructure/db/models/`)**:
  - `UserORM` (таблица `users`): `id`, `tg_id` UNIQUE, `username` (nullable, indexed), `length_cm`, `thickness_level`, `title`, `name`, `status` (default `active`), `created_at`, `updated_at`. CHECK-constraint-ы дублируют доменные инварианты VO `Length` (≥0) и `Thickness` (≥1) — защита от ручных UPDATE-ов в обход домена.
  - `ClanORM` (таблица `clans`): `id`, `chat_id` UNIQUE (BigInteger — для `-100…` супергрупп), `chat_kind`, `title` (≤255), `status`, `created_at`, `updated_at`.
  - `ClanMemberORM` (таблица `clan_members`): PK `(clan_id, player_id)` + дополнительный `UNIQUE(player_id)` — DB-инвариант ГДД §4 «один игрок = один клан за раз». FK с `ON DELETE CASCADE` на обе стороны.
- **Alembic-миграция `0002_player_clan`** (`infrastructure/db/migrations/versions/20260504_0002_player_clan_schema.py`) — `down_revision = "0001_initial"`. Полные `upgrade()` и `downgrade()` для всех трёх таблиц, индексов, FK и CHECK-constraint-ов. `BigInteger().with_variant(Integer, "sqlite")` для совместимости тестового SQLite.
- **`alembic.ini`** — добавлено `path_separator = os` (alembic 1.16+ требует явный, иначе `DeprecationWarning` падает в strict-режиме).
- **`migrations/env.py`** — расширен импорт ORM-моделей (необходим для регистрации в `Base.metadata`, иначе alembic не увидит новые таблицы при `alembic check` / `revision --autogenerate`).
- **Реальные репозитории (`infrastructure/db/repositories/`)**:
  - `SqlAlchemyPlayerRepository` — реализует `IPlayerRepository`. `add()` — INSERT, ловит `IntegrityError` → `PlayerAlreadyRegisteredError(tg_id)`. `save()` — UPDATE известного `id` (CHECK-constraint бьёт по доменным инвариантам). `get_by_tg_id` — точечный SELECT. Все методы исполняются строго внутри активного `SqlAlchemyUnitOfWork`.
  - `SqlAlchemyClanRepository` — реализует `IClanRepository`. INSERT-ошибка превращается в `ClanAlreadyRegisteredError(chat_id)`. `save()` корректно обрабатывает миграцию group→supergroup (`chat_id` мог измениться, поэтому повторный `IntegrityError` — тоже «уже занято»).
  - `SqlAlchemyClanMembershipRepository` — реализует `IClanMembershipRepository`. `add()` ловит как PK-дубль `(clan_id, player_id)`, так и нарушение `UNIQUE(player_id)` (попытка добавить игрока в новый клан, не выйдя из старого) — оба → `ClanMembershipExistsError`. `remove()` идемпотентен (DELETE rowcount=0 → возвращаем `False`, без исключения).
- **`infrastructure/db/utils.py`** — хелпер `ensure_utc(dt)` нормализует `datetime` до tz-aware. Postgres + asyncpg отдают datetime с tzinfo, но aiosqlite — naive (даже для `DateTime(timezone=True)`). Чтобы тесты на SQLite вели себя как production на Postgres, в маппинге ORM → domain дописываем UTC, если tzinfo отсутствует.

Тесты:
- **`tests/integration/db/test_player_repository.py`** (10 тестов) — round-trip add/get, дубль `tg_id`, save с мутациями, очистка optional-полей, freeze/unfreeze, защита от `add()` сущности с pre-set `id` и `save()` сущности без `id`, ошибка save для несуществующего id.
- **`tests/integration/db/test_clan_repository.py`** (13 тестов) — клан: round-trip, дубль `chat_id`, save title/status, миграция group→supergroup (id сохраняется); membership: добавление, `UNIQUE(player_id)` ловит вторую группу, идемпотентный remove, `list_by_clan` сортирует по `joined_at`.
- **`tests/integration/db/test_migrations.py`** (6 тестов) — структурные (один HEAD, наличие 0001/0002, корректный `down_revision`, контроль состава `versions/`) + smoke (`alembic upgrade head` создаёт ожидаемый набор таблиц на свежей SQLite-БД, `upgrade → downgrade base → upgrade` round-trip без ошибок). `migrations/env.py` тянет URL из `DatabaseSettings()`, поэтому переопределение через env-переменную `DATABASE_URL` (`monkeypatch.setenv`) — а не `cfg.set_main_option`.

Результат:
- 311 тестов (282 + 29 новых), покрытие 95.91 %, локальный `make ci` зелёный.
- `alembic upgrade head` чисто отрабатывает с пустой SQLite, downgrade всё корректно сворачивает (acceptance criteria 1.1.2 выполнен).

Заметки / решения:
- **Зачем `UNIQUE(player_id)` в `clan_members`.** Правило ГДД §4 «один игрок = один клан за раз» — критическое; держать его только на доменном уровне небезопасно при гонках двух одновременных `JoinClan` от разных чатов. Дублирование в БД-индексе превращает гонку в честный `IntegrityError`, который use-case переводит в `ClanMembershipExistsError`.
- **`ensure_utc` вместо нормализации в каждом тесте.** Альтернативы — (а) сделать тесты лояльными к naive vs aware, (б) хранить datetime как `String`/`Float`. (а) приводит к расхождению поведения тестов и production, (б) ломает SQL-операторы вроде `WHERE created_at > now() - interval`. Хелпер на границе ORM → domain — компромисс, не утечка инфраструктуры в домен (домен по-прежнему получает `datetime` с UTC).
- **Pure-sync миграционный smoke-тест.** Объяснение в docstring `test_migrations.py`: `command.upgrade()` сам вызывает `asyncio.run()` (через `env.py`), а pytest-asyncio запускает тест внутри своего loop — две загруженные ссылки на event-loop конфликтуют. Помечать тест `@pytest.mark.asyncio` нельзя; вместо этого делаем sync-тест и переопределяем URL через `DATABASE_URL`.
- **Repository не коммитит и не открывает UoW.** `add()`/`save()` делают `flush()` (чтобы получить сгенерированный PK/поймать IntegrityError до конца транзакции), но коммит — ответственность UoW в `__aexit__`. Это сохраняет атомарность мульти-репозиторных use-case-ов из 1.1.D (`RegisterPlayer + AuditLog + IdempotencyKey`).

Дальше: PR 1.1.C — aiogram bootstrap (dispatcher + middleware-стек + `/start` stub).

---

## 2026-05-04 — Спринт 1.1.A: domain layer для игрока и клана

**Автор:** Devin (по запросу 612amaranth)
**Тип:** feature (domain) / scaffold
**Связано:** PR #N (TBD), [development_plan.md §3 / Спринт 1.1, задачи 1.1.7 / часть 1.1.3 / 1.1.4 / 1.1.10 (доменная половина)](development_plan.md), [current_tasks.md Спринт 1.1 → 1.1.A](current_tasks.md)

Стартовый PR серии Спринта 1.1: чистый доменный слой для игрока и клана. Никакого I/O, никакого aiogram, никакой БД — только value-objects, агрегаты, репозиторий-порты и доменные ошибки. Дальнейшие PR-ы серии (1.1.B alembic+repos, 1.1.C aiogram bootstrap, 1.1.D use-cases+handlers, 1.1.E `/profile` + `/balance_reload`) будут опираться на эти типы.

Что сделано:
- **`domain/player/value_objects.py`** — `Length` (≥0 см), `Thickness` (≥1), `Title(str, Enum)` с единственным значением `NEWBIE` (расширим в 1.3.8/Q12b/Q13), `PlayerName` (строка с инвариантами), `DisplayName` (типизированная обёртка для расчётного «названия» из `balance.yaml.display_names`), `Username` (без `@`, ≤32, не пустая).
- **`domain/player/entities.py`** — агрегат `Player` (frozen-датакласс, slots): `id|None / tg_id / username / length / thickness / title / name / status / created_at / updated_at`. Фабрика `Player.new(tg_id, username, now)` ставит стартовое состояние ГДД §1.1: длина=2, толщина=1, без титула, без имени, status=ACTIVE. Мутаторы `with_username/with_length/with_thickness/with_title/with_name/without_name` возвращают новый инстанс; на `frozen`-игроке бросают `PlayerFrozenError`. `freeze`/`unfreeze` идемпотентны и работают и на frozen-игроке (это администраторский путь).
- **`domain/player/errors.py`** — `PlayerAlreadyRegisteredError(ConcurrencyError)`, `PlayerFrozenError(DomainError)`.
- **`domain/player/repositories.py`** — порт `IPlayerRepository` (`get_by_tg_id / add / save`). Все методы — внутри активного UoW, собственный коммит репозиторий не делает (правило Спринта 0.2).
- **`domain/clan/value_objects.py`** — `ChatKind` (`group / supergroup`), `ClanStatus` (`active / frozen`), `ClanTitle` (с инвариантами).
- **`domain/clan/entities.py`** — агрегат `Clan` (frozen+slots): `id|None / chat_id / chat_kind / title / status / created_at / updated_at`. Фабрика `Clan.new(chat_id, chat_kind, title, now)`. Мутатор `with_chat_id(new_chat_id, new_chat_kind, now)` для миграции `group → supergroup` (Telegram меняет `chat_id` при промоушене, внутренний `id` сохраняется). `with_title / freeze / unfreeze` — идемпотентные. `ClanMember` — отдельный «связующий» агрегат `(clan_id, player_id, role, joined_at)` с ролью `MEMBER / LEADER`.
- **`domain/clan/errors.py`** — `ClanAlreadyRegisteredError(ConcurrencyError)`, `ClanFrozenError(DomainError)`, `ClanMembershipExistsError(ConcurrencyError)`.
- **`domain/clan/repositories.py`** — порты `IClanRepository` (`get_by_chat_id / get_by_id / add / save`) и `IClanMembershipRepository` (`get_by_player / list_by_clan / add / remove`). `remove` идемпотентен (повторный кик — не ошибка).

Тесты:
- 94 новых юнит-теста (`tests/unit/domain/player/{test_value_objects, test_entities, test_errors}.py` + аналогичные для clan). Покрытие веток ≥ 95 % на новых файлах.
- Проверены: VO-инварианты (границы, пустые/whitespace, длина), стартовые значения регистрации (ГДД §1.1), идемпотентность мутаций (с=прежнее → возвращаем `is`-тот же инстанс), миграция group→supergroup, frozen-блокировка мутаций (кроме freeze/unfreeze).

Результат:
- 282 теста (188 предыдущих + 94 новых), покрытие 95.63% (порог 80%).
- `make ci` зелёный (lint + format + mypy --strict + import-linter + pytest).
- Все три import-linter-контракта сохранены: domain/player и domain/clan не импортируют ничего, кроме stdlib и `pipirik_wars.shared.errors`.

Заметки / решения:
- **Иммутабельность вместо мутирующих setter-ов.** Player/Clan — frozen-датаклассы, мутации возвращают новый инстанс. Это делает невозможной частичную мутацию объекта, который держит UoW/audit-buffer/кэш — старая ссылка остаётся валидной. Use-case всегда работает с явной заменой `player = player.with_length(...)`, что хорошо матчится с audit-логом «было/стало».
- **`Title` как `str, Enum` с одним значением.** Сейчас в ГДД доступен только `NEWBIE`; остальные титулы (Нежный, Умный и т. п.) ждут уточнений геймдиза (Q12b/Q13). Расширение enum-а — backwards-compatible, существующий код менять не придётся.
- **`DisplayName` — отдельный VO, а не `str`.** Это требование dev_plan.md §1.1.7 («value object DisplayName»). Сама лукап-логика остаётся в `BalanceConfig.display_name_for(length_cm)`, но в use-case-ах и презентерах мы несём типизированный VO, а не голую строку — ниже шанс перепутать «название» и «имя».
- **`with_chat_id` для миграции group→supergroup.** Telegram меняет `chat_id` при промоушене группы в супергруппу (с положительного в `-100…`), но внутренняя сущность клана при этом не должна пересоздаваться. Метод-мутатор делает атомарную замену `(chat_id, chat_kind)` без потери `id` и `created_at`.
- **`ClanMember.remove` идемпотентен.** Telegram может присылать дубль `chat_member`-евента, и use-case не должен валиться при «уже ушёл».

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
