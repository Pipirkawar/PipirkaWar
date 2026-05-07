# 🍆 Pipirik Wars — Admin Runbook

> **Аудитория:** оператор поддержки, экономист, super-admin. Любой, у кого есть запись в `admins` и роль выше `read_only`.
>
> **Жанр:** операционная инструкция. «Что нажать, чтобы…» Не спецификация и не план разработки.
>
> **Источники правды (НЕ дублируем):**
>
> - Игровые правила, формулы, лимиты, политики безопасности — [`game_design.md`](game_design.md) §0, §16, §18.6.
> - План разработки и критерии приёмки спринтов — [`development_plan.md`](development_plan.md).
> - История завершённых спринтов и их операционные приложения — [`history.md`](history.md).
> - Текущий PR / активная feature-ветка — [`current_tasks.md`](current_tasks.md).
>
> Этот файл живёт в `docs/`, версия — git. При изменении правил доступа / бутстрапа / 2FA — runbook обновляется тем же PR-ом, что меняет код. Расхождение с кодом = баг.

---

## 0. Канал админ-интерфейса

Основной интерфейс — **Telegram-бот** (см. [`game_design.md`](game_design.md) §18.6.0). Веб-панель — фаза 4.5+, runbook про неё пока не пишет.

Все админ-команды:

- работают **только в личке бота** (`chat_kind == "private"`). В группе бот молча отвечает «Админ-команды доступны только в ЛС бота» — это намеренно, чтобы не светить параметры в общем чате.
- доступны только пользователям из таблицы `admins` с `is_active = TRUE`. Не-админ → router-уровневый `IsAdminFilter` отбрасывает апдейт **тихо** (без ответа). Это дефенс-в-глубину: у потенциального атакующего не должно быть способа отличить «команды нет» от «прав нет».
- активный админ с **недостаточной ролью** → handler ловит `AdminAuthorizationDeniedError` и шлёт локализованный «недостаточно прав». При этом **в `/audit` уже лежит запись `ADMIN_AUTHORIZATION_DENIED`** — попытка эскалации привилегий видна супер-админу.
- write-side-команды требуют параметра `reason` (минимум 10 символов) и пишутся в `admin_audit_log` той же транзакцией, что и сама мутация.
- опасные write-side-команды (`/grant_*`, `/balance_set`, `/ban`, `/announce`) идут **двухфазно** через TOTP-confirm: первая фаза выдаёт `<token>` и просит `/confirm`, вторая фаза проверяет TOTP-код и выполняет команду (см. §6).

---

## 1. Кому что доступно (ролевая модель)

Whitelist ролей (`AdminRole`):

| Роль | Что может |
|---|---|
| `read_only` | Только read-side: `/find_player`, `/player`, `/clan`, `/clan_daily_head_history`, `/balance_get`, `/audit`, `/admin_stats`. Никаких мутаций. |
| `support` | Всё из `read_only` + операционка над игроками/кланами: `/freeze`, `/unfreeze`, `/freeze_clan`, `/unfreeze_clan`, `/ban` (TOTP). Не имеет прав на правки баланса. |
| `economist` | Всё из `read_only` + правки баланса: `/grant_length` (TOTP), `/grant_thickness` (TOTP), `/balance_set` (TOTP), `/balance_reload`. **НЕ** имеет прав на freeze/ban игроков (это саппорт-функция). |
| `super_admin` | Всё. Плюс уникальные `super-admin-only`: `/anticheat_unban`, `/set_max_dau`, `/announce` (TOTP), `/admin_setup_totp`. |

Иерархия **не суперсетная** в матрице (см. `domain/admin/authorization.py::RoleBasedAdminAuthorizationPolicy._matrix`): `super_admin` явно перечислен в каждой ячейке, где разрешена команда. Это защищает от ошибки «забыли super-admin-у выдать новую команду». Команда без явного правила → отказ (fail-closed).

**Bootstrap первого `super_admin`-а** — через env-переменную `BOOTSTRAP_ADMIN_IDS` (CSV из `tg_id`-ов). Срабатывает один раз при пустой таблице `admins`. Хранится в Devin Secrets `PIPIRIK_BOOTSTRAP_ADMIN_TG_ID` (`save_scope: org`). Подробности в [`game_design.md`](game_design.md) §18.6.4.

---

## 2. Полный список admin-команд

> Команды разбиты по разделам. В колонке «TOTP» стоит `да`, если команда требует двухфазного `/confirm` после ввода (то есть админу нужен настроенный `totp_secret`).

