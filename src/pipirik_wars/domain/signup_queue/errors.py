"""Ошибки очереди регистраций."""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError


class SignupQueueError(DomainError):
    """База ошибок `signup_queue`."""


class AlreadyQueuedError(SignupQueueError):
    """Игрок уже в очереди — повторный enqueue запрещён."""

    def __init__(self, *, tg_id: int) -> None:
        super().__init__(f"tg_id={tg_id} is already in signup queue")
        self.tg_id = tg_id
