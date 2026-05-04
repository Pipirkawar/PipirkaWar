"""Порты `signup_queue`."""

from __future__ import annotations

import abc

from pipirik_wars.domain.signup_queue.entities import SignupQueueEntry


class ISignupQueueRepository(abc.ABC):
    """Репозиторий очереди регистраций (FIFO по `enqueued_at`)."""

    @abc.abstractmethod
    async def enqueue(self, *, entry: SignupQueueEntry) -> SignupQueueEntry:
        """Добавить игрока в конец очереди и вернуть «канонический» инстанс
        с `id` и `position`.

        Бросает `AlreadyQueuedError`, если `tg_id` уже стоит в очереди.
        """

    @abc.abstractmethod
    async def get_by_tg_id(self, tg_id: int) -> SignupQueueEntry | None:
        """Найти запись по `tg_id`. `None`, если такого `tg_id` нет."""

    @abc.abstractmethod
    async def size(self) -> int:
        """Сколько игроков сейчас в очереди."""

    @abc.abstractmethod
    async def pop_front(self, *, limit: int) -> list[SignupQueueEntry]:
        """Удалить первые `limit` записей (FIFO) и вернуть их.

        Если `limit <= 0` — возвращает пустой список без модификации.
        Если в очереди меньше, чем `limit` — возвращает все, что есть.
        """
