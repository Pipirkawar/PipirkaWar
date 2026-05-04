"""Доменные ошибки подсистемы «Клан» (Спринт 1.1)."""

from __future__ import annotations

from pipirik_wars.shared.errors import ConcurrencyError, DomainError


class ClanAlreadyRegisteredError(ConcurrencyError):
    """Попытка зарегистрировать `chat_id`, который уже есть в `clans`.

    Случай: бот добавили в чат → запись создана; кто-то снова кикнул и
    добавил бота → use-case должен переиспользовать существующую запись
    (через `unfreeze`), а не создавать дубль. Эта ошибка означает баг
    в use-case (вызвал `add` вместо `save`), а не пользовательскую
    ситуацию.
    """

    def __init__(self, *, chat_id: int) -> None:
        super().__init__(f"clan with chat_id={chat_id} is already registered")
        self.chat_id = chat_id


class ClanFrozenError(DomainError):
    """Попытка мутировать состояние замороженного клана."""

    def __init__(self, *, chat_id: int) -> None:
        super().__init__(f"clan chat_id={chat_id} is frozen and cannot be mutated")
        self.chat_id = chat_id


class ClanMembershipExistsError(ConcurrencyError):
    """Игрок уже состоит в этом клане.

    Бросается из `IClanMembershipRepository.add` при дубле
    `(clan_id, player_id)`.
    """

    def __init__(self, *, clan_id: int, player_id: int) -> None:
        super().__init__(f"player_id={player_id} is already a member of clan_id={clan_id}")
        self.clan_id = clan_id
        self.player_id = player_id
