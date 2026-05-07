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

**На `main`:** последний смерженный PR — **postmerge 2.5-D.11** ([PR #95](https://github.com/Pipirkawar/PipirkaWar/pull/95), коммит `61b33f1`) — sync `history.md` + `current_tasks.md` под `main = c434b3d`, без изменений кода. Перед ним: 2.5-D.11 (PR #94, `c434b3d`) — exhaustive RBAC-матрица в unit-тестах; postmerge 2.5-D.10 (PR #93, `3288fc6`); 2.5-D.10 (PR #92, `a8f26e5`) — новый файл `docs/admin_runbook.md`; postmerge 2.5-D.6 (PR #91, `cb40c2e`); 2.5-D.6 (PR #90, `4c2b100`); postmerge 2.5-D.4 (PR #89, `8df66e7`); 2.5-D.4 (PR #88, `774bd7c`). До этого: 2.5-A (PR #79), 2.5-B (PR #81), 2.5-C (PR #83), постмердж-доки (PR #84), 2.5-D часть 1 (PR #85), 2.5-D.7 (PR #86), postmerge 2.5-D.7 (PR #87). **Спринт 2.5 закрывается этим PR-ом — D.12 — последний пункт чек-листа.**

**Активная feature-ветка:** `devin/1778167492-sprint-2-5-d.12-locales` (текущий PR — 2.5-D.12: аудит локалей `admin-*` в `locales/{ru,en}.ftl`, дедупликация 5 silently-shadowed-ключей `admin-confirm-*`, удаление 2 orphan-ключей-наследия 2.5-A.3, новый lint-тест `tests/unit/locales/test_admin_keys_lint.py`).

**Что уже есть в коде после postmerge 2.5-D.11 (PR #95) — в production-коде ничего нового (D.11 + postmerge = test-only/docs-only); срез кода отражает состояние после 2.5-D.6 (PR #90); в тестах появилась exhaustive RBAC-матрица:**
- `domain/admin/authorization.py` — `AdminCommandKind` (whitelist 22 команды, включая `BROADCAST_ANNOUNCEMENT` и `SETUP_TOTP`), `IAdminAuthorizationPolicy`, `RoleBasedAdminAuthorizationPolicy` (fail-closed-матрица; `SETUP_TOTP` → только `SUPER_ADMIN`), `AdminAuthorizationDeniedError`.
- `application/admin/_authorization.py` — helper `ensure_admin_authorized(...)` с отдельным коротким UoW для `ADMIN_AUTHORIZATION_DENIED`-аудита.
- **Все 19 admin-use-case-ов** (с D.6 добавился `SetupAdminTotp`) принимают `authz: IAdminAuthorizationPolicy` и зовут helper до основного UoW.
- `bot/main.py::build_container` — `admin_audit: IAdminAuditLogger` + `admin_authz: IAdminAuthorizationPolicy` создаются раньше, пробрасываются во все admin-use-case-ы. В D.6 добавлен production-адаптер `PyOtpTotpSecretGenerator` (из `infrastructure/admin/pyotp_totp_secret_generator.py`) и `BootstrapSettings.admin_password` (env `BOOTSTRAP_ADMIN_PASSWORD`).
- `CONFIRM_DISPATCHERS` registry — **5** TOTP-обязательных команд (`grant_length`, `grant_thickness`, `set_balance_value`, `ban_player`, `broadcast_announcement`); `/admin_setup_totp` НЕ требует TOTP-confirm (это команда выдачи самого TOTP — chicken-and-egg).
- `domain/admin/`: `Admin.totp_secret: str | None` (миграция `0017_admins_totp_secret`, BASE32 plain-text), новый порт `ITotpSecretGenerator.generate() -> str`, новый абстрактный метод `IAdminRepository.set_totp_secret(*, admin_id, secret)`, новые ошибки `BootstrapPasswordNotConfiguredError`/`BootstrapPasswordInvalidError`/`TotpAlreadyConfiguredError` (из `domain/admin/setup_totp_errors.py`), `AdminAuditAction.ADMIN_TOTP_SETUP`.
- `infrastructure/admin/pyotp_totp_verifier.py::PyOtpTotpVerifier` — проверка 6-значных кодов с `valid_window=1` (D.4-prep).
- **Тесты RBAC после 2.5-D.11 (PR #94):** `tests/unit/domain/admin/test_authorization.py` — exhaustive matrix `AdminRole × AdminCommandKind` (88 параметризованных кейсов через `itertools.product` из независимой спецификации §18.6.2 ГДД) + consistency-test (все enum-значения покрыты ожиданиями) + per-role inactive-deny (4 кейса). Старый hand-picked класс (~30 кейсов) сохранён как human-readable reference. `tests/unit/application/admin/test_authorization_helper.py` — 11-кейсовый parametrized-test, что helper НЕ затирает `actor_role`/`command_kind` константой — пробрасывает в audit-after-snapshot, в reason, в исключение.
- **Что меняет 2.5-D.12 (этот PR):** ничего в production-коде. В `locales/{ru,en}.ftl` удалена секция-наследие Sprint 2.5-A.3 («Admin — TOTP confirmation of dangerous commands») с 7 ключами: 5 из них дублировались в section /confirm 2.5-B (Fluent молча оставлял первое определение, из-за чего админам отдавались устаревшие тексты без `<code>{ $token }</code>` substitution-а), 2 (`admin-confirm-prompt`, `admin-confirm-success`) — orphan-ы, не зацепленные из кода (заменены per-команда `*-confirm-issued`/`admin-confirm-success-{cmd}`). В `tests/unit/locales/test_admin_keys_lint.py` — 11-параметризованный lint-тест из 5 классов: `TestNoDuplicateKeys` (дубль = silent shadow в Fluent, ловить на CI), `TestLocaleParity` (RU↔EN parity full + admin-only), `TestAdminKeysCoverage` (used in src ⊆ defined in locale), `TestNoOrphanAdminKeys` (defined in locale ⊆ used in src), `TestSanityCounts` (guard, что AST-обход и regex не сломались).

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
- ~~**2.5-D.11**~~ ✅ закрыт PR #94 (`c434b3d`) — exhaustive RBAC-матрица в `tests/unit/domain/admin/test_authorization.py` (88 кейсов через `itertools.product` + consistency-test, что все `AdminCommandKind` покрыты ожиданиями + inactive-deny per-role) + parametrized helper-test в `tests/unit/application/admin/test_authorization_helper.py` (11 кейсов: verify `actor_role`/`command_kind` propagation для каждой роли × запрещённой команды). Без изменений production-кода / локалей / миграций. **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.11`.**
- ~~**postmerge 2.5-D.11**~~ ✅ закрыт PR #95 (`61b33f1`) — sync `history.md` (+1 запись `2026-05-07 — Спринт 2.5-D.11`) + `current_tasks.md` (снимок / позиция / чек-лист под `main = c434b3d`). Без изменений кода.
- **Текущий PR (2.5-D.12):** аудит локалей `admin-*` — дедупликация 5 silently-shadowed-ключей `admin-confirm-*` в обеих локалях, удаление 2 orphan-ключей `admin-confirm-prompt`/`admin-confirm-success` (наследие 2.5-A.3), новый lint-тест `tests/unit/locales/test_admin_keys_lint.py` (11 кейсов: no-duplicates / RU↔EN parity / used⊆defined / defined⊆used / sanity-counts). Без изменений production-кода и миграций.
- **Дальше:** Спринт 2.5 закрыт — следующий — Спринт 3.

**`make ci` локально на `main` (после 2.5-D.11 = `c434b3d`):** зелёный — **3406 passed / 1 skipped** (+69 кейсов vs `3288fc6`), coverage **95.90%** (без падения), ~1:34. На текущей feature-ветке (postmerge — docs-only) `make ci` идентичен main, будет прогон перед PR-ом.

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `2.5 — Расширенный админ-интерфейс в боте (финал)` |
| **Активный PR / шаг** | **2.5-D.12** — аудит локалей `admin-*` в `locales/{ru,en}.ftl`: дедупликация 5 silently-shadowed-ключей `admin-confirm-*`, удаление 2 orphan-ключей-наследия 2.5-A.3 (`admin-confirm-prompt`, `admin-confirm-success`), новый lint-тест `tests/unit/locales/test_admin_keys_lint.py` (11 кейсов). Без изменений production-кода и миграций. |
| **Активная feature-ветка** | `devin/1778167492-sprint-2-5-d.12-locales` (создана от `main = 61b33f1`) |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `61b33f1` (мерж PR #95 «docs(postmerge 2.5-D.11): history.md +1 запись, current_tasks.md sync под D.11-в-main») |
| **Последний коммит на feature-ветке** | будет зафиксирован при первом push-е |
| **PR (если открыт)** | будет открыт после локального зелёного `make ci` |
| **CI статус** | на main зелёный: `make ci` — 3406 passed / 1 skipped, coverage 95.90% |
| **Связанная задача в `development_plan.md`** | §5 / Спринт 2.5 / задача 2.5.10 (локали admin-команд). D.12 — закрытие пробела «нет lint-проверки RU↔EN parity и duplicate-detection в .ftl». |
| **Связанная спецификация в `game_design.md`** | §18.6 (admin-интерфейс) — все admin-команды двуязычные; §0 — i18n-канон через Mozilla Fluent. |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**Текущий PR — 2.5-D.12 (аудит локалей):**

- [x] `git fetch && git checkout main && git pull` — получить `main = 61b33f1`.
- [x] Создать ветку `devin/1778167492-sprint-2-5-d.12-locales` от `main`.
- [x] Собрать реестр used `admin-*` ключей (AST-обход `src/`) — 147 ключей в 9 admin-presenter-ах + handler-ах.
- [x] Сверить с присутствующими в `locales/{ru,en}.ftl` — выявлено: 154 `admin-*` ключа в каждой локали (полная RU↔EN parity); 5 дубликатов `admin-confirm-*` (`token-not-found`/`token-expired`/`totp-not-configured`/`admin-mismatch`/`code-invalid`) — Fluent молча оставляет первое определение, второе игнорируется без warning-а; 2 orphan-ключа (`admin-confirm-prompt`, `admin-confirm-success`) не зацеплены из кода (наследие планируемого generic confirm-flow из 2.5-A.3, вытеснённого per-командой `*-confirm-issued`/`admin-confirm-success-{cmd}`).
- [x] Удалить из `locales/ru.ftl` (-20 строк) и `locales/en.ftl` (-18 строк) section-header-комментарий «## Admin — TOTP confirmation of dangerous commands (Sprint 2.5-A.3)» + 7 obsolete-ключей. Сохранить второе определение каждого из 5 дублей — оно использует `<code>{ $token }</code>` substitution и согласуется с пасстерном остальных `admin-confirm-*-success-{cmd}`/`admin-confirm-unknown-command-kind`.
- [x] Создать `tests/unit/locales/__init__.py` + `tests/unit/locales/test_admin_keys_lint.py` (11 параметризованных кейсов из 5 классов).
- [x] Обновить `docs/current_tasks.md` под D.12 (снимок / позиция / чек-лист / дельта).
- [ ] **Перед PR:** `make ci` локально зелёный (ожидание: 3417 passed, 95.90% — добавлено 11 lint-кейсов, удалены 7 .ftl-ключей).
- [ ] Открыть PR `feat(2.5-D.12): аудит/дедупликация admin-* локалей + lint-тест RU↔EN parity`.
- [ ] **После мерджа:** Спринт 2.5 закрыт. Postmerge-PR sync `history.md` + `current_tasks.md`.

**Спринт 2.5 — что ещё осталось (детализация на референс):**

- [x] **2.5-D.4 — `/announce <ru|en|*> <message>`** ✅ закрыт PR #88 (`774bd7c`). Two-phase flow с TOTP-confirm: Phase 1 (`BroadcastAnnouncement`) валидирует локаль/длину, делает RBAC-проверку (`SUPER_ADMIN`), pre-flight `list_active_for_broadcast(...)` и выдаёт `/confirm`-токен; Phase 2 (`RunBroadcastAnnouncement` через `CONFIRM_DISPATCHERS["broadcast_announcement"]`) запускает фоновую рассылку через `IBroadcastTaskSpawner` с throttle `25 msg/sec` (`BATCH_SIZE=25` × `BATCH_INTERVAL=1.0s`). Production: `AiogramBroadcastSender`/`AsyncIOBroadcastTaskSpawner`. Audit: `ADMIN_BROADCAST_SENT`. Локали: 11 ключей `admin-announce-*` (RU/EN). **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.4`.**
- [x] **2.5-D.6 — `/admin_setup_totp <bootstrap_password>`** ✅ закрыт PR #90 (`4c2b100`). Self-service-команда генерирует BASE32-секрет (`pyotp.random_base32()`), сохраняет в `Admin.totp_secret` через `IAdminRepository.set_totp_secret(...)`, выдаёт `ADMIN_TOTP_SETUP`-audit. Защита: RBAC (`SUPER_ADMIN`) + constant-time-сравнение пароля (`hmac.compare_digest`) + idempotency (`TotpAlreadyConfiguredError` на повторный вызов). **Канал доставки секрета — bot-логи, а не Telegram-чат**: `secret` и `otpauth://`-URI пишутся в `structlog.info(event="admin_totp_setup", actor_tg_id=..., secret=..., provisioning_uri=...)`; в чат уходит только локализованный `admin-setup-totp-success` без секретного материала. Локали: 7 ключей `admin-setup-totp-*` (RU/EN). **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.6`.**
- [x] **2.5-D.8 — RBAC** (`game_design.md` §18.6.2) — закрыт PR #85. Whitelist-enum `AdminCommandKind` (22 команды) + `IAdminAuthorizationPolicy` + `RoleBasedAdminAuthorizationPolicy` (fail-closed-матрица) + helper `ensure_admin_authorized(...)`. RBAC для `BROADCAST_ANNOUNCEMENT` (`/announce`): только `SUPER_ADMIN` — это нужно для D.4. **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D часть 1/2`.** [legacy: ниже была развёрнутая инлайн-версия задачи; перенесена в history.md, чтобы не дублировать.] DI: `Container.admin_authz: IAdminAuthorizationPolicy`, инстанциируется как `RoleBasedAdminAuthorizationPolicy()` в `build_container()`. Тесты: после D.11 — exhaustive matrix `AdminRole × AdminCommandKind` (88 кейсов через `itertools.product` + consistency-test, что все enum-значения покрыты ожиданиями + per-role inactive-deny) + helper `ensure_admin_authorized` (allow no-op / deny + audit + raise / reason_suffix + parametrized verify `actor_role`/`command_kind` propagation). Двойная проверка по слоям: интеграционные тесты use-case-ов через `FakeAdminAuthzAllowAll` подтверждают, что DI пробрасывает `authz` корректно; legacy-команды `/balance_reload`/`/admin_stats`/`/set_max_dau`/`/anticheat_unban` останутся вне RBAC до 2.5-D.7 (там же — переход на `AdminGuard`).
- [x] **2.5-D.9 — Перенести `command_kind="ban"` из inline в `CONFIRM_DISPATCHERS` registry.** ✅ закрыт коммитом `3ef53b7` на ветке `devin/1778101600-sprint-2-5-d-final`: `_dispatch_ban` добавлен в `bot/handlers/admin_economy.py`, зарегистрирован в `CONFIRM_DISPATCHERS`, inline-кейс из `bot/handlers/admin_support.py` удалён.
- [x] **2.5-D.10 — `docs/admin_runbook.md`** ✅ закрыт PR #92 (`a8f26e5`). Новый файл ~324 строки, 10 секций: §0 канал интерфейса, §1 ролевая модель, §2 полный список admin-команд (live из кода), §3 `/admin_setup_totp` пошаговый флоу, §4 RBAC, §5 TOTP-confirm, §6 чтение `/audit`, §7 recovery 2FA (3 сценария), §8 ротация `BOOTSTRAP_ADMIN_PASSWORD`, §9 FAQ, §10 куда идти. Не дублирует `game_design.md §18.6` — ссылается. **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.10`.**
- [x] **2.5-D.11 — Доптесты RBAC** ✅ закрыт PR #94 (`c434b3d`). Exhaustive matrix `AdminRole × AdminCommandKind` (88 кейсов через `itertools.product` из независимой спецификации §18.6.2 ГДД) + consistency-test (все enum-значения покрыты ожиданиями) + per-role inactive-deny (4 кейса). Helper-coverage: 11-кейсовый parametrized-test, что helper НЕ затирает `actor_role`/`command_kind` константой (пробрасывает в audit-after-snapshot, reason, исключение). Без изменений production-кода. **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.11`.**
- [ ] **2.5-D.12 — Локали** — текущий PR. Исторический скоуп задачи: пройти по `locales/{ru,en}.ftl` и убедиться, что все `admin-*` ключи присутствуют двуязычно. По факту все 147 used-в-коде ключей уже присутствовали в обеих локалях, но обнаружено 5 silently-shadowed-дублей `admin-confirm-*` (Fluent молча даёт первое определение в production, тестам этого не видно из-за `_StubBundle`) + 2 orphan-ключа из 2.5-A.3, не зацепленных из кода. Скоуп D.12 фактически: удалить obsolete-секцию + добавить lint-тест, чтобы регрессия (новый ключ только в RU, или дубль, или мёртвый ключ) падала на CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты. Не дублируй ТЗ из `development_plan.md` — пиши только то, что важно для **текущего PR**.

**Текущий PR (2.5-D.12) — аудит и санитизация .ftl + lint-тест:**
- `locales/ru.ftl` (−20 строк) и `locales/en.ftl` (−18 строк) — удалена секция-наследие 2.5-A.3 «## Admin — TOTP confirmation of dangerous commands» (комментарий-заголовок ~6-7 строк + 7 ключей). 5 из них (`admin-confirm-totp-not-configured` / `*-token-not-found` / `*-token-expired` / `*-code-invalid` / `*-admin-mismatch`) были дубликатами keys-of-same-name из section «# /confirm (B.5)»; Mozilla Fluent при дублях молча использует первое определение и игнорирует второе без warning-а — из-за чего админам в production отдавались устаревшие тексты без `<code>{ $token }</code>` substitution-а, заданного во втором определении. 2 ключа (`admin-confirm-prompt`, `admin-confirm-success`) — orphan-ы, не зацепленные ни одним `MessageKey(...)` в `src/`: они проектировались как generic confirm-prompt/success в 2.5-A.3, но в 2.5-B флоу был раздроблен по командам (`admin-{cmd}-confirm-issued` + `admin-confirm-success-{cmd}`), и эти два ключа никогда не были зацеплены. Поведение admin-команд в production сохраняется идентичным — для пользователя меняются только тексты ошибок `/confirm`-handler-а: с лаконичных однострочных «⚠️Токен не найден» на богатые «❌ Токен <code>TOK-123</code> уже использован или не существует.» (т.е. админ начинает видеть, какой именно токен не нашёлся — это уже подразумевалось вторым определением, но не доходило до пользователя из-за дубля).
- `tests/unit/locales/__init__.py` (новый, пустой `__init__`) + `tests/unit/locales/test_admin_keys_lint.py` (новый, ~170 строк, 11 параметризованных кейсов из 5 классов): `TestNoDuplicateKeys[ru,en]` — Counter по Message-ID-ам через `fluent.syntax.parse`, ловит дубль; `TestLocaleParity::test_full_parity` + `test_admin_keys_parity` — set-симметрия RU vs EN; `TestAdminKeysCoverage[ru,en]::test_no_missing_admin_keys` — used in src ⊆ defined in locale; `TestNoOrphanAdminKeys[ru,en]::test_no_orphan_admin_keys` — defined-admin-* in locale ⊆ used-in-src; `TestSanityCounts` — guard ≥100 admin-ключей в коде и в каждой локали (защита от случайного «успеха» при пустых множествах).
- `docs/current_tasks.md` — обновлены 4 секции под D.12: «Снимок состояния» (main = `61b33f1`, D.12 — текущий PR, Спринт 2.5 закрывается), «Текущая позиция», «Чек-лист текущего PR» (D.12 шаги), «Что ровно сейчас в работе» (дельта D.12). D.12-пункт в «Спринт 2.5 — что ещё осталось» переписан с фактической дельтой.
- **Без изменений production-кода и миграций.** `make ci` локально зелёный: **3417 passed / 1 skipped** (+11 lint-кейсов vs `main`), coverage **95.90%** (без падения), ruff / mypy / import-linter — clean.

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
