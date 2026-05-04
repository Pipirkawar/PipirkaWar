"""Доменные ошибки подсистемы безопасности."""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError


class LockAlreadyHeldError(DomainError):
    """Двойной захват блокировки тем же актором.

    Бросается из `ActivityLockService.acquire`, когда у `(actor_kind, actor_id)`
    уже есть НЕ-истёкшая запись. На уровне bot/admin маппится на
    дружелюбное сообщение «вы уже что-то делаете, дождитесь окончания».
    """

    def __init__(self, *, actor_kind: str, actor_id: int) -> None:
        super().__init__(
            f"activity lock already held by ({actor_kind}, {actor_id})",
        )
        self.actor_kind = actor_kind
        self.actor_id = actor_id
