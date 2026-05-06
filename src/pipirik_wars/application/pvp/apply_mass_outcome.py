"""Применение `MassDuelOutcome` к длинам всех участников (Спринт 2.2.E).

Хелпер для use-cases `ResolveMassDuel` и `ForceResolveMassDuel`.
Вызывается **внутри** активного `IUnitOfWork` сразу после того, как
:class:`MassDuel` переходит в `COMPLETED` и `final_outcome` известен.

Семантика:

* Mass-PvP zero-sum: сумма ``damage_cm`` всех ударов в одну сторону
  забирается у защитников и достаётся атакующим. Доменный
  :class:`MassDuelOutcome` гарантирует
  ``clan1_delta_cm + clan2_delta_cm == 0``; на уровне отдельного
  участника:

  * **delta_cm > 0** (атакующий нанёс хотя бы один не заблокированный
    удар) — прибавка через :class:`ILengthGranter` с
    ``source=PVP_REWARD`` (anti-cheat-cap из 1.6 применяется ровно
    как в 1×1 PvP);
  * **delta_cm < 0** (защитника пробили хотя бы один раз) —
    прямой ``Player.with_length(...)`` + audit ``LENGTH_REVOKE``
    (cap-ы 1.6 к вычетам не применимы; этот файл попадает в
    ``_ALLOWED_FILES`` архитектурного guard-а
    `tests/unit/architecture/test_length_grant_guard.py` симметрично
    `apply_outcome.py`);
  * **delta_cm == 0** (не атаковал и не пробит) — ничего не пишем.

Идемпотентность:

* Прибавки победителям через `idempotency_key=
  f"add_length:pvp_mass_duel:{duel_id}:{player_id}"` (повторное
  применение исхода не задублирует gain через `AddLength`).
* Audit-записи списания — `idempotency_key=
  f"pvp_mass_duel_loss_revoke:{duel_id}:{player_id}"`.

Эта операция мутирует N+M игроков в худшем случае (каждый mass-duel
участник либо +, либо -). Загружаем игроков лениво по `id`-ам из
`damage_entries`, не из ростера, чтобы не делать N запросов «впустую»
для тех, кто и не атаковал, и не был задет.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from pipirik_wars.domain.player import IPlayerRepository, Length, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.pvp import MassDuel
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    AuditSource,
    IAuditLogger,
)


async def apply_mass_duel_outcome(
    *,
    duel: MassDuel,
    players: IPlayerRepository,
    length_granter: ILengthGranter,
    audit: IAuditLogger,
    now: datetime,
) -> None:
    """Применить `duel.final_outcome` к длинам всех участников.

    Контракт: `duel.is_completed` (use-case вызывает только после
    `MassDuel.resolve(...)` вернул `state=COMPLETED`).

    Бросает:
    - `PlayerNotFoundError` — если кто-то из участников пропал из БД
      между `add` и `resolve` (не должно случаться, но мы защищаемся);
    - `AnticheatSoftBanError` — если кто-то из атакующих влетел в
      soft-ban через cap-trip-wire предыдущего add_length. Транзакция
      откатится, mass-duel остаётся в `COMPLETED` — admin руками смотрит
      audit-лог.
    """

    assert duel.id is not None, "mass-duel must be persisted before apply_mass_duel_outcome"
    outcome = duel.final_outcome
    assert outcome is not None, "COMPLETED mass-duel must have final_outcome"

    # Считаем per-player delta из damage_entries: атакующий → +damage_cm,
    # защитник → -damage_cm. Заблокированные удары (`damage_cm == 0`)
    # дают нулевой вклад, но мы всё равно их игнорируем явно для ясности.
    player_deltas: dict[int, int] = defaultdict(int)
    for entry in outcome.outcome.damage_entries:
        if entry.blocked or entry.damage_cm == 0:
            continue
        player_deltas[entry.attacker_id] += entry.damage_cm
        player_deltas[entry.defender_id] -= entry.damage_cm

    if not player_deltas:
        # Тотальная ничья (все удары заблокированы) — никому ничего не пишем,
        # как и в 1×1 при `delta == 0`.
        return

    # Сортируем по player_id для детерминированного порядка операций
    # и одинаковых idempotency-keys между ретраями.
    for player_id in sorted(player_deltas):
        delta_cm = player_deltas[player_id]
        if delta_cm == 0:
            continue
        await _apply_participant(
            player_id=player_id,
            delta_cm=delta_cm,
            duel_id=duel.id,
            players=players,
            length_granter=length_granter,
            audit=audit,
            now=now,
        )


async def _apply_participant(
    *,
    player_id: int,
    delta_cm: int,
    duel_id: int,
    players: IPlayerRepository,
    length_granter: ILengthGranter,
    audit: IAuditLogger,
    now: datetime,
) -> None:
    if delta_cm > 0:
        # Прибавка атакующему — через ILengthGranter (anti-cheat cap).
        await length_granter.grant(
            player_id=player_id,
            delta_cm=delta_cm,
            source=AuditSource.PVP_REWARD,
            reason="pvp_mass_duel_dealt",
            idempotency_key=f"add_length:pvp_mass_duel:{duel_id}:{player_id}",
        )
        return

    # delta_cm < 0 — списание длины защитника. По тому же шаблону, что
    # `apply_outcome.py` для 1×1: загружаем игрока из БД, считаем
    # `Player.with_length(...)` и пишем audit `LENGTH_REVOKE`.
    player: Player | None = await players.get_by_id(player_id=player_id)
    if player is None:
        raise PlayerNotFoundError(tg_id=player_id)
    new_cm = max(0, player.length.cm + delta_cm)
    new_length = Length(cm=new_cm)
    after = player.with_length(new_length, now=now)
    saved = await players.save(after)
    assert player.id is not None
    await audit.record(
        AuditEntry(
            action=AuditAction.LENGTH_REVOKE,
            actor_id=player.tg_id,
            target_kind="player",
            target_id=str(player.id),
            before={"length_cm": player.length.cm},
            after={"length_cm": saved.length.cm},
            reason="pvp_mass_duel_loss",
            idempotency_key=f"pvp_mass_duel_loss_revoke:{duel_id}:{player_id}",
            occurred_at=now,
            source=AuditSource.PVP_REWARD,
            delta_cm=delta_cm,
        )
    )


__all__ = [
    "apply_mass_duel_outcome",
]
