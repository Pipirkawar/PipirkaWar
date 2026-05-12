"""Infrastructure-имплементации `ITonConnectVerifier` (Спринт 4.1-D, шаг D.10.c).

Производственный путь верификации TON Connect-proof-а (ED25519-подпись
TON-Connect-сообщения через wallet-app) подключается в Спринте 4.1-E
(см. `docs/development_plan.md` §7 Спринт 4.1.2 — TON Connect).

Сейчас (D.10.c) `LinkWallet`-use-case пробрасывается в composition root
со stub-верификатором `SandboxTonConnectVerifier`, который:

* В **sandbox** (`is_sandbox=True`) — принимает любой non-empty `proof`.
  Это позволяет вручную тестировать handler-flow `/link_wallet_confirm`
  в testnet-окружении (4.1-D MVP).
* В **mainnet** (`is_sandbox=False`) — отвергает все proof-ы (fail-closed).
  Это безопасный дефолт, пока реальная верификация не подключена.

Когда D.10.c+ закроется и появится `TonConnectHttpVerifier` (D.10.e+ или
4.1-E), `build_container` переключится на production-реализацию.
"""

from __future__ import annotations

import structlog

from pipirik_wars.infrastructure.payments.ton_connect.canonical_message import (
    build_canonical_message,
)
from pipirik_wars.infrastructure.payments.ton_connect.in_memory_nonce_store import (
    InMemoryNonceStore,
)
from pipirik_wars.infrastructure.payments.ton_connect.production import (
    TonConnectProductionConfig,
    TonConnectProductionVerifier,
)
from pipirik_wars.infrastructure.payments.ton_connect.proof_parser import parse_ton_proof

__all__ = [
    "InMemoryNonceStore",
    "SandboxTonConnectVerifier",
    "TonConnectProductionConfig",
    "TonConnectProductionVerifier",
    "build_canonical_message",
    "parse_ton_proof",
]

_logger = structlog.get_logger(__name__)


class SandboxTonConnectVerifier:
    """Stub-имплементация `ITonConnectVerifier` для sandbox/testnet (D.10.c).

    Семантика:
    * `is_sandbox=True` — принимает любой non-empty `proof` (manual entry,
      Спринт 4.1-D MVP).
    * `is_sandbox=False` — отвергает любой `proof` (fail-closed).

    Когда подключится `TonConnectHttpVerifier` (4.1-E), composition root
    переключится на production-имплементацию. Этот класс остаётся
    в `infrastructure/payments/ton_connect/` только как fixture для тестов.
    """

    def __init__(self, *, is_sandbox: bool) -> None:
        """DI-конструктор.

        Параметры:
            is_sandbox: режим работы. `True` — testnet/manual-entry;
                `False` — mainnet (fail-closed).
        """
        self._is_sandbox = is_sandbox

    async def verify(self, *, address: str, proof: str) -> bool:
        """Проверить proof. См. docstring класса.

        В mainnet-режиме (fail-closed) — пишет WARNING-лог, чтобы
        оператор видел отказы и понимал, что нужно подключить
        реальный верификатор.
        """
        if not self._is_sandbox:
            _logger.warning(
                "ton_connect_verifier.sandbox_stub_rejects_in_mainnet",
                address_prefix=address[:8] if address else "",
                proof_len=len(proof),
                reason="real_verifier_not_wired_yet",
            )
            return False
        if not proof:
            return False
        _logger.info(
            "ton_connect_verifier.sandbox_stub_accepts",
            address_prefix=address[:8] if address else "",
            proof_len=len(proof),
        )
        return True