### 2.1 Read-side / lookup (доступно всем активным админам)

| Команда | Что делает | TOTP |
|---|---|---|
| `/admin_stats` | DAU/MAX_DAU и размер очереди регистраций. | нет |
| `/find_player <tg_id\|@username\|часть_имени>` | Поиск игрока по идентификатору или имени; краткая карточка. | нет |
| `/player <tg_id>` | Полная карточка игрока (длина/толщина/титул/экипировка/последние события). | нет |
| `/clan <chat_id\|часть_названия>` | Карточка клана. | нет |
| `/clan_daily_head_history <chat_id>` | История «Главы клана дня» по клану. | нет |
| `/balance_get <key>` | Прочитать значение балансового ключа из `config/balance.yaml`. | нет |
| `/audit [tg_id\|-] [action\|-] [limit]` | Листинг `admin_audit_log` (см. §7). | нет |

### 2.2 Поддержка игроков (`support+`)

| Команда | Что делает | TOTP |
|---|---|---|
| `/freeze <tg_id> <reason>` | Заморозить игрока. | нет |
| `/unfreeze <tg_id> <reason>` | Разморозить. | нет |
| `/ban <tg_id> <reason>` | Постоянный бан. | **да** |

### 2.3 Поддержка кланов (`support+`)

| Команда | Что делает | TOTP |
|---|---|---|
| `/freeze_clan <chat_id> <reason>` | Ручная заморозка клана (отличается от автоматической: пишется в admin-аудит и привязана к админу). | нет |
| `/unfreeze_clan <chat_id> <reason>` | Ручная разморозка клана. | нет |

### 2.4 Экономика (`economist+`)

| Команда | Что делает | TOTP |
|---|---|---|
| `/grant_length <tg_id> <±delta_cm> <reason>` | Начислить/отозвать длину игроку. Положительная дельта проходит через anti-cheat rolling-окно. | **да** |
| `/grant_thickness <tg_id> <new_level> <reason>` | Установить абсолютный уровень толщины (не дельта). | **да** |
| `/balance_set <key> <value> <reason>` | Изменить значение в `balance.yaml` (atomic write + hot-reload). | **да** |
| `/balance_reload` | Hot-reload `config/balance.yaml` (если файл уже подменили снаружи). | нет |

### 2.5 Только super-admin

| Команда | Что делает | TOTP |
|---|---|---|
| `/set_max_dau <N>` | Изменить runtime-`MAX_DAU`. Если лимит вырос — автоматически поднимает соответствующее число игроков из очереди. | нет |
| `/anticheat_unban <tg_id> <reason>` | Снять anti-cheat soft-ban с игрока (Спринт 1.6.G). Reason обязателен — идёт в audit как причина. | нет |
| `/announce <ru\|en\|*> <message>` | Глобальное объявление по выборке локалей. Throttle `25 msg/sec` через фоновый воркер. | **да** |
| `/admin_setup_totp <bootstrap_password>` | Self-service выдача TOTP-секрета супер-админу (см. §3). | нет |

> **Пометка:** для всех TOTP-команд handler первой фазы выдаёт токен `<6-значный hex>`. Подтверждение — `/confirm <TOTP_код>` в тот же чат, в течение 5 минут. См. §6.

---

## 3. Настройка 2FA (`/admin_setup_totp`)

Команда `/admin_setup_totp` — self-service. Доступна только активному `super_admin`. Используется один раз: после успешного выполнения у админа в БД заполняется `admin.totp_secret` (BASE32-секрет, RFC 6238), и все TOTP-команды для него начинают работать.

**Предусловие — настроен `BOOTSTRAP_ADMIN_PASSWORD`:**

- Хранится в Devin Secrets `PIPIRIK_BOOTSTRAP_ADMIN_PASSWORD` (`save_scope: org`).
- Прокидывается в окружение бота как env-переменная `BOOTSTRAP_ADMIN_PASSWORD`.
- Если переменная не задана — `/admin_setup_totp` отказывает с локализованным «настройка не удалась» (`admin-setup-totp-password-not-configured`). Это намеренный fail-closed: self-service-выдача секрета без второго фактора недопустима.
- Пароль out-of-band: оператор получает его не через Telegram, а через защищённый канал (например, password manager / зашифрованное сообщение).

**Шаги:**

