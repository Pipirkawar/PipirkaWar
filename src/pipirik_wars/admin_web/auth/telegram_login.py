"""Telegram Login Widget HMAC verification (Sprint 4.5-A, §3.2)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any


class InvalidLoginHashError(Exception):
    """HMAC mismatch — forged or corrupted login data."""


class StaleLoginError(Exception):
    """``auth_date`` is older than 24 hours (anti-replay)."""


@dataclass(frozen=True, slots=True)
class TelegramLoginData:
    """Parsed fields from the TG Login Widget callback."""

    id: int
    first_name: str
    last_name: str | None
    username: str | None
    photo_url: str | None
    auth_date: int
    hash: str


def verify_telegram_login(
    *,
    data: dict[str, Any],
    bot_token: str,
    max_age_seconds: int = 86400,
) -> TelegramLoginData:
    """Verify Telegram Login Widget data and return parsed result.

    Raises ``InvalidLoginHashError`` on HMAC mismatch,
    ``StaleLoginError`` if ``auth_date`` is too old,
    ``ValueError`` if ``bot_token`` is empty.
    """
    if not bot_token:
        raise ValueError("bot_token must not be empty")

    received_hash = str(data.get("hash", ""))
    check_pairs: list[str] = []
    for key in sorted(data):
        if key == "hash":
            continue
        check_pairs.append(f"{key}={data[key]}")
    data_check_string = "\n".join(check_pairs)

    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    computed = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not secrets.compare_digest(computed, received_hash):
        raise InvalidLoginHashError("HMAC mismatch")

    auth_date = int(data.get("auth_date", 0))
    if time.time() - auth_date > max_age_seconds:
        raise StaleLoginError(f"auth_date is older than {max_age_seconds}s")

    raw_last_name: Any = data.get("last_name")
    raw_username: Any = data.get("username")
    raw_photo_url: Any = data.get("photo_url")

    return TelegramLoginData(
        id=int(data["id"]),
        first_name=str(data.get("first_name", "")),
        last_name=str(raw_last_name) if isinstance(raw_last_name, str) else None,
        username=str(raw_username) if isinstance(raw_username, str) else None,
        photo_url=str(raw_photo_url) if isinstance(raw_photo_url, str) else None,
        auth_date=auth_date,
        hash=received_hash,
    )


__all__ = [
    "InvalidLoginHashError",
    "StaleLoginError",
    "TelegramLoginData",
    "verify_telegram_login",
]
