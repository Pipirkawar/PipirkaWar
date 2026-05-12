"""Value-объекты доменного слоя монетизации (ГДД §12.5–§12.6, Спринт 4.1-A).

Иммутабельные VO:

* `Currency` (StrEnum) — три валюты приёма платежей: Telegram Stars
  (`STARS`), TON (`TON_NANO` — нано-тонкоины как `int`), USDT
  (`USDT_DECIMAL` — `Decimal`-минор-юниты, jetton-decimals=6 на TON).
  `value` — машинный id, попадает в `payments.currency` и в
  `audit_log.payload.currency` (Спринт 4.1-A migration `0026`). Не менять
  без миграции.
* `StarsAmount(int, > 0)` — вокруг положительного `int` (TG Stars
  всегда целое количество ⭐, дробных нет; ГДД §12.5.1: `1⭐` /
  `9⭐`-pack). Frozen-VO; защищает от случайного «0 ⭐» / «-1 ⭐»
  на доменной границе и гарантирует сохранность инварианта при
  сериализации в `payments.amount_native`.
* `IdempotencyKey` — строковый VO с валидируемым форматом
  `[A-Za-z0-9_-]{1,64}` (защита от инъекций в SQL и от чрезмерно
  длинных ключей в `UNIQUE`-индексе `payments.idempotency_key`).
  Конкретный формат генерации ключа — на стороне application-слоя
  (use-case `SpinPaidRoulette` использует `"paid_roulette:{player}:
  {tg_payment_charge_id}"`), но валидация формата живёт здесь, ближе
  к VO, чтобы invariant держался независимо от вызывающего кода.

Все VO — `frozen=True, slots=True` (см. конвенцию
`domain/roulette/entities.py::RouletteOutcome`). Frozen + slots даёт
нам неизменяемость, hashability и нулевой `__dict__`-overhead;
сравнение по полям — «два одинаковых ключа == друг другу».
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

__all__ = [
    "Currency",
    "FeeBufferAmount",
    "IdempotencyKey",
    "PayoutLimitCheckResult",
    "PayoutLimitOverLimit",
    "PayoutLimitWithin",
    "StarsAmount",
    "StarsPayload",
    "StarsPoolBalance",
    "TonAddress",
    "TonNanoAmount",
    "TonProof",
    "UsdtDecimalAmount",
    "UsdtJettonAddress",
]


class Currency(StrEnum):
    """Поддерживаемые валюты приёма платежей (ГДД §12.5.1, §12.6).

    `STARS` — Telegram Stars, целочисленные единицы (`int >= 1`).
    `TON_NANO` — TON, нано-тонкоины (`int >= 1`; 1 TON = 10**9 nano-TON).
    `USDT_DECIMAL` — USDT через TON-сеть (jetton-decimals=6;
    1 USDT = 10**6 минор-юнит). На уровне БД хранится как
    `NUMERIC(38, 0)` без потери точности (Спринт 4.1-A migration `0026`).

    Стабильные машинные id, попадают в `payments.currency` (CHECK-constraint
    `payments_currency_whitelist`) и в `audit_log.payload.currency`. Не
    менять без миграции.
    """

    STARS = "stars"
    TON_NANO = "ton_nano"
    USDT_DECIMAL = "usdt_decimal"


@dataclass(frozen=True, slots=True)
class StarsAmount:
    """Положительное целое количество Telegram Stars (ГДД §12.5.1).

    Поле `value: int` — количество ⭐ (`>= 1`). VO защищает от случайных
    нулевых / отрицательных значений на доменной границе и гарантирует
    инвариант при сериализации в `payments.amount_native: NUMERIC(38, 0)`.

    Использование: `StarsAmount(1)` (single spin), `StarsAmount(9)`
    (10-pack). Любое значение `<= 0` → `ValueError` в `__post_init__`.

    Frozen + slots → VO без identity, hashable, безопасно сравнивать `==`.
    """

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError(
                f"StarsAmount.value must be int, got {type(self.value).__name__}",
            )
        if self.value < 1:
            raise ValueError(
                f"StarsAmount.value must be >= 1, got {self.value}",
            )


@dataclass(frozen=True, slots=True)
class StarsPoolBalance:
    """Неотрицательный баланс пула Telegram Stars (ГДД §12.6, Спринт 4.1-B).

    Поле `value: int` — сколько ⋆ лежит в призовом пуле (`>= 0`,
    пустой пул — это ок). Почему отдельный VO, а не `StarsAmount`:
    `StarsAmount.value >= 1` по своей семантике (размер одного
    платежа — не может быть нулевым, Спринт 4.1-A); «cуммарный баланс
    пула» имеет другую семантику и разрешает ноль (свежезаведённый
    seed-row в `prize_pool_balance` — 0 ⋆).

    Frozen + slots → VO без identity, hashable, безопасно сравнивать `==`.
    """

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError(
                f"StarsPoolBalance.value must be int, got {type(self.value).__name__}",
            )
        if self.value < 0:
            raise ValueError(
                f"StarsPoolBalance.value must be >= 0, got {self.value}",
            )


@dataclass(frozen=True, slots=True)
class TonNanoAmount:
    """Неотрицательное целое число нано-тонкоинов (ГДД §12.6, Спринт 4.1-B).

    Поле `value: int` — количество нано-тонкоинов (`>= 0`;
    `1 TON = 10**9 nano-TON`). Используется как баланс пула
    (`PrizePool.ton_nano`) и как входная сумма инкремента. На
    уровне БД хранится как `NUMERIC(38, 0)` без потери точности
    (Спринт 4.1-B миграция `0027`).

    Разрешает ноль (пустой пул / нулевой инкремент = noop). Для «размера
    платежа» — введём в 4.1-D свой VO с `>= 1`-инвариантом
    (аналогично `StarsAmount`).

    Frozen + slots → VO без identity, hashable, безопасно сравнивать `==`.
    """

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError(
                f"TonNanoAmount.value must be int, got {type(self.value).__name__}",
            )
        if self.value < 0:
            raise ValueError(
                f"TonNanoAmount.value must be >= 0, got {self.value}",
            )


@dataclass(frozen=True, slots=True)
class UsdtDecimalAmount:
    """Неотрицательное целое число минор-юнит USDT (ГДД §12.6, Спринт 4.1-B).

    Поле `value: int` — количество минор-юнит USDT-jetton (`>= 0`;
    `1 USDT = 10**6` юнит при `decimals=6`). Используется как баланс
    пула (`PrizePool.usdt_decimal`) и как входная сумма инкремента.
    На уровне БД хранится как `NUMERIC(38, 0)` без потери точности.

    Разрешает ноль (пустой пул / нулевой инкремент = noop). Для «размера
    платежа» — введём в 4.1-D свой VO с `>= 1`-инвариантом.

    Frozen + slots → VO без identity, hashable, безопасно сравнивать `==`.
    """

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError(
                f"UsdtDecimalAmount.value must be int, got {type(self.value).__name__}",
            )
        if self.value < 0:
            raise ValueError(
                f"UsdtDecimalAmount.value must be >= 0, got {self.value}",
            )


@dataclass(frozen=True, slots=True)
class FeeBufferAmount:
    """Неотрицательный целочисленный буфер комиссии лота (ГДД §12.6.3, Спринт 4.1-C).

    Поле `value: int` — заложенный в `PrizeLot` буфер на оплату сетевой
    комиссии (`>= 0`; для STARS-лотов обычно `0`, для TON / USDT —
    P95-аппроксимация газа за последние 7 дней, источник —
    `IFeeEstimator.estimate_fee(...)`).

    Семантика на уровне `PrizeLot`: invariant
    `amount_native > fee_buffer_native >= 0` гарантирует, что при
    выводе приза в 4.1-D на руки игроку остаётся `amount_native -
    fee_buffer_native >= 1`-натив-юнит после удержания комиссии.

    Frozen + slots → VO без identity, hashable, безопасно сравнивать `==`.
    """

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError(
                f"FeeBufferAmount.value must be int, got {type(self.value).__name__}",
            )
        if self.value < 0:
            raise ValueError(
                f"FeeBufferAmount.value must be >= 0, got {self.value}",
            )


_IDEMPOTENCY_KEY_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_\-:]{1,64}$")


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """Идемпотентный ключ платежа (ГДД §12.5.1, антифрод 4.1.4).

    Поле `value: str` — `[A-Za-z0-9_\\-:]{1,64}`. Запрещает SQL-инъекции
    и слишком длинные ключи в `UNIQUE (player_id, idempotency_key)`-
    индексе `payments`-таблицы (Спринт 4.1-A migration `0026`).

    Двоеточие `:` в whitelist-е оставлено намеренно: application-слой
    генерирует ключи вида `"paid_roulette:{player_id}:{tg_payment_charge_id}"`
    (use-case `SpinPaidRoulette`).

    Use-case `SpinPaidRoulette` (Спринт 4.1-A) при повторном вызове с
    тем же `IdempotencyKey` возвращает существующий receipt без
    повторного списания (антифрод; ГДД §12.5.1, плана 4.1.4). Если ключ
    есть, но с другой суммой / игроком — `IdempotencyConflictError`
    (см. `errors.py`).

    Frozen + slots → VO без identity, hashable, безопасно сравнивать `==`.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(
                f"IdempotencyKey.value must be str, got {type(self.value).__name__}",
            )
        if not _IDEMPOTENCY_KEY_RE.fullmatch(self.value):
            raise ValueError(
                f"IdempotencyKey.value must match [A-Za-z0-9_-:]{{1,64}}, got {self.value!r}",
            )


