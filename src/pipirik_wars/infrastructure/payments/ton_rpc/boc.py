"""Минимальный TON BoC (Bag of Cells) encoder (Спринт 4.1-D, шаг D.10.b-2).

Реализует ровно тот набор примитивов, который нужен ``TonRpcAdapter`` (D.10.b-3)
для построения signed-BOC-ов:

* ``Cell`` — immutable TON-ячейка: ``bits`` (bit-string), ``bits_count``,
  ``refs`` (0..4 child-ячеек).
* ``CellBuilder`` — mutable accumulator со ``store_*``-методами в стиле
  ``ton-blockchain/ton`` (`store_uint`, `store_int`, `store_bool`,
  `store_bits`, `store_bytes`, `store_coins` — TEP-74 VarUInteger 16,
  `store_address` — TL-B `addr_std$10`, `store_address_none` — `addr_none$00`,
  `store_ref` + `end_cell()`).
* ``Cell.repr_hash()`` — 32-байтовый representation-hash (SHA256 от
  ``d1 || d2 || data || depths_BE16 || refs_hashes``). Используется
  для Ed25519-подписи signed-body-cell-а в wallet-v3R2 / TEP-67-wrapping-е.
* ``Cell.depth()`` — глубина под-дерева (для BoC-serialization-а).
* ``parse_address(addr)`` — разбор TON-адреса (raw ``wc:hex`` или
  user-friendly base64url 48 chars с CRC16-XMODEM) в ``(workchain, hash32)``.
* ``serialize_boc(root)`` — минимальная BoC-сериализация (single-root,
  ``size_bytes=1``, ``off_bytes=1``, без idx, без CRC).

Формат и хеши соответствуют референсной TON-имплементации
(`ton-blockchain/ton`, `tonsdk`, `pytoniq-core`) — golden-vectors в
``tests/unit/infrastructure/payments/ton_rpc/test_boc.py`` сравнивают
с tonsdk-выходом 1-в-1.

Что НЕ делает этот модуль:

* Не работает с exotic-ячейками (pruned-branch / library / merkle-proof /
  merkle-update) — это не нужно для базовой подписи TON/USDT payout.
* Не валидирует TL-B-схемы. Caller (``TonRpcAdapter``) сам знает, какие
  ``store_*``-вызовы соответствуют TEP-74 jetton-transfer или wallet-v3R2.
* Не делает MerkleProof / cache-hashes / Hash_n>0 — единственный hash,
  возвращаемый ``Cell.repr_hash()``, — это level-0 representation-hash
  (он же и ``Hash_0`` по TVM-whitepaper).
"""

from __future__ import annotations

import base64
import hashlib
import struct
from dataclasses import dataclass, field

__all__ = [
    "Cell",
    "CellBuilder",
    "deserialize_boc",
    "format_raw_address",
    "parse_address",
    "parse_msgaddress_int_from_cell",
    "serialize_boc",
]


# Магическое число BoC-формата ("magic_simple_boc", ton-blockchain/ton).
_BOC_MAGIC = b"\xb5\xee\x9c\x72"

# Максимум 1023 бит данных в одной cell-е (по стандарту TVM).
_MAX_BITS_PER_CELL = 1023

# Максимум 4 child-references в одной cell-е.
_MAX_REFS_PER_CELL = 4

# VarUInteger 16: max 120-битное значение (15 байт). Реальные TON-coins
# умещаются в гораздо меньшее число байт (10**18 nano-TON ≈ 60 бит).
_MAX_COINS_BIT_LENGTH = 120

# Friendly-address: 36 байт после base64url-decode (1 flag + 1 wc + 32 hash + 2 crc16).
_FRIENDLY_ADDRESS_RAW_LENGTH = 36

# Длина friendly-address-а в base64url (с возможными `_-` и без paddinga).
_FRIENDLY_ADDRESS_B64_LENGTH = 48

# 256-битный (32-байтовый) account-hash.
_ADDRESS_HASH_BYTES = 32


