"""Players section routes (Sprint 4.5-D, task 4.5.5).

Routes:
- GET  /players                       — list / HTMX live-search
- GET  /players/search                — HTMX partial for search results
- GET  /players/{player_id}           — player card
- GET  /players/{player_id}/activity  — activity / audit trail
- POST /players/{player_id}/ban       — ban player
- POST /players/{player_id}/freeze    — freeze player
- POST /players/{player_id}/unfreeze  — unfreeze player
- POST /players/{player_id}/grant-length     — grant length
- POST /players/{player_id}/grant-thickness  — grant thickness

All actions delegate to existing application use-cases.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from pipirik_wars.admin_web.deps import get_container, require_totp_verified
from pipirik_wars.application.admin.ban_player import BanPlayer, BanPlayerInput
from pipirik_wars.application.admin.find_players import (
    FindPlayers,
    FindPlayersInput,
    PlayerSummary,
)
from pipirik_wars.application.admin.freeze_player import FreezePlayer, FreezePlayerInput
from pipirik_wars.application.admin.get_player_card import (
    GetPlayerCard,
    GetPlayerCardInput,
)
from pipirik_wars.application.admin.unfreeze_player import (
    UnfreezePlayer,
    UnfreezePlayerInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
)
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyAdminRepository,
    SqlAlchemyClanMembershipRepository,
    SqlAlchemyClanRepository,
    SqlAlchemyForestRunRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.services.admin_audit import (
    SqlAlchemyAdminAuditLogger,
    SqlAlchemyAdminAuditQuery,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/players")

_SEARCH_LIMIT = 50
_ACTIVITY_LIMIT = 30


def _render(request: Request, template: str, **ctx: object) -> HTMLResponse:
    templates = request.app.state.templates
    content: str = templates.get_template(template).render(request=request, **ctx)
    return HTMLResponse(content=content)


@router.get("", response_class=HTMLResponse)
async def players_list(request: Request) -> HTMLResponse:
    """Full page with search input and initial empty results."""
    session = require_totp_verified(request)
    query = request.query_params.get("q", "").strip()
    results: list[PlayerSummary] = []

    if query:
        container = get_container(request)
        async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
            repo = SqlAlchemyPlayerRepository(uow=uow)
            admins = SqlAlchemyAdminRepository(uow=uow)
            audit = SqlAlchemyAdminAuditLogger(uow=uow)
            uc = FindPlayers(
                uow=uow,
                admins=admins,
                players=repo,
                audit=audit,
                clock=container.clock,
                authz=container.authorization_policy,
                limit=_SEARCH_LIMIT,
            )
            try:
                output = await uc.execute(
                    FindPlayersInput(
                        actor_tg_id=session.admin_id,
                        query=query,
                    ),
                )
                results = list(output.results)
            except AuthorizationError:
                raise HTTPException(status_code=403, detail="Forbidden") from None

    return _render(
        request,
        "players_list.html",
        session=session,
        query=query,
        results=results,
    )


@router.get("/search", response_class=HTMLResponse)
async def players_search(request: Request) -> HTMLResponse:
    """HTMX partial: returns only the results table rows."""
    session = require_totp_verified(request)
    query = request.query_params.get("q", "").strip()
    results: list[PlayerSummary] = []

    if query:
        container = get_container(request)
        async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
            repo = SqlAlchemyPlayerRepository(uow=uow)
            admins = SqlAlchemyAdminRepository(uow=uow)
            audit = SqlAlchemyAdminAuditLogger(uow=uow)
            uc = FindPlayers(
                uow=uow,
                admins=admins,
                players=repo,
                audit=audit,
                clock=container.clock,
                authz=container.authorization_policy,
                limit=_SEARCH_LIMIT,
            )
            try:
                output = await uc.execute(
                    FindPlayersInput(
                        actor_tg_id=session.admin_id,
                        query=query,
                    ),
                )
                results = list(output.results)
            except AuthorizationError:
                raise HTTPException(status_code=403, detail="Forbidden") from None

    return _render(
        request,
        "partials/players_rows.html",
        results=results,
        query=query,
    )


@router.get("/{player_tg_id}", response_class=HTMLResponse)
async def player_card(request: Request, player_tg_id: int) -> HTMLResponse:
    """Full player card page."""
    session = require_totp_verified(request)
    container = get_container(request)

    flash = request.query_params.get("flash", "")

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        admins = SqlAlchemyAdminRepository(uow=uow)
        players = SqlAlchemyPlayerRepository(uow=uow)
        clans = SqlAlchemyClanRepository(uow=uow)
        clan_members = SqlAlchemyClanMembershipRepository(uow=uow)
        forest_runs = SqlAlchemyForestRunRepository(uow=uow, balance=container.balance_config)
        audit = SqlAlchemyAdminAuditLogger(uow=uow)

        uc = GetPlayerCard(
            uow=uow,
            admins=admins,
            players=players,
            clans=clans,
            clan_members=clan_members,
            forest_runs=forest_runs,
            audit=audit,
            clock=container.clock,
            authz=container.authorization_policy,
        )
        try:
            output = await uc.execute(
                GetPlayerCardInput(
                    actor_tg_id=session.admin_id,
                    target_tg_id=player_tg_id,
                ),
            )
        except AuthorizationError:
            raise HTTPException(status_code=403, detail="Forbidden") from None

    if output.card is None:
        raise HTTPException(status_code=404, detail="Player not found") from None

    return _render(
        request,
        "player_card.html",
        session=session,
        card=output.card,
        player_tg_id=player_tg_id,
        flash=flash,
    )


@router.get("/{player_tg_id}/activity", response_class=HTMLResponse)
async def player_activity(request: Request, player_tg_id: int) -> HTMLResponse:
    """Activity / audit trail for a specific player."""
    session = require_totp_verified(request)
    container = get_container(request)

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        admins = SqlAlchemyAdminRepository(uow=uow)
        audit_query = SqlAlchemyAdminAuditQuery(uow=uow)
        audit_logger = SqlAlchemyAdminAuditLogger(uow=uow)

        admin = await admins.get_by_tg_id(session.admin_id)
        if admin is None or not admin.is_active:
            raise HTTPException(status_code=403, detail="Forbidden") from None

        admin_id = admin.id
        if admin_id is None:  # pragma: no cover
            raise HTTPException(status_code=500, detail="Server error")

        records = await audit_query.list_recent(
            limit=_ACTIVITY_LIMIT,
            action=None,
        )
        player_records = [
            r for r in records if r.target_kind == "player" and r.target_id == str(player_tg_id)
        ]

        now = container.clock.now()
        await audit_logger.record(
            AdminAuditEntry(
                admin_id=admin_id,
                action=AdminAuditAction.ADMIN_PLAYER_LOOKUP,
                target_kind="player_activity",
                target_id=str(player_tg_id),
                before=None,
                after={"records": len(player_records)},
                reason=f"player_activity:{player_tg_id}",
                idempotency_key=None,
                source=AdminAuditSource.WEB,
                tg_chat_id=None,
                ip=request.client.host if request.client else None,
                occurred_at=now,
            ),
        )

    return _render(
        request,
        "partials/player_activity.html",
        session=session,
        player_tg_id=player_tg_id,
        records=player_records,
    )


@router.post("/{player_tg_id}/ban", response_class=HTMLResponse)
async def ban_player_action(request: Request, player_tg_id: int) -> HTMLResponse:
    """Ban a player via existing use-case."""
    session = require_totp_verified(request)
    container = get_container(request)
    form = await request.form()
    reason = str(form.get("reason", "")).strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Reason is required")

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        admins = SqlAlchemyAdminRepository(uow=uow)
        players = SqlAlchemyPlayerRepository(uow=uow)
        audit = SqlAlchemyAdminAuditLogger(uow=uow)

        uc = BanPlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=container.clock,
            authz=container.authorization_policy,
        )
        try:
            output = await uc.execute(
                BanPlayerInput(
                    actor_tg_id=session.admin_id,
                    target_tg_id=player_tg_id,
                    reason=reason,
                ),
            )
        except AuthorizationError:
            raise HTTPException(status_code=403, detail="Forbidden") from None
        except PlayerNotFoundError:
            raise HTTPException(status_code=404, detail="Player not found") from None

    flash = "already_banned" if output.was_already_banned else "banned"
    return _redirect_to_card(player_tg_id, flash)


@router.post("/{player_tg_id}/freeze", response_class=HTMLResponse)
async def freeze_player_action(request: Request, player_tg_id: int) -> HTMLResponse:
    """Freeze a player."""
    session = require_totp_verified(request)
    container = get_container(request)
    form = await request.form()
    reason = str(form.get("reason", "")) or None

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        admins = SqlAlchemyAdminRepository(uow=uow)
        players = SqlAlchemyPlayerRepository(uow=uow)
        audit = SqlAlchemyAdminAuditLogger(uow=uow)

        uc = FreezePlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=container.clock,
            authz=container.authorization_policy,
        )
        try:
            output = await uc.execute(
                FreezePlayerInput(
                    actor_tg_id=session.admin_id,
                    target_tg_id=player_tg_id,
                    reason=reason,
                ),
            )
        except AuthorizationError:
            raise HTTPException(status_code=403, detail="Forbidden") from None
        except PlayerNotFoundError:
            raise HTTPException(status_code=404, detail="Player not found") from None

    flash = "already_frozen" if output.was_already_frozen else "frozen"
    return _redirect_to_card(player_tg_id, flash)


@router.post("/{player_tg_id}/unfreeze", response_class=HTMLResponse)
async def unfreeze_player_action(request: Request, player_tg_id: int) -> HTMLResponse:
    """Unfreeze a player."""
    session = require_totp_verified(request)
    container = get_container(request)

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        admins = SqlAlchemyAdminRepository(uow=uow)
        players = SqlAlchemyPlayerRepository(uow=uow)
        audit = SqlAlchemyAdminAuditLogger(uow=uow)

        uc = UnfreezePlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=container.clock,
            authz=container.authorization_policy,
        )
        try:
            output = await uc.execute(
                UnfreezePlayerInput(
                    actor_tg_id=session.admin_id,
                    target_tg_id=player_tg_id,
                ),
            )
        except AuthorizationError:
            raise HTTPException(status_code=403, detail="Forbidden") from None
        except PlayerNotFoundError:
            raise HTTPException(status_code=404, detail="Player not found") from None

    flash = "already_active" if output.was_already_active else "unfrozen"
    return _redirect_to_card(player_tg_id, flash)


def _redirect_to_card(player_tg_id: int, flash: str) -> HTMLResponse:
    """HX-Redirect header for HTMX, fallback Location for browsers."""
    response = HTMLResponse(content="", status_code=303)
    url = f"/players/{player_tg_id}?flash={flash}"
    response.headers["Location"] = url
    response.headers["HX-Redirect"] = url
    return response
