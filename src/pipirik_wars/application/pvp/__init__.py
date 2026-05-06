"""Application-use-cases подсистемы PvP 1×1 (Спринт 2.1.D, ГДД §7.1).

Состав:

* `ChallengeDuel` — создание pending-вызова + activity-lock на
  челленджера + audit `PVP_DUEL_CREATED`.
* `AcceptDuel` — приём вызова, переход PENDING_ACCEPT → IN_PROGRESS,
  снапшот длин, activity-lock на оппонента, audit `PVP_DUEL_ACCEPTED`.
* `CancelDuel` — отмена pending-вызова челленджером (или
  шедулером 2.1.F при истечении TTL); audit `PVP_DUEL_CANCELLED`.
* `SubmitMove` — отправка хода; при завершении дуэли применяет ±длины
  через `apply_duel_outcome` и пишет audit `PVP_DUEL_COMPLETED`.
* `ResolveAfkRound` — AFK-фоллбэк раунда: добивает случайные выборы
  через `IRandom` и продолжает как `SubmitMove`.

Все use-cases работают через ambient `IUnitOfWork` (вызывающий
шедулер/handler сам открывает транзакцию через `async with self._uow:`),
сохраняют через `IDuelRepository`, пишут аудит атомарно, и интегрируются
с `ActivityLockService` (ГДД §3.2: «нельзя одновременно в `/forest`
и в дуэли»).

`apply_duel_outcome` — внутренний хелпер, шеринг между `SubmitMove`
и `ResolveAfkRound`. Прибавка победителю — через `ILengthGranter.grant(
source=PVP_REWARD)` (anti-cheat-cap из 1.6); списание проигравшему —
прямой `with_length` + audit `LENGTH_REVOKE` (как в `UpgradeThickness`).
"""

from pipirik_wars.application.pvp.accept_duel import AcceptDuel, DuelAccepted
from pipirik_wars.application.pvp.apply_mass_outcome import apply_mass_duel_outcome
from pipirik_wars.application.pvp.apply_outcome import apply_duel_outcome
from pipirik_wars.application.pvp.cancel_duel import CancelDuel, DuelCancelled
from pipirik_wars.application.pvp.cancel_mass_duel import CancelMassDuel, MassDuelCancelled
from pipirik_wars.application.pvp.challenge_duel import ChallengeDuel, DuelChallenged
from pipirik_wars.application.pvp.clan_history_query import IClanMassDuelHistoryQuery
from pipirik_wars.application.pvp.enqueue_global_duel import (
    EnqueueGlobalDuel,
    GlobalDuelEnqueued,
    InvalidLobbyEnqueueError,
)
from pipirik_wars.application.pvp.escalate_chat_to_global import (
    DuelEscalated,
    DuelEscalationSkipped,
    EscalateChatToGlobal,
)
from pipirik_wars.application.pvp.expire_lobby_entry import (
    ExpireLobbyEntry,
    LobbyEntryExpirationSkipped,
    LobbyEntryExpired,
)
from pipirik_wars.application.pvp.force_resolve_mass_duel import (
    ForceResolveMassDuel,
    MassDuelForceResolved,
)
from pipirik_wars.application.pvp.get_clan_attack_history import GetClanAttackHistory
from pipirik_wars.application.pvp.log_templates import IDuelLogTemplateProvider
from pipirik_wars.application.pvp.match_from_lobby import (
    DuelMatched,
    EmptyLobby,
    LobbyEntryStale,
    MatchFromLobby,
)
from pipirik_wars.application.pvp.resolve_afk_round import (
    AfkRoundResolved,
    ResolveAfkRound,
)
from pipirik_wars.application.pvp.resolve_mass_duel import MassDuelResolved, ResolveMassDuel
from pipirik_wars.application.pvp.start_mass_duel import MassDuelStarted, StartMassDuel
from pipirik_wars.application.pvp.submit_mass_move import MassMoveSubmitted, SubmitMassMove
from pipirik_wars.application.pvp.submit_move import MoveSubmitted, SubmitMove

__all__ = [
    "AcceptDuel",
    "AfkRoundResolved",
    "CancelDuel",
    "CancelMassDuel",
    "ChallengeDuel",
    "DuelAccepted",
    "DuelCancelled",
    "DuelChallenged",
    "DuelEscalated",
    "DuelEscalationSkipped",
    "DuelMatched",
    "EmptyLobby",
    "EnqueueGlobalDuel",
    "EscalateChatToGlobal",
    "ExpireLobbyEntry",
    "ForceResolveMassDuel",
    "GetClanAttackHistory",
    "GlobalDuelEnqueued",
    "IClanMassDuelHistoryQuery",
    "IDuelLogTemplateProvider",
    "InvalidLobbyEnqueueError",
    "LobbyEntryExpirationSkipped",
    "LobbyEntryExpired",
    "LobbyEntryStale",
    "MassDuelCancelled",
    "MassDuelForceResolved",
    "MassDuelResolved",
    "MassDuelStarted",
    "MassMoveSubmitted",
    "MatchFromLobby",
    "MoveSubmitted",
    "ResolveAfkRound",
    "ResolveMassDuel",
    "StartMassDuel",
    "SubmitMassMove",
    "SubmitMove",
    "apply_duel_outcome",
    "apply_mass_duel_outcome",
]
