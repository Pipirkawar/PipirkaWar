"""Доменный пакет монетизации (ГДД §12.5–§12.6, Фаза 4 / Спринт 4.1).

Ре-экспорт публичных VO / сущностей / ошибок: импорт из соседних
доменных пакетов и application-слоя должен идти одной строкой:

    from pipirik_wars.domain.monetization import (
        Currency,
        IdempotencyConflictError,
        IdempotencyKey,
        Payment,
        PaymentStatus,
        PrizeLot,
        PrizeLotStatus,
        StarsAmount,
        Wallet,
    )

Это идентично конвенции `domain/roulette/__init__.py` (Спринт 3.5-A) и
`domain/oracle/__init__.py` (Спринт 3.6-A).
"""

from pipirik_wars.domain.monetization.entities import (
    Payment,
    PaymentStatus,
    PrizeLot,
    PrizeLotStatus,
    PrizePool,
    Wallet,
)
from pipirik_wars.domain.monetization.errors import (
    IdempotencyConflictError,
    InvalidStarsPayloadError,
    MonetizationDomainError,
    PrizeLotInvariantError,
    PrizeLotNotFoundError,
    PrizeLotStatusTransitionError,
    PrizePoolAmountInvariantError,
    WalletAlreadyLinkedError,
    WalletNotLinkedError,
)
from pipirik_wars.domain.monetization.ports import (
    IFeeEstimator,
    IPaymentLedger,
    IPrizeLotRepository,
    IPrizePoolRepository,
    ITgStarsPayloadVerifier,
    ITonConnectVerifier,
    ITonPayoutAdapter,
    IWalletRepository,
    PayoutResult,
)
from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    FeeBufferAmount,
    IdempotencyKey,
    StarsAmount,
    StarsPayload,
    StarsPoolBalance,
    TonAddress,
    TonNanoAmount,
    UsdtDecimalAmount,
    UsdtJettonAddress,
)

__all__ = [
    "Currency",
    "FeeBufferAmount",
    "IFeeEstimator",
    "IPaymentLedger",
    "IPrizeLotRepository",
    "IPrizePoolRepository",
    "ITgStarsPayloadVerifier",
    "ITonConnectVerifier",
    "ITonPayoutAdapter",
    "IWalletRepository",
    "IdempotencyConflictError",
    "IdempotencyKey",
    "InvalidStarsPayloadError",
    "MonetizationDomainError",
    "Payment",
    "PaymentStatus",
    "PayoutResult",
    "PrizeLot",
    "PrizeLotInvariantError",
    "PrizeLotNotFoundError",
    "PrizeLotStatus",
    "PrizeLotStatusTransitionError",
    "PrizePool",
    "PrizePoolAmountInvariantError",
    "StarsAmount",
    "StarsPayload",
    "StarsPoolBalance",
    "TonAddress",
    "TonNanoAmount",
    "UsdtDecimalAmount",
    "UsdtJettonAddress",
    "Wallet",
    "WalletAlreadyLinkedError",
    "WalletNotLinkedError",
]
