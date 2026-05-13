# Pipirik Wars — Observability stack

Локальный стек **Prometheus + Grafana** для разработки и демо. Визуализирует Prometheus-метрики Redis-операций, инструментированные в Спринте 4.1-J (`pipirik_redis_op_total` + `pipirik_redis_op_duration_seconds`).

> **Scope.** Это **локальный** observability-стек: для отладки, демонстраций, отладки SLO-формул. Production-deployment (AlertManager, long-term storage Thanos / Cortex, TLS, OAuth/SSO) — отдельная инфраструктурная задача за рамками 4.1-L.

---

## 🚀 Quick start

Запустить стек (Prometheus + Grafana):

```bash
docker compose -f monitoring/docker-compose.yml up -d
```

Открыть Grafana:

- URL: <http://localhost:3000>
- Login: `admin`
- Password: `admin`

Дашборд **«Pipirik Redis Operations»** автопровиженится в папку «Pipirik Wars» — открой его из главного меню → Dashboards.

Prometheus UI: <http://localhost:9090>. Полезные query:

- `up{job="pipirik-bot"}` — `1` если бот доступен на `host.docker.internal:9100`.
- `sum(rate(pipirik_redis_op_total[1m]))` — глобальный RPS Redis-операций.

Остановить стек:

```bash
docker compose -f monitoring/docker-compose.yml down
```

Полный сброс (включая Grafana-БД с настройками и Prometheus TSDB):

```bash
docker compose -f monitoring/docker-compose.yml down -v
```

---

## 🏗 Архитектура

```
┌────────────┐    /metrics       ┌──────────────┐   query   ┌──────────────┐
│ pipirik-bot│ ────────────────▶ │  Prometheus  │ ◀──────── │   Grafana    │
│  :9100     │   (scrape 15s)    │   :9090      │           │    :3000     │
└────────────┘                   └──────────────┘           └──────────────┘
   (host)                           (docker)                   (docker)
```

- **`pipirik-bot`** — основной aiogram-бот. Запущен на хосте (не в docker-сети). Через aiohttp-сервер `infrastructure/observability/http.py` экспортирует Prometheus-метрики по адресу `:9100/metrics`. Порт настраивается env-var `BOT_METRICS_PORT`.
- **`prometheus`** — собирает метрики с бота каждые 15с. Target: `host.docker.internal:9100` (на macOS/Windows резолвится автоматически; на Linux — благодаря `extra_hosts` в `docker-compose.yml`).
- **`grafana`** — визуализирует метрики. Datasource `Prometheus` (UID `prometheus`) и дашборд `redis-metrics.json` автопровиженятся из `grafana/provisioning/`.

---

## 📁 Структура каталога

```
monitoring/
├── README.md                                 # этот файл
├── docker-compose.yml                        # сервисы prometheus + grafana
├── prometheus/
│   └── prometheus.yml                        # scrape-конфиг
└── grafana/
    ├── dashboards/
    │   └── redis-metrics.json                # сам дашборд (JSON)
    └── provisioning/
        ├── datasources/
        │   └── prometheus.yml                # auto-provision datasource
        └── dashboards/
            └── dashboards.yml                # auto-provision dashboards-provider
```

---

## 📊 Описание панелей дашборда

Дашборд **«Pipirik Redis Operations»** (`redis-metrics.json`) разбит на 4 ряда.

### Row 1 — Overview

- **Redis RPS by backend** (`stat`). Суммарный rate Redis-операций на secondbackend, окно 1 мин. PromQL:
  ```promql
  sum by (backend) (rate(pipirik_redis_op_total{backend=~"$backend"}[1m]))
  ```
  Пороги: 0 → зелёный, 100 → жёлтый, 1000 → красный.

- **Error rate % (5m)** (`stat`). Доля операций с `outcome=error` от всех операций (по всем backend-ам), окно 5 мин. PromQL:
  ```promql
  100 * (sum(rate(pipirik_redis_op_total{outcome="error"}[5m]))
       / clamp_min(sum(rate(pipirik_redis_op_total[5m])), 0.001))
  ```
  Пороги: 0 → зелёный, 0.5 % → жёлтый, 1 % → красный.

### Row 2 — Latency

- **Latency p50/p95/p99 by backend** (`timeseries`). Квантили задержки на каждый backend, окно 5 мин, через `histogram_quantile()` поверх `_bucket`-метрики. Пример формулы (p95):
  ```promql
  histogram_quantile(
    0.95,
    sum by (le, backend) (rate(pipirik_redis_op_duration_seconds_bucket[5m]))
  )
  ```
  Три query (p50/p95/p99) × до 3 backend-ов = до 9 серий. Легенда в виде таблицы внизу с агрегатами mean/last/max.

- **Latency distribution heatmap** (`heatmap`). Тепловая карта распределения задержки по всем backend×op-парам (окно 5 мин). По вертикали — `le`-bucket границы (`s`), по горизонтали — время; яркость ячеек пропорциональна количеству операций. Помогает увидеть multi-modal-распределения (например, lobby-операции бимодальны: быстрые `is_in_lobby` + медленные `pop_oldest` с BRPOPLPUSH-block).

### Row 3 — Throughput

- **RPS by backend × op (stacked)** (`timeseries`). RPS по каждой паре `(backend, op)` стек-плотом, окно 1 мин. PromQL:
  ```promql
  sum by (backend, op) (rate(pipirik_redis_op_total{backend=~"$backend"}[1m]))
  ```
  Все 10 серий: `dau` × {`record_active`, `current`}, `activity_lock` × {`try_acquire`, `release`, `get`}, `lobby` × {`enqueue`, `pop_oldest`, `remove`, `is_in_lobby`}. Легенда справа.

