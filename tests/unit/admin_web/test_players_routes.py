"""Unit tests for players routes module (Sprint 4.5-D, task 4.5.5)."""

from __future__ import annotations

from pipirik_wars.admin_web.routes.players import (
    _ACTIVITY_LIMIT,
    _SEARCH_LIMIT,
    _redirect_to_card,
    _render,
)


class TestRedirectToCard:
    def test_redirect_sets_location_header(self) -> None:
        resp = _redirect_to_card(12345, "banned")
        assert resp.status_code == 303
        assert resp.headers["Location"] == "/players/12345?flash=banned"

    def test_redirect_sets_hx_redirect_header(self) -> None:
        resp = _redirect_to_card(99, "frozen")
        assert resp.headers["HX-Redirect"] == "/players/99?flash=frozen"

    def test_redirect_already_banned_flash(self) -> None:
        resp = _redirect_to_card(1, "already_banned")
        assert "already_banned" in resp.headers["Location"]

    def test_redirect_unfrozen_flash(self) -> None:
        resp = _redirect_to_card(42, "unfrozen")
        assert "unfrozen" in resp.headers["Location"]

    def test_redirect_already_active_flash(self) -> None:
        resp = _redirect_to_card(7, "already_active")
        assert "already_active" in resp.headers["Location"]

    def test_redirect_already_frozen_flash(self) -> None:
        resp = _redirect_to_card(8, "already_frozen")
        assert "already_frozen" in resp.headers["Location"]


class TestConstants:
    def test_search_limit_is_positive(self) -> None:
        assert _SEARCH_LIMIT > 0

    def test_activity_limit_is_positive(self) -> None:
        assert _ACTIVITY_LIMIT > 0

    def test_search_limit_value(self) -> None:
        assert _SEARCH_LIMIT == 50

    def test_activity_limit_value(self) -> None:
        assert _ACTIVITY_LIMIT == 30


class TestRenderHelper:
    def test_render_is_callable(self) -> None:
        assert callable(_render)
