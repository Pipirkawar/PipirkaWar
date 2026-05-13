# Runbook: деплой Pipirik Wars на VPS 1 GB + Neon free Postgres

Спринт **1.5.H** (ПД 1.5.7). Цель — поднять MVP за < 30 минут на минимальном стенде:

- **VPS:** 1 GB RAM, 1 vCPU, 25 GB SSD (любой провайдер: DigitalOcean, Hetzner, Vultr, Timeweb).
- **БД:** [Neon](https://neon.tech) free tier (3 GB storage, без лимита на queries).
- **Бот:** Docker + docker compose, режим long-polling (без webhook-а — упрощает деплой, нет нужды в TLS-терминаторе).

> **Кому подходит:** закрытый альфа-тест (≤ 200 DAU). Под Phase-2 (открытое тестирование) понадобится отдельный Postgres + webhook через Cloudflare Tunnel или nginx + Let's Encrypt.

---

## 0. Pre-flight

Понадобится:

- доступ к VPS по SSH (ключ + sudo);
- BOT_TOKEN от [@BotFather](https://t.me/BotFather);
- список Telegram tg_id первых супер-админов (проще всего — узнать у [@userinfobot](https://t.me/userinfobot));
- аккаунт на [neon.tech](https://neon.tech) (Google/GitHub-логин, без карты).

## 1. Поднять Postgres на Neon

1. На neon.tech → **New Project**:
    - имя: `pipirik-wars-prod`,
    - регион: ближайший к VPS (для VPS в Frankfurt — `EU Central`),
    - Postgres version: 16.
2. Открыть **Dashboard → Connection Details**.
3. Скопировать `DATABASE_URL`. Обычно вида:
    ```
    postgresql://pipirik_owner:XXXXXXXX@ep-cool-xxx.eu-central-1.aws.neon.tech/pipirik?sslmode=require
    ```
4. **Заменить scheme** на `postgresql+asyncpg://` (asyncpg — наш драйвер) и **убрать** `sslmode=require` (asyncpg использует свой SSL — параметр через query string не поддерживается):
    ```
    postgresql+asyncpg://pipirik_owner:XXXXXXXX@ep-cool-xxx.eu-central-1.aws.neon.tech/pipirik
    ```
    > Если на этапе миграций вылезет «SSL required» — добавить `?ssl=true` (asyncpg-вариант) или сконфигурировать SSL в `infrastructure/db/engine.py`. Neon **обязательно** требует SSL.

## 2. Подготовить VPS

```bash
# 1. SSH в VPS как root или sudo-пользователь.
ssh user@vps.example.com

# 2. Обновить пакеты + поставить Docker (если ещё нет).
sudo apt-get update && sudo apt-get install -y ca-certificates curl
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
# Перелогиниться (выйти и зайти заново), чтобы группа применилась.
exit
ssh user@vps.example.com

# 3. Проверить, что docker compose работает.
docker --version
docker compose version

# 4. Поставить git и склонировать репо (либо rsync-ом, если репо приватное).
sudo apt-get install -y git
cd ~
git clone https://github.com/Pipirkawar/PipirkaWar.git
cd PipirkaWar
```

## 3. Подготовить prod-конфиг

В отличие от локального `docker-compose.yml`, в production **не нужен** локальный сервис `postgres` (БД на Neon). Сделаем prod-overlay:

```bash
cat > ops/docker/docker-compose.prod.yml <<'EOF'
# Production-overlay: использует Neon вместо локальной Postgres.
# Запуск:
#   docker compose -f ops/docker/docker-compose.yml -f ops/docker/docker-compose.prod.yml up -d --build
#
# Что меняется относительно базового compose:
#   - сервис `postgres` отключается (scale: 0);
#   - `migrations` и `bot` зависят только друг от друга, не от postgres;
#   - DATABASE_URL берётся из .env (внешний Neon), а не из шаблона "@postgres".

services:
  postgres:
    profiles: ["never"]  # Neon — внешний, локальная БД не нужна.

  migrations:
    depends_on: !reset []   # снимаем зависимость от postgres
    environment:
      DATABASE_URL: ${DATABASE_URL:?DATABASE_URL must be set in .env (Neon)}

  bot:
    depends_on:
      migrations:
        condition: service_completed_successfully
    environment:
      DATABASE_URL: ${DATABASE_URL:?DATABASE_URL must be set in .env (Neon)}
EOF
```

Заполнить `.env` (никогда не коммитить!):

```bash
cat > .env <<EOF
BOT_TOKEN=<from-botfather>
DATABASE_URL=postgresql+asyncpg://pipirik_owner:XXXXXXXX@ep-cool-xxx.eu-central-1.aws.neon.tech/pipirik
BOOTSTRAP_ADMIN_IDS=<your-tg-id-1>,<your-tg-id-2>
BOT_MAX_DAU=200
LOG_LEVEL=INFO
EOF
chmod 600 .env
```

## 4. Запуск

```bash
# Билд и запуск в фоне (-d):
docker compose \
    -f ops/docker/docker-compose.yml \
    -f ops/docker/docker-compose.prod.yml \
    up -d --build

# Посмотреть, что миграции прошли:
docker compose -f ops/docker/docker-compose.yml -f ops/docker/docker-compose.prod.yml logs migrations

# Ожидаем:
#   pipirik-migrations  | INFO  [alembic.runtime.migration] Running upgrade -> 0006_users_locale_override

# Логи бота:
docker compose -f ops/docker/docker-compose.yml -f ops/docker/docker-compose.prod.yml logs -f bot

# Ожидаем:
#   pipirik-bot         | INFO  aiogram.dispatcher  ...  Run polling for bot @YourBotUsername
```

## 5. Smoke-тест

В Telegram:

1. Найти бота по username (`@YourBotUsername`).
2. `/start` — должен ответить «Привет!» (или EN-аналог, в зависимости от вашей локали).
3. **Зарегистрироваться:** `/start` в любом групп-чате, где бот добавлен админом.
4. `/profile` — карточка пипирика.
5. `/forest` — поход в лес. Бот должен ответить «Ты ушёл в лес...» и через 10–20 минут прислать finished-сообщение.
6. `/oracle` — предсказание (даётся раз в сутки на пользователя).
7. `/lang en` → `/profile` — должен переключиться на английскую локаль.
8. **Admin-команды** (только для tg_id из `BOOTSTRAP_ADMIN_IDS`):
    - `/dau_stats` — текущий DAU vs MAX_DAU.
    - `/set_max_dau 100` — поменять лимит на горячую.
    - `/balance_reload` — перечитать `config/balance.yaml`.

> Если `/start` не приходит ответ — проверьте `docker logs pipirik-bot`. Самая частая причина — невалидный `BOT_TOKEN` (бот @BotFather, проверьте, что не перепутан с тестовым).

## 6. Закрытый альфа-тест (24 часа)

Definition of Done MVP (см. `docs/dod_mvp.md`) требует **24 часа стабильной работы под закрытым тестом**.

Минимальный мониторинг:

```bash
# Каждые 6 часов проверяем, что бот живой:
docker compose -f ops/docker/docker-compose.yml -f ops/docker/docker-compose.prod.yml ps

# Должен быть статус:
#   pipirik-bot   ...   Up 6 hours (healthy)

# Если статус не healthy — смотрим healthcheck:
docker inspect pipirik-bot --format='{{json .State.Health}}'
```

> Healthcheck из Dockerfile: `python -c "from pipirik_wars.infrastructure.settings import Settings; Settings()"`. Если падает — проблема в env (например, поломался `DATABASE_URL`).

## 7. Обновление до новой версии

```bash
# 1. Подтянуть свежий код:
cd ~/PipirkaWar
git pull --ff-only origin main

# 2. Пересобрать и перезапустить:
docker compose \
    -f ops/docker/docker-compose.yml \
    -f ops/docker/docker-compose.prod.yml \
    up -d --build

# 3. Проверить, что миграции прошли (если они были в этом релизе):
docker compose -f ops/docker/docker-compose.yml -f ops/docker/docker-compose.prod.yml logs migrations | tail -20
```

> **Безопасность миграций:** alembic-миграции в Pipirik Wars написаны как **идемпотентные additive-only** (новые таблицы / nullable-колонки / partial unique indexes). DROP COLUMN / ALTER TYPE — только через cascade-миграцию с двумя релизами (deploy → backfill → switch → cleanup). Это закрывает риск «накатили миграцию, потом откат не пускает».

## 8. Откат

Если после деплоя что-то сломалось:

```bash
# 1. Откатить код:
git checkout <previous-commit-sha>

# 2. Пересобрать:
docker compose \
    -f ops/docker/docker-compose.yml \
    -f ops/docker/docker-compose.prod.yml \
    up -d --build

# 3. Если откат требует и downgrade миграции (редко) — alembic downgrade:
docker compose -f ops/docker/docker-compose.yml -f ops/docker/docker-compose.prod.yml run --rm migrations alembic downgrade -1
```

> Downgrade миграции на production-БД с реальными пользователями — **рискованная операция**. Перед запуском — снапшот БД (Neon → Branch).

## 9. Часто задаваемые вопросы

### Бот не отвечает на `/start`

1. `docker logs pipirik-bot` — ищем ERROR / Exception.
2. Проверить `BOT_TOKEN` — должен быть из @BotFather, без пробелов / лишних кавычек.
3. Проверить, что бот добавлен в чат (или вы пишете в личку).
4. `docker compose ps` → бот healthy?

### Postgres connection refused (Neon)

1. Проверить, что `DATABASE_URL` начинается с `postgresql+asyncpg://`, а не `postgresql://`.
2. Проверить, что в URL **нет** `?sslmode=require` (asyncpg не понимает этот параметр).
3. На Neon — проект не «paused» (free-tier засыпает после 5 мин неактивности; при первом запросе просыпается, но первый запрос может зависать на 5–10 секунд).

### Healthcheck показывает unhealthy

```bash
docker inspect pipirik-bot --format='{{json .State.Health}}' | python -m json.tool
```

В `Log[].Output` — текст ошибки. Чаще всего: невалидный env (например, `BOT_TOKEN` пустой).

### Memory pressure (1 GB RAM)

Pipirik Wars в покое жрёт ~150 MB RAM. Postgres локальный — ещё ~80 MB. С Neon (внешний) — суммарно ~150 MB. Если приближаетесь к лимиту — проверить, что в `docker stats` нет утечек (растёт RSS бота со временем).

```bash
docker stats --no-stream
```

### Где смотреть audit log?

В БД, таблица `audit_log` (см. `infrastructure/db/models/audit_log.py`). Просто:

```bash
docker compose -f ops/docker/docker-compose.yml -f ops/docker/docker-compose.prod.yml run --rm migrations \
    psql "$DATABASE_URL" -c "SELECT created_at, action, actor_id, payload FROM audit_log ORDER BY created_at DESC LIMIT 20;"
```

(Удобнее — подключиться к Neon Dashboard SQL editor.)

---

## Чек-лист после деплоя

- [ ] `docker compose ps` — все три сервиса (`bot`, `migrations` exited с 0, `postgres` отсутствует / в profile `never`).
- [ ] Бот отвечает на `/start` в Telegram.
- [ ] `/dau_stats` доступна супер-админу.
- [ ] `/balance_reload` срабатывает и пишет audit-запись.
- [ ] 24 часа без рестарта (`docker logs` не показывает Exception).
- [ ] `audit_log` пишется (есть записи `PLAYER_REGISTERED`, `FOREST_RUN_STARTED`, `FOREST_RUN_FINISHED`).

После прохождения чек-листа — MVP считается задеплоенным. Открываем альфа-тест по приглашениям.

---

## Деплой admin web panel (Sprint 4.5-H)

> Веб-админка (`pipirik-admin-web`) деплоится **отдельно** от бота.
> Она привязывается к `127.0.0.1` (или internal-only сети) и доступна
> только через SSH-tunnel, VPN или reverse-proxy с IP-allowlist.

### Вариант 1: SSH-tunnel (минимальный, рекомендуется для ≤ 3 админов)

```bash
# На VPS — запуск как systemd-сервис (описание ниже).
# На рабочей машине — SSH-туннель:
ssh -L 8080:127.0.0.1:8080 user@vps-host
# Админка доступна в браузере по http://localhost:8080
```

### Вариант 2: VPN (WireGuard / OpenVPN)

Бот и админка находятся в одной VPN-сети. `ADMIN_WEB_ALLOWED_IPS`
настраивается на CIDR диапазон VPN (например `10.8.0.0/24` для
WireGuard). Пример `.env`:

```env
ADMIN_WEB_HOST=0.0.0.0
ADMIN_WEB_ALLOWED_IPS=10.8.0.0/24
ADMIN_WEB_TRUST_PROXY=false
```

### Вариант 3: Reverse-proxy (nginx) с отдельным поддоменом

```nginx
server {
    listen 443 ssl;
    server_name admin.pipirik.example.com;

    ssl_certificate     /etc/letsencrypt/live/admin.pipirik.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/admin.pipirik.example.com/privkey.pem;

    # Allow only VPN / office IPs
    allow 10.8.0.0/24;   # WireGuard VPN
    allow 203.0.113.0/24; # Office
    deny all;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Если используется reverse-proxy, включите:
```env
ADMIN_WEB_TRUST_PROXY=true
ADMIN_WEB_TRUSTED_PROXY_CIDRS=127.0.0.1/32
ADMIN_WEB_SUBDOMAIN=admin.pipirik.example.com
ADMIN_WEB_CORS_ALLOWED_ORIGINS=https://admin.pipirik.example.com
```

### docker-compose (admin-web)

```yaml
# ops/docker/docker-compose.admin.yml
# Запуск: docker compose -f ops/docker/docker-compose.admin.yml up -d
services:
  admin-web:
    build:
      context: ../..
      dockerfile: ops/docker/Dockerfile
    image: pipirik-wars:dev
    container_name: pipirik-admin-web
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-pipirik}:${POSTGRES_PASSWORD:-pipirik_dev_password}@postgres:5432/${POSTGRES_DB:-pipirik}
      ADMIN_WEB_SECRET_KEY: ${ADMIN_WEB_SECRET_KEY:?must be set}
      ADMIN_WEB_BOT_USERNAME: ${ADMIN_WEB_BOT_USERNAME:?must be set}
      ADMIN_WEB_BOT_TOKEN: ${BOT_TOKEN:?must be set}
      ADMIN_WEB_DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-pipirik}:${POSTGRES_PASSWORD:-pipirik_dev_password}@postgres:5432/${POSTGRES_DB:-pipirik}
      ADMIN_WEB_ALLOWED_IPS: ${ADMIN_WEB_ALLOWED_IPS:-127.0.0.0/8}
      ADMIN_WEB_TRUST_PROXY: ${ADMIN_WEB_TRUST_PROXY:-false}
      ADMIN_WEB_HOST: "0.0.0.0"
      ADMIN_WEB_PORT: "8080"
    ports:
      - "127.0.0.1:8080:8080"  # bind to localhost only!
    entrypoint: ["tini", "--"]
    command: ["pipirik-admin-web"]
    restart: unless-stopped
```

### systemd unit (без Docker)

```ini
# /etc/systemd/system/pipirik-admin-web.service
[Unit]
Description=Pipirik Wars Admin Web Panel
After=network.target postgresql.service

[Service]
Type=simple
User=pipirik
WorkingDirectory=/opt/pipirik-wars
EnvironmentFile=/opt/pipirik-wars/.env.admin
ExecStart=/opt/pipirik-wars/.venv/bin/pipirik-admin-web
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Переменные окружения (`.env.admin`)

| Переменная | Описание | По умолчанию |
|---|---|---|
| `ADMIN_WEB_SECRET_KEY` | Ключ signed-cookie (≥32 символов) | **обязательно** |
| `ADMIN_WEB_BOT_USERNAME` | Username бота для Telegram Login Widget | **обязательно** |
| `ADMIN_WEB_BOT_TOKEN` | Токен бота для HMAC-верификации | **обязательно** |
| `ADMIN_WEB_DATABASE_URL` | Async SQLAlchemy URL | `postgresql+asyncpg://...` |
| `ADMIN_WEB_HOST` | Bind address | `127.0.0.1` |
| `ADMIN_WEB_PORT` | Bind port | `8080` |
| `ADMIN_WEB_ALLOWED_IPS` | CIDR allowlist (CSV); `*` = allow-all; пустой = deny-all | `""` (deny-all) |
| `ADMIN_WEB_TRUST_PROXY` | Доверять X-Forwarded-For | `false` |
| `ADMIN_WEB_TRUSTED_PROXY_CIDRS` | CIDR trusted-прокси для XFF-chain | `""` |
| `ADMIN_WEB_RATE_LIMIT_MAX_REQUESTS` | Лимит auth-запросов/окно/IP | `10` |
| `ADMIN_WEB_RATE_LIMIT_WINDOW_SECONDS` | Окно rate-limit (сек) | `60` |
| `ADMIN_WEB_SUBDOMAIN` | Поддомен для деплоя | `admin.pipirik.example.com` |
| `ADMIN_WEB_CORS_ALLOWED_ORIGINS` | CORS origins (CSV) | `""` (same-origin) |

### Чек-лист после деплоя admin-web

- [ ] `curl -s http://127.0.0.1:8080/healthz` — 200 OK.
- [ ] С разрешённого IP — логин-страница отдаётся (200).
- [ ] С неразрешённого IP — 403 Forbidden.
- [ ] Rate-limiting: 11+ POST на `/auth/telegram/callback` за минуту — 429.
- [ ] SSH-tunnel: `ssh -L 8080:127.0.0.1:8080 user@vps` → браузер → `http://localhost:8080`.
- [ ] TOTP-авторизация работает через браузер.
- [ ] audit_log содержит записи с `source='web'`.