### Row 4 — Errors

- **Error rate % by backend (5m)** (`timeseries`). Доля ошибок на backend во времени с порогами 0.5 % / 1 %. PromQL:
  ```promql
  100 * (sum by (backend) (rate(pipirik_redis_op_total{outcome="error"}[5m]))
       / clamp_min(sum by (backend) (rate(pipirik_redis_op_total[5m])), 0.001))
  ```

- **Top error ops (last 5m)** (`table`). Топ-5 backend×op-пар по абсолютному числу ошибок за последние 5 мин. Используй для триажа: какая конкретно операция ломается. PromQL (`instant`-query):
  ```promql
  topk(5, sum by (backend, op) (increase(pipirik_redis_op_total{outcome="error"}[5m])))
  ```

---

## 📐 Метрик-референс

Метрики инструментированы классом `RedisMetrics` (`src/pipirik_wars/infrastructure/observability/redis_metrics.py`). Полная семантика — в docstring-ах.

| Метрика | Тип | Labels | Описание |
|---------|-----|--------|----------|
| `pipirik_redis_op_total` | counter | `backend`, `op`, `outcome` | Счётчик завершённых Redis-операций. |
| `pipirik_redis_op_duration_seconds` | histogram | `backend`, `op` | Histogram длительности операций (секунды). |

Buckets histogram-а: `0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0` (от 1 мс до 5 с). Plus автоматический `+Inf` для overflow.

### Допустимые значения labels

- **`backend`** ∈ `"activity_lock"`, `"lobby"`, `"dau"`.
- **`outcome`** ∈ `"ok"`, `"error"`.
- **`op`** — зависит от `backend`:
  - `backend="activity_lock"`: `try_acquire`, `release`, `get`.
  - `backend="lobby"`: `enqueue`, `pop_oldest`, `remove`, `is_in_lobby`.
  - `backend="dau"`: `record_active`, `current`.

Итого 10 backend×op-пар.

---

## 🚨 Recommended alert rules

Production-AlertManager-конфигурация за рамками 4.1-L, но эти базовые алерты стоит подключить в первую очередь:

### High error rate

```promql
100 * (sum(rate(pipirik_redis_op_total{outcome="error"}[5m]))
     / clamp_min(sum(rate(pipirik_redis_op_total[5m])), 0.001)) > 1
```

> Триггерится, когда доля ошибок > 1 % за 5 минут. Critical: > 5 %.

### High latency p99

```promql
histogram_quantile(
  0.99,
  sum by (le, backend) (rate(pipirik_redis_op_duration_seconds_bucket[5m]))
) > 0.5
```

> Триггерится, когда p99 задержка Redis-операций > 500 мс на каком-либо backend-е. Critical: > 2 с.

### Bot unreachable (scrape down)

```promql
up{job="pipirik-bot"} == 0
```

> Триггерится, когда Prometheus не может скрейпнуть `/metrics` бота. После 5 минут — critical.

### Sudden RPS drop

```promql
sum(rate(pipirik_redis_op_total[5m]))
  < 0.5 * sum(rate(pipirik_redis_op_total[1h] offset 1h))
```

> Триггерится, если текущий RPS упал более чем вдвое относительно среднего за прошлый час. Полезно для детекта silent failure-ов (бот живёт, но события не приходят).

---

## 🛠 Траблшутинг

### Grafana показывает пустой дашборд

1. Проверь, что бот живёт: `curl http://localhost:9100/metrics | head -5` — должно вернуть `# HELP pipirik_redis_op_total ...`.
2. Проверь, что Prometheus видит target: в Prometheus UI открой **Status → Targets** → должен быть `pipirik-bot` в состоянии `UP`.
3. На Linux: если `host.docker.internal` не резолвится, проверь, что в `docker-compose.yml` присутствует `extra_hosts: host.docker.internal:host-gateway` для prometheus-сервиса.

### Datasource в дашборде показывает «not found»

Дашборд использует placeholder `${DS_PROMETHEUS}` в templating-секции. Если grafana auto-provisioning не подхватил datasource, открой дашборд → шестерёнка → **Variables** → `DS_PROMETHEUS` → выбери `Prometheus`. Затем **Save**.

### Бот не экспортирует метрики

Проверь:

- `BOT_METRICS_PORT` env-var (default `9100`) — порт `/metrics`-эндпоинта.
- В логах бота должна быть строка `INFO Starting metrics endpoint on port 9100`.
- Файрвол на хосте не блокирует `9100`.

---

## 📚 Связанные документы

- [`src/pipirik_wars/infrastructure/observability/redis_metrics.py`](../src/pipirik_wars/infrastructure/observability/redis_metrics.py) — источник истины по метрикам.
- [`src/pipirik_wars/infrastructure/observability/http.py`](../src/pipirik_wars/infrastructure/observability/http.py) — aiohttp `/metrics`-эндпоинт.
- [`docs/history.md`](../docs/history.md) — изменения по спринтам (см. записи 4.1-J и 4.1-L).
- [`docs/development_plan.md`](../docs/development_plan.md) §7 — задача 4.1.15 «Метрики и дашборд».
- [Prometheus documentation](https://prometheus.io/docs/).
- [Grafana documentation](https://grafana.com/docs/).
