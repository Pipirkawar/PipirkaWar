"""Application-уровень модуля «Рейд-боссы» (Спринт 3.3-B / 3.3-C, ГДД §10).

Use-case-ы:

- :class:`SummonBoss` — игрок-саммонер уровня 9+ призывает рейд-босса
  (случайного из топ-30 по длине). Создаёт `BossFight` в `LOBBY` и
  атомарно вступает первым рейдером (`is_summoner=True`).
- :class:`JoinBossLobby` — игрок жмёт «Вступить в рейд» в лобби
  (lvl 4+, ≥ 20 см длины).
- :class:`LeaveBossLobby` — игрок выходит из лобби. На уровне 3.3-B
  без авто-каскада в `CANCELLED` (это 3.3-C / `CancelBossFight`).
- :class:`CloseBossLobby` — APScheduler-job переводит рейд-бой
  `LOBBY → IN_BATTLE` идемпотентно, шедулит `boss_round_tick` и
  `boss_fight_finish` safety-net.

Боевая механика (`RunBossRound` / `FinishBossFight`) — Спринт 3.3-C.
Use-case `CancelBossFight` (саммонер отменяет рейд из лобби) +
bot-handler-ы + i18n-сообщения — Спринт 3.3-D.
"""

from pipirik_wars.application.bosses.cancel_boss_fight import (
    BossFightCancelled,
    CancelBossFight,
)
from pipirik_wars.application.bosses.close_boss_lobby import (
    BossLobbyClosed,
    CloseBossLobby,
)
from pipirik_wars.application.bosses.finish_boss_fight import (
    BossFightFinished,
    BossScrollDrop,
    FinishBossFight,
)
from pipirik_wars.application.bosses.join_boss_lobby import (
    BossLobbyJoined,
    JoinBossLobby,
)
from pipirik_wars.application.bosses.leave_boss_lobby import (
    BossLobbyLeft,
    LeaveBossLobby,
)
from pipirik_wars.application.bosses.run_boss_round import (
    BossRoundResolved,
    RunBossRound,
)
from pipirik_wars.application.bosses.summon_boss import (
    BossSummoned,
    SummonBoss,
)

__all__ = [
    "BossFightCancelled",
    "BossFightFinished",
    "BossLobbyClosed",
    "BossLobbyJoined",
    "BossLobbyLeft",
    "BossRoundResolved",
    "BossScrollDrop",
    "BossSummoned",
    "CancelBossFight",
    "CloseBossLobby",
    "FinishBossFight",
    "JoinBossLobby",
    "LeaveBossLobby",
    "RunBossRound",
    "SummonBoss",
]
