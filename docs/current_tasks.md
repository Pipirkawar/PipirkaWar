# 🍆 Пипирик Варс — Текущие задачи

> Этот файл описывает **только то, что в работе сейчас**: активная feature-ветка, активный спринт/PR, чек-лист текущих шагов и их статусы. По мере выполнения шаги отмечаются `[x]`; после мерджа PR-а соответствующая запись переносится в [`history.md`](history.md), а файл обновляется под следующий спринт.
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

**На `main`:** последний смерженный спринт — **2.5-B** ([PR #81](https://github.com/Pipirkawar/PipirkaWar/pull/81), коммит `3653e40`) «Команды поддержки в боте» — `/find_player`, `/player`, `/freeze`, `/unfreeze`, `/ban` (TOTP) + общий `/confirm`-dispatcher; добавлен `IsAdminFilter` на `admin_support_router`, расширены `IPlayerRepository` (`find_by_query`, `freeze`, `unfreeze`) + `Player.ban` + `PlayerStatus.BANNED`, новые `AdminAuditAction`-константы (`ADMIN_PLAYER_LOOKUP/FROZEN/UNFROZEN/BANNED`), DI всех 7 admin-use-case-ов в `Container`. Завершены Фазы 0, 1 (MVP), 1.6 (анти-чит) полностью; из Фазы 2 закрыты 2.1–2.4 целиком и **2.5-A + 2.5-B** из Спринта 2.5. Идёт **Спринт 2.5-C** (команды экономики в боте: `/grant_length`, `/grant_thickness`, `/balance_get`, `/balance_set`).

**Активная feature-ветка:** `devin/1778098395-sprint-2-5-c-economy` (от `main` = `395e053`). На ветке 2 коммита Спринта 2.5-C; PR ещё не открыт. Делаются финальные шаги: проверить `make ci` целиком, открыть PR.

**Что сделано на ветке 2.5-C (последний коммит `39d4c5d`):**
- C.1–C.5, C.7 — use-case-ы `GrantLength`/`GrantThickness`/`GetBalanceValue`/`SetBalanceValue` + `IBalanceWriter`/`YamlBalanceWriter` (atomic-write + flock + hot-reload через `IBalanceReloader`) + `IIdempotencyKey` → `build_admin_idempotency_key` (sha256, minute-floor); `AdminAuditAction.ADMIN_GRANT_LENGTH/_THICKNESS/_BALANCE_GET/_BALANCE_SET`.
- C.6 — рефактор `/confirm`-handler-а на **registry-pattern** (`CONFIRM_DISPATCHERS: dict[command_kind, dispatcher]`); `bot/handlers/admin_economy.py` (4 handler-а + 3 dispatch-функции + `ConfirmDispatchDeps`).
- C.8 — DI всех 4 use-case-ов в `Container` (`bot/main.py`) + регистрация `admin_economy_router` в `dispatcher` + workflow-data injection (`grant_length`, `grant_thickness`, `get_balance_value`, `set_balance_value`).
- C.10 — локали `admin-grant-length-*` (12 ключей), `admin-grant-thickness-*` (11), `admin-balance-get-*` (4), `admin-balance-set-*` (9), `admin-idempotency-replay-*` (1) в `locales/{ru,en}.ftl`.
- C.9 — `tests/unit/bot/handlers/test_admin_economy.py` (48 тестов: 4 handler-а × валидация + 3 dispatch × все ветки + idempotency-replay + registry-проверка); правки `test_composition_root.py` под новый Container; integration-тесты `tests/integration/balance/test_yaml_writer.py` уже есть из C.4. Локально pytest целиком: 3118 passed / 1 skipped (без coverage-gate).
- В ходе C.9 ослаблен тип `YamlBalanceWriter.loader` с `YamlBalanceLoader` до **порта** `IBalanceReloader` (мелкий refactor, mypy-clean — позволяет подсунуть `FakeBalanceConfig` в тестах composition_root, FakeBalanceConfig уже реализует и `IBalanceConfig`, и `IBalanceReloader`).

**Что уже есть в коде после 2.5-B:**
- `domain/player/{entities,repositories}.py` — `Player.ban(now)` (идемпотентный) + `PlayerStatus.BANNED`; `IPlayerRepository.find_by_query(query, limit)` / `freeze(tg_id, *, reason)` / `unfreeze(tg_id)`.
- `application/admin/{find_players,get_player_card,freeze_player,unfreeze_player,ban_player}.py` + `request_confirm,verify_confirm` (из 2.5-A).
- `bot/filters/admin.py` (`IsAdminFilter`) + `bot/handlers/admin_support.py` (5 handler-ов + `/confirm` dispatcher на `command_kind="ban"`) + `bot/presenters/admin_support.py`.
- `bot/main.py` (Container) — DI `find_players`, `get_player_card`, `freeze_player`, `unfreeze_player`, `ban_player`, `request_admin_confirm`, `verify_admin_confirm` + `SqlAlchemyAdminAuditLogger` + `InMemoryAdminConfirmStore` + `PyOtpTotpVerifier` + `TokenFactory`.
- `infrastructure/db/repositories/player.py` — Sql-impl новых методов (case-insensitive ILIKE-подстрока, экранирование `%`/`_`).
- `tests/fakes/totp_verifier.py` (Fake для unit-тестов TOTP-flow), `tests/fakes/player_repo.py` (Fake-impl новых методов).
- Локали `admin-find-player-*` / `admin-player-*` / `admin-freeze-*` / `admin-unfreeze-*` / `admin-ban-*` / `admin-confirm-*` в `locales/{ru,en}.ftl`.
- Старые `bot/handlers/admin.py` (`/balance_reload`, `/admin_stats`, `/set_max_dau`, `/anticheat_unban`) — пока на старой авторизации use-case-уровня; в 2.5-D будут перенесены под `AdminGuard` + RBAC.

**Скоуп Спринта 2.5 (4 PR-а):**
- ~~**2.5-A**~~ ✅ закрыт PR #79 (`b358349`) — каркас `admin_audit_log` + `AdminGuard` + TOTP-confirm.
- ~~**2.5-B**~~ ✅ закрыт PR #81 (`3653e40`) — команды поддержки + общий `/confirm`-dispatcher.
- **2.5-C** (текущий PR): экономика — `/grant_length`, `/grant_thickness`, `/balance_get`, `/balance_set` + TOTP на все мутирующие + idempotency_key из `(admin_id, command, target, minute)`.
- **2.5-D** (финал): кланы (`/clan`, `/freeze_clan`, `/unfreeze_clan`, `/clan_daily_head_history`) + `/announce` + `/audit` + `/admin_setup_totp` + миграция старых `/balance_reload` / `/admin_stats` / `/set_max_dau` / `/anticheat_unban` под `AdminGuard` + RBAC + `docs/admin_runbook.md`.

**`make ci` на main:** зелёный (последний прогон в PR #81: 2997 passed / 1 skipped, coverage 96.18%).

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `2.5 — Расширенный админ-интерфейс в боте` |
| **Активный PR / шаг** | **2.5-C**: команды экономики (`/grant_length`, `/grant_thickness`, `/balance_get`, `/balance_set`) |
| **Активная feature-ветка** | _ещё не создана_ — будет ветвиться от свежего `main` (`3653e40`); сейчас идёт docs-PR с этой переразметкой на ветке `devin/1778097868-sprint-2-5-b-postmerge-docs` |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `3653e40` (мерж PR #81 «Спринт 2.5-B: команды поддержки в боте») |
| **PR (если открыт)** | _docs-PR (postmerge 2.5-B) — будет открыт этим коммитом; сам 2.5-C — ещё не открыт_ |
| **CI статус** | зелёный (последний прогон в PR #81: 2997 passed / 1 skipped, coverage 96.18%) |
| **Связанная задача в `development_plan.md`** | §5 / Спринт 2.5 / задачи 2.5.4 (`/grant_*`, `/balance_*`), 2.5.5 (TOTP на мутирующие), 2.5.9 (use-case каркас) |
| **Связанная спецификация в `game_design.md`** | §18.6 (RBAC + 2FA для `economist`), §16 (`/grant_length`/`/grant_thickness`/`/balance_*` командные права), §6 (анти-чит окно — `/grant_length` обязан проходить через тот же rolling-24h-clamp) |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**PR 2.5-C — команды экономики:**

- [ ] **2.5-C.1 — `/grant_length <tg_id> <±cm> <reason>`** — мутирующая команда, TOTP-обязательная. Use-case `GrantLength(admin_id, target_tg_id, delta_cm, reason, idempotency_key)`. Ограничения: `delta_cm != 0`, `reason` не пустой, `target` существует и не забанен. Должен **обязательно** проходить через тот же `LENGTH_DELTA`-clamp + rolling-24h-окно из анти-чита (`source="admin_grant"`, см. ГДД §6 — попадает в окно `3000 см / сутки`). Audit: `ADMIN_GRANT_LENGTH` с `before/after/delta/reason`. Локаль `admin-grant-length-*` (RU+EN). Handler: `RequestAdminConfirm(command_kind="grant_length", payload={target_tg_id, delta_cm, reason})` → `/confirm <token> <code>` → `GrantLength.execute()`.
- [ ] **2.5-C.2 — `/grant_thickness <tg_id> <level> <reason>`** — установка нового уровня толщины (НЕ дельта, согласно ГДД §16). Use-case `GrantThickness(admin_id, target_tg_id, new_level, reason, idempotency_key)`. Валидация `new_level` — допустимый диапазон из доменных констант (`MIN_THICKNESS_LEVEL`/`MAX_THICKNESS_LEVEL`). Audit: `ADMIN_GRANT_THICKNESS` с `before/after/reason`. Локаль `admin-grant-thickness-*`. TOTP-обязательна (`command_kind="grant_thickness"`).
- [ ] **2.5-C.3 — `/balance_get <key>`** — read-only чтение значения из `balance.yaml` (через существующий `IBalanceConfig`). Use-case `GetBalanceValue(admin_id, key)`. БЕЗ TOTP. Audit: `ADMIN_BALANCE_GET` (опционально — поддержка может расследовать «кто что смотрел»). Локаль `admin-balance-get-*`.
- [ ] **2.5-C.4 — `/balance_set <key> <value> <reason>`** — мутирующая команда, TOTP-обязательная. Use-case `SetBalanceValue(admin_id, key, raw_value, reason, idempotency_key)`. Должен валидировать `key` (существует в `balance.yaml`), типизировать `raw_value` (через `IBalanceWriter`), писать в файл (или БД-overlay, если используется), вызывать существующий hot-reload через `IBalanceReloader`. Audit: `ADMIN_BALANCE_SET` с `before/after/reason`. Локаль `admin-balance-set-*`. TOTP-обязательна (`command_kind="balance_set"`).
- [ ] **2.5-C.5 — Идемпотентность мутирующих команд.** `idempotency_key = sha256(f"{admin_id}|{command}|{target}|{minute_floor(ts)}")`. Use-case-ы зовут `IIdempotencyService.try_acquire(idempotency_key)` перед мутацией; повторный вызов в ту же минуту — no-op + ответ «уже выполнено в HH:MM:SS». Покрыть тестом: дважды подряд `/grant_length 123 +5` → второй ответ «no-op», audit-лог содержит **одну** запись.
- [ ] **2.5-C.6 — Расширить `/confirm`-dispatcher** под новые `command_kind`-ы: `grant_length` / `grant_thickness` / `balance_set`. Старый switch (был только `ban`) превращается в реестр (`{"ban": _dispatch_ban, "grant_length": _dispatch_grant_length, ...}`); неизвестный kind — `admin-confirm-unknown-command-kind` (как сейчас).
- [ ] **2.5-C.7 — Расширить `AdminAuditAction`** enum: `ADMIN_GRANT_LENGTH`, `ADMIN_GRANT_THICKNESS`, `ADMIN_BALANCE_GET` (если решим логировать read-side), `ADMIN_BALANCE_SET`. Обновить `domain/admin/ports/admin_audit.py` + миграции/тесты не требуются (enum хранится как str в JSONB-колонке `action`).
- [ ] **2.5-C.8 — DI use-case-ов в `Container`** — `grant_length`, `grant_thickness`, `get_balance_value`, `set_balance_value` + `IIdempotencyService` (если уже есть — переиспользовать, иначе создать adapter в инфраструктуре). Все use-case-ы прокинуты в `dispatcher` workflow-data.
- [ ] **2.5-C.9 — Тесты:** unit на каждый новый use-case (≥ 4 кейса: happy / not_found / TOTP-fail / idempotent-replay для мутирующих); 2-3 integration-теста на запись в `balance.yaml` (или стораджи балансов) + откат при ошибке reload-а; e2e-тесты на TOTP-flow всех 3 мутирующих команд (правильный код / неверный код / истечение токена / неизвестный command_kind).
- [ ] **2.5-C.10 — Локали** `admin-grant-length-*` / `admin-grant-thickness-*` / `admin-balance-get-*` / `admin-balance-set-*` в `locales/{ru,en}.ftl`. Сообщения об idempotent-replay — отдельный ключ `admin-idempotency-replay-*`.
- [ ] **Перед PR:** прогон `make ci` зелёный, lint/typecheck/import-linter ✅.
- [ ] **Перед мерджем:** sync `current_tasks.md` под 2.5-D; запись в `history.md`.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты. Не дублируй ТЗ из `development_plan.md` — пиши только то, что важно для **текущего PR**.

**Текущая дельта (PR 2.5-C будет про):**
- Все мутирующие команды (`/grant_length`, `/grant_thickness`, `/balance_set`) проходят через **тот же** `/confirm`-dispatcher и `RequestAdminConfirm`/`VerifyAdminConfirm` use-case-ы из 2.5-A. В 2.5-B мы добавили только `command_kind="ban"`; в 2.5-C расширяем реестр на 3 новых kind-а.
- `/grant_length` ОБЯЗАН проходить через анти-чит-окно (ГДД §6, табл. «положительные `LENGTH_DELTA`», `source="admin_grant"`). Если уже существующий `LengthDeltaApplier` / clamp-сервис не покрывает админ-источник — расширяем его через **новый параметр `source`** в существующем порту, не создаём отдельный путь.
- `/balance_set` зависит от способа хранения баланса. Текущий код использует `balance.yaml` + hot-reload (`IBalanceReloader`). Если запись в файл вызовет race-condition в проде (одновременные правки разными админами), для 2.5-C достаточно last-write-wins + serialize запись через единый `IBalanceWriter` + audit-log; full-fledged БД-overlay — отдельная задача в Фазе 4 (если потребуется веб-админкой).
- Новые `AdminAuditAction`-константы — продолжение добавленных в 2.5-B (`ADMIN_PLAYER_*`).
- Новый dispatcher `command_kind`-реестр — рефактор существующего switch в `bot/handlers/admin_support.py:_dispatch_confirm_*` (если он там) или вынесение в отдельный `application/admin/confirm_dispatcher.py`. Решить в первом коммите.
- Идемпотентность — **обязательна для всех 3 мутирующих команд**. Нет защиты от двойного нажатия в Telegram = нет фичи.
- Затронутые слои: `domain/admin/ports/admin_audit.py` (расширение enum), `application/admin/{grant_length,grant_thickness,get_balance_value,set_balance_value}.py` (новые use-case-ы), `bot/handlers/admin_support.py` (новые handler-ы) + регистрация в `admin_support_router`, `bot/main.py` (DI), `locales/{ru,en}.ftl`.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- _нет_

---

## 🧹 Что делать при передаче работы другому агенту

Если текущий агент не успевает закрыть PR (закончились токены, упал инструментарий, обрыв сессии), **обязательно**:

1. Обнови «Текущая позиция» и чек-лист выше — отметь, что готово, что начато, что не тронуто.
2. Создай `AGENT_HANDOFF.md` в корне репо с расширенным контекстом по шаблону из `CONTRIBUTING.md` («Протокол передачи работы между агентами»).
3. Закоммить + запушь свои текущие наработки на feature-ветку (даже если они не работают — в WIP-коммите явно укажи `WIP:` в заголовке и опиши состояние в теле).
4. Не открывай PR, если ветка в полусломанном состоянии (CI красный, тесты падают): следующий агент откроет PR сам, когда доведёт до зелёного.
