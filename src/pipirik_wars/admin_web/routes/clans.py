"""Clan admin routes (Sprint 4.5-E, task 4.5.6)."""

from __future__ import annotations

import math

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pipirik_wars.admin_web.deps import get_container, require_totp_verified
from pipirik_wars.application.admin.freeze_clan import (
    FreezeClanAdmin,
    FreezeClanAdminInput,
)
from pipirik_wars.application.admin.get_clan_card import (
    GetClanCard,
    GetClanCardInput,
)
from pipirik_wars.application.admin.get_clan_daily_head_history import (
    GetClanDailyHeadHistory,
    GetClanDailyHeadHistoryInput,
)
from pipirik_wars.application.admin.list_clans import (
    DEFAULT_PAGE_SIZE,
    ListClansAdmin,
    ListClansAdminInput,
)
from pipirik_wars.application.admin.unfreeze_clan import (
    UnfreezeClanAdmin,
    UnfreezeClanAdminInput,
)
from pipirik_wars.domain.clan import ClanStatus
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyAdminRepository,
    SqlAlchemyClanMembershipRepository,
    SqlAlchemyClanRepository,
    SqlAlchemyDailyHeadRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.services import SqlAlchemyAdminAuditLogger
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

router = APIRouter()


def _parse_status_filter(raw: str | None) -> ClanStatus | None:
    if raw is None or raw in {"", "all"}:
        return None
    if raw == "frozen":
        return ClanStatus.FROZEN
    if raw == "active":
        return ClanStatus.ACTIVE
    return None


@router.get("/clans", response_class=HTMLResponse)
async def clans_list(
    request: Request,
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
) -> HTMLResponse:
    session = require_totp_verified(request)
    container = get_container(request)
    status_filter = _parse_status_filter(status)

    uow = SqlAlchemyUnitOfWork(container.session_factory)
    admins = SqlAlchemyAdminRepository(uow=uow)
    clans = SqlAlchemyClanRepository(uow=uow)
    audit = SqlAlchemyAdminAuditLogger(uow=uow)

    use_case = ListClansAdmin(
        uow=uow,
        admins=admins,
        clans=clans,
        audit=audit,
        clock=container.clock,
        authz=container.authorization_policy,
    )

    result = await use_case.execute(
        ListClansAdminInput(
            actor_tg_id=session.admin_id,
            status_filter=status_filter,
            page=page,
            page_size=DEFAULT_PAGE_SIZE,
        ),
    )

    total_pages = max(1, math.ceil(result.total / result.page_size))

    templates = request.app.state.templates
    content: str = templates.get_template("clans_list.html").render(
        request=request,
        session=session,
        clans=result.clans,
        total=result.total,
        page=result.page,
        total_pages=total_pages,
        status_filter=status or "all",
    )
    return HTMLResponse(content=content)


@router.get("/clans/{clan_id}", response_class=HTMLResponse)
async def clan_card(
    request: Request,
    clan_id: int,
) -> HTMLResponse:
    session = require_totp_verified(request)
    container = get_container(request)

    uow = SqlAlchemyUnitOfWork(container.session_factory)
    admins = SqlAlchemyAdminRepository(uow=uow)
    clans = SqlAlchemyClanRepository(uow=uow)
    clan_members = SqlAlchemyClanMembershipRepository(uow=uow)
    players = SqlAlchemyPlayerRepository(uow=uow)
    audit = SqlAlchemyAdminAuditLogger(uow=uow)

    use_case = GetClanCard(
        uow=uow,
        admins=admins,
        players=players,
        clans=clans,
        clan_members=clan_members,
        audit=audit,
        clock=container.clock,
        authz=container.authorization_policy,
    )

    result = await use_case.execute(
        GetClanCardInput(actor_tg_id=session.admin_id, query=clan_id),
    )

    head_history = None
    if result.card is not None:
        daily_heads = SqlAlchemyDailyHeadRepository(uow=uow)
        head_uc = GetClanDailyHeadHistory(
            uow=uow,
            admins=admins,
            clans=clans,
            players=players,
            daily_heads=daily_heads,
            audit=audit,
            clock=container.clock,
            authz=container.authorization_policy,
        )
        head_result = await head_uc.execute(
            GetClanDailyHeadHistoryInput(
                actor_tg_id=session.admin_id,
                query=clan_id,
                limit=10,
            ),
        )
        head_history = head_result.entries

    templates = request.app.state.templates
    content: str = templates.get_template("clan_card.html").render(
        request=request,
        session=session,
        card=result.card,
        clan_id=clan_id,
        head_history=head_history,
    )
    return HTMLResponse(content=content)


@router.post("/clans/{clan_id}/freeze")
async def freeze_clan(
    request: Request,
    clan_id: int,
    reason: str = Form(default=""),
) -> RedirectResponse:
    session = require_totp_verified(request)
    container = get_container(request)

    uow = SqlAlchemyUnitOfWork(container.session_factory)
    admins = SqlAlchemyAdminRepository(uow=uow)
    clans = SqlAlchemyClanRepository(uow=uow)
    audit = SqlAlchemyAdminAuditLogger(uow=uow)

    use_case = FreezeClanAdmin(
        uow=uow,
        admins=admins,
        clans=clans,
        audit=audit,
        clock=container.clock,
        authz=container.authorization_policy,
    )

    await use_case.execute(
        FreezeClanAdminInput(
            actor_tg_id=session.admin_id,
            query=clan_id,
            reason=reason or None,
        ),
    )

    return RedirectResponse(url=f"/clans/{clan_id}", status_code=303)


@router.post("/clans/{clan_id}/unfreeze")
async def unfreeze_clan(
    request: Request,
    clan_id: int,
) -> RedirectResponse:
    session = require_totp_verified(request)
    container = get_container(request)

    uow = SqlAlchemyUnitOfWork(container.session_factory)
    admins = SqlAlchemyAdminRepository(uow=uow)
    clans = SqlAlchemyClanRepository(uow=uow)
    audit = SqlAlchemyAdminAuditLogger(uow=uow)

    use_case = UnfreezeClanAdmin(
        uow=uow,
        admins=admins,
        clans=clans,
        audit=audit,
        clock=container.clock,
        authz=container.authorization_policy,
    )

    await use_case.execute(
        UnfreezeClanAdminInput(
            actor_tg_id=session.admin_id,
            query=clan_id,
        ),
    )

    return RedirectResponse(url=f"/clans/{clan_id}", status_code=303)