# ---------------------------------------------------------------------------
# TON-адреса  (ГДД §12.6.4, Спринт 4.1-D)
# ---------------------------------------------------------------------------

# User-friendly TON-address: 48 base64url characters (0:[32 bytes hex] raw
# form is 66 chars, but user-friendly is always 48 chars base64url, starting
# with 'E' / 'U' / '0' etc.).  We accept both raw (`0:hex{64}`) and
# user-friendly (48-char base64url) formats.
_TON_RAW_RE: re.Pattern[str] = re.compile(r"^-?[0-9]+:[0-9a-fA-F]{64}$")
_TON_FRIENDLY_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_\-+/]{48}$")


@dataclass(frozen=True, slots=True)
class TonAddress:
    """Адрес TON-кошелька игрока (ГДД §12.6.4, Спринт 4.1-D).

    Принимает два формата:
    * Raw — ``<workchain>:<hex64>`` (e.g. ``0:abcdef...``);
    * User-friendly — 48-символьный base64url (e.g.
      ``EQD...``).

    Frozen + slots → VO без identity, hashable, безопасно сравнивать ``==``.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(
                f"TonAddress.value must be str, got {type(self.value).__name__}",
            )
        if not (_TON_RAW_RE.fullmatch(self.value) or _TON_FRIENDLY_RE.fullmatch(self.value)):
            raise ValueError(
                f"TonAddress.value must be a valid TON address "
                f"(raw or user-friendly), got {self.value!r}",
            )


@dataclass(frozen=True, slots=True)
class UsdtJettonAddress:
    """Адрес USDT-jetton-кошелька на сети TON (ГДД §12.6.4, Спринт 4.1-D).

    Формат идентичен ``TonAddress`` (USDT на TON — это jetton, кошелёк
    которого адресуется стандартным TON-адресом). Отдельный VO для
    type-safety: caller не может случайно подставить ``TonAddress``
    вместо ``UsdtJettonAddress`` (Liskov violation предотвращён).

    Frozen + slots → VO без identity, hashable, безопасно сравнивать ``==``.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(
                f"UsdtJettonAddress.value must be str, got {type(self.value).__name__}",
            )
        if not (_TON_RAW_RE.fullmatch(self.value) or _TON_FRIENDLY_RE.fullmatch(self.value)):
            raise ValueError(
                f"UsdtJettonAddress.value must be a valid TON address "
                f"(raw or user-friendly), got {self.value!r}",
            )


