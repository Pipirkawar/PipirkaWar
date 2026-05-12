"""TON Connect 2.0 ``ton_proof``-JSON → ``TonProof``-VO десериалайзер (Спринт 4.1-F, шаг F.5.a).

Кошельковые приложения (Tonkeeper, MyTonWallet, Tonhub, ...) по TON Connect
2.0-спеке возвращают dApp-у ответ на `tonProof`-запрос в виде JSON-объекта.
Канонический shape (см. https://docs.ton.org/develop/dapps/ton-connect/sign):

::

    {
      "proof": {
        "timestamp": <int unix-seconds>,
        "domain": {
          "lengthBytes": <int>,
          "value": "<utf8-host>"
        },
        "payload": "<server-issued nonce>",
        "signature": "<base64 Ed25519 64-bytes>",
        "state_init": "<base64 BoC, optional>"
      },
      "account": {
        "address": "<workchain:hex64 raw form>",
        "publicKey": "<64 hex Ed25519>"
      }
    }

В нашем интерфейсе `ITonConnectVerifier.verify(*, address, proof)` параметр
`proof: str` — это JSON-строка с указанной структурой. Этот модуль её парсит
и валидирует, затем строит `TonProof`-VO (см. `domain.monetization.value_objects`).

На любой ошибке (JSON / schema / type / VO-invariant) — единственный тип
исключения `TonProofMalformedError(reason, raw_len)` с короткой машинно-
читаемой причиной и длиной raw-payload-а (без содержимого; sensitive-данные
не утекают в лог).
"""

from __future__ import annotations

import json
from typing import Final

from pipirik_wars.domain.monetization.errors import TonProofMalformedError
from pipirik_wars.domain.monetization.value_objects import TonProof

__all__ = ["parse_ton_proof"]

# Машино-читаемые `reason`-коды (стабильные API для лога/метрик).
_REASON_JSON_PARSE: Final = "json_parse"
_REASON_NOT_OBJECT: Final = "not_object"
_REASON_MISSING_FIELD: Final = "missing_field"
_REASON_TYPE_MISMATCH: Final = "type_mismatch"
_REASON_DOMAIN_LENGTH_MISMATCH: Final = "domain_length_mismatch"
_REASON_BAD_TIMESTAMP: Final = "bad_timestamp"
_REASON_BAD_DOMAIN: Final = "bad_domain"
_REASON_BAD_PAYLOAD: Final = "bad_payload"
_REASON_BAD_SIGNATURE: Final = "bad_signature"
_REASON_BAD_PUBKEY: Final = "bad_pubkey"
_REASON_BAD_ADDRESS: Final = "bad_address"
_REASON_BAD_STATE_INIT: Final = "bad_state_init"
_REASON_VO_INVARIANT: Final = "vo_invariant"


