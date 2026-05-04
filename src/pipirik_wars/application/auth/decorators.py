"""Декораторы авторизации use-case-ов.

Декорируют корутины формы `async def fn(ctx: AuthContext, ...)`.
Если требование не выполнено, бросают `AuthorizationError` с указанием
непройденного критерия. На уровне bot/admin это маппится на user-friendly
сообщение через локализацию.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from pipirik_wars.application.auth.context import AuthContext
from pipirik_wars.shared.errors import DomainError

P = ParamSpec("P")
R = TypeVar("R")


class AuthorizationError(DomainError):
    """Доступ к use-case-у запрещён."""

    def __init__(self, *, requirement: str, detail: str) -> None:
        super().__init__(f"authorization failed: {requirement} ({detail})")
        self.requirement = requirement
        self.detail = detail


def _extract_ctx(args: tuple[object, ...]) -> AuthContext:
    if not args:
        raise TypeError("decorated function must accept AuthContext as first arg")
    ctx = args[0]
    if not isinstance(ctx, AuthContext):
        raise TypeError(
            "first arg must be AuthContext, got " + type(ctx).__name__,
        )
    return ctx


def requires_level(
    minimum: int,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Гейт по минимальному уровню."""

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            ctx = _extract_ctx(args)
            if ctx.level < minimum:
                raise AuthorizationError(
                    requirement="level",
                    detail=f"need >= {minimum}, have {ctx.level}",
                )
            return await fn(*args, **kwargs)

        return wrapper

    return decorator


def requires_length(
    minimum_cm: int,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Гейт по минимальной длине (например, «правило 20 см» для PvP)."""

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            ctx = _extract_ctx(args)
            if ctx.length_cm < minimum_cm:
                raise AuthorizationError(
                    requirement="length",
                    detail=f"need >= {minimum_cm} cm, have {ctx.length_cm} cm",
                )
            return await fn(*args, **kwargs)

        return wrapper

    return decorator


def requires_clan_member(
    fn: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    """Гейт «участник клана».

    Принимает функцию напрямую (без аргументов в декораторе), чтобы
    не плодить пустые `requires_clan_member()`.
    """

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        ctx = _extract_ctx(args)
        if ctx.clan_id is None:
            raise AuthorizationError(
                requirement="clan_member",
                detail="actor is not a clan member",
            )
        return await fn(*args, **kwargs)

    return wrapper