# ---------------------------------------------------------------------------
# Telegram Stars signed payload  (4.1-A handler выводится в продакшн в 4.1-D, шаг D.8)
# ---------------------------------------------------------------------------

# `idempotency_seed` — серверный nonce, зашитый в `invoice_payload` при
# `bot.send_invoice(...)`. На `successful_payment` верификатор проверяет
# HMAC и возвращает `StarsPayload(pack, idempotency_seed)`; use-case строит
# `IdempotencyKey` из `(player_id, telegram_payment_charge_id)` и сверяет
# `idempotency_seed` как часть антифрод-валидации. Длина 16-32 символа
# (достаточно энтропии, помещается в 128-байтовый лимит invoice_payload
# вместе с pack-meta и HMAC).
_IDEMPOTENCY_SEED_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_\-]{16,32}$")


@dataclass(frozen=True, slots=True)
class StarsPayload:
    """Декодированный и проверенный invoice-payload TG Stars (4.1-D, шаг D.8).

    Skeleton-handler 4.1-A принимал «голый» `invoice_payload` строкой
    (формат `paid_roulette:<pack>`) и доверял Telegram-callback-у без
    серверной верификации. В продакшне (шаг D.8) сервер подписывает
    payload HMAC-SHA256-ом по `(provider_id, idempotency_key, amount,
    currency)`, что закрывает подмену payload-а между созданием invoice-а
    и приёмом `successful_payment` (детали — `ITgStarsPayloadVerifier`).

    `StarsPayload` — результат успешной верификации:

    * `pack_value: str` — машинный id `PaidRoulettePack` (`single` /
      `pack_10`). Хранится строкой (а не `PaidRoulettePack`-enum-ом),
      чтобы доменный пакет монетизации не зависел от
      application-слоя (`PaidRoulettePack` живёт в
      `pipirik_wars.application.monetization`); caller (handler 4.1-A)
      сам мапит строку в enum.
    * `idempotency_seed: str` — серверный nonce, зашитый в `invoice_payload`
      при создании invoice-а. `[A-Za-z0-9_-]{16,32}`. Verifier обязан
      сверить HMAC поверх `seed`-а; use-case дополнительно использует
      `seed` как часть scope-а audit-payload-а (debug-trace «какой
      invoice сработал»).

    Frozen + slots → VO без identity, hashable, безопасно сравнивать ``==``.
    """

    pack_value: str
    idempotency_seed: str

    def __post_init__(self) -> None:
        if not isinstance(self.pack_value, str):
            raise TypeError(
                f"StarsPayload.pack_value must be str, got {type(self.pack_value).__name__}",
            )
        if not self.pack_value:
            raise ValueError("StarsPayload.pack_value must be non-empty")
        if not isinstance(self.idempotency_seed, str):
            raise TypeError(
                "StarsPayload.idempotency_seed must be str, "
                f"got {type(self.idempotency_seed).__name__}",
            )
        if not _IDEMPOTENCY_SEED_RE.fullmatch(self.idempotency_seed):
            raise ValueError(
                "StarsPayload.idempotency_seed must match "
                f"[A-Za-z0-9_-]{{16,32}}, got {self.idempotency_seed!r}",
            )


