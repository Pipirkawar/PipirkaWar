"""Pydantic-DTO на границе bot ↔ application.

Зачем DTO в application/, а не в bot/:
- Pydantic-валидация — это часть application-контракта; bot/ только
  собирает строки из Telegram update-а и передаёт DTO дальше.
- Тесты валидации не требуют поднимать aiogram.
- При появлении web-admin или REST-handler-ов DTO переиспользуются.
"""

from pipirik_wars.application.dto.inputs import (
    GrantLengthInput,
    RegisterClanInput,
    RegisterPlayerInput,
)

__all__ = [
    "GrantLengthInput",
    "RegisterClanInput",
    "RegisterPlayerInput",
]
