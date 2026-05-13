"""Health check endpoint (Sprint 4.5-A, §3.8)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

router = APIRouter()

_START_TIME: float = time.time()


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, object]:
    return {"status": "ok", "uptime_seconds": int(time.time() - _START_TIME)}
