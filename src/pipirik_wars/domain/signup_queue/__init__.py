"""Доменный слой `signup_queue` — очередь регистраций при `DAU >= MAX_DAU`.

См. ГДД §18 (DAU Gate) и `development_plan.md` Спринт 1.2 задачи 1.2.4 / 1.2.5.

Очередь FIFO: при превышении `MAX_DAU` `RegisterPlayer` ставит игрока
сюда; `PromoteFromQueue` забирает первых N, когда появляется свободное
место (либо `/set_max_dau` поднял лимит, либо новый день обнулил DAU).
"""

from pipirik_wars.domain.signup_queue.entities import (
    SignupQueueEntry,
    SignupQueueStatus,
)
from pipirik_wars.domain.signup_queue.errors import (
    AlreadyQueuedError,
    SignupQueueError,
)
from pipirik_wars.domain.signup_queue.ports import ISignupQueueRepository

__all__ = [
    "AlreadyQueuedError",
    "ISignupQueueRepository",
    "SignupQueueEntry",
    "SignupQueueError",
    "SignupQueueStatus",
]
