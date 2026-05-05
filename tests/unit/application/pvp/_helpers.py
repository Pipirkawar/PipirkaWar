"""Общие фикстуры для unit-тестов use-cases PvP (Спринт 2.1.D)."""

from __future__ import annotations

from datetime import UTC, datetime

from pipirik_wars.domain.player import Length, Player, Thickness, Username
from tests.fakes import FakePlayerRepository

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


async def seed_pvp_eligible_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    username: str = "alice",
    length_cm: int = 50,
    thickness_level: int = 2,
) -> Player:
    """Создать игрока, проходящего PvP-требования по умолчанию.

    Дефолтный balance.pvp.duel_1v1: `min_length_cm=20`,
    `min_thickness_level=2`. Стартовый `Player.new` имеет
    length=2, thickness=1 — оба ниже порога; здесь сразу
    апгрейдим до значений выше порога.
    """

    fresh = Player.new(
        tg_id=tg_id,
        username=Username(value=username),
        now=_NOW,
    )
    persisted = await players.add(fresh)
    upgraded = persisted.with_thickness(Thickness(level=thickness_level), now=_NOW).with_length(
        Length(cm=length_cm), now=_NOW
    )
    return await players.save(upgraded)


__all__ = ["seed_pvp_eligible_player"]
