"""Application-уровень модуля «Караван» (Спринты 3.2-B / 3.2-C / 3.2-D, ГДД §9).

Use-case-ы:

- :class:`CreateCaravan` — лидер клана-отправителя создаёт караван
  и автоматически становится первым `CARAVANEER`-ом-лидером.
- :class:`JoinCaravanLobby` — игрок вступает в лобби в одной из
  трёх ролей (`CARAVANEER` / `DEFENDER` / `RAIDER`).
- :class:`LeaveCaravanLobby` — игрок (не лидер) выходит из лобби.
- :class:`CloseCaravanLobby` — APScheduler-job или ручной вызов
  переводит караван `LOBBY → IN_BATTLE`.
- :class:`FinishCaravanBattle` — APScheduler-job на `battle_ends_at`
  резолвит бой, начисляет награды, переводит `IN_BATTLE → FINISHED`.
- :class:`CancelCaravan` — лидер отменяет караван из `LOBBY`
  (Спринт 3.2-D).

Bot-handler-ы и i18n-сообщения — Спринт 3.2-D.
"""

from pipirik_wars.application.caravans.cancel_caravan import (
    CancelCaravan,
    CaravanCancelled,
)
from pipirik_wars.application.caravans.close_caravan_lobby import (
    CloseCaravanLobby,
    ClosedCaravanLobby,
)
from pipirik_wars.application.caravans.create_caravan import (
    CaravanCreated,
    CreateCaravan,
)
from pipirik_wars.application.caravans.finish_caravan_battle import (
    CaravanBattleFinished,
    FinishCaravanBattle,
)
from pipirik_wars.application.caravans.join_caravan_lobby import (
    JoinCaravanLobby,
    JoinedCaravanLobby,
)
from pipirik_wars.application.caravans.leave_caravan_lobby import (
    LeaveCaravanLobby,
    LeftCaravanLobby,
)
from pipirik_wars.application.caravans.notifier import (
    ICaravanBattleFinishNotifier,
    ICaravanLobbyCloseNotifier,
)

__all__ = [
    "CancelCaravan",
    "CaravanBattleFinished",
    "CaravanCancelled",
    "CaravanCreated",
    "CloseCaravanLobby",
    "ClosedCaravanLobby",
    "CreateCaravan",
    "FinishCaravanBattle",
    "ICaravanBattleFinishNotifier",
    "ICaravanLobbyCloseNotifier",
    "JoinCaravanLobby",
    "JoinedCaravanLobby",
    "LeaveCaravanLobby",
    "LeftCaravanLobby",
]
