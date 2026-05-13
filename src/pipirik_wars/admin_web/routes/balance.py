"""Balance editor routes (Sprint 4.5-G, task 4.5.8).

Provides:
- ``GET /balance`` — overview of all balance.yaml sections.
- ``GET /balance/{section}`` — editor view for a specific section.
- ``POST /balance/{section}`` — save updated section YAML (with audit).
- ``POST /balance/reload`` — hot-reload balance config in-memory.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError

from pipirik_wars.admin_web.composition import AdminWebContainer
from pipirik_wars.admin_web.deps import get_container, require_totp_verified
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
)
from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.infrastructure.db.repositories import SqlAlchemyAdminRepository
from pipirik_wars.infrastructure.db.services.admin_audit import (
    SqlAlchemyAdminAuditLogger,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import ConfigError

router = APIRouter()

_SECTION_DESCRIPTIONS: dict[str, str] = {
    "version": "Версия конфигурации баланса",
    "display_names": "Таблица «Длина → Название» (ГДД §2.3)",
    "forest": "Конфиг похода в лес (ГДД §8.2)",
    "mountains": "Конфиг гор (ГДД §8, Спринт 3.1.1)",
    "dungeon": "Конфиг данжона (ГДД §8, Спринт 3.1.2)",
    "caravans": "Конфиг караванов (ГДД §9)",
    "bosses": "Конфиг боссов",
    "oracle": "Предсказатель (ГДД §11)",
    "referral": "Реферальная схема (ГДД §13.1)",
    "thickness": "Формула цены толщины (ГДД §3.2)",
    "dau_gate": "DAU-Gate (ГДД §0.5)",
    "daily_head": "Глава клана дня (ГДД §6.1)",
    "anticheat": "Анти-чит хардкап (ГДД §3.3.5)",
    "pvp": "PvP-конфиг",
    "content_policy": "Политика контента",
    "enchantment": "Конфиг заточки (ГДД §2.8)",
    "roulette": "Конфиг рулетки",
    "prize_lot": "Конфиг призовых лотов",
    "monetization": "Конфиг монетизации",
    "items_catalog": "Каталог экипировки (ГДД §1.3.5, §2.6)",
    "names_catalog": "Каталог имён (ГДД §2.5)",
}


def _section_names() -> list[str]:
    """Return top-level field names of BalanceConfig in declaration order."""
    return list(BalanceConfig.model_fields.keys())


def _section_to_raw(snapshot: BalanceConfig, section: str) -> Any:
    """Extract a section from BalanceConfig as a JSON-friendly dict/list."""
    value = getattr(snapshot, section)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, tuple):
        return [
            item.model_dump(mode="json", by_alias=True) if isinstance(item, BaseModel) else item
            for item in value
        ]
    return value


def _section_to_yaml(snapshot: BalanceConfig, section: str) -> str:
    """Serialize a section to YAML text for the editor."""
    raw = _section_to_raw(snapshot, section)
    return yaml.safe_dump(
        raw,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )


def _get_balance_yaml_path(container: AdminWebContainer) -> Path:
    """Resolve the balance.yaml path from settings."""
    return Path(container.settings.balance_yaml_path)


def _atomic_write_yaml(path: Path, raw: dict[str, Any]) -> None:
    """Atomic write of full YAML dict to disk (tmp + os.replace)."""
    text = yaml.safe_dump(
        raw,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


@router.get("/balance", response_class=HTMLResponse)
async def balance_overview(request: Request) -> HTMLResponse:
    """Render the balance overview page listing all sections."""
    session = require_totp_verified(request)
    container = get_container(request)
    snapshot = container.balance_config.get()
    sections = [
        {"name": name, "description": _SECTION_DESCRIPTIONS.get(name, "")}
        for name in _section_names()
    ]
    templates = request.app.state.templates
    content: str = templates.get_template("balance_overview.html").render(
        request=request,
        session=session,
        sections=sections,
        version=snapshot.version,
    )
    return HTMLResponse(content=content)


@router.get("/balance/{section}", response_class=HTMLResponse)
async def balance_section_editor(request: Request, section: str) -> HTMLResponse:
    """Render the editor for a specific balance section."""
    session = require_totp_verified(request)
    container = get_container(request)
    snapshot = container.balance_config.get()

    if section not in BalanceConfig.model_fields:
        templates = request.app.state.templates
        content: str = templates.get_template("balance_editor.html").render(
            request=request,
            session=session,
            section=section,
            error=f"Секция «{section}» не найдена в BalanceConfig.",
            yaml_text="",
            version=snapshot.version,
            description="",
        )
        return HTMLResponse(content=content, status_code=404)

    yaml_text = _section_to_yaml(snapshot, section)

    templates = request.app.state.templates
    content = templates.get_template("balance_editor.html").render(
        request=request,
        session=session,
        section=section,
        yaml_text=yaml_text,
        version=snapshot.version,
        description=_SECTION_DESCRIPTIONS.get(section, ""),
        error=None,
        success=None,
    )
    return HTMLResponse(content=content)


@router.post("/balance/reload", response_class=HTMLResponse)
async def balance_reload(request: Request) -> HTMLResponse:
    """Hot-reload balance config from disk."""
    session = require_totp_verified(request)
    container = get_container(request)
    client_ip = request.client.host if request.client else None

    try:
        new_snapshot = container.balance_reloader.reload()
    except ConfigError as e:
        templates = request.app.state.templates
        content: str = templates.get_template("balance_overview.html").render(
            request=request,
            session=session,
            sections=[
                {"name": n, "description": _SECTION_DESCRIPTIONS.get(n, "")}
                for n in _section_names()
            ],
            version=container.balance_config.get().version,
            error=f"Ошибка reload: {e}",
        )
        return HTMLResponse(content=content, status_code=500)

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        repo = SqlAlchemyAdminRepository(uow=uow)
        admin = await repo.get_by_tg_id(session.admin_id)
        if admin is not None and admin.id is not None:
            audit = SqlAlchemyAdminAuditLogger(uow=uow)
            await audit.record(
                AdminAuditEntry(
                    admin_id=admin.id,
                    action=AdminAuditAction.ADMIN_BALANCE_SET,
                    target_kind="balance_reload",
                    target_id="*",
                    before=None,
                    after={"version": new_snapshot.version},
                    reason="web_balance_reload",
                    idempotency_key=f"web_balance_reload_{uuid.uuid4().hex}",
                    source=AdminAuditSource.WEB,
                    tg_chat_id=None,
                    ip=client_ip,
                    occurred_at=container.clock.now(),
                ),
            )

    templates = request.app.state.templates
    content = templates.get_template("balance_overview.html").render(
        request=request,
        session=session,
        sections=[
            {"name": n, "description": _SECTION_DESCRIPTIONS.get(n, "")} for n in _section_names()
        ],
        version=new_snapshot.version,
        success=f"Баланс перезагружен. Версия: {new_snapshot.version}.",
    )
    return HTMLResponse(content=content)


def _validate_and_write_section(
    container: AdminWebContainer,
    section: str,
    yaml_text: str,
) -> tuple[BalanceConfig, Any, Any] | str:
    """Parse, validate, write and reload a balance section.

    Returns ``(new_snapshot, before_raw, new_section_value)`` on success,
    or an error message string on failure.
    """
    try:
        new_section_value = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        return f"Невалидный YAML: {e}"

    snapshot_before = container.balance_config.get()
    before_raw = _section_to_raw(snapshot_before, section)

    balance_path = _get_balance_yaml_path(container)
    try:
        raw_file: dict[str, Any] = yaml.safe_load(
            balance_path.read_text(encoding="utf-8"),
        )
    except (OSError, yaml.YAMLError) as e:
        return f"Ошибка чтения balance.yaml: {e}"

    raw_file[section] = new_section_value

    try:
        BalanceConfig.model_validate(raw_file)
    except ValidationError as e:
        return f"Ошибка валидации: {e}"

    try:
        _atomic_write_yaml(balance_path, raw_file)
    except OSError as e:
        return f"Ошибка записи файла: {e}"

    try:
        new_snapshot = container.balance_reloader.reload()
    except ConfigError as e:
        return f"Ошибка reload: {e}"

    return new_snapshot, before_raw, new_section_value


@router.post("/balance/{section}", response_class=HTMLResponse)
async def balance_section_save(request: Request, section: str) -> HTMLResponse:
    """Validate and save updated YAML for a section."""
    session = require_totp_verified(request)
    container = get_container(request)

    if section not in BalanceConfig.model_fields:
        return _render_editor_error(
            request,
            session,
            section,
            "",
            container,
            error=f"Секция «{section}» не найдена.",
            status_code=404,
        )

    form = await request.form()
    yaml_text = str(form.get("yaml_text", ""))
    client_ip = request.client.host if request.client else None

    result = _validate_and_write_section(container, section, yaml_text)
    if isinstance(result, str):
        return _render_editor_error(
            request,
            session,
            section,
            yaml_text,
            container,
            error=result,
        )

    new_snapshot, before_raw, new_section_value = result

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        repo = SqlAlchemyAdminRepository(uow=uow)
        admin = await repo.get_by_tg_id(session.admin_id)
        if admin is not None and admin.id is not None:
            audit = SqlAlchemyAdminAuditLogger(uow=uow)
            await audit.record(
                AdminAuditEntry(
                    admin_id=admin.id,
                    action=AdminAuditAction.ADMIN_BALANCE_SET,
                    target_kind="balance_section",
                    target_id=section,
                    before={"value": before_raw},
                    after={"value": new_section_value},
                    reason=f"web_balance_editor:{section}",
                    idempotency_key=f"web_balance_{section}_{uuid.uuid4().hex}",
                    source=AdminAuditSource.WEB,
                    tg_chat_id=None,
                    ip=client_ip,
                    occurred_at=container.clock.now(),
                ),
            )

    new_yaml_text = _section_to_yaml(new_snapshot, section)
    templates = request.app.state.templates
    content: str = templates.get_template("balance_editor.html").render(
        request=request,
        session=session,
        section=section,
        yaml_text=new_yaml_text,
        version=new_snapshot.version,
        description=_SECTION_DESCRIPTIONS.get(section, ""),
        error=None,
        success=f"Секция «{section}» сохранена. Версия баланса: {new_snapshot.version}.",
    )
    return HTMLResponse(content=content)


def _render_editor_error(
    request: Request,
    session: object,
    section: str,
    yaml_text: str,
    container: AdminWebContainer,
    *,
    error: str,
    status_code: int = 400,
) -> HTMLResponse:
    snapshot = container.balance_config.get()
    templates = request.app.state.templates
    content: str = templates.get_template("balance_editor.html").render(
        request=request,
        session=session,
        section=section,
        yaml_text=yaml_text,
        version=snapshot.version,
        description=_SECTION_DESCRIPTIONS.get(section, ""),
        error=error,
        success=None,
    )
    return HTMLResponse(content=content, status_code=status_code)
