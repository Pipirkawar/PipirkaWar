"""Smoke-тест: все порты — абстрактные, экземпляр без реализации не создаётся."""

from __future__ import annotations

import pytest

from pipirik_wars.domain.shared.ports import (
    IAuditLogger,
    IClock,
    IIdempotencyKey,
    IRandom,
    IUnitOfWork,
)


@pytest.mark.parametrize(
    "port_cls",
    [IClock, IRandom, IUnitOfWork, IIdempotencyKey, IAuditLogger],
)
def test_ports_cannot_be_instantiated_directly(
    port_cls: type[object],
) -> None:
    with pytest.raises(TypeError):
        port_cls()
