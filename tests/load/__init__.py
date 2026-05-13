"""Load-тесты Redis-репозиториев (Спринт 4.1-J, шаги J.3—J.5).

Все тесты в этом пакете помечены `pytest.mark.load` и **исключены**
из дефолтного `make ci` через `addopts = "-m 'not load'"` в
``pyproject.toml``. Запуск — `make load-test` (см. ``Makefile``).

Сценарии:

* ``test_dau_load.py``       — ``RedisDauCounter`` (``record_active`` +
  ``current``);
* ``test_lobby_load.py``     — ``RedisGlobalLobbyRepository`` (``enqueue``
  + ``pop_oldest`` + ``is_in_lobby``);
* ``test_activity_lock_load.py`` — ``RedisActivityLockRepository``
  (``try_acquire`` + ``release`` + ``get``).

Бэкенд — ``fakeredis.aioredis.FakeRedis`` (in-process Redis-эмулятор).
Это даёт high-fidelity-эмуляцию атомарных команд (включая Lua-скрипты
и MULTI/EXEC-pipeline-ы), не требуя живого Redis-инстанса в CI.

Параметризация (env-vars):

* ``LOAD_OPS_COUNT``       (default ``2000``) — сколько операций
  отправить в каждом сценарии. На CI оставляем 2000 (≈30 c); в
  staging-окружении можно поднять до 100_000+.

* ``LOAD_P99_BUDGET_MS``   (default ``50``) — верхняя граница p99-
  латенси одной операции (миллисекунды). При превышении тест падает
  с конкретным числом, что упрощает регрессионный triage.
"""