def parse_ton_proof(raw: str) -> TonProof:  # noqa: PLR0912, PLR0915 — линейная цепочка schema-инвариантов
    """Распарсить JSON-строку TON Connect 2.0 ``ton_proof``-ответа кошелька.

    Параметры:
        raw: исходная JSON-строка ровно в формате, описанном в module-docstring-е.
            Никаких URL-encode / base64-врапов — голый JSON.

    Возвращает:
        ``TonProof``-VO (frozen+slots), прошедший все инварианты из
        ``domain.monetization.value_objects.TonProof.__post_init__``.

    Бросает:
        ``TonProofMalformedError(reason, raw_len)`` — на любой schema-,
        type- или VO-invariant-ошибке. ``raw_len`` всегда равен `len(raw)`
        в байтах исходной utf8-encoded строки (для лога без содержимого).

    Контракт:
        * Парсинг строго pure-CPU (никаких I/O, threads, asyncio-await-ов);
          можно вызывать из любого контекста — sync или async.
        * Никаких partial-результатов: либо валидный `TonProof`, либо
          исключение. Никаких `None`-ов в полях.
        * Sensitive-данные (signature_b64, payload, public_key_hex) в
          текст исключения НЕ попадают — только короткий `reason`-код
          и длина raw-payload-а.
    """
    raw_len = len(raw.encode("utf-8"))

    # Шаг 1: JSON-парс.
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TonProofMalformedError(
            reason=_REASON_JSON_PARSE,
            raw_len=raw_len,
        ) from exc

    if not isinstance(decoded, dict):
        raise TonProofMalformedError(reason=_REASON_NOT_OBJECT, raw_len=raw_len)

    # Шаг 2: обязательные top-level-объекты `proof` и `account`.
    proof_section = _require_field(decoded, "proof", raw_len)
    account_section = _require_field(decoded, "account", raw_len)
    if not isinstance(proof_section, dict):
        raise TonProofMalformedError(reason=_REASON_TYPE_MISMATCH, raw_len=raw_len)
    if not isinstance(account_section, dict):
        raise TonProofMalformedError(reason=_REASON_TYPE_MISMATCH, raw_len=raw_len)

    # Шаг 3: поля proof.{timestamp, domain.{lengthBytes,value}, payload, signature, state_init?}.
    timestamp_raw = _require_field(proof_section, "timestamp", raw_len)
    if not isinstance(timestamp_raw, int) or isinstance(timestamp_raw, bool):
        raise TonProofMalformedError(reason=_REASON_BAD_TIMESTAMP, raw_len=raw_len)

    domain_obj = _require_field(proof_section, "domain", raw_len)
    if not isinstance(domain_obj, dict):
        raise TonProofMalformedError(reason=_REASON_BAD_DOMAIN, raw_len=raw_len)
    domain_value = _require_field(domain_obj, "value", raw_len)
    domain_length_bytes = _require_field(domain_obj, "lengthBytes", raw_len)
    if not isinstance(domain_value, str):
        raise TonProofMalformedError(reason=_REASON_BAD_DOMAIN, raw_len=raw_len)
    if not isinstance(domain_length_bytes, int) or isinstance(domain_length_bytes, bool):
        raise TonProofMalformedError(reason=_REASON_BAD_DOMAIN, raw_len=raw_len)
    # Согласно спеке TON Connect 2.0, `lengthBytes` обязан равняться utf8-длине `value`.
    if domain_length_bytes != len(domain_value.encode("utf-8")):
        raise TonProofMalformedError(
            reason=_REASON_DOMAIN_LENGTH_MISMATCH,
            raw_len=raw_len,
        )

    payload_value = _require_field(proof_section, "payload", raw_len)
    if not isinstance(payload_value, str):
        raise TonProofMalformedError(reason=_REASON_BAD_PAYLOAD, raw_len=raw_len)

    signature_b64 = _require_field(proof_section, "signature", raw_len)
    if not isinstance(signature_b64, str):
        raise TonProofMalformedError(reason=_REASON_BAD_SIGNATURE, raw_len=raw_len)

    state_init_b64_raw = proof_section.get("state_init")
    state_init_b64: str | None
    if state_init_b64_raw is None:
        state_init_b64 = None
    elif isinstance(state_init_b64_raw, str):
        state_init_b64 = state_init_b64_raw
    else:
        raise TonProofMalformedError(reason=_REASON_BAD_STATE_INIT, raw_len=raw_len)

    # Шаг 4: поля account.{address, publicKey}.
    address_value = _require_field(account_section, "address", raw_len)
    if not isinstance(address_value, str):
        raise TonProofMalformedError(reason=_REASON_BAD_ADDRESS, raw_len=raw_len)

    public_key_hex = _require_field(account_section, "publicKey", raw_len)
    if not isinstance(public_key_hex, str):
        raise TonProofMalformedError(reason=_REASON_BAD_PUBKEY, raw_len=raw_len)

    # Шаг 5: построить VO; ловим любой `__post_init__`-invariant.
    try:
        return TonProof(
            timestamp=timestamp_raw,
            domain_value=domain_value,
            payload=payload_value,
            signature_b64=signature_b64,
            public_key_hex=public_key_hex,
            address=address_value,
            state_init_b64=state_init_b64,
        )
    except (ValueError, TypeError) as exc:
        raise TonProofMalformedError(
            reason=_REASON_VO_INVARIANT,
            raw_len=raw_len,
        ) from exc


def _require_field(obj: dict[str, object], key: str, raw_len: int) -> object:
    """Достать обязательное поле из dict-а или бросить `missing_field`.

    Возвращает «голый» `object`, типизация — на стороне caller-а.
    """
    if key not in obj:
        raise TonProofMalformedError(reason=_REASON_MISSING_FIELD, raw_len=raw_len)
    return obj[key]