@dataclass(frozen=True, slots=True)
class PayoutLimitWithin:
    """Игрок укладывается в rolling-window-лимит выплат (ГДД §12.6.5, Спринт 4.1-E).

    Результат успешной проверки ``IPayoutLimitChecker.check(...)``. Use-case
    ``ClaimPrize`` (E.10) при получении этого результата продолжает выплату
    как обычно; админ-use-case ``GetPrizePoolStatus`` (E.9) использует
    ``remaining_native`` для печати «осталось N USDT до месячного лимита».

    Поле ``remaining_native: int`` — сколько ещё native-юнитов игрок может
    получить в текущем rolling-окне (``>= 0``). При omitted-в-конфиге
    currency (=unlimited) реализация возвращает большой sentinel-int
    (`sys.maxsize`), но граница `>= 0` гарантирована.

    Frozen + slots → VO без identity, hashable, безопасно сравнивать ``==``.
    """

    remaining_native: int

    def __post_init__(self) -> None:
        if not isinstance(self.remaining_native, int) or isinstance(
            self.remaining_native,
            bool,
        ):
            raise TypeError(
                "PayoutLimitWithin.remaining_native must be int, "
                f"got {type(self.remaining_native).__name__}",
            )
        if self.remaining_native < 0:
            raise ValueError(
                f"PayoutLimitWithin.remaining_native must be >= 0, got {self.remaining_native}",
            )


