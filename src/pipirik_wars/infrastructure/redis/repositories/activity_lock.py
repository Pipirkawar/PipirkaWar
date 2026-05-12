"""Redis-имплементация `IActivityLockRepository` (Спринт 4.1-G, шаг G.3).

Семантика:

* ``try_acquire`` — атомарный native-Redis `SET key value NX PX ttl_ms`
  (NX = только если ключ не существует, PX = TTL в миллисекундах).
  Возвращает `True` если ключ создан; `False` если у этого актора уже
  есть активная (НЕ-истёкшая) блокировка.
* ``release`` — `DEL key`. NO-OP если ключа нет.
* ``get`` — `GET` + `PTTL` в одном MULTI/EXEC-pipeline (atomic). Если
  ключа нет (или истёк) — возвращает `None`. Иначе восстанавливает
  `ActivityLock`-VO из JSON-payload-а + `expires_at = clock.now() + PTTL`.

Key-format: ``lock:{actor_kind}:{actor_id}``. Префикс ``lock`` —
namespace для будущей миграции лобби (4.1-H) и DAU (4.1-I), чтобы
ключи разных репозиториев не пересекались в shared-Redis-инстансе.

Value-format: JSON ``{"reason": "<LockReason.value>", "acquired_at":
"<ISO-8601 datetime>"}``. JSON выбран вместо MessagePack/BSON для
human-readability в `redis-cli` (operational debug) — payload крохотный
(<100 байт), парсинг не bottleneck.

Atomicity: ``SET NX PX`` гарантирует, что ровно один из конкурентных
вызовов получит `True` (Redis single-threaded для команд). Race-
condition между двумя ``try_acquire`` на один key невозможен.

`get` использует MULTI/EXEC-pipeline (`pipeline(transaction=True)`),
чтобы избежать TOCTOU между ``GET`` и ``PTTL``: оба читают одно и то
же состояние key-а в Redis-а. Если key expired между двумя командами
(`pipe.get` вернёт bytes, `pipe.pttl` вернёт `-2`) — repository
интерпретирует как "lock уже expired", возвращает `None`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from redis.asyncio import Redis

from pipirik_wars.domain.security import (
    ActivityLock,
    IActivityLockRepository,
    LockReason,
)
from pipirik_wars.domain.shared.ports.clock import IClock

__all__ = ["RedisActivityLockRepository"]

_KEY_PREFIX_DEFAULT = "lock"


class RedisActivityLockRepository(IActivityLockRepository):
    """Redis-имплементация `IActivityLockRepository` (Спринт 4.1-G, G.3)."""

    __slots__ = ("_client", "_clock", "_key_prefix")

    def __init__(
        self,
        *,
        client: Redis,
        clock: IClock,
        key_prefix: str = _KEY_PREFIX_DEFAULT,
    ) -> None:
        self._client = client
        self._clock = clock
        self._key_prefix = key_prefix

    def _key(self, actor_kind: str, actor_id: int) -> str:
        return f"{self._key_prefix}:{actor_kind}:{actor_id}"

    async def try_acquire(
        self,
        *,
        actor_kind: str,
        actor_id: int,
        reason: LockReason,
        now: datetime,
        expires_at: datetime,
    ) -> bool:
        """`SET key value NX PX ttl_ms` — атомарно создать lock.

        Возвращает `True` если ключ создан; `False` если у актора уже
        активный lock (NX-conflict).

        Если ``expires_at <= now`` (некорректный TTL), возвращает
        `False` без обращения к Redis — fail-safe (Redis не принимает
        ``PX 0`` или отрицательные значения).
        """
        ttl_ms = int((expires_at - now).total_seconds() * 1000)
        if ttl_ms <= 0:
            return False
        key = self._key(actor_kind, actor_id)
        payload = json.dumps(
            {
                "reason": reason.value,
                "acquired_at": now.isoformat(),
            },
            separators=(",", ":"),
        )
        # redis-py возвращает True если ключ создан (NX-success), None
        # если ключ уже существовал (NX-conflict). Bool-cast: True → True,
        # None → False.
        result = await self._client.set(key, payload, nx=True, px=ttl_ms)
        return result is True

    async def release(self, *, actor_kind: str, actor_id: int) -> None:
        """`DEL key`. NO-OP если ключа нет (Redis возвращает 0)."""
        await self._client.delete(self._key(actor_kind, actor_id))

    async def get(
        self,
        *,
        actor_kind: str,
        actor_id: int,
    ) -> ActivityLock | None:
        """Прочитать текущую блокировку.

        Atomic `GET` + `PTTL` в одном MULTI/EXEC-pipeline:

        * Если key не существует (`GET` → `None`) — возвращает `None`.
        * Если key уже expired между `GET` и `PTTL` (`PTTL` → `-2`) —
          возвращает `None` (race-condition).
        * Если key не имеет TTL (`PTTL` → `-1`) — возвращает `None`
          (наш ``try_acquire`` всегда выставляет PX, такого быть не
          должно; но защита от внешних SET-ов того же ключа).
        * Иначе восстанавливает `ActivityLock` из JSON-payload-а;
          ``expires_at = clock.now() + PTTL``.
        """
        key = self._key(actor_kind, actor_id)
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.get(key)
            pipe.pttl(key)
            results = await pipe.execute()
        raw_value, pttl_ms = results
        if raw_value is None:
            return None
        if not isinstance(pttl_ms, int) or pttl_ms < 0:
            return None
        data = json.loads(raw_value)
        reason = LockReason(data["reason"])
        acquired_at = datetime.fromisoformat(data["acquired_at"])
        expires_at = self._clock.now() + timedelta(milliseconds=pttl_ms)
        return ActivityLock(
            actor_kind=actor_kind,
            actor_id=actor_id,
            reason=reason,
            acquired_at=acquired_at,
            expires_at=expires_at,
        )
