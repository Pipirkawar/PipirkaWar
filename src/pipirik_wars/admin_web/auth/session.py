"""Signed-cookie session management via ``itsdangerous`` (Sprint 4.5-A, §1.4)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Self

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


@dataclass(slots=True)
class AdminSession:
    """In-cookie session payload."""

    admin_id: int
    tg_username: str | None
    totp_verified_at: float | None
    csrf_token: str

    def to_dict(self) -> dict[str, object]:
        return {
            "admin_id": self.admin_id,
            "tg_username": self.tg_username,
            "totp_verified_at": self.totp_verified_at,
            "csrf_token": self.csrf_token,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        raw_admin_id: Any = data["admin_id"]
        raw_tg_username: Any = data.get("tg_username")
        raw_totp_verified: Any = data.get("totp_verified_at")
        return cls(
            admin_id=int(raw_admin_id),
            tg_username=str(raw_tg_username) if raw_tg_username is not None else None,
            totp_verified_at=float(raw_totp_verified) if raw_totp_verified is not None else None,
            csrf_token=str(data["csrf_token"]),
        )


class SessionManager:
    """Encode / decode admin session cookies."""

    def __init__(self, *, secret_key: str, max_age: int) -> None:
        self._serializer = URLSafeTimedSerializer(secret_key)
        self._max_age = max_age

    def encode(self, session: AdminSession) -> str:
        payload = json.dumps(session.to_dict(), separators=(",", ":"))
        result: str = self._serializer.dumps(payload)
        return result

    def decode(self, cookie_value: str) -> AdminSession:
        """Decode and verify cookie.

        Raises ``BadSignature`` on tampered data,
        ``SignatureExpired`` when max-age exceeded.
        """
        raw: str = self._serializer.loads(cookie_value, max_age=self._max_age)
        data: dict[str, Any] = json.loads(raw)
        return AdminSession.from_dict(data)


__all__ = ["AdminSession", "BadSignature", "SessionManager", "SignatureExpired"]
