"""Smoke-тест production TON Connect verify-flow-а (Спринт 4.1-F, шаг F.9).

Цель — собрать **полную production-цепочку** для двухфазного
``/link_wallet`` → ``/link_wallet_confirm``-flow-а и прогнать её
end-to-end через реальные доменные/приложенческие/инфра-объекты,
чтобы убедиться, что:

* ``RequestLinkWalletProof.execute(...)`` (phase-1) выдаёт nonce
  и кладёт его в `SqlAlchemyNonceStore` (production-store поверх
  ``ton_connect_nonces``-таблицы).
* ``TonConnectProductionVerifier`` (F.5.c) реально верифицирует
  Ed25519-подпись, собранную тест-кошельком ``nacl.signing.SigningKey``
  поверх ``build_canonical_message(...)`` (F.5.b).
* ``LinkWallet.execute(...)`` (phase-2) consume-ит nonce в `SqlAlchemyNonceStore`
  и кладёт ``Wallet`` в `SqlAlchemyWalletRepository`.
* Повторный вызов того же ``LinkWallet.execute(...)`` с тем же
  ``(scope, nonce, proof)`` бросит ``TonProofReplayedError`` — нонс
  уже помечен ``consumed_at``, CAS-update не сработает.

В отличие от unit-тестов в ``tests/unit/application/monetization/
test_link_wallet.py`` и ``tests/unit/infrastructure/payments/
ton_connect/test_production.py`` — здесь **нет** ``FakeNonceStore`` /
``FakeWalletRepository`` / ``FakeTonConnectVerifier``: cборка ровно
такая же, как в ``bot/main.py::build_container(verifier_mode=
"production")``. БД — SQLite-in-memory (тот же портабельный путь, что
``tests/integration/db/test_ton_connect_nonce_store.py`` —
``Base.metadata.create_all`` без Postgres-зависимости).

Marker ``smoke`` (``@pytest.mark.smoke``) — позволяет выбрать только
smoke-тесты через ``pytest -m smoke tests/smoke/`` или ``make smoke``.
По умолчанию они идут в общий ``pytest``-прогон (быстрые).
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import nacl.signing
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pipirik_wars.application.monetization.link_wallet import (
    LinkWallet,
    LinkWalletCommand,
)
from pipirik_wars.application.monetization.request_link_wallet_proof import (
    RequestLinkWalletProof,
    RequestLinkWalletProofCommand,
    RequestLinkWalletProofConfig,
)
from pipirik_wars.domain.monetization import (
    Currency,
    TonProofReplayedError,
    Wallet,
)
from pipirik_wars.domain.monetization.value_objects import TonProof
from pipirik_wars.infrastructure.db.base import Base
from pipirik_wars.infrastructure.db.models import (  # noqa: F401  (регистрация моделей)
    TonConnectNonceORM,
    WalletORM,
)
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyNonceStore,
    SqlAlchemyWalletRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.payments.ton_connect.canonical_message import (
    build_canonical_message,
)
from pipirik_wars.infrastructure.payments.ton_connect.production import (
    TonConnectProductionConfig,
    TonConnectProductionVerifier,
)
from tests.fakes.audit import FakeAuditLogger
from tests.fakes.clock import FakeClock

# Фиксированные параметры smoke-теста.
_NOW = datetime(2026, 5, 12, 12, 0, tzinfo=UTC)
_CANONICAL_DOMAIN = "pipirik.example.com"
_ALLOWED_DOMAINS: tuple[str, ...] = (_CANONICAL_DOMAIN,)
_MAX_AGE_SECONDS = 600
_CLOCK_SKEW_SECONDS = 60
_NONCE_TTL_SECONDS = 600

_PLAYER_ID = 42
_WALLET_ADDRESS = "0:" + "ab" * 32

# Детерминированный Ed25519 seed для воспроизводимости smoke-а.
_TEST_WALLET_SEED = bytes.fromhex("11" * 32)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """In-memory SQLite-engine с применением DDL ORM-моделей.

    Аналог ``tests/integration/db/conftest.py::engine`` — но локальный
    для smoke-теста, чтобы не подмешивать prize-pool/payout-freeze-seed-ы
    из integration-conftest-а (они тут не нужны).
    """
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_maker(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        class_=AsyncSession,
    )


@pytest_asyncio.fixture
async def uow(
    session_maker: async_sessionmaker[AsyncSession],
) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(session_maker)


def _sign_proof(
    *,
    signing_key: nacl.signing.SigningKey,
    nonce: str,
    domain: str,
    timestamp: int,
    address: str,
) -> str:
    """Подписать canonical-message тест-кошельком и собрать TonProof-JSON.

    Эмулирует то, что делает TonConnect-app кошелька (Tonkeeper / Tonhub
    / MyTonWallet): берёт server-issued nonce + domain + timestamp +
    address, строит canonical-message по спеке TON Connect 2.0
    (``infrastructure.payments.ton_connect.canonical_message``), подписывает
    его Ed25519-private-key-ом и возвращает dApp-у JSON-ответ ровно того
    shape-а, который парсит ``parse_ton_proof`` (F.5.a).
    """
    # Сначала собираем VO напрямую (не через JSON-roundtrip) — нам нужны
    # ровно те же байты, которые увидит верификатор после re-parse.
    domain_bytes = domain.encode("utf-8")
    public_key_bytes = bytes(signing_key.verify_key)

    proof_vo = TonProof(
        timestamp=timestamp,
        domain_value=domain,
        payload=nonce,
        # Подпись добавим после построения canonical — placeholder под VO-invariants.
        signature_b64=base64.b64encode(b"\x00" * 64).decode("ascii"),
        public_key_hex=public_key_bytes.hex(),
        address=address,
    )

    canonical = build_canonical_message(proof_vo)
    signed = signing_key.sign(canonical)
    signature_bytes: bytes = signed.signature

    return json.dumps(
        {
            "proof": {
                "timestamp": timestamp,
                "domain": {
                    "lengthBytes": len(domain_bytes),
                    "value": domain,
                },
                "payload": nonce,
                "signature": base64.b64encode(signature_bytes).decode("ascii"),
            },
            "account": {
                "address": address,
                "publicKey": public_key_bytes.hex(),
            },
        },
    )


@pytest.mark.smoke
class TestTonConnectProductionFullFlow:
    """End-to-end production TON Connect verify-flow."""

    @pytest.mark.asyncio
    async def test_happy_path_and_replay(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Happy-path link-wallet + replay-detect через production-стек.

        Шаги:

        1. Phase-1: ``RequestLinkWalletProof.execute(...)`` → выдаёт
           ``(nonce, domain, scope, expires_at)`` и записывает строку
           в `ton_connect_nonces` через `SqlAlchemyNonceStore`.
        2. Эмуляция кошелькового app-а: ``_sign_proof(...)`` подписывает
           canonical-message Ed25519-ключом тест-кошелька и собирает
           TON Connect-JSON-ответ.
        3. Phase-2 (happy): ``LinkWallet.execute(...)`` →
           ``TonConnectProductionVerifier`` re-parse-ит proof, проверяет
           всю цепочку (address-match, timestamp-window, domain-whitelist,
           Ed25519-signature) и возвращает ``True``; затем
           `SqlAlchemyNonceStore.consume_nonce` атомарно помечает
           ``consumed_at = now``; `SqlAlchemyWalletRepository.add_or_replace`
           кладёт ``Wallet`` в `wallets`; audit пишется.
        4. Phase-2 (replay): повторный ``LinkWallet.execute(...)`` с тем
           же ``(scope, nonce, proof)`` — proof снова валидный
           (signature по тому же canonical-message), верификатор вернёт
           ``True``, но ``consume_nonce`` теперь даст ``False``
           (нонс помечен ``consumed_at``), и use-case бросит
           ``TonProofReplayedError(scope=...)``. Wallet в БД остаётся
           неизменным (одна запись с теми же полями).
        """
        clock = FakeClock(_NOW)
        signing_key = nacl.signing.SigningKey(_TEST_WALLET_SEED)
        timestamp = int(_NOW.timestamp())

        # ── Production-стек: ровно как в bot/main.py::build_container.
        nonce_store = SqlAlchemyNonceStore(uow=uow, clock=clock)
        wallet_repo = SqlAlchemyWalletRepository(uow=uow)
        verifier = TonConnectProductionVerifier(
            config=TonConnectProductionConfig(
                allowed_domains=_ALLOWED_DOMAINS,
                max_age_seconds=_MAX_AGE_SECONDS,
                clock_skew_seconds=_CLOCK_SKEW_SECONDS,
            ),
            clock=clock,
        )
        audit = FakeAuditLogger()
        request_proof_uc = RequestLinkWalletProof(
            nonce_store=nonce_store,
            clock=clock,
            config=RequestLinkWalletProofConfig(
                canonical_domain=_CANONICAL_DOMAIN,
                nonce_ttl_seconds=_NONCE_TTL_SECONDS,
            ),
        )
        link_wallet_uc = LinkWallet(
            wallet_repository=wallet_repo,
            ton_connect_verifier=verifier,
            nonce_store=nonce_store,
            audit_logger=audit,
            clock=clock,
        )

        # ── Phase-1: server-issued nonce + payload-инструкция.
        async with uow:
            phase1 = await request_proof_uc.execute(
                RequestLinkWalletProofCommand(
                    player_id=_PLAYER_ID,
                    address=_WALLET_ADDRESS,
                    currency=Currency.TON_NANO,
                ),
            )
            await uow.commit()

        assert phase1.domain == _CANONICAL_DOMAIN
        assert phase1.scope == f"link_wallet:{_PLAYER_ID}:{Currency.TON_NANO.value}"
        assert phase1.expires_at == _NOW + timedelta(seconds=_NONCE_TTL_SECONDS)
        # Nonce — base64url, > 0 символов; точное значение случайное.
        assert isinstance(phase1.nonce, str)
        assert phase1.nonce  # non-empty

        # ── Эмуляция кошелька: подписываем canonical-message.
        proof_json = _sign_proof(
            signing_key=signing_key,
            nonce=phase1.nonce,
            domain=phase1.domain,
            timestamp=timestamp,
            address=_WALLET_ADDRESS,
        )

        # ── Phase-2 (happy): production-verifier + consume + upsert wallet.
        async with uow:
            result = await link_wallet_uc.execute(
                LinkWalletCommand(
                    player_id=_PLAYER_ID,
                    address=_WALLET_ADDRESS,
                    currency=Currency.TON_NANO,
                    proof=proof_json,
                    scope=phase1.scope,
                    nonce=phase1.nonce,
                ),
            )
            await uow.commit()

        assert isinstance(result.wallet, Wallet)
        assert result.wallet.player_id == _PLAYER_ID
        assert result.wallet.address == _WALLET_ADDRESS
        assert result.wallet.currency is Currency.TON_NANO
        assert result.replaced is False

        # Verify persisted state — wallet записан, nonce помечен consumed.
        async with uow:
            stored = await wallet_repo.get_by_player_and_currency(
                player_id=_PLAYER_ID,
                currency=Currency.TON_NANO,
            )
        assert stored is not None
        assert stored.address == _WALLET_ADDRESS

        # ── Phase-2 (replay): тот же proof + scope + nonce → TonProofReplayedError.
        with pytest.raises(TonProofReplayedError) as exc_info:
            async with uow:
                await link_wallet_uc.execute(
                    LinkWalletCommand(
                        player_id=_PLAYER_ID,
                        address=_WALLET_ADDRESS,
                        currency=Currency.TON_NANO,
                        proof=proof_json,
                        scope=phase1.scope,
                        nonce=phase1.nonce,
                    ),
                )
                await uow.commit()
        assert exc_info.value.scope == phase1.scope

        # Wallet в БД остался тем же (одна запись).
        async with uow:
            stored_after_replay = await wallet_repo.get_by_player_and_currency(
                player_id=_PLAYER_ID,
                currency=Currency.TON_NANO,
            )
        assert stored_after_replay == stored
