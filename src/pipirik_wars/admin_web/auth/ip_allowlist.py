"""IP-allowlist middleware (Sprint 4.5-A, §4.1).

Blocks requests from IPs not in the configured CIDR allowlist.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

HEALTH_PATHS = frozenset({"/healthz"})


def parse_cidr_list(raw: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse comma-separated CIDR list.

    ``"*"`` returns empty list (caller treats as allow-all).
    """
    raw = raw.strip()
    if not raw or raw == "*":
        return []
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in raw.split(","):
        cleaned = entry.strip()
        if not cleaned:
            continue
        networks.append(ipaddress.ip_network(cleaned, strict=False))
    return networks


class IpAllowlistMiddleware(BaseHTTPMiddleware):
    """Reject requests whose client IP is not in the allowlist."""

    def __init__(
        self,
        app: Any,
        *,
        allowed_ips_raw: str,
        trust_proxy: bool = False,
    ) -> None:
        super().__init__(app)
        self._allow_all = allowed_ips_raw.strip() == "*"
        self._networks = parse_cidr_list(allowed_ips_raw)
        self._trust_proxy = trust_proxy
        self._deny_all = not self._allow_all and len(self._networks) == 0

        if self._allow_all:
            logger.warning("ADMIN_WEB_ALLOWED_IPS='*' — all IPs allowed (use only in dev!)")
        if self._deny_all:
            logger.warning("ADMIN_WEB_ALLOWED_IPS is empty — deny-all mode (fail-closed)")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in HEALTH_PATHS:
            return await call_next(request)

        if self._allow_all:
            return await call_next(request)

        client_ip = self._resolve_ip(request)

        if self._deny_all:
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

        for net in self._networks:
            if addr in net:
                return await call_next(request)

        return JSONResponse({"detail": "Forbidden"}, status_code=403)

    def _resolve_ip(self, request: Request) -> str:
        if self._trust_proxy:
            forwarded = request.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
        host = request.client.host if request.client else "0.0.0.0"
        return host


__all__ = ["IpAllowlistMiddleware", "parse_cidr_list"]
