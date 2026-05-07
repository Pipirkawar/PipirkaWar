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

**На `main`:** последний смерженный PR — **postmerge 2.5-D.6** ([PR #91](https://github.com/Pipirkawar/PipirkaWar/pull/91), коммит `cb40c2e`) — sync `history.md` + `current_tasks.md` под D.6-в-main, без изменений кода. Перед ним: 2.5-D.6 (PR #90, `4c2b100`) — `/admin_setup_totp <bootstrap_password>` self-service выдача TOTP-секрета `SUPER_ADMIN`-у; postmerge 2.5-D.4 (PR #89, `8df66e7`); 2.5-D.4 (PR #88, `774bd7c`) — `/announce` broadcast с TOTP-confirm + throttle. До этого: 2.5-A (PR #79), 2.5-B (PR #81), 2.5-C (PR #83), постмердж-доки (PR #84), 2.5-D часть 1 (PR #85), 2.5-D.7 (PR #86), postmerge 2.5-D.7 (PR #87). Из Спринта 2.5 остаётся: **D.10** (`docs/admin_runbook.md`) — в работе сейчас, **D.11** (доптесты RBAC), **D.12** (расширение локалей).

**Активная feature-ветка:** `devin/1778160466-sprint-2-5-d.10-admin-runbook` (текущий PR — **2.5-D.10**: новый файл `docs/admin_runbook.md` — операционная документация для админ-команды; обновление `current_tasks.md` под смену PR; без изменений кода/тестов/локалей).

**Что уже есть в коде после 2.5-D.6 (PR #90):**
- `domain/admin/authorization.py` — `AdminCommandKind` (whitelist 27 команд, включая `BROADCAST_ANNOUNCEMENT` и `SETUP_TOTP`), `IAdminAuthorizationPolicy`, `RoleBasedAdminAuthorizationPolicy` (file-closed-матрица; `SETUP_TOTP` → только `SUPER_ADMIN`), `AdminAuthorizationDeniedError`.
- `application/admin/_authorization.py` — helper `ensure_admin_authorized(...)` с отдельным коротким UoW для `ADMIN_AUTHORIZATION_DENIED`-аудита.
- **Все 19 admin-use-case-ов** (с D.6 добавился `SetupAdminTotp`) принимают `authz: IAdminAuthorizationPolicy` и зовут helper до основного UoW.
- `bot/main.py::build_container` — `admin_audit: IAdminAuditLogger` + `admin_authz: IAdminAuthorizationPolicy` создаются раньше, пробрасываются во все admin-use-case-ы. В D.6 добавлен production-адаптер `PyOtpTotpSecretGenerator` (из `infrastructure/admin/pyotp_totp_secret_generator.py`) и `BootstrapSettings.admin_password` (env `BOOTSTRAP_ADMIN_PASSWORD`).
- `CONFIRM_DISPATCHERS` registry — **5** TOTP-обязательных команд (`grant_length`, `grant_thickness`, `set_balance_value`, `ban_player`, `broadcast_announcement`); `/admin_setup_totp` НЕ требует TOTP-confirm (это команда выдачи самого TOTP — chicken-and-egg).
- `domain/admin/`: `Admin.totp_secret: str | None` (миграция `0017_admins_totp_secret`, BASE32 plain-text), новый порт `ITotpSecretGenerator.generate() -> str`, новый абстрактный метод `IAdminRepository.set_totp_secret(*, admin_id, secret)`, новые ошибки `BootstrapPasswordNotConfiguredError`/`BootstrapPasswordInvalidError`/`TotpAlreadyConfiguredError` (из `domain/admin/setup_totp_errors.py`), `AdminAuditAction.ADMIN_TOTP_SETUP`.
- `infrastructure/admin/pyotp_totp_verifier.py::PyOtpTotpVerifier` — проверка 6-значных кодов с `valid_window=1` (D.4-prep).
- **Чего нет до D.10–D.12:** `docs/admin_runbook.md` (D.10) не существует. Coverage RBAC-deny по 27 `AdminCommandKind`-значениям × 5 ролей — неравномерное (D.11). Аудит локалей `admin-*` после D.1–D.9/D.4/D.6 — не пройден (D.12).

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
- **Текущий PR (2.5-D.10):** новый файл `docs/admin_runbook.md` — operational doc для админ-команды (RBAC-матрица, TOTP setup, `/audit`-чтение, recovery при потере 2FA, ротация `BOOTSTRAP_ADMIN_PASSWORD`); пересинк `current_tasks.md` под D.10. Без изменений кода/тестов/локалей.
- **Дальше:** D.11 (доптесты RBAC), D.12 (локали) — отдельными PR-ами.

**`make ci` локально на `main` (после postmerge 2.5-D.6):** зелёный — 3337 passed / 1 skipped, coverage **95.90%** (~1:38). На текущей feature-ветке D.10 — будет прогон перед открытием PR.

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `2.5 — Расширенный админ-интерфейс в боте (финал)` |
| **Активный PR / шаг** | **2.5-D.10 (`docs/admin_runbook.md`)**: новый файл `docs/admin_runbook.md` — operational doc для админ-команды (RBAC-матрица live из кода, TOTP-setup через `/admin_setup_totp`, чтение `/audit`, recovery при потере 2FA, ротация `BOOTSTRAP_ADMIN_PASSWORD`); пересинк `current_tasks.md` под D.10. **Без изменений кода/тестов/локалей.** |
| **Активная feature-ветка** | `devin/1778160466-sprint-2-5-d.10-admin-runbook` (создана от `main = cb40c2e`) |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `cb40c2e` (мерж PR #91 «postmerge 2.5-D.6: history.md +1 запись, current_tasks.md sync под D.6-в-main») |
| **Последний коммит на feature-ветке** | будет зафиксирован при первом push-е |
| **PR (если открыт)** | будет открыт после локального зелёного `make ci` |
| **CI статус** | на main зелёный: `make ci` — 3337 passed / 1 skipped, coverage 95.90% |
| **Связанная задача в `development_plan.md`** | §5 / Спринт 2.5 / задача 2.5.8 (общая инфраструктура `admin_audit_log` + RBAC); D.10 — operational documentation для уже реализованных D.1–D.9 + D.4 + D.6 |
| **Связанная спецификация в `game_design.md`** | §18.6 (целиком: интерфейс админ-панели), §18.6.4 (безопасность, bootstrap super-admin), §18.6.5 (TOTP-flow для опасных команд). Runbook не дублирует спеку — ссылается на неё. |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**Текущий PR — 2.5-D.10 (`docs/admin_runbook.md`):**

- [x] Завести feature-ветку `devin/1778160466-sprint-2-5-d.10-admin-runbook` от `main = cb40c2e`.
- [x] Изучить источники: `game_design.md §18.6`, `domain/admin/authorization.py` (`AdminCommandKind` whitelist + RBAC-матрица), все `application/admin/*.py` (use-case-ы), все `bot/handlers/admin*.py` (canonical command list + TOTP-required).
- [x] Собрать live-список admin-команд по разделам (lookup / support игроки / support кланы / экономика / super-admin) с пометкой TOTP — синхронно с `CONFIRM_DISPATCHERS` registry в `bot/handlers/admin_economy.py`.
- [x] Написать `docs/admin_runbook.md`: §0 канал интерфейса → §1 ролевая модель → §2 полный список команд → §3 `/admin_setup_totp` пошаговый флоу → §4 RBAC и обработка отказов → §5 TOTP-confirm для опасных команд → §6 чтение `/audit` (полный whitelist `AdminAuditAction`) → §7 recovery при потере 2FA (3 сценария) → §8 ротация `BOOTSTRAP_ADMIN_PASSWORD` → §9 FAQ → §10 куда идти за подробностями. Ссылки на `game_design.md` / `history.md` / `development_plan.md` — без дублирования содержимого.
- [x] Обновить «Снимок состояния» / «Текущая позиция» / «Чек-лист текущего PR» в `current_tasks.md` под D.10.
- [ ] **Перед PR:** `make ci` локально зелёный (docs-only — должен быть идентичен main-CI; runbook не импортируется кодом).
- [ ] Открыть PR `docs(2.5-D.10): admin_runbook.md — operational doc для админ-команды`.
- [ ] **После мерджа:** перейти к следующей задаче (D.11 → D.12 — выбор пользователя).

**Спринт 2.5 — что ещё осталось (детализация на референс):**

- [x] **2.5-D.4 — `/announce <ru|en|*> <message>`** ✅ закрыт PR #88 (`774bd7c`). Two-phase flow с TOTP-confirm: Phase 1 (`BroadcastAnnouncement`) валидирует локаль/длину, делает RBAC-проверку (`SUPER_ADMIN`), pre-flight `list_active_for_broadcast(...)` и выдаёт `/confirm`-токен; Phase 2 (`RunBroadcastAnnouncement` через `CONFIRM_DISPATCHERS["broadcast_announcement"]`) запускает фоновую рассылку через `IBroadcastTaskSpawner` с throttle `25 msg/sec` (`BATCH_SIZE=25` × `BATCH_INTERVAL=1.0s`). Production: `AiogramBroadcastSender`/`AsyncIOBroadcastTaskSpawner`. Audit: `ADMIN_BROADCAST_SENT`. Локали: 11 ключей `admin-announce-*` (RU/EN). **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.4`.**
- [x] **2.5-D.6 — `/admin_setup_totp <bootstrap_password>`** ✅ закрыт PR #90 (`4c2b100`). Self-service-команда генерирует BASE32-секрет (`pyotp.random_base32()`), сохраняет в `Admin.totp_secret` через `IAdminRepository.set_totp_secret(...)`, выдаёт `ADMIN_TOTP_SETUP`-audit. Защита: RBAC (`SUPER_ADMIN`) + constant-time-сравнение пароля (`hmac.compare_digest`) + idempotency (`TotpAlreadyConfiguredError` на повторный вызов). **Канал доставки секрета — bot-логи, а не Telegram-чат**: `secret` и `otpauth://`-URI пишутся в `structlog.info(event="admin_totp_setup", actor_tg_id=..., secret=..., provisioning_uri=...)`; в чат уходит только локализованный `admin-setup-totp-success` без секретного материала. Локали: 7 ключей `admin-setup-totp-*` (RU/EN). **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.6`.**
- [x] **2.5-D.8 — RBAC** (`game_design.md` §18.6.2) — закрыт PR #85. Whitelist-enum `AdminCommandKind` (27 команд) + `IAdminAuthorizationPolicy` + `RoleBasedAdminAuthorizationPolicy` (file-closed-матрица) + helper `ensure_admin_authorized(...)`. RBAC для `BROADCAST_ANNOUNCEMENT` (`/announce`): только `SUPER_ADMIN` — это нужно для D.4. **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D часть 1/2`.** [legacy: ниже была развёрнутая инлайн-версия задачи; перенесена в history.md, чтобы не дублировать.] DI: `Container.admin_authz: IAdminAuthorizationPolicy`, инстанциируется как `RoleBasedAdminAuthorizationPolicy()` в `build_container()`. Тесты: матрица `RoleBasedAdminAuthorizationPolicy` (29 случаев параметризованных + super-admin allows-all + inactive-admin denied) + helper `ensure_admin_authorized` (allow no-op / deny + audit + raise / reason_suffix). Двойная проверка по слоям: интеграционные тесты use-case-ов через `FakeAdminAuthzAllowAll` подтверждают, что DI пробрасывает `authz` корректно; legacy-команды `/balance_reload`/`/admin_stats`/`/set_max_dau`/`/anticheat_unban` останутся вне RBAC до 2.5-D.7 (там же — переход на `AdminGuard`).
- [x] **2.5-D.9 — Перенести `command_kind="ban"` из inline в `CONFIRM_DISPATCHERS` registry.** ✅ закрыт коммитом `3ef53b7` на ветке `devin/1778101600-sprint-2-5-d-final`: `_dispatch_ban` добавлен в `bot/handlers/admin_economy.py`, зарегистрирован в `CONFIRM_DISPATCHERS`, inline-кейс из `bot/handlers/admin_support.py` удалён.
- [ ] **2.5-D.10 — `docs/admin_runbook.md`** — документация для команды поддержки/экономистов: список всех админ-команд, какая роль нужна, какие требуют TOTP, как настроить `pyotp` в их Authenticator, что делать при потере 2FA, как читать `/audit`. Не дублировать `game_design.md §18.6` — runbook это операционная инструкция, а не спека.
- [ ] **2.5-D.11 — Тесты:** unit на каждый новый use-case (≥4 кейса), integration-тесты на repo-методы (clan freeze/unfreeze, audit query), e2e на handler-ы и TOTP-flow `/announce`. Покрытие RBAC: каждая команда тестируется на отказ для недостаточной роли.
- [ ] **2.5-D.12 — Локали** всех новых ключей `admin-announce-*` / `admin-setup-totp-*` / `admin-rbac-*` в `locales/{ru,en}.ftl` (ключи D.1/D.2/D.3/D.5 уже добавлены в PR #85; ключи D.7 — без новых строк).

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты. Не дублируй ТЗ из `development_plan.md` — пиши только то, что важно для **текущего PR**.

**Текущий PR (postmerge 2.5-D.6) — только доки, без изменений кода:**
- `docs/history.md` — одна запись сверху (свежие — первыми): `2026-05-07 — Спринт 2.5-D.6: /admin_setup_totp — self-service выдача TOTP-секрета SUPER_ADMIN-у` (PR #90, merge `4c2b100`). По канону: «Что сделано» / «Результат / артефакты» / «Заметки / решения», ссылки на коммиты и PR.
- `docs/current_tasks.md` — переписана секция «Снимок состояния» под `main = 4c2b100`, обновлена таблица «Текущая позиция», заменён чек-лист на постмердж-список 2.5-D.6, обновлён этот блок, обновлён референс в «Спринт 2.5 — что ещё осталось» (D.6 → ✅ закрыт).
- **Без изменений кода.** `make ci` гонится для подтверждения, что postmerge-PR не ломает ничего.

**Следующий PR (после мерджа этого) — выбор пользователя из остатка Спринта 2.5:**
- **D.11 — доптесты RBAC** (рекомендован первым: низкий риск, добивает coverage). Coverage для каждой admin-команды на отказ для недостаточной роли (`READ_ONLY`/`SUPPORT`/`ECONOMIST`/`SUPER_ADMIN` × 27 `AdminCommandKind`-значений). Параметризованная матрица в `tests/unit/domain/admin/test_authorization_matrix.py` + integration-тесты на helper-уровне (`ensure_admin_authorized`).
- **D.12 — расширение локалей** — пройти по `locales/{ru,en}.ftl` и убедиться, что для всех admin-команд из D.1–D.9 + D.4 + D.6 есть полный набор `*-confirm-issued`/`*-not-authorized`/`*-success`/etc. ключей. Linter-проверка соответствия RU/EN ключей (нет drift-а).
- **D.10 `docs/admin_runbook.md`** — операционная документация для команды поддержки/экономистов: список всех админ-команд, RBAC-матрица (роль ↔ команда), какие требуют TOTP, как настроить `pyotp` в Authenticator (через `/admin_setup_totp <bootstrap_password>`), что делать при потере 2FA, как читать `/audit`, rotation `BOOTSTRAP_ADMIN_PASSWORD`. Не дублировать `game_design.md §18.6` — runbook это операционная инструкция, а не спека.

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
