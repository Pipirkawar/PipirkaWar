"""Use-case `GrantReferralSignupBonus` (Спринт 2.4.C, ГДД §13.1).

Начисляет signup-бонус по уже-созданной реферальной связи:
- `+balance.referral.on_signup.newbie_bonus_cm` см → новичку;
- `+balance.referral.on_signup.referrer_bonus_cm` см → рефереру.

Зовётся `/start`-handler-ом сразу **после** `RegisterReferral`. Идемпотентен
по `Referral.signup_granted_at`: повторный вызов на уже-обработанной
записи бросает `SignupBonusAlreadyGrantedError` (handler swallow-ит в no-op).

Все начисления — через `ILengthGranter.grant`, который:
- пишет audit `LENGTH_GRANT` с `source=REFERRAL_SIGNUP` атомарно;
- проверяет anti-cheat soft-ban-гейт (если новичок забанен — обычно
  такой ситуации не бывает на свежей регистрации, но defense-in-depth);
- клампит дельту по hardcap-ам (organic-источник — REFERRAL_SIGNUP в whitelist);
- обеспечивает идемпотентность через `IIdempotencyKey`.

Транзакционная модель: всё внутри одного `async with self._uow:` —
если начисление рефереру упадёт после начисления новичку, **обе**
дельты откатятся, плюс не проставится `signup_granted_at`. Повтор
вызова по re-delivery подберёт всё с нуля.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import GrantReferralSignupBonusInput
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.referral import (
    IReferralRepository,
    Referral,
    SignupBonusAlreadyGrantedError,
)
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork
from pipirik_wars.domain.shared.ports.audit import AuditSource


@dataclass(frozen=True, slots=True)
class ReferralSignupBonusGranted:
    """Результат успешного начисления signup-бонуса по рефке."""

    referral: Referral
    newbie_bonus_cm: int
    referrer_bonus_cm: int


class GrantReferralSignupBonus:
    """Use-case начисления signup-бонуса по реферальной связи."""

    __slots__ = (
        "_balance",
        "_clock",
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
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._referrals = referrals
        self._length_granter = length_granter
        self._balance = balance
        self._clock = clock

    async def execute(self, input_dto: GrantReferralSignupBonusInput) -> ReferralSignupBonusGranted:
        """Начислить +newbie_cm новичку и +referrer_cm рефереру.

        Бросает:
        - `PlayerNotFoundError` — новичок не существует (баг в caller-е);
        - `ReferralNotFoundError`-style — у новичка нет реферальной записи;
          бросаем `KeyError` — caller отвечает за гарантию вызова после
          `RegisterReferral`. (handler не должен ловить — это programming
          error.)
        - `SignupBonusAlreadyGrantedError` — повторный вызов на уже-обработанной
          реферальной записи. Handler swallow-ит в no-op.
        - `AnticheatSoftBanError` (от `ILengthGranter.grant`) — крайне
          редко (новичок только что зарегистрирован), но возможно через
          backfill / админскую ручку.
        """
        cfg = self._balance.get().referral.on_signup

        async with self._uow:
            referred = await self._players.get_by_tg_id(tg_id=input_dto.referred_tg_id)
            if referred is None:
                raise PlayerNotFoundError(tg_id=input_dto.referred_tg_id)
            assert referred.id is not None

            referral = await self._referrals.get_by_referred_id(referred_id=referred.id)
            if referral is None:
                # Caller обязан был сначала позвать RegisterReferral — это баг.
                raise KeyError(f"Referral for referred_tg_id={input_dto.referred_tg_id} not found")
            if referral.signup_granted_at is not None:
                raise SignupBonusAlreadyGrantedError(referred_id=referred.id)

            # 1. Бонус новичку (+5 см дефолт).
            if cfg.newbie_bonus_cm > 0:
                await self._length_granter.grant(
                    player_id=referred.id,
                    delta_cm=cfg.newbie_bonus_cm,
                    source=AuditSource.REFERRAL_SIGNUP,
                    reason="referral_signup_newbie",
                    idempotency_key=f"add_length:referral:signup:newbie:{referred.id}",
                )
            # 2. Бонус рефереру (+1 см дефолт).
            if cfg.referrer_bonus_cm > 0:
                await self._length_granter.grant(
                    player_id=referral.referrer_id,
                    delta_cm=cfg.referrer_bonus_cm,
                    source=AuditSource.REFERRAL_SIGNUP,
                    reason="referral_signup_referrer",
                    idempotency_key=(
                        f"add_length:referral:signup:referrer:{referral.referrer_id}:{referred.id}"
                    ),
                )
            # 3. Маркируем запись «бонус выдан».
            now = self._clock.now()
            updated = await self._referrals.mark_signup_granted(
                referred_id=referred.id,
                granted_at=now,
            )

        return ReferralSignupBonusGranted(
            referral=updated,
            newbie_bonus_cm=cfg.newbie_bonus_cm,
            referrer_bonus_cm=cfg.referrer_bonus_cm,
        )


__all__ = [
    "GrantReferralSignupBonus",
    "ReferralSignupBonusGranted",
]
