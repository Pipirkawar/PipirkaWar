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

**На `main`:** последний смерженный PR — **2.5-D.12** ([PR #96](https://github.com/Pipirkawar/PipirkaWar/pull/96), коммит `e6f7512`) — аудит/дедупликация `admin-*` локалей в `locales/{ru,en}.ftl` + lint-тест RU↔EN parity. Без изменений production-кода и миграций. **Спринт 2.5 закрыт полностью.** Перед ним: postmerge 2.5-D.11 (PR #95, `61b33f1`); 2.5-D.11 (PR #94, `c434b3d`) — exhaustive RBAC-матрица в unit-тестах; postmerge 2.5-D.10 (PR #93, `3288fc6`); 2.5-D.10 (PR #92, `a8f26e5`) — новый файл `docs/admin_runbook.md`; postmerge 2.5-D.6 (PR #91, `cb40c2e`); 2.5-D.6 (PR #90, `4c2b100`); postmerge 2.5-D.4 (PR #89, `8df66e7`); 2.5-D.4 (PR #88, `774bd7c`). До этого: 2.5-A (PR #79), 2.5-B (PR #81), 2.5-C (PR #83), постмердж-доки (PR #84), 2.5-D часть 1 (PR #85), 2.5-D.7 (PR #86), postmerge 2.5-D.7 (PR #87). **Спринт 2.5 — все 12 пунктов чек-листа (`A`, `B`, `C`, `D.1–D.12`) — закрыт.**

**Активная feature-ветка:** `devin/1778168493-sprint-2-5-d.12-postmerge` (текущий PR — postmerge 2.5-D.12: sync `history.md` (+1 запись `2026-05-07 — Спринт 2.5-D.12`) + `current_tasks.md` (снимок / позиция / чек-лист под `main = e6f7512`, Спринт 2.5 закрыт). Без изменений кода).

**Что уже есть в коде после 2.5-D.12 (PR #96) — в production-коде ничего нового (D.12 = .ftl-cleanup + lint-test, без изменения public API); срез кода отражает состояние после 2.5-D.6 (PR #90); в тестах появилась exhaustive RBAC-матрица + lint-тест локалей:**
- `domain/admin/authorization.py` — `AdminCommandKind` (whitelist 22 команды, включая `BROADCAST_ANNOUNCEMENT` и `SETUP_TOTP`), `IAdminAuthorizationPolicy`, `RoleBasedAdminAuthorizationPolicy` (fail-closed-матрица; `SETUP_TOTP` → только `SUPER_ADMIN`), `AdminAuthorizationDeniedError`.
- `application/admin/_authorization.py` — helper `ensure_admin_authorized(...)` с отдельным коротким UoW для `ADMIN_AUTHORIZATION_DENIED`-аудита.
- **Все 19 admin-use-case-ов** (с D.6 добавился `SetupAdminTotp`) принимают `authz: IAdminAuthorizationPolicy` и зовут helper до основного UoW.
- `bot/main.py::build_container` — `admin_audit: IAdminAuditLogger` + `admin_authz: IAdminAuthorizationPolicy` создаются раньше, пробрасываются во все admin-use-case-ы. В D.6 добавлен production-адаптер `PyOtpTotpSecretGenerator` (из `infrastructure/admin/pyotp_totp_secret_generator.py`) и `BootstrapSettings.admin_password` (env `BOOTSTRAP_ADMIN_PASSWORD`).
- `CONFIRM_DISPATCHERS` registry — **5** TOTP-обязательных команд (`grant_length`, `grant_thickness`, `set_balance_value`, `ban_player`, `broadcast_announcement`); `/admin_setup_totp` НЕ требует TOTP-confirm (это команда выдачи самого TOTP — chicken-and-egg).
- `domain/admin/`: `Admin.totp_secret: str | None` (миграция `0017_admins_totp_secret`, BASE32 plain-text), новый порт `ITotpSecretGenerator.generate() -> str`, новый абстрактный метод `IAdminRepository.set_totp_secret(*, admin_id, secret)`, новые ошибки `BootstrapPasswordNotConfiguredError`/`BootstrapPasswordInvalidError`/`TotpAlreadyConfiguredError` (из `domain/admin/setup_totp_errors.py`), `AdminAuditAction.ADMIN_TOTP_SETUP`.
- `infrastructure/admin/pyotp_totp_verifier.py::PyOtpTotpVerifier` — проверка 6-значных кодов с `valid_window=1` (D.4-prep).
- **Тесты RBAC после 2.5-D.11 (PR #94):** `tests/unit/domain/admin/test_authorization.py` — exhaustive matrix `AdminRole × AdminCommandKind` (88 параметризованных кейсов через `itertools.product` из независимой спецификации §18.6.2 ГДД) + consistency-test (все enum-значения покрыты ожиданиями) + per-role inactive-deny (4 кейса). Старый hand-picked класс (~30 кейсов) сохранён как human-readable reference. `tests/unit/application/admin/test_authorization_helper.py` — 11-кейсовый parametrized-test, что helper НЕ затирает `actor_role`/`command_kind` константой — пробрасывает в audit-after-snapshot, в reason, в исключение.
- **Тесты локалей после 2.5-D.12 (PR #96):** `tests/unit/locales/test_admin_keys_lint.py` — 11 параметризованных кейсов в 5 классах: `TestNoDuplicateKeys[ru,en]` (Counter по Message-ID через `fluent.syntax.parse`, ловит silent-shadow в Fluent), `TestLocaleParity` (set-симметрия RU↔EN — full + admin-only), `TestAdminKeysCoverage[ru,en]` (used-in-src ⊆ defined-in-locale), `TestNoOrphanAdminKeys[ru,en]` (defined-in-locale ⊆ used-in-src), `TestSanityCounts` (guard ≥100 admin-ключей в коде и в каждой локали — защита от vacuously-passed на пустых множествах).
- **Что меняет postmerge 2.5-D.12 (этот PR):** ничего в коде / тестах / локалях / миграциях. Только sync `docs/history.md` (+1 запись `2026-05-07 — Спринт 2.5-D.12`) + `docs/current_tasks.md` (снимок / позиция / чек-лист под `main = e6f7512`, Спринт 2.5 закрыт).

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
- ~~**2.5-D.12**~~ ✅ закрыт PR #96 (`e6f7512`) — аудит/дедупликация `admin-*` локалей: удалена секция-наследие 2.5-A.3 в `locales/{ru,en}.ftl` (5 silently-shadowed-дублей `admin-confirm-*` + 2 orphan-ключа), новый lint-тест `tests/unit/locales/test_admin_keys_lint.py` (11 кейсов из 5 классов: no-duplicates / RU↔EN parity / used⊆defined / defined⊆used / sanity-counts). Без изменений production-кода и миграций. **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.12`.**
- **Текущий PR (postmerge 2.5-D.12):** sync `history.md` (+1 запись `2026-05-07 — Спринт 2.5-D.12`) + `current_tasks.md` (снимок / позиция / чек-лист под `main = e6f7512`, Спринт 2.5 закрыт). Без изменений кода.
- **Дальше:** Спринт 2.5 закрыт полностью — следующий — Спринт 3 (см. `docs/development_plan.md`).

**`make ci` локально на `main` (после 2.5-D.12 = `e6f7512`):** зелёный — **3417 passed / 1 skipped** (+11 lint-кейсов vs `c434b3d`), coverage **95.90%** (без падения), ~1:35. На текущей feature-ветке (postmerge — docs-only) `make ci` идентичен main, будет прогон перед PR-ом.

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `2.5 — Расширенный админ-интерфейс в боте (финал)` — **закрыт после мерджа PR #96.** Этот PR — finalisation-док. |
| **Активный PR / шаг** | **postmerge 2.5-D.12** — sync `history.md` (+1 запись `2026-05-07 — Спринт 2.5-D.12`) + `current_tasks.md` (снимок, позиция, чек-лист) под `main = e6f7512`. Без изменений кода / тестов / локалей / миграций. |
| **Активная feature-ветка** | `devin/1778168493-sprint-2-5-d.12-postmerge` (создана от `main = e6f7512`) |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `e6f7512` (мерж PR #96 «feat(2.5-D.12): аудит/дедупликация admin-* локалей + lint-тест RU↔EN parity») |
| **Последний коммит на feature-ветке** | будет зафиксирован при первом push-е |
| **PR (если открыт)** | будет открыт после локального зелёного `make ci` |
| **CI статус** | на main зелёный: `make ci` — 3417 passed / 1 skipped, coverage 95.90% |
| **Связанная задача в `development_plan.md`** | §5 / Спринт 2.5 / задача 2.5.10 (локали admin-команд); postmerge D.12 — синхронизация док под состояние после мерджа PR #96. |
| **Связанная спецификация в `game_design.md`** | §18.6 (admin-интерфейс) — все admin-команды двуязычные; §0 — i18n-канон через Mozilla Fluent. |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**Текущий PR — postmerge 2.5-D.12 (sync док, без изменений кода):**

- [x] Мердж PR #96 на `main` (коммит `e6f7512`).
- [x] `git fetch && git checkout main && git pull` — получить `main = e6f7512`.
- [x] Создать ветку `devin/1778168493-sprint-2-5-d.12-postmerge` от `main`.
- [x] Добавить в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.12: аудит/дедупликация admin-* локалей + lint-тест RU↔EN parity (закрытие Спринта 2.5)` (сверху) по канону: Что сделано / Результат / Заметки.
- [x] Обновить `docs/current_tasks.md` под новый снимок (`main = e6f7512`, postmerge-ветка, обновлённый чек-лист, Спринт 2.5 закрыт).
- [ ] **Перед PR:** `make ci` локально зелёный (docs-only — coverage не падает; ожидание: 3417 passed, 95.90%).
- [ ] Открыть PR `docs(postmerge 2.5-D.12): history.md +1 запись, current_tasks.md sync под D.12-в-main, Спринт 2.5 закрыт`.
- [ ] **После мерджа:** Спринт 2.5 закрыт полностью. Следующая работа — Спринт 3 (см. `docs/development_plan.md`).

**Спринт 2.5 — что ещё осталось (детализация на референс):**

- [x] **2.5-D.4 — `/announce <ru|en|*> <message>`** ✅ закрыт PR #88 (`774bd7c`). Two-phase flow с TOTP-confirm: Phase 1 (`BroadcastAnnouncement`) валидирует локаль/длину, делает RBAC-проверку (`SUPER_ADMIN`), pre-flight `list_active_for_broadcast(...)` и выдаёт `/confirm`-токен; Phase 2 (`RunBroadcastAnnouncement` через `CONFIRM_DISPATCHERS["broadcast_announcement"]`) запускает фоновую рассылку через `IBroadcastTaskSpawner` с throttle `25 msg/sec` (`BATCH_SIZE=25` × `BATCH_INTERVAL=1.0s`). Production: `AiogramBroadcastSender`/`AsyncIOBroadcastTaskSpawner`. Audit: `ADMIN_BROADCAST_SENT`. Локали: 11 ключей `admin-announce-*` (RU/EN). **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.4`.**
- [x] **2.5-D.6 — `/admin_setup_totp <bootstrap_password>`** ✅ закрыт PR #90 (`4c2b100`). Self-service-команда генерирует BASE32-секрет (`pyotp.random_base32()`), сохраняет в `Admin.totp_secret` через `IAdminRepository.set_totp_secret(...)`, выдаёт `ADMIN_TOTP_SETUP`-audit. Защита: RBAC (`SUPER_ADMIN`) + constant-time-сравнение пароля (`hmac.compare_digest`) + idempotency (`TotpAlreadyConfiguredError` на повторный вызов). **Канал доставки секрета — bot-логи, а не Telegram-чат**: `secret` и `otpauth://`-URI пишутся в `structlog.info(event="admin_totp_setup", actor_tg_id=..., secret=..., provisioning_uri=...)`; в чат уходит только локализованный `admin-setup-totp-success` без секретного материала. Локали: 7 ключей `admin-setup-totp-*` (RU/EN). **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.6`.**
- [x] **2.5-D.8 — RBAC** (`game_design.md` §18.6.2) — закрыт PR #85. Whitelist-enum `AdminCommandKind` (22 команды) + `IAdminAuthorizationPolicy` + `RoleBasedAdminAuthorizationPolicy` (fail-closed-матрица) + helper `ensure_admin_authorized(...)`. RBAC для `BROADCAST_ANNOUNCEMENT` (`/announce`): только `SUPER_ADMIN` — это нужно для D.4. **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D часть 1/2`.** [legacy: ниже была развёрнутая инлайн-версия задачи; перенесена в history.md, чтобы не дублировать.] DI: `Container.admin_authz: IAdminAuthorizationPolicy`, инстанциируется как `RoleBasedAdminAuthorizationPolicy()` в `build_container()`. Тесты: после D.11 — exhaustive matrix `AdminRole × AdminCommandKind` (88 кейсов через `itertools.product` + consistency-test, что все enum-значения покрыты ожиданиями + per-role inactive-deny) + helper `ensure_admin_authorized` (allow no-op / deny + audit + raise / reason_suffix + parametrized verify `actor_role`/`command_kind` propagation). Двойная проверка по слоям: интеграционные тесты use-case-ов через `FakeAdminAuthzAllowAll` подтверждают, что DI пробрасывает `authz` корректно; legacy-команды `/balance_reload`/`/admin_stats`/`/set_max_dau`/`/anticheat_unban` останутся вне RBAC до 2.5-D.7 (там же — переход на `AdminGuard`).
- [x] **2.5-D.9 — Перенести `command_kind="ban"` из inline в `CONFIRM_DISPATCHERS` registry.** ✅ закрыт коммитом `3ef53b7` на ветке `devin/1778101600-sprint-2-5-d-final`: `_dispatch_ban` добавлен в `bot/handlers/admin_economy.py`, зарегистрирован в `CONFIRM_DISPATCHERS`, inline-кейс из `bot/handlers/admin_support.py` удалён.
- [x] **2.5-D.10 — `docs/admin_runbook.md`** ✅ закрыт PR #92 (`a8f26e5`). Новый файл ~324 строки, 10 секций: §0 канал интерфейса, §1 ролевая модель, §2 полный список admin-команд (live из кода), §3 `/admin_setup_totp` пошаговый флоу, §4 RBAC, §5 TOTP-confirm, §6 чтение `/audit`, §7 recovery 2FA (3 сценария), §8 ротация `BOOTSTRAP_ADMIN_PASSWORD`, §9 FAQ, §10 куда идти. Не дублирует `game_design.md §18.6` — ссылается. **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.10`.**
- [x] **2.5-D.11 — Доптесты RBAC** ✅ закрыт PR #94 (`c434b3d`). Exhaustive matrix `AdminRole × AdminCommandKind` (88 кейсов через `itertools.product` из независимой спецификации §18.6.2 ГДД) + consistency-test (все enum-значения покрыты ожиданиями) + per-role inactive-deny (4 кейса). Helper-coverage: 11-кейсовый parametrized-test, что helper НЕ затирает `actor_role`/`command_kind` константой (пробрасывает в audit-after-snapshot, reason, исключение). Без изменений production-кода. **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.11`.**
- [x] **2.5-D.12 — Локали** ✅ закрыт PR #96 (`e6f7512`). Исторический скоуп задачи: пройти по `locales/{ru,en}.ftl` и убедиться, что все `admin-*` ключи присутствуют двуязычно. По факту все 147 used-в-коде ключей уже присутствовали в обеих локалях, но обнаружено 5 silently-shadowed-дублей `admin-confirm-*` (Fluent молча даёт первое определение в production, тестам этого не видно из-за `_StubBundle`) + 2 orphan-ключа из 2.5-A.3, не зацепленных из кода. Фактически выполнено: удалена obsolete-секция 2.5-A.3 в обеих локалях, добавлен lint-тест `tests/unit/locales/test_admin_keys_lint.py` (11 кейсов: no-duplicates / RU↔EN parity / used⊆defined / defined⊆used / sanity-counts). **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.12`.**

**Спринт 2.5 закрыт полностью — все 12 D-задач + A/B/C смержены в `main`.**

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты. Не дублируй ТЗ из `development_plan.md` — пиши только то, что важно для **текущего PR**.

**Текущий PR (postmerge 2.5-D.12) — только доки, без изменений кода / тестов / локалей / миграций:**
- `docs/history.md` — добавлена запись `2026-05-07 — Спринт 2.5-D.12: аудит/дедупликация admin-* локалей + lint-тест RU↔EN parity (закрытие Спринта 2.5)` (сверху, перед записью D.11) по каноническому формату: Что сделано (Fluent silent-shadow / dedup 5 ключей / удаление 2 orphan-ов / lint-тест 5 классов), Результат (коммит `c456dfa`, merge `e6f7512`, CI 3417 passed, 95.90%), Заметки (AST-обход ловит только литералы / sanity-порог ≥100 / видимое поведенческое изменение для админов / почему dedup а не remove+add / закрытие Спринта 2.5).
- `docs/current_tasks.md` — обновлены 4 секции под postmerge: «Снимок состояния» (`main = e6f7512`, D.12 смержен, Спринт 2.5 закрыт, активная ветка = postmerge), «Текущая позиция», «Чек-лист текущего PR» (postmerge шаги), «Что ровно сейчас в работе» (дельта postmerge). D.12-пункт в «Спринт 2.5 — что ещё осталось» помечен как `[x]`.
- **Без изменений кода / тестов / локалей / миграций.** `make ci` будет прогон перед открытием PR — ожидание: 3417 passed / 1 skipped, coverage **95.90%** (docs-only — идентично main = `e6f7512`).

**Следующий PR (после мерджа этого) — Спринт 3:**
- Спринт 2.5 полностью закрыт. Следующая работа — Спринт 3 (см. `docs/development_plan.md`). Конкретный скоуп Спринта 3 — за пределами этого postmerge-PR-а; следующий агент должен выполнить «Промпт-приёмку для нового агента» из `CONTRIBUTING.md` и согласовать скоуп с пользователем.

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
