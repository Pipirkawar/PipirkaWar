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

**На `main`:** последний смерженный спринт — **2.5-D.7** ([PR #86](https://github.com/Pipirkawar/PipirkaWar/pull/86), коммит `12f9ea0`) — миграция legacy `/balance_reload`/`/admin_stats`/`/set_max_dau`/`/anticheat_unban` с `Admin.can_*()`-API на единый RBAC-канал из D.8 (`ensure_admin_authorized` helper + `AdminCommandKind`). До этого были смержены 2.5-A (PR #79), 2.5-B (PR #81), 2.5-C (PR #83), постмердж-доки (PR #84), 2.5-D часть 1 (PR #85). Из Спринта 2.5 остаётся: **D.4** (`/announce`), **D.6** (`/admin_setup_totp`), **D.10** (`docs/admin_runbook.md`), **D.11** (доптесты RBAC), **D.12** (локали).

**Активная feature-ветка:** `devin/<ts>-sprint-2-5-d.7-postmerge-docs` (текущий PR — постмердж 2.5-D.7: запись в `history.md` + sync «Снимок» / «Текущая позиция» под D.4 как следующий активный шаг). После мерджа этого PR-а будет открыта новая ветка `devin/<ts>-sprint-2-5-d.4-announce` под фичу `/announce`.

**Что уже есть в коде после 2.5-D.7 (PR #86):**
- `domain/admin/authorization.py` — `AdminCommandKind` (whitelist 27 команд, включая `BROADCAST_ANNOUNCEMENT`), `IAdminAuthorizationPolicy`, `RoleBasedAdminAuthorizationPolicy` (file-closed-матрица), `AdminAuthorizationDeniedError`.
- `application/admin/_authorization.py` — helper `ensure_admin_authorized(...)` с отдельным коротким UoW для `ADMIN_AUTHORIZATION_DENIED`-аудита.
- **Все 16 admin-use-case-ов** (13 из D.8 + `application/balance/reload.py`, `application/dau/set_max.py`, `application/anticheat/lift_ban.py` — мигрированы D.7) принимают `authz: IAdminAuthorizationPolicy` и зовут helper до основного UoW. Дублирующая `Admin.can_*()`-логика удалена.
- `bot/main.py::build_container` — `admin_audit: IAdminAuditLogger` + `admin_authz: IAdminAuthorizationPolicy` создаются раньше, пробрасываются во все admin-use-case-ы.
- `CONFIRM_DISPATCHERS` registry — 4 TOTP-обязательные команды (`grant_length`, `grant_thickness`, `set_balance_value`, `ban_player`); добавление новой мутирующей команды = «добавить пару `(kind, fn)` в реестр».
- **Чего нет:** `/announce` (D.4) — use-case `BroadcastAnnouncement` не реализован, нет фоновой job через `IDelayedJobScheduler`, нет throttling-логики, нет локали `admin-announce-*`. `/admin_setup_totp` (D.6) — не реализован. `docs/admin_runbook.md` (D.10) — не существует.

**Скоуп Спринта 2.5 (история PR-ов):**
- ~~**2.5-A**~~ ✅ закрыт PR #79 (`b358349`) — каркас `admin_audit_log` + `AdminGuard` + TOTP-confirm.
- ~~**2.5-B**~~ ✅ закрыт PR #81 (`3653e40`) — команды поддержки + общий `/confirm`-dispatcher.
- ~~**2.5-C**~~ ✅ закрыт PR #83 (`10b3ee6`) — команды экономики + registry-pattern в `/confirm` + atomic balance-writer + idempotency.
- ~~**2.5-D часть 1**~~ ✅ закрыт PR #85 (`2b17c09`) — D.1+D.2+D.3+D.5+D.8+D.9 (клановые read/write команды, `/audit`, RBAC, registry-pattern для `"ban"`).
- ~~**2.5-D.7**~~ ✅ закрыт PR #86 (`12f9ea0`) — миграция legacy admin-команд под RBAC.
- **Текущий PR (postmerge 2.5-D.7):** sync `history.md` + `current_tasks.md` под D.7-в-main и переход к D.4 как активной фиче. Без изменений кода.
- **Следующий PR (2.5-D.4):** `/announce` — broadcast с TOTP, фоновая job через `IDelayedJobScheduler`, throttling.
- **Дальше:** D.6 (`/admin_setup_totp`), D.10 (`admin_runbook.md`), D.11 (доптесты RBAC), D.12 (локали) — отдельными PR-ами.

**`make ci` локально на `main`:** зелёный — 3262 passed / 1 skipped, coverage 95.98% (~3:08).

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `2.5 — Расширенный админ-интерфейс в боте (финал)` |
| **Активный PR / шаг** | **postmerge 2.5-D.7**: запись 2.5-D-часть-1 + 2.5-D.7 в `history.md`, sync «Снимок» / «Текущая позиция» / чек-лист в `current_tasks.md` под актуальное состояние main и переход к D.4 как следующей фиче. После мерджа — следующий PR `2.5-D.4` (`/announce`). |
| **Активная feature-ветка** | `devin/<ts>-sprint-2-5-d.7-postmerge-docs` (создана от `main = 12f9ea0`) |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `12f9ea0` (мерж PR #86 «Спринт 2.5-D.7») |
| **Последний коммит на feature-ветке** | будет зафиксирован при push-е postmerge-коммита |
| **PR (если открыт)** | будет открыт после первого push-а |
| **CI статус** | на main зелёный: `make ci` — 3262 passed / 1 skipped, coverage 95.98% |
| **Связанная задача в `development_plan.md`** | §5 / Спринт 2.5 / задачи 2.5.6 (`/announce` — следующий шаг), 2.5.8 (`/admin_setup_totp` — далее) |
| **Связанная спецификация в `game_design.md`** | §17 (моратории / `/announce` для broadcast), §18.6 (RBAC + 2FA — для D.6) |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**Текущий PR — postmerge 2.5-D.7 (sync docs):**

- [x] Добавить запись **2.5-D.7** в `docs/history.md` (свежие — сверху): миграция legacy admin-команд под `AdminGuard` + RBAC, PR #86, merge `12f9ea0`.
- [x] Добавить запись **2.5-D часть 1** (PR #85, merge `2b17c09`) в `docs/history.md` — она не была добавлена отдельным postmerge-PR-ом до D.7 (технический долг, закрывается этим PR-ом).
- [x] Обновить «Снимок состояния проекта» в `docs/current_tasks.md` под фактический `main = 12f9ea0` и переход к D.4 как следующей активной фиче.
- [x] Обновить «Текущая позиция» в `docs/current_tasks.md` под postmerge 2.5-D.7.
- [x] Заменить «Чек-лист текущего PR» на постмердж-список (этот блок).
- [x] Обновить «Что ровно сейчас в работе» — описать дельту postmerge-PR-а (доки) и кратко наметить следующий PR (D.4 `/announce`).
- [ ] **Перед PR:** `make ci` локально зелёный.
- [ ] Открыть PR `docs(postmerge 2.5-D.7): history.md +2 записи, current_tasks.md sync под D.4`.
- [ ] **После мерджа:** в новом PR-цикле создать ветку `devin/<ts>-sprint-2-5-d.4-announce` от `main` и переключить `current_tasks.md` под D.4.

**Спринт 2.5 — что ещё осталось (детализация на референс):**

- [ ] **2.5-D.4 — `/announce <ru|en|*> <message>`** — broadcast всем активным игрокам (или с фильтром по локали). Use-case `BroadcastAnnouncement(admin_id, locale_filter, message)`. **TOTP-обязательная** (массовая рассылка — высокий риск). Реализация рассылки: фоновая job через `IDelayedJobScheduler` с throttling (макс N сообщений/сек чтобы не упереться в rate-limit Telegram); progress-update в чат админу (стартовое «отправляю N игрокам», финальное «отправлено / failed / blocked»). Audit: `ADMIN_BROADCAST_SENT` (с `recipient_count`/`failed_count`). Локаль `admin-announce-*`. **`AdminCommandKind.BROADCAST_ANNOUNCEMENT` уже в whitelist-enum** (D.8) — RBAC-матрица: только `SUPER_ADMIN`. Доступа к `CONFIRM_DISPATCHERS` потребует расширение `ConfirmDispatchDeps` под `broadcast_announcement` use-case.
- [ ] **2.5-D.6 — `/admin_setup_totp`** — выдача нового TOTP-секрета админу: генерация secret через `pyotp.random_base32()`, сохранение в `Admin.totp_secret_encrypted` (через `IAdminRepository.set_totp_secret`), отправка QR-кода (или otpauth-URL) в личку админу. **Защищена паролем-инициализатором** (`bootstrap_admin_password` из `BootstrapSettings` — единоразовый пароль из ENV, который ломается после первого использования). Audit: `ADMIN_TOTP_SETUP`. Локаль `admin-setup-totp-*`. ⚠ опасно — выдача QR-кода через Telegram-канал; рассмотреть alternative: вывод только в логи бота (читаемые только из VM).
- [x] **2.5-D.8 — RBAC** (`game_design.md` §18.6.2) — закрыт PR #85. Whitelist-enum `AdminCommandKind` (27 команд) + `IAdminAuthorizationPolicy` + `RoleBasedAdminAuthorizationPolicy` (file-closed-матрица) + helper `ensure_admin_authorized(...)`. RBAC для `BROADCAST_ANNOUNCEMENT` (`/announce`): только `SUPER_ADMIN` — это нужно для D.4. **Подробности — в `docs/history.md` запись `2026-05-07 — Спринт 2.5-D часть 1/2`.** [legacy: ниже была развёрнутая инлайн-версия задачи; перенесена в history.md, чтобы не дублировать.] DI: `Container.admin_authz: IAdminAuthorizationPolicy`, инстанциируется как `RoleBasedAdminAuthorizationPolicy()` в `build_container()`. Тесты: матрица `RoleBasedAdminAuthorizationPolicy` (29 случаев параметризованных + super-admin allows-all + inactive-admin denied) + helper `ensure_admin_authorized` (allow no-op / deny + audit + raise / reason_suffix). Двойная проверка по слоям: интеграционные тесты use-case-ов через `FakeAdminAuthzAllowAll` подтверждают, что DI пробрасывает `authz` корректно; legacy-команды `/balance_reload`/`/admin_stats`/`/set_max_dau`/`/anticheat_unban` останутся вне RBAC до 2.5-D.7 (там же — переход на `AdminGuard`).
- [x] **2.5-D.9 — Перенести `command_kind="ban"` из inline в `CONFIRM_DISPATCHERS` registry.** ✅ закрыт коммитом `3ef53b7` на ветке `devin/1778101600-sprint-2-5-d-final`: `_dispatch_ban` добавлен в `bot/handlers/admin_economy.py`, зарегистрирован в `CONFIRM_DISPATCHERS`, inline-кейс из `bot/handlers/admin_support.py` удалён.
- [ ] **2.5-D.10 — `docs/admin_runbook.md`** — документация для команды поддержки/экономистов: список всех админ-команд, какая роль нужна, какие требуют TOTP, как настроить `pyotp` в их Authenticator, что делать при потере 2FA, как читать `/audit`. Не дублировать `game_design.md §18.6` — runbook это операционная инструкция, а не спека.
- [ ] **2.5-D.11 — Тесты:** unit на каждый новый use-case (≥4 кейса), integration-тесты на repo-методы (clan freeze/unfreeze, audit query), e2e на handler-ы и TOTP-flow `/announce`. Покрытие RBAC: каждая команда тестируется на отказ для недостаточной роли.
- [ ] **2.5-D.12 — Локали** всех новых ключей `admin-announce-*` / `admin-setup-totp-*` / `admin-rbac-*` в `locales/{ru,en}.ftl` (ключи D.1/D.2/D.3/D.5 уже добавлены в PR #85; ключи D.7 — без новых строк).

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты. Не дублируй ТЗ из `development_plan.md` — пиши только то, что важно для **текущего PR**.

**Текущий PR (postmerge 2.5-D.7) — только доки, без изменений кода:**
- `docs/history.md` — добавляются **две** записи сверху (свежие — первыми): `2026-05-07 — Спринт 2.5-D.7` (PR #86) и `2026-05-07 — Спринт 2.5-D часть 1/2` (PR #85, технический долг — postmerge-PR не был оформлен до D.7). Обе по канону: «Что сделано» / «Результат / артефакты» / «Заметки / решения», ссылки на коммиты и PR-ы.
- `docs/current_tasks.md` — переписана секция «Снимок состояния», обновлена таблица «Текущая позиция», заменён чек-лист на постмердж-список + референс на остаток Спринта 2.5, обновлён этот блок.
- **Без изменений кода.** `make ci` гонится для подтверждения, что postmerge-PR не ломает ничего.

**Следующий PR (после мерджа этого) — 2.5-D.4 `/announce` (на новой ветке):**
- Use-case `application/admin/broadcast_announcement.py::BroadcastAnnouncement(admin_id, locale_filter, message)` — фаза 1: проверка RBAC (`AdminCommandKind.BROADCAST_ANNOUNCEMENT` → только `SUPER_ADMIN`), валидация `locale_filter` (`ru` | `en` | `*`), pre-flight подсчёт получателей через `IPlayerRepository`, кладёт payload в `AdminConfirmStore` (как `grant_*` в 2.5-C), возвращает hint «введите `/confirm <code>`». Фаза 2 (после `/confirm`): запуск фоновой job через `IDelayedJobScheduler`, которая шлёт сообщения с throttling, аудит `ADMIN_BROADCAST_SENT` (с `recipient_count` / `sent_count` / `failed_count` / `blocked_count`).
- Throttling: чтобы не упереться в Telegram rate-limit (~30 messages/sec для bot-ов), послать `RATE_LIMIT_MESSAGES_PER_SECOND` сообщений/сек (значение в `balance.yaml::admin.broadcast_throttle_per_sec` по умолчанию `25` с запасом). Job обрабатывает партии и спит между ними.
- Progress-update в чат админу: стартовое «отправляю N игрокам», финальное «отправлено: X, failed: Y, blocked: Z».
- `bot/handlers/admin_communication.py` — новый router (`Router(name="admin_communication")` + `IsAdminFilter()`), один handler `handle_announce`, dispatch-функция `_dispatch_announce` для `CONFIRM_DISPATCHERS["broadcast_announcement"]`. Расширение `ConfirmDispatchDeps` (опциональный `broadcast_announcement: BroadcastAnnouncement | None`).
- DI в `bot/main.py::build_container` — `broadcast_announcement` use-case, его передача в admin_communication-router.
- Локаль `admin-announce-*` (RU + EN) в `locales/{ru,en}.ftl` — usage-text, confirm-prompt, progress-start, progress-final, ошибки.
- Тесты: ≥ 4 unit на use-case (RBAC-отказ + audit, valid case → planned job, invalid locale_filter, идемпотентность через `IIdempotencyKey`), ≥ 4 unit на handler (parsing, RBAC, не-админ, success), 1 integration на throttling в job. Покрытие RBAC: `READ_ONLY`/`SUPPORT`/`ECONOMIST` → отказ + audit `ADMIN_AUTHORIZATION_DENIED`.
- Затронутые слои: `application/admin/broadcast_announcement.py` (новый use-case), `bot/handlers/admin_communication.py` (новый router) + регистрация в `bot/dispatcher.py`, `bot/handlers/admin_economy.py::CONFIRM_DISPATCHERS` (запись `"broadcast_announcement"`), `bot/main.py` (DI), `domain/admin/ports/admin_audit.py::AdminAuditAction.ADMIN_BROADCAST_SENT` (новое значение), `locales/{ru,en}.ftl` (`admin-announce-*`), `tests/unit/application/admin/test_broadcast_announcement.py`, `tests/unit/bot/handlers/test_admin_communication.py`, `tests/integration/.../test_broadcast_throttle.py`.

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
