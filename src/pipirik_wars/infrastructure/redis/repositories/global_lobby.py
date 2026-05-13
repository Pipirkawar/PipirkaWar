"""Redis-имплементация `IGlobalLobbyRepository` (Спринт 4.1-H, шаг H.1).

Семантика (контракт идентичен `SqlAlchemyGlobalLobbyRepository`):

* ``enqueue(duel_id, enqueued_at)`` — атомарный Lua-скрипт:
  ``HEXISTS lobby:enqueued_at duel_id`` → если запись уже стоит, вернуть
  ``0`` (дублирующий enqueue безопасен и **сохраняет первоначальный
  `enqueued_at`** для FIFO-упорядочивания). Иначе
  ``HSET + LPUSH`` атомарно и вернуть ``1``.
* ``pop_oldest()`` — атомарный Lua-скрипт: ``RPOP lobby:queue`` (хвост
  LIST-а — самая старая запись, потому что enqueue делает ``LPUSH`` в
  голову); затем ``HGET + HDEL`` той же записи в HASH-е. Возвращает
  ``LobbyEntry(duel_id, enqueued_at)`` или ``None``.
* ``remove(duel_id)`` — атомарный Lua-скрипт: ``HDEL lobby:enqueued_at``;
  если 0 (записи не было) → вернуть ``0``; иначе
  ``LREM lobby:queue 0 duel_id`` → вернуть ``1``. NO-OP если записи нет.
* ``is_in_lobby(duel_id)`` — single ``HEXISTS`` (Lua не нужен, чистое
  чтение).

Data-model: ``LIST + HASH`` (а не ``LIST + SET``).

* ``{prefix}:queue`` — LIST, элементы — `duel_id`-строки (``LPUSH`` в
  head, ``RPOP`` с tail для FIFO).
* ``{prefix}:enqueued_at`` — HASH ``duel_id -> ISO-8601 datetime``;
  одновременно membership-источник (``HEXISTS``) и носитель значения
  ``enqueued_at`` (нужен для реконструкции ``LobbyEntry`` в
  ``pop_oldest``).

Почему HASH, а не SET (отход от исходного предложения чек-листа
`current_tasks.md` «LIST + SET»): SET даёт membership, но потерял бы
``enqueued_at`` per-duel. Вариант с composite-payload-ом LIST-а
(``duel_id|iso``) требует O(N)-скана ``LRANGE`` для ``remove(duel_id)``
(не знаем ``enqueued_at`` в API ``remove``-а — пришлось бы искать
запись с нужным префиксом и ``LREM`` её точное значение). Параллельный
HASH рядом с SET — лишний key, та же логика. Single HASH — чище:
``HEXISTS`` для membership, ``HGET`` для значения, ``HDEL`` для удаления
— всё O(1).

Atomicity: ``redis.call(...)`` внутри Lua-скрипта single-threaded;
Redis выполняет всю последовательность как одну атомарную команду.
Race-condition между двумя ``enqueue`` на тот же `duel_id` невозможен —
ровно один из них сделает ``HSET + LPUSH``, второй увидит
``HEXISTS == 1`` и вернёт ``0``.

Key-prefix: ``lobby`` (default через параметр конструктора). Не
пересекается с ``lock`` (4.1-G `RedisActivityLockRepository`) и
``dau`` (будущий 4.1-I) в shared-Redis-инстансе.
"""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import datetime
from typing import cast

from redis.asyncio import Redis
from redis.commands.core import AsyncScript

from pipirik_wars.domain.pvp.lobby import IGlobalLobbyRepository, LobbyEntry

__all__ = ["RedisGlobalLobbyRepository"]

_KEY_PREFIX_DEFAULT = "lobby"

# Lua: enqueue + dedup-check.
#   KEYS[1] = lobby:queue (LIST)
#   KEYS[2] = lobby:enqueued_at (HASH)
#   ARGV[1] = duel_id-строка
#   ARGV[2] = enqueued_at ISO-8601
# Returns 1 если запись добавлена; 0 если уже существовала.
_ENQUEUE_LUA = """
if redis.call('HEXISTS', KEYS[2], ARGV[1]) == 1 then
  return 0
end
redis.call('HSET', KEYS[2], ARGV[1], ARGV[2])
redis.call('LPUSH', KEYS[1], ARGV[1])
return 1
"""

# Lua: pop oldest (tail of LIST).
#   KEYS[1] = lobby:queue, KEYS[2] = lobby:enqueued_at
# Returns {duel_id, iso} двухэлементный список, либо nil если очередь
# пустая.
_POP_OLDEST_LUA = """
local duel_id = redis.call('RPOP', KEYS[1])
if not duel_id then
  return nil
end
local iso = redis.call('HGET', KEYS[2], duel_id)
redis.call('HDEL', KEYS[2], duel_id)
return {duel_id, iso}
"""

