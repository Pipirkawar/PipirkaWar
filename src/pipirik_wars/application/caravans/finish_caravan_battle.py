"""Use-case `FinishCaravanBattle` (Спринт 3.2-C, ГДД §9.5–§9.6).

Срабатывает по APScheduler-job-у `caravan_battle_finish`,
запланированному в момент перехода `LOBBY → IN_BATTLE` на
`caravan.battle_ends_at`. Применяет ранее не применённый исход:

1. Загружает `caravan` (`ICaravanRepository.get_by_id`).
   Не найден → :class:`CaravanNotFoundError`.
2. Если `status` ∈ {`FINISHED`, `CANCELLED`} — идемпотентный no-op
   (job мог стрельнуть повторно после рестарта воркера или
   `CancelCaravan` уже всё закрыл): возвращаем `was_already_finished=True`,
   ничего не пишем в БД.
3. Если `status` = `LOBBY` — это инвариантное нарушение (job на
   battle_ends_at не должен сработать без LOBBY→IN_BATTLE-перехода);
   бросаем :class:`InvalidCaravanStateError`.
4. Загружает участников (`ICaravanParticipantRepository.list_by_caravan`).
5. Конструирует :class:`IRandom` от `caravan.random_seed` через
   `random_factory: Callable[[int], IRandom]`. В production это
   :class:`SeededRandom`, в тестах — :class:`tests.fakes.random.FakeRandom`.
6. Зовёт чистый :func:`resolve_caravan_battle` (детерминистично от
   seed-а).
7. Применяет per-player длины:
   - **delta_cm > 0** — через :class:`ILengthGranter.grant(...)` с
     `source=CARAVAN_REWARD` и idempotency-key
     `add_length:caravan_battle:{caravan_id}:{player_id}` (anti-cheat
     hardcap из 1.6 применяется ровно как в forest/mountains).
   - **delta_cm < 0** — прямой `Player.with_length(...)` + audit
     `LENGTH_REVOKE` (cap-ы к вычетам неприменимы, см. PvP
     `apply_mass_outcome.py`).
   - **delta_cm == 0** — пропускаем (например, рейдер без
     заблокированных ударов в delivery-исходе).
8. Если `gets_ataman_title=True` (только при победе рейдеров,
   ровно у одного рейдера) — `Player.with_title(Title.ATAMAN)` +
   audit `TITLE_GRANT`.
9. Применяет клан-бонус (только при доставке каравана, ГДД §9.6
   «+1 см каждому» участнику обоих кланов) — для каждого участника
   `IClanMembershipRepository.list_by_clan(sender_clan_id)` и
   `..._by_clan(receiver_clan_id)`: `ILengthGranter.grant(+1)` через
   `source=CARAVAN_REWARD` с idempotency-key
   `add_length:caravan_clan_bonus:{caravan_id}:{sender|receiver}:{player_id}`.
   Дубли (игрок состоит в обоих кланах) теоретически невозможны
   (БД-инвариант `UNIQUE(player_id)` в `clan_members`), но idempotency-keys
   защитят даже при ретрае job-а.
10. Снимает `activity_lock(player, *)` для всех участников каравана
    (NO-OP, если истёк или уже снят).
11. `Caravan.mark_finished(finished_at=now)`, сохраняет.
12. Audit `CARAVAN_BATTLE_FINISHED` (raiders_won, num_outcomes,
    clan_bonus_cm) + `CARAVAN_REWARDS_GRANTED` (агрегаты).

Транзакционность: всё внутри одного `IUnitOfWork`. Любая ошибка
(soft-ban от cap-trip-wire-а, integrity error на player) откатывает
все mutations + аудит — job-воркер ретраит позже.

Идемпотентность по job-уровню: повторный вызов на `FINISHED` —
no-op (см. шаг 2). Повторный вызов из-за рестарта воркера до
коммита транзакции — каждый под-вызов
(`length_granter.grant`, `audit.record`, …) использует idempotency-keys,
так что дубль-апплая не будет.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pipirik_wars.application.dto.inputs import FinishCaravanBattleInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.balance.config import CaravansConfig
from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanNotFoundError,
    ICaravanParticipantRepository,
    ICaravanRepository,
)
from pipirik_wars.domain.caravan.errors import InvalidCaravanStateError
from pipirik_wars.domain.caravan.services import (
    CaravanBattleResult,
    CaravanParticipantOutcome,
    resolve_caravan_battle,
)
from pipirik_wars.domain.clan import IClanMembershipRepository
from pipirik_wars.domain.player import IPlayerRepository, Length, Title
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    AuditSource,
    IAuditLogger,
    IClock,
    IRandom,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class CaravanBattleFinished:
    """Результат :class:`FinishCaravanBattle`.

    Используется bot-handler-ом (Спринт 3.2-D) для рассылки итоговых
    карточек участникам и кланам.

    Поля:
    - `caravan` — финальное состояние (`status=FINISHED` или текущее,
      если `was_already_finished=True`).
    - `result` — `None`, если `was_already_finished=True` (повторный
      вызов на уже завершённом караване — handler сам должен
      проигнорировать). Иначе — полный исход боя
      (`raiders_won`, `participant_outcomes`, `clan_bonus_cm_*`).
    - `was_already_finished` — `True` при идемпотентном no-op-е.
    """

    caravan: Caravan
    result: CaravanBattleResult | None
    was_already_finished: bool


class FinishCaravanBattle:
    """Use-case «применить исход боя каравана и снять блокировки» (ГДД §9.5–§9.6)."""

    __slots__ = (
        "_audit",
        "_balance",
        "_caravan_participants",
        "_caravans",
        "_clan_memberships",
        "_clock",
        "_length_granter",
        "_locks",
        "_players",
        "_random_factory",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        caravans: ICaravanRepository,
        caravan_participants: ICaravanParticipantRepository,
        clan_memberships: IClanMembershipRepository,
        players: IPlayerRepository,
        length_granter: ILengthGranter,
        locks: ActivityLockService,
        audit: IAuditLogger,
        clock: IClock,
        balance: CaravansConfig,
        random_factory: Callable[[int], IRandom],
    ) -> None:
        self._uow = uow
        self._caravans = caravans
        self._caravan_participants = caravan_participants
        self._clan_memberships = clan_memberships
        self._players = players
        self._length_granter = length_granter
        self._locks = locks
        self._audit = audit
        self._clock = clock
        self._balance = balance
        self._random_factory = random_factory

    async def execute(
        self,
        input_dto: FinishCaravanBattleInput,
    ) -> CaravanBattleFinished:
        """Финиш боя каравана. См. docstring модуля для контракта."""
        async with self._uow:
            caravan = await self._caravans.get_by_id(caravan_id=input_dto.caravan_id)
            if caravan is None:
                raise CaravanNotFoundError(caravan_id=input_dto.caravan_id)
            assert caravan.id is not None

            if caravan.is_terminal:
                # Идемпотентный no-op: бой уже завершён (FINISHED) или
                # отменён (CANCELLED). Возвращаем текущее состояние,
                # ничего не пишем.
                return CaravanBattleFinished(
                    caravan=caravan,
                    result=None,
                    was_already_finished=True,
                )

            if not caravan.is_in_battle:
                # LOBBY → инвариант нарушен: job не должен был сработать.
                raise InvalidCaravanStateError(
                    caravan_id=caravan.id,
                    expected="IN_BATTLE",
                    actual=caravan.status.value,
                )

            now = self._clock.now()
            caravan_id: int = caravan.id

            participants = await self._caravan_participants.list_by_caravan(
                caravan_id=caravan_id,
            )

            # 1. Резолв боя (детерминистично от random_seed).
            random_source = self._random_factory(caravan.random_seed)
            result = resolve_caravan_battle(
                caravan=caravan,
                participants=participants,
                balance=self._balance,
                random=random_source,
            )

            # 2. Применяем per-player длины + Атаман-титул.
            total_granted_cm = 0
            total_revoked_cm = 0
            ataman_player_id: int | None = None
            for outcome in result.participant_outcomes:
                granted, revoked = await self._apply_participant_outcome(
                    outcome=outcome,
                    caravan_id=caravan_id,
                    now=now,
                )
                total_granted_cm += granted
                total_revoked_cm += revoked
                if outcome.gets_ataman_title:
                    ataman_player_id = outcome.participant.player_id

            # 3. Клан-бонус (только при доставке).
            clan_bonus_total_cm = 0
            if result.clan_bonus_cm_sender > 0:
                clan_bonus_total_cm += await self._apply_clan_bonus(
                    caravan_id=caravan_id,
                    clan_id=caravan.sender_clan_id,
                    side="sender",
                    delta_cm=result.clan_bonus_cm_sender,
                )
            if result.clan_bonus_cm_receiver > 0:
                clan_bonus_total_cm += await self._apply_clan_bonus(
                    caravan_id=caravan_id,
                    clan_id=caravan.receiver_clan_id,
                    side="receiver",
                    delta_cm=result.clan_bonus_cm_receiver,
                )

            # 4. Снимаем activity-lock-и всех участников (NO-OP, если
            # уже истёк/снят). Делаем после применения наград, чтобы
            # игрок не успел дёрнуть параллельный /forest или /caravan
            # до записи длин в БД.
            for participant in participants:
                await self._locks.release(
                    actor_kind="player",
                    actor_id=participant.player_id,
                )

            # 5. Финальный transition статуса.
            finished_caravan = await self._caravans.save(
                caravan.mark_finished(finished_at=now),
            )

            # 6. Audit-запись «бой завершён» + «награды выданы».
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.CARAVAN_BATTLE_FINISHED,
                    actor_id=None,
                    target_kind="caravan",
                    target_id=str(finished_caravan.id),
                    before={"status": caravan.status.value},
                    after={
                        "status": finished_caravan.status.value,
                        "raiders_won": result.raiders_won,
                        "participants": len(result.participant_outcomes),
                    },
                    reason="caravan_battle_finished",
                    idempotency_key=f"caravan_battle_finished:{finished_caravan.id}",
                    occurred_at=now,
                )
            )
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.CARAVAN_REWARDS_GRANTED,
                    actor_id=None,
                    target_kind="caravan",
                    target_id=str(finished_caravan.id),
                    before=None,
                    after={
                        "raiders_won": result.raiders_won,
                        "total_granted_cm": total_granted_cm,
                        "total_revoked_cm": total_revoked_cm,
                        "clan_bonus_total_cm": clan_bonus_total_cm,
                        "ataman_player_id": ataman_player_id,
                    },
                    reason="caravan_rewards_granted",
                    idempotency_key=f"caravan_rewards_granted:{finished_caravan.id}",
                    occurred_at=now,
                )
            )

        return CaravanBattleFinished(
            caravan=finished_caravan,
            result=result,
            was_already_finished=False,
        )

    # -------- helpers --------

    async def _apply_participant_outcome(
        self,
        *,
        outcome: CaravanParticipantOutcome,
        caravan_id: int,
        now: datetime,
    ) -> tuple[int, int]:
        """Применить per-player исход (длина + Атаман-титул).

        Возвращает `(granted_cm, revoked_cm)` — суммы прибавок
        и потерь (revoked — со знаком плюс, для агрегации в audit).
        """
        granted_cm = 0
        revoked_cm = 0
        delta_cm = outcome.length_delta_cm
        player_id = outcome.participant.player_id

        if delta_cm > 0:
            await self._length_granter.grant(
                player_id=player_id,
                delta_cm=delta_cm,
                source=AuditSource.CARAVAN_REWARD,
                reason=(
                    "caravan_ataman_bonus" if outcome.gets_ataman_title else "caravan_battle_reward"
                ),
                idempotency_key=(f"add_length:caravan_battle:{caravan_id}:{player_id}"),
            )
            granted_cm = delta_cm
        elif delta_cm < 0:
            revoked_cm = await self._revoke_length(
                player_id=player_id,
                delta_cm=delta_cm,
                caravan_id=caravan_id,
                now=now,
            )

        if outcome.gets_ataman_title:
            await self._grant_ataman_title(
                player_id=player_id,
                caravan_id=caravan_id,
                now=now,
            )

        return granted_cm, revoked_cm

    async def _revoke_length(
        self,
        *,
        player_id: int,
        delta_cm: int,
        caravan_id: int,
        now: datetime,
    ) -> int:
        """Списать длину игроку (defender/caravaneer погиб; рейдер потерял от блока).

        Возвращает абсолютную величину списания (для агрегации в audit).
        """
        assert delta_cm < 0

        player = await self._players.get_by_id(player_id=player_id)
        if player is None:
            raise PlayerNotFoundError(tg_id=player_id)
        new_cm = max(0, player.length.cm + delta_cm)
        new_length = Length(cm=new_cm)
        after = player.with_length(new_length, now=now)
        saved = await self._players.save(after)
        assert player.id is not None
        await self._audit.record(
            AuditEntry(
                action=AuditAction.LENGTH_REVOKE,
                actor_id=player.tg_id,
                target_kind="player",
                target_id=str(player.id),
                before={"length_cm": player.length.cm},
                after={"length_cm": saved.length.cm},
                reason="caravan_battle_loss",
                idempotency_key=(f"caravan_battle_loss_revoke:{caravan_id}:{player_id}"),
                occurred_at=now,
                source=AuditSource.CARAVAN_REWARD,
                delta_cm=delta_cm,
            )
        )
        return -delta_cm

    async def _grant_ataman_title(
        self,
        *,
        player_id: int,
        caravan_id: int,
        now: datetime,
    ) -> None:
        """Выдать `Title.ATAMAN` рейдеру-победителю.

        Идемпотентность: повторный вызов перезапишет тот же титул
        (`Player.with_title` — pure replace), audit-запись с тем же
        `idempotency_key` тоже идемпотентна.
        """
        player = await self._players.get_by_id(player_id=player_id)
        if player is None:
            raise PlayerNotFoundError(tg_id=player_id)
        before_title = player.title.value if player.title is not None else None
        with_ataman = player.with_title(Title.ATAMAN, now=now)
        saved = await self._players.save(with_ataman)
        assert player.id is not None
        await self._audit.record(
            AuditEntry(
                action=AuditAction.TITLE_GRANT,
                actor_id=player.tg_id,
                target_kind="player",
                target_id=str(player.id),
                before={"title": before_title},
                after={"title": saved.title.value if saved.title is not None else None},
                reason="caravan_ataman_title",
                idempotency_key=(f"caravan_battle_finished:title:{caravan_id}:{player_id}"),
                occurred_at=now,
            )
        )

    async def _apply_clan_bonus(
        self,
        *,
        caravan_id: int,
        clan_id: int,
        side: str,
        delta_cm: int,
    ) -> int:
        """Раздать `+delta_cm` каждому участнику клана (ГДД §9.6).

        Возвращает суммарную выданную дельту по клану.
        """
        assert delta_cm > 0
        members = await self._clan_memberships.list_by_clan(clan_id)
        total = 0
        for member in members:
            await self._length_granter.grant(
                player_id=member.player_id,
                delta_cm=delta_cm,
                source=AuditSource.CARAVAN_REWARD,
                reason="caravan_clan_bonus",
                idempotency_key=(
                    f"add_length:caravan_clan_bonus:{caravan_id}:{side}:{member.player_id}"
                ),
            )
            total += delta_cm
        return total


__all__ = [
    "CaravanBattleFinished",
    "FinishCaravanBattle",
]