1. Откройте ЛС с ботом. Группа не подойдёт — handler откажет «только в ЛС».
2. Отправьте `/admin_setup_totp <bootstrap_password>` (через пробел, без кавычек). Пример: `/admin_setup_totp s3cret-once`.
3. В чат придёт локализованный ответ «✅ настроено, секрет в логах сервера» (RU) / «✅ done, secret is in server logs» (EN). **В чате секрета НЕТ — это намеренно**, чтобы он не остался в истории Telegram.
4. Оператор VM (или автор команды, если у него есть SSH к VM) открывает структурированные логи бота и ищет запись `event="admin_totp_setup"`. В ней — `secret` (BASE32, например `JBSWY3DPEHPK3PXP`) и `provisioning_uri` (формат `otpauth://totp/Pipirik%20Wars:admin_<id>?secret=...&issuer=Pipirik%20Wars&algorithm=SHA1&digits=6&period=30`).
5. Импортируйте секрет в TOTP-приложение (Google Authenticator / Authy / 1Password):
    - **QR:** скопируйте `provisioning_uri` и сгенерируйте QR (например, `qrencode -t ANSIUTF8 "$URI"` или любой online-QR-генератор поверх HTTPS). Сосканируйте телефоном.
    - **Вручную:** введите `secret` в разделе «Add account → Manual entry». Issuer: `Pipirik Wars`. Account: `admin_<id>`. Algorithm: `SHA1`. Digits: `6`. Period: `30`.
6. Проверьте, что приложение каждые 30 секунд показывает свежий 6-значный код.
7. Прогоните любую TOTP-команду на тестовом сценарии (например, `/grant_length <ваш_tg_id> 1 "self test"` → `/confirm <6_цифр>`), чтобы убедиться, что код проходит.

**Что нельзя делать:**

- Перезапустить `/admin_setup_totp` для уже настроенного админа — use-case ответит `TotpAlreadyConfiguredError` (локализуется в `admin-setup-totp-already-configured`). Это защита: даже если злоумышленник перехватил bootstrap-пароль, он не сможет молча подменить чужой `totp_secret` без ручного сброса поля в БД.
- Делиться секретом / `provisioning_uri` через любые каналы. Логи VM — единственный авторизованный канал.
- Использовать один и тот же секрет на нескольких устройствах. Если нужен резервный девайс — настройте отдельный `super_admin`-аккаунт (см. §8 «Recovery»).

**Что попадёт в `/audit`:**

- Категория `ADMIN_TOTP_SETUP`, `target_kind="admin"`, `target_id=<self admin_id>` (actor и target совпадают).
- `before`/`after` — `None`. Сам секрет в audit-лог **не пишется**, чтобы из аудита его нельзя было извлечь.
- `reason` — `self setup via /admin_setup_totp`.

---

## 4. RBAC: что делать с отказами

Если активный админ дёрнул команду, на которую ему не хватает роли:

1. Use-case (через helper `ensure_admin_authorized(...)`) **сначала пишет** в admin-аудит запись `ADMIN_AUTHORIZATION_DENIED` отдельной короткой транзакцией.
2. Бросает `AdminAuthorizationDeniedError`.
3. Handler ловит ошибку и шлёт локализованный «недостаточно прав» — без подсказок «какая роль нужна» (чтобы не подсказывать, какую роль запросить).
4. Super-admin может посмотреть `/audit <актер_tg_id> admin_authorization_denied` и решить:
    - повысить роль штатно (через прямую правку `admins.role` в БД до появления `/admin_grant_role` в фазе 2.5+);
    - проигнорировать как ошибку оператора;
    - расследовать как попытку эскалации.

**Read-side `/audit`** доступен всем активным админам (включая `read_only`) — это намеренно, чтобы любой админ мог видеть свои собственные действия и действия системы. Сам факт чтения логируется (`ADMIN_AUDIT_QUERIED`) — super-admin видит, кто и какой срез аудита смотрел.

---

## 5. TOTP-confirm для опасных команд

Команды `/grant_length`, `/grant_thickness`, `/balance_set`, `/ban`, `/announce` идут двухфазно. У админа должен быть настроен `admin.totp_secret` (см. §3) и установлен Authenticator. Без TOTP-секрета фаза 1 откажет (`TotpNotConfiguredError`).

**Фаза 1 — выдача токена:**

1. Отправляете команду с параметрами в ЛС, например: `/grant_length 12345 50 "compensation per ticket #4567"`.
2. Use-case `RequestAdminConfirm`:
    - резолвит админа, проверяет `is_active`, RBAC (`AdminCommandKind.REQUEST_ADMIN_CONFIRM` доступна `support+`/`economist+`/`super_admin`);
    - валидирует параметры конкретной команды (`tg_id` существует, дельта в диапазоне, `reason` ≥ 10 символов);
    - выдаёт `/confirm`-токен `<6-значный hex>` и пишет `ADMIN_CONFIRM_REQUESTED` в audit.
