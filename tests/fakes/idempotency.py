"""Фейк idempotency-сервиса. In-memory set ключей."""

from __future__ import annotations

from collections.abc import Sequence

from pipirik_wars.domain.shared.ports import IIdempotencyKey


class FakeIdempotencyKey(IIdempotencyKey):
    """In-memory реализация."""

    __slots__ = ("_seen",)

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def build(self, namespace: str, parts: Sequence[str]) -> str:
        if not namespace:
            raise ValueError("namespace must be non-empty")
        return namespace + ":" + "|".join(parts)

    async def is_seen(self, key: str) -> bool:
        return key in self._seen

    async def mark(self, key: str, *, namespace: str) -> None:
        if not key.startswith(namespace + ":"):
            raise ValueError(f"key {key!r} does not match namespace {namespace!r}")
        self._seen.add(key)