# ---------------------------------------------------------------------------
# Cell + CellBuilder.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Cell:
    """TON cell (immutable). Конструируется через ``CellBuilder``.

    Поля:
    * ``bits: bytes`` — байты данных, длина = ``ceil(bits_count / 8)``.
      Биты упакованы слева-направо: первый bit = старший бит первого байта.
      Хвостовые биты (если ``bits_count % 8 != 0``) — каноническая TON-padding-схема:
      сразу за последним значащим битом ставится `1`, далее `0`-ы до конца байта.
    * ``bits_count: int`` — число значащих бит (0..1023).
    * ``refs: tuple[Cell, ...]`` — 0..4 child-ячеек.
    """

    bits: bytes
    bits_count: int
    refs: tuple[Cell, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not 0 <= self.bits_count <= _MAX_BITS_PER_CELL:
            raise ValueError(
                f"Cell.bits_count must be in [0, {_MAX_BITS_PER_CELL}], got {self.bits_count}",
            )
        expected_bytes = (self.bits_count + 7) // 8
        if len(self.bits) != expected_bytes:
            raise ValueError(
                "Cell.bits length mismatch: bits_count="
                f"{self.bits_count} → expected {expected_bytes} bytes, "
                f"got {len(self.bits)}",
            )
        if len(self.refs) > _MAX_REFS_PER_CELL:
            raise ValueError(
                f"Cell.refs must contain at most {_MAX_REFS_PER_CELL} cells, got {len(self.refs)}",
            )

    # ----- Public hashing / depth API ---------------------------------

    def repr_hash(self) -> bytes:
        """32-байтовый representation-hash level-0 (SHA256).

        Формула (TVM whitepaper §3.1.5, ordinary cells):
        ``Hash(c) = SHA256(d1 || d2 || data || depths || hashes)``
        где ``depths`` — конкатенация BE-uint16 глубин refs-ов,
        ``hashes`` — конкатенация ``repr_hash`` каждого ref-а.

        Используется ``TonRpcAdapter`` для signing-а body-cell-а
        в wallet-v3R2-message-е (D.10.b-3): ``signature = signer.sign(repr_hash(body_cell))``.
        """
        d1, d2 = self._descriptor_bytes()
        data = self._finalized_data()
        depths = b"".join(struct.pack(">H", r.depth()) for r in self.refs)
        hashes = b"".join(r.repr_hash() for r in self.refs)
        return hashlib.sha256(bytes([d1, d2]) + data + depths + hashes).digest()

    def depth(self) -> int:
        """Глубина под-дерева ячейки.

        Для cell без refs — ``0``. Иначе — ``1 + max(ref.depth() for ref in refs)``.
        Используется при сериализации BoC (depths-секция reference-list-а
        каждой ячейки + общий ``max_depth`` BoC-header-а).
        """
        if not self.refs:
            return 0
        return 1 + max(r.depth() for r in self.refs)

    # ----- Internals: descriptor + data finalization ------------------

    def _descriptor_bytes(self) -> tuple[int, int]:
        """Вернуть ``(d1, d2)`` дескриптор cell-а.

        * ``d1 = refs_count + 8*is_exotic + 32*has_hashes + 16*level``.
          У нас всегда exotic=0, hashes=0, level=0 → ``d1 = len(refs)``.
        * ``d2 = floor(bits_count/8) + ceil(bits_count/8)`` (TVM §3.1.4).
        """
        full_bytes = self.bits_count // 8
        used_bytes = (self.bits_count + 7) // 8
        return len(self.refs), full_bytes + used_bytes

    def _finalized_data(self) -> bytes:
        """Вернуть data-bytes уже с padding-битом (если bits_count % 8 != 0).

        Padding в TON: за последним значащим битом — `1`, потом `0`-ы.
        ``CellBuilder.end_cell()`` гарантирует, что lower-padding-биты
        в hex-данных = `0`, поэтому достаточно поставить разделительный `1`.
        """
        if self.bits_count % 8 == 0:
            return self.bits
        full_bytes = self.bits_count // 8
        rem = self.bits_count - 8 * full_bytes  # 1..7
        # Padding-биты сидят в `bits[full_bytes]` справа от значащих бит:
        # `bits[full_bytes] = <rem значащих><1><(7-rem) нолей>`. Padding-биты
        # CellBuilder.end_cell() уже привёл к 0, поэтому достаточно OR-нуть
        # bit на позиции (7-rem).
        data = bytearray(self.bits)
        data[full_bytes] |= 1 << (7 - rem)
        return bytes(data)


class CellBuilder:
    """Mutable builder для ``Cell``. См. docstring модуля для контракта."""

    __slots__ = ("_bits", "_bits_count", "_refs")

    def __init__(self) -> None:
        # Биты копим в bytearray-е. Каждый новый бит сдвигается в текущий
        # последний байт; при достижении 8 бит — открываем новый.
        self._bits = bytearray()
        self._bits_count = 0
        self._refs: list[Cell] = []

    # ----- Bit-level primitives --------------------------------------

    def store_uint(self, value: int, n_bits: int) -> CellBuilder:
        """Положить ``value`` как unsigned-int-в-n_bits-битах (big-endian).

        Поднимает ``ValueError`` при ``value < 0`` / ``value >= 2**n_bits`` /
        переполнении cell-а (> 1023 бит).
        """
        if n_bits < 0:
            raise ValueError(f"CellBuilder.store_uint: n_bits must be >= 0, got {n_bits}")
        if n_bits == 0:
            if value != 0:
                raise ValueError(
                    f"CellBuilder.store_uint: n_bits=0 requires value=0, got {value}",
                )
            return self
        if value < 0:
            raise ValueError(
                f"CellBuilder.store_uint: value must be >= 0 (use store_int for signed), got {value}",
            )
        if value >> n_bits != 0:
            raise ValueError(
                f"CellBuilder.store_uint: value={value} does not fit in n_bits={n_bits}",
            )
        # Сериализуем value в bit-stream и кладём по биту.
        for shift in range(n_bits - 1, -1, -1):
            self._append_bit((value >> shift) & 1)
        return self

    def store_int(self, value: int, n_bits: int) -> CellBuilder:
        """Положить ``value`` как signed-int-в-n_bits-битах (two's complement)."""
        if n_bits <= 0:
            raise ValueError(
                f"CellBuilder.store_int: n_bits must be >= 1, got {n_bits}",
            )
        bound = 1 << (n_bits - 1)
        if not (-bound <= value < bound):
            raise ValueError(
                f"CellBuilder.store_int: value={value} does not fit in n_bits={n_bits}",
            )
        # Two's complement: если value < 0, приводим в unsigned-домен.
        unsigned = value if value >= 0 else (value + (1 << n_bits))
        return self.store_uint(unsigned, n_bits)

    def store_bool(self, value: bool) -> CellBuilder:
        """1-bit boolean (``True`` → 1, ``False`` → 0)."""
        return self.store_uint(1 if value else 0, 1)

    def store_bits(self, data: bytes | bytearray, n_bits: int) -> CellBuilder:
        """Положить ``n_bits`` бит из ``data`` (left-to-right)."""
        if n_bits < 0:
            raise ValueError(f"CellBuilder.store_bits: n_bits must be >= 0, got {n_bits}")
        required_bytes = (n_bits + 7) // 8
        if len(data) < required_bytes:
            raise ValueError(
                f"CellBuilder.store_bits: data is too short for n_bits={n_bits} "
                f"(need {required_bytes} bytes, got {len(data)})",
            )
        for i in range(n_bits):
            bit = (data[i // 8] >> (7 - (i % 8))) & 1
            self._append_bit(bit)
        return self

    def store_bytes(self, data: bytes | bytearray) -> CellBuilder:
        """Положить произвольный байтовый блок (``len(data) * 8`` бит)."""
        return self.store_bits(data, len(data) * 8)

    # ----- TL-B-shaped primitives -------------------------------------

    def store_coins(self, value: int) -> CellBuilder:
        """TEP-74 / TVM ``VarUInteger 16``: 4-битная длина n + n*8 бит value.

        ``value == 0`` → ровно 4 нулевых бита (n=0). Иначе ``n = ceil(bit_length / 8)``,
        max ``n = 15`` (15*8 = 120 бит, max 2^120-1).
        """
        if value < 0:
            raise ValueError(f"CellBuilder.store_coins: value must be >= 0, got {value}")
        if value.bit_length() > _MAX_COINS_BIT_LENGTH:
            raise ValueError(
                f"CellBuilder.store_coins: value too large ({value.bit_length()} bits, "
                f"max {_MAX_COINS_BIT_LENGTH})",
            )
        if value == 0:
            return self.store_uint(0, 4)
        n_bytes = (value.bit_length() + 7) // 8
        self.store_uint(n_bytes, 4)
        return self.store_uint(value, n_bytes * 8)

    def store_address(self, *, workchain: int, account_hash: bytes) -> CellBuilder:
        """TL-B ``MsgAddressInt`` ``addr_std$10`` (без anycast).

        Структура (267 бит): ``10`` (tag, 2 бит) + ``0`` (anycast Nothing, 1 бит) +
        ``workchain`` (int8, 8 бит) + ``account_hash`` (256 бит).

        Параметры:
        * ``workchain: int`` — workchain id (signed int8, обычно ``0`` basechain или ``-1`` masterchain).
        * ``account_hash: bytes`` — ровно 32 байта account-id-а.
        """
        if not -128 <= workchain <= 127:
            raise ValueError(
                f"CellBuilder.store_address: workchain must fit in int8, got {workchain}",
            )
        if len(account_hash) != _ADDRESS_HASH_BYTES:
            raise ValueError(
                "CellBuilder.store_address: account_hash must be "
                f"{_ADDRESS_HASH_BYTES} bytes, got {len(account_hash)}",
            )
        self.store_uint(0b10, 2)  # addr_std$10
        self.store_uint(0, 1)  # anycast = Maybe Nothing
        self.store_int(workchain, 8)
        return self.store_bytes(account_hash)

    def store_address_none(self) -> CellBuilder:
        """TL-B ``MsgAddressExt`` ``addr_none$00`` (2 нулевых бита)."""
        return self.store_uint(0, 2)

    # ----- Refs --------------------------------------------------------

    def store_ref(self, cell: Cell) -> CellBuilder:
        """Добавить child-ref. До 4 refs на одну ячейку."""
        if len(self._refs) >= _MAX_REFS_PER_CELL:
            raise ValueError(
                f"CellBuilder.store_ref: cannot exceed {_MAX_REFS_PER_CELL} refs",
            )
        self._refs.append(cell)
        return self

    # ----- Finalization -----------------------------------------------

    def end_cell(self) -> Cell:
        """Заморозить builder в ``Cell``.

        Хвостовые padding-биты (биты после последнего ``store_*`` в текущем
        байте) принудительно зануляются — TON-padding-формат предполагает
        `1` сразу после последнего значащего бита, потом нули; padding `1`
        ставится при сериализации ``Cell._finalized_data()``.
        """
        # Нули в padding-области — Cell._finalized_data() сам поставит
        # разделительный `1`-бит. Здесь только убедимся, что не остался
        # «мусор» от каких-нибудь bytearray-операций (на практике
        # _append_bit всегда явно ставит 0/1).
        return Cell(
            bits=bytes(self._bits),
            bits_count=self._bits_count,
            refs=tuple(self._refs),
        )

    # ----- Internal helpers -------------------------------------------

    def _append_bit(self, bit: int) -> None:
        if self._bits_count >= _MAX_BITS_PER_CELL:
            raise ValueError(
                f"CellBuilder: cell overflow ({_MAX_BITS_PER_CELL} bits max)",
            )
        byte_index = self._bits_count // 8
        bit_offset = 7 - (self._bits_count % 8)
        if byte_index >= len(self._bits):
            self._bits.append(0)
        if bit:
            self._bits[byte_index] |= 1 << bit_offset
        # else: leave 0 (default after append).
        self._bits_count += 1


# ---------------------------------------------------------------------------
# Address parsing.
# ---------------------------------------------------------------------------


def parse_address(addr: str) -> tuple[int, bytes]:
    """Разобрать TON-адрес из строки в ``(workchain, account_hash)``.

    Поддерживает оба формата:

    1. **Raw** — ``"<workchain>:<64-hex>"`` (например ``"0:abcd...32-bytes-hex"``).
    2. **User-friendly base64url** — 48 chars, кодирует
       ``flags(1) || workchain(int8) || account_hash(32) || crc16(2)``.
       CRC16 — XMODEM (poly=0x1021, init=0x0000). Любая ошибка decode-а
       или mismatch CRC → ``ValueError``.

    Поднимает ``ValueError`` при невалидном формате.
    """
    if not isinstance(addr, str) or not addr:
        raise ValueError(f"parse_address: addr must be non-empty str, got {addr!r}")

    if ":" in addr:
        return _parse_raw_address(addr)
    return _parse_friendly_address(addr)


def _parse_raw_address(addr: str) -> tuple[int, bytes]:
    parts = addr.split(":")
    if len(parts) != 2:
        raise ValueError(f"parse_address: raw form must be 'wc:hex', got {addr!r}")
    wc_str, hex_str = parts
    try:
        workchain = int(wc_str)
    except ValueError as exc:
        raise ValueError(
            f"parse_address: workchain must be integer, got {wc_str!r}",
        ) from exc
    if not -128 <= workchain <= 127:
        raise ValueError(
            f"parse_address: workchain must fit in int8, got {workchain}",
        )
    if len(hex_str) != _ADDRESS_HASH_BYTES * 2:
        raise ValueError(
            f"parse_address: raw account-hash must be {_ADDRESS_HASH_BYTES * 2} hex chars, "
            f"got {len(hex_str)}",
        )
    try:
        account_hash = bytes.fromhex(hex_str)
    except ValueError as exc:
        raise ValueError(
            f"parse_address: account-hash is not valid hex: {hex_str!r}",
        ) from exc
    return workchain, account_hash


def _parse_friendly_address(addr: str) -> tuple[int, bytes]:
    if len(addr) != _FRIENDLY_ADDRESS_B64_LENGTH:
        raise ValueError(
            "parse_address: friendly addr must be "
            f"{_FRIENDLY_ADDRESS_B64_LENGTH} base64url chars, got len={len(addr)}",
        )
    # Принимаем как `urlsafe_b64encode`-формат (-_), так и обычный (+/);
    # дополняем `=` до длины-кратной-4.
    normalized = addr.replace("-", "+").replace("_", "/")
    padding = (-len(normalized)) % 4
    try:
        raw = base64.b64decode(normalized + "=" * padding, validate=True)
    except ValueError as exc:
        raise ValueError(
            f"parse_address: friendly addr is not valid base64url: {addr!r}",
        ) from exc
    if len(raw) != _FRIENDLY_ADDRESS_RAW_LENGTH:
        raise ValueError(
            "parse_address: friendly addr decodes to "
            f"{len(raw)} bytes, expected {_FRIENDLY_ADDRESS_RAW_LENGTH}",
        )
    flags = raw[0]
    workchain_byte = raw[1]
    account_hash = raw[2 : 2 + _ADDRESS_HASH_BYTES]
    crc_be = raw[-2:]
    # Валидируем CRC16-XMODEM по первым 34 байтам.
    expected_crc = _crc16_xmodem(raw[:-2])
    if struct.pack(">H", expected_crc) != crc_be:
        raise ValueError(
            f"parse_address: friendly addr CRC16 mismatch (got {crc_be.hex()}, "
            f"expected {expected_crc:04x}), addr={addr!r}",
        )
    # Игнорируем bouncable / testnet-флаги — caller на этом уровне
    # этим не интересуется (он работает только с workchain + hash).
    _ = flags
    # workchain — int8 signed. byte → signed conversion.
    workchain = workchain_byte if workchain_byte < 128 else workchain_byte - 256
    return workchain, account_hash


def _crc16_xmodem(data: bytes) -> int:
    """CRC16-XMODEM (poly=0x1021, init=0x0000, no inversion, no xorout)."""
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


# ---------------------------------------------------------------------------
# BoC serialization.
# ---------------------------------------------------------------------------


def serialize_boc(root: Cell) -> bytes:
    """Сериализовать cell-дерево в минимальный TON BoC (single-root).

    Формат: ``size_bytes=1`` (≤256 cells), ``off_bytes`` адаптивный (1 или 2
    байта), без has_idx / без has_crc / без cache_bits. Этот формат
    совместим с ``Cell.to_boc(has_idx=False, hash_crc32=False,
    has_cache_bits=False, flags=0)`` из ``tonsdk`` (cross-checked в
    golden-тестах для off_bytes=1).

    `off_bytes` подбирается по минимально-необходимому: ``1`` если
    ``tot_cells_size ≤ 255``, иначе ``2`` (поддержка до ~64 KB cell-data,
    достаточно для wallet-v3R2 + TEP-74 jetton-transfer и более сложных
    message-ей).

    Поднимает ``ValueError`` при ``> 255`` cells (size_bytes=1 limit) или
    ``> 65535`` bytes cell-data (off_bytes=2 limit).
    """
    # 1. Топологическая сортировка: каждая cell идёт после своих refs.
    #    Однако TON-формат хранит references как «индекс в массиве cells,
    #    больший индекса parent-а». Это значит, что parent должен быть
    #    раньше child-а в массиве. Поэтому делаем reverse-post-order DFS.
    ordered: list[Cell] = []
    index_by_id: dict[int, int] = {}
    _visit_cell(root, ordered, index_by_id)
    cells_num = len(ordered)
    if cells_num > 0xFF:
        raise ValueError(
            f"serialize_boc: too many cells ({cells_num} > 255); size_bytes=1 supports up to 255",
        )

    # 2. Сериализуем data-секцию: для каждой cell — d1, d2, finalized-data,
    #    рефы-индексы (1 байт каждый, т.к. size_bytes=1).
    cells_bytes = bytearray()
    for cell in ordered:
        d1, d2 = cell._descriptor_bytes()
        cells_bytes.append(d1)
        cells_bytes.append(d2)
        cells_bytes.extend(cell._finalized_data())
        for ref in cell.refs:
            ref_index = index_by_id[id(ref)]
            cells_bytes.append(ref_index)
    tot_cells_size = len(cells_bytes)

    # 3. Выбираем минимальный off_bytes для упаковки tot_cells_size.
    if tot_cells_size <= 0xFF:
        off_bytes = 1
    elif tot_cells_size <= 0xFFFF:
        off_bytes = 2
    else:
        raise ValueError(
            f"serialize_boc: tot_cells_size={tot_cells_size} > 65535; "
            "off_bytes=2 cannot fit (need >=3, не поддерживаем в minimal-encoder)",
        )

    # 4. Header (минимальный):
    #    magic(4) || flag_byte(1) || off_bytes(1) || cells_num(1) ||
    #    roots_num(1) || absent_num(1) || tot_cells_size(off_bytes) ||
    #    root_idx(1).
    header = bytearray(_BOC_MAGIC)
    # flag_byte: has_idx=0, hash_crc32=0, has_cache_bits=0, flags=0, size_bytes=1.
    header.append(0b0000_0001)
    header.append(off_bytes)
    header.append(cells_num)
    header.append(1)  # roots_num = 1
    header.append(0)  # absent_num = 0
    header.extend(tot_cells_size.to_bytes(off_bytes, byteorder="big"))
    header.append(index_by_id[id(root)])  # root index (== 0 после нашего обхода)

    return bytes(header) + bytes(cells_bytes)


def _visit_cell(
    cell: Cell,
    ordered: list[Cell],
    index_by_id: dict[int, int],
) -> int:
    """Добавить cell в ``ordered`` (parent раньше child-а) и вернуть индекс.

    Цель: parent.index < child.index для каждой пары parent → ref (это
    требование TON-BoC-формата для ``size_bytes=1`` минимальной формы).
    Используем простой BFS-обход: сначала добавляем root, потом — refs,
    потом — refs-of-refs. ``id(...)`` достаточно как key, потому что
    Cell — frozen-dataclass и hashable, но равные Cell-ы по содержимому
    могут совпадать; нам же важна именно identity (одна и та же in-memory
    cell может встретиться несколько раз через разные ``store_ref``-ы,
    и мы хотим её записать один раз).
    """
    queue: list[Cell] = [cell]
    while queue:
        current = queue.pop(0)
        if id(current) in index_by_id:
            continue
        index_by_id[id(current)] = len(ordered)
        ordered.append(current)
        queue.extend(current.refs)
    return index_by_id[id(cell)]


# ---------------------------------------------------------------------------
# BoC deserialization (Спринт 4.1-E, шаг E.2).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _BocHeader:
    off_bytes: int
    cells_num: int
    root_idx: int
    cells_section: bytes


@dataclass(frozen=True, slots=True)
class _CellSpec:
    bits_count: int
    refs_count: int
    data_bytes: bytes
    ref_indices: tuple[int, ...]


def deserialize_boc(raw: bytes) -> Cell:
    """Распарсить минимальный TON BoC обратно в корневую ``Cell``.

    Симметрично к ``serialize_boc(...)`` — поддерживает single-root BoC
    с ``size_bytes=1``, ``off_bytes ∈ {1, 2}``, без has_idx / без has_crc /
    без cache_bits. Это та форма, в которой TON Center возвращает
    cell-/slice-результаты ``get_wallet_address`` и подобных
    ``runGetMethod``-вызовов.

    Padding-биты trailing-байта канонического TON-формата (`1`-разделитель
    + нули) отрезаются: возвращаемая ``Cell.bits_count`` отражает реальное
    число значащих бит.

    Поднимает ``ValueError`` при любой поломке (неверный magic /
    неподдерживаемые флаги / форвард-рефы / truncated input / выход за границы).
    """
    if not isinstance(raw, bytes | bytearray):
        raise ValueError(
            f"deserialize_boc: raw must be bytes, got {type(raw).__name__}",
        )
    header = _parse_boc_header(bytes(raw))
    specs = _parse_cell_specs(header.cells_section, header.cells_num)

    # Build Cell-objects bottom-up (highest index first), so that by the time we
    # build cell N, all its refs (indices > N) already exist. Each ref-index is
    # strictly greater than parent-index (validated in `_validate_ref_indices`),
    # therefore `cells_built[i]` for `i in spec.ref_indices` is guaranteed
    # non-None when we read it.
    cells_built: list[Cell | None] = [None] * header.cells_num
    for cell_index in reversed(range(header.cells_num)):
        spec = specs[cell_index]
        ref_cells: list[Cell] = []
        for i in spec.ref_indices:
            built = cells_built[i]
            if built is None:  # pragma: no cover — guarded by reverse-iteration order
                raise ValueError(
                    f"deserialize_boc: cell {cell_index} ref-target {i} not yet built",
                )
            ref_cells.append(built)
        cells_built[cell_index] = Cell(
            bits=spec.data_bytes,
            bits_count=spec.bits_count,
            refs=tuple(ref_cells),
        )

    root_cell = cells_built[header.root_idx]
    if root_cell is None:  # pragma: no cover — guarded by cells_num >= 1 + root_idx < cells_num
        raise ValueError("deserialize_boc: root cell unexpectedly missing after second pass")
    return root_cell


def _parse_boc_header(raw: bytes) -> _BocHeader:
    """Разобрать BoC-хедер: валидировать флаги + извлечь секцию ячеек.

    Поддерживаем только single-root + size_bytes=1 + off_bytes ∈ {1, 2}.
    См. ``deserialize_boc`` для полного контракта.
    """
    min_header_len = len(_BOC_MAGIC) + 6  # magic + flag + off + cells + roots + absent
    if len(raw) < min_header_len:
        raise ValueError(
            f"deserialize_boc: input too short ({len(raw)} bytes; minimal header = {min_header_len} bytes)",
        )
    if raw[: len(_BOC_MAGIC)] != _BOC_MAGIC:
        raise ValueError(
            f"deserialize_boc: invalid BoC magic (got {raw[:4].hex()}, expected b5ee9c72)",
        )

    cursor = len(_BOC_MAGIC)
    flag_byte = raw[cursor]
    cursor += 1
    if flag_byte & 0b1110_0000 or (flag_byte >> 3) & 0b0000_0011:
        raise ValueError(
            f"deserialize_boc: unsupported flag-byte {flag_byte:#010b} "
            "(has_idx/hash_crc32/has_cache_bits/flags not supported in minimal-decoder)",
        )
    if (flag_byte & 0b0000_0111) != 1:
        raise ValueError(
            f"deserialize_boc: size_bytes={flag_byte & 0b0000_0111} not supported (only 1)",
        )

    off_bytes = raw[cursor]
    cursor += 1
    if off_bytes not in (1, 2):
        raise ValueError(
            f"deserialize_boc: off_bytes={off_bytes} not supported (only 1 or 2)",
        )

    cells_num, roots_num, absent_num = raw[cursor], raw[cursor + 1], raw[cursor + 2]
    cursor += 3
    if roots_num != 1:
        raise ValueError(f"deserialize_boc: roots_num={roots_num} not supported (only 1)")
    if absent_num != 0:
        raise ValueError(f"deserialize_boc: absent_num={absent_num} not supported (only 0)")
    if cells_num == 0:
        raise ValueError("deserialize_boc: cells_num must be >= 1")

    if cursor + off_bytes + 1 > len(raw):
        raise ValueError(
            "deserialize_boc: input truncated in header (tot_cells_size + root_idx)",
        )
    tot_cells_size = int.from_bytes(raw[cursor : cursor + off_bytes], byteorder="big")
    cursor += off_bytes
    root_idx = raw[cursor]
    cursor += 1
    if root_idx >= cells_num:
        raise ValueError(
            f"deserialize_boc: root_idx={root_idx} >= cells_num={cells_num}",
        )

    cells_section = raw[cursor : cursor + tot_cells_size]
    if len(cells_section) != tot_cells_size:
        raise ValueError(
            f"deserialize_boc: cells-section truncated (need {tot_cells_size} bytes, "
            f"got {len(cells_section)})",
        )
    return _BocHeader(
        off_bytes=off_bytes,
        cells_num=cells_num,
        root_idx=root_idx,
        cells_section=bytes(cells_section),
    )


def _parse_cell_specs(cells_section: bytes, cells_num: int) -> list[_CellSpec]:
    """Разобрать секцию ячеек в список `_CellSpec`-ов.

    `Cell`-объекты эта функция ещё не строит (refs - forward-only); caller
    собирает их bottom-up.
    """
    specs: list[_CellSpec] = []
    cursor = 0
    tot_size = len(cells_section)
    for cell_index in range(cells_num):
        cursor, spec = _parse_one_cell_spec(
            cells_section,
            cursor,
            cell_index,
            cells_num,
            tot_size,
        )
        specs.append(spec)
    if cursor != tot_size:
        raise ValueError(
            f"deserialize_boc: cells-section has {tot_size - cursor} trailing bytes",
        )
    return specs


def _parse_one_cell_spec(
    cells_section: bytes,
    cursor: int,
    cell_index: int,
    cells_num: int,
    tot_size: int,
) -> tuple[int, _CellSpec]:
    """Разобрать (d1, d2, data, refs) одной ячейки. Возвращает (new_cursor, spec)."""
    if cursor + 2 > tot_size:
        raise ValueError("deserialize_boc: cells-section truncated in descriptor")
    d1 = cells_section[cursor]
    d2 = cells_section[cursor + 1]
    cursor += 2
    if d1 & 0b0000_1000:
        raise ValueError(
            f"deserialize_boc: exotic cells not supported (cell {cell_index})",
        )
    refs_count = d1 & 0b0000_0111
    if refs_count > _MAX_REFS_PER_CELL:
        raise ValueError(
            f"deserialize_boc: cell {cell_index} has refs_count={refs_count} > 4",
        )
    is_byte_aligned, data_byte_length = _decode_d2(d2)
    if cursor + data_byte_length > tot_size:
        raise ValueError(
            f"deserialize_boc: cell {cell_index} data truncated",
        )
    data_bytes = bytes(cells_section[cursor : cursor + data_byte_length])
    cursor += data_byte_length
    if cursor + refs_count > tot_size:
        raise ValueError(f"deserialize_boc: cell {cell_index} ref-table truncated")
    ref_indices = tuple(cells_section[cursor + j] for j in range(refs_count))
    cursor += refs_count
    _validate_ref_indices(ref_indices, cell_index, cells_num)
    if is_byte_aligned or data_byte_length == 0:
        bits_count = data_byte_length * 8
    else:
        bits_count, data_bytes = _recover_bits_count_and_strip_padding(
            data_bytes,
            data_byte_length,
        )
    return cursor, _CellSpec(
        bits_count=bits_count,
        refs_count=refs_count,
        data_bytes=data_bytes,
        ref_indices=ref_indices,
    )


def _validate_ref_indices(
    ref_indices: tuple[int, ...],
    cell_index: int,
    cells_num: int,
) -> None:
    """Forward-only constraint: parent.index < child.index < cells_num."""
    for ref_idx in ref_indices:
        if ref_idx <= cell_index:
            raise ValueError(
                f"deserialize_boc: cell {cell_index} references "
                f"cell {ref_idx} (must be strictly greater than parent index)",
            )
        if ref_idx >= cells_num:
            raise ValueError(
                f"deserialize_boc: cell {cell_index} references "
                f"cell {ref_idx} >= cells_num={cells_num}",
            )


def _decode_d2(d2: int) -> tuple[bool, int]:
    """Декодировать ``d2`` дескриптор в ``(is_byte_aligned, data_byte_length)``.

    ``d2 = floor(bits_count / 8) + ceil(bits_count / 8)``:
    * для byte-aligned (``bits_count % 8 == 0``) — чётный, ``data_byte_length = d2 / 2``;
    * для non-aligned — нечётный, ``data_byte_length = (d2 + 1) / 2``;
      точный ``bits_count`` восстановим из padding `1`-бита в последнем байте.
    """
    data_byte_length = (d2 + 1) // 2
    is_byte_aligned = d2 % 2 == 0
    return is_byte_aligned, data_byte_length


def _recover_bits_count_and_strip_padding(
    data: bytes,
    data_byte_length: int,
) -> tuple[int, bytes]:
    """Восстановить ``bits_count`` для non-aligned cell-а + срезать TON-padding.

    Padding-схема: за последним значащим битом cell-а ставится `1`,
    дальше — нули до конца последнего байта. Поэтому позиция самого
    младшего set-бита последнего байта = позиция padding-`1`-бита,
    а ``bits_count = (data_byte_length - 1) * 8 + (7 - pad_pos)``.

    Возвращает ``(bits_count, data_bytes_with_padding_cleared)``.
    Поднимает ``ValueError``, если последний байт = `0` (тогда нет
    padding-`1`-бита — нарушение TON-protocol-а).
    """
    last_byte_idx = data_byte_length - 1
    last_byte = data[last_byte_idx]
    if last_byte == 0:
        raise ValueError(
            "deserialize_boc: non-aligned cell last byte is 0 (padding `1`-bit missing)",
        )
    pad_pos = (last_byte & -last_byte).bit_length() - 1  # 0..7, младший set-бит
    bits_count = last_byte_idx * 8 + (7 - pad_pos)
    cleared = last_byte & ~(1 << pad_pos)
    result = bytearray(data)
    result[last_byte_idx] = cleared
    return bits_count, bytes(result)


# ---------------------------------------------------------------------------
# MsgAddressInt parsing from a Cell (Спринт 4.1-E, шаг E.2).
# ---------------------------------------------------------------------------


def parse_msgaddress_int_from_cell(cell: Cell) -> tuple[int, bytes]:
    """Распарсить TL-B ``MsgAddressInt`` ``addr_std$10`` из первых 267 бит ``cell``.

    Симметрично ``CellBuilder.store_address(workchain, account_hash)``:
    структура (267 бит) — ``10`` (tag) + ``0`` (anycast None) +
    ``workchain`` (int8) + ``account_hash`` (256 бит).

    Это базовая форма, которую возвращает TON Center в ответе
    ``get_wallet_address``-вызова на jetton-master (TEP-89). Поддерживает
    оба варианта: cell содержит только адрес (267 бит) или адрес + хвост
    (просто игнорируем хвост).

    Поднимает ``ValueError`` при:
    * ``cell.bits_count < 267``;
    * tag != ``0b10`` (это не addr_std);
    * anycast != ``0`` (этот upstream-вариант не поддерживаем).
    """
    if cell.bits_count < 267:
        raise ValueError(
            f"parse_msgaddress_int_from_cell: need >= 267 bits for addr_std$10, "
            f"got {cell.bits_count}",
        )
    bits = _read_bits(cell.bits, count=11)  # tag(2) + anycast(1) + workchain(8)
    tag = (bits >> 9) & 0b11
    anycast = (bits >> 8) & 0b1
    workchain_byte = bits & 0xFF
    if tag != 0b10:
        raise ValueError(
            f"parse_msgaddress_int_from_cell: tag={tag:02b} != 10 (only addr_std$10 supported)",
        )
    if anycast != 0:
        raise ValueError(
            "parse_msgaddress_int_from_cell: anycast addresses not supported (only Maybe None)",
        )
    # workchain — int8 (signed).
    workchain = workchain_byte if workchain_byte < 128 else workchain_byte - 256
    # Read 256 bits of account_hash starting from bit-offset 11.
    account_hash = _read_bit_slice(cell.bits, bit_offset=11, bit_count=256)
    return workchain, account_hash


def _read_bits(data: bytes, *, count: int) -> int:
    """Прочитать первые ``count`` бит из ``data`` как big-endian uint.

    ``count`` должен быть ``<= 64``. Bits packed left-to-right (MSB first).
    """
    if count == 0:
        return 0
    full_bytes = count // 8
    rem = count % 8
    value = 0
    for i in range(full_bytes):
        value = (value << 8) | data[i]
    if rem:
        last = data[full_bytes] >> (8 - rem)
        value = (value << rem) | last
    return value


def _read_bit_slice(data: bytes, *, bit_offset: int, bit_count: int) -> bytes:
    """Прочитать ``bit_count`` бит из ``data`` начиная с ``bit_offset``,
    вернуть как big-endian byte-string длины ``ceil(bit_count / 8)``.
    """
    if bit_count == 0:
        return b""
    end_bit = bit_offset + bit_count
    if (end_bit + 7) // 8 > len(data):
        raise ValueError(
            f"_read_bit_slice: data has {len(data)} bytes, "
            f"need at least {(end_bit + 7) // 8} for bit_offset={bit_offset} + bit_count={bit_count}",
        )
    # Bit-shift подход: собираем биты в bigint, потом упаковываем в bytes.
    skip_bytes = bit_offset // 8
    skip_rem = bit_offset % 8
    work_bytes = data[skip_bytes : (end_bit + 7) // 8]
    value = int.from_bytes(work_bytes, byteorder="big")
    total_bits = len(work_bytes) * 8
    # Сдвигаем вправо, чтобы откинуть лишние биты в конце.
    trailing_bits = total_bits - skip_rem - bit_count
    value >>= trailing_bits
    # Маскируем верхние биты (skip_rem).
    value &= (1 << bit_count) - 1
    out_byte_length = (bit_count + 7) // 8
    # Если bit_count % 8 != 0, выравниваем по верхнему биту.
    leftover = bit_count % 8
    if leftover != 0:
        value <<= 8 - leftover
    return value.to_bytes(out_byte_length, byteorder="big")


def format_raw_address(workchain: int, account_hash: bytes) -> str:
    """Сформатировать ``(workchain, account_hash)`` в raw-форму ``"<wc>:<hex>"``.

    Симметрично к ``_parse_raw_address(addr)``. ``account_hash`` должен быть
    ровно 32 байта; ``workchain`` — int8 (-128..127). Hex выводится в
    нижнем регистре (стандартная convention TON Center).
    """
    if not -128 <= workchain <= 127:
        raise ValueError(
            f"format_raw_address: workchain must fit in int8, got {workchain}",
        )
    if len(account_hash) != _ADDRESS_HASH_BYTES:
        raise ValueError(
            f"format_raw_address: account_hash must be {_ADDRESS_HASH_BYTES} bytes, "
            f"got {len(account_hash)}",
        )
    return f"{workchain}:{account_hash.hex()}"
