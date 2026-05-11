"""TON RPC infrastructure adapters (Спринт 4.1-D, шаг D.5).

Реализации портов `ITonPayoutAdapter` / `IFeeEstimator` поверх TON-RPC,
плюс jetton-USDT-провайдер для резолва кошелька получателя по
jetton-master-у. Внутри используется абстракция `ITonRpcClient` —
тонкая HTTP-обёртка над TON-RPC (toncenter / tonapi / собственный node).
Реальная HTTP-имплементация (`AiohttpTonRpcClient` или аналог) — на
шаг **D.10** (composition root); до того момента в проде остаётся
`InMemoryFeeEstimator` (4.1-C), а тесты D.5 — на `FakeTonRpcClient`
(см. `tests/unit/infrastructure/payments/ton_rpc/_fakes.py`).

Логически разнесено по подмодулям:

* `client` — `ITonRpcClient`-протокол + DTO результата вызова (`RecentFee`).
* `errors` — иерархия исключений infra-слоя (`TonRpcCallError`,
  `TonRpcTimeoutError`, `JettonResolutionError`,
  `UnsupportedPayoutCurrencyError`).
* `settings` — `TonRpcSettings` (`pydantic-settings`, prefix `TON_RPC_`),
  читается из env / `.env`; включает sandbox-флаг, jetton-master USDT,
  окно P95-оценки в днях, timeout-ы.
* `jetton` — `JettonUsdtProvider` (`get_wallet_address` + сборка
  jetton-`transfer`-payload-а).
* `fee_estimator` — `TonRpcFeeEstimator` (`IFeeEstimator`) — P95
  газа за `fee_window_days` дней через `client.recent_fees(...)`.
* `adapter` — `TonRpcAdapter` (`ITonPayoutAdapter`) — отправляет TON
  / USDT-jetton-перевод и возвращает `PayoutResult` с фактической
  комиссией.
"""

from pipirik_wars.infrastructure.payments.ton_rpc.adapter import TonRpcAdapter
from pipirik_wars.infrastructure.payments.ton_rpc.client import (
    ITonRpcClient,
    RecentFee,
)
from pipirik_wars.infrastructure.payments.ton_rpc.errors import (
    JettonResolutionError,
    TonRpcCallError,
    TonRpcTimeoutError,
    UnsupportedPayoutCurrencyError,
)
from pipirik_wars.infrastructure.payments.ton_rpc.fee_estimator import (
    TonRpcFeeEstimator,
)
from pipirik_wars.infrastructure.payments.ton_rpc.http_client import TonRpcHttpClient
from pipirik_wars.infrastructure.payments.ton_rpc.jetton import (
    JettonTransferPayload,
    JettonUsdtProvider,
)
from pipirik_wars.infrastructure.payments.ton_rpc.settings import TonRpcSettings
from pipirik_wars.infrastructure.payments.ton_rpc.signer import (
    Ed25519MessageSigner,
    ITonMessageSigner,
)

__all__ = [
    "Ed25519MessageSigner",
    "ITonMessageSigner",
    "ITonRpcClient",
    "JettonResolutionError",
    "JettonTransferPayload",
    "JettonUsdtProvider",
    "RecentFee",
    "TonRpcAdapter",
    "TonRpcCallError",
    "TonRpcFeeEstimator",
    "TonRpcHttpClient",
    "TonRpcSettings",
    "TonRpcTimeoutError",
    "UnsupportedPayoutCurrencyError",
]