3. Бот отвечает «выдан токен `<X>`, подтверди /confirm <TOTP-код>».

**Фаза 2 — подтверждение:**

1. В Authenticator-е смотрите свежий 6-значный код (период 30 секунд, `valid_window=1` — принимаем код этого окна и предыдущего).
2. Отправляете в тот же чат: `/confirm <код>`. Например: `/confirm 482931`.
3. Use-case `VerifyAdminConfirm`:
    - резолвит токен (по умолчанию TTL 5 минут с момента выдачи);
    - сверяет TOTP-код через `ITotpVerifier` (production = `PyOtpTotpVerifier`);
    - на успех: пишет `ADMIN_CONFIRM_VERIFIED`, передаёт управление dispatcher-у (`CONFIRM_DISPATCHERS`), который выполняет основную мутацию (например, `GrantLength`);
    - на провал (неверный код, просрочен, чужой токен): пишет `ADMIN_CONFIRM_FAILED`, отвечает «код не подошёл, попробуй ещё раз» — токен **не сжигается**, попробовать можно ещё раз в пределах TTL.

**Идемпотентность:** dispatch-функция собирает `idempotency_key` из `(admin_id, command, target, timestamp_minute)` (см. `bot/handlers/_idempotency.py`). Повторный `/confirm` с тем же токеном после успеха — no-op (use-case вернёт «уже выполнено»).

**Если токен просрочен:** просто запустите фазу 1 заново. Старый токен после 5 минут невалиден; никаких ручных действий не требуется.

---

## 6. Как читать `/audit`

Команда: `/audit [target_tg_id|-] [action|-] [limit]`. Все аргументы опциональные, разделитель — пробел. Спецсимвол `-` или `_` означает «без фильтра».

Примеры:

```
/audit                                # последние 20 записей по всем
/audit 12345                          # последние 20 от админа tg_id=12345
/audit 12345 admin_player_banned      # только баны от этого админа
/audit - admin_balance_set 50         # все админы, action=balance_set, limit=50
/audit - admin_authorization_denied   # все попытки эскалации
```

`limit` ≤ `MAX_AUDIT_LIMIT` (см. константу в `application/admin`). Большие выборки — через web-панель (фаза 4.5+).

**Категории `AdminAuditAction`** (`domain/admin/ports/admin_audit.py::AdminAuditAction`):

| Категория | Когда пишется |
|---|---|
| `ADMIN_PLAYER_LOOKUP` | `/find_player`, `/player` (даже read-only — super-admin должен видеть, кто и кого «пробивал»). |
| `ADMIN_CLAN_LOOKUP` | `/clan`, `/clan_daily_head_history`. |
| `ADMIN_BALANCE_GET` | `/balance_get`. |
| `ADMIN_AUDIT_QUERIED` | `/audit` (мета-аудит чтения аудита). |
| `ADMIN_PLAYER_FROZEN` / `ADMIN_PLAYER_UNFROZEN` | `/freeze`, `/unfreeze`. |
| `ADMIN_CLAN_FROZEN` / `ADMIN_CLAN_UNFROZEN` | `/freeze_clan`, `/unfreeze_clan`. |
| `ADMIN_PLAYER_BANNED` | `/ban` после успешного `/confirm`. |
| `ADMIN_BAN_BLOCKED` | `/ban` отбит на TOTP-фазе (handler не должен звать `BanPlayer.execute()`). |
| `ADMIN_GRANT_LENGTH` / `ADMIN_GRANT_THICKNESS` | `/grant_length`, `/grant_thickness` после успешного `/confirm`. |
| `ADMIN_BALANCE_SET` | `/balance_set` (audit пишется ДО `IBalanceReloader.reload()` — иначе при сбое reload-а потеряли бы запись о попытке). |
| `ADMIN_BROADCAST_SENT` | `/announce` — пишется **после** завершения фоновой рассылки, в `after` лежит `recipient_count` / `sent_count` / `failed_count` / `blocked_count` и `message_preview`. |
| `ADMIN_TOTP_SETUP` | `/admin_setup_totp` — `before`/`after` всегда `None`, секрет не пишется. |
| `ADMIN_CONFIRM_REQUESTED` / `ADMIN_CONFIRM_VERIFIED` / `ADMIN_CONFIRM_FAILED` | TOTP-confirm-flow на любую команду. |
| `ADMIN_AUTHORIZATION_DENIED` | RBAC-deny: попытка дёрнуть команду без роли. |

