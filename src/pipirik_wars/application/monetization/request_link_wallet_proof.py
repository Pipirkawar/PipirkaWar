"""Use-case ``RequestLinkWalletProof`` (Спринт 4.1-F, шаг F.4.a).

Phase-1 двухфазного flow привязки TON-кошелька (`/link_wallet` →
`/link_wallet_confirm`). До F.4.a flow был **однофазным**: игрок сразу
присылал `proof: str` из своего TonConnect-app-а и `LinkWallet`-use-case
синхронно его верифицировал через ``ITonConnectVerifier.verify(...)``.
Это работало с ``SandboxTonConnectVerifier`` (D.10.c), но НЕ закрывает
replay-атаки: тот же `proof` мог быть переподан второй раз.

Сейчас F.4.a/b разделяет flow на две фазы:

* **Phase-1** (``RequestLinkWalletProof``, этот файл): сервер генерирует
  криптографически-сильный nonce через ``secrets.token_urlsafe(24)``
  (32-байтовая URL-safe-строка), привязывает к ``scope =
  "link_wallet:{player_id}:{currency}"`` и сохраняет в ``INonceStore``
  с TTL (default 5 минут — настраивается через `config.nonce_ttl_seconds`).
  Возвращает игроку ``RequestLinkWalletProofResult(nonce, domain,
  expires_at, scope)`` — handler 4.1-F (F.8.a) превратит это в
  human-readable инструкцию: «возьмите этот nonce, подпишите его в
  TonConnect-app, пришлите proof обратно командой
  `/link_wallet_confirm <proof-json>`».
* **Phase-2** (``LinkWallet`` after F.4.b): use-case верифицирует
  ton_proof через production-verifier (F.5.c) и атомарно
  ``consume_nonce(scope, nonce)`` через ``INonceStore``. Замена
  `SandboxTonConnectVerifier`-stub-а — отдельный шаг F.7
  (composition root config-switch).

Этот use-case **не выполняет verify**, он только готовит площадку для
phase-2. Никаких `IWalletRepository` / `ITonConnectVerifier` зависимостей.

Side-effects: одна запись `(scope, nonce, expires_at)` в `INonceStore`
+ optional audit-запись (отложена в F.7 при composition; в этом use-case
audit-логирование не добавлено, чтобы не плодить audit-action до того,
как handler F.8.a его реально использует).
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from pipirik_wars.domain.monetization.ports import INonceStore
from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.domain.shared.ports.clock import IClock

__all__ = [
    "RequestLinkWalletProof",
    "RequestLinkWalletProofCommand",
    "RequestLinkWalletProofConfig",
    "RequestLinkWalletProofResult",
]

# secrets.token_urlsafe(24) → ровно 32 символа base64url из 24 байт энтропии.
# ASCII-printable, помещается в `TonProof.payload`-инвариант [1, 512].
_DEFAULT_NONCE_BYTES: int = 24

# Default TTL — 5 минут (достаточно для подписи в TonConnect-app, не
# даёт слишком большое окно для perched-replay).
_DEFAULT_NONCE_TTL_SECONDS: int = 5 * 60


@dataclass(frozen=True, slots=True)
class RequestLinkWalletProofConfig:
    """Конфиг use-case-а ``RequestLinkWalletProof``.

    Все поля настраиваются через `BotSettings` (F.7); здесь — дефолты
    + invariants.

    * ``canonical_domain: str`` — utf8-имя хоста dApp-а, которое
      будет проверять production-verifier (F.5.c) против
      ``ton_proof.domain.value`` в phase-2. Должно совпадать с тем
      доменом, на котором развёрнут bot-backend (e.g.
      ``"pipirik.example.com"``). Игроку возвращается, чтобы TonConnect-
      app-а сразу попадал в whitelist.
    * ``nonce_ttl_seconds: int`` — TTL nonce-а в секундах (`> 0`).
      Default 300 (5 минут).
    """

    canonical_domain: str
    nonce_ttl_seconds: int = _DEFAULT_NONCE_TTL_SECONDS

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_domain, str) or not self.canonical_domain:
            raise ValueError(
                "RequestLinkWalletProofConfig.canonical_domain must be non-empty str, "
                f"got {self.canonical_domain!r}",
            )
        if (
            not isinstance(self.nonce_ttl_seconds, int)
            or isinstance(self.nonce_ttl_seconds, bool)
            or self.nonce_ttl_seconds <= 0
        ):
            raise ValueError(
                "RequestLinkWalletProofConfig.nonce_ttl_seconds must be int > 0, "
                f"got {self.nonce_ttl_seconds!r}",
            )


@dataclass(frozen=True, slots=True)
class RequestLinkWalletProofCommand:
    """Команда use-case ``RequestLinkWalletProof``.

    * ``player_id: int`` — id игрока (`> 0`, валидируется handler-ом).
    * ``address: str`` — TON-адрес кошелька, который игрок хочет
      привязать. Контракт: raw-форма ``workchain:hex64`` (как и
      ``TonProof.address``). Handler 4.1-F (F.8.a) принимает оба
      формата от игрока и нормализует в raw перед вызовом use-case-а.
    * ``currency: Currency`` — ``TON_NANO`` или ``USDT_DECIMAL``
      (USDT — jetton поверх TON, тот же кошелёк). ``STARS``
      не поддерживается (TG Stars не имеет on-chain-кошелька).
    """

    player_id: int
    address: str
    currency: Currency


@dataclass(frozen=True, slots=True)
class RequestLinkWalletProofResult:
    """Результат use-case ``RequestLinkWalletProof``.

    * ``nonce: str`` — server-issued nonce (32-символьная base64url-
      строка из ``secrets.token_urlsafe(24)``). Должен попасть в
      ``ton_proof.payload`` в phase-2.
    * ``domain: str`` — canonical-domain dApp-а. Должен попасть в
      ``ton_proof.domain.value`` в phase-2. Production-verifier
      (F.5.c) проверит match с whitelist-ом.
    * ``scope: str`` — бизнес-scope nonce-а
      (``"link_wallet:{player_id}:{currency}"``). Phase-2 будет
      использовать тот же scope при ``consume_nonce`` — это привязывает
      proof к конкретному игроку + currency-комбу.
    * ``expires_at: datetime`` — TZ-aware момент истечения nonce-а
      (``now + nonce_ttl_seconds``). Handler 4.1-F форматирует это
      в локаль-сообщение «у вас N минут».
    """

    nonce: str
    domain: str
    scope: str
    expires_at: datetime


class RequestLinkWalletProof:
    """Use-case: phase-1 двухфазного flow привязки TON-кошелька (Спринт 4.1-F)."""

    __slots__ = ("_clock", "_config", "_nonce_generator", "_nonce_store")

    def __init__(
        self,
        *,
        nonce_store: INonceStore,
        clock: IClock,
        config: RequestLinkWalletProofConfig,
        nonce_generator: Callable[[], str] | None = None,
    ) -> None:
        """DI-конструктор.

        Параметры:

        * ``nonce_store: INonceStore`` — порт хранилища nonces (F.3).
          Production — ``SqlAlchemyNonceStore`` (F.6.b); тесты —
          ``FakeNonceStore``.
        * ``clock: IClock`` — TZ-aware-часы (для `expires_at`).
        * ``config: RequestLinkWalletProofConfig`` — canonical_domain
          + nonce_ttl_seconds.
        * ``nonce_generator: Callable[[], str] | None`` — фабрика
          nonce-строк. Default — ``lambda: secrets.token_urlsafe(24)``.
          Тесты могут заменить на детерминированную (e.g. ``itertools.
          count``), чтобы assert-ить точные значения.
        """
        self._nonce_store = nonce_store
        self._clock = clock
        self._config = config
        self._nonce_generator = nonce_generator or self._default_nonce_generator

    @staticmethod
    def _default_nonce_generator() -> str:
        return secrets.token_urlsafe(_DEFAULT_NONCE_BYTES)

    async def execute(
        self,
        command: RequestLinkWalletProofCommand,
    ) -> RequestLinkWalletProofResult:
        """Сгенерировать nonce, привязать к scope-у, вернуть payload-инструкцию."""
        if command.player_id <= 0:
            raise ValueError(
                f"RequestLinkWalletProof: player_id must be > 0, got {command.player_id}",
            )
        if command.currency is Currency.STARS:
            raise ValueError(
                "RequestLinkWalletProof: currency=STARS not supported (Telegram "
                "Stars has no on-chain wallet to link)",
            )
        if not command.address:
            raise ValueError(
                f"RequestLinkWalletProof: address must be non-empty str, got {command.address!r}",
            )

        scope = f"link_wallet:{command.player_id}:{command.currency.value}"
        nonce = self._nonce_generator()
        now = self._clock.now()
        expires_at = now + timedelta(seconds=self._config.nonce_ttl_seconds)

        await self._nonce_store.issue_nonce(
            scope=scope,
            nonce=nonce,
            expires_at=expires_at,
        )

        return RequestLinkWalletProofResult(
            nonce=nonce,
            domain=self._config.canonical_domain,
            scope=scope,
            expires_at=expires_at,
        )
