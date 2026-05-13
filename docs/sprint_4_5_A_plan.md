# Sprint 4.5-A — Foundation: FastAPI scaffold + Telegram Login + TOTP gate

> **Статус:** план готов, реализация — следующий агент.
> **Закрывает ПД-задачи:** 4.5.1 (FastAPI + TG Login) и 4.5.3 (TOTP gate).
> **НЕ закрывает в этом PR:** 4.5.2 (RBAC), 4.5.4 (dashboard widgets), 4.5.5–4.5.7 (Players/Clans/Audit), 4.5.8 (balance editor), 4.5.9 (network hardening), 4.5.10 (audit-source parity).
> **Базовый коммит:** `main = 9163b9f` (после merge PR #143 follow-up к 4.1-N).
> **Baseline `make ci`:** 7184 passed + 2 skipped + 95.26 % cov, 533.39 с.

---

## 1. Обоснование технологических выборов

Решения приняты исходя из:
* Текущего стека (Python 3.12, async-first, pydantic 2, SQLAlchemy 2 async, aiogram 3, structlog).
* Профиля админ-панели: единицы пользователей, admin-only, security-critical, низкая частота изменений UI, нулевая необходимость SPA-фронтенда.
* Принципа «минимум новых deps» и «переиспользуем существующие порты».

### 1.1 HTTP-фреймворк: **FastAPI**

* **За**: async-native (matches проект), декларативная зависимостная инъекция через `Depends`, авто-OpenAPI для будущих интеграций, идеально интегрируется с pydantic (уже в проекте), readability decorator-based роутов.
* **Альтернативы рассмотрены**:
  * `aiohttp.web` — уже используется в проекте для `/metrics` endpoint-а (Спринт 4.1-J/L). Но: ручной DI, нет встроенной валидации, нет OpenAPI-генерации. Подходит для одного хелсчека, не для админ-панели с 8+ роутами.
  * `Starlette` — FastAPI поверх него; смысла обходить FastAPI нет.
  * `Litestar` / `Robyn` — экзотика, не нужно. Команде надо быстро онбордиться.
* **Версия:** `fastapi>=0.115,<0.120` (sufficient pydantic-2 поддержка, актив. сапорт).

### 1.2 ASGI-сервер: **Uvicorn (standard)**

* **За**: де-факто стандарт, отличная производительность (httptools + uvloop), просто запускается под gunicorn в проде. `[standard]` extras — `websockets`, `uvloop`, `httptools` (для прода).
* **Версия:** `uvicorn[standard]>=0.32,<0.40`.

### 1.3 Templating: **Jinja2 + HTMX (CDN)**

* **За (Jinja2)**: server-side templating без JS-фреймворка, минимальная пов. атак. Идеально для админ-форм. Поддержка hot-reload в dev.
* **За (HTMX, без npm-build-step)**: partial-page updates через HTML-атрибуты. Никакого webpack/vite. Подгружается с CDN `<script src="https://unpkg.com/htmx.org@2"></script>` (либо vendored static-файл — рекомендуется vendored для офлайн-режима).
* **Альтернативы рассмотрены**:
  * **React/Vue SPA** — overkill для админки; ввели бы npm + webpack + проксирование API. Slow time-to-market.
  * **Django Admin** — отдельный фреймворк, дублирует ORM-слой.
  * **FastAPI + чистый jinja2 без htmx** — невозможен partial-update UX, страницы перезагружаются полностью; для редактора `balance.yaml` (4.5-G) это плохо.
* **Версии:** `jinja2>=3.1,<4`; HTMX **vendored** (один файл `static/htmx.min.js` v2.x ≈ 48KB, копируется при первой сборке).

### 1.4 Sessions: **`itsdangerous` signed cookies**

* **За**: stateless (нет server-side store), достаточно для коротких admin-сессий (1–4 ч), используется Flask/Starlette экосистемой, минимальная dep.
* **Содержимое cookie**: `admin_id`, `tg_username`, `totp_verified_at` (UNIX timestamp), `csrf_token`.
* **Подпись**: HMAC-SHA256 с секретом из `ADMIN_WEB_SECRET_KEY` (минимум 32 байта random). TTL — `max-age=3600` (1 час); `Secure=True`, `HttpOnly=True`, `SameSite=Lax`.
* **Альтернативы рассмотрены**:
  * `starlette.middleware.sessions.SessionMiddleware` — тот же `itsdangerous` внутри. Используем напрямую.
  * Server-side sessions в Redis — overkill; revocation не нужна (TTL короткий).
* **Версия:** `itsdangerous>=2.2,<3`.

### 1.5 CSRF: **Custom HMAC-token middleware**

* **За**: минимум deps (не нужен отдельный пакет), полный контроль. Токен генерируется при создании сессии (random 32 байта), хранится в session-cookie, проверяется на POST через скрытый input `csrf_token` либо заголовок `X-CSRF-Token` (для HTMX).
* **Алгоритм**:
  1. На каждый GET-ответ — устанавливаем `csrf_token` в session-cookie (если не set).
  2. На POST/PUT/DELETE/PATCH — middleware ожидает заголовок `X-CSRF-Token` ИЛИ form-field `csrf_token`; сравнивает с тем, что в session через `secrets.compare_digest`. Mismatch → 403.
  3. HTMX автоматически отправляет `X-CSRF-Token` из метатэга `<meta name="csrf-token">` (стандартный паттерн).
* **Альтернативы рассмотрены**:
  * `starlette-csrf` — лишний dep ради 50 строк кода.
  * `fastapi-csrf-protect` — заброшен.

### 1.6 QR-генерация: **`qrcode[pil]`**

* **За**: канонический Python QR-libpkg, активен. Используется один раз — на `/totp/setup`-странице для отображения provisioning-URI.
* **Версия:** `qrcode[pil]>=7.4,<9`.

### 1.7 Что НЕ берём

* **`python-multipart`** — НЕ нужен (НЕ принимаем file-uploads). Только form-urlencoded и JSON.
* **`pyjwt`** — НЕ нужен (cookies подписаны через itsdangerous, JWT — overkill для бэк-only).
* **`bcrypt` / `passlib`** — НЕ нужен (нет user-passwords; auth исключительно через TG Login + TOTP).
* **CORS** — НЕ нужен (single-origin app; cookies same-site).

### 1.8 Полный diff `pyproject.toml`

```toml
dependencies = [
    # ... существующие ...
    "fastapi>=0.115,<0.120",          # ADMIN-WEB: HTTP-фреймворк
    "uvicorn[standard]>=0.32,<0.40",  # ADMIN-WEB: ASGI-сервер
    "jinja2>=3.1,<4",                 # ADMIN-WEB: server-side templates
    "itsdangerous>=2.2,<3",           # ADMIN-WEB: signed-cookie sessions
    "qrcode[pil]>=7.4,<9",            # ADMIN-WEB: TOTP-setup QR
]

[project.optional-dependencies]
dev = [
    # ... существующие ...
    "httpx>=0.27,<1",                  # ALREADY PRESENT — also used by FastAPI TestClient
]
```

`httpx` уже в production-deps (TON-RPC) → переиспользуется TestClient-ом, дополнительной dev-deps НЕТ.

### 1.9 Console-script

В `[project.scripts]`:
```toml
[project.scripts]
pipirik-admin-web = "pipirik_wars.admin_web.main:run"
```

`run()` — точка входа: парсит CLI/env, поднимает `uvicorn.run(app, host=settings.host, port=settings.port)`.

---

## 2. Архитектура: package layout

```
src/pipirik_wars/admin_web/
├── __init__.py
├── main.py                     # create_app(settings) фабрика + run() entrypoint
├── settings.py                 # AdminWebSettings(BaseSettings)
├── composition.py              # build_admin_use_cases(settings, session_factory)
├── auth/
│   ├── __init__.py
│   ├── telegram_login.py       # verify_telegram_login_hash() + dataclass TelegramLoginData
│   ├── session.py              # AdminSession dataclass + load/save via itsdangerous
│   ├── csrf.py                 # CsrfMiddleware + generate_csrf_token()
│   └── ip_allowlist.py         # IpAllowlistMiddleware + parse CIDR list
├── deps.py                     # FastAPI Depends-helpers (current_admin, uow_session)
├── routes/
│   ├── __init__.py
│   ├── auth.py                 # GET /, POST /auth/telegram/callback, POST /logout
│   ├── totp.py                 # GET /totp, POST /totp/setup, POST /totp/verify
│   ├── dashboard.py            # GET /dashboard (placeholder)
│   └── health.py               # GET /healthz
├── templates/
│   ├── base.html               # навигация + CSRF-meta-tag + HTMX-загрузка
│   ├── login.html              # лендинг с TG Login Widget
│   ├── totp_setup.html         # QR-картинка + поле кода
│   ├── totp_verify.html        # только поле кода
│   ├── dashboard.html          # «Привет, {{ admin.username }}» + ссылка logout
│   └── partials/
│       └── flash.html          # HTMX-partial для toast-сообщений
└── static/
    ├── htmx.min.js             # vendored HTMX v2 (≈48KB; downloaded ONCE on initial scaffold)
    └── styles.css              # минимальный CSS (Pico.css? либо ручной)

src/pipirik_wars/admin_web/static/ — статика сервится через
StarletteStaticFiles middleware. Для прода рекомендуется wrapper-nginx
с долгим Cache-Control, но в этом PR — Python отдаёт напрямую.
```

**Принцип**: `admin_web/` живёт в той же кодовой базе, что `bot/`, но НЕ импортируется из `bot/`. И наоборот — `bot/` не импортируется из `admin_web/`. Зависимости — только domain + application + infrastructure.

---

## 3. Routes (подробно)

### 3.1 `GET /` — Login page

* **Auth:** anonymous.
* **Render:** `login.html` с встроенным TG Login Widget script:
  ```html
  <script async src="https://telegram.org/js/telegram-widget.js?22"
          data-telegram-login="{{ bot_username }}"
          data-size="large"
          data-userpic="false"
          data-onauth="onTelegramAuth(user)"
          data-request-access="write"></script>
  ```
  + custom `onTelegramAuth(user)` JS, который POST-ит JSON в `/auth/telegram/callback`.
* **Если уже авторизован** (session валидна, TOTP проверен): redirect → `/dashboard`.

### 3.2 `POST /auth/telegram/callback` — TG Login HMAC verification

* **Body:** JSON с полями TG Login Widget: `id`, `first_name`, `last_name?`, `username?`, `photo_url?`, `auth_date`, `hash`.
* **Шаги (use-case-style, but inline для простоты):**
  1. Парс JSON через pydantic-модель `TelegramLoginData`.
  2. Вычисление `secret_key = sha256(BOT_TOKEN.encode())`.
  3. `data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data) if k != "hash")`.
  4. `computed_hash = hmac_sha256(secret_key, data_check_string).hexdigest()`.
  5. `secrets.compare_digest(computed_hash, data.hash)` → mismatch ⇒ **401**.
  6. `if now - auth_date > 86400: raise 401` (anti-replay; TG-doc-рекомендация).
  7. Резолв админа через `IAdminRepository.get_by_tg_id(data.id)`.
     * `None` или `is_active=False` ⇒ **403 Forbidden** (запись в `admin_audit_log`: `ADMIN_AUTHORIZATION_DENIED`, `target_id=str(data.id)`, source=WEB).
  8. Создание session-cookie: `AdminSession(admin_id=admin.id, tg_username=data.username, totp_verified_at=None, csrf_token=secrets.token_urlsafe(32))`.
  9. **Redirect** → `/totp` (TOTP setup or verify, see 3.3).
* **Логирование (structlog):** `auth.tg_login.success` / `auth.tg_login.hmac_mismatch` / `auth.tg_login.inactive_admin`.

### 3.3 `GET /totp` — TOTP page

* **Auth:** session valid, `totp_verified_at=None`.
* **Логика:**
  * Если `admin.totp_secret IS NULL` ⇒ render `totp_setup.html` (POST goes to `/totp/setup`).
  * Иначе ⇒ render `totp_verify.html` (POST goes to `/totp/verify`).

### 3.4 `POST /totp/setup` — генерация TOTP-секрета

* **Auth:** session valid, `totp_verified_at=None`, `admin.totp_secret IS NULL`.
* **Body:** `bootstrap_password` (form-field).
* **Шаги:**
  1. CSRF-check.
  2. Вызов use-case `SetupAdminTotp.execute(SetupAdminTotpInput(actor_tg_id=session.tg_id, bootstrap_password=bootstrap_password, tg_chat_id=None, source=AdminAuditSource.WEB, ip=request.client.host))`.
  3. На успех — рендер `totp_setup.html` с QR-картинкой:
     * `secret`, `provisioning_uri` ⇒ qrcode.make(provisioning_uri) → PIL image → base64 data:image/png.
     * Юзер сканирует, копирует 6-значный код, отдельный POST на `/totp/verify`.
  4. На ошибку (`BootstrapPasswordInvalidError` / `BootstrapPasswordNotConfiguredError` / `AuthorizationError`) — flash-message «Не удалось», redirect на `/totp`.

> **ВАЖНО:** use-case `SetupAdminTotp` принимает `tg_chat_id`. В web-контексте `tg_chat_id=None`. Необходимо проверить, что use-case это допускает (по коду — да, см. `setup_totp.py:62-69`).

### 3.5 `POST /totp/verify` — verify 6-значного кода

* **Auth:** session valid, `totp_verified_at=None`, `admin.totp_secret IS NOT NULL`.
* **Body:** `code` (6 цифр).
* **Шаги:**
  1. CSRF-check.
  2. Загружаем admin, проверяем `is_active`.
  3. Прямой вызов `ITotpVerifier.verify(secret=admin.totp_secret, code=code, now=clock.now())`.
  4. На успех:
     * Обновить session: `totp_verified_at=now`, persist через `set_cookie`.
     * Запись в `admin_audit_log`: `ADMIN_TOTP_VERIFY_SUCCESS` (новый action; если его нет — переиспользуем `ADMIN_AUTHORIZATION_DENIED` зеркально для VERIFY_SUCCESS, или создаём новый action в отдельной миграции).
     * Redirect → `/dashboard`.
  5. На неуспех: flash «Неверный код», retry counter в session (если > 5 за 5 мин — temp-block).

> **Решение для следующего агента:** проверить, есть ли уже action `ADMIN_TOTP_VERIFY_SUCCESS` в `AdminAuditAction`-enum-е (`domain/admin/ports/admin_audit.py`). Если нет — добавить + миграция Alembic, расширяющая CHECK-constraint на `admin_audit_log.action`. Или (предпочтительно для 4.5-A) — использовать существующий action для совместимости, отложив новый action до 4.5-F (Audit-log UI), когда будем смотреть на полный список.

### 3.6 `GET /dashboard` — placeholder

* **Auth:** session valid, `totp_verified_at < 4h ago`.
* **Render:** `dashboard.html` — «Привет, {{ admin.username }}! Роль: {{ admin.role }}. (Здесь будут DAU/караваны/рейды — Спринт 4.5-D.)»

### 3.7 `POST /logout`

* **Auth:** any session.
* **Шаги:**
  1. CSRF-check.
  2. Запись в `admin_audit_log`: `ADMIN_WEB_LOGOUT` (новый action ⇒ см. примечание в 3.5; либо опустить логирование в 4.5-A и добавить в 4.5-F).
  3. Очистка session-cookie (`response.delete_cookie("session")`).
  4. Redirect → `/`.

### 3.8 `GET /healthz`

* **Auth:** anonymous.
* **Render:** `{"status": "ok", "uptime_seconds": int}`. Не требует БД-коннекта (liveness-only).
* Для readiness-проб (4.5-H/4.5.9) — отдельный `/readyz` с БД-pingом.

---

## 4. Security model

### 4.1 IP-allowlist middleware

* **Env-var:** `ADMIN_WEB_ALLOWED_IPS` — comma-separated CIDR-список (e.g. `"10.0.0.0/8,192.168.1.42/32"`). Default — пустая строка ⇒ **deny-all** (fail-closed).
* **Бой-mode** (`ADMIN_WEB_ALLOWED_IPS="*"`) — допускается только для localhost-dev, лог при старте предупреждает.
* **Источник IP:** `X-Forwarded-For` если стоит за прокси, иначе `request.client.host`. Поведение управляется флагом `ADMIN_WEB_TRUST_PROXY` (default `False`).
* **Реализация:** `IpAllowlistMiddleware(BaseHTTPMiddleware)` с `ipaddress`-stdlib для проверки CIDR.

### 4.2 CSRF

См. §1.5. Подробности: использовать `secrets.compare_digest` для constant-time. Token-rotation при логине/логауте.

### 4.3 Session

См. §1.4. Cookie атрибуты: `Secure=True` (HTTPS-only — в dev можно отключить через `ADMIN_WEB_COOKIE_INSECURE_DEV=true`), `HttpOnly=True`, `SameSite=Lax`.

### 4.4 Headers

* `Content-Security-Policy: default-src 'self'; script-src 'self' telegram.org;`
  * `'self'` — для vendored static (htmx).
  * `telegram.org` — для TG Login Widget script.
* `X-Frame-Options: DENY`
* `X-Content-Type-Options: nosniff`
* `Referrer-Policy: strict-origin-when-cross-origin`
* `Strict-Transport-Security: max-age=31536000; includeSubDomains` (только в HTTPS-deploy)

### 4.5 Auth flow state machine

```
[anonymous] ──/auth/telegram/callback (HMAC OK + admin found + is_active)──> [session.admin_id, totp_verified_at=None]
                                                                                          │
                                                                                          ├─ totp_secret IS NULL ─> /totp/setup ─> /totp/verify ─> [totp_verified_at=now] ─> /dashboard
                                                                                          │
                                                                                          └─ totp_secret SET ─> /totp/verify ─> [totp_verified_at=now] ─> /dashboard

[totp_verified_at < 4h ago] ──/logout──> [anonymous]
[totp_verified_at > 4h ago] ──any request──> redirect /totp
```

---

## 5. Composition root (DI)

### 5.1 `src/pipirik_wars/admin_web/composition.py`

Файл создаёт subset-Container специально под admin-web, переиспользует существующие конструкторы:

```python
@dataclass(frozen=True, slots=True)
class AdminWebContainer:
    settings: AdminWebSettings
    session_factory: async_sessionmaker[AsyncSession]
    bot_username: str  # для TG Login Widget
    bot_token: str     # для HMAC верификации
    secret_key: bytes  # для itsdangerous

    # use-cases
    setup_admin_totp: SetupAdminTotp
    # ... (далее по PR-ам — get_player_card, find_players, etc.)

    # порты
    admin_repository_factory: Callable[[SqlAlchemyUnitOfWork], IAdminRepository]
    uow_factory: Callable[[], SqlAlchemyUnitOfWork]
    totp_verifier: ITotpVerifier
    totp_secret_generator: ITotpSecretGenerator
    clock: IClock
    admin_audit_logger_factory: Callable[[SqlAlchemyUnitOfWork], IAdminAuditLogger]
    authorization_policy: IAdminAuthorizationPolicy


def build_admin_web_container(settings: AdminWebSettings) -> AdminWebContainer:
    engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    # ... оставшиеся фабрики ...
```

**Принцип:** контейнер инициализируется один раз при старте app, инжектится в роуты через `Depends`.

### 5.2 `src/pipirik_wars/admin_web/deps.py`

FastAPI Depends-хелперы:

```python
def get_container(request: Request) -> AdminWebContainer:
    return request.app.state.container

def get_session(request: Request) -> AdminSession | None:
    return getattr(request.state, "session", None)

def get_current_admin(
    session: AdminSession | None = Depends(get_session),
    container: AdminWebContainer = Depends(get_container),
) -> Admin:
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if session.totp_verified_at is None or _is_totp_expired(session.totp_verified_at):
        raise HTTPException(status_code=302, headers={"Location": "/totp"})
    async with container.uow_factory() as uow:
        admin = await container.admin_repository_factory(uow).get_by_id(session.admin_id)
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=403, detail="Admin inactive")
    return admin
```

---

## 6. AdminWebSettings (env-config)

`src/pipirik_wars/admin_web/settings.py`:

```python
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminWebSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADMIN_WEB_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8080

    secret_key: SecretStr = Field(min_length=32)  # signed-cookie key
    bot_username: str  # для рендеринга TG Login Widget
    bot_token: SecretStr  # для HMAC верификации (тот же, что и BOT_TOKEN основного бота)

    database_url: str  # async PG / sqlite

    allowed_ips: str = ""  # CSV CIDR
    trust_proxy: bool = False
    cookie_insecure_dev: bool = False  # ОПАСНО: ставить True только в dev

    totp_verify_ttl_seconds: int = 14400  # 4 часа
    session_max_age_seconds: int = 3600  # 1 час
```

Env-vars (примеры):
```bash
ADMIN_WEB_HOST=0.0.0.0
ADMIN_WEB_PORT=8080
ADMIN_WEB_SECRET_KEY="$(openssl rand -hex 32)"
ADMIN_WEB_BOT_USERNAME=PipirikWarsBot
ADMIN_WEB_BOT_TOKEN="<тот же, что BOT_TOKEN>"
ADMIN_WEB_DATABASE_URL=postgresql+asyncpg://...
ADMIN_WEB_ALLOWED_IPS="10.0.0.0/8,192.168.1.42/32"
ADMIN_WEB_TRUST_PROXY=true
```

---

## 7. Тест-план (≥30 тестов)

### 7.1 Unit (без БД, без HTTP)

`tests/unit/admin_web/test_telegram_login.py`:
* `verify_telegram_login_hash`:
  * happy path (валидный HMAC + auth_date свежий) ⇒ возвращает `TelegramLoginData`
  * mismatch HMAC ⇒ raises `InvalidLoginHashError`
  * stale auth_date (> 86400s) ⇒ raises `StaleLoginError`
  * пустой `bot_token` ⇒ raises ValueError

`tests/unit/admin_web/test_session.py`:
* encode/decode round-trip
* tampered signature ⇒ `BadSignature` (itsdangerous)
* expired (max_age exceeded) ⇒ raises `SignatureExpired`

`tests/unit/admin_web/test_csrf.py`:
* token validation: matching ⇒ OK; mismatching ⇒ 403
* `secrets.compare_digest` constant-time

`tests/unit/admin_web/test_ip_allowlist.py`:
* CIDR-список парсится корректно (IPv4 и IPv6 mix)
* empty list ⇒ deny-all
* "*" ⇒ allow-all (с warning)
* `X-Forwarded-For` берётся только при `trust_proxy=True`

### 7.2 Integration (FastAPI TestClient + in-memory или sqlite БД)

`tests/integration/admin_web/test_auth_flow.py`:
* GET / без auth ⇒ 200, render `login.html`
* POST /auth/telegram/callback (валидный HMAC, admin existed and is_active) ⇒ 302 → /totp + session cookie
* POST /auth/telegram/callback (admin не существует) ⇒ 403, audit-запись `ADMIN_AUTHORIZATION_DENIED`
* POST /auth/telegram/callback (admin.is_active=False) ⇒ 403
* POST /auth/telegram/callback (HMAC mismatch) ⇒ 401

`tests/integration/admin_web/test_totp_setup.py`:
* GET /totp (admin.totp_secret IS NULL) ⇒ render `totp_setup.html`
* POST /totp/setup (валидный bootstrap_password) ⇒ updates admin.totp_secret, renders QR
* POST /totp/setup (невалидный bootstrap_password) ⇒ 400, audit-запись о попытке

`tests/integration/admin_web/test_totp_verify.py`:
* GET /totp (admin.totp_secret SET) ⇒ render `totp_verify.html`
* POST /totp/verify (валидный code) ⇒ updates session.totp_verified_at, redirect → /dashboard
* POST /totp/verify (невалидный code) ⇒ flash, retry counter increments

`tests/integration/admin_web/test_dashboard_guard.py`:
* GET /dashboard без session ⇒ 401
* GET /dashboard с session, totp_verified_at=None ⇒ 302 → /totp
* GET /dashboard с session, totp_verified_at > 4h ago ⇒ 302 → /totp
* GET /dashboard с session, totp_verified_at < 4h ago ⇒ 200

`tests/integration/admin_web/test_csrf_middleware.py`:
* POST без CSRF-токена ⇒ 403
* POST с неверным CSRF-токеном ⇒ 403
* POST с верным CSRF-токеном ⇒ OK

`tests/integration/admin_web/test_ip_allowlist_middleware.py`:
* Запрос с allowed IP ⇒ OK
* Запрос с denied IP ⇒ 403
* `trust_proxy=True` + `X-Forwarded-For: <allowed>` ⇒ OK

`tests/integration/admin_web/test_health.py`:
* GET /healthz без auth ⇒ 200, `{"status": "ok"}`
* IP-allowlist НЕ применяется к /healthz (требование для health-чеков от Kubernetes/load-balancer)

### 7.3 Architecture contract

Добавить в `setup.cfg`/`.importlinter` правило:
* `bot.*` MUST NOT import from `admin_web.*`
* `admin_web.*` MUST NOT import from `bot.*`
* `admin_web.*` allowed to import from: `domain.*`, `application.*`, `infrastructure.*`

Проверить через `make imports` — должно быть **5 kept, 0 broken** (текущие 4 + новый контракт).

---

## 8. Implementation checklist для следующего агента

### A.0 — Snapshot pivot + sticky HANDOFF (этот коммит)

* [x] `docs/sprint_4_5_A_plan.md` (этот файл)
* [x] `AGENT_HANDOFF.md` (sticky baton)
* [x] `docs/current_tasks.md` — snapshot pivot
* [x] `docs/history.md` — placeholder entry о hand-off (но не помечать как done)

### A.1 — pyproject.toml + lockfile

* [ ] `pyproject.toml`: добавить 5 deps (см. §1.8)
* [ ] `pyproject.toml`: добавить `pipirik-admin-web` в `[project.scripts]`
* [ ] `uv sync` / `pip install -e .[dev]` → проверить что все ставится
* [ ] `make lint typecheck imports` — pass

### A.2 — settings.py

* [ ] `src/pipirik_wars/admin_web/settings.py` — `AdminWebSettings(BaseSettings)`
* [ ] Тесты: `tests/unit/admin_web/test_settings.py` (3-4 теста: min-length-validator, defaults, env-loading)

### A.3 — Auth helpers

* [ ] `src/pipirik_wars/admin_web/auth/telegram_login.py`
* [ ] `src/pipirik_wars/admin_web/auth/session.py`
* [ ] `src/pipirik_wars/admin_web/auth/csrf.py`
* [ ] `src/pipirik_wars/admin_web/auth/ip_allowlist.py`
* [ ] Unit-тесты (см. §7.1)

### A.4 — Composition root

* [ ] `src/pipirik_wars/admin_web/composition.py` — `AdminWebContainer` + `build_admin_web_container(settings)`
* [ ] `src/pipirik_wars/admin_web/deps.py` — FastAPI Depends-хелперы

### A.5 — Routes + templates

* [ ] `src/pipirik_wars/admin_web/routes/{auth,totp,dashboard,health}.py`
* [ ] `src/pipirik_wars/admin_web/templates/{base,login,totp_setup,totp_verify,dashboard}.html`
* [ ] `src/pipirik_wars/admin_web/static/htmx.min.js` (vendored v2)
* [ ] `src/pipirik_wars/admin_web/static/styles.css` (минимум)
* [ ] Integration-тесты (см. §7.2)

### A.6 — Main entrypoint

* [ ] `src/pipirik_wars/admin_web/main.py`:
  * `create_app(settings) -> FastAPI`
  * `run() -> None` (console-script entrypoint; парс env + uvicorn.run)
* [ ] Smoke-тест запуска: `pipirik-admin-web --help` или `python -m pipirik_wars.admin_web.main`

### A.7 — Architecture contract

* [ ] Дополнить `setup.cfg`/`.importlinter` (см. §7.3)
* [ ] `make imports` → 5 kept, 0 broken

### A.8 — Doc-sync + PR

* [ ] `docs/history.md` — финальная запись 4.5-A с метриками
* [ ] `docs/current_tasks.md` — отметить 4.5.1 и 4.5.3 как `[x]`, 4.5.2 и далее — `[ ]`
* [ ] `git rm AGENT_HANDOFF.md`
* [ ] PR через `git_pr(action="create")` + body по template (см. §9 ниже)
* [ ] CI: `git pr_checks wait_mode=all` до green
* [ ] Сообщение пользователю с PR-ссылкой

---

## 9. PR body template (для следующего агента)

```markdown
## Summary

Спринт **4.5-A «Foundation: FastAPI scaffold + Telegram Login + TOTP gate»** —
первый PR опц. Спринта 4.5 «Веб-админ-панель». Закрывает задачи 4.5.1 (FastAPI
+ TG Login) и 4.5.3 (TOTP gate) из ПД §7.

Что сделано (A.1–A.8):
* A.1 — добавлены 5 production-deps (fastapi, uvicorn[standard], jinja2,
  itsdangerous, qrcode[pil]). Console-script `pipirik-admin-web` ⇒ `admin_web.main:run`.
* A.2 — `AdminWebSettings(BaseSettings)` с 9 env-vars (host/port/secret_key/
  bot_username/bot_token/database_url/allowed_ips/trust_proxy/cookie_insecure_dev).
* A.3 — 4 auth-хелпера: TG Login HMAC verification, signed-cookie sessions
  (itsdangerous), CSRF middleware (custom HMAC + X-CSRF-Token / form-field),
  IP-allowlist middleware (CIDR через `ipaddress`-stdlib).
* A.4 — `AdminWebContainer` (DI subset) + `build_admin_web_container()`;
  FastAPI Depends-хелперы (`get_container`, `get_session`, `get_current_admin`).
* A.5 — 8 routes (/, /auth/telegram/callback, /totp, /totp/setup, /totp/verify,
  /dashboard, /logout, /healthz) + Jinja2-templates + vendored HTMX.
* A.6 — `create_app(settings) -> FastAPI` factory + `run()` entrypoint.
* A.7 — `bot.* ⇏ admin_web.*` + `admin_web.* ⇏ bot.*` import-linter rules.
* A.8 — 35+ тестов (15 unit + 20 integration); `make ci` локально passed.

## Review & Testing Checklist for Human

Риск: **yellow** — новый production-сервис с auth, но изолирован (отдельный
процесс + порт), не трогает bot/-pipeline, использует существующие admin
use-case-ы из 2.5.

- [ ] **TG Login Widget E2E** на staging-домене: `ADMIN_WEB_BOT_USERNAME` указан,
      TG Login виджет рендерится, после клика — редирект на /totp, далее QR
      сканируется в Google Authenticator, 6-значный код принимается, /dashboard
      открывается.
- [ ] **IP-allowlist sanity**: `ADMIN_WEB_ALLOWED_IPS="*"` логирует warning при
      старте; `ADMIN_WEB_ALLOWED_IPS=""` отдаёт 403 на любой запрос.
- [ ] **TOTP-rate-limit** на /totp/verify: 5 неверных кодов за 5 мин ⇒ session
      получает temp-block (см. retry counter в session).

## Notes

* После merge: deploy admin-web как отдельный systemd-юнит / Docker-контейнер
  на отдельном поддомене (e.g. `admin.pipirik.example`). Nginx-proxy с HTTPS
  и `X-Forwarded-For` (ADMIN_WEB_TRUST_PROXY=true).
* Следующий PR — **4.5-B**: RBAC (4.5.2) + `AuthorizedRoute`-хелпер на каждый
  permission. Затем 4.5-C (Players section), 4.5-D (dashboard widgets), и т.д.
```

---

## 10. Открытые вопросы (для пользователя или следующего агента)

1. **TG Login Widget bot_username:** в проекте есть единственный prod-bot — `Pipirik Wars Bot` (или другое). Точное имя надо взять из `BOT_USERNAME` env-vars (если оно настроено) либо запросить у пользователя.
2. **HTMX версия:** v2 (latest) — стабильна. v1 — legacy. Использовать **v2**.
3. **CSS-фреймворк:** оставить **минимальный hand-written styles.css** в 4.5-A; в 4.5-B рассмотреть Pico.css (classless, ~10KB).
4. **AuditAction для web-flow:** нужны как минимум 3 новых action-а: `ADMIN_WEB_LOGIN_SUCCESS`, `ADMIN_WEB_LOGIN_FAILED`, `ADMIN_WEB_LOGOUT`. **Решение:** для 4.5-A — переиспользовать `ADMIN_AUTHORIZATION_DENIED` для failure-кейсов; success-логин и logout — БЕЗ audit-записи в этом PR (отложить до 4.5-F с миграцией). Запись о действиях через web — уже через source=WEB в существующих action-ах use-case-ов.
5. **TOTP-setup без bootstrap_password в web-контексте:** use-case требует bootstrap-пароль. Если в продакшене этот пароль не настроен (`bootstrap_admin_password is None`) — TOTP setup НЕ доступен через web. **Решение для 4.5-A:** добавить отдельную ветку в /totp/setup-route: «не настроено — обратитесь к super-admin через бот, чтобы он выполнил `/admin_setup_totp`».
6. **Database URL:** admin-web подключается к **той же** БД, что и бот. Use `ADMIN_WEB_DATABASE_URL` env-var ИЛИ переиспользовать `DATABASE_URL` из основного бота. **Рекомендация:** переиспользовать `DATABASE_URL` (один источник истины), но дать `ADMIN_WEB_DATABASE_URL` приоритет, если задан.

---

## 11. Discovery-материалы (для быстрого онбординга следующего агента)

* **Use-case `SetupAdminTotp`:** `src/pipirik_wars/application/admin/setup_totp.py`. Принимает `actor_tg_id`, `bootstrap_password`, `tg_chat_id` (Optional!). Источник BOT по умолчанию; передавать `source=AdminAuditSource.WEB` через расширение Input — **РЕШЕНИЕ**: Add `source: AdminAuditSource = AdminAuditSource.BOT` + `ip: str | None = None` к Input-DTO. См. как это сделано в `unfreeze_player.py:114-122`.
* **IAdminRepository:** `src/pipirik_wars/domain/admin/repositories.py:10`. Метод `get_by_tg_id(tg_id) -> Admin | None`.
* **AdminAuditSource:** `src/pipirik_wars/domain/admin/ports/admin_audit.py:189` — enum `BOT`/`WEB`. Уже поддержано доменом.
* **ITotpVerifier:** `src/pipirik_wars/domain/admin/ports/admin_confirm.py:44`. Конкретная реализация: `PyOtpTotpVerifier`.
* **ITotpSecretGenerator:** `src/pipirik_wars/domain/admin/ports/totp_secret_generator.py:23`. Реализация: `PyOtpTotpSecretGenerator`.
* **AdminORM:** `src/pipirik_wars/infrastructure/db/models/admin.py:16`.
* **Composition root (bot):** `src/pipirik_wars/bot/main.py::build_container()` — НЕ переиспользуется напрямую, но является source-of-truth для конструирования repos и use-cases. Скопировать паттерны для admin-web composition root.
* **Settings parsing:** `src/pipirik_wars/infrastructure/settings.py` — пример Pydantic-Settings класса для бота. Использовать как референс.

---

## 12. Estimated effort

* **A.1 (deps):** 30 мин
* **A.2 (settings):** 30 мин
* **A.3 (auth helpers):** 2 ч
* **A.4 (composition + deps):** 1 ч
* **A.5 (routes + templates + tests):** 2-3 ч
* **A.6 (main entrypoint):** 30 мин
* **A.7 (import-linter):** 15 мин
* **A.8 (doc-sync + PR):** 30 мин

**Total:** 7-8 часов чистого времени; на одного агента — 1 рабочая сессия.

**Lines-of-Code estimate:**
* Production code: ~900-1100 LOC (preponderant: routes + composition + auth)
* Tests: ~600-800 LOC (35-40 тестов)
* Templates + static: ~200 LOC (HTML + минимальный CSS)
* **Total:** ~1700-2100 LOC, single PR.
