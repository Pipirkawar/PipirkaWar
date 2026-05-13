# AGENT_HANDOFF — Спринт 4.1-J «Load-test 10× от MVP + Prometheus-метрики Redis-операций»

> **Sticky-документ.** Создаётся в первом коммите PR-а и обновляется в каждом
> последующем (без отдельного chore-коммита). Удаляется ровно одним
> финальным коммитом перед `git_pr(action="create")` — никогда раньше.
> Протокол см. `CONTRIBUTING.md` секция «Протокол передачи работы между агентами».

## Контекст

* **Сессия:** https://app.devin.ai/sessions/6c5ba011a4b7439ea5b274f397440c59
* **База:** `main = 21bde6e` (merge PR #137 — Спринт 4.1-I «Redis DAU-миграция»).
* **Ветка:** `devin/1778653875-sprint-4-1-J-redis-loadtest-metrics`.
* **Скоуп:** добавить Prometheus-метрики на все логические Redis-операции
  (`RedisActivityLockRepository` / `RedisGlobalLobbyRepository` /
  `RedisDauCounter`) + HTTP `/metrics` endpoint + load-test harness
  на FakeRedis (2000 ops/test, sanity-сценарий; параметризован env
  `LOAD_OPS_COUNT` для production-staging). **Четвёртый и финальный
  PR задачи 4.1.12 «Переход на Redis».**

## Шаги PR-а (J.0–J.7)

* [x] **J.0** — Snapshot pivot + sticky `AGENT_HANDOFF.md`. `make ci` baseline
  на `main = 21bde6e` зелён: **6969 passed + 2 skipped + 95.51 % cov,
  708.57 s**. На момент J.0 в проекте **нет** модуля
  `infrastructure/observability/` / `infrastructure/metrics/`, **нет**
  зависимостей `prometheus_client`/`aioprometheus` — observability-инфра
  4.1-J разворачивается с нуля. Решения J.0: библиотека —
  `prometheus_client>=0.20,<1` (sync API, async-friendly, де-факто
  стандарт), модуль — `infrastructure/observability/`, гранулярность
  метрик — **logical-op-level** (`backend=dau, op=record_active`),
  load-test backend — FakeRedis, scale — 2000 ops/test ~30 s.

* [ ] **J.1** — `prometheus_client>=0.20,<1` в runtime-deps; модуль
  `src/pipirik_wars/infrastructure/observability/redis_metrics.py` с
  классом `RedisMetrics(registry: CollectorRegistry | None = None)`:
  counter `pipirik_redis_op_total{backend,op,outcome}` + histogram
  `pipirik_redis_op_duration_seconds{backend,op}` (buckets
  `[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]`);
  async-context-manager `track(backend, op)` измеряет
  `time.perf_counter()`-elapsed и инкрементирует метрики в finally
  (outcome=`error` при любом исключении, then re-raise). Все три
  Redis-репозитория обёрнуты через `async with self._metrics.track(...)`.
  Tests: counter on success/error / histogram bucket precision / no-op
  при `metrics=None` / isolated `CollectorRegistry`-fixture (избежать
  Duplicated timeseries при повторной инстанциации).

* [ ] **J.2** — `src/pipirik_wars/infrastructure/observability/http.py`:
  `build_metrics_app(registry) -> aiohttp.web.Application` с одним
  GET-route `/metrics` (Content-Type `text/plain; version=0.0.4;
  charset=utf-8`); на отдельном порту `BOT_METRICS_PORT` (default
  `9100`). Регистрация в composition-root под `needs_redis`. Тесты:
  200 OK + Content-Type + payload содержит имена метрик / 404 на
  других путях.

* [ ] **J.3** — `tests/load/` с `pytest.mark.load` (исключён из default
  `make ci` через `addopts = "-m 'not load'"`); `make load-test`. Три
  файла: `test_dau_load.py` / `test_lobby_load.py` /
  `test_activity_lock_load.py` — каждый 2000-ops-сценарий через
  `asyncio.gather` на FakeRedis с p99-метриками (`time.perf_counter()`)
  и assert p99 < 50ms. Параметризация через env `LOAD_OPS_COUNT`.

* [ ] **J.4** — Profile-анализ узких мест **если** на J.3 p99 не уложился
  в таргет; иначе пропустить.

* [ ] **J.5** — `make ci` локально зелён + `make load-test` локально
  зелён.

* [ ] **J.6** — Doc-sync: `docs/history.md` запись 4.1-J + `docs/current_tasks.md`
  снимок под `main = <future-merge-sha 4.1-J>` + предварительный
  чек-лист 4.1-K (i18n PT/ES/TR/ID/FA/UK + ИИ-предсказания опц. +
  Grafana-дашборд).

* [ ] **J.7** — Удалить этот `AGENT_HANDOFF.md` отдельным коммитом +
  `git_pr(action="fetch_template")` → `git_pr(action="create")` +
  `git(action="pr_checks", wait_mode="all")` → дождаться зелёного
  GitHub-CI.

## Forbidden actions

* Не удалять `InMemoryDauCounter` / `SqlAlchemyActivityLockRepository` /
  `SqlAlchemyGlobalLobbyRepository` — default-backends остаются для
  backward-compat.
* Не пересобирать ГДД / `docs/plan.md` — скоуп явно не включает.
* Не делать force-push на main; не пропускать pre-commit hooks; не
  amend-ить созданные коммиты.

## Контрольные точки

* В каждом коммите обновить раздел «📌 Последний коммит на ветке»
  в `docs/current_tasks.md` (см. ритуалы документации).
* Перед PR — `make ci` локально должен дать **6969+ passed +
  2 skipped + ≥95.51 % cov** (load-тесты исключены через mark).
* После открытия PR — `git(action="pr_checks", wait_mode="all")`,
  дождаться зелёного GitHub-CI; если упало — `ci_job_logs(job_id=...)`
  и фикс.
