"""`AnticheatGuard` — гейт спендалок длины (Спринт 1.6.E, ГДД §3.3.5).

Symmetrical к soft-ban-гейту в `progression.add_length` (1.6.D):
если игрок в активном soft-ban-е, ему нельзя ни **получать** длину
(гейт в `AddLength`), ни **тратить** длину (этот гейт здесь). Иначе
читер мог бы быстро спустить накопленное и обойти проверку.

Use-cases-спендалки длины (`UpgradeThickness`, в будущем PvP-дуэли,
караваны, рейды) вызывают `AnticheatGuard.require_unlocked(player,
now=clock.now())` ДО любой mutate-логики (после load player).

Сервис — чистая stateless-функция (`@staticmethod`), без I/O, без
конструктора, без слотов. Достаточно `from ... import AnticheatGuard;
AnticheatGuard.require_unlocked(...)`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pipirik_wars.domain.progression.errors import AnticheatSoftBanError

if TYPE_CHECKING:
    from pipirik_wars.domain.player import Player


class AnticheatGuard:
    """Чистый гейт «не в soft-ban-е»."""

    @staticmethod
    def require_unlocked(player: Player, *, now: datetime) -> None:
        """Бросает `AnticheatSoftBanError`, если игрок в soft-ban-е.

        :param player: Игрок (`Player.anticheat_ban_until` — момент
            истечения soft-ban-а или None).
        :param now: Текущее время (UTC, tz-aware) — обычно
            `clock.now()` из use-case-а.
        :raises AnticheatSoftBanError: если
            `player.is_anticheat_banned(now=now)` вернул True.
        """
        if player.is_anticheat_banned(now=now):
            assert player.anticheat_ban_until is not None
            raise AnticheatSoftBanError(
                tg_id=player.tg_id,
                banned_until=player.anticheat_ban_until,
            )
