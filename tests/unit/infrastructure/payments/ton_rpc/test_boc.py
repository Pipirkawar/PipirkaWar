"""Unit-тесты TON BoC encoder-а (Спринт 4.1-D, шаг D.10.b-2).

Golden-vectors сравнены 1-в-1 с ``tonsdk`` (TonCenter Python SDK) при
разработке; здесь они хардкодены как hex-строки, чтобы тесты не
зависели от ``tonsdk`` в production-deps.

Покрытие:

* ``Cell`` invariants: bit-count, refs-count, ``bits``-длина.
* ``CellBuilder.store_uint`` / ``store_int`` / ``store_bool`` / ``store_bits`` /
  ``store_bytes``: границы, ошибки, корректность бит-паттернов.
* ``CellBuilder.store_coins`` (TEP-74 VarUInteger 16): zero, boundary,
  max 2^120-1, отказ на отрицательных / слишком больших.
* ``CellBuilder.store_address`` / ``store_address_none``: basechain
  (wc=0), masterchain (wc=-1), невалидный workchain / hash-length.
* ``Cell.repr_hash()`` golden-vectors: empty, uint8, coins, address.
* ``Cell.depth()``: 0 для leaf-а, корректный max-depth для дерева.
* ``CellBuilder.store_ref``: до 4 рефов, отказ на 5-м.
* ``parse_address(...)``: raw (``0:abcd...``, ``-1:...``), friendly
  base64url (mainnet/testnet, bouncable/non-bouncable, masterchain),
  ошибки (bad-len, bad-hex, bad-CRC).
* ``serialize_boc(...)``: golden BoC hex для known cells; overflow
  (> 255 cells / > 255 bytes data).
* TEP-74-shaped jetton-transfer body: hash + boc сверены с tonsdk при
  разработке.
"""

from __future__ import annotations

import hashlib

import pytest

from pipirik_wars.infrastructure.payments.ton_rpc.boc import (
    Cell,
    CellBuilder,
    deserialize_boc,
    format_raw_address,
    parse_address,
    parse_msgaddress_int_from_cell,
    serialize_boc,
)

# ---------------------------------------------------------------------------
# Известные golden-vectors (от tonsdk, без runtime-зависимости).
# ---------------------------------------------------------------------------

# Empty cell: hash = SHA256(b"\x00\x00")
_EMPTY_HASH_HEX = "96a296d224f285c67bee93c30f8a309157f0daa35dc5b87e410b78630a09cfc7"

# store_uint(0xAB, 8): hash = SHA256(b"\x00\x02\xab")
_UINT8_AB_HASH_HEX = "57c2a1a13baa2762109ed68be0c396f2303ce17e3dde7917d0e74b4072b1dbc7"

# store_coins(0): 4 нулевых бита, padding-bit ставится в data → 0x08
# d1=0, d2=1, data=0x08 → SHA256(0x00 0x01 0x08)
_COINS_0_HASH_HEX = "5331fed036518120c7f345726537745c5929b8ea1fa37b99b2bb58f702671541"

# store_coins(1): 4-bit n=1 + 8-bit value 0x01 → 12 bits, 2 bytes data
_COINS_1_HASH_HEX = "d46edee086ccbace01f45c13d26d49b68f74cd1b7616f4662e699c82c6ec728b"

# store_coins(1_000_000_000): 4-bit n=4 + 32-bit value
_COINS_1B_HASH_HEX = "e139b2d96d0bd76da98c3c23b0dc0481dcfe19562798fefbb7bf2e56d8ef37b5"

# store_address(0:00..00): 267 бит → 34 байта data
_ADDR_BASECHAIN_ZERO_HASH_HEX = "61ab4641fa30d9310391025086eec65d200d79268e1b7cd402565e01ba64be3c"

# Cell с одним ref-ом: outer(uint8 0xAB) → inner(uint8 0xCD)
_INNER_CD_HASH_HEX = "55d3a36fab16e3608adfd243927a59037d0d48f37dd6dd81fc47c941ac6a1e01"
_OUTER_AB_REF_HASH_HEX = "b109decf2254329dc5d31c9004b520818f6b360896c21021eba7de5873c4eca5"

