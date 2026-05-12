"""TON Connect 2.0 production-верификатор (Спринт 4.1-F, шаг F.5.c).

`TonConnectProductionVerifier` — реализация `ITonConnectVerifier`,
которая на mainnet/testnet делает реальную Ed25519-верификацию TON
Connect 2.0 ``ton_proof``-а кошелька.

Пайплайн `verify(*, address, proof) -> bool`:

1. **Parse** — `parse_ton_proof(raw=proof)` (F.5.a) → `TonProof`-VO.
   `TonProofMalformedError` → `False` + WARNING(`reason="malformed"`).
2. **Address-match** — `proof.address == address` (точная строка,
   raw-формат ``workchain:hex64``). False → `False` + WARNING(
   `reason="address_mismatch"`).
3. **Timestamp-window** — `now - max_age <= proof.timestamp <=
   now + clock_skew` (Unix seconds, UTC). Out-of-window → `False`
   + WARNING(`reason="expired"` или `"future"`).
4. **Domain-whitelist** — `proof.domain_value in allowed_domains`.
   Не whitelist-ed → `False` + WARNING(`reason="domain_not_allowed"`).
5. **Canonical-message** — `build_canonical_message(proof)` (F.5.b)
   → 32-byte hash.
6. **Ed25519-verify** — `nacl.signing.VerifyKey(pub_key_bytes).
   verify(canonical, signature_bytes)`. `BadSignatureError` → `False`
   + WARNING(`reason="signature_invalid"`). Любое другое исключение
   тоже логируется и возвращает `False` (fail-closed).

При успехе — `True` + INFO-log (без sensitive-данных).

Sensitive-данные (signature, payload, public_key_hex) **не** попадают
в WARNING-сообщения целиком; в лог уходит только короткий `reason`
+ безопасные context-поля (address-prefix, proof_len, domain-prefix,
timestamp-сравнение).

**Сознательный пропуск (4.1-G backlog):** address-from-pubkey-recovery
(TON wallet contract `state_init → hash`). Проверка `proof.public_key`
↔ `proof.address` сейчас не делается напрямую — Ed25519-signature
гарантирует, что подписавший владеет приватным ключом к pub-key, и
address-есть-в-canonical-message → подпись не сойдётся, если address
не тот. Но дополнительный layer "address восстанавливается из pubkey
по wallet-contract-у" — backlog 4.1-G.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Final

import nacl.exceptions
import nacl.signing
import structlog

from pipirik_wars.domain.monetization.errors import TonProofMalformedError
from pipirik_wars.domain.shared.ports.clock import IClock
from pipirik_wars.infrastructure.payments.ton_connect.canonical_message import (
    build_canonical_message,
)
from pipirik_wars.infrastructure.payments.ton_connect.proof_parser import (
    parse_ton_proof,
)

__all__ = ["TonConnectProductionConfig", "TonConnectProductionVerifier"]

_logger = structlog.get_logger(__name__)

# Машино-читаемые `reason`-коды (стабильные для лога/метрик).
_REASON_MALFORMED: Final = "malformed"
_REASON_ADDRESS_MISMATCH: Final = "address_mismatch"
_REASON_EXPIRED: Final = "expired"
_REASON_FUTURE: Final = "future"
_REASON_DOMAIN_NOT_ALLOWED: Final = "domain_not_allowed"
_REASON_SIGNATURE_INVALID: Final = "signature_invalid"
_REASON_INTERNAL: Final = "internal_error"


@dataclass(frozen=True, slots=True)
class TonConnectProductionConfig:
    """Конфигурация `TonConnectProductionVerifier` (F.5.c, F.7).

    Поля:
        allowed_domains: whitelist доменов, на которые мы принимаем
            TON Connect-proof-ы. Пример: ``("pipirik.example.com",)``.
            Если ``proof.domain_value`` не равен ни одному элементу —
            verify возвращает False (защита от phishing-replay).
        max_age_seconds: лимит «давности» подписи. Если ``proof.
            timestamp < now - max_age_seconds`` → expired. Дефолт-
            рекомендация: 600 (10 минут) — достаточно для wallet-app-а.
        clock_skew_seconds: допуск на расхождение часов клиента в
            будущее. Если ``proof.timestamp > now + clock_skew_seconds``
            → "future" (отвергается). Дефолт-рекомендация: 60.

    Инварианты:
        * ``allowed_domains`` непустой.
        * ``max_age_seconds > 0``, ``clock_skew_seconds >= 0`` (оба `int`).
    """

    allowed_domains: tuple[str, ...]
    max_age_seconds: int
    clock_skew_seconds: int

    def __post_init__(self) -> None:
        if not self.allowed_domains:
            raise ValueError(
                "TonConnectProductionConfig.allowed_domains must be non-empty",
            )
        for d in self.allowed_domains:
            if not isinstance(d, str) or not d:
                raise ValueError(
                    "TonConnectProductionConfig.allowed_domains entries must be "
                    f"non-empty strings, got {d!r}",
                )
        if not isinstance(self.max_age_seconds, int) or isinstance(self.max_age_seconds, bool):
            raise TypeError(
                "TonConnectProductionConfig.max_age_seconds must be int, got "
                f"{type(self.max_age_seconds).__name__}",
            )
        if self.max_age_seconds <= 0:
            raise ValueError(
                "TonConnectProductionConfig.max_age_seconds must be > 0, got "
                f"{self.max_age_seconds}",
            )
        if not isinstance(self.clock_skew_seconds, int) or isinstance(
            self.clock_skew_seconds, bool
        ):
            raise TypeError(
                "TonConnectProductionConfig.clock_skew_seconds must be int, got "
                f"{type(self.clock_skew_seconds).__name__}",
            )
        if self.clock_skew_seconds < 0:
            raise ValueError(
                "TonConnectProductionConfig.clock_skew_seconds must be >= 0, got "
                f"{self.clock_skew_seconds}",
            )


class TonConnectProductionVerifier:
    """Производственная имплементация `ITonConnectVerifier` (F.5.c).

    Делает реальную Ed25519-верификацию TON Connect 2.0 ``ton_proof``-а.
    См. module-docstring для полного пайплайна.
    """

    __slots__ = ("_clock", "_config")

    def __init__(
        self,
        *,
        config: TonConnectProductionConfig,
        clock: IClock,
    ) -> None:
        self._config = config
        self._clock = clock

    async def verify(self, *, address: str, proof: str) -> bool:  # noqa: PLR0911 — линейные fail-paths
        """См. `ITonConnectVerifier.verify`."""
        # 1. Parse JSON → TonProof VO.
        try:
            parsed = parse_ton_proof(proof)
        except TonProofMalformedError as exc:
            _logger.warning(
                "ton_connect_verifier.production.rejected",
                reason=_REASON_MALFORMED,
                malformed_reason=exc.reason,
                raw_len=exc.raw_len,
                address_prefix=address[:8] if address else "",
            )
            return False

        # 2. Address-match (точная строка, raw-формат).
        if parsed.address != address:
            _logger.warning(
                "ton_connect_verifier.production.rejected",
                reason=_REASON_ADDRESS_MISMATCH,
                expected_prefix=address[:8] if address else "",
                actual_prefix=parsed.address[:8] if parsed.address else "",
            )
            return False

        # 3. Timestamp window.
        now_ts = int(self._clock.now().timestamp())
        if parsed.timestamp < now_ts - self._config.max_age_seconds:
            _logger.warning(
                "ton_connect_verifier.production.rejected",
                reason=_REASON_EXPIRED,
                proof_timestamp=parsed.timestamp,
                now_timestamp=now_ts,
                max_age_seconds=self._config.max_age_seconds,
            )
            return False
        if parsed.timestamp > now_ts + self._config.clock_skew_seconds:
            _logger.warning(
                "ton_connect_verifier.production.rejected",
                reason=_REASON_FUTURE,
                proof_timestamp=parsed.timestamp,
                now_timestamp=now_ts,
                clock_skew_seconds=self._config.clock_skew_seconds,
            )
            return False

        # 4. Domain whitelist.
        if parsed.domain_value not in self._config.allowed_domains:
            _logger.warning(
                "ton_connect_verifier.production.rejected",
                reason=_REASON_DOMAIN_NOT_ALLOWED,
                actual_domain=parsed.domain_value,
                allowed_count=len(self._config.allowed_domains),
            )
            return False

        # 5. Canonical-message + 6. Ed25519-verify.
        try:
            canonical = build_canonical_message(parsed)
            pub_key_bytes = bytes.fromhex(parsed.public_key_hex)
            signature_bytes = base64.b64decode(parsed.signature_b64, validate=True)
            nacl.signing.VerifyKey(pub_key_bytes).verify(canonical, signature_bytes)
        except nacl.exceptions.BadSignatureError:
            _logger.warning(
                "ton_connect_verifier.production.rejected",
                reason=_REASON_SIGNATURE_INVALID,
                pubkey_prefix=parsed.public_key_hex[:8],
                address_prefix=parsed.address[:8],
            )
            return False
        except (ValueError, binascii.Error) as exc:
            # Эти ошибки означают, что VO-инварианты не сошлись с реальностью
            # (e.g. base64-decode упал на signature_b64). VO-проверки должны
            # были это поймать — но если нет, fail-closed.
            _logger.warning(
                "ton_connect_verifier.production.rejected",
                reason=_REASON_INTERNAL,
                error_type=type(exc).__name__,
                address_prefix=parsed.address[:8],
            )
            return False

        _logger.info(
            "ton_connect_verifier.production.accepted",
            address_prefix=parsed.address[:8],
            domain=parsed.domain_value,
            proof_timestamp=parsed.timestamp,
            now_timestamp=now_ts,
        )
        return True
