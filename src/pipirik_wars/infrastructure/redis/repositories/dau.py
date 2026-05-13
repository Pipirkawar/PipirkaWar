"""Redis-имплементация `IDauCounter` (Спринт 4.1-I, шаг I.1).

Семантика (контракт идентичен `InMemoryDauCounter`):

* ``record_active(tg_user_id)`` — атомарный ``ZADD`` + ``EXPIRE`` через
  pipeline-транзакцию (`pipeline(transaction=True)`). Key — sorted-set
  ``dau:{YYYY-MM-DD}`` по текущему игровому дню (``Europe/Moscow``);
  member — строка ``str(tg_user_id)``; score — Unix-timestamp (seconds-
  since-epoch как ``float``). Повторный ``record_active`` того же
  ``tg_user_id`` в течение дня — идемпотентен: ``ZADD`` обновляет score
  (Redis не считает это новым элементом, ``ZCARD`` остаётся прежним).
  TTL ``172800`` секунд (48h) выставляется на каждый key через ``EXPIRE``
  при каждом ``record_active`` (Redis запретит ``EXPIRE`` на отсутствующий
  key, поэтому вызов после ``ZADD`` корректен). 48h-окно нужно для
  cross-midnight-чтений: после полуночи UTC ``current()`` для нового
  игрового дня вернёт 0, но «вчерашний» key ещё жив до +48h, что
  оставляет пространство для аналитики и cron-снапшотов.
* ``current()`` — ``ZCARD dau:{YYYY-MM-DD}`` по текущему игровому дню.
  Если key не существует (ещё ни одного ``record_active`` за сегодня
  или истёк TTL) — Redis возвращает ``0``.

«Сегодня» — игровой день по ``Europe/Moscow`` через ``IClock.now()``
(совпадает с ``oracle.cooldown_tz`` из `balance.yaml` и с поведением
``InMemoryDauCounter._moscow_today``). Lazy-reset на стороне Redis-key-а
происходит автоматически: каждый день генерирует новый key с новым
``{YYYY-MM-DD}``-суффиксом, старые keys уходят по TTL.

Key-format: ``{prefix}:{YYYY-MM-DD}`` (`prefix` через параметр
конструктора, default ``"dau"``). Namespace-н с ``lock`` 4.1-G и ``lobby``
4.1-H в shared-Redis-инстансе.

Atomicity: ``record_active`` использует MULTI/EXEC-pipeline
(`pipeline(transaction=True)`) — оба ``ZADD`` и ``EXPIRE`` выполняются
как одна атомарная команда, исключая ситуацию, когда между ``ZADD`` и
``EXPIRE`` параллельный воркер «увидит» key без TTL. ``ZCARD`` — single
read, atomicity не нужна.

Выбор ZSET (а не SET ``SADD``/``SCARD``): SET был бы достаточен для
текущего контракта (`record_active` + `current` без аналитики по
времени), но ZSET с ``score=timestamp`` даёт zero-cost-расширение в
сторону аналитики (``ZRANGEBYSCORE`` для «активные между T1 и T2») —
требование из `docs/current_tasks.md` плана 4.1-I. Storage-overhead
ZSET vs SET ≈ 30% на один element (skip-list-узел против hashtable-
bucket-а), что несущественно при MVP-масштабе DAU=200.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from datetime import date, timedelta, timezone
from typing import cast

from redis.asyncio import Redis

from pipirik_wars.domain.dau import IDauCounter
from pipirik_wars.domain.shared.ports.clock import IClock
from pipirik_wars.infrastructure.observability.redis_metrics import RedisMetrics

__all__ = ["RedisDauCounter"]

_KEY_PREFIX_DEFAULT = "dau"
_TTL_SECONDS = 172_800  # 48h — cross-midnight чтения «вчерашнего» key-а
_MOSCOW_TZ = timezone(timedelta(hours=3), name="Europe/Moscow")
_BACKEND = "dau"


class RedisDauCounter(IDauCounter):
    """Redis-имплементация `IDauCounter` (Спринт 4.1-I, I.1).

    Контракт идентичен `InMemoryDauCounter`: уникальные активные
    игроки за текущий ``Europe/Moscow``-день; повторный ``record_active``
    того же ``tg_user_id`` — идемпотентен (счётчик не растёт); сброс на
    границе дня (00:00 МСК) — через смену key-а (старые keys уходят
    по TTL 48h).
    """

    __slots__ = ("_client", "_clock", "_key_prefix", "_metrics")

    def __init__(
        self,
        *,
        client: Redis,
        clock: IClock,
        key_prefix: str = _KEY_PREFIX_DEFAULT,
        metrics: RedisMetrics | None = None,
    ) -> None:
        self._client = client
        self._clock = clock
        self._key_prefix = key_prefix
        self._metrics = metrics

    @asynccontextmanager
    async def _track(self, op: str) -> AsyncIterator[None]:
        """Обёртка для опциональной Prometheus-instrumentation.

        Если ``metrics is None`` (default-конфигурация без observability)
        — yield-им без инкрементов. Иначе делегируем в
        ``RedisMetrics.track(backend=_BACKEND, op=op)``.
        """
        if self._metrics is None:
            yield
            return
        async with self._metrics.track(backend=_BACKEND, op=op):
            yield

    def _moscow_today(self) -> date:
        """Текущий игровой день по ``Europe/Moscow``."""
        return self._clock.now().astimezone(_MOSCOW_TZ).date()

    def _key_for_day(self, day: date) -> str:
        return f"{self._key_prefix}:{day.isoformat()}"

    async def record_active(self, *, tg_user_id: int) -> None:
        """Зарегистрировать актора как активного сегодня. Идемпотентно.

        Атомарный MULTI/EXEC-pipeline ``ZADD + EXPIRE``: оба вызова
        выполняются как одна команда (single-threaded в Redis-е),
        исключая интервал «key создан, но без TTL» между ``ZADD`` и
        ``EXPIRE``. Повторный ``record_active`` того же ``tg_user_id``
        — `ZADD` обновляет score (``current()`` остаётся прежним).
        """
        async with self._track("record_active"):
            now = self._clock.now()
            key = self._key_for_day(now.astimezone(_MOSCOW_TZ).date())
            score = now.timestamp()
            member = str(tg_user_id)
            async with self._client.pipeline(transaction=True) as pipe:
                pipe.zadd(key, {member: score})
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()

    async def current(self) -> int:
        """Сколько уникальных активных игроков за сегодня.

        Single ``ZCARD`` по key-у текущего дня. Если key не существует
        (никто ещё не пришёл / TTL истёк) — Redis возвращает ``0``.
        """
        async with self._track("current"):
            key = self._key_for_day(self._moscow_today())
            # `redis-py` объявляет `Redis.zcard` как `Awaitable[int] | int`
            # (один и тот же шим для sync- и async-клиента); на async всегда
            # `Awaitable[int]`. Сужаем тип через `cast`, чтобы mypy --strict
            # видел корректный `await`.
            raw = await cast("Awaitable[int]", self._client.zcard(key))
            return int(raw)
