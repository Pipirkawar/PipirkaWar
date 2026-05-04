"""Use-cases подсистемы `signup_queue` (Спринт 1.2.5)."""

from pipirik_wars.application.signup_queue.promote import (
    PromoteFromQueue,
    PromoteFromQueueResult,
)

__all__ = ["PromoteFromQueue", "PromoteFromQueueResult"]
