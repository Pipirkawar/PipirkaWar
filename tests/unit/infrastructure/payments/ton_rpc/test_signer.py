"""Unit-тесты Ed25519-сигнера TON-сообщений (Спринт 4.1-D, шаг D.10.b-1).

Покрытие:

* Структурное: `Ed25519MessageSigner` имплементит `ITonMessageSigner`-Protocol
  (runtime-`isinstance`-check + mypy-typecheck).
* `__slots__`: запрещены лишние атрибуты, нет `__dict__`.
* Конструктор: валидация типа/длины seed-а; `TypeError` / `ValueError`
  на невалид; bytearray / bytes — оба допустимы.
* `public_key`: ровно 32 байта, детерминирован от seed-а, не меняется
  между чтениями.
* `sign(...)`: 64-байтовая Ed25519-signature; детерминирована для
  одного seed-а + одного message-а; меняется при изменении message-а.
* Golden-vectors: на zero-seed-е (`bytes(32)`) — известные RFC 8032
  Ed25519 test vectors (sanity-check, что PyNaCl выдаёт ту же
  signature, что и стандарт).
* Round-trip: signature валидна через `nacl.signing.VerifyKey`.
* `sign(...)` принимает bytes и bytearray, отвергает прочее
  (TypeError).
* `__repr__` маскирует signing-key seed (не появляется в repr-е).
"""

from __future__ import annotations

import nacl.signing
import pytest
from nacl.exceptions import BadSignatureError

from pipirik_wars.infrastructure.payments.ton_rpc.signer import (
    Ed25519MessageSigner,
    ITonMessageSigner,
)

_ZERO_SEED = b"\x00" * 32
# Известный non-zero seed (детерминирован — повторяемые тесты).
_FIXED_SEED = bytes(range(32))


class TestStructure:
    """Структурные тесты порта/имплементации."""

    def test_ed25519_signer_implements_protocol(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=_ZERO_SEED)
        # `ITonMessageSigner` помечен `@runtime_checkable` — поэтому
        # isinstance работает.
        assert isinstance(signer, ITonMessageSigner)

    def test_slots_disallow_dynamic_attrs(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=_ZERO_SEED)
        # __slots__ должен блокировать любые внешние атрибуты.
        with pytest.raises(AttributeError):
            signer.foo = "bar"  # type: ignore[attr-defined]
        # И не должно быть __dict__.
        assert not hasattr(signer, "__dict__")


class TestConstructor:
    """Валидация входных параметров конструктора."""

    def test_accepts_32_byte_bytes_seed(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=_FIXED_SEED)
        assert len(signer.public_key) == 32

    def test_accepts_bytearray_seed(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=bytearray(_FIXED_SEED))
        assert len(signer.public_key) == 32

    @pytest.mark.parametrize("bad_length", [0, 1, 16, 31, 33, 64])
    def test_rejects_wrong_length_seed(self, bad_length: int) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            Ed25519MessageSigner(signing_key_seed=b"\x00" * bad_length)

    @pytest.mark.parametrize(
        "bad",
        ["not-bytes", 12345, None, [0] * 32, (0,) * 32],
    )
    def test_rejects_non_bytes_seed(self, bad: object) -> None:
        with pytest.raises(TypeError, match="must be bytes"):
            Ed25519MessageSigner(signing_key_seed=bad)  # type: ignore[arg-type]


class TestPublicKey:
    """`public_key` — детерминирован, ровно 32 байта."""

    def test_public_key_is_32_bytes(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=_ZERO_SEED)
        assert isinstance(signer.public_key, bytes)
        assert len(signer.public_key) == 32

    def test_public_key_is_deterministic_for_same_seed(self) -> None:
        signer_a = Ed25519MessageSigner(signing_key_seed=_FIXED_SEED)
        signer_b = Ed25519MessageSigner(signing_key_seed=_FIXED_SEED)
        assert signer_a.public_key == signer_b.public_key

    def test_public_key_differs_for_different_seeds(self) -> None:
        signer_a = Ed25519MessageSigner(signing_key_seed=_ZERO_SEED)
        signer_b = Ed25519MessageSigner(signing_key_seed=_FIXED_SEED)
        assert signer_a.public_key != signer_b.public_key

    def test_public_key_repeated_reads_stable(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=_FIXED_SEED)
        first = signer.public_key
        second = signer.public_key
        assert first == second


class TestSignVectors:
    """RFC 8032 Ed25519 test vectors (golden-проверка совместимости PyNaCl).

    Источник: https://www.rfc-editor.org/rfc/rfc8032#section-7.1, test 1.
    seed = 0x9d61b19d… → public_key = 0xd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a.
    """

    _RFC_SEED = bytes.fromhex(
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
    )
    _RFC_PUBLIC_KEY = bytes.fromhex(
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
    )
    # Test 1: signing empty message → known signature.
    _RFC_EMPTY_MESSAGE_SIGNATURE = bytes.fromhex(
        "e5564300c360ac729086e2cc806e828a"
        "84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46b"
        "d25bf5f0595bbe24655141438e7a100b",
    )

    def test_public_key_matches_rfc_vector(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=self._RFC_SEED)
        assert signer.public_key == self._RFC_PUBLIC_KEY

    def test_signature_matches_rfc_vector(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=self._RFC_SEED)
        sig = signer.sign(message=b"")
        assert sig == self._RFC_EMPTY_MESSAGE_SIGNATURE