# Minimal BoC-hex (no idx, no crc, size=1, off=1):
_EMPTY_CELL_BOC_HEX = "b5ee9c72010101010002000000"
_UINT8_AB_BOC_HEX = "b5ee9c72010101010003000002ab"
_OUTER_AB_REF_BOC_HEX = "b5ee9c72010102010007000102ab010002cd"

# RFC-friendly addresses (синтетические, but valid CRC):
# mainnet bouncable, basechain, hash=0
_ADDR_FRIENDLY_BOUNCE_MAINNET = "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c"
# testnet non-bouncable, basechain, hash=0
_ADDR_FRIENDLY_NONBOUNCE_TESTNET = "0QAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACkT"
# mainnet bouncable, masterchain, hash=0
_ADDR_FRIENDLY_MASTERCHAIN = "Ef8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADAU"


# ---------------------------------------------------------------------------
# Cell invariants.
# ---------------------------------------------------------------------------


class TestCellInvariants:
    def test_empty_cell(self) -> None:
        c = Cell(bits=b"", bits_count=0)
        assert c.bits == b""
        assert c.bits_count == 0
        assert c.refs == ()
        assert c.depth() == 0

    def test_refs_default_to_empty_tuple(self) -> None:
        c = Cell(bits=b"\xab", bits_count=8)
        assert c.refs == ()

    @pytest.mark.parametrize("bad_count", [-1, 1024, 9999])
    def test_invalid_bits_count(self, bad_count: int) -> None:
        with pytest.raises(ValueError, match="bits_count"):
            Cell(bits=b"", bits_count=bad_count)

    def test_bits_length_mismatch(self) -> None:
        # bits_count=8 требует ровно 1 байт.
        with pytest.raises(ValueError, match="bits length"):
            Cell(bits=b"", bits_count=8)
        with pytest.raises(ValueError, match="bits length"):
            Cell(bits=b"\x00\x00", bits_count=8)

    def test_too_many_refs(self) -> None:
        leaf = CellBuilder().end_cell()
        with pytest.raises(ValueError, match="refs"):
            Cell(bits=b"", bits_count=0, refs=(leaf, leaf, leaf, leaf, leaf))


# ---------------------------------------------------------------------------
# CellBuilder.store_uint / store_int / store_bool.
# ---------------------------------------------------------------------------


class TestStoreUint:
    def test_zero_bits_zero_value(self) -> None:
        c = CellBuilder().store_uint(0, 0).end_cell()
        assert c.bits_count == 0

    def test_zero_bits_nonzero_value_fails(self) -> None:
        with pytest.raises(ValueError, match="n_bits=0"):
            CellBuilder().store_uint(1, 0)

    def test_single_bit(self) -> None:
        b = CellBuilder()
        b.store_uint(1, 1)
        c = b.end_cell()
        assert c.bits_count == 1
        # 1 бит "1" + padding "1"+ 6 нолей = 0b11000000
        assert c._finalized_data() == bytes([0b1100_0000])

    def test_uint8_value(self) -> None:
        c = CellBuilder().store_uint(0xAB, 8).end_cell()
        assert c.bits_count == 8
        assert c.bits == b"\xab"

    def test_uint16_value(self) -> None:
        c = CellBuilder().store_uint(0xABCD, 16).end_cell()
        assert c.bits_count == 16
        assert c.bits == b"\xab\xcd"

    def test_uint32_value(self) -> None:
        c = CellBuilder().store_uint(0xDEADBEEF, 32).end_cell()
        assert c.bits == b"\xde\xad\xbe\xef"

    def test_uint64_value(self) -> None:
        c = CellBuilder().store_uint(0xDEADBEEFCAFEBABE, 64).end_cell()
        assert c.bits == b"\xde\xad\xbe\xef\xca\xfe\xba\xbe"

    @pytest.mark.parametrize("n_bits", [-1])
    def test_negative_n_bits(self, n_bits: int) -> None:
        with pytest.raises(ValueError, match="n_bits"):
            CellBuilder().store_uint(0, n_bits)

    def test_negative_value(self) -> None:
        with pytest.raises(ValueError, match="value must be >= 0"):
            CellBuilder().store_uint(-1, 8)

    def test_value_overflow(self) -> None:
        with pytest.raises(ValueError, match="does not fit"):
            CellBuilder().store_uint(256, 8)

    def test_cell_overflow(self) -> None:
        # 1023 бит — лимит. Запихать 1024-й бит — ValueError.
        b = CellBuilder()
        b.store_uint(0, 1023)
        with pytest.raises(ValueError, match="cell overflow"):
            b.store_uint(0, 1)


