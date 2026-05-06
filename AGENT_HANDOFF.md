# AGENT_HANDOFF — Спринт 2.3.E (handler `/clan_head` + presenter + DI + locales)

> **Контекст:** Если ты читаешь это, у предыдущего агента закончились
> токены посреди работы. Этот файл — точный чек-лист, чтобы поднять
> работу там, где она была остановлена.
>
> **Ветка:** `devin/<timestamp>-sprint-2-3-e-clan-head-handler`
>  (имя см. `git rev-parse --abbrev-ref HEAD`).
>
> **Базовая ветка:** `main` @ `623d7e7` (после merge PR #70).
>
> **Предыдущий PR:** #71 — Спринт 2.3.D (каталог цитат) **смержен**.

## Что уже сделано в этой ветке

- (Заполняется по мере коммитов; см. `git log --oneline main..HEAD`.)

## План спринта 2.3.E (по шагам)

Цель: пользователь / админ клана может вручную назначить главу клана
дня командой `/clan_head` или нажав inline-кнопку. Идемпотентно по
`(clan_id, moscow_date)` через UNIQUE-индекс `daily_heads`.

> **Что НЕ делаем в 2.3.E (намеренно отложено в 2.3.F):**
> - APScheduler-cron с `random_offset(0..24h)` (это 2.3.F).
> - Middleware `daily_active`-записи на каждое сообщение (тоже 2.3.F
>   или 2.3.E.2 — see Decisions ниже).

### Шаг 1. DI-провязка `clan_quote_provider`

В <ref_file file="/home/ubuntu/PipirkaWar/src/pipirik_wars/bot/main.py" />:

1. Добавить импорт:
   ```python
   from pipirik_wars.application.daily_head import IClanQuoteTemplateProvider
   from pipirik_wars.infrastructure.templates import (
       JsonClanQuoteTemplateProvider,  # +
       JsonDuelLogTemplateProvider,
       JsonForestLogTemplateProvider,
       JsonOracleTemplateProvider,
   )
   ```
2. В `Container` добавить поле `clan_quote_provider: IClanQuoteTemplateProvider`
   (рядом с `oracle_templates`, `duel_log_templates` и т.д.).
3. В `build_container()` после `forest_log_templates` / `duel_log_templates`
   создать инстанс:
   ```python
   clan_quote_provider = JsonClanQuoteTemplateProvider(
       templates_dir=templates_dir or _DEFAULT_TEMPLATES_DIR,
   )
   ```
4. Передать в `Container(...)` (порядок: рядом с `oracle_templates`).
5. В `build_dispatcher()` пробросить:
   ```python
   dispatcher["clan_quote_provider"] = container.clan_quote_provider
   ```

### Шаг 2. Handler `/clan_head`

Создать <ref_file file="/home/ubuntu/PipirkaWar/src/pipirik_wars/bot/handlers/clan_head.py" />:
- `Router(name="clan_head")`.
- `@router.message(Command("clan_head"))` async handler.
- Параметры (DI через aiogram workflow-data): `message`, `tg_identity`,
  `request_daily_head`, `clans`, `bundle`, `clan_quote_provider`,
  `locale`.
- Логика:
  1. Если `tg_identity is None` → return (cм. clan_history).
  2. Если `chat_kind not in ("group", "supergroup")` →
     `presenter.needs_group_chat(...)`.
  3. `clan = await clans.get_by_chat_id(tg_identity.chat_id)` —
     если `None` или `clan.id is None` → `presenter.not_registered(...)`.
  4. **Найти `tg_id → player_id`**: получить инициатора через
     `players.get_by_tg_id(tg_identity.user_id)`. Если `None` →
     `presenter.not_registered(...)` (или отдельный ключ
     `clan-head-player-not-registered`).
  5. Вызвать `await request_daily_head.execute(RequestDailyHeadInput(
        clan_id=clan.id, requested_by_player_id=player.id))` (проверить
     точное имя DTO в `application/daily_head/dto.py`).
  6. Поймать ошибки:
     - `DailyHeadInsufficientActivityError` → `presenter.not_enough_active(...)`.
     - `ClanFrozenError` → `presenter.frozen_clan(...)`.
  7. На успех:
     - Получить `templates = clan_quote_provider.get_templates(locale=effective_locale.value)`.
     - Выбрать случайную через **`container.random`** (проброшенную в
       handler через `random: IRandom`) — или передавать
       `IRandom`-инстанс отдельно. См. как делает `oracle.py` handler.
     - Вызвать `presenter.success(resolved=resolved, quote=quote, locale=...)`.
- Зарегистрировать роутер в `bot/handlers/__init__.py` →
  `register_routers()`.

> ⚠ **Открытый вопрос #1:** в каком слое выбирается цитата?
> Варианты:
> - **A.** В handler-е (доступ к `IRandom` + `clan_quote_provider`).
>   Проще, нет нового use-case-а, но handler делает random-выбор.
> - **B.** Отдельный use-case `RenderDailyHeadAnnouncement` /
>   расширение `RequestDailyHead.execute()` чтобы оно возвращало уже
>   `quote_id + quote_text`. Чище архитектурно, но требует поправок в
>   2.3.C-коде.
>
> **Рекомендация:** идти по варианту **A** для 2.3.E (минимальный
> диффе), а в 2.3.F/2.3.G можно перерефакторить в use-case если
> потребуется по требованию ПД 2.3.5 «запись `quote_id` в audit_log».
>
> Если выбираем **A** — random-выбор делается через
> `container.random`, проброшенный в handler через `dispatcher["random"]`
> (проверить, есть ли такая привязка). Если нет — добавить:
> `dispatcher["random"] = container.random`.

### Шаг 3. Presenter `ClanHeadPresenter`

Создать <ref_file file="/home/ubuntu/PipirkaWar/src/pipirik_wars/bot/presenters/clan_head.py" />:
- Аналог `ClanHistoryPresenter`.
- Методы:
  - `needs_group_chat(*, locale)` → ключ `clan-head-needs-group-chat`.
  - `not_registered(*, locale)` → ключ `clan-head-not-registered`.
  - `not_enough_active(*, locale, active_count, required)` →
    ключ `clan-head-not-enough-active`.
  - `frozen_clan(*, locale)` → ключ `clan-head-frozen-clan`.
  - `success(*, locale, player_display_name, bonus_cm, quote_text)` →
    ключ `clan-head-success`. Шаблон должен включать тонко
    отформатированную цитату; см. формат ниже.
  - `already_assigned(*, locale, current_head_name, bonus_cm, quote_text)` →
    ключ `clan-head-already-assigned`. Это случай когда `was_new=False`
    в `DailyHeadResolved` — день уже занят, тихое сообщение.

Зарегистрировать в `bot/presenters/__init__.py`.

### Шаг 4. Локали

В <ref_file file="/home/ubuntu/PipirkaWar/locales/ru.ftl" />:

```ftl
## /clan_head (Спринт 2.3.E — глава клана дня)

clan-head-needs-group-chat = 👑Команда `/clan_head` работает только в групповом чате клана.
clan-head-not-registered = 👑Этот чат не привязан к зарегистрированному клану. Используй /start.
clan-head-not-enough-active = 👑В клане слишком мало активных за последние 7 дней (нужно как минимум { $required }, активны: { $active_count }).
clan-head-frozen-clan = 👑Клан временно заморожен. Назначить главу нельзя.
clan-head-success = 👑<b>Глава клана дня</b> — { $player_display_name }!
  +{ NUMBER($bonus_cm, useGrouping: 0) } см к длине.

  💬 <i>{ $quote_text }</i>
clan-head-already-assigned = 👑На сегодня глава уже назначен — { $player_display_name }.

  💬 <i>{ $quote_text }</i>
```

И аналог в <ref_file file="/home/ubuntu/PipirkaWar/locales/en.ftl" />.

### Шаг 5. Тесты

1. **`tests/unit/bot/presenters/test_clan_head.py`** — рендер всех
   методов через `FakeMessageBundle`. ~6 тестов.
2. **`tests/unit/bot/handlers/test_clan_head.py`** — handler-смоук:
   - private-chat → `needs_group_chat`.
   - group-chat без клана → `not_registered`.
   - group-chat без зарегистрированного игрока → `not_registered`.
   - frozen clan → `frozen_clan`.
   - insufficient active → `not_enough_active`.
   - success (was_new=True) → `success` + цитата выбрана из каталога.
   - already-assigned (was_new=False) → `already_assigned`.

   Используй `FakeRequestDailyHead`-стуб (или мокни через monkeypatch)
   и `FakeClanQuoteTemplateProvider` (см. <ref_file file="/home/ubuntu/PipirkaWar/tests/fakes/__init__.py" />).
3. **Composition root** — добавить `clan_quote_provider` field в
   `_container_with_fakes()` и assertions в
   <ref_file file="/home/ubuntu/PipirkaWar/tests/unit/bot/test_composition_root.py" />.

### Шаг 6. Документация

- В <ref_file file="/home/ubuntu/PipirkaWar/docs/current_tasks.md" /> добавить запись 2.3.E
  (формат см. 2.3.D entry, поменять статус 2.3.D на «✅смержено (PR #71)»).
- В <ref_file file="/home/ubuntu/PipirkaWar/docs/history.md" /> добавить запись «2026-05-05 —
  Спринт 2.3.E» сверху текущей записи 2.3.D.

### Шаг 7. CI / PR

1. `pre-commit run --all-files` — должно быть зелёным.
2. `make ci` — должно быть зелёным (~2600 passed, coverage ≥ 95.85%).
3. **Удалить этот HANDOFF** (`git rm AGENT_HANDOFF.md`).
4. Коммит, push, `git_pr(action="fetch_template")`, `git_pr(action="create")`.
5. `git(action="pr_checks", wait_mode="all")` — дождаться зелёного CI.
6. Сообщение пользователю с PR-линком.

## Decisions / открытые вопросы

1. **Middleware `daily_active`-записи** — отложено в 2.3.F (или
   отдельный 2.3.E.2). Без middleware `daily_active`-таблица будет
   пустой в проде, и `RequestDailyHead` упадёт с
   `DailyHeadInsufficientActivityError` каждый раз. На MVP-этапе для
   2.3.E можно оставить так, потому что тесты handler-а используют
   фейк-репозиторий с предзаписанными активными игроками. В реальном
   проде до 2.3.F не будет работать `/clan_head`, но 2.3.F приземлится
   быстро.

2. **`tags`-фильтр по `mild_profanity`** — в каталоге пока нет цитат
   с `profanity`-тегом, но handler должен быть готов фильтровать:
   ```python
   filtered = [
       t for t in templates
       if balance.daily_head.content_policy.mild_profanity or not t.has_profanity
   ]
   ```
   ⚠ В `BalanceConfig.DailyHeadConfig` пока нет поля
   `content_policy.mild_profanity`. Можно либо:
   - **(a)** Добавить в `DailyHeadConfig` (см. <ref_file file="/home/ubuntu/PipirkaWar/src/pipirik_wars/domain/balance/config.py" />)
     поле `content_policy: ContentPolicyConfig` с `mild_profanity: bool = True`,
     и в `config/balance.yaml` добавить:
     ```yaml
     daily_head:
       ...
       content_policy:
         mild_profanity: true
     ```
   - **(b)** Просто не фильтровать в 2.3.E (раз цитат с `profanity`
     нет) и отложить фильтрацию + balance-поле в 2.3.E.2.
   **Рекомендация:** (b) — минимизировать диффе, добавим поле когда
   появится первая `profanity`-цитата.

3. **Audit `DAILY_HEAD_ASSIGN`** уже пишется в `RequestDailyHead`
   (см. 2.3.C). В 2.3.E дополнительно НЕ нужно ничего логировать —
   handler только рендерит результат.

## Полезные файлы для изучения

- <ref_file file="/home/ubuntu/PipirkaWar/src/pipirik_wars/bot/handlers/clan_history.py" /> — образец group-only handler с `tg_identity`.
- <ref_file file="/home/ubuntu/PipirkaWar/src/pipirik_wars/bot/handlers/oracle.py" /> — образец handler с template-выбором цитаты + `IRandom`.
- <ref_file file="/home/ubuntu/PipirkaWar/src/pipirik_wars/bot/presenters/clan_history.py" /> — образец presenter через `IMessageBundle`.
- <ref_file file="/home/ubuntu/PipirkaWar/src/pipirik_wars/application/daily_head/request.py" /> — `RequestDailyHead` use-case (см. сигнатуру `execute()`).
- <ref_file file="/home/ubuntu/PipirkaWar/src/pipirik_wars/application/daily_head/dto.py" /> — `DailyHeadResolved` (что возвращает use-case).
- <ref_file file="/home/ubuntu/PipirkaWar/tests/fakes/__init__.py" /> — список существующих fakes (нужно добавить `FakeClanQuoteTemplateProvider`).
