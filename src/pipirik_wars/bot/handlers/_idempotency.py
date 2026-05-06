"""Helper для построения idempotency-ключей админ-команд (Спринт 2.5-C.5).

Формат ключа: ``admin_<command>:<sha256(admin_id|command|target|minute_floor)>``.

Минутный floor — компромисс: достаточно крупный, чтобы покрывать
двойное нажатие в Telegram (admin случайно отправил `/grant_length`
дважды), и достаточно мелкий, чтобы повторная команда минуту спустя
выполнялась как новая мутация.
"""

from __future__ import annotations

import hashlib
from datetime import datetime


def build_admin_idempotency_key(
    *,
    admin_tg_id: int,
    command: str,
    target: str,
    when: datetime,
) -> str:
    """Собрать idempotency-ключ для одной попытки админ-команды."""
    minute = when.replace(second=0, microsecond=0)
    raw = f"{admin_tg_id}|{command}|{target}|{minute.isoformat()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"admin_{command}:{digest}"


__all__ = ["build_admin_idempotency_key"]
