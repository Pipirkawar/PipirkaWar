"""RBAC enforcement for admin-web routes (Sprint 4.5-B, task 4.5.2).

Reuses the same ``IAdminAuthorizationPolicy`` and ``AdminCommandKind``
from the bot RBAC (Sprint 2.5).  No separate user system — the ``admins``
table is the single source of truth.

Usage in a route::

    @router.get("/dashboard")
    async def dashboard(
        request: Request,
        admin: Admin = Depends(require_permission(AdminCommandKind.ADMIN_STATS)),
    ) -> HTMLResponse: ...

``require_permission`` returns a *factory*: each call produces a fresh
``Depends``-compatible async callable bound to the given ``command_kind``.
The callable:

1. Extracts the ``AdminSession`` from the signed cookie (via
   ``require_totp_verified``).
2. Loads the ``Admin`` entity from the DB by ``session.admin_id``.
3. Checks ``IAdminAuthorizationPolicy.is_authorized(admin, command_kind)``.
4. On denial — records ``ADMIN_AUTHORIZATION_DENIED`` in ``admin_audit_log``
   (via ``ensure_admin_authorized`` helper) and raises HTTP 403.
5. On success — returns the loaded ``Admin`` to the handler.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import HTTPException, Request

from pipirik_wars.admin_web.auth.session import AdminSession
from pipirik_wars.admin_web.composition import AdminWebContainer
from pipirik_wars.domain.admin.authorization import AdminCommandKind
from pipirik_wars.domain.admin.entities import Admin
from pipirik_wars.domain.admin.ports.admin_audit import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
)
from pipirik_wars.infrastructure.db.repositories import SqlAlchemyAdminRepository
from pipirik_wars.infrastructure.db.services.admin_audit import SqlAlchemyAdminAuditLogger
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

logger = logging.getLogger(__name__)


def require_permission(
    command_kind: AdminCommandKind,
) -> Callable[[Request], Coroutine[Any, Any, Admin]]:
    """Dependency factory: returns an async callable that enforces RBAC.

    The returned callable resolves the ``Admin`` entity (loaded from DB)
    for the current session and verifies the permission via
    ``RoleBasedAdminAuthorizationPolicy``.

    Raises:
        HTTPException(401): session missing or TOTP not verified.
        HTTPException(403): admin not found, inactive, or lacks permission.
    """

    async def _check(request: Request) -> Admin:
        from pipirik_wars.admin_web.deps import require_totp_verified  # noqa: PLC0415

        session: AdminSession = require_totp_verified(request)
        container: AdminWebContainer = request.app.state.container

        async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
            repo = SqlAlchemyAdminRepository(uow=uow)
            admin = await repo.get_by_tg_id(session.admin_id)

            if admin is None or not admin.is_active:
                audit = SqlAlchemyAdminAuditLogger(uow=uow)
                await audit.record(
                    AdminAuditEntry(
                        admin_id=admin.id if admin and admin.id is not None else 0,
                        action=AdminAuditAction.ADMIN_AUTHORIZATION_DENIED,
                        target_kind="web_route",
                        target_id=command_kind.value,
                        before=None,
                        after={"command_kind": command_kind.value},
                        reason=f"web_rbac:admin_{'inactive' if admin else 'not_found'}",
                        idempotency_key=None,
                        source=AdminAuditSource.WEB,
                        tg_chat_id=None,
                        ip=request.client.host if request.client else None,
                        occurred_at=container.clock.now(),
                    ),
                )
                await uow.commit()
                raise HTTPException(status_code=403, detail="Forbidden")

            policy = container.authorization_policy
            if not policy.is_authorized(admin, command_kind):
                admin_id = admin.id
                if admin_id is None:  # pragma: no cover
                    raise HTTPException(status_code=403, detail="Forbidden")
                audit = SqlAlchemyAdminAuditLogger(uow=uow)
                await audit.record(
                    AdminAuditEntry(
                        admin_id=admin_id,
                        action=AdminAuditAction.ADMIN_AUTHORIZATION_DENIED,
                        target_kind="web_route",
                        target_id=command_kind.value,
                        before=None,
                        after={
                            "command_kind": command_kind.value,
                            "actor_role": admin.role.value,
                        },
                        reason=(f"web_rbac:denied:{command_kind.value}:role={admin.role.value}"),
                        idempotency_key=None,
                        source=AdminAuditSource.WEB,
                        tg_chat_id=None,
                        ip=request.client.host if request.client else None,
                        occurred_at=container.clock.now(),
                    ),
                )
                await uow.commit()
                logger.warning(
                    "rbac.denied command=%s role=%s admin_id=%s",
                    command_kind.value,
                    admin.role.value,
                    admin_id,
                )
                raise HTTPException(status_code=403, detail="Forbidden")

        return admin

    return _check


__all__ = ["require_permission"]