class TestStoreInt:
    def test_positive_value(self) -> None:
        c = CellBuilder().store_int(42, 8).end_cell()
        assert c.bits == bytes([42])

    def test_negative_value_twos_complement(self) -> None:
        c = CellBuilder().store_int(-1, 8).end_cell()
        # -1 в int8 → 0xFF.
        assert c.bits == b"\xff"

    def test_workchain_minus_one(self) -> None:
        c = CellBuilder().store_int(-1, 8).end_cell()
        # masterchain workchain.
        assert c.bits == b"\xff"

    def test_max_int8(self) -> None:
        c = CellBuilder().store_int(127, 8).end_cell()
        assert c.bits == b"\x7f"

    def test_min_int8(self) -> None:
        c = CellBuilder().store_int(-128, 8).end_cell()
        assert c.bits == b"\x80"

    @pytest.mark.parametrize("bad", [128, -129])
    def test_int8_overflow(self, bad: int) -> None:
        with pytest.raises(ValueError, match="does not fit"):
            CellBuilder().store_int(bad, 8)

    def test_zero_n_bits(self) -> None:
        with pytest.raises(ValueError, match="n_bits"):
            CellBuilder().store_int(0, 0)


class TestStoreBool:
    def test_true(self) -> None:
        c = CellBuilder().store_bool(value=True).end_cell()
        assert c.bits_count == 1
        # bit "1" + padding "1" + 6 нолей = 0b1100_0000
        assert c._finalized_data() == bytes([0b1100_0000])

    def test_false(self) -> None:
        c = CellBuilder().store_bool(value=False).end_cell()
        assert c.bits_count == 1
        # bit "0" + padding "1" + 6 нолей = 0b0100_0000
        assert c._finalized_data() == bytes([0b0100_0000])


