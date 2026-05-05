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
from pipirik_wars.application.pvp.apply_outcome import apply_duel_outcome
from pipirik_wars.application.pvp.cancel_duel import CancelDuel, DuelCancelled
from pipirik_wars.application.pvp.challenge_duel import ChallengeDuel, DuelChallenged
from pipirik_wars.application.pvp.resolve_afk_round import (
    AfkRoundResolved,
    ResolveAfkRound,
)
from pipirik_wars.application.pvp.submit_move import MoveSubmitted, SubmitMove

__all__ = [
    "AcceptDuel",
    "AfkRoundResolved",
    "CancelDuel",
    "ChallengeDuel",
    "DuelAccepted",
    "DuelCancelled",
    "DuelChallenged",
    "MoveSubmitted",
    "ResolveAfkRound",
    "SubmitMove",
    "apply_duel_outcome",
]
