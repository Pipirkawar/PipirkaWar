"""Use-case `RegisterReferral` (Спринт 2.4.C, ГДД §13.1).

Создаёт реферальную связь между двумя игроками. Зовётся `/start`-handler-ом
**после** успешного `RegisterPlayer`, если в payload-е был `start=ref_<id>`.

Контракт:

1. **Self-referral** (`referrer_tg_id == referred_tg_id`) — `SelfReferralError`.
   Pydantic-DTO бьёт это раньше use-case-а; здесь ловим как defense-in-depth.
2. **Реферер не зарегистрирован** — `ReferrerNotRegisteredError`. Handler
   тихо игнорирует (нельзя стать реферером, не пройдя сам `RegisterPlayer`).
3. **Новичок ещё не существует** — `PlayerNotFoundError`. Use-case вызывается
   после `RegisterPlayer`, поэтому это сигнал бага в caller-е.
4. **Игрок уже был приглашён** (`UNIQUE` по `referred_id`) —
   `ReferralAlreadyExistsError`. Handler swallow-ит в no-op (re-delivery
   `/start` после повторного entry).
5. **Happy-path**: создаётся `Referral`, audit-запись (опц., через action
   `PLAYER_REGISTER`-style — но логика самого начисления длины —
   в `GrantReferralSignupBonus`).

Audit на этом шаге **не пишется** — собственно начисление длины
произойдёт в `GrantReferralSignupBonus` через `ILengthGranter.grant`,
который пишет audit `LENGTH_GRANT` с `source=REFERRAL_SIGNUP` автоматически.
Само создание реферальной записи — внутрисистемный факт, аудитируется
implicitly через `audit_log` начислений.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import RegisterReferralInput
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.referral import (
    IReferralRepository,
    Referral,
    ReferralAlreadyExistsError,
    ReferrerNotRegisteredError,
    SelfReferralError,
)
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork


@dataclass(frozen=True, slots=True)
class ReferralRegistered:
    """Результат успешной регистрации новой реферальной связи."""

    referral: Referral


@dataclass(frozen=True, slots=True)
class ReferralAlreadyRegistered:
    """Результат «игрок уже был рефнут ранее» — повторное `/start ref_<id>`.

    Handler swallow-ит в no-op: повторный entry с тем же `start=ref_<id>`
    после уже прошедшей регистрации не должен пересоздавать связь и не
    должен начислять бонусы. Содержит существующую запись для логирования.
    """

    referral: Referral


RegisterReferralResult = ReferralRegistered | ReferralAlreadyRegistered


class RegisterReferral:
    """Use-case создания реферальной связи (без начисления длины)."""

    __slots__ = (
        "_clock",
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
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._referrals = referrals
        self._clock = clock

    async def execute(self, input_dto: RegisterReferralInput) -> RegisterReferralResult:
        """Создать реферальную связь, либо вернуть существующую.

        Бросает:
        - `SelfReferralError` — если pydantic-DTO как-то пропустил
          `referrer_tg_id == referred_tg_id` (defense-in-depth);
        - `ReferrerNotRegisteredError` — реферер не в `users`;
        - `PlayerNotFoundError` — новичок не в `users` (баг в caller-е);
        - **не** бросает `ReferralAlreadyExistsError` — конвертируется
          в `ReferralAlreadyRegistered`.
        """
        if input_dto.referrer_tg_id == input_dto.referred_tg_id:
            raise SelfReferralError(player_id=input_dto.referrer_tg_id)

        async with self._uow:
            referrer = await self._players.get_by_tg_id(tg_id=input_dto.referrer_tg_id)
            if referrer is None:
                raise ReferrerNotRegisteredError(referrer_tg_id=input_dto.referrer_tg_id)
            referred = await self._players.get_by_tg_id(tg_id=input_dto.referred_tg_id)
            if referred is None:
                raise PlayerNotFoundError(tg_id=input_dto.referred_tg_id)

            assert referrer.id is not None, "Player from repo must have id"
            assert referred.id is not None, "Player from repo must have id"

            # Если игрока уже рефнул кто-то — возвращаем существующую запись.
            existing = await self._referrals.get_by_referred_id(referred_id=referred.id)
            if existing is not None:
                return ReferralAlreadyRegistered(referral=existing)

            now = self._clock.now()
            try:
                saved = await self._referrals.add(
                    Referral(
                        id=None,
                        referrer_id=referrer.id,
                        referred_id=referred.id,
                        created_at=now,
                    )
                )
            except ReferralAlreadyExistsError:
                # Race: между get_by_referred_id и add() кто-то успел
                # вставить запись. Перечитаем и вернём как existing.
                race_winner = await self._referrals.get_by_referred_id(referred_id=referred.id)
                assert race_winner is not None, "ReferralAlreadyExistsError implies row exists"
                return ReferralAlreadyRegistered(referral=race_winner)
            return ReferralRegistered(referral=saved)


__all__ = [
    "ReferralAlreadyRegistered",
    "ReferralRegistered",
    "RegisterReferral",
    "RegisterReferralResult",
]
