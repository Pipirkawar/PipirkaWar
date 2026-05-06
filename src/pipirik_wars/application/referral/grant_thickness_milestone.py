"""Use-case `GrantReferralThicknessMilestone` (Спринт 2.4.C, ГДД §13.1).

Начисляет рефереру milestone-бонус за достижение приглашённым игроком
определённого уровня толщины. По дефолту:
- толщина 3 → +10 см рефереру;
- толщина 5 → +30 см рефереру.

Конфиг — `balance.referral.on_thickness_milestones` (отсортированы по
толщине, без дублей; гарантируется pydantic-валидатором).

Зовётся handler-ом `/upgrade_thickness` (Спринт 2.4.D) **после** успешного
апгрейда толщины. Использует `last_milestone_thickness` на `Referral`
для идемпотентности:
- если `new_thickness < milestone_thickness` — `MilestoneAlreadyGrantedError`
  (текущий уровень не достиг milestone-а);
- если `last_milestone_thickness >= milestone_thickness` —
  `MilestoneAlreadyGrantedError` (milestone уже выдавался ранее, в
  частности после понижения и повторного повышения толщины).

В одном вызове выдаём **только тот milestone, который точно совпал с
новым уровнем**. Если апгрейд прыгнул с 1 на 5, и 3, и 5 milestones
не выдавались, то их выдаст последовательность вызовов (use-case
зовётся на каждый успешный `upgrade_thickness`-инкремент).

Все начисления — через `ILengthGranter.grant`, который пишет audit
`LENGTH_GRANT` с `source=REFERRAL_THICKNESS` атомарно.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import GrantReferralThicknessMilestoneInput
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.referral import (
    IReferralRepository,
    MilestoneAlreadyGrantedError,
    Referral,
)
from pipirik_wars.domain.shared.ports import IUnitOfWork
from pipirik_wars.domain.shared.ports.audit import AuditSource


@dataclass(frozen=True, slots=True)
class ReferralMilestoneGranted:
    """Результат успешного начисления milestone-бонуса по рефке."""

    referral: Referral
    thickness: int
    referrer_bonus_cm: int


@dataclass(frozen=True, slots=True)
class ReferralMilestoneNotApplicable:
    """Результат «реферальной записи нет» — игрок не был рефнут.

    Handler swallow-ит в no-op без побочных эффектов: апгрейд толщины
    игроков-без-рефки не должен ничего никому начислять.
    """


GrantReferralThicknessMilestoneResult = ReferralMilestoneGranted | ReferralMilestoneNotApplicable


class GrantReferralThicknessMilestone:
    """Use-case начисления milestone-бонуса рефереру."""

    __slots__ = (
        "_balance",
        "_length_granter",
        "_players",
        "_referrals",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        referrals: IReferralRepository,
        length_granter: ILengthGranter,
        balance: IBalanceConfig,
    ) -> None:
        self._uow = uow
        self._players = players
        self._referrals = referrals
        self._length_granter = length_granter
        self._balance = balance

    async def execute(
        self, input_dto: GrantReferralThicknessMilestoneInput
    ) -> GrantReferralThicknessMilestoneResult:
        """Найти подходящий milestone и начислить рефереру бонус.

        Возвращает `ReferralMilestoneNotApplicable`, если:
        - игрок не был рефнут (нет записи в `referrals`);
        - в `balance.referral.on_thickness_milestones` нет milestone
          с `thickness == input.new_thickness_level`.

        Бросает:
        - `PlayerNotFoundError` — новичок не существует (баг в caller-е);
        - `MilestoneAlreadyGrantedError` — milestone этой толщины
          уже был выдан этому рефереру за этого приглашённого.
        """
        milestones = self._balance.get().referral.on_thickness_milestones
        # Ищем milestone, точно совпавший с новой толщиной.
        matching = next(
            (m for m in milestones if m.thickness == input_dto.new_thickness_level),
            None,
        )
        if matching is None:
            return ReferralMilestoneNotApplicable()

        async with self._uow:
            referred = await self._players.get_by_tg_id(tg_id=input_dto.referred_tg_id)
            if referred is None:
                raise PlayerNotFoundError(tg_id=input_dto.referred_tg_id)
            assert referred.id is not None

            referral = await self._referrals.get_by_referred_id(referred_id=referred.id)
            if referral is None:
                return ReferralMilestoneNotApplicable()

            if referral.last_milestone_thickness >= matching.thickness:
                raise MilestoneAlreadyGrantedError(
                    referred_id=referred.id,
                    thickness=matching.thickness,
                )

            if matching.referrer_bonus_cm > 0:
                await self._length_granter.grant(
                    player_id=referral.referrer_id,
                    delta_cm=matching.referrer_bonus_cm,
                    source=AuditSource.REFERRAL_THICKNESS,
                    reason=f"referral_thickness_milestone_{matching.thickness}",
                    idempotency_key=(
                        f"add_length:referral:thickness:{matching.thickness}:"
                        f"{referral.referrer_id}:{referred.id}"
                    ),
                )
            updated = await self._referrals.mark_milestone_granted(
                referred_id=referred.id,
                thickness=matching.thickness,
            )

        return ReferralMilestoneGranted(
            referral=updated,
            thickness=matching.thickness,
            referrer_bonus_cm=matching.referrer_bonus_cm,
        )


__all__ = [
    "GrantReferralThicknessMilestone",
    "GrantReferralThicknessMilestoneResult",
    "ReferralMilestoneGranted",
    "ReferralMilestoneNotApplicable",
]
