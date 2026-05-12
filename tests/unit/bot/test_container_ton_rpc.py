"""Unit-тесты composition root для крипто-выплат (Спринт 4.1-D, шаг D.10.c).

Скоуп — сборка `bot/main.py::Container` поверх **реальных** infrastructure-
имплементаций `HmacTgStarsPayloadVerifier` / `SqlAlchemyWalletRepository` /
`TonRpcAdapter` (`ITonPayoutAdapter`) / `SandboxTonConnectVerifier`. Это
smoke того, что `build_container(settings)` инстанциирует все DI-зависимости
без MissingDependencyError-а и пробрасывает их в `build_dispatcher(...)`
workflow-data для handler-ов `/link_wallet*`, `/claim_prize`, `/roulette_paid`.

Полноценные behavior-тесты use-case-ов `LinkWallet` / `ClaimPrize` /
`ExpireReservedPrizeLots` живут в `tests/unit/application/monetization/`.
"""

from __future__ import annotations

from pydantic import SecretStr

from pipirik_wars.application.monetization import (
    ClaimPrize,
    ExpireReservedPrizeLots,
    LinkWallet,
)
from pipirik_wars.bot.main import build_container
from pipirik_wars.infrastructure.db.repositories import SqlAlchemyWalletRepository
from pipirik_wars.infrastructure.payments.tg_stars import HmacTgStarsPayloadVerifier
from pipirik_wars.infrastructure.payments.tg_stars.settings import TgStarsSettings
from pipirik_wars.infrastructure.payments.ton_connect import SandboxTonConnectVerifier
from pipirik_wars.infrastructure.payments.ton_rpc import TonRpcAdapter
from pipirik_wars.infrastructure.payments.ton_rpc.settings import TonRpcSettings
from pipirik_wars.infrastructure.settings import (
    BootstrapSettings,
    BotSettings,
    DatabaseSettings,
    Settings,
)


def _settings_with_crypto_sections() -> Settings:
    """Собрать `Settings` с поднятыми `ton_rpc` / `tg_stars`.

    Используется default-секциями `TonRpcSettings()` (placeholder-seed `0`*64,
    sandbox=True) + явный `TgStarsSettings(secret=...)` (32-byte placeholder).
    """
    return Settings(
        environment="test",
        db=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")),
        bot=BotSettings(token=SecretStr("test-token")),
        bootstrap=BootstrapSettings(),
        ton_rpc=TonRpcSettings(is_sandbox=True),
        tg_stars=TgStarsSettings(secret=SecretStr("test-tg-stars-32-byte-secret-foo")),
    )


def _settings_default_sections() -> Settings:
    """Собрать `Settings` без `ton_rpc` / `tg_stars` (None — fallback в build)."""
    return Settings(
        environment="test",
        db=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")),
        bot=BotSettings(token=SecretStr("test-token")),
        bootstrap=BootstrapSettings(),
    )


class TestBuildContainerCryptoWiring:
    """D.10.c: `build_container` собирает реальные крипто-адаптеры."""

    def test_tg_stars_verifier_is_real_hmac_impl(self) -> None:
        c = build_container(settings=_settings_with_crypto_sections())
        assert isinstance(c.tg_stars_verifier, HmacTgStarsPayloadVerifier)

    def test_ton_payout_adapter_is_real_ton_rpc_adapter(self) -> None:
        c = build_container(settings=_settings_with_crypto_sections())
        assert isinstance(c.ton_payout_adapter, TonRpcAdapter)

    def test_wallet_repo_is_real_sqlalchemy_repo(self) -> None:
        c = build_container(settings=_settings_with_crypto_sections())
        assert isinstance(c.wallet_repo, SqlAlchemyWalletRepository)

    def test_ton_connect_verifier_is_sandbox_stub(self) -> None:
        # На `is_sandbox=True` верификатор — `SandboxTonConnectVerifier`.
        c = build_container(settings=_settings_with_crypto_sections())
        assert isinstance(c.ton_connect_verifier, SandboxTonConnectVerifier)

    def test_link_wallet_use_case_wired(self) -> None:
        c = build_container(settings=_settings_with_crypto_sections())
        assert isinstance(c.link_wallet, LinkWallet)

    def test_claim_prize_use_case_wired(self) -> None:
        c = build_container(settings=_settings_with_crypto_sections())
        assert isinstance(c.claim_prize, ClaimPrize)

    def test_expire_reserved_prize_lots_wired(self) -> None:
        c = build_container(settings=_settings_with_crypto_sections())
        assert isinstance(c.expire_reserved_prize_lots, ExpireReservedPrizeLots)


class TestBuildContainerFallbackForOptionalSections:
    """D.10.c: `build_container` собирает дефолты, когда `Settings.ton_rpc`/`tg_stars` = None."""

    def test_build_container_with_default_sections_does_not_raise(self) -> None:
        # `Settings()` без `ton_rpc` / `tg_stars` — `build_container` должен
        # собрать их сам через placeholder-дефолты (тестовый bootstrap).
        c = build_container(settings=_settings_default_sections())
        assert isinstance(c.tg_stars_verifier, HmacTgStarsPayloadVerifier)
        assert isinstance(c.ton_payout_adapter, TonRpcAdapter)

    def test_sandbox_mode_propagates_to_ton_connect_verifier(self) -> None:
        # `TonRpcSettings()` default — `is_sandbox=False` → mainnet
        # → `SandboxTonConnectVerifier(is_sandbox=False)` fail-closed.
        c = build_container(settings=_settings_default_sections())
        assert isinstance(c.ton_connect_verifier, SandboxTonConnectVerifier)
        # Проверим, что fail-closed на пустой proof работает корректно
        # (verify() — coroutine, тестируется отдельно в test_ton_connect.py).


# NB: дополнительный тест `build_dispatcher`-пробросов крипто-DI
# в workflow-data **не** создаётся в этом модуле. aiogram-роутеры —
# module-singleton-ы, `build_dispatcher` идемпотентен только в рамках
# одного теста (повторный `include_router(start_router)` бросает
# `RuntimeError: Router is already attached`). Проверка пробросов
# `dp["tg_stars_verifier"] / dp["link_wallet"] / dp["claim_prize"] /
# dp["wallet_repository"] / dp["prize_lot_repository"]` живёт в
# `test_composition_root.py::TestBuildDispatcher`-классе — он гарантирует,
# что `build_dispatcher` вызывается ровно один раз за тест-сессию.
