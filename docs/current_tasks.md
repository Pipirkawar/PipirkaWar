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

**На `main`:** последний смерженный спринт — **2.5-D.4** ([PR #88](https://github.com/Pipirkawar/PipirkaWar/pull/88), коммит `774bd7c`) — `/announce <ru|en|*> <text>`: broadcast с TOTP-confirm, RBAC (`SUPER_ADMIN`), фоновая рассылка через `IBroadcastTaskSpawner` с throttle (~25 msg/sec), audit `ADMIN_BROADCAST_SENT`. До этого были смержены 2.5-A (PR #79), 2.5-B (PR #81), 2.5-C (PR #83), постмердж-доки (PR #84), 2.5-D часть 1 (PR #85), 2.5-D.7 (PR #86), postmerge 2.5-D.7 (PR #87). Из Спринта 2.5 остаётся: **D.6** (`/admin_setup_totp`), **D.10** (`docs/admin_runbook.md`), **D.11** (доптесты RBAC), **D.12** (локали).

**Активная feature-ветка:** `devin/1778149111-sprint-2-5-d.4-postmerge-docs` (текущий PR — postmerge 2.5-D.4: запись в `history.md` + sync «Снимок» / «Текущая позиция» под D.4-в-main и переход к следующей фиче спринта 2.5).

**Что уже есть в коде после 2.5-D.4 (PR #88):**
- `domain/admin/authorization.py` — `AdminCommandKind` (whitelist 27 команд, включая `BROADCAST_ANNOUNCEMENT`), `IAdminAuthorizationPolicy`, `RoleBasedAdminAuthorizationPolicy` (file-closed-матрица), `AdminAuthorizationDeniedError`.
- `application/admin/_authorization.py` — helper `ensure_admin_authorized(...)` с отдельным коротким UoW для `ADMIN_AUTHORIZATION_DENIED`-аудита.
- **Все 18 admin-use-case-ов** (с D.4 добавились `BroadcastAnnouncement` Phase 1 и `RunBroadcastAnnouncement` Phase 2) принимают `authz: IAdminAuthorizationPolicy` и зовут helper до основного UoW.
- `bot/main.py::build_container` — `admin_audit: IAdminAuditLogger` + `admin_authz: IAdminAuthorizationPolicy` создаются раньше, пробрасываются во все admin-use-case-ы. В D.4 добавлены production-адаптеры `AiogramBroadcastSender`/`AsyncIOBroadcastTaskSpawner`/`NoopBroadcastSender` (из `infrastructure/telegram/broadcast.py`).
- `CONFIRM_DISPATCHERS` registry — **5** TOTP-обязательных команд (`grant_length`, `grant_thickness`, `set_balance_value`, `ban_player`, `broadcast_announcement`); D.4 регистрируется через мутацию dict-а в `bot/handlers/admin_communication.py` (порядок включения router-ов в `bot/handlers/__init__.py` гарантирует mutation до первого использования).
- **Чего нет:** `/admin_setup_totp` (D.6) — не реализован (TOTP-выдаётся сейчас только через `bootstrap_admin_password` на старте; нет выдачи нового секрета живому админу). `docs/admin_runbook.md` (D.10) — не существует.

**Скоуп Спринта 2.5 (история PR-ов):**
- ~~**2.5-A**~~ ✅ закрыт PR #79 (`b358349`) — каркас `admin_audit_log` + `AdminGuard` + TOTP-confirm.
- ~~**2.5-B**~~ ✅ закрыт PR #81 (`3653e40`) — команды поддержки + общий `/confirm`-dispatcher.
- ~~**2.5-C**~~ ✅ закрыт PR #83 (`10b3ee6`) — команды экономики + registry-pattern + atomic balance-writer + idempotency.
- ~~**2.5-D часть 1**~~ ✅ закрыт PR #85 (`2b17c09`) — D.1+D.2+D.3+D.5+D.8+D.9 (клановые read/write команды, `/audit`, RBAC, registry-pattern для `"ban"`).
- ~~**2.5-D.7**~~ ✅ закрыт PR #86 (`12f9ea0`) — миграция legacy admin-команд под RBAC.
- ~~**postmerge 2.5-D.7**~~ ✅ закрыт PR #87 — sync док (без кода).
- ~~**2.5-D.4**~~ ✅ закрыт PR #88 (`774bd7c`) — `/announce` broadcast с TOTP-confirm + фоновый throttle.
- **Текущий PR (postmerge 2.5-D.4):** sync `history.md` + `current_tasks.md` под D.4-в-main и выбор следующей фичи (D.6 / D.10 / D.11 / D.12). Без изменений кода.
- **Дальше:** D.6 (`/admin_setup_totp`), D.10 (`admin_runbook.md`), D.11 (доптесты RBAC), D.12 (локали) — отдельными PR-ами. Выбор следующей вернётся агенту после мерджа текущего postmerge-PR-а.

**`make ci` локально на `main` (после D.4):** зелёный — 3306 passed / 1 skipped, coverage **95.86%** (~1:30).

**`AGENT_HANDOFF.md`:** нет.

---

## 📍 Текущая позиция

| Поле | Значение |
|---|---|
| **Активный спринт** | `2.5 — Расширенный админ-интерфейс в боте (финал)` |
| **Активный PR / шаг** | **postmerge 2.5-D.4**: запись 2.5-D.4 в `history.md` + sync «Снимок» / «Текущая позиция» / чек-лист в `current_tasks.md` под D.4-в-main. Без изменений кода. После мерджа — выбор следующей фичи (D.6 / D.10 / D.11 / D.12). |
| **Активная feature-ветка** | `devin/1778149111-sprint-2-5-d.4-postmerge-docs` (создана от `main = 774bd7c`) |
| **Базовая ветка** | `main` |
| **Последний коммит на main** | `774bd7c` (мерж PR #88 «Спринт 2.5-D.4: `/announce` broadcast») |
| **Последний коммит на feature-ветке** | будет зафиксирован при push-е postmerge-коммита |
| **PR (если открыт)** | будет открыт после первого push-а |
| **CI статус** | на main зелёный: `make ci` — 3306 passed / 1 skipped, coverage 95.86% |
| **Связанная задача в `development_plan.md`** | §5 / Спринт 2.5 / задачи 2.5.8 (`/admin_setup_totp` — D.6), 2.5.10 (`admin_runbook.md` — D.10) |
| **Связанная спецификация в `game_design.md`** | §18.6.2 (RBAC — D.11), §18.6.5 (TOTP — D.6) |
| **`AGENT_HANDOFF.md` существует?** | нет |

---

## ✅ Чек-лист текущего PR

> Отмечай `[x]` по мере выполнения. **Перед каждым `git commit`** обнови этот чек-лист (даже если шаг ещё не закрыт — отметь, что начат). Это safety-net на случай, если агент прервётся в середине работы.

**Текущий PR — postmerge 2.5-D.4 (sync docs):**

- [x] Добавить запись **2.5-D.4** в `docs/history.md` (свежие — сверху): `/announce` broadcast с TOTP-confirm + фоновый throttle, PR #88, merge `774bd7c`.
- [x] Обновить «Снимок состояния проекта» в `docs/current_tasks.md` под фактический `main = 774bd7c`.
- [x] Обновить «Текущая позиция» под postmerge 2.5-D.4.
- [x] Заменить «Чек-лист текущего PR» на постмердж-список (этот блок).
- [ ] **Перед PR:** `make ci` локально зелёный (доки-only — должен быть идентичен main-CI).
- [ ] Открыть PR `docs(postmerge 2.5-D.4): history.md +1 запись, current_tasks.md sync под D.4-в-main`.
- [ ] **После мерджа:** выбрать следующую фичу (D.6 / D.10 / D.11 / D.12) по решению юзера.

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