@dataclass(frozen=True, slots=True)
class PayoutLimitOverLimit:
    """Игрок превысил rolling-window-лимит выплат (ГДД §12.6.5, Спринт 4.1-E).

    Результат проверки ``IPayoutLimitChecker.check(...)`` в случае, когда
    суммарный выплаченный объём за окно + текущий запрос превышает
    ``max_amount_native``. Use-case ``ClaimPrize`` (E.10) при получении
    этого результата ставит лот в over-limit-очередь (E.11) и сообщает
    игроку, когда можно повторить попытку (через локаль presenter-а).

    Поля:

    * ``retry_after: datetime`` — TZ-aware момент, в который самая ранняя
      выплата в окне выпадет из rolling-окна (``oldest_claim_at +
      window_days``). После этого момента игрок может повторить
      ``/claim_prize`` и проверка снова даст ``PayoutLimitWithin``.
    * ``exceeded_by_native: int`` — насколько (в native-юнитах) запрос
      превышает оставшийся лимит. ``>= 1``: «ровно столько native
      нужно сэкономить, чтобы уложиться». Используется в presenter-е
      ``/prize_pool`` / ``/claim_prize``-ошибки для диагностики.

    Frozen + slots → VO без identity, hashable, безопасно сравнивать ``==``.
    """

    retry_after: datetime
    exceeded_by_native: int

    def __post_init__(self) -> None:
        if not isinstance(self.retry_after, datetime):
            raise TypeError(
                "PayoutLimitOverLimit.retry_after must be datetime, "
                f"got {type(self.retry_after).__name__}",
            )
        if self.retry_after.tzinfo is None:
            raise ValueError(
                "PayoutLimitOverLimit.retry_after must be timezone-aware "
                "(naïve datetime would lose UTC offset on persistence)",
            )
        if not isinstance(self.exceeded_by_native, int) or isinstance(
            self.exceeded_by_native,
            bool,
        ):
            raise TypeError(
                "PayoutLimitOverLimit.exceeded_by_native must be int, "
                f"got {type(self.exceeded_by_native).__name__}",
            )
        if self.exceeded_by_native < 1:
            raise ValueError(
                "PayoutLimitOverLimit.exceeded_by_native must be >= 1, "
                f"got {self.exceeded_by_native}",
            )


PayoutLimitCheckResult = PayoutLimitWithin | PayoutLimitOverLimit
"""Sum-type результата ``IPayoutLimitChecker.check(...)`` (Спринт 4.1-E).

Use-case ``ClaimPrize`` (E.10) выполняет ``match`` по этому результату:
``Within`` → продолжить выплату; ``OverLimit`` → перевести лот в очередь.
"""


# ---------------------------------------------------------------------------
# TON Connect 2.0 ton_proof  (Спринт 4.1-F)
# ---------------------------------------------------------------------------

