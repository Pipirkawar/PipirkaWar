"""Application-уровень модуля «Караван» (Спринт 3.2-B, ГДД §9).

Use-case-ы:

- :class:`CreateCaravan` — лидер клана-отправителя создаёт караван
  и автоматически становится первым `CARAVANEER`-ом-лидером.
- :class:`JoinCaravanLobby` — игрок вступает в лобби в одной из
  трёх ролей (`CARAVANEER` / `DEFENDER` / `RAIDER`).
- :class:`LeaveCaravanLobby` — игрок (не лидер) выходит из лобби.
- :class:`CloseCaravanLobby` — APScheduler-job или ручной вызов
  переводит караван `LOBBY → IN_BATTLE`.

Resolve боя и финальные награды — Спринт 3.2-C (`FinishCaravanBattle`).
Bot-handler-ы и i18n-сообщения — Спринт 3.2-D.
"""

from pipirik_wars.application.caravans.close_caravan_lobby import (
    CloseCaravanLobby,
    ClosedCaravanLobby,
)
from pipirik_wars.application.caravans.create_caravan import (
    CaravanCreated,
    CreateCaravan,
)
from pipirik_wars.application.caravans.join_caravan_lobby import (
    JoinCaravanLobby,
    JoinedCaravanLobby,
)
from pipirik_wars.application.caravans.leave_caravan_lobby import (
    LeaveCaravanLobby,
    LeftCaravanLobby,
)

__all__ = [
    "CaravanCreated",
    "CloseCaravanLobby",
    "ClosedCaravanLobby",
    "CreateCaravan",
    "JoinCaravanLobby",
    "JoinedCaravanLobby",
    "LeaveCaravanLobby",
    "LeftCaravanLobby",
]
