"""Dashboard route with real data widgets (Sprint 4.5-C, ПД §7 задача 4.5.4).

Виджеты: DAU / MAU / total players, очередь регистраций,
активные караваны / рейды, последние админ-ошибки.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from pipirik_wars.admin_web.deps import get_container, require_totp_verified
from pipirik_wars.application.admin.get_dashboard_stats import (
    DashboardStats,
    ErrorEntry,
    thirty_days_ago_msk,
    today_msk,
)
from pipirik_wars.infrastructure.db.models import (
    AdminAuditLogORM,
    BossFightORM,
    CaravanORM,
    SignupQueueORM,
    UserORM,
)
from pipirik_wars.infrastructure.db.models.daily_active import DailyActiveORM
from pipirik_wars.infrastructure.db.repositories import SqlAlchemyAdminRepository
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc

router = APIRouter()

_CARAVAN_ACTIVE_STATUSES = ("lobby", "in_battle")
_RAID_ACTIVE_STATUSES = ("lobby", "in_battle")
_ACTIVE_PLAYER_STATUS = "active"
_RECENT_ERRORS_LIMIT = 20


async def _fetch_dashboard_stats(uow: SqlAlchemyUnitOfWork) -> DashboardStats:
    """Fetch all dashboard widget data within one UoW session."""
    session = uow.session
    today = today_msk()
    mau_start = thirty_days_ago_msk()

    # DAU: unique users in daily_active for today (MSK)
    dau_result = await session.execute(
        select(func.count(DailyActiveORM.user_id)).where(
            DailyActiveORM.date == today,
        ),
    )
    dau: int = int(dau_result.scalar_one())

    # MAU: unique users in daily_active for last 30 days
    mau_result = await session.execute(
        select(func.count(func.distinct(DailyActiveORM.user_id))).where(
            DailyActiveORM.date >= mau_start,
        ),
    )
    mau: int = int(mau_result.scalar_one())

    # Total players
    total_result = await session.execute(
        select(func.count(UserORM.id)).where(
            UserORM.status == _ACTIVE_PLAYER_STATUS,
        ),
    )
    total_players: int = int(total_result.scalar_one())

    # Signup queue size
    queue_result = await session.execute(
        select(func.count()).select_from(SignupQueueORM),
    )
    signup_queue_size: int = int(queue_result.scalar_one())

    # Active caravans
    caravan_result = await session.execute(
        select(func.count(CaravanORM.id)).where(
            CaravanORM.status.in_(_CARAVAN_ACTIVE_STATUSES),
        ),
    )
    active_caravans: int = int(caravan_result.scalar_one())

    # Active raids (boss_fights)
    raid_result = await session.execute(
        select(func.count(BossFightORM.id)).where(
            BossFightORM.status.in_(_RAID_ACTIVE_STATUSES),
        ),
    )
    active_raids: int = int(raid_result.scalar_one())

    # Recent admin audit log entries (errors / actions)
    audit_result = await session.execute(
        select(AdminAuditLogORM)
        .order_by(AdminAuditLogORM.occurred_at.desc())
        .limit(_RECENT_ERRORS_LIMIT),
    )
    rows = audit_result.scalars().all()
    errors = tuple(
        ErrorEntry(
            occurred_at=ensure_utc(row.occurred_at),
            action=row.action,
            admin_id=row.admin_id,
            target_kind=row.target_kind,
            target_id=row.target_id,
            reason=row.reason,
        )
        for row in rows
    )

    return DashboardStats(
        dau=dau,
        mau=mau,
        total_players=total_players,
        signup_queue_size=signup_queue_size,
        active_caravans=active_caravans,
        active_raids=active_raids,
        recent_errors=errors,
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    session = require_totp_verified(request)
    container = get_container(request)

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        repo = SqlAlchemyAdminRepository(uow=uow)
        admin = await repo.get_by_tg_id(session.admin_id)
        stats = await _fetch_dashboard_stats(uow)

    templates = request.app.state.templates
    content: str = templates.get_template("dashboard.html").render(
        request=request,
        session=session,
        admin=admin,
        stats=stats,
    )
    return HTMLResponse(content=content)


@router.get("/dashboard/stats", response_class=HTMLResponse)
async def dashboard_stats_partial(request: Request) -> HTMLResponse:
    """HTMX partial: refresh dashboard widget data without full page reload."""
    require_totp_verified(request)
    container = get_container(request)

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        stats = await _fetch_dashboard_stats(uow)

    templates = request.app.state.templates
    content: str = templates.get_template("partials/dashboard_widgets.html").render(
        stats=stats,
    )
    return HTMLResponse(content=content)