Каждая запись содержит `actor_admin_id` / `actor_tg_id` / `target_kind` / `target_id` / `before` / `after` / `reason` / `idempotency_key` / `source` (`bot`/`web`) / `tg_chat_id` (для бота) / `ip` (для веба) / `occurred_at`.

---

## 7. Recovery: что делать при потере 2FA

«Потеря 2FA» = админ потерял девайс с Authenticator-ом / случайно удалил аккаунт в Authenticator-е / TOTP-приложение не открывается. Сам секрет в БД (`admins.totp_secret`) живой, но получить из него код невозможно без приложения.

`/admin_setup_totp` для уже настроенного админа **не работает** (`TotpAlreadyConfiguredError`). Перезапустить self-service-флоу нельзя по дизайну. Способы восстановления:

### 7.1 Если ключ лежит в защищённом хранилище

Если оператор сохранил `secret`/`provisioning_uri` из логов VM в password manager при первой настройке (рекомендуется), просто заново импортируйте их в новый Authenticator. Никаких изменений в коде/БД не требуется.

### 7.2 Если ключ утерян безвозвратно — ручной сброс через БД

Делает другой активный `super_admin`. Если других super-admin-ов нет — см. §7.3.

1. Подключитесь к Postgres (через bastion / SSH-tunnel; никаких public DB endpoint-ов).
2. **До правки** запишите в `admin_audit_log` факт расследования инцидента (через `/audit` super-admin может видеть только команды бота — внеплановые правки БД фиксируйте отдельно в incident log).
3. Сбросьте секрет:
    ```sql
    BEGIN;
    SELECT id, tg_id, role, totp_secret IS NOT NULL AS had_totp
    FROM admins
    WHERE tg_id = <потерянный_tg_id>;
    -- убедитесь, что это нужный аккаунт; роль = super_admin
    UPDATE admins SET totp_secret = NULL WHERE tg_id = <потерянный_tg_id>;
    COMMIT;
    ```
4. Затронутый админ выполняет `/admin_setup_totp <bootstrap_password>` повторно — поле пустое, идемпотентность пропустит.
5. После успешной перенастройки **ротируйте `BOOTSTRAP_ADMIN_PASSWORD`** (см. §8) — пароль, который использовали для повторной настройки, теперь считаем скомпрометированным (хотя бы с учётом, что админ его уже видел повторно).
6. Сделайте отдельную запись в incident log (вне admin-аудита, например в `docs/history.md` если инцидент significant): кто, когда, почему, какой DB-апдейт.

### 7.3 Если других super-admin-ов нет (single-super-admin lockout)

Это **намеренно болезненный** сценарий — single-super-admin без backup-девайса противоречит политике безопасности. Восстановление возможно только через прямой доступ к БД и/или env-переменным:

1. Отдельным релизом / hotfix-деплоем добавьте в `BOOTSTRAP_ADMIN_IDS` вашего нового аварийного super-admin-а (новый `tg_id`, отличный от потерянного). Запись в `admins` создастся автоматически на следующем старте бота.
2. Через нового super-admin-а проделайте §7.2 для старого аккаунта.
3. После восстановления обнулите `BOOTSTRAP_ADMIN_IDS` обратно (или оставьте — он игнорируется, если `admins` уже не пуст).
4. Зафиксируйте инцидент в `docs/history.md`.

> **Профилактика:** держите минимум **двух** активных `super_admin`-ов с разными физическими девайсами Authenticator. Это политика, а не суждение тулинга.

---

## 8. Ротация `BOOTSTRAP_ADMIN_PASSWORD`

`BOOTSTRAP_ADMIN_PASSWORD` — out-of-band пароль для `/admin_setup_totp`. Не одноразовый по конструкции (use-case разрешает повторную настройку, если у админа `totp_secret IS NULL`), но политически считается **компрометируемым каждый раз, когда он покидает password manager** — поэтому ротируем регулярно и обязательно после §7.

**Когда ротировать:**

- После каждого использования (если использовали для recovery).
- Регулярно по календарю (рекомендация: квартал).
- При увольнении/ротации оператора с доступом к Devin Secrets `PIPIRIK_BOOTSTRAP_ADMIN_PASSWORD`.
- При подозрении на утечку.

**Как ротировать:**