# Domain-value в TON Connect proof — utf8-имя хоста dApp-а, который просил
# подпись («origin» без схемы: ``pipirik.example.com``, но может включать
# порт ``:8443``). По спеке это произвольная utf8-строка с полем
# ``lengthBytes`` = длина в байтах. Для безопасности ограничиваем формат именем
# хоста (RFC 1123-like: буквы/цифры/точки/дефисы/двоеточия для порта)
# — это резальный срез ``allowed_domains``-whitelist-а в верификаторе (F.5.c),
# но в домене мы хотим базовый sanity-check поверх utf8-строки.
_TON_PROOF_DOMAIN_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._:\-]{1,253}$")

# Payload — серверный nonce, выданный в phase-1 (`RequestLinkWalletProof`-use-
# case-е). По спеке — произвольные байты, но мы из INonceStore выдаём
# ASCII-printable nonce (`secrets.token_urlsafe(24)` = 32-байтная строка).
# Ограничиваем [1, 512] как sanity-check.
_TON_PROOF_PAYLOAD_RE: re.Pattern[str] = re.compile(r"^[\x20-\x7e]{1,512}$")

# Ed25519: signature — 64 байта, public-key — 32 байта.
_ED25519_SIGNATURE_BYTES: int = 64
_ED25519_PUBLIC_KEY_BYTES: int = 32

