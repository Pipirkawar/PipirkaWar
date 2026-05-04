"""Авторизация в application-слое.

Декораторы `requires_*` — это контракты use-case-ов: «мой вход требует
такого-то контекста». Они не зависят от aiogram (handlers); aiogram-
middleware будет в `bot/` собирать `AuthContext` и передавать его в use-case.

ГДД §0: безопасность через слои → каждое требование явно и тестируемо.
"""

from pipirik_wars.application.auth.context import AuthContext
from pipirik_wars.application.auth.decorators import (
    AuthorizationError,
    requires_clan_member,
    requires_length,
    requires_level,
)

__all__ = [
    "AuthContext",
    "AuthorizationError",
    "requires_clan_member",
    "requires_length",
    "requires_level",
]
