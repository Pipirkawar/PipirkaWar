"""FTL-snapshot-тесты ключей `link-wallet-request-*` (Спринт 4.1-F, шаг F.8.c).

Эти тесты проверяют, что финальные русские и английские формулировки
4 ключей `/link_wallet`-phase-1 (`-usage`, `-invalid-currency`,
`-invalid-address`, `-issued`) загружаются `FluentMessageBundle` без
ошибок и подставляют все параметры, которые передаёт презентер.

Логика идентична `test_admin_keys_lint.py`-духу: ловим mishaps
вида «ключ удалён», «параметр переименован», «локаль рассыпается».
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from pipirik_wars.application.i18n import Locale, MessageKey
from pipirik_wars.infrastructure.i18n import FluentMessageBundle

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_LOCALES_DIR: Final[Path] = _REPO_ROOT / "locales"


@pytest.fixture
def bundle() -> FluentMessageBundle:
    return FluentMessageBundle(locales_dir=_LOCALES_DIR)


_NONCE: Final[str] = "abcXYZ0123_-.~test"
_DOMAIN: Final[str] = "pipirik.example.com"
_ADDRESS: Final[str] = "0:" + "ab" * 32
_FRIENDLY_ADDRESS: Final[str] = "EQBvW8Z5huBkMJYdnfAEM5JqTNkuWX3diqYENkWsIL0XggGG"


@pytest.mark.parametrize("locale_code", ["ru", "en"])
class TestLinkWalletRequestUsage:
    def test_usage_loads_without_error(
        self,
        bundle: FluentMessageBundle,
        locale_code: str,
    ) -> None:
        text = bundle.format(
            MessageKey("link-wallet-request-usage"),
            locale=Locale(locale_code),
        )
        assert text
        # «usage» инструкция упоминает имя команды и валюты.
        assert "/link_wallet" in text
        assert "ton" in text
        assert "usdt" in text


@pytest.mark.parametrize("locale_code", ["ru", "en"])
class TestLinkWalletRequestInvalidCurrency:
    def test_invalid_currency_substitutes_code(
        self,
        bundle: FluentMessageBundle,
        locale_code: str,
    ) -> None:
        text = bundle.format(
            MessageKey("link-wallet-request-invalid-currency"),
            locale=Locale(locale_code),
            code="doge",
        )
        assert "doge" in text


@pytest.mark.parametrize("locale_code", ["ru", "en"])
class TestLinkWalletRequestInvalidAddress:
    def test_invalid_address_substitutes_address(
        self,
        bundle: FluentMessageBundle,
        locale_code: str,
    ) -> None:
        text = bundle.format(
            MessageKey("link-wallet-request-invalid-address"),
            locale=Locale(locale_code),
            address="not-an-address",
        )
        assert "not-an-address" in text


@pytest.mark.parametrize("locale_code", ["ru", "en"])
class TestLinkWalletRequestIssued:
    def test_issued_substitutes_all_params(
        self,
        bundle: FluentMessageBundle,
        locale_code: str,
    ) -> None:
        text = bundle.format(
            MessageKey("link-wallet-request-issued"),
            locale=Locale(locale_code),
            nonce=_NONCE,
            domain=_DOMAIN,
            expires_at_minutes=10,
            currency="ton",
            address=_FRIENDLY_ADDRESS,
        )
        # Все параметры пересоставлены в финальный текст —
        # если ключ переименовали или параметр поменяли, Fluent
        # либо бросит ошибку, либо просто оставит литерал `{ $foo }`.
        assert _NONCE in text
        assert _DOMAIN in text
        assert _FRIENDLY_ADDRESS in text
        # Ни одного нерендеренного литерального плейсхолдера.
        assert "{ $nonce }" not in text
        assert "{ $domain }" not in text
        assert "{ $address }" not in text
        assert "{ $expires_at_minutes }" not in text
        assert "{ $currency }" not in text

    def test_issued_mentions_ton_connect_and_confirm_command(
        self,
        bundle: FluentMessageBundle,
        locale_code: str,
    ) -> None:
        text = bundle.format(
            MessageKey("link-wallet-request-issued"),
            locale=Locale(locale_code),
            nonce=_NONCE,
            domain=_DOMAIN,
            expires_at_minutes=10,
            currency="ton",
            address=_FRIENDLY_ADDRESS,
        )
        # Инструкция упоминает TON Connect-приложение и команду подтверждения.
        assert "TON Connect" in text or "TonConnect" in text or "TON-Connect" in text
        assert "/link_wallet_confirm" in text