class TestSign:
    """`sign(...)` поведение."""

    def test_returns_64_byte_signature(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=_ZERO_SEED)
        sig = signer.sign(message=b"\x11" * 32)
        assert isinstance(sig, bytes)
        assert len(sig) == 64

    def test_signature_is_deterministic_for_same_message(self) -> None:
        # Ed25519 — деривированно-детерминированная схема (HashEd25519
        # не используется). Для одного secret-key + message signature
        # стабильна.
        signer = Ed25519MessageSigner(signing_key_seed=_FIXED_SEED)
        sig_a = signer.sign(message=b"cell-repr-hash-test")
        sig_b = signer.sign(message=b"cell-repr-hash-test")
        assert sig_a == sig_b

    def test_signature_differs_for_different_messages(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=_FIXED_SEED)
        sig_a = signer.sign(message=b"message-a")
        sig_b = signer.sign(message=b"message-b")
        assert sig_a != sig_b

    def test_signature_differs_for_different_seeds(self) -> None:
        message = b"\x00" * 32
        sig_zero = Ed25519MessageSigner(signing_key_seed=_ZERO_SEED).sign(message=message)
        sig_fixed = Ed25519MessageSigner(signing_key_seed=_FIXED_SEED).sign(message=message)
        assert sig_zero != sig_fixed

    def test_signature_verifies_with_nacl_verify_key(self) -> None:
        """Round-trip: подпись валидна через `nacl.signing.VerifyKey`."""
        signer = Ed25519MessageSigner(signing_key_seed=_FIXED_SEED)
        message = b"some 32-byte BoC repr-hash--xxxx"
        sig = signer.sign(message=message)
        verify_key = nacl.signing.VerifyKey(signer.public_key)
        # VerifyKey.verify бросает BadSignatureError при провале; здесь
        # ожидаем успех (возврат — оригинальный message).
        assert verify_key.verify(message, sig) == message

    def test_signature_fails_verification_for_wrong_key(self) -> None:
        """Sanity: чужой public-key не должен верифицировать нашу подпись."""
        signer = Ed25519MessageSigner(signing_key_seed=_FIXED_SEED)
        message = b"another 32-byte BoC repr-hash--y"
        sig = signer.sign(message=message)

        # Подсунем другой public-key — должна свалиться верификация.
        other_signer = Ed25519MessageSigner(signing_key_seed=_ZERO_SEED)
        wrong_verify_key = nacl.signing.VerifyKey(other_signer.public_key)
        with pytest.raises(BadSignatureError):
            wrong_verify_key.verify(message, sig)

    def test_accepts_bytearray_message(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=_ZERO_SEED)
        sig = signer.sign(message=bytearray(b"\x42" * 32))
        assert len(sig) == 64

    def test_accepts_empty_message(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=_ZERO_SEED)
        sig = signer.sign(message=b"")
        assert len(sig) == 64

    @pytest.mark.parametrize("bad", ["string-msg", 0, None, [1, 2, 3]])
    def test_rejects_non_bytes_message(self, bad: object) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=_ZERO_SEED)
        with pytest.raises(TypeError, match="bytes-like"):
            signer.sign(message=bad)  # type: ignore[arg-type]

    @pytest.mark.parametrize("message_length", [1, 16, 32, 33, 64, 256, 1024])
    def test_signs_messages_of_arbitrary_length(self, message_length: int) -> None:
        # Ed25519 принимает любую длину; в TON-контексте обычно 32
        # (cell-repr-hash), но контракт не ограничивает.
        signer = Ed25519MessageSigner(signing_key_seed=_FIXED_SEED)
        sig = signer.sign(message=b"\x55" * message_length)
        assert len(sig) == 64


class TestRepr:
    """`__repr__` маскирует secret-key-seed."""

    def test_repr_does_not_leak_seed(self) -> None:
        seed = b"\xaa" * 32
        signer = Ed25519MessageSigner(signing_key_seed=seed)
        repr_str = repr(signer)
        # Hex seed-а не должно появиться в repr-е.
        assert seed.hex() not in repr_str
        # И отдельной hex-подстрокой тоже не.
        assert "aa" * 16 not in repr_str.lower()

    def test_repr_contains_public_key(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=_FIXED_SEED)
        repr_str = repr(signer)
        assert signer.public_key.hex() in repr_str

    def test_repr_marks_seed_as_redacted(self) -> None:
        signer = Ed25519MessageSigner(signing_key_seed=_FIXED_SEED)
        assert "redacted" in repr(signer).lower()
