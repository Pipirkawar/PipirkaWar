"""Unit-тесты декораторов авторизации use-case-ов."""

from __future__ import annotations

import pytest

from pipirik_wars.application.auth import (
    AuthContext,
    AuthorizationError,
    requires_clan_member,
    requires_length,
    requires_level,
)


def _ctx(
    *,
    length: int = 5,
    thickness: int = 1,
    level: int = 1,
    clan_id: int | None = None,
    is_admin: bool = False,
) -> AuthContext:
    return AuthContext(
        actor_tg_id=1,
        length_cm=length,
        thickness=thickness,
        level=level,
        clan_id=clan_id,
        is_admin=is_admin,
    )


class TestRequiresLevel:
    @pytest.mark.asyncio
    async def test_passes_when_level_sufficient(self) -> None:
        @requires_level(3)
        async def use_case(ctx: AuthContext) -> str:
            return "ok"

        assert await use_case(_ctx(level=5)) == "ok"

    @pytest.mark.asyncio
    async def test_blocks_when_level_low(self) -> None:
        @requires_level(3)
        async def use_case(ctx: AuthContext) -> str:
            return "ok"

        with pytest.raises(AuthorizationError) as exc:
            await use_case(_ctx(level=1))
        assert exc.value.requirement == "level"

    @pytest.mark.asyncio
    async def test_no_ctx_raises_typeerror(self) -> None:
        @requires_level(1)
        async def use_case() -> str:
            return "ok"

        with pytest.raises(TypeError, match="AuthContext"):
            await use_case()

    @pytest.mark.asyncio
    async def test_wrong_first_arg_type(self) -> None:
        @requires_level(1)
        async def use_case(ctx: object) -> str:
            return "ok"

        with pytest.raises(TypeError, match="AuthContext"):
            await use_case("not a ctx")


class TestRequiresLength:
    @pytest.mark.asyncio
    async def test_pass_and_block(self) -> None:
        @requires_length(20)
        async def pvp_attack(ctx: AuthContext) -> str:
            return "fight"

        assert await pvp_attack(_ctx(length=25)) == "fight"
        with pytest.raises(AuthorizationError) as exc:
            await pvp_attack(_ctx(length=5))
        assert exc.value.requirement == "length"


class TestRequiresClanMember:
    @pytest.mark.asyncio
    async def test_member_passes(self) -> None:
        @requires_clan_member
        async def clan_action(ctx: AuthContext) -> str:
            return "ok"

        assert await clan_action(_ctx(clan_id=42)) == "ok"

    @pytest.mark.asyncio
    async def test_non_member_blocked(self) -> None:
        @requires_clan_member
        async def clan_action(ctx: AuthContext) -> str:
            return "ok"

        with pytest.raises(AuthorizationError) as exc:
            await clan_action(_ctx(clan_id=None))
        assert exc.value.requirement == "clan_member"