# Lua: remove by duel_id.
#   KEYS[1] = lobby:queue, KEYS[2] = lobby:enqueued_at
#   ARGV[1] = duel_id-строка
# Returns 1 если удалена; 0 если её не было.
_REMOVE_LUA = """
if redis.call('HDEL', KEYS[2], ARGV[1]) == 0 then
  return 0
end
redis.call('LREM', KEYS[1], 0, ARGV[1])
return 1
"""


def _decode(value: bytes | str) -> str:
    """Привести значение Redis-а к ``str``.

    `redis-py` по умолчанию отдаёт значения как ``bytes``; в Lua-результате
    тоже приходят bytes. Декодируем явно как UTF-8 — все наши payload-ы
    ASCII (id + ISO-8601), безопасно.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


class RedisGlobalLobbyRepository(IGlobalLobbyRepository):
    """Redis-имплементация FIFO-лобби PvP (Спринт 4.1-H, H.1).

    Контракт идентичен `SqlAlchemyGlobalLobbyRepository`: dedup по
    ``duel_id`` (повторный ``enqueue`` сохраняет оригинальный
    ``enqueued_at``); FIFO по моменту первого ``enqueue``.

    Все мутирующие операции — атомарные Lua-скрипты. Использует
    ``client.register_script(...)`` (precomputed SHA1 + ``EVALSHA``);
    при первом запуске на свежем Redis-инстансе ``AsyncScript``
    автоматически делает ``SCRIPT LOAD`` через fallback (`NoScriptError`
    → `script_load` → retry).
    """

    __slots__ = (
        "_client",
        "_enqueue_script",
        "_hash_key",
        "_list_key",
        "_pop_oldest_script",
        "_remove_script",
    )

    def __init__(self, *, client: Redis, key_prefix: str = _KEY_PREFIX_DEFAULT) -> None:
        self._client = client
        self._list_key = f"{key_prefix}:queue"
        self._hash_key = f"{key_prefix}:enqueued_at"
        self._enqueue_script: AsyncScript = client.register_script(_ENQUEUE_LUA)
        self._pop_oldest_script: AsyncScript = client.register_script(_POP_OLDEST_LUA)
        self._remove_script: AsyncScript = client.register_script(_REMOVE_LUA)

    async def enqueue(self, *, duel_id: int, enqueued_at: datetime) -> bool:
        """Поставить дуэль в очередь.

        Атомарный Lua-скрипт ``HEXISTS → HSET + LPUSH``. Повторный
        ``enqueue`` сохраняет первоначальный ``enqueued_at`` (НЕ
        перезаписывает HASH-поле и НЕ двигает позицию в LIST-е) — это
        контрактное поведение для FIFO-идемпотентности.

        Возвращает ``True`` если запись реально добавлена; ``False``
        если такая ``duel_id`` уже стоит в очереди.
        """
        raw = await self._enqueue_script(
            keys=[self._list_key, self._hash_key],
            args=[str(duel_id), enqueued_at.isoformat()],
        )
        return int(cast(int, raw)) == 1

    async def pop_oldest(self) -> LobbyEntry | None:
        """Атомарно извлечь самую старую запись из очереди.

        Атомарный Lua-скрипт ``RPOP + HGET + HDEL`` (single-threaded
        execution гарантирует, что два конкурентных воркера не
        «выхватят» одну и ту же запись). Возвращает ``None`` если
        очередь пустая.
        """
        raw = await self._pop_oldest_script(
            keys=[self._list_key, self._hash_key],
        )
        if raw is None:
            return None
        pair = cast(list[bytes | str], raw)
        duel_id_str = _decode(pair[0])
        iso = _decode(pair[1])
        return LobbyEntry(duel_id=int(duel_id_str), enqueued_at=datetime.fromisoformat(iso))

    async def remove(self, *, duel_id: int) -> bool:
        """Удалить запись по `duel_id`.

        Атомарный Lua-скрипт ``HDEL → (если был) LREM``. Возвращает
        ``True`` если запись была удалена; ``False`` если её не было
        (NO-OP).
        """
        raw = await self._remove_script(
            keys=[self._list_key, self._hash_key],
            args=[str(duel_id)],
        )
        return int(cast(int, raw)) == 1

    async def is_in_lobby(self, *, duel_id: int) -> bool:
        """Проверить, стоит ли указанная дуэль в очереди.

        Single ``HEXISTS`` — чистое чтение, Lua не нужен.
        """
        # `Redis.hexists` объявлен в redis-py как `Awaitable[bool] | bool`
        # (один и тот же сигнатурный шим используется sync- и async-клиентом);
        # на async-клиенте всегда возвращается `Awaitable[bool]`. Сужаем тип
        # через `cast`, чтобы mypy --strict видел корректный `await`.
        result = await cast(
            "Awaitable[bool]",
            self._client.hexists(self._hash_key, str(duel_id)),
        )
        return bool(result)
