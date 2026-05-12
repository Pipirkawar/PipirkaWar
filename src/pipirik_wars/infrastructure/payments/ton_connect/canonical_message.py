"""TON Connect 2.0 canonical-message-builder (Спринт 4.1-F, шаг F.5.b).

`build_canonical_message(proof: TonProof) -> bytes` — детерминированная
функция, превращающая распарсенный `TonProof`-VO в 32-байтовый
canonical-message-hash, который и подписан Ed25519-ключом кошелька.

Спека: https://docs.ton.org/develop/dapps/ton-connect/sign#message-scheme

Алгоритм:

::

    message = b"ton-proof-item-v2/"
        + workchain (int32 BE)
        + address_hash (32 bytes)
        + domain_length (uint32 LE)
        + domain_value_utf8_bytes
        + timestamp (uint64 LE)
        + payload_utf8_bytes

    inner_hash = sha256(message)             # 32 bytes
    prefix = b"\\xff\\xff" + b"ton-connect"  # 2 + 11 = 13 bytes
    canonical = sha256(prefix + inner_hash)  # 32 bytes

Подпись (`proof.signature_b64` после base64-decode, 64 bytes) — это
``Ed25519Sign(secret_key, canonical)``. Верификатор (F.5.c) вызывает
``VerifyKey(pub_key).verify(canonical, signature)``.

Функция pure-CPU (никаких I/O), детерминирована, безопасна для вызова
из любого контекста. Любая внутренняя ошибка (битый address-формат —
такой не должен достигнуть нас, потому что `TonProof.__post_init__`
уже проверил инвариант) — `ValueError` (контрактно не должно случаться,
но в коде есть guard).
"""

from __future__ import annotations

import hashlib
from typing import Final

from pipirik_wars.domain.monetization.value_objects import TonProof

__all__ = ["build_canonical_message"]

# Префиксы из спеки — fixed.
_SCHEMA_PREFIX: Final = b"ton-proof-item-v2/"
_TON_CONNECT_PREFIX: Final = b"\xff\xff" + b"ton-connect"

_WORKCHAIN_BYTES: Final = 4  # int32 BE
_ADDRESS_HASH_HEX_CHARS: Final = 64  # 32 bytes
_DOMAIN_LENGTH_BYTES: Final = 4  # uint32 LE
_TIMESTAMP_BYTES: Final = 8  # uint64 LE


def build_canonical_message(proof: TonProof) -> bytes:
    """Построить 32-байтовый canonical-message-hash из `TonProof`-VO.

    Параметры:
        proof: `TonProof`-VO, прошедший все инварианты `__post_init__`
            (включая raw-address-формат ``workchain:hex64``).

    Возвращает:
        ровно 32 байта — финальный sha256-hash, который сам подписан
        Ed25519-ключом кошелька. Передаётся в `pynacl.VerifyKey.verify(...)`
        в F.5.c как `smessage`.

    Семантика:
        * Pure-CPU, никаких I/O.
        * Детерминированно: одинаковый proof → одинаковый hash.
        * Не зависит от текущего времени, окружения, любого external state-а.
    """
    workchain_str, address_hash_hex = proof.address.split(":", 1)
    workchain = int(workchain_str)
    address_hash = bytes.fromhex(address_hash_hex)

    domain_bytes = proof.domain_value.encode("utf-8")
    payload_bytes = proof.payload.encode("utf-8")

    message = (
        _SCHEMA_PREFIX
        + workchain.to_bytes(_WORKCHAIN_BYTES, byteorder="big", signed=True)
        + address_hash
        + len(domain_bytes).to_bytes(_DOMAIN_LENGTH_BYTES, byteorder="little", signed=False)
        + domain_bytes
        + proof.timestamp.to_bytes(_TIMESTAMP_BYTES, byteorder="little", signed=False)
        + payload_bytes
    )

    inner_hash = hashlib.sha256(message).digest()
    return hashlib.sha256(_TON_CONNECT_PREFIX + inner_hash).digest()