# Hex-encoded Ed25519 public key — 64 hex-символа (32 байта).
_TON_PROOF_PUBKEY_HEX_RE: re.Pattern[str] = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True, slots=True)
class TonProof:
    """Parsed TON Connect 2.0 ``ton_proof`` (Спринт 4.1-F).

    Связанная информация, полученная от кошелькового приложения по
    спеке https://docs.ton.org/develop/dapps/ton-connect/sign. Пришёл
    от игрока как JSON-строка в хендлере ``/link_wallet_confirm``;
    Infrastructure-парсер в ``infrastructure/payments/ton_connect/
    proof_parser.py`` (F.5.a) превращает JSON в этот VO, ловя все
    ``ValueError`` / ``TypeError`` и диспетчеризируя их в ``TonProofMalformedError``
    с машино-читаемым ``reason``.

    Поля:

    * ``timestamp: int`` — Unix seconds (UTC) когда кошелёк подписал proof.
      Равно ``> 0``. Окно ``[now - max_age, now]`` проверяет F.5.c,
      не домен-VO (домен не знает «now» — только базовый инвариант типа).
    * ``domain_value: str`` — utf8-имя хоста dApp-а (является частью
      canonical-message при верификации в F.5.b). Проверяется общий
      формат (RFC 1123-like + порт); whitelist-мэтч — в F.5.c.
    * ``payload: str`` — server-изданный nonce (`RequestLinkWalletProof`-
      use-case-ом в F.4.a). ASCII-printable, [1, 512] символов.
      Replay-protection — в F.4.b (consume в ``LinkWallet``).
    * ``signature_b64: str`` — raw Ed25519-signature, base64-encoded. Равна
      64 байтам после декода. Сама верификация через ``pynacl.
      VerifyKey.verify(...)`` — в F.5.c.
    * ``public_key_hex: str`` — Ed25519-public-key кошелька, hex-encoded.
      Равен 64 hex-символам (32 байта raw).
    * ``address: str`` — TON-адрес кошелька в raw-формате ``workchain:hex64``
      (является частью canonical-message). Не user-friendly-формат (b64url)
      — потому что canonical-message-билдер (F.5.b) работает с workchain-
      ом и address-hash по отдельности.
    * ``state_init_b64: str | None`` — опциональный BoC кошелькового
      state_init (база для address-from-pubkey-recovery; этот путь
      вынесён в backlog 4.1-G). Если задан — валидный base64.

    Frozen + slots → VO без identity, hashable, безопасно сравнивать ``==``.
    """

    timestamp: int
    domain_value: str
    payload: str
    signature_b64: str
    public_key_hex: str
    address: str
    state_init_b64: str | None = None

    def __post_init__(self) -> None:  # noqa: PLR0912 — линейная цепочка инвариантов VO
        # timestamp — строго int (не bool), > 0.
        if not isinstance(self.timestamp, int) or isinstance(self.timestamp, bool):
            raise TypeError(
                f"TonProof.timestamp must be int, got {type(self.timestamp).__name__}",
            )
        if self.timestamp <= 0:
            raise ValueError(
                f"TonProof.timestamp must be > 0 (Unix seconds), got {self.timestamp}",
            )

        # domain_value — непустая utf8-строка, host-like формат.
        if not isinstance(self.domain_value, str):
            raise TypeError(
                f"TonProof.domain_value must be str, got {type(self.domain_value).__name__}",
            )
        if not _TON_PROOF_DOMAIN_RE.fullmatch(self.domain_value):
            raise ValueError(
                f"TonProof.domain_value must match {_TON_PROOF_DOMAIN_RE.pattern!r}, "
                f"got {self.domain_value!r}",
            )

        # payload — ASCII-printable, [1, 512] символов.
        if not isinstance(self.payload, str):
            raise TypeError(
                f"TonProof.payload must be str, got {type(self.payload).__name__}",
            )
        if not _TON_PROOF_PAYLOAD_RE.fullmatch(self.payload):
            raise ValueError(
                f"TonProof.payload must match {_TON_PROOF_PAYLOAD_RE.pattern!r}, "
                f"got len={len(self.payload)} payload={self.payload!r}",
            )

        # signature_b64 — валидный base64, декодируется в 64 байта.
        if not isinstance(self.signature_b64, str):
            raise TypeError(
                f"TonProof.signature_b64 must be str, got {type(self.signature_b64).__name__}",
            )
        try:
            sig_bytes = base64.b64decode(self.signature_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(
                f"TonProof.signature_b64 must be valid base64, got {self.signature_b64!r}",
            ) from exc
        if len(sig_bytes) != _ED25519_SIGNATURE_BYTES:
            raise ValueError(
                f"TonProof.signature_b64 must decode to {_ED25519_SIGNATURE_BYTES} bytes "
                f"(Ed25519 signature), got {len(sig_bytes)} bytes",
            )

        # public_key_hex — 64 hex-символа (32 байта Ed25519 public key).
        if not isinstance(self.public_key_hex, str):
            raise TypeError(
                f"TonProof.public_key_hex must be str, got {type(self.public_key_hex).__name__}",
            )
        if not _TON_PROOF_PUBKEY_HEX_RE.fullmatch(self.public_key_hex):
            raise ValueError(
                f"TonProof.public_key_hex must be {_ED25519_PUBLIC_KEY_BYTES * 2} hex chars "
                f"({_ED25519_PUBLIC_KEY_BYTES} bytes Ed25519 public key), "
                f"got {self.public_key_hex!r}",
            )

        # address — только raw-формат «workchain:hex64» (canonical-message-
        # builder в F.5.b работает именно с этим форматом).
        if not isinstance(self.address, str):
            raise TypeError(
                f"TonProof.address must be str, got {type(self.address).__name__}",
            )
        if not _TON_RAW_RE.fullmatch(self.address):
            raise ValueError(
                "TonProof.address must be in raw form 'workchain:hex64' "
                f"(canonical-message requires raw form), got {self.address!r}",
            )

        # state_init_b64 — опциональный валидный base64 (если задан).
        if self.state_init_b64 is not None:
            if not isinstance(self.state_init_b64, str):
                raise TypeError(
                    "TonProof.state_init_b64 must be str | None, "
                    f"got {type(self.state_init_b64).__name__}",
                )
            try:
                base64.b64decode(self.state_init_b64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError(
                    f"TonProof.state_init_b64 must be valid base64, got {self.state_init_b64!r}",
                ) from exc
