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

**На `main`:** последний смерженный спринт — **2.5-C** ([PR #83](https://github.com/Pipirkawar/PipirkaWar/pull/83), коммит `10b3ee6`) «Команды экономики в боте» — `/grant_length`, `/grant_thickness` (обе TOTP, через анти-чит-clamp `source="admin_grant"`/`"admin_refund"`), `/balance_get` (read-only), `/balance_set` (TOTP, atomic YAML-write + flock + hot-reload). Введён `IBalanceWriter` + `YamlBalanceWriter` (atomic + `fcntl.flock`), `IIdempotencyKey` (`sha256(admin_id|command|target|minute_floor(ts))`), refactor `/confirm`-handler-а на **registry-pattern** (`CONFIRM_DISPATCHERS: dict[command_kind, dispatcher]`), новые `AdminAuditAction.ADMIN_GRANT_LENGTH/_THICKNESS/_BALANCE_GET/_BALANCE_SET`. DI 4 новых use-case-ов + регистрация `admin_economy_router`. Поверх `main` смержен PR #84 (`d2f7cb4`) — postmerge-доки 2.5-C (запись в `history.md` + переразметка `current_tasks.md`). Завершены Фазы 0, 1 (MVP), 1.6 (анти-чит) полностью; из Фазы 2 закрыты 2.1–2.4 целиком и **2.5-A + 2.5-B + 2.5-C** из Спринта 2.5. Идёт **Спринт 2.5-D** (финал — кланы + `/announce` + `/audit` + `/admin_setup_totp` + миграция старых admin-команд).

**Активная feature-ветка:** `devin/1778101600-sprint-2-5-d-final` (от `main = d2f7cb4`). Закоммичены/запушены: **D.9** (`3ef53b7` — `command_kind="ban"` → `CONFIRM_DISPATCHERS`), **docs sync** (`0bc4000`), **D.5** (`9634695` — `/audit`), **D.1** (`ce39097` — `/clan`), **D.2** (`fb761e7` — `/freeze_clan`+`/unfreeze_clan`), **D.3** (`176216c` — `/clan_daily_head_history`). Дальше — D.4, D.6, D.7+D.8, D.10–D.12.

**Что уже есть в коде после 2.5-C:**
- `domain/admin/ports/admin_audit.py` — расширенный `AdminAuditAction` (с 2.5-C: `ADMIN_GRANT_LENGTH/_THICKNESS/_BALANCE_GET/_BALANCE_SET`; с 2.5-B: `ADMIN_PLAYER_LOOKUP/FROZEN/UNFROZEN/BANNED`).
- `domain/balance/{ports,errors}.py` — порт `IBalanceWriter` + `BalanceKeyError(key, segment, reason)`.
- `application/admin/{grant_length,grant_thickness,get_balance_value,set_balance_value,_balance_path}.py` — 4 use-case-а экономики + хелпер dotted-path lookup-а.
- `infrastructure/balance/writer.py` — `YamlBalanceWriter` (atomic + flock + hot-reload через `IBalanceReloader`).
- `bot/handlers/admin_economy.py` — 4 handler-а + 3 dispatch-функции + `CONFIRM_DISPATCHERS` registry + `ConfirmDispatchDeps`.
- `bot/handlers/_idempotency.py` — `build_admin_idempotency_key(admin_tg_id, command, target, when)`.
- `bot/handlers/admin_support.py` — `handle_confirm` теперь делегирует на `CONFIRM_DISPATCHERS` для всех kind-ов, включая `"ban"` (с 2.5-D.9 / коммит `3ef53b7`); inline-логика удалена.
- `bot/presenters/admin_economy.py` — 5 презентеров (`GrantLength/Thickness/GetBalance/SetBalance/IdempotencyReplay`).
- `bot/main.py::Container` — DI всех 11 admin-use-case-ов (с 2.5-A: `request_admin_confirm`/`verify_admin_confirm`; с 2.5-B: `find_players`/`get_player_card`/`freeze_player`/`unfreeze_player`/`ban_player`; с 2.5-C: `grant_length`/`grant_thickness`/`get_balance_value`/`set_balance_value`).
- Старые `bot/handlers/admin.py` (`/balance_reload`, `/admin_stats`, `/set_max_dau`, `/anticheat_unban`) — пока на старой авторизации use-case-уровня; в 2.5-D будут перенесены под `AdminGuard` + RBAC.

**Скоуп Спринта 2.5 (4 PR-а):**
- ~~**2.5-A**~~ ✅ закрыт PR #79 (`b358349`) — каркас `admin_audit_log` + `AdminGuard` + TOTP-confirm.
- ~~**2.5-B**~~ ✅ закрыт PR #81 (`3653e40`) — команды поддержки + общий `/confirm`-dispatcher.
- ~~**2.5-C**~~ ✅ закрыт PR #83 (`10b3ee6`) — команды экономики + registry-pattern в `/confirm` + atomic balance-writer + idempotency.
- **2.5-D** (текущий PR / финал): кланы (`/clan`, `/freeze_clan`, `/unfreeze_clan`, `/clan_daily_head_history`) + `/announce` + `/audit` + `/admin_setup_totp` + миграция старых `/balance_reload` / `/admin_stats` / `/set_max_dau` / `/anticheat_unban` под `AdminGuard` + RBAC + `docs/admin_runbook.md`.

**`make ci` локально на feature-ветке (после D.1+D.2+D.3+D.5+D.8+D.9):** зелёный — 3262 passed / 1 skipped, coverage 96.00%.

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `2.5 — Расширенный админ-интерфейс в боте` |
| **Активный PR / шаг** | **2.5-D** (финал): кланы (`/clan`, `/freeze_clan`, `/unfreeze_clan`, `/clan_daily_head_history`) + `/announce` + `/audit` + `/admin_setup_totp` + миграция старых admin-команд под `AdminGuard` + RBAC + `docs/admin_runbook.md` |
| **Активная feature-ветка** | `devin/1778101600-sprint-2-5-d-final` (создана от `main = d2f7cb4`) |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `d2f7cb4` (мерж PR #84 «postmerge-доки 2.5-C») |
| **Последний коммит на feature-ветке** | `ba04dc5` docs(2.5-D): sync current_tasks после D.1+D.2+D.3 (до коммита по D.8) |
| **PR (если открыт)** | будет открыт после серии D.1+D.2+D.3+D.5+D.8+D.9; D.4/D.6/D.7/D.10–D.12 — отдельной серией коммитов на той же ветке (append) |
| **CI статус** | зелёный локально на feature-ветке (после D.1+D.2+D.3+D.5+D.8+D.9): `make ci` — 3262 passed / 1 skipped, coverage 96.00% |
| **Связанная задача в `development_plan.md`** | §5 / Спринт 2.5 / задачи 2.5.3 (кланы), 2.5.6 (`/announce`), 2.5.7 (`/audit`), 2.5.8 (RBAC + `/admin_setup_totp`), 2.5.9 (миграция старых команд) |
| **Связанная спецификация в `game_design.md`** | §18.6 (RBAC + 2FA для всех ролей), §10–11 (клановая механика), §17 (моратории / `/announce` для broadcast), §18.6.5 (`/audit` — last 50 records по фильтрам) |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**PR 2.5-D — финальный спринт админ-интерфейса:**

- [x] **2.5-D.1 — `/clan <id|chat_id>`** — read-only карточка клана: id, chat_id, chat_kind, title, status (active/frozen), member_count, active_member_count, total_length_cm, лидер каравана + список участников (как сводка `/player`). Use-case `GetClanCard(actor_tg_id, query)` с двойным lookup-ом (сначала по внутреннему `Clan.id`, потом по Telegram `chat_id`). Без TOTP. Audit: `ADMIN_CLAN_LOOKUP` (новое значение `AdminAuditAction`, добавлено в D.5-этапе). Локаль `admin-clan-*` (RU + EN). Тесты: 9 unit (use-case), 8 unit (handler) — handler покрыт включая default-locale-кейс.
- [x] **2.5-D.2 — `/freeze_clan <id|chat_id> [reason]` / `/unfreeze_clan <id|chat_id>`** — обратимая ручная заморозка/разморозка клана админом (без TOTP, как `/freeze`/`/unfreeze` для игроков). Use-cases `FreezeClanAdmin` / `UnfreezeClanAdmin`. Идемпотентны (no-op если уже frozen/active, audit не пишется). Audit: `ADMIN_CLAN_FROZEN` / `ADMIN_CLAN_UNFROZEN` (новые admin-аудит-действия — отдельно от системных `CLAN_FREEZE` из 1.1.6). Локали `admin-freeze-clan-*` / `admin-unfreeze-clan-*` (RU+EN). Тесты: 12 unit (use-cases), 17 unit (handlers).
- [x] **2.5-D.3 — `/clan_daily_head_history <id|chat_id> [N=10]`** — read-only история последних N назначений «Главы клана дня» (дата, игрок, bonus_cm, источник). Use-case `GetClanDailyHeadHistory(actor, query, limit=10)` через `IDailyHeadRepository.list_recent_for_clan(clan_id, limit)`. Без TOTP. Audit: `ADMIN_CLAN_LOOKUP` (тот же ключ, что у `/clan`). Локали `admin-clan-daily-head-history-*` (RU+EN). Тесты: 10 unit (use-case), 11 unit (handler).
- [ ] **2.5-D.4 — `/announce <ru|en> <message>`** — broadcast всем активным игрокам (или с фильтром по локали). Use-case `BroadcastAnnouncement(admin_id, locale_filter, message)`. **TOTP-обязательная** (массовая рассылка — высокий риск). Реализация рассылки: фоновая job через `IDelayedJobScheduler` с throttling (макс N сообщений/сек чтобы не упереться в rate-limit Telegram); progress-update в чат админу (стартовое «отправляю N игрокам», финальное «отправлено / failed / blocked»). Audit: `ADMIN_BROADCAST_SENT` (с `recipient_count`/`failed_count`). Локаль `admin-announce-*`.
- [x] **2.5-D.5 — `/audit [target_tg_id|-] [action|-] [N]`** — query последних N записей `admin_audit_log` с опциональными фильтрами по `admin_id` и `action`. Use-case `GetAdminAuditTrail(actor_tg_id, *, target_admin_tg_id?, action_value?, limit=20)` через новый read-port `IAdminAuditQuery.list_recent(...)` (отдельный от write-side `IAdminAuditLogger` по ISP). Read-only, без TOTP. Сам факт чтения логируется как `ADMIN_AUDIT_QUERIED`. Локаль `admin-audit-*` (RU + EN). Реализация — `SqlAlchemyAdminAuditQuery` (один SELECT + JOIN к `admins`, без N+1).
- [ ] **2.5-D.6 — `/admin_setup_totp`** — выдача нового TOTP-секрета админу: генерация secret через `pyotp.random_base32()`, сохранение в `Admin.totp_secret_encrypted` (через `IAdminRepository.set_totp_secret`), отправка QR-кода (или otpauth-URL) в личку админу. **Защищена паролем-инициализатором** (`bootstrap_admin_password` из `BootstrapSettings` — единоразовый пароль из ENV, который ломается после первого использования). Audit: `ADMIN_TOTP_SETUP`. Локаль `admin-setup-totp-*`. ⚠ опасно — выдача QR-кода через Telegram-канал; рассмотреть alternative: вывод только в логи бота (читаемые только из VM).
- [ ] **2.5-D.7 — Миграция старых admin-команд под `AdminGuard` + RBAC.** В коде сейчас `bot/handlers/admin.py` содержит `/balance_reload`, `/admin_stats`, `/set_max_dau`, `/anticheat_unban` — они авторизуются через `IAdminRepository.get_by_tg_id` внутри use-case-ов (legacy-путь, до 2.5-A). Переписать так, чтобы `IsAdminFilter` работал на router-е (как в 2.5-B/C), а use-case-ы получали `Admin` из `data["admin"]` (от `AdminGuard`). По возможности — добавить в `CONFIRM_DISPATCHERS` registry (`/balance_reload` уже мутирующая → возможно стоит сделать TOTP-обязательной).
- [x] **2.5-D.8 — RBAC** (`game_design.md` §18.6.2): домен — whitelist-enum `AdminCommandKind` (27 команд) + порт `IAdminAuthorizationPolicy.is_authorized(admin, command_kind) -> bool` + дефолтная реализация `RoleBasedAdminAuthorizationPolicy` с матрицей `(role × command_kind) → frozenset[AdminRole]`, fail-closed (команда без правила всегда отказывает; неактивный админ всегда отказывает). Иерархия (без «суперсетов» — каждая ячейка явная): `READ_ONLY` — все read-side; `SUPPORT` — `freeze_*`/`unfreeze_*`/`ban_player` + read-side; `ECONOMIST` — `grant_*`/`set_balance_value`/`reload_balance` + read-side; `SUPER_ADMIN` — всё, включая `lift_anticheat_ban`/`set_max_dau`/`broadcast_announcement`/`setup_totp`. Application-helper `ensure_admin_authorized(...)` в `application/admin/_authorization.py` — открывает **отдельный, короткоживущий** UoW и пишет `ADMIN_AUTHORIZATION_DENIED` до того, как поднять `AdminAuthorizationDeniedError`, чтобы попытка эскалации была зафиксирована независимо от основной транзакции use-case-а. Все 13 admin-use-case-ов (`find_players`, `get_player_card`, `freeze_player`, `unfreeze_player`, `ban_player`, `request_admin_confirm`, `verify_admin_confirm`, `grant_length`, `grant_thickness`, `get_balance_value`, `set_balance_value`, `get_admin_audit_trail`, `get_clan_card`, `freeze_clan_admin`, `unfreeze_clan_admin`, `get_clan_daily_head_history`) принимают `authz: IAdminAuthorizationPolicy` и зовут helper до открытия основного UoW. Колонка `Admin.role` (enum) уже существовала с миграции `0001` — отдельная миграция под D.8 не нужна. DI: `Container.admin_authz: IAdminAuthorizationPolicy`, инстанциируется как `RoleBasedAdminAuthorizationPolicy()` в `build_container()`. Тесты: матрица `RoleBasedAdminAuthorizationPolicy` (29 случаев параметризованных + super-admin allows-all + inactive-admin denied) + helper `ensure_admin_authorized` (allow no-op / deny + audit + raise / reason_suffix). Двойная проверка по слоям: интеграционные тесты use-case-ов через `FakeAdminAuthzAllowAll` подтверждают, что DI пробрасывает `authz` корректно; legacy-команды `/balance_reload`/`/admin_stats`/`/set_max_dau`/`/anticheat_unban` останутся вне RBAC до 2.5-D.7 (там же — переход на `AdminGuard`).
- [x] **2.5-D.9 — Перенести `command_kind="ban"` из inline в `CONFIRM_DISPATCHERS` registry.** ✅ закрыт коммитом `3ef53b7` на ветке `devin/1778101600-sprint-2-5-d-final`: `_dispatch_ban` добавлен в `bot/handlers/admin_economy.py`, зарегистрирован в `CONFIRM_DISPATCHERS`, inline-кейс из `bot/handlers/admin_support.py` удалён.
- [ ] **2.5-D.10 — `docs/admin_runbook.md`** — документация для команды поддержки/экономистов: список всех админ-команд, какая роль нужна, какие требуют TOTP, как настроить `pyotp` в их Authenticator, что делать при потере 2FA, как читать `/audit`. Не дублировать `game_design.md §18.6` — runbook это операционная инструкция, а не спека.
- [ ] **2.5-D.11 — Тесты:** unit на каждый новый use-case (≥4 кейса), integration-тесты на repo-методы (clan freeze/unfreeze, audit query), e2e на handler-ы и TOTP-flow `/announce`. Покрытие RBAC: каждая команда тестируется на отказ для недостаточной роли.
- [ ] **2.5-D.12 — Локали** всех новых ключей `admin-clan-*` / `admin-freeze-clan-*` / `admin-unfreeze-clan-*` / `admin-clan-daily-head-history-*` / `admin-announce-*` / `admin-audit-*` / `admin-setup-totp-*` / `admin-rbac-*` в `locales/{ru,en}.ftl`.
- [ ] **Перед PR:** прогон `make ci` зелёный, lint/typecheck/import-linter ✅.
- [ ] **Перед мерджем:** postmerge — запись 2.5-D в `history.md`; sync `current_tasks.md` под Спринт 2.6 (или Фазу 3, если 2.5 целиком закрыт).

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты. Не дублируй ТЗ из `development_plan.md` — пиши только то, что важно для **текущего PR**.

**Текущая дельта (PR 2.5-D будет про):**
- Все 7 новых команд используют существующий `AdminGuard` middleware из 2.5-A + `IsAdminFilter` на router-е (как в 2.5-B/C). `data["admin"]` уже наполняется — handler-ы должны его читать (а не перепроверять через `IAdminRepository.get_by_tg_id`).
- `/freeze_clan`/`/unfreeze_clan` — обратимые (без TOTP). `/announce`/`/admin_setup_totp` — мутирующие/высокорисковые → TOTP-обязательные → попадают в `CONFIRM_DISPATCHERS` registry (расширить `ConfirmDispatchDeps` или сделать его опциональным; см. D.9).
- `/audit` — read-side, требует нового read-порта на `IAdminAuditLogger` (или отдельный `IAdminAuditQuery`). Sql-импл уже есть для write-side (`SqlAlchemyAdminAuditLogger`); нужно дописать read-методы (`list_recent` с фильтрами `admin_id`/`action`/`occurred_at >= since`).
- `/announce` — реализация массовой рассылки. Нельзя слать в синхронном handler-е (Telegram timeout 30 сек, а 1000 игроков × 0.5 сек на сообщение = 500 сек). Нужна фоновая job через существующий `IDelayedJobScheduler` (APS), с throttling и progress-update обратно в чат админу.
- ~~**RBAC** (`Admin.role` enum + `IAdminAuthorizationPolicy.can(admin, command_kind)`) — это структурное изменение, затрагивает все админ-команды (включая старые из 2.5-B/C/legacy). Самый рискованный пункт спринта; стоит отдельным первым коммитом, чтобы можно было его откатить если что-то сломается.~~ ✅ закрыто в D.8: `IAdminAuthorizationPolicy.is_authorized(admin, command_kind)` + `RoleBasedAdminAuthorizationPolicy` с матрицей `(role × command_kind)` (fail-closed) + `application/admin/_authorization.py::ensure_admin_authorized(...)` (audit-denied в отдельном UoW + `AdminAuthorizationDeniedError`). Все 13 admin-use-case-ов уже принимают `authz: IAdminAuthorizationPolicy` и зовут helper до основного UoW. **Колонка `Admin.role` уже была в миграции `0001`** — отдельная миграция `0017_admin_role` не понадобилась. RBAC для старых команд (`/balance_reload`/`/admin_stats`/`/set_max_dau`/`/anticheat_unban`) добавится в D.7 при миграции их под `AdminGuard`.
- **Миграция старых команд** (D.7) — рискованная: `bot/handlers/admin.py` имеет 4 команды на legacy-авторизации; переписать их без потери функционала, добавить тесты на `AdminGuard`-flow + RBAC.
- Затронутые слои: `domain/clan/{entities,repositories}.py` (`Clan.freeze/unfreeze` + repo-методы), `domain/admin/ports/{admin_audit,authorization}.py` (read-side audit-port + RBAC-port), `application/admin/{get_clan_card,freeze_clan,unfreeze_clan,clan_daily_head_history,broadcast_announcement,get_admin_audit_trail,setup_totp}.py` (7 новых use-case-ов), `bot/handlers/{admin_clan,admin_communication,admin_audit,admin_setup}.py` (новые router-ы) + регистрация, `bot/handlers/admin.py` (рефактор legacy-команд), `bot/main.py` (DI 7 use-case-ов + `IAdminAuthorizationPolicy`), миграция `0017_admin_role`, `locales/{ru,en}.ftl`, `docs/admin_runbook.md`.

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