1. Сгенерируйте новый случайный пароль ≥ 24 символов (`openssl rand -base64 32` подойдёт).
2. Обновите Devin Secret `PIPIRIK_BOOTSTRAP_ADMIN_PASSWORD` (`save_scope: org`) на новое значение.
3. Передеплойте бота (или дождитесь следующего реcтарта) — `BootstrapSettings` читается из env при старте процесса.
4. Удалите старый пароль из всех каналов хранения (password managers, заметки, чаты — везде).
5. Проверьте, что новая выдача через `/admin_setup_totp` работает: используйте на тестовом super-admin-е с `totp_secret = NULL` (если такого нет — см. §7.3, иначе пропустите этот шаг и ограничьтесь визуальной проверкой деплоя).

---

## 9. Известные ограничения и FAQ

**Q: Можно ли получить секрет TOTP в чат, а не в логи?**
A: Нет. Это намеренный security-trade-off (см. шапку `bot/handlers/admin_setup_totp.py`): история чата Telegram-а живёт долго и читается на любом устройстве с этим аккаунтом, а server-logs — single-source-of-truth с контролируемым доступом.

**Q: Можно ли «переустановить» TOTP, не дёргая БД?**
A: Нет, см. §7. Это защита от перехвата bootstrap-пароля.

**Q: Команды экономики работают в группе?**
A: Нет, только в ЛС. См. §0.

**Q: `/audit` молчит — не пишет о моих read-side-командах?**
A: Не все read-side пишутся: `/admin_stats` и `/balance_reload` — нет (`/admin_stats` — операционная статистика, не чувствительна; `/balance_reload` — чтение файла, без идентификатора игрока). Все player/clan/balance lookup-команды и сам `/audit` пишутся.

**Q: Что считается «опасной» командой и требует TOTP?**
A: На сегодня: `/ban`, `/grant_length`, `/grant_thickness`, `/balance_set`, `/announce`. См. таблицы в §2 и [`game_design.md`](game_design.md) §18.6.5.

**Q: Где живёт RBAC-матрица?**
A: `src/pipirik_wars/domain/admin/authorization.py::RoleBasedAdminAuthorizationPolicy._matrix`. Если открываете PR на новую admin-команду — добавьте значение в `AdminCommandKind`-enum, добавьте правило в матрицу, добавьте unit-тест (см. `tests/unit/domain/admin/test_authorization.py`). Команда без явного правила → fail-closed deny.

**Q: Что делать, если Authenticator показывает «code expired» сразу после ввода?**
A: Часы на VM и часы Authenticator-а должны синхронизироваться по NTP. Допустимое расхождение — `±30 секунд` (`valid_window=1` в `PyOtpTotpVerifier`). Большее расхождение → синхронизируйте часы VM (`timedatectl status`) и проверьте часы устройства. Если часы в порядке, а код всё равно не подходит — возможно, импортировали не тот секрет (например, чужого админа); сверьтесь с `event="admin_totp_setup"`-логом.

**Q: `/announce` доходит до всех игроков?**
A: До всех игроков из выборки локалей (`ru` / `en` / `*`), кто не забанил бота, в throttle-окне `25 msg/sec`. По завершении audit-запись `ADMIN_BROADCAST_SENT` содержит `recipient_count`, `sent_count`, `failed_count`, `blocked_count`. См. [`history.md`](history.md) запись `2026-05-07 — Спринт 2.5-D.4`.

---

## 10. Куда идти за подробностями

- **Спецификация админ-панели и политика безопасности:** [`game_design.md`](game_design.md) §18.6 (целиком).
- **История реализации (что в каком спринте сделано):** [`history.md`](history.md), записи `Спринт 2.5-A` … `Спринт 2.5-D.6`.
- **План оставшихся работ:** [`current_tasks.md`](current_tasks.md) и [`development_plan.md`](development_plan.md) §5.
- **Код RBAC-матрицы и use-case-ов:** `src/pipirik_wars/domain/admin/authorization.py`, `src/pipirik_wars/application/admin/`.
- **Код TOTP-флоу:** `src/pipirik_wars/application/admin/{setup_totp,request_confirm,verify_confirm}.py`, `src/pipirik_wars/infrastructure/admin/pyotp_*`.
- **Код handler-ов:** `src/pipirik_wars/bot/handlers/admin*.py`.

Если runbook и код разошлись — runbook не прав, открывайте PR на правку этого файла. Если разошлись runbook и `game_design.md` — приоритет у ГДД, и runbook нужно подтянуть.
