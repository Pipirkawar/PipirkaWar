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

**На `main`:** последний смерженный PR — **postmerge 2.5-D.4** ([PR #89](https://github.com/Pipirkawar/PipirkaWar/pull/89), коммит `8df66e7`) — sync док (без изменений кода). Перед ним: 2.5-D.4 ([PR #88](https://github.com/Pipirkawar/PipirkaWar/pull/88), коммит `774bd7c`) — `/announce <ru|en|*> <text>`: broadcast с TOTP-confirm, RBAC (`SUPER_ADMIN`), фоновая рассылка через `IBroadcastTaskSpawner` с throttle (~25 msg/sec), audit `ADMIN_BROADCAST_SENT`. До этого были смержены 2.5-A (PR #79), 2.5-B (PR #81), 2.5-C (PR #83), постмердж-доки (PR #84), 2.5-D часть 1 (PR #85), 2.5-D.7 (PR #86), postmerge 2.5-D.7 (PR #87). Из Спринта 2.5 остаётся: **D.6** (`/admin_setup_totp` — в работе), **D.10** (`docs/admin_runbook.md`), **D.11** (доптесты RBAC), **D.12** (локали).

**Активная feature-ветка:** `devin/1778151428-sprint-2-5-d.6-admin-setup-totp` (текущий PR — Спринт 2.5-D.6: `/admin_setup_totp` — выдача TOTP-секрета живому админу с защитой одноразовым `bootstrap_admin_password`, audit `ADMIN_TOTP_SETUP`).

**Что уже есть в коде после 2.5-D.4 (PR #88, sync PR #89):**
- `domain/admin/authorization.py` — `AdminCommandKind` (whitelist 27 команд, включая `BROADCAST_ANNOUNCEMENT` и `SETUP_TOTP`), `IAdminAuthorizationPolicy`, `RoleBasedAdminAuthorizationPolicy` (file-closed-матрица; `SETUP_TOTP` → только `SUPER_ADMIN`), `AdminAuthorizationDeniedError`.
- `application/admin/_authorization.py` — helper `ensure_admin_authorized(...)` с отдельным коротким UoW для `ADMIN_AUTHORIZATION_DENIED`-аудита.
- **Все 18 admin-use-case-ов** (с D.4 добавились `BroadcastAnnouncement` Phase 1 и `RunBroadcastAnnouncement` Phase 2) принимают `authz: IAdminAuthorizationPolicy` и зовут helper до основного UoW.
- `bot/main.py::build_container` — `admin_audit: IAdminAuditLogger` + `admin_authz: IAdminAuthorizationPolicy` создаются раньше, пробрасываются во все admin-use-case-ы. В D.4 добавлены production-адаптеры `AiogramBroadcastSender`/`AsyncIOBroadcastTaskSpawner`/`NoopBroadcastSender` (из `infrastructure/telegram/broadcast.py`).
- `CONFIRM_DISPATCHERS` registry — **5** TOTP-обязательных команд (`grant_length`, `grant_thickness`, `set_balance_value`, `ban_player`, `broadcast_announcement`); D.4 регистрируется через мутацию dict-а в `bot/handlers/admin_communication.py` (порядок включения router-ов в `bot/handlers/__init__.py` гарантирует mutation до первого использования).
- `domain/admin/entities.py::Admin.totp_secret: str | None`, миграция `0017_admins_totp_secret` (BASE32 plain-text, обоснование plain в самой миграции). `infrastructure/admin/pyotp_totp_verifier.py::PyOtpTotpVerifier` — проверка 6-значных кодов с `valid_window=1`.
- **Чего нет до D.6:** `/admin_setup_totp` — не реализован. TOTP сейчас задаётся только напрямую миграцией/SQL; нет команды-self-service для выдачи нового секрета живому super-admin-у. `IAdminRepository.set_totp_secret(...)`, `ITotpSecretGenerator`, `BootstrapSettings.admin_password` ещё не созданы. `docs/admin_runbook.md` (D.10) — не существует.

**Скоуп Спринта 2.5 (история PR-ов):**
- ~~**2.5-A**~~ ✅ закрыт PR #79 (`b358349`) — каркас `admin_audit_log` + `AdminGuard` + TOTP-confirm.
- ~~**2.5-B**~~ ✅ закрыт PR #81 (`3653e40`) — команды поддержки + общий `/confirm`-dispatcher.
- ~~**2.5-C**~~ ✅ закрыт PR #83 (`10b3ee6`) — команды экономики + registry-pattern + atomic balance-writer + idempotency.
- ~~**2.5-D часть 1**~~ ✅ закрыт PR #85 (`2b17c09`) — D.1+D.2+D.3+D.5+D.8+D.9 (клановые read/write команды, `/audit`, RBAC, registry-pattern для `"ban"`).
- ~~**2.5-D.7**~~ ✅ закрыт PR #86 (`12f9ea0`) — миграция legacy admin-команд под RBAC.
- ~~**postmerge 2.5-D.7**~~ ✅ закрыт PR #87 — sync док (без кода).
- ~~**2.5-D.4**~~ ✅ закрыт PR #88 (`774bd7c`) — `/announce` broadcast с TOTP-confirm + фоновый throttle.
- ~~**postmerge 2.5-D.4**~~ ✅ закрыт PR #89 (`8df66e7`) — sync `history.md` + `current_tasks.md` под D.4-в-main. Без изменений кода.
- **Текущий PR (Спринт 2.5-D.6):** `/admin_setup_totp` — выдача TOTP-секрета живому super-admin-у с защитой одноразовым `bootstrap_admin_password`, audit `ADMIN_TOTP_SETUP`. Новые порты `IAdminRepository.set_totp_secret(...)` и `ITotpSecretGenerator`. Локали `admin-setup-totp-*` (RU/EN). Тесты на use-case (RBAC, плохой пароль, повторная настройка, успех) и handler (парсинг команды, локализация, не-ЛС).
- **Дальше:** D.10 (`admin_runbook.md`), D.11 (доптесты RBAC), D.12 (локали) — отдельными PR-ами.

**`make ci` локально на `main` (после `postmerge 2.5-D.4`):** зелёный — 3306 passed / 1 skipped, coverage **95.86%** (~1:30).

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `2.5 — Расширенный админ-интерфейс в боте (финал)` |
| **Активный PR / шаг** | **2.5-D.6 `/admin_setup_totp`**: выдача TOTP-секрета живому super-admin-у; защита одноразовым `bootstrap_admin_password`; audit `ADMIN_TOTP_SETUP`; вывод `otpauth://`-URL только в логи бота (не в Telegram-чат). |
| **Активная feature-ветка** | `devin/1778151428-sprint-2-5-d.6-admin-setup-totp` (создана от `main = 8df66e7`) |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `8df66e7` (мерж PR #89 «postmerge 2.5-D.4 docs») |
| **Последний коммит на feature-ветке** | будет зафиксирован при первом push-е |
| **PR (если открыт)** | будет открыт после готовности кода + локального зелёного `make ci` |
| **CI статус** | на main зелёный: `make ci` — 3306 passed / 1 skipped, coverage 95.86% |
| **Связанная задача в `development_plan.md`** | §5 / Спринт 2.5 / задача 2.5.8 (косвенно — общая инфраструктура `admin_audit_log`); сама команда D.6 описана в чек-листе ниже и в `current_tasks.md` истории |
| **Связанная спецификация в `game_design.md`** | §18.6 (`admins.totp_secret`, `admin_audit_log`), §18.6.2 (RBAC — `SETUP_TOTP` → `SUPER_ADMIN`), §18.6.5 (TOTP-flow для опасных команд) |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**Текущий PR — Спринт 2.5-D.6 (`/admin_setup_totp`):**

- [x] Завести feature-ветку `devin/1778151428-sprint-2-5-d.6-admin-setup-totp` от `main = 8df66e7` и обновить `current_tasks.md` под D.6.
- [ ] **Domain:**
  - `domain/admin/ports/admin_audit.py` — добавить `AdminAuditAction.ADMIN_TOTP_SETUP`.
  - `domain/admin/repositories.py::IAdminRepository` — добавить абстрактный метод `set_totp_secret(admin_id, secret)`.
  - `domain/admin/ports/totp_secret_generator.py` — новый порт `ITotpSecretGenerator.generate() -> str` (BASE32).
  - `domain/admin/setup_totp_errors.py` — новые `BootstrapPasswordNotConfiguredError`, `BootstrapPasswordInvalidError`, `TotpAlreadyConfiguredError` (наследники `DomainError`).
- [ ] **Application:** `application/admin/setup_totp.py::SetupAdminTotp` — use-case (RBAC через `ensure_admin_authorized` → constant-time проверка пароля → если `admin.totp_secret is not None` → `TotpAlreadyConfiguredError` → генерация secret → `IAdminRepository.set_totp_secret(...)` → `AdminAuditAction.ADMIN_TOTP_SETUP` → возврат `otpauth://`-URL handler-у).
- [ ] **Infrastructure:**
  - `infrastructure/admin/pyotp_totp_secret_generator.py::PyOtpTotpSecretGenerator` (использует `pyotp.random_base32()`).
  - `infrastructure/db/repositories/admin.py::SqlAlchemyAdminRepository.set_totp_secret(...)` (SQL `UPDATE admins SET totp_secret = :secret WHERE id = :admin_id`).
  - `infrastructure/settings/settings.py::BootstrapSettings.admin_password: SecretStr | None` (env `BOOTSTRAP_ADMIN_PASSWORD`).
- [ ] **Bot/handlers:**
  - `bot/handlers/admin_setup_totp.py` — handler `/admin_setup_totp <password>`, парсинг аргументов, локализованные ответы, **только в ЛС**, `IsAdminFilter` на router-е, `otpauth://`-URL пишется в `structlog`-логи на INFO с явным маркером.
  - Регистрация в `bot/handlers/__init__.py::register_routers`.
  - DI в `bot/main.py::build_container`: `bootstrap_admin_password` (из settings), `totp_secret_generator: ITotpSecretGenerator`, `setup_admin_totp: SetupAdminTotp`.
- [ ] **Локали:** `locales/{ru,en}.ftl` — ключи `admin-setup-totp-*` (usage / non-private / not-authorized / password-not-configured / password-invalid / already-configured / success).
- [ ] **Тесты:**
  - `tests/unit/application/admin/test_setup_totp.py` — RBAC-deny, password-not-configured, password-invalid, already-configured, success (audit + secret saved + otpauth URL).
  - `tests/unit/bot/handlers/test_admin_setup_totp.py` — usage, non-private, not-authorized, success/error.
  - `tests/integration/admin/` — integration тест на `SqlAlchemyAdminRepository.set_totp_secret` (если такой папки нет — добавить).
  - Coverage ≥ 80% на новый код.
- [ ] **Перед PR:** `make ci` локально зелёный.
- [ ] Открыть PR `Sprint 2.5-D.6: /admin_setup_totp — выдача TOTP-секрета super-admin-у` в `main`.
- [ ] **После мерджа:** обновить `docs/history.md` + `current_tasks.md` (postmerge-PR), удалить feature-ветку.

**Спринт 2.5 — что ещё осталось (детализация на референс):**

- [x] **2.5-D.4 — `/announce <ru|en|*> <message>`** ✅ закрыт PR #88 (`774bd7c`). Two-phase flow с TOTP-confirm: Phase 1 (`BroadcastAnnouncement`) валидирует локаль/длину, делает RBAC-проверку (`SUPER_ADMIN`), pre-flight `list_active_for_broadcast(...)` и выдаёт `/confirm`-токен; Phase 2 (`RunBroadcastAnnouncement` через `CONFIRM_DISPATCHERS["broadcast_announcement"]`) запускает фоновую рассылку через `IBroadcastTaskSpawner` с throttle `25 msg/sec` (`BATCH_SIZE=25` × `BATCH_INTERVAL=1.0s`). Production: `AiogramBroadcastSender`/`AsyncIOBroadcastTaskSpawner`. Audit: `ADMIN_BROADCAST_SENT`. Локали: 11 ключей `admin-announce-*` (RU/EN). **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D.4`.**
- [ ] **2.5-D.6 — `/admin_setup_totp`** — выдача нового TOTP-секрета админу: генерация secret через `pyotp.random_base32()`, сохранение в `Admin.totp_secret_encrypted` (через `IAdminRepository.set_totp_secret`), отправка QR-кода (или otpauth-URL) в личку админу. **Защищена паролем-инициализатором** (`bootstrap_admin_password` из `BootstrapSettings` — единоразовый пароль из ENV, который ломается после первого использования). Audit: `ADMIN_TOTP_SETUP`. Локаль `admin-setup-totp-*`. ⚠ опасно — выдача QR-кода через Telegram-канал; рассмотреть alternative: вывод только в логи бота (читаемые только из VM).
- [x] **2.5-D.8 — RBAC** (`game_design.md` §18.6.2) — закрыт PR #85. Whitelist-enum `AdminCommandKind` (27 команд) + `IAdminAuthorizationPolicy` + `RoleBasedAdminAuthorizationPolicy` (file-closed-матрица) + helper `ensure_admin_authorized(...)`. RBAC для `BROADCAST_ANNOUNCEMENT` (`/announce`): только `SUPER_ADMIN` — это нужно для D.4. **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D часть 1/2`.** [legacy: ниже была развёрнутая инлайн-версия задачи; перенесена в history.md, чтобы не дублировать.] DI: `Container.admin_authz: IAdminAuthorizationPolicy`, инстанциируется как `RoleBasedAdminAuthorizationPolicy()` в `build_container()`. Тесты: матрица `RoleBasedAdminAuthorizationPolicy` (29 случаев параметризованных + super-admin allows-all + inactive-admin denied) + helper `ensure_admin_authorized` (allow no-op / deny + audit + raise / reason_suffix). Двойная проверка по слоям: интеграционные тесты use-case-ов через `FakeAdminAuthzAllowAll` подтверждают, что DI пробрасывает `authz` корректно; legacy-команды `/balance_reload`/`/admin_stats`/`/set_max_dau`/`/anticheat_unban` останутся вне RBAC до 2.5-D.7 (там же — переход на `AdminGuard`).
- [x] **2.5-D.9 — Перенести `command_kind="ban"` из inline в `CONFIRM_DISPATCHERS` registry.** ✅ закрыт коммитом `3ef53b7` на ветке `devin/1778101600-sprint-2-5-d-final`: `_dispatch_ban` добавлен в `bot/handlers/admin_economy.py`, зарегистрирован в `CONFIRM_DISPATCHERS`, inline-кейс из `bot/handlers/admin_support.py` удалён.
- [ ] **2.5-D.10 — `docs/admin_runbook.md`** — документация для команды поддержки/экономистов: список всех админ-команд, какая роль нужна, какие требуют TOTP, как настроить `pyotp` в их Authenticator, что делать при потере 2FA, как читать `/audit`. Не дублировать `game_design.md §18.6` — runbook это операционная инструкция, а не спека.
- [ ] **2.5-D.11 — Тесты:** unit на каждый новый use-case (≥4 кейса), integration-тесты на repo-методы (clan freeze/unfreeze, audit query), e2e на handler-ы и TOTP-flow `/announce`. Покрытие RBAC: каждая команда тестируется на отказ для недостаточной роли.
- [ ] **2.5-D.12 — Локали** всех новых ключей `admin-announce-*` / `admin-setup-totp-*` / `admin-rbac-*` в `locales/{ru,en}.ftl` (ключи D.1/D.2/D.3/D.5 уже добавлены в PR #85; ключи D.7 — без новых строк).

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты. Не дублируй ТЗ из `development_plan.md` — пиши только то, что важно для **текущего PR**.

**Текущий PR (postmerge 2.5-D.4) — только доки, без изменений кода:**
- `docs/history.md` — одна запись сверху (свежие — первыми): `2026-05-07 — Спринт 2.5-D.4: /announce — broadcast с TOTP-confirm и фоновым throttle` (PR #88, merge `774bd7c`). По канону: «Что сделано» / «Результат / артефакты» / «Заметки / решения», ссылки на коммиты и PR.
- `docs/current_tasks.md` — переписана секция «Снимок состояния» под `main = 774bd7c`, обновлена таблица «Текущая позиция», заменён чек-лист на постмердж-список 2.5-D.4, обновлён этот блок.
- **Без изменений кода.** `make ci` гонится для подтверждения, что postmerge-PR не ломает ничего.

**Следующий PR (после мерджа этого) — выбор пользователя из остатка Спринта 2.5:**
- **D.6 `/admin_setup_totp`** — выдача нового TOTP-секрета живому админу (генерация `pyotp.random_base32()` → сохранение через `IAdminRepository.set_totp_secret` → отправка QR/`otpauth://`-URL); защита через `bootstrap_admin_password` (одноразовый ENV-пароль, ломается после первого использования). ⚠ безопасность: QR через Telegram-канал — рассмотреть alternative (вывод только в логи бота на VM).
- **D.10 `docs/admin_runbook.md`** — операционная документация для команды поддержки/экономистов: список всех админ-команд, RBAC-матрица (роль ↔ команда), какие требуют TOTP, как настроить `pyotp` в Authenticator, что делать при потере 2FA, как читать `/audit`. Не дублировать `game_design.md §18.6` — runbook это операционная инструкция, а не спека.
- **D.11 — доптесты RBAC** — coverage для каждой admin-команды на отказ для недостаточной роли (`READ_ONLY`/`SUPPORT`/`ECONOMIST`/`SUPER_ADMIN` × 27 `AdminCommandKind`-значений). Ныне покрытие неравномерное.
- **D.12 — расширение локалей** — пройти по `locales/{ru,en}.ftl` и убедиться, что для всех admin-команд из D.1–D.9 + D.4 есть полный набор `*-confirm-issued`/`*-not-authorized`/`*-success`/etc. ключей.

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
