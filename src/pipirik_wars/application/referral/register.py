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
5. **Реферер исчерпал лимит** (Спринт 2.4.F, антифрод) —
   `ReferralRateLimitedError`. Handler тихо игнорирует (новичок не должен
   видеть «лимит» — это не его проблема, и отсутствие feedback-а ломает
   скан-стратегию). Audit пишется до raise (action=REFERRAL_RATE_LIMITED).
6. **Happy-path**: создаётся `Referral` + audit-запись `REFERRAL_REGISTERED`
   (Спринт 2.4.F). Само начисление длины — в `GrantReferralSignupBonus`
   через `ILengthGranter.grant`, который пишет audit `LENGTH_GRANT` с
   `source=REFERRAL_SIGNUP` автоматически.
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
    ReferralRateLimitedError,
    ReferrerNotRegisteredError,
    SelfReferralError,
)
from pipirik_wars.domain.shared.ports import IClock, IRateLimiter, IUnitOfWork
from pipirik_wars.domain.shared.ports.audit import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
)

#: Префикс ключа для token-bucket-а реферального rate-limit-а (2.4.F).
RATE_LIMIT_KEY_PREFIX: str = "referral:"


def _rate_limit_key(referrer_tg_id: int) -> str:
    """Канонический ключ token-bucket-а для одного реферера."""
    return f"{RATE_LIMIT_KEY_PREFIX}{referrer_tg_id}"


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
        "_audit",
        "_clock",
        "_players",
        "_rate_limiter",
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
        rate_limiter: IRateLimiter,
        audit: IAuditLogger,
    ) -> None:
        self._uow = uow
        self._players = players
        self._referrals = referrals
        self._clock = clock
        self._rate_limiter = rate_limiter
        self._audit = audit

    async def execute(self, input_dto: RegisterReferralInput) -> RegisterReferralResult:
        """Создать реферальную связь, либо вернуть существующую.

        Бросает:
        - `SelfReferralError` — если pydantic-DTO как-то пропустил
          `referrer_tg_id == referred_tg_id` (defense-in-depth);
        - `ReferralRateLimitedError` — реферер исчерпал часовой лимит
          новых рефералов (Спринт 2.4.F, антифрод);
        - `ReferrerNotRegisteredError` — реферер не в `users`;
        - `PlayerNotFoundError` — новичок не в `users` (баг в caller-е);
        - **не** бросает `ReferralAlreadyExistsError` — конвертируется
          в `ReferralAlreadyRegistered`.
        """
        if input_dto.referrer_tg_id == input_dto.referred_tg_id:
            raise SelfReferralError(player_id=input_dto.referrer_tg_id)

        # Антифрод-защита: token-bucket по `referrer_tg_id` (Спринт 2.4.F).
        # Token-bucket — sync (in-memory), проверяем до открытия UoW.
        # Если реферер исчерпал лимит — пишем audit (в отдельной UoW-транзакции,
        # чтобы попытка зафиксировалась в логе даже при racing-conditions),
        # затем raise. Handler swallow-ит в no-op.
        rate_key = _rate_limit_key(input_dto.referrer_tg_id)
        if not self._rate_limiter.try_acquire(key=rate_key):
            await self._record_rate_limit_audit(
                referrer_tg_id=input_dto.referrer_tg_id,
                referred_tg_id=input_dto.referred_tg_id,
            )
            raise ReferralRateLimitedError(referrer_tg_id=input_dto.referrer_tg_id)

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

            assert saved.id is not None, "Saved referral must have id"
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.REFERRAL_REGISTERED,
                    actor_id=referrer.id,
                    target_kind="referral",
                    target_id=str(saved.id),
                    before=None,
                    after={
                        "referrer_id": referrer.id,
                        "referred_id": referred.id,
                    },
                    reason="referral_registered",
                    idempotency_key=f"referral_registered:{saved.id}",
                    occurred_at=now,
                )
            )
            return ReferralRegistered(referral=saved)

    async def _record_rate_limit_audit(
        self,
        *,
        referrer_tg_id: int,
        referred_tg_id: int,
    ) -> None:
        """Записать audit-попытку обхода rate-limit-а (Спринт 2.4.F).

        Открывает отдельную короткую UoW-транзакцию, чтобы попытка
        зафиксировалась независимо от исхода `execute`. Если запись
        не удалась (DB down) — пробрасываем ошибку, она должна быть
        видна на CI/мониторинге.
        """
        now = self._clock.now()
        async with self._uow:
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.REFERRAL_RATE_LIMITED,
                    actor_id=referrer_tg_id,
                    target_kind="referrer_tg_id",
                    target_id=str(referrer_tg_id),
                    before=None,
                    after={"referred_tg_id": referred_tg_id},
                    reason="referral_rate_limit_exceeded",
                    idempotency_key=None,
                    occurred_at=now,
                )
            )


__all__ = [
    "RATE_LIMIT_KEY_PREFIX",
    "ReferralAlreadyRegistered",
    "ReferralRegistered",
    "RegisterReferral",
    "RegisterReferralResult",
]
