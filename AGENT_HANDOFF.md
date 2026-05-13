# AGENT_HANDOFF — Спринт 4.1-L «Grafana-дашборд для Prometheus-метрик Redis-операций»

> **STICKY** — обновляется в коммите вместе с прогрессом по шагам L.0–L.6. Удаляется отдельным коммитом перед PR (см. L.6).

## Контекст передачи

- **Сессия:** https://app.devin.ai/sessions/dc53351a3caf438ea211fc897a110dc0
- **Ветка:** `devin/1778692137-sprint-4-1-L-grafana-dashboard`
- **База:** `main = 1b8f0be` (merge PR #139 «4.1-K i18n: расширение каталога локалей»)
- **PR #139 (4.1-K):** влит в main. CI зелёный (7055 passed + 2 skipped + 95.45% cov, 530.40 с).
- **Текущий шаг:** L.3 закрыт (monitoring/README.md + ссылка из root README) → L.4 (smoke-тесты dashboard JSON) следующий.
- **Baseline CI на `main = 1b8f0be`:** **7055 passed + 2 skipped + 95.45 % cov, 529.77 с** (Python 3.12.8 + pre-commit hooks, без warnings).

## Скоуп 4.1-L (часть задачи 4.1.15)

Закрывает часть задачи 4.1.15 из ПД §7 «Метрики и дашборд (Prometheus + Grafana)» — **визуализация уже инструментированных в 4.1-J Redis-метрик**:

- Counter `pipirik_redis_op_total{backend, op, outcome}` (outcome ∈ `ok`/`error`).
- Histogram `pipirik_redis_op_duration_seconds{backend, op}` (11 buckets от 1 мс до 5 с).
- 10 backend×op-серий: `dau` (record_active/current), `activity_lock` (try_acquire/release/get), `lobby` (enqueue/pop_oldest/remove/is_in_lobby).
- HTTP `/metrics` endpoint (aiohttp, порт `BOT_METRICS_PORT=9100`).

### Что НЕ входит

- Бизнес-метрики DAU / караваны / рейды / крипто-пул per currency — требуют **новых** инструментаций в `application/`-слое (не были сделаны в 4.1-J). Отложено до отдельного спринта после 4.1-M.
- AlertManager-конфигурация — production-инфра, за рамками.
- Live Grafana-инстанс — только локальный `docker-compose` для разработки/демо.

## Декомпозиция L.0 → L.6

- **L.0 — Snapshot pivot + sticky HANDOFF** (этот коммит): обновить `docs/current_tasks.md` под 4.1-L, создать `AGENT_HANDOFF.md`, baseline `make ci` зафиксирован.
- **L.1 — Grafana dashboard JSON**: `monitoring/grafana/dashboards/redis-metrics.json` — 4 ряда × 5-6 панелей.
  - Row 1 Overview: `stat`-панель «Redis RPS by backend» (`sum by (backend) (rate(pipirik_redis_op_total[1m]))`) + `stat` «Error rate %» (`100 * sum(rate(...{outcome="error"}[5m])) / sum(rate(...[5m]))`).
  - Row 2 Latency: `timeseries`-панель «p50/p95/p99 by backend» (3 query через `histogram_quantile(0.5/0.95/0.99, sum by (le, backend) (rate(..._bucket[5m])))`).
  - Row 3 Throughput: `timeseries`-панель «RPS by backend × op» (stacked, `sum by (backend, op) (rate(pipirik_redis_op_total[1m]))`).
  - Row 4 Errors: `timeseries`-панель «Error-rate by backend» + `table`-панель «Top error ops (5m)» (`topk(5, sum by (backend, op) (increase(...{outcome="error"}[5m])))`).
  - Datasource UID — placeholder `${DS_PROMETHEUS}` (auto-provisioning подставит при импорте).
- **L.2 — docker-compose stack**: `monitoring/docker-compose.yml` (`prom/prometheus:v2.55.0` + `grafana/grafana:11.4.0-oss`, порты 9090/3000) + `monitoring/prometheus/prometheus.yml` (job `pipirik-bot` с target `host.docker.internal:9100`) + `monitoring/grafana/provisioning/datasources/prometheus.yml` + `monitoring/grafana/provisioning/dashboards/dashboards.yml` (auto-load из `/var/lib/grafana/dashboards`).
- **L.3 — Документация**: `monitoring/README.md` (Quick start / Архитектура / Описание панелей / Метрик-референс / Recommended alert rules) + ссылка из корневого `README.md` (секция «Observability»).
- **L.4 — Smoke-тесты dashboard-JSON-валидности**: `tests/integration/monitoring/test_grafana_dashboard.py`. 6 тестов: (1) JSON парсится, (2) top-level поля (`schemaVersion`/`version`/`title`/`uid`/`panels`) присутствуют, (3) каждая panel имеет `targets[0].expr`, (4) referenced metrics существуют в `RedisMetrics`-источнике, (5) labels (`backend`/`op`/`outcome`) совпадают с `labelnames`-кортежем, (6) `backend`-значения в dashboard JSON совпадают с `_BACKEND`-константами в Redis-репозиториях.
- **L.5 — Doc-sync**: `docs/history.md` запись «Спринт 4.1-L» + `docs/current_tasks.md` чек-лист L.0–L.5 → `[x]`.
- **L.6 — PR + CI**: отдельный коммит `git rm AGENT_HANDOFF.md` + `make ci` локально зелёный + `git_pr(create)` + `git(pr_checks, wait_mode="all")`.

## Артефакты, на которые опираемся

- `src/pipirik_wars/infrastructure/observability/redis_metrics.py` — класс `RedisMetrics` с counter/histogram, async-CM `track(backend, op)`.
- `src/pipirik_wars/infrastructure/observability/http.py` — `build_metrics_app(registry)` → aiohttp `Application` с GET `/metrics`.
- `src/pipirik_wars/bot/main.py` — wire-up `RedisMetrics` в Redis-репозитории + TCPSite на порту 9100.
- `src/pipirik_wars/infrastructure/settings/settings.py` — `BotSettings.metrics_port` (env `BOT_METRICS_PORT`).
- 3 Redis-репозитория с `_BACKEND`-константами:
  - `infrastructure/redis/repositories/activity_lock.py` — `_BACKEND = "activity_lock"`.
  - `infrastructure/redis/repositories/lobby.py` — `_BACKEND = "lobby"`.
  - `infrastructure/redis/repositories/dau.py` — `_BACKEND = "dau"`.

## Решения по 4.1-L

1. **Подход к dashboard JSON.** Ручной JSON (не `grafanalib`-Python-DSL): дашборд один-на-всю-жизнь, Python-бутстрап неоправдан; `grafanalib` был бы лишней рантайм-зависимостью; ручной JSON проще в review для operator-а.
2. **Datasource UID.** Placeholder `${DS_PROMETHEUS}` (Grafana автоматически предложит выбрать datasource при импорте; в docker-compose-стеке auto-provisioning сам подставит).
3. **Панель-лейаут.** 4 ряда (overview / latency / throughput / errors), 24-grid Grafana, панели по ширине 8 или 12.
4. **Buckets/quantiles.** p50/p95/p99 через `histogram_quantile()`; rate-окна — 1 м для throughput, 5 м для quantile-ов и error-rate, 30 м для top error ops.
5. **Smoke-тесты.** В `tests/integration/monitoring/` (интеграционные, не unit, потому что читают файлы); каждый PromQL-expression из dashboard JSON-а сверяется с metric-именами в `redis_metrics.py` и лейблами `_BACKEND`/`_OP` в `infrastructure/redis/repositories/`.

## CONTRIBUTING.md / приёмка

- 7-шаговая приёмка пройдена в L.0: (1) HANDOFF не существует на main → этот файл создаётся в L.0, (2) `git fetch origin --prune` + `git branch -r` подтвердил свежий `origin/main = 1b8f0be`, (3) доки `CONTRIBUTING.md` / `current_tasks.md` / `history.md` / `development_plan.md` / `README.md` перечитаны, (4) baseline `make ci` 7055 passed + 2 skipped, (5) артефакты — нет (clean main), (6) `current_tasks.md` обновлён под L.0, (7) старт L.1.
- Pre-commit hooks (`.pre-commit-config.yaml`) активны: `trailing-whitespace`, `end-of-file-fixer`, `ruff` (lint + format), `mypy --strict`, `import-linter`. Никаких `--no-verify` коммитов.
- Каждый шаг L.X — отдельный коммит. AGENT_HANDOFF обновляется в том же коммите, что и код-изменения (sticky-режим до L.5).
- L.6 — отдельный коммит `git rm AGENT_HANDOFF.md` перед `git_pr(action="create")`.

## Команды, которые могут пригодиться

```bash
# Локальный CI
make ci

# Targeted-тесты (например, после L.4)
pytest tests/integration/monitoring/ -v

# Pre-commit hooks вручную
pre-commit run --all-files

# Просмотр Prometheus-метрик локально (если запущен бот)
curl http://localhost:9100/metrics | grep pipirik_redis_op_

# Проверить, что dashboard-JSON валиден (после L.1)
python -c "import json; json.loads(open('monitoring/grafana/dashboards/redis-metrics.json').read()); print('OK')"
```
