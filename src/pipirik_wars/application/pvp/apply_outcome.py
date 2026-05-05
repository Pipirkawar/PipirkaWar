"""Применение `DuelOutcome` к длинам игроков (Спринт 2.1.D).

Хелпер для use-cases `SubmitMove` и `ResolveAfkRound`. Вызывается
**внутри** активного `IUnitOfWork` сразу после того, как `Duel`
переходит в `COMPLETED` и `final_outcome` известен.

Семантика:

* PvP zero-sum: `outcome.p1_delta_cm + outcome.p2_delta_cm == 0`
  (домен это гарантирует).
* **Прибавка** длины победителю (`delta > 0`) идёт через единый
  `ILengthGranter.grant(source=PVP_REWARD)` — anti-cheat-cap из
  Спринта 1.6 «лечит» PvP-фарм-экспоит (ГДД §3.3.4 / 3.3.5).
* **Списание** длины проигравшему (`delta < 0`) идёт прямой мутацией
  `Player.with_length(...)` + audit `LENGTH_REVOKE` — это «трата»
  длины, к которой cap-ы 1.6 не применимы (по той же причине, что
  и в `UpgradeThickness`). Файл попадает в `_ALLOWED_FILES`
  архитектурного guard-а `tests/unit/architecture/test_length_grant_guard.py`.
* Ничья (`delta == 0` у обеих сторон) — ничего не пишем, ни в audit,
  ни в `players` (соответствует ГДД §7.1: «при равных дамажах —
  длина не меняется»).

Идемпотентность:

* Audit-записи помечены `idempotency_key=f"pvp_duel_completed:<duel.id>:<side>"`
  и `f"pvp_duel_loss_revoke:<duel.id>:<side>"` — повторное
  «применение исхода» (например, ресхед) не задублирует записи в
  audit-логе. На практике повторного применения быть не должно
  (`Duel` иммутабелен после `COMPLETED`), но дубль-защита дёшева.
* Прибавка победителю переиспользует idempotency-инфраструктуру
  `AddLength` через `idempotency_key=f"pvp_duel_won:<duel.id>:<winner_side>"`.

Эта операция мутирует двух игроков, поэтому требует загрузки обоих
из репозитория (даже если delta == 0 — для логирования new_length_cm).
"""

from __future__ import annotations

from datetime import datetime

from pipirik_wars.domain.player import IPlayerRepository, Length, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.pvp import Duel
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    AuditSource,
    IAuditLogger,
)


async def apply_duel_outcome(
    *,
    duel: Duel,
    players: IPlayerRepository,
    length_granter: ILengthGranter,
    audit: IAuditLogger,
    now: datetime,
) -> None:
    """Применить `duel.final_outcome` к длинам обеих сторон.

    Контракт: `duel.is_completed` и `duel.final_outcome is not None`
    (use-case вызывает только после `Duel.submit_move` /
    `Duel.force_complete_round` вернул `state=COMPLETED`).

    Бросает:
    - `PlayerNotFoundError` — если кто-то из игроков пропал из БД
      между `accept` и `complete` (не должно случаться, но мы
      защищаемся);
    - `AnticheatSoftBanError` — если победитель влетел в soft-ban
      между ходами (через cap-trip-wire предыдущего add_length).
      Транзакция откатится, дуэль остаётся в `COMPLETED` — admin
      руками смотрит audit-лог.
    """

    assert duel.id is not None, "duel must be persisted before apply_outcome"
    assert duel.is_completed, "apply_outcome only on COMPLETED duels"
    outcome = duel.final_outcome
    assert outcome is not None, "COMPLETED duel must have final_outcome"
    assert duel.challenged_id is not None, "challenged_id is set in IN_PROGRESS / COMPLETED states"

    p1 = await players.get_by_id(player_id=duel.challenger_id)
    if p1 is None:
        raise PlayerNotFoundError(tg_id=duel.challenger_id)
    p2 = await players.get_by_id(player_id=duel.challenged_id)
    if p2 is None:
        raise PlayerNotFoundError(tg_id=duel.challenged_id)

    await _apply_side(
        side="p1",
        player=p1,
        delta_cm=outcome.p1_delta_cm,
        duel_id=duel.id,
        players=players,
        length_granter=length_granter,
        audit=audit,
        now=now,
    )
    await _apply_side(
        side="p2",
        player=p2,
        delta_cm=outcome.p2_delta_cm,
        duel_id=duel.id,
        players=players,
        length_granter=length_granter,
        audit=audit,
        now=now,
    )


async def _apply_side(
    *,
    side: str,
    player: Player,
    delta_cm: int,
    duel_id: int,
    players: IPlayerRepository,
    length_granter: ILengthGranter,
    audit: IAuditLogger,
    now: datetime,
) -> None:
    if delta_cm == 0:
        return
    assert player.id is not None
    if delta_cm > 0:
        # Прибавка победителю — через ILengthGranter (anti-cheat cap).
        await length_granter.grant(
            player_id=player.id,
            delta_cm=delta_cm,
            source=AuditSource.PVP_REWARD,
            reason="pvp_duel_won",
            idempotency_key=f"add_length:pvp_duel:{duel_id}:{side}",
        )
        return
    # delta_cm < 0 — списание длины проигравшему. Длина не уходит
    # ниже нуля (Length.__post_init__: cm >= 0). В реальности
    # min_length_cm проверяется на входе в PvP, а урон ограничен
    # снимком длин, поэтому вычитание физически не уведёт ниже 0
    # (max-clamp здесь — страховка от багов в будущих версиях
    # резолвера).
    new_cm = max(0, player.length.cm + delta_cm)
    new_length = Length(cm=new_cm)
    after = player.with_length(new_length, now=now)
    saved = await players.save(after)
    await audit.record(
        AuditEntry(
            action=AuditAction.LENGTH_REVOKE,
            actor_id=player.tg_id,
            target_kind="player",
            target_id=str(player.id),
            before={"length_cm": player.length.cm},
            after={"length_cm": saved.length.cm},
            reason="pvp_duel_loss",
            idempotency_key=f"pvp_duel_loss_revoke:{duel_id}:{side}",
            occurred_at=now,
            source=AuditSource.PVP_REWARD,
            delta_cm=delta_cm,
        )
    )


__all__ = [
    "apply_duel_outcome",
]
