"""Доменные ошибки подсистемы «Игрок» (Спринт 1.1)."""

from __future__ import annotations

from pipirik_wars.shared.errors import ConcurrencyError, DomainError


class PlayerAlreadyRegisteredError(ConcurrencyError):
    """Попытка зарегистрировать `tg_id`, которая уже есть в `users`.

    Отличается от `ConcurrencyError` лишь типом — на уровне bot-handler-а
    превратится в дружелюбное «вы уже зарегистрированы». Это не баг и
    не нарушение инвариантов, поэтому `ConcurrencyError`, а не
    `DomainError`.
    """

    def __init__(self, *, tg_id: int) -> None:
        super().__init__(f"player with tg_id={tg_id} is already registered")
        self.tg_id = tg_id


class PlayerFrozenError(DomainError):
    """Любая попытка мутировать состояние замороженного игрока.

    «Заморозка» (`PlayerStatus.FROZEN`) — это сохранение всех данных
    игрока без возможности играть (ГДД §1.5). Любые `with_*`-операции
    на замороженном `Player` должны бросать эту ошибку, чтобы
    use-case-ы могли отдать пользователю «вы заморожены, обратитесь к
    админам» вместо тихой перезаписи.
    """

    def __init__(self, *, tg_id: int) -> None:
        super().__init__(f"player tg_id={tg_id} is frozen and cannot be mutated")
        self.tg_id = tg_id


class PlayerNotFoundError(DomainError):
    """Игрок с таким `tg_id` не зарегистрирован.

    Use-case-ы, которые требуют существующего игрока (например,
    `StartForestRun`), бросают её, чтобы handler показал «сначала
    /start» вместо «непонятная ошибка». Не путать с
    `PlayerAlreadyRegisteredError` — там попытка зарегистрировать
    дубль; здесь — попытка работать с несуществующим.
    """

    def __init__(self, *, tg_id: int) -> None:
        super().__init__(f"player with tg_id={tg_id} is not registered")
        self.tg_id = tg_id
