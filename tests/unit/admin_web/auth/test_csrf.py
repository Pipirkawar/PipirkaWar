"""Unit-тесты CSRF middleware (Sprint 4.5-A)."""

from __future__ import annotations

import secrets

from pipirik_wars.admin_web.auth.csrf import (
    CSRF_HEADER,
    EXEMPT_PATHS,
    SAFE_METHODS,
    generate_csrf_token,
)


class TestGenerateCsrfToken:
    def test_returns_string(self) -> None:
        token = generate_csrf_token()
        assert isinstance(token, str)
        assert len(token) > 20

    def test_tokens_unique(self) -> None:
        tokens = {generate_csrf_token() for _ in range(50)}
        assert len(tokens) == 50


class TestCsrfConstants:
    def test_safe_methods(self) -> None:
        assert "GET" in SAFE_METHODS
        assert "HEAD" in SAFE_METHODS
        assert "OPTIONS" in SAFE_METHODS
        assert "POST" not in SAFE_METHODS
        assert "DELETE" not in SAFE_METHODS

    def test_header_name(self) -> None:
        assert CSRF_HEADER == "X-CSRF-Token"

    def test_exempt_paths(self) -> None:
        assert "/healthz" in EXEMPT_PATHS
        assert "/auth/telegram/callback" in EXEMPT_PATHS


class TestCsrfCompareDigest:
    def test_matching_tokens(self) -> None:
        token = generate_csrf_token()
        assert secrets.compare_digest(token, token)

    def test_mismatched_tokens(self) -> None:
        t1 = generate_csrf_token()
        t2 = generate_csrf_token()
        assert not secrets.compare_digest(t1, t2)
