"""`ErrorHandlerMiddleware` — последний рубеж перед aiogram-ом.

Доменные исключения (`DomainError` и подклассы) превращаются в
дружелюбные ответы пользователю; неожиданные исключения логируются
структурированно через `structlog` и **прокидываются** дальше — пусть
их подберёт aiogram-овский логгер ошибок и при необходимости отправит
в наблюдаемость (Sentry-like, когда подключим).

Это middleware ставится первым в цепочке (то есть — как outermost),
чтобы видеть исключения всех остальных middleware-ов и handler-а.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from pipirik_wars.shared.errors import DomainError

DOMAIN_ERROR_REPLY_RU = "❌ {message}"
UNEXPECTED_REPLY_RU = "⚠️ Что-то пошло не так. Попробуй позже."

_log = structlog.get_logger("bot.error_handler")


class ErrorHandlerMiddleware(BaseMiddleware):
    """Ловит `DomainError` (отвечает пользователю) и неожиданные ошибки."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except DomainError as exc:
            _log.info(
                "domain_error",
                error_type=type(exc).__name__,
                message=str(exc),
            )
            if isinstance(event, Message):
                await event.answer(DOMAIN_ERROR_REPLY_RU.format(message=str(exc)))
            return None
        except Exception as exc:
            _log.exception(
                "unexpected_handler_error",
                error_type=type(exc).__name__,
            )
            if isinstance(event, Message):
                await event.answer(UNEXPECTED_REPLY_RU)
            # Прокидываем дальше — чтобы aiogram/observability увидели.
            raise
