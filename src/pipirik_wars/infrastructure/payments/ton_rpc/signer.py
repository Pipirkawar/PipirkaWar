"""Ed25519-подпись TON-message-ей (Спринт 4.1-D, шаг D.10.b-1).

Контракт + production-имплементация Ed25519-сигнера, используемого
``TonRpcAdapter``-ом в D.10.b-3 для подписи signed-BOC-ов (TEP-67
internal_message wallet-v3R2 wrapping + TEP-74 jetton-transfer-body).

Архитектура:

* ``ITonMessageSigner`` — Protocol-порт. Тонкий: одна операция
  ``sign(message)`` поверх Ed25519 + чтение ``public_key``. Никакого
  знания о Cell / BoC / TEP-67 — это исключительно криптографический
  примитив. Caller (``TonRpcAdapter``) сам строит сообщение для
  подписи (стандартно — 32-байтовый ``Cell.repr_hash`` от inner-Cell-а)
  и вкладывает 64-байтовую signature в начало финальной ячейки.

* ``Ed25519MessageSigner`` — единственная production-имплементация
  поверх ``nacl.signing.SigningKey`` из PyNaCl (libsodium-backend,
  constant-time, аудированный код). Хранит signing-key в RAM
  (``__slots__``), `__repr__` маскирует материал ключа.

Тесты подсовывают `Ed25519MessageSigner` с детерминированным seed-ом
(``test_signer.py``); в D.10.b-3 будет использоваться тот же подход
для golden-BOC-тестов adapter-а.

Безопасность:

* Seed-ы — 32 байта. ``Ed25519MessageSigner`` принимает их как
  ``bytes``; caller (composition-root, D.10.c) **обязан** загрузить
  seed из ``SecretStr``-env-переменной, никогда не из git-tracked
  файла. ``TonRpcSettings`` в D.10.c расширится полем
  ``payout_wallet_signing_key_seed: SecretStr`` (fail-closed — пустой
  seed запрещён для production-mode-а).
* ``Ed25519MessageSigner.__slots__`` запрещает добавление новых
  атрибутов (защита от accidental-mixin-загрязнения signer-объекта).
* ``__repr__`` маскирует signing-key + публикует только public-key
  base16, чтобы случайный ``logger.info(signer)`` не утёк seed.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import nacl.signing

__all__ = [
    "Ed25519MessageSigner",
    "ITonMessageSigner",
]


# Ed25519: seed — 32 байта, public-key — 32 байта, signature — 64 байта.
# Константы выведены наружу, чтобы тесты валидировали границы без
# импорта внутренностей PyNaCl.
_ED25519_SEED_BYTES = 32
_ED25519_PUBLIC_KEY_BYTES = 32
_ED25519_SIGNATURE_BYTES = 64


@runtime_checkable
class ITonMessageSigner(Protocol):
    """Тонкий порт Ed25519-подписи TON-message-bytes (Спринт 4.1-D, D.10.b).

    Реализация — ``Ed25519MessageSigner`` (поверх PyNaCl). Тесты могут
    использовать её же с детерминированным seed-ом или подменять
    через Protocol-conformance.

    Все методы — синхронные: Ed25519-подпись детерминирована и не
    делает I/O, поэтому ``async``-обёртка избыточна. ``TonRpcAdapter``
    зовёт ``sign(...)`` строго после сборки inner-Cell-а; стоимость
    одного ``sign(...)`` ≈ десятки микросекунд.
    """

    @property
    def public_key(self) -> bytes:
        """Публичный Ed25519-ключ (ровно 32 байта).

        Используется caller-ом (``TonRpcAdapter`` D.10.b-3) для:
        * вывода wallet-address-а (wallet-v3R2: ``state_init.hash(public_key
          + wallet_id + seqno=0)`` → ``MsgAddressInt(workchain=0, hash)``);
        * валидации, что seed соответствует hot-wallet-у, на котором
          хранятся призовые средства (sanity-check в composition root).
        """
        ...

    def sign(self, *, message: bytes) -> bytes:
        """Подписать ``message`` 32-байтовым Ed25519-secret-key-ом.

        Параметры:
        * ``message: bytes`` — произвольной длины байтовая последовательность.
          В TON-контексте — это 32-байтовый ``Cell.repr_hash`` от
          inner-message-cell-а. Реализации **не** обязаны валидировать
          длину; caller сам отвечает за корректный digest.

        Возвращает: 64-байтовый Ed25519-signature.
        """
        ...


class Ed25519MessageSigner:
    """Production Ed25519-сигнер поверх ``nacl.signing.SigningKey``.

    PyNaCl — Python-binding для libsodium; ``SigningKey``-операции
    constant-time + аудированный код. Seed хранится только в
    ``_signing_key`` (приватный slot); ``__repr__`` маскирует.

    Использование (тесты / production):

    >>> seed = b"\\x00" * 32  # доpkaйте через SecretStr-env
    >>> signer = Ed25519MessageSigner(signing_key_seed=seed)
    >>> public = signer.public_key  # 32 байта
    >>> sig = signer.sign(message=b"\\x00" * 32)  # 64 байта

    В production seed загружается из ``TonRpcSettings.payout_wallet_signing_key_seed``
    (расширим в D.10.c) или прокидывается извне.

    Безопасность: не логируйте instance целиком — `__repr__` уже
    маскирует, но не отдавайте signer наружу через DI больше, чем
    нужно (используйте один экземпляр на `TonRpcAdapter`).
    """

    __slots__ = ("_signing_key",)

    def __init__(self, *, signing_key_seed: bytes | bytearray) -> None:
        """Создать сигнер из 32-байтового Ed25519-seed-а.

        Поднимает ``ValueError`` при невалидной длине seed-а.
        """
        if not isinstance(signing_key_seed, bytes | bytearray):
            raise TypeError(
                "Ed25519MessageSigner.signing_key_seed must be bytes, "
                f"got {type(signing_key_seed).__name__}",
            )
        if len(signing_key_seed) != _ED25519_SEED_BYTES:
            raise ValueError(
                "Ed25519MessageSigner.signing_key_seed must be exactly "
                f"{_ED25519_SEED_BYTES} bytes (Ed25519 seed); got {len(signing_key_seed)}.",
            )
        self._signing_key = nacl.signing.SigningKey(bytes(signing_key_seed))

    @property
    def public_key(self) -> bytes:
        """Публичный Ed25519-ключ (32 байта). Безопасно логировать."""
        return bytes(self._signing_key.verify_key)

    def sign(self, *, message: bytes | bytearray) -> bytes:
        """Подписать ``message`` Ed25519-private-key-ом; вернуть 64-байтовую signature.

        Поднимает ``TypeError`` если ``message`` не bytes.
        """
        if not isinstance(message, bytes | bytearray):
            raise TypeError(
                "Ed25519MessageSigner.sign(message=): bytes-like required, "
                f"got {type(message).__name__}",
            )
        signed = self._signing_key.sign(bytes(message))
        return signed.signature

    def __repr__(self) -> str:
        # Маскируем seed; раскрываем только public-key, чтобы видеть
        # привязку signer-а к hot-wallet-у при дебаге.
        return (
            f"Ed25519MessageSigner(public_key={self.public_key.hex()}, "
            f"signing_key_seed=<redacted {_ED25519_SEED_BYTES}-bytes>)"
        )
