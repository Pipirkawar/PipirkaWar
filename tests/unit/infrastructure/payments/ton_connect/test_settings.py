"""Unit-тесты ``TonConnectSettings`` (Спринт 4.1-F, шаг F.7).

Покрытие:

* Default-ы (sandbox-mode, default canonical_domain в whitelist-е).
* Explicit production-mode с консистентными параметрами.
* CSV-parser ``allowed_domains`` (env → tuple[str, ...]).
* Cross-field-validation: production-mode + canonical_domain не в
  whitelist-е → ValueError при ``model_post_init``.
* Cross-field-validation: production-mode + пустой whitelist → ValueError.
* Cross-field-validation: sandbox-mode игнорирует whitelist-mismatch.
* Field-invariants: ``max_age_seconds > 0``, ``clock_skew_seconds >= 0``,
  ``nonce_ttl_seconds > 0``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipirik_wars.infrastructure.payments.ton_connect.settings import TonConnectSettings


class TestDefaults:
    def test_default_is_sandbox(self) -> None:
        s = TonConnectSettings()
        assert s.verifier_mode == "sandbox"
        assert s.max_age_seconds == 600
        assert s.clock_skew_seconds == 60
        assert s.nonce_ttl_seconds == 600

    def test_default_canonical_domain_in_default_whitelist(self) -> None:
        """Sanity: дефолты согласованы (canonical в whitelist)."""
        s = TonConnectSettings()
        assert s.canonical_domain in s.allowed_domains


class TestProductionMode:
    def test_explicit_production_with_consistent_domains_ok(self) -> None:
        s = TonConnectSettings(
            verifier_mode="production",
            allowed_domains=("pipirik.example.com", "foo.example.com"),
            canonical_domain="pipirik.example.com",
        )
        assert s.verifier_mode == "production"
        assert s.allowed_domains == ("pipirik.example.com", "foo.example.com")

    def test_production_with_canonical_not_in_whitelist_raises(self) -> None:
        with pytest.raises(ValidationError, match="canonical_domain"):
            TonConnectSettings(
                verifier_mode="production",
                allowed_domains=("foo.example.com",),
                canonical_domain="bar.example.com",
            )

    def test_production_with_empty_whitelist_raises(self) -> None:
        with pytest.raises(ValidationError, match="allowed_domains"):
            TonConnectSettings(
                verifier_mode="production",
                allowed_domains=(),
                canonical_domain="pipirik.example.com",
            )

    def test_sandbox_ignores_whitelist_mismatch(self) -> None:
        """Sandbox-режим не использует whitelist, поэтому mismatch ОК."""
        s = TonConnectSettings(
            verifier_mode="sandbox",
            allowed_domains=("foo.example.com",),
            canonical_domain="bar.example.com",
        )
        assert s.verifier_mode == "sandbox"


class TestCsvParser:
    def test_csv_string_parsed_to_tuple(self) -> None:
        s = TonConnectSettings(allowed_domains="a.example.com,b.example.com")  # type: ignore[arg-type]
        assert s.allowed_domains == ("a.example.com", "b.example.com")

    def test_csv_with_whitespace_trimmed(self) -> None:
        s = TonConnectSettings(allowed_domains="  a.example.com ,  b.example.com  ")  # type: ignore[arg-type]
        assert s.allowed_domains == ("a.example.com", "b.example.com")

    def test_empty_csv_returns_empty_tuple_in_sandbox(self) -> None:
        s = TonConnectSettings(verifier_mode="sandbox", allowed_domains="")  # type: ignore[arg-type]
        assert s.allowed_domains == ()


class TestFieldInvariants:
    def test_max_age_seconds_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            TonConnectSettings(max_age_seconds=0)

    def test_max_age_seconds_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TonConnectSettings(max_age_seconds=-1)

    def test_clock_skew_seconds_zero_ok(self) -> None:
        """Zero is допустимо (no skew tolerance)."""
        s = TonConnectSettings(clock_skew_seconds=0)
        assert s.clock_skew_seconds == 0

    def test_clock_skew_seconds_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TonConnectSettings(clock_skew_seconds=-1)

    def test_nonce_ttl_seconds_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            TonConnectSettings(nonce_ttl_seconds=0)
