"""Use-case ``LinkWallet`` (Спринт 4.1-D, ГДД §12.6.4).

Привязка TON-кошелька игрока:

1. Verify TON Connect proof (``ITonConnectVerifier.verify``).
2. Upsert ``Wallet`` через ``IWalletRepository.add_or_replace``.
3. Audit-запись ``WALLET_LINKED``.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.monetization.entities import Wallet
from pipirik_wars.domain.monetization.errors import WalletAlreadyLinkedError
from pipirik_wars.domain.monetization.ports import (
    ITonConnectVerifier,
    IWalletRepository,
)
from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.domain.shared.ports.audit import (
    AuditAction,
    AuditEntry,
    AuditSource,
    IAuditLogger,
)
from pipirik_wars.domain.shared.ports.clock import IClock

__all__ = [
    "LinkWallet",
    "LinkWalletCommand",
    "LinkWalletResult",
]

_REASON_WALLET_LINKED = "player linked TON wallet via LinkWallet"


@dataclass(frozen=True, slots=True)
class LinkWalletCommand:
    """Команда use-case ``LinkWallet``.

    * ``player_id`` — id игрока.
    * ``address`` — TON-адрес кошелька (raw или user-friendly).
    * ``currency`` — ``TON_NANO`` или ``USDT_DECIMAL``.
    * ``proof`` — TON Connect proof для верификации.
    """

    player_id: int
    address: str
    currency: Currency
    proof: str


@dataclass(frozen=True, slots=True)
class LinkWalletResult:
    """Результат use-case ``LinkWallet``.

    * ``wallet`` — сохранённый ``Wallet``.
    * ``replaced`` — ``True`` если адрес был заменён (а не впервые привязан).
    """

    wallet: Wallet
    replaced: bool


class LinkWallet:
    """Use-case: привязка TON-кошелька (ГДД §12.6.4)."""

    __slots__ = ("_audit", "_clock", "_verifier", "_wallet_repo")

    def __init__(
        self,
        *,
        wallet_repository: IWalletRepository,
        ton_connect_verifier: ITonConnectVerifier,
        audit_logger: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._wallet_repo = wallet_repository
        self._verifier = ton_connect_verifier
        self._audit = audit_logger
        self._clock = clock

    async def execute(self, command: LinkWalletCommand) -> LinkWalletResult:
        """Привязать кошелёк."""
        is_valid = await self._verifier.verify(
            address=command.address,
            proof=command.proof,
        )
        if not is_valid:
            raise ValueError(
                f"LinkWallet: TON Connect proof verification failed "
                f"for address {command.address!r}",
            )

        existing = await self._wallet_repo.get_by_player_and_currency(
            player_id=command.player_id,
            currency=command.currency,
        )

        if existing is not None and existing.address == command.address:
            raise WalletAlreadyLinkedError(
                player_id=command.player_id,
                currency=command.currency,
                existing_address=existing.address,
            )

        now = self._clock.now()
        wallet = Wallet(
            player_id=command.player_id,
            address=command.address,
            currency=command.currency,
            linked_at=now,
        )

        saved = await self._wallet_repo.add_or_replace(wallet=wallet)

        replaced = existing is not None

        await self._audit.record(
            AuditEntry(
                action=AuditAction.WALLET_LINKED,
                actor_id=command.player_id,
                target_kind="wallet",
                target_id=f"{command.player_id}:{command.currency.value}",
                before=(
                    {"address": existing.address, "linked_at": existing.linked_at.isoformat()}
                    if existing is not None
                    else None
                ),
                after={
                    "address": saved.address,
                    "currency": saved.currency.value,
                    "player_id": saved.player_id,
                    "replaced": replaced,
                },
                reason=_REASON_WALLET_LINKED,
                idempotency_key=f"link_wallet:{command.player_id}:{command.currency.value}:{now.isoformat()}",
                occurred_at=now,
                source=AuditSource.WALLET_LINKED,
            )
        )

        return LinkWalletResult(wallet=saved, replaced=replaced)
