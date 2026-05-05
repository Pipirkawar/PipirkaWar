"""Глобальное FIFO-лобби PvP (Спринт 2.1.F, ГДД §7.1).

Лобби — это очередь pending-вызовов в режиме ``GLOBAL_ONLY`` (либо
авто-промоутнутых из ``CHAT_THEN_GLOBAL`` по истечении 3 мин). Любой
свободный игрок, проходящий PvP-требования, может «принять из лобби»
самый старый вызов через use-case ``MatchFromLobby`` (Спринт 2.1.F.2).

Записи в лобби живут не дольше ``balance.pvp.duel_1v1.global_lobby_ttl_minutes``
(по умолчанию **10 мин**). Истечение TTL обслуживается шедулером
(``ExpireLobbyEntry``-job, Спринт 2.1.F.2): по моменту
``enqueued_at + ttl`` запись удаляется и связанная дуэль автоматически
отменяется.

Архитектурные решения:

* **Один pending-вызов на одну запись лобби.** Связь 1:1 через `duel_id`
  (он же PK таблицы ``pvp_global_lobby``). Если шедулер пытается
  поставить уже стоящий вызов в очередь — `enqueue` идемпотентен.
* **FIFO по `enqueued_at`.** На уровне БД отсортировано индексом
  ``ix_pvp_global_lobby_enqueued_at``. На уровне домена тип
  ``LobbyEntry`` несёт момент постановки в очередь и `duel_id`.
* **Атомарный `pop_oldest`.** Использует `SELECT … ORDER BY … LIMIT 1
  FOR UPDATE SKIP LOCKED` (на PG; на SQLite в тестах деградирует до
  обычного SELECT + DELETE под единой транзакцией UoW). Так не возникает
  гонки, когда два игрока нажмут "/duel_global" одновременно.
* **Каскадное удаление по `pvp_duels`.** Если основной duel-row удалён
  (что в проде не должно случаться — мы только меняем `state`), то
  лобби-запись тоже пропадает (ON DELETE CASCADE).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "IGlobalLobbyRepository",
    "LobbyEntry",
]


@dataclass(frozen=True, slots=True)
class LobbyEntry:
    """Запись в глобальном FIFO-лобби PvP (одна на pending-дуэль).

    Атрибуты:

    * ``duel_id`` — идентификатор дуэли (PK таблицы и FK на ``pvp_duels``).
    * ``enqueued_at`` — момент постановки в очередь (UTC, tz-aware).
      По этому полю упорядочено лобби (FIFO).
    """

    duel_id: int
    enqueued_at: datetime


class IGlobalLobbyRepository(abc.ABC):
    """Доступ к таблице ``pvp_global_lobby`` (Спринт 2.1.F).

    Все методы исполняются внутри активного ``IUnitOfWork``; собственный
    коммит репозиторий не делает. Use-case-ы 2.1.F.2 вызывают этот порт
    через ambient-UoW.
    """

    @abc.abstractmethod
    async def enqueue(self, *, duel_id: int, enqueued_at: datetime) -> bool:
        """Поставить дуэль в очередь.

        Возвращает ``True``, если запись была реально добавлена; ``False`` —
        если такая запись уже существует (идемпотентный вход для шедулера
        и для случая параллельной попытки enqueue одного и того же
        дуэли). Дублирующая попытка не падает — это намеренно: вызов
        `EnqueueGlobalDuel` может прийти несколько раз
        (challenge → escalation), и нам важно сохранить первоначальный
        ``enqueued_at`` для FIFO-упорядочивания.
        """

    @abc.abstractmethod
    async def pop_oldest(self) -> LobbyEntry | None:
        """Атомарно извлечь самую старую запись из очереди.

        Возвращает ``None``, если лобби пустое. Удаляет запись из
        таблицы под той же транзакцией. На PG использует
        ``FOR UPDATE SKIP LOCKED`` для безопасной конкуренции
        нескольких воркеров; на SQLite — простую сериализацию.
        """

    @abc.abstractmethod
    async def remove(self, *, duel_id: int) -> bool:
        """Удалить запись по `duel_id` (NO-OP, если её нет).

        Возвращает ``True``, если запись была удалена; ``False``,
        если её не было. Используется в `AcceptDuel` (когда
        самопринятие из лобби) и `CancelDuel` (когда челленджер
        передумал до ExpireLobbyEntry).
        """

    @abc.abstractmethod
    async def is_in_lobby(self, *, duel_id: int) -> bool:
        """Проверить, стоит ли указанная дуэль в очереди.

        Используется use-case-ами для idempotency-проверок (например,
        `EscalateChatToGlobal` не двинет вторую запись, если уже
        двинули первую). Чистый read; никаких побочных эффектов.
        """
