"""`AuthContext` — снимок «кто и откуда вызывает use-case»."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Контекст авторизации use-case-а.

    Сборка контекста — задача bot/-слоя (через middleware): он берёт
    Telegram update, ищет в БД профиль игрока (длина/толщина/клан) и
    передаёт `AuthContext` первым позиционным аргументом в use-case.

    Уровень = производная от толщины (см. ГДД §3); рассчитывается там же,
    в middleware. Для игроков, не проходивших регистрацию, контекст не
    создаётся вовсе — поэтому `length_cm`/`thickness`/`level` гарантированно
    инициализированы.
    """

    actor_tg_id: int
    length_cm: int
    thickness: int
    level: int
    clan_id: int | None
    is_admin: bool
