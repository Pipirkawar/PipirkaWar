"""IP-allowlist middleware (Sprint 4.5-A §4.1, extended in 4.5-H §4.5.9).

Blocks requests from IPs not in the configured CIDR allowlist.
Supports trusted-proxy chain parsing and private-range detection
for SSH-tunnel / VPN scenarios.
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

_PRIVATE_RANGES: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
)


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


def is_private_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check whether *addr* belongs to a private/loopback range."""
    return any(addr in net for net in _PRIVATE_RANGES)


def extract_client_ip_from_xff(
    xff_header: str,
    *,
    trusted_proxies: frozenset[ipaddress.IPv4Network | ipaddress.IPv6Network] | None = None,
) -> str:
    """Extract the real client IP from an ``X-Forwarded-For`` header.

    Walks the chain **right-to-left** (the rightmost entry was added by the
    nearest proxy).  Stops at the first IP that is *not* in the
    ``trusted_proxies`` set.  If ``trusted_proxies`` is ``None``, falls back
    to using private-range detection.
    """
    parts = [p.strip() for p in xff_header.split(",") if p.strip()]
    if not parts:
        return ""

    for ip_str in reversed(parts):
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return ip_str

        if trusted_proxies is not None:
            is_trusted = any(addr in net for net in trusted_proxies)
        else:
            is_trusted = is_private_ip(addr)

        if not is_trusted:
            return ip_str

    return parts[0]


class IpAllowlistMiddleware(BaseHTTPMiddleware):
    """Reject requests whose client IP is not in the allowlist."""

    def __init__(
        self,
        app: Any,
        *,
        allowed_ips_raw: str,
        trust_proxy: bool = False,
        trusted_proxy_cidrs: str = "",
    ) -> None:
        super().__init__(app)
        self._allow_all = allowed_ips_raw.strip() == "*"
        self._networks = parse_cidr_list(allowed_ips_raw)
        self._trust_proxy = trust_proxy
        self._deny_all = not self._allow_all and len(self._networks) == 0

        proxy_nets = parse_cidr_list(trusted_proxy_cidrs)
        self._trusted_proxies: frozenset[ipaddress.IPv4Network | ipaddress.IPv6Network] | None = (
            frozenset(proxy_nets) if proxy_nets else None
        )

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
            logger.info("ip_allowlist.deny client_ip=%s (deny-all mode)", client_ip)
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            logger.warning("ip_allowlist.invalid_ip raw=%s", client_ip)
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

        for net in self._networks:
            if addr in net:
                return await call_next(request)

        logger.info("ip_allowlist.deny client_ip=%s", client_ip)
        return JSONResponse({"detail": "Forbidden"}, status_code=403)

    def _resolve_ip(self, request: Request) -> str:
        if self._trust_proxy:
            forwarded = request.headers.get("X-Forwarded-For", "")
            if forwarded:
                return extract_client_ip_from_xff(
                    forwarded,
                    trusted_proxies=self._trusted_proxies,
                )
        host = request.client.host if request.client else "0.0.0.0"
        return host


__all__ = [
    "IpAllowlistMiddleware",
    "extract_client_ip_from_xff",
    "is_private_ip",
    "parse_cidr_list",
]
