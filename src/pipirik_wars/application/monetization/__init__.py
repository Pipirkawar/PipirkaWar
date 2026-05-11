"""Application-слой монетизации (ГДД §12.5–§12.6, Фаза 4 / Спринт 4.1).

Use-case-ы и DTO-комманды для платных операций. Re-export публичных
символов:

    from pipirik_wars.application.monetization import (
        ClaimPrize,
        ClaimPrizeCommand,
        ClaimPrizeResult,
        GeneratePrizeLots,
        GeneratePrizeLotsCommand,
        GeneratePrizeLotsResult,
        PaidRoulettePack,
        RecordDonation,
        RecordDonationCommand,
        RecordDonationResult,
        SpinPaidRoulette,
        SpinPaidRouletteCommand,
        SpinPaidRouletteResult,
    )
"""

from pipirik_wars.application.monetization.claim_prize import (
    ClaimPrize,
    ClaimPrizeCommand,
    ClaimPrizeResult,
)
from pipirik_wars.application.monetization.generate_prize_lots import (
    GeneratePrizeLots,
    GeneratePrizeLotsCommand,
    GeneratePrizeLotsResult,
)
from pipirik_wars.application.monetization.link_wallet import (
    LinkWallet,
    LinkWalletCommand,
    LinkWalletResult,
)
from pipirik_wars.application.monetization.record_donation import (
    RecordDonation,
    RecordDonationCommand,
    RecordDonationResult,
)
from pipirik_wars.application.monetization.spin_paid_roulette import (
    PaidRoulettePack,
    SpinPaidRoulette,
    SpinPaidRouletteCommand,
    SpinPaidRouletteResult,
)

__all__ = [
    "ClaimPrize",
    "ClaimPrizeCommand",
    "ClaimPrizeResult",
    "GeneratePrizeLots",
    "GeneratePrizeLotsCommand",
    "GeneratePrizeLotsResult",
    "LinkWallet",
    "LinkWalletCommand",
    "LinkWalletResult",
    "PaidRoulettePack",
    "RecordDonation",
    "RecordDonationCommand",
    "RecordDonationResult",
    "SpinPaidRoulette",
    "SpinPaidRouletteCommand",
    "SpinPaidRouletteResult",
]
