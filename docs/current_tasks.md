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

**На `main`:** последний смерженный PR — **postmerge 2.5-D.10** ([PR #93](https://github.com/Pipirkawar/PipirkaWar/pull/93), коммит `3288fc6`) — sync `history.md` + `current_tasks.md` под D.10-в-main, без изменений кода. Перед ним: 2.5-D.10 (PR #92, `a8f26e5`) — новый файл `docs/admin_runbook.md`; postmerge 2.5-D.6 (PR #91, `cb40c2e`); 2.5-D.6 (PR #90, `4c2b100`); postmerge 2.5-D.4 (PR #89, `8df66e7`); 2.5-D.4 (PR #88, `774bd7c`). До этого: 2.5-A (PR #79), 2.5-B (PR #81), 2.5-C (PR #83), постмердж-доки (PR #84), 2.5-D часть 1 (PR #85), 2.5-D.7 (PR #86), postmerge 2.5-D.7 (PR #87). Из Спринта 2.5 остаётся: **D.11** (доптесты RBAC — текущий PR), **D.12** (расширение локалей).

**Активная feature-ветка:** `devin/1778164769-sprint-2-5-d.11-rbac-tests` (текущий PR — 2.5-D.11: exhaustive RBAC-матрица в unit-тестах + helper-coverage по `actor_role`. Без изменений production-кода).

**Что уже есть в коде после 2.5-D.10 (PR #92) — в коде ничего нового (D.10 = docs-only); срез кода отражает состояние после 2.5-D.6 (PR #90):**
- `domain/admin/authorization.py` — `AdminCommandKind` (whitelist 22 команды, включая `BROADCAST_ANNOUNCEMENT` и `SETUP_TOTP`), `IAdminAuthorizationPolicy`, `RoleBasedAdminAuthorizationPolicy` (fail-closed-матрица; `SETUP_TOTP` → только `SUPER_ADMIN`), `AdminAuthorizationDeniedError`.
- `application/admin/_authorization.py` — helper `ensure_admin_authorized(...)` с отдельным коротким UoW для `ADMIN_AUTHORIZATION_DENIED`-аудита.
- **Все 19 admin-use-case-ов** (с D.6 добавился `SetupAdminTotp`) принимают `authz: IAdminAuthorizationPolicy` и зовут helper до основного UoW.
- `bot/main.py::build_container` — `admin_audit: IAdminAuditLogger` + `admin_authz: IAdminAuthorizationPolicy` создаются раньше, пробрасываются во все admin-use-case-ы. В D.6 добавлен production-адаптер `PyOtpTotpSecretGenerator` (из `infrastructure/admin/pyotp_totp_secret_generator.py`) и `BootstrapSettings.admin_password` (env `BOOTSTRAP_ADMIN_PASSWORD`).
- `CONFIRM_DISPATCHERS` registry — **5** TOTP-обязательных команд (`grant_length`, `grant_thickness`, `set_balance_value`, `ban_player`, `broadcast_announcement`); `/admin_setup_totp` НЕ требует TOTP-confirm (это команда выдачи самого TOTP — chicken-and-egg).
- `domain/admin/`: `Admin.totp_secret: str | None` (миграция `0017_admins_totp_secret`, BASE32 plain-text), новый порт `ITotpSecretGenerator.generate() -> str`, новый абстрактный метод `IAdminRepository.set_totp_secret(*, admin_id, secret)`, новые ошибки `BootstrapPasswordNotConfiguredError`/`BootstrapPasswordInvalidError`/`TotpAlreadyConfiguredError` (из `domain/admin/setup_totp_errors.py`), `AdminAuditAction.ADMIN_TOTP_SETUP`.
- `infrastructure/admin/pyotp_totp_verifier.py::PyOtpTotpVerifier` — проверка 6-значных кодов с `valid_window=1` (D.4-prep).
- **Чего нет до D.11–D.12:** Coverage RBAC-deny по 27 `AdminCommandKind`-значениям × 5 ролей — неравномерное (D.11). Аудит локалей `admin-*` после D.1–D.9/D.4/D.6/D.10 — не пройден (D.12). `docs/admin_runbook.md` (D.10) — смержен в PR #92.

**Скоуп Спринта 2.5 (история PR-ов):**
- ~~**2.5-A**~~ ✅ закрыт PR #79 (`b358349`) — каркас `admin_audit_log` + `AdminGuard` + TOTP-confirm.
- ~~**2.5-B**~~ ✅ закрыт PR #81 (`3653e40`) — команды поддержки + общий `/confirm`-dispatcher.
- ~~**2.5-C**~~ ✅ закрыт PR #83 (`10b3ee6`) — команды экономики + registry-pattern + atomic balance-writer + idempotency.
- ~~**2.5-D часть 1**~~ ✅ закрыт PR #85 (`2b17c09`) — D.1+D.2+D.3+D.5+D.8+D.9 (клановые read/write команды, `/audit`, RBAC, registry-pattern для `"ban"`).
- ~~**2.5-D.7**~~ ✅ закрыт PR #86 (`12f9ea0`) — миграция legacy admin-команд под RBAC.
- ~~**postmerge 2.5-D.7**~~ ✅ закрыт PR #87 — sync док (без кода).
- ~~**2.5-D.4**~~ ✅ закрыт PR #88 (`774bd7c`) — `/announce` broadcast с TOTP-confirm + фоновый throttle.
- ~~**postmerge 2.5-D.4**~~ ✅ закрыт PR #89 (`8df66e7`) — sync `history.md` + `current_tasks.md` под D.4-в-main. Без изменений кода.
- ~~**2.5-D.6**~~ ✅ закрыт PR #90 (`4c2b100`) — `/admin_setup_totp <bootstrap_password>`: self-service выдача TOTP-секрета `SUPER_ADMIN`-у; constant-time-сравнение пароля; secret + `otpauth://`-URI пишутся ТОЛЬКО в structlog-логи; audit `ADMIN_TOTP_SETUP`.
- ~~**postmerge 2.5-D.6**~~ ✅ закрыт PR #91 (`cb40c2e`) — sync `history.md` + `current_tasks.md` под `main = 4c2b100`. Без изменений кода.
- ~~**2.5-D.10**~~ ✅ закрыт PR #92 (`a8f26e5`) — новый файл `docs/admin_runbook.md` (operational doc, ~324 строки, 10 секций). Без изменений кода.
- ~~**postmerge 2.5-D.10**~~ ✅ закрыт PR #93 (`3288fc6`) — sync `history.md` + `current_tasks.md` под `main = a8f26e5`. Без изменений кода.
- **Текущий PR (2.5-D.11):** exhaustive RBAC-матрица в `tests/unit/domain/admin/test_authorization.py` (88 кейсов через `itertools.product` + consistency-test, что все `AdminCommandKind` покрыты ожиданиями + inactive-deny per-role) + parametrized helper-test в `tests/unit/application/admin/test_authorization_helper.py` (verify `actor_role`/`command_kind` propagation для каждой роли × запрещённой команды). Без изменений production-кода / локалей / миграций.
- **Дальше:** D.12 (локали) — отдельным PR-ом.

**`make ci` локально на `main` (после postmerge 2.5-D.10 = `3288fc6`):** зелёный — 3337 passed / 1 skipped, coverage **95.90%** (~1:37). На текущей feature-ветке D.11 — будет прогон перед открытием PR (ожидание: ~3340+ тестов / 1 skipped, coverage не падает — добавляются только тесты).

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `2.5 — Расширенный админ-интерфейс в боте (финал)` |
| **Активный PR / шаг** | **2.5-D.11 (доптесты RBAC)**: exhaustive matrix `AdminRole × AdminCommandKind` (88 кейсов через `itertools.product`), consistency-test «все enum-значения покрыты ожиданиями», inactive-deny per-role; helper-test verify `actor_role`/`command_kind` propagation per role × forbidden command. Без изменений production-кода. |
| **Активная feature-ветка** | `devin/1778164769-sprint-2-5-d.11-rbac-tests` (создана от `main = 3288fc6`) |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `3288fc6` (мерж PR #93 «docs(postmerge 2.5-D.10): history.md +1 запись, current_tasks.md sync под D.10-в-main») |
| **Последний коммит на feature-ветке** | будет зафиксирован при первом push-е |
| **PR (если открыт)** | будет открыт после локального зелёного `make ci` |
| **CI статус** | на main зелёный: `make ci` — 3337 passed / 1 skipped, coverage 95.90% |
| **Связанная задача в `development_plan.md`** | §5 / Спринт 2.5 / задача 2.5.8 (общая инфраструктура `admin_audit_log` + RBAC); D.11 — закрытие пробела «неравномерное coverage RBAC-deny по `AdminCommandKind × AdminRole`» |
| **Связанная спецификация в `game_design.md`** | §18.6.2 (RBAC-матрица: какие роли что могут). Тесты независимо кодируют это правило, чтобы дрейф `_matrix` от ГДД падал на ревью. |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**Текущий PR — 2.5-D.11 (доптесты RBAC):**

- [x] Создать ветку `devin/1778164769-sprint-2-5-d.11-rbac-tests` от `main = 3288fc6`.
- [x] Прочитать `domain/admin/authorization.py` (`AdminCommandKind` ×22 значения, `RoleBasedAdminAuthorizationPolicy._matrix`) и `domain/admin/entities.py` (`AdminRole` ×4 значения).
- [x] В `tests/unit/domain/admin/test_authorization.py` независимо специфицировать ожидания (frozenset-группы по §18.6.2 ГДД: read-side / confirm-flow / support-ops / economy / super-only) — отдельно от `_matrix` в коде, чтобы любой дрейф ловился на CI.
- [x] Сгенерировать exhaustive-матрицу через `itertools.product(AdminRole, AdminCommandKind)` → 88 кейсов; добавить consistency-test (все enum-значения покрыты ожиданиями) + per-role inactive-deny-test.
- [x] В `tests/unit/application/admin/test_authorization_helper.py` параметризовать helper по 11 (роль × запрещённая команда), verify `actor_role`/`command_kind` в `after`-snapshot, в `reason`, в исключении.
- [x] Обновить «Снимок состояния», «Текущая позиция», «Что ровно сейчас в работе», «Чек-лист текущего PR» в `docs/current_tasks.md` под D.11.
- [ ] **Перед PR:** `make ci` локально зелёный (test-only PR — coverage не падает).
- [ ] Открыть PR `test(2.5-D.11): exhaustive RBAC matrix tests (22 × 4 = 88 cases) + helper-coverage по actor_role`.
- [ ] **После мерджа:** перейти к D.12 (локали).

**Спринт 2.5 — что ещё осталось (детализация на референс):**

- [x] **2.5-D.4 — `/announce <ru|en|*> <message>`** ✅ закрыт PR #88 (`774bd7c`). Two-phase flow с TOTP-confirm: Phase 1 (`BroadcastAnnouncement`) валидирует локаль/длину, делает RBAC-проверку (`SUPER_ADMIN`), pre-flight `list_active_for_broadcast(...)` и выдаёт `/confirm`-токен; Phase 2 (`RunBroadcastAnnouncement` через `CONFIRM_DISPATCHERS["broadcast_announcement"]`) запускает фоновую рассылку через `IBroadcastTaskSpawner` с throttle `25 msg/sec` (`BATCH_SIZE=25` × `BATCH_INTERVAL=1.0s`). Production: `AiogramBroadcastSender`/`AsyncIOBroadcastTaskSpawner`. Audit: `ADMIN_BROADCAST_SENT`. Локали: 11 ключей `admin-announce-*` (RU/EN). **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.4`.**
- [x] **2.5-D.6 — `/admin_setup_totp <bootstrap_password>`** ✅ закрыт PR #90 (`4c2b100`). Self-service-команда генерирует BASE32-секрет (`pyotp.random_base32()`), сохраняет в `Admin.totp_secret` через `IAdminRepository.set_totp_secret(...)`, выдаёт `ADMIN_TOTP_SETUP`-audit. Защита: RBAC (`SUPER_ADMIN`) + constant-time-сравнение пароля (`hmac.compare_digest`) + idempotency (`TotpAlreadyConfiguredError` на повторный вызов). **Канал доставки секрета — bot-логи, а не Telegram-чат**: `secret` и `otpauth://`-URI пишутся в `structlog.info(event="admin_totp_setup", actor_tg_id=..., secret=..., provisioning_uri=...)`; в чат уходит только локализованный `admin-setup-totp-success` без секретного материала. Локали: 7 ключей `admin-setup-totp-*` (RU/EN). **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.6`.**
- [x] **2.5-D.8 — RBAC** (`game_design.md` §18.6.2) — закрыт PR #85. Whitelist-enum `AdminCommandKind` (22 команды) + `IAdminAuthorizationPolicy` + `RoleBasedAdminAuthorizationPolicy` (fail-closed-матрица) + helper `ensure_admin_authorized(...)`. RBAC для `BROADCAST_ANNOUNCEMENT` (`/announce`): только `SUPER_ADMIN` — это нужно для D.4. **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D часть 1/2`.** [legacy: ниже была развёрнутая инлайн-версия задачи; перенесена в history.md, чтобы не дублировать.] DI: `Container.admin_authz: IAdminAuthorizationPolicy`, инстанциируется как `RoleBasedAdminAuthorizationPolicy()` в `build_container()`. Тесты: после D.11 — exhaustive matrix `AdminRole × AdminCommandKind` (88 кейсов через `itertools.product` + consistency-test, что все enum-значения покрыты ожиданиями + per-role inactive-deny) + helper `ensure_admin_authorized` (allow no-op / deny + audit + raise / reason_suffix + parametrized verify `actor_role`/`command_kind` propagation). Двойная проверка по слоям: интеграционные тесты use-case-ов через `FakeAdminAuthzAllowAll` подтверждают, что DI пробрасывает `authz` корректно; legacy-команды `/balance_reload`/`/admin_stats`/`/set_max_dau`/`/anticheat_unban` останутся вне RBAC до 2.5-D.7 (там же — переход на `AdminGuard`).
- [x] **2.5-D.9 — Перенести `command_kind="ban"` из inline в `CONFIRM_DISPATCHERS` registry.** ✅ закрыт коммитом `3ef53b7` на ветке `devin/1778101600-sprint-2-5-d-final`: `_dispatch_ban` добавлен в `bot/handlers/admin_economy.py`, зарегистрирован в `CONFIRM_DISPATCHERS`, inline-кейс из `bot/handlers/admin_support.py` удалён.
- [x] **2.5-D.10 — `docs/admin_runbook.md`** ✅ закрыт PR #92 (`a8f26e5`). Новый файл ~324 строки, 10 секций: §0 канал интерфейса, §1 ролевая модель, §2 полный список admin-команд (live из кода), §3 `/admin_setup_totp` пошаговый флоу, §4 RBAC, §5 TOTP-confirm, §6 чтение `/audit`, §7 recovery 2FA (3 сценария), §8 ротация `BOOTSTRAP_ADMIN_PASSWORD`, §9 FAQ, §10 куда идти. Не дублирует `game_design.md §18.6` — ссылается. **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.10`.**
- [ ] **2.5-D.11 — Тесты:** unit на каждый новый use-case (≥4 кейса), integration-тесты на repo-методы (clan freeze/unfreeze, audit query), e2e на handler-ы и TOTP-flow `/announce`. Покрытие RBAC: каждая команда тестируется на отказ для недостаточной роли.
- [ ] **2.5-D.12 — Локали** всех новых ключей `admin-announce-*` / `admin-setup-totp-*` / `admin-rbac-*` в `locales/{ru,en}.ftl` (ключи D.1/D.2/D.3/D.5 уже добавлены в PR #85; ключи D.7 — без новых строк).

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты. Не дублируй ТЗ из `development_plan.md` — пиши только то, что важно для **текущего PR**.

**Текущий PR (2.5-D.11) — только тесты, без изменений production-кода:**
- `tests/unit/domain/admin/test_authorization.py` — добавлены: independent-спецификация ожидаемых ролей по группам команд (frozenset-ы `_READ_SIDE_COMMANDS` / `_CONFIRM_FLOW_COMMANDS` / `_SUPPORT_OPS_COMMANDS` / `_ECONOMY_COMMANDS` / `_SUPER_ONLY_COMMANDS`), функция `_build_expected_matrix()` собирающая ожидания, `_FULL_MATRIX_CASES` через `itertools.product(AdminRole, AdminCommandKind) → 88 кейсов`, класс `TestRoleCommandMatrixExhaustive` с тремя методами: `test_consistency_every_command_kind_has_expected_rule`, `test_full_matrix_active_admin` (88 параметризованных кейсов), `test_inactive_admin_denied_for_every_role` (4 кейса). Существующие hand-picked tests (`TestRoleBasedAdminAuthorizationPolicy`) сохранены.
- `tests/unit/application/admin/test_authorization_helper.py` — добавлен `test_deny_audit_entry_carries_correct_actor_role_and_command` (11 параметризованных кейсов: `READ_ONLY × 3` + `SUPPORT × 4` + `ECONOMIST × 4`), verify что helper не «затирает» `actor_role`/`command_kind` константой, а пробрасывает их в `after`-snapshot, в `reason`, в `AdminAuthorizationDeniedError`.
- `docs/current_tasks.md` — обновлены 4 секции под D.11.
- **Без изменений production-кода / локалей / миграций.** `make ci` будет прогон перед открытием PR — coverage не падает (только добавляются тесты).

**Следующий PR (после мерджа этого) — D.12:**
- **D.12 — расширение локалей** — пройти по `locales/{ru,en}.ftl` и убедиться, что для всех admin-команд из D.1–D.9 + D.4 + D.6 + D.10 есть полный набор `*-confirm-issued`/`*-not-authorized`/`*-success`/etc. ключей. Linter-проверка соответствия RU/EN ключей (нет drift-а).

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
