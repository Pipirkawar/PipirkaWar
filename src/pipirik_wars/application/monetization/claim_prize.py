"""Use-case ``ClaimPrize`` (Спринт 4.1-D + 4.1-E, ГДД §12.6.4–§12.6.5).

Выплата зарезервированного крипто-лота игроку:

1. Загрузить лот по ``lot_id``; убедиться что ``status == RESERVED``.
2. **Freeze-check** (E.10): если ``IPayoutFreezeRepository.get_state().is_frozen``
   → ``ClaimPrizePayoutsFrozenError`` (без попытки выплаты).
3. **Payout-limit-check** (E.10): ``IPayoutLimitChecker.check(...)``;
   ``OverLimit`` → ``ClaimPrizeOverLimitError``.
4. Загрузить кошелёк игрока; anti-fraud — ``wallet.address == recipient_address``.
5. Вызвать ``ITonPayoutAdapter.payout(...)`` — перевод на сеть TON/USDT.
6. Если ``actual_fee <= fee_buffer_native`` — ``RESERVED → CLAIMED`` + audit
   ``PRIZE_LOT_CLAIMED``.
7. Если ``actual_fee > fee_buffer_native`` — refund-в-пул: ``RESERVED → REFUNDED``
   + ``apply_increment(currency, +amount_native)`` + audit ``PRIZE_LOT_REFUNDED``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pipirik_wars.domain.monetization.entities import PrizeLot, PrizeLotStatus
from pipirik_wars.domain.monetization.errors import (
    ClaimPrizeOverLimitError,
    ClaimPrizePayoutsFrozenError,
    PrizeLotNotFoundError,
    PrizeLotStatusTransitionError,
    WalletNotLinkedError,
)
from pipirik_wars.domain.monetization.ports import (
    IPayoutFreezeRepository,
    IPayoutLimitChecker,
    IPrizeLotRepository,
    IPrizePoolRepository,
    ITonPayoutAdapter,
    IWalletRepository,
    PayoutResult,
)
from pipirik_wars.domain.monetization.value_objects import (
    PayoutLimitOverLimit,
)
from pipirik_wars.domain.shared.ports.audit import (
    AuditAction,
    AuditEntry,
    AuditSource,
    IAuditLogger,
)
from pipirik_wars.domain.shared.ports.clock import IClock

__all__ = [
    "ClaimPrize",
    "ClaimPrizeCommand",
    "ClaimPrizeResult",
]

_REASON_LOT_CLAIMED = "player claimed reserved crypto lot via ClaimPrize"
_REASON_LOT_REFUND_FEE = "actual fee exceeded fee buffer; lot returned to pool"


@dataclass(frozen=True, slots=True)
class ClaimPrizeCommand:
    """Команда use-case ``ClaimPrize``.

    * ``player_id`` — id игрока.
    * ``lot_id`` — id зарезервированного лота.
    * ``recipient_address`` — адрес кошелька для anti-fraud-сверки.
    """

    player_id: int
    lot_id: int
    recipient_address: str


@dataclass(frozen=True, slots=True)
class ClaimPrizeResult:
    """Результат use-case ``ClaimPrize``.

    * ``claimed`` — ``True`` если выплата прошла.
    * ``refunded`` — ``True`` если лот вернулся в пул (fee overflow).
    * ``payout`` — детали выплаты (``None`` при refund).
    * ``lot_id`` — id лота.
    """

    claimed: bool
    refunded: bool
    payout: PayoutResult | None
    lot_id: int


class ClaimPrize:
    """Use-case: выплата зарезервированного лота (ГДД §12.6.4–§12.6.5)."""

    __slots__ = (
        "_audit",
        "_clock",
        "_freeze_repo",
        "_limit_checker",
        "_lot_repo",
        "_payout_adapter",
        "_pool_repo",
        "_wallet_repo",
    )

    def __init__(
        self,
        *,
        prize_lot_repository: IPrizeLotRepository,
        prize_pool_repository: IPrizePoolRepository,
        wallet_repository: IWalletRepository,
        payout_adapter: ITonPayoutAdapter,
        audit_logger: IAuditLogger,
        clock: IClock,
        payout_freeze_repository: IPayoutFreezeRepository,
        payout_limit_checker: IPayoutLimitChecker,
    ) -> None:
        self._lot_repo = prize_lot_repository
        self._pool_repo = prize_pool_repository
        self._wallet_repo = wallet_repository
        self._payout_adapter = payout_adapter
        self._audit = audit_logger
        self._clock = clock
        self._freeze_repo = payout_freeze_repository
        self._limit_checker = payout_limit_checker

    async def execute(self, command: ClaimPrizeCommand) -> ClaimPrizeResult:
        """Выплатить или вернуть зарезервированный лот."""
        lot = await self._lot_repo.get_by_id(lot_id=command.lot_id)
        if lot is None:
            raise PrizeLotNotFoundError(lot_id=command.lot_id)
        if lot.status is not PrizeLotStatus.RESERVED:
            raise PrizeLotStatusTransitionError(
                lot_id=lot.id,
                from_status=lot.status,
                to_status=PrizeLotStatus.CLAIMED,
            )

        # E.10: freeze-check — замороженные выплаты → reject.
        freeze = await self._freeze_repo.get_state()
        if freeze.is_frozen:
            assert lot.id is not None
            assert freeze.reason is not None
            raise ClaimPrizePayoutsFrozenError(
                lot_id=lot.id,
                reason=freeze.reason,
            )

        # E.10: payout-limit-check — rolling-window-лимит пер игрок.
        now = self._clock.now()
        limit_result = await self._limit_checker.check(
            player_id=command.player_id,
            currency=lot.currency,
            amount_native=lot.amount_native,
            now=now,
        )
        if isinstance(limit_result, PayoutLimitOverLimit):
            assert lot.id is not None
            raise ClaimPrizeOverLimitError(
                lot_id=lot.id,
                player_id=command.player_id,
                retry_after=limit_result.retry_after,
                exceeded_by_native=limit_result.exceeded_by_native,
            )

        wallet = await self._wallet_repo.get_by_player_and_currency(
            player_id=command.player_id,
            currency=lot.currency,
        )
        if wallet is None:
            raise WalletNotLinkedError(
                player_id=command.player_id,
                currency=lot.currency,
            )
        if wallet.address != command.recipient_address:
            raise ValueError(
                f"ClaimPrize anti-fraud: recipient_address "
                f"{command.recipient_address!r} does not match linked wallet "
                f"{wallet.address!r} for player {command.player_id}",
            )

        payout_result = await self._payout_adapter.payout(
            currency=lot.currency,
            amount_native=lot.net_amount_native,
            recipient_address=command.recipient_address,
        )

        now = self._clock.now()

        if payout_result.actual_fee_native <= lot.fee_buffer_native.value:
            return await self._handle_claimed(command, lot, payout_result, now)
        return await self._handle_refund(command, lot, payout_result, now)

    async def _handle_claimed(
        self,
        command: ClaimPrizeCommand,
        lot: PrizeLot,
        payout_result: PayoutResult,
        now: datetime,
    ) -> ClaimPrizeResult:
        assert lot.id is not None

        await self._lot_repo.update_status(
            lot_id=lot.id,
            new_status=PrizeLotStatus.CLAIMED,
            claimed_at=now,
            winner_id=command.player_id,
        )
        await self._audit.record(
            AuditEntry(
                action=AuditAction.PRIZE_LOT_CLAIMED,
                actor_id=command.player_id,
                target_kind="prize_lot",
                target_id=f"{lot.id}:claimed",
                before=None,
                after={
                    "lot_id": lot.id,
                    "currency": lot.currency.value,
                    "amount_native": lot.amount_native,
                    "net_amount_native": lot.net_amount_native,
                    "actual_fee_native": payout_result.actual_fee_native,
                    "tx_hash": payout_result.tx_hash,
                    "recipient_address": command.recipient_address,
                    "player_id": command.player_id,
                },
                reason=_REASON_LOT_CLAIMED,
                idempotency_key=f"claim_prize:{lot.id}",
                occurred_at=now,
                source=AuditSource.PRIZE_LOT_CLAIMED,
            )
        )
        return ClaimPrizeResult(
            claimed=True,
            refunded=False,
            payout=payout_result,
            lot_id=lot.id,
        )

    async def _handle_refund(
        self,
        command: ClaimPrizeCommand,
        lot: PrizeLot,
        payout_result: PayoutResult,
        now: datetime,
    ) -> ClaimPrizeResult:
        assert lot.id is not None

        await self._lot_repo.update_status(
            lot_id=lot.id,
            new_status=PrizeLotStatus.REFUNDED,
        )
        pool_after = await self._pool_repo.apply_increment(
            currency=lot.currency,
            amount_native=lot.amount_native,
        )
        await self._audit.record(
            AuditEntry(
                action=AuditAction.PRIZE_LOT_REFUNDED,
                actor_id=command.player_id,
                target_kind="prize_lot",
                target_id=f"{lot.id}:refund",
                before=None,
                after={
                    "lot_id": lot.id,
                    "currency": lot.currency.value,
                    "amount_native": lot.amount_native,
                    "actual_fee_native": payout_result.actual_fee_native,
                    "fee_buffer_native": lot.fee_buffer_native.value,
                    "prev_status": "reserved",
                    "pool_after_native": pool_after.balance_for(lot.currency),
                    "reason": "fee_overflow",
                    "player_id": command.player_id,
                },
                reason=_REASON_LOT_REFUND_FEE,
                idempotency_key=f"claim_prize:{lot.id}:refund",
                occurred_at=now,
                source=AuditSource.PRIZE_LOT_REFUNDED,
            )
        )
        return ClaimPrizeResult(
            claimed=False,
            refunded=True,
            payout=None,
            lot_id=lot.id,
        )