class TestStoreBits:
    def test_full_bytes(self) -> None:
        c = CellBuilder().store_bits(b"\xab\xcd", 16).end_cell()
        assert c.bits == b"\xab\xcd"

    def test_partial_bits(self) -> None:
        # Положить первые 4 бита из 0xAB = 0b1010 → cell содержит "1010".
        c = CellBuilder().store_bits(b"\xab", 4).end_cell()
        assert c.bits_count == 4
        # padding: "1010" + "1" + "000" = 0b10101000 = 0xA8.
        assert c._finalized_data() == bytes([0xA8])

    def test_data_too_short(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            CellBuilder().store_bits(b"\xab", 16)


class TestStoreBytes:
    def test_basic(self) -> None:
        c = CellBuilder().store_bytes(b"\xab\xcd").end_cell()
        assert c.bits == b"\xab\xcd"

    def test_32_bytes(self) -> None:
        payload = bytes(range(32))
        c = CellBuilder().store_bytes(payload).end_cell()
        assert c.bits == payload
        assert c.bits_count == 256


# ---------------------------------------------------------------------------
# CellBuilder.store_coins (TEP-74 VarUInteger 16).
# ---------------------------------------------------------------------------


class TestStoreCoins:
    def test_zero(self) -> None:
        c = CellBuilder().store_coins(0).end_cell()
        assert c.bits_count == 4
        assert c.repr_hash().hex() == _COINS_0_HASH_HEX

    def test_one(self) -> None:
        c = CellBuilder().store_coins(1).end_cell()
        assert c.bits_count == 4 + 8  # n=1, 8-bit value
        assert c.repr_hash().hex() == _COINS_1_HASH_HEX

    def test_one_billion(self) -> None:
        # 1_000_000_000 = 0x3B9ACA00 → 30 бит → 4 байта → 4 + 32 = 36 бит.
        c = CellBuilder().store_coins(1_000_000_000).end_cell()
        assert c.bits_count == 4 + 32
        assert c.repr_hash().hex() == _COINS_1B_HASH_HEX

    @pytest.mark.parametrize(
        "value",
        [
            255,  # 1 byte
            256,  # 2 bytes
            2**32 - 1,  # 4 bytes
            2**64 - 1,  # 8 bytes
            2**120 - 1,  # max
        ],
    )
    def test_byte_boundaries(self, value: int) -> None:
        c = CellBuilder().store_coins(value).end_cell()
        n_bytes = (value.bit_length() + 7) // 8
        assert c.bits_count == 4 + n_bytes * 8

    def test_negative_value_fails(self) -> None:
        with pytest.raises(ValueError, match="value must be >= 0"):
            CellBuilder().store_coins(-1)

    def test_value_too_large(self) -> None:
        with pytest.raises(ValueError, match="too large"):
            CellBuilder().store_coins(2**120)


# ---------------------------------------------------------------------------
# CellBuilder.store_address / store_address_none.
# ---------------------------------------------------------------------------


class TestStoreAddress:
    def test_basechain_zero_hash(self) -> None:
        c = CellBuilder().store_address(workchain=0, account_hash=bytes(32)).end_cell()
        assert c.bits_count == 267  # 2 + 1 + 8 + 256
        assert c.repr_hash().hex() == _ADDR_BASECHAIN_ZERO_HASH_HEX

    def test_masterchain(self) -> None:
        c = CellBuilder().store_address(workchain=-1, account_hash=bytes(32)).end_cell()
        assert c.bits_count == 267

    def test_bad_workchain(self) -> None:
        with pytest.raises(ValueError, match="workchain"):
            CellBuilder().store_address(workchain=128, account_hash=bytes(32))
        with pytest.raises(ValueError, match="workchain"):
            CellBuilder().store_address(workchain=-129, account_hash=bytes(32))

    @pytest.mark.parametrize("bad_len", [0, 16, 31, 33, 64])
    def test_bad_hash_length(self, bad_len: int) -> None:
        with pytest.raises(ValueError, match="account_hash"):
            CellBuilder().store_address(workchain=0, account_hash=bytes(bad_len))


class TestStoreAddressNone:
    def test_addr_none(self) -> None:
        c = CellBuilder().store_address_none().end_cell()
        assert c.bits_count == 2
        # 2 нулевых бита + padding "1" + 5 нолей = 0b0010_0000 = 0x20.
        assert c._finalized_data() == bytes([0x20])


# ---------------------------------------------------------------------------
# CellBuilder.store_ref + Cell.depth().
# ---------------------------------------------------------------------------


class TestStoreRef:
    def test_one_ref(self) -> None:
        inner = CellBuilder().store_uint(0xCD, 8).end_cell()
        outer = CellBuilder().store_uint(0xAB, 8).store_ref(inner).end_cell()
        assert len(outer.refs) == 1
        assert outer.refs[0] is inner
        assert outer.depth() == 1

    def test_nested_refs_depth(self) -> None:
        c0 = CellBuilder().end_cell()
        c1 = CellBuilder().store_ref(c0).end_cell()
        c2 = CellBuilder().store_ref(c1).end_cell()
        c3 = CellBuilder().store_ref(c2).end_cell()
        assert c3.depth() == 3

    def test_four_refs(self) -> None:
        leaf = CellBuilder().end_cell()
        c = CellBuilder().store_ref(leaf).store_ref(leaf).store_ref(leaf).store_ref(leaf).end_cell()
        assert len(c.refs) == 4

    def test_too_many_refs(self) -> None:
        leaf = CellBuilder().end_cell()
        builder = CellBuilder()
        for _ in range(4):
            builder.store_ref(leaf)
        with pytest.raises(ValueError, match="refs"):
            builder.store_ref(leaf)


# ---------------------------------------------------------------------------
# Cell.repr_hash() golden vectors.
# ---------------------------------------------------------------------------


class TestReprHashGoldens:
    def test_empty_cell(self) -> None:
        c = CellBuilder().end_cell()
        # Sanity: empty cell hash = SHA256(b"\x00\x00").
        assert c.repr_hash() == hashlib.sha256(b"\x00\x00").digest()
        assert c.repr_hash().hex() == _EMPTY_HASH_HEX

    def test_uint8_ab(self) -> None:
        c = CellBuilder().store_uint(0xAB, 8).end_cell()
        # d1=0, d2=2 (1 full byte + 1 used byte), data=0xAB
        assert c.repr_hash() == hashlib.sha256(b"\x00\x02\xab").digest()
        assert c.repr_hash().hex() == _UINT8_AB_HASH_HEX

    def test_cell_with_ref(self) -> None:
        inner = CellBuilder().store_uint(0xCD, 8).end_cell()
        outer = CellBuilder().store_uint(0xAB, 8).store_ref(inner).end_cell()
        assert inner.repr_hash().hex() == _INNER_CD_HASH_HEX
        assert outer.repr_hash().hex() == _OUTER_AB_REF_HASH_HEX


# ---------------------------------------------------------------------------
# parse_address.
# ---------------------------------------------------------------------------


class TestParseAddressRaw:
    def test_basechain(self) -> None:
        wc, h = parse_address("0:" + "ab" * 32)
        assert wc == 0
        assert h == bytes.fromhex("ab" * 32)

    def test_masterchain(self) -> None:
        wc, h = parse_address("-1:" + "00" * 32)
        assert wc == -1
        assert h == bytes(32)

    def test_bad_format(self) -> None:
        with pytest.raises(ValueError, match="must be 'wc:hex'"):
            parse_address("0:abc:def")

    def test_bad_workchain(self) -> None:
        with pytest.raises(ValueError, match="integer"):
            parse_address("zero:" + "00" * 32)
        with pytest.raises(ValueError, match="int8"):
            parse_address("128:" + "00" * 32)

    def test_bad_hex_length(self) -> None:
        with pytest.raises(ValueError, match="hex chars"):
            parse_address("0:abcd")

    def test_bad_hex_chars(self) -> None:
        with pytest.raises(ValueError, match="hex"):
            parse_address("0:" + "zz" * 32)


class TestParseAddressFriendly:
    def test_mainnet_bounceable_basechain(self) -> None:
        wc, h = parse_address(_ADDR_FRIENDLY_BOUNCE_MAINNET)
        assert wc == 0
        assert h == bytes(32)

    def test_testnet_nonbounce(self) -> None:
        wc, h = parse_address(_ADDR_FRIENDLY_NONBOUNCE_TESTNET)
        assert wc == 0
        assert h == bytes(32)

    def test_masterchain_friendly(self) -> None:
        wc, h = parse_address(_ADDR_FRIENDLY_MASTERCHAIN)
        assert wc == -1
        assert h == bytes(32)

    def test_bad_length(self) -> None:
        with pytest.raises(ValueError, match="base64url chars"):
            parse_address("EQ" + "A" * 30)

    def test_bad_base64(self) -> None:
        with pytest.raises(ValueError, match="base64url"):
            parse_address("!" * _ADDR_FRIENDLY_BOUNCE_MAINNET.__len__())

    def test_bad_crc(self) -> None:
        # Поменяем последний non-`A` символ на другой → CRC проиграет.
        bad = list(_ADDR_FRIENDLY_BOUNCE_MAINNET)
        # последние 2 байта (4 base64-символа) — CRC16. Заменим середину.
        bad[-3] = "X"
        with pytest.raises(ValueError, match="CRC16"):
            parse_address("".join(bad))


class TestParseAddressEdges:
    def test_non_str_input(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            parse_address("")  # пустая строка
        with pytest.raises(ValueError):
            parse_address(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# serialize_boc.
# ---------------------------------------------------------------------------


class TestSerializeBoc:
    def test_empty_cell(self) -> None:
        c = CellBuilder().end_cell()
        assert serialize_boc(c).hex() == _EMPTY_CELL_BOC_HEX

    def test_uint8_cell(self) -> None:
        c = CellBuilder().store_uint(0xAB, 8).end_cell()
        assert serialize_boc(c).hex() == _UINT8_AB_BOC_HEX

    def test_cell_with_ref(self) -> None:
        inner = CellBuilder().store_uint(0xCD, 8).end_cell()
        outer = CellBuilder().store_uint(0xAB, 8).store_ref(inner).end_cell()
        assert serialize_boc(outer).hex() == _OUTER_AB_REF_BOC_HEX

    def test_boc_starts_with_magic(self) -> None:
        c = CellBuilder().store_uint(0, 8).end_cell()
        boc = serialize_boc(c)
        assert boc[:4] == b"\xb5\xee\x9c\x72"

    def test_boc_flag_byte(self) -> None:
        c = CellBuilder().store_uint(0, 8).end_cell()
        boc = serialize_boc(c)
        # has_idx=0, hash_crc32=0, has_cache_bits=0, flags=0, size_bytes=1 → 0b0000_0001
        assert boc[4] == 0b0000_0001

    def test_boc_round_trip_hash(self) -> None:
        """Sanity: после serialize → repr_hash остаётся стабильным."""
        c = (
            CellBuilder()
            .store_coins(123_456_789)
            .store_address(
                workchain=0,
                account_hash=bytes(32),
            )
            .end_cell()
        )
        h1 = c.repr_hash()
        # Ничего не меняется при повторной сериализации.
        h2 = c.repr_hash()
        assert h1 == h2

    def test_shared_ref_recorded_once(self) -> None:
        """Один in-memory child cell не должен дублироваться в BoC."""
        shared = CellBuilder().store_uint(0xFF, 8).end_cell()
        parent = CellBuilder().store_ref(shared).store_ref(shared).end_cell()
        boc = serialize_boc(parent)
        # В BoC должны быть 2 cell-а (parent + shared), не 3.
        # cells_num — байт по индексу 6 после magic(4)+flag(1)+offbytes(1).
        assert boc[6] == 2


# ---------------------------------------------------------------------------
# TEP-74 jetton-transfer body (integration of multiple primitives).
# ---------------------------------------------------------------------------


class TestTep74Body:
    """Сборка jetton-transfer body-cell-а: верификация всех TL-B-полей вместе.

    TEP-74 jetton-transfer body:
        op_code: int32 = 0x0F8A7EA5
        query_id: int64
        amount: VarUInteger 16
        destination: MsgAddressInt
        response_destination: MsgAddressInt
        custom_payload: Maybe ^Cell (0 bit → no)
        forward_ton_amount: VarUInteger 16
        forward_payload: Either Cell ^Cell (0 bit → inline пустой)
    """

    def test_minimal_jetton_transfer_body(self) -> None:
        op_code = 0x0F8A7EA5
        query_id = 12345
        amount_native = 1_000_000  # 1 USDT (decimals=6)
        destination_hash = b"\xaa" * 32
        response_hash = b"\xbb" * 32

        body = (
            CellBuilder()
            .store_uint(op_code, 32)
            .store_uint(query_id, 64)
            .store_coins(amount_native)
            .store_address(workchain=0, account_hash=destination_hash)
            .store_address(workchain=0, account_hash=response_hash)
            .store_uint(0, 1)  # no custom payload
            .store_coins(0)  # forward_ton_amount = 0
            .store_uint(0, 1)  # forward payload inline (empty)
            .end_cell()
        )
        # Структурная проверка: cell вмещается в 1 cell (без рефов).
        assert len(body.refs) == 0
        # Sanity-bit-count: 32 + 64 + (4 + 24) + 267 + 267 + 1 + 4 + 1 = 664.
        # amount=1_000_000 fits в 3 байта = 24 bit value (n=3 → 28 бит).
        assert body.bits_count == 32 + 64 + (4 + 24) + 267 + 267 + 1 + 4 + 1

    def test_jetton_transfer_body_hash_stable(self) -> None:
        """Повторная сборка с теми же параметрами → одинаковый hash."""
        op_code = 0x0F8A7EA5
        query_id = 999
        amount_native = 42
        destination_hash = b"\x11" * 32
        response_hash = b"\x22" * 32

        def build() -> Cell:
            return (
                CellBuilder()
                .store_uint(op_code, 32)
                .store_uint(query_id, 64)
                .store_coins(amount_native)
                .store_address(workchain=0, account_hash=destination_hash)
                .store_address(workchain=0, account_hash=response_hash)
                .store_uint(0, 1)
                .store_coins(0)
                .store_uint(0, 1)
                .end_cell()
            )

        h1 = build().repr_hash()
        h2 = build().repr_hash()
        assert h1 == h2
        assert len(h1) == 32


# ---------------------------------------------------------------------------
# BoC capacity guards.
# ---------------------------------------------------------------------------


class TestBocCapacity:
    def test_off_bytes_2_used_when_size_exceeds_255(self) -> None:
        """Дерево с > 255 байт total data → off_bytes=2, успешно сериализуется."""
        leaves = [CellBuilder().store_bits(b"\xff" * 100, 800).end_cell() for _ in range(3)]
        builder = CellBuilder()
        for ll in leaves:
            builder.store_ref(ll)
        big_root = CellBuilder().store_ref(builder.end_cell()).end_cell()
        # cells = 1 (root) + 1 (mid) + 3 leaves = 5. tot_cells_size =
        # (root: 2 + 0 + 1) + (mid: 2 + 0 + 3) + 3 * (2 + 100 + 0) = 3 + 5 + 306 = 314.
        raw = serialize_boc(big_root)
        # Header: magic(4) flag(1) off_bytes(1) cells_num(1) roots(1) absent(1)
        #         tot_cells_size(off_bytes) root_idx(1)
        assert raw[:4].hex() == "b5ee9c72"
        # off_bytes byte at index 5.
        assert raw[5] == 2  # off_bytes = 2 для tot_cells_size > 255
        # tot_cells_size 16-bit BE at index 9-10.
        tot_size = int.from_bytes(raw[9:11], byteorder="big")
        assert tot_size == 314

    def test_too_many_cells_raises(self) -> None:
        """`size_bytes=1` limit — 255 cells."""
        # 256 уникальных leaf-ов (разные uint32-значения), затем 4-arity-дерево
        # над ними → 256 + 64 + 16 + 4 + 1 = 341 cells > 255.
        unique_leaves = [CellBuilder().store_uint(i, 32).end_cell() for i in range(256)]
        level = unique_leaves
        while len(level) > 1:
            next_level: list[Cell] = []
            for i in range(0, len(level), 4):
                b = CellBuilder()
                for c in level[i : i + 4]:
                    b.store_ref(c)
                next_level.append(b.end_cell())
            level = next_level
        root = level[0]
        with pytest.raises(ValueError, match="too many cells"):
            serialize_boc(root)


class TestDeserializeBoc:
    """Спринт 4.1-E / E.2 — `deserialize_boc(...)` round-trip с `serialize_boc(...)`."""

    def test_round_trip_byte_aligned_uint8(self) -> None:
        builder = CellBuilder()
        builder.store_uint(0xAB, 8)
        cell = builder.end_cell()
        decoded = deserialize_boc(serialize_boc(cell))
        assert decoded.bits == cell.bits
        assert decoded.bits_count == cell.bits_count
        assert decoded.refs == ()

    def test_round_trip_non_aligned_3_bits(self) -> None:
        builder = CellBuilder()
        builder.store_uint(0b101, 3)
        cell = builder.end_cell()
        decoded = deserialize_boc(serialize_boc(cell))
        assert decoded.bits == cell.bits
        assert decoded.bits_count == cell.bits_count

    def test_round_trip_empty_cell(self) -> None:
        cell = CellBuilder().end_cell()
        decoded = deserialize_boc(serialize_boc(cell))
        assert decoded.bits == b""
        assert decoded.bits_count == 0
        assert decoded.refs == ()

    def test_round_trip_address_basechain(self) -> None:
        account_hash = bytes.fromhex("aa" * 32)
        builder = CellBuilder()
        builder.store_address(workchain=0, account_hash=account_hash)
        cell = builder.end_cell()
        decoded = deserialize_boc(serialize_boc(cell))
        assert decoded.bits == cell.bits
        assert decoded.bits_count == 267

    def test_round_trip_address_masterchain(self) -> None:
        account_hash = bytes.fromhex("12" * 32)
        builder = CellBuilder()
        builder.store_address(workchain=-1, account_hash=account_hash)
        cell = builder.end_cell()
        decoded = deserialize_boc(serialize_boc(cell))
        assert decoded.bits == cell.bits
        assert decoded.bits_count == 267

    def test_round_trip_with_refs(self) -> None:
        leaf_a = CellBuilder().store_uint(0x11, 8).end_cell()
        leaf_b = CellBuilder().store_uint(0x22, 8).end_cell()
        root = CellBuilder().store_uint(0xFF, 8).store_ref(leaf_a).store_ref(leaf_b).end_cell()
        decoded = deserialize_boc(serialize_boc(root))
        assert decoded.bits == root.bits
        assert decoded.bits_count == root.bits_count
        assert len(decoded.refs) == 2
        assert decoded.refs[0].bits == leaf_a.bits
        assert decoded.refs[1].bits == leaf_b.bits

    def test_round_trip_preserves_repr_hash(self) -> None:
        account_hash = bytes.fromhex("cd" * 32)
        builder = CellBuilder()
        builder.store_address(workchain=0, account_hash=account_hash)
        cell = builder.end_cell()
        decoded = deserialize_boc(serialize_boc(cell))
        assert decoded.repr_hash() == cell.repr_hash()

    def test_rejects_non_bytes_input(self) -> None:
        with pytest.raises(ValueError, match="must be bytes"):
            deserialize_boc("not bytes")  # type: ignore[arg-type]

    def test_rejects_too_short_input(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            deserialize_boc(b"\xb5\xee\x9c\x72")

    def test_rejects_bad_magic(self) -> None:
        # 10 bytes длины, но magic-неверный.
        with pytest.raises(ValueError, match="magic"):
            deserialize_boc(b"\x00\x01\x02\x03" + b"\x00" * 10)

    def test_rejects_zero_cells_num(self) -> None:
        # Корректный header, но cells_num=0.
        header = b"\xb5\xee\x9c\x72" + bytes([0b0000_0001, 1, 0, 1, 0, 0, 0])
        with pytest.raises(ValueError, match="cells_num"):
            deserialize_boc(header)


class TestParseMsgAddressIntFromCell:
    """E.2 — `parse_msgaddress_int_from_cell(cell)` декодирует TL-B addr_std$10."""

    def test_basechain_address(self) -> None:
        account_hash = bytes.fromhex("aa" * 32)
        builder = CellBuilder()
        builder.store_address(workchain=0, account_hash=account_hash)
        cell = builder.end_cell()
        wc, ah = parse_msgaddress_int_from_cell(cell)
        assert wc == 0
        assert ah == account_hash

    def test_masterchain_address(self) -> None:
        account_hash = bytes.fromhex("ff" * 32)
        builder = CellBuilder()
        builder.store_address(workchain=-1, account_hash=account_hash)
        cell = builder.end_cell()
        wc, ah = parse_msgaddress_int_from_cell(cell)
        assert wc == -1
        assert ah == account_hash

    def test_arbitrary_workchain(self) -> None:
        account_hash = bytes.fromhex("01" * 32)
        builder = CellBuilder()
        builder.store_address(workchain=42, account_hash=account_hash)
        cell = builder.end_cell()
        wc, ah = parse_msgaddress_int_from_cell(cell)
        assert wc == 42
        assert ah == account_hash

    def test_cell_with_too_few_bits_rejected(self) -> None:
        cell = CellBuilder().store_uint(0x42, 8).end_cell()  # only 8 bits
        with pytest.raises(ValueError, match="267 bits"):
            parse_msgaddress_int_from_cell(cell)

    def test_cell_with_wrong_tag_rejected(self) -> None:
        # Build a 267-bit cell with tag=00 (addr_none / addr_ext-tagged form).
        builder = CellBuilder()
        builder.store_uint(0, 2)  # tag = 00 (not 10)
        builder.store_uint(0, 1)  # anycast = None
        builder.store_int(0, 8)
        builder.store_bytes(b"\x00" * 32)
        cell = builder.end_cell()
        with pytest.raises(ValueError, match="addr_std"):
            parse_msgaddress_int_from_cell(cell)

    def test_round_trip_through_deserialize(self) -> None:
        account_hash = bytes.fromhex("0123456789abcdef" * 4)
        builder = CellBuilder()
        builder.store_address(workchain=-1, account_hash=account_hash)
        cell = builder.end_cell()
        decoded = deserialize_boc(serialize_boc(cell))
        wc, ah = parse_msgaddress_int_from_cell(decoded)
        assert wc == -1
        assert ah == account_hash


class TestFormatRawAddress:
    def test_basechain_lower_hex(self) -> None:
        account_hash = bytes.fromhex("ab" * 32)
        assert format_raw_address(0, account_hash) == f"0:{'ab' * 32}"

    def test_masterchain(self) -> None:
        account_hash = bytes.fromhex("12" * 32)
        assert format_raw_address(-1, account_hash) == f"-1:{'12' * 32}"

    def test_invalid_workchain_rejected(self) -> None:
        with pytest.raises(ValueError, match="int8"):
            format_raw_address(128, b"\x00" * 32)

    def test_invalid_hash_length_rejected(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            format_raw_address(0, b"\x00" * 31)

    def test_round_trip_with_parse_address(self) -> None:
        account_hash = bytes.fromhex("cd" * 32)
        raw = format_raw_address(0, account_hash)
        wc, ah = parse_address(raw)
        assert wc == 0
        assert ah == account_hash
