"""Тесты на whitelist `AuditSource` (Спринт 1.6.A + расширения).

Цель — поймать рассогласование enum-а в `domain.shared.ports.audit` и
БД-CHECK-инварианта (`audit_log.source` whitelist). Если кто-то добавит
источник только в одно из мест — тест упадёт.

Whitelist первоначально создан в миграции 0007 и расширяется
последующими миграциями. Тест читает whitelist из **последней расширяющей
миграции** — 0031 (`prize_lot_refunded`, Спринт 4.1-C / C.4).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from pipirik_wars.domain.shared.ports.audit import AuditSource


def _load_migration_whitelist() -> tuple[str, ...]:
    """Грузим whitelist прямо из файла последней расширяющей миграции.

    Файл миграции назван с timestamp-префиксом
    (`20260511_0032_audit_source_prize_lot_reserved.py`), что не валиден
    как Python-идентификатор; обычный `import` не работает.
    """
    repo_root = Path(__file__).resolve().parents[5]
    migration_path = (
        repo_root
        / "src/pipirik_wars/infrastructure/db/migrations/versions"
        / "20260511_0032_audit_source_prize_lot_reserved.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_migration_0032_audit_source_prize_lot_reserved",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    whitelist: tuple[str, ...] = module._SOURCE_WHITELIST
    return whitelist


class TestAuditSourceWhitelist:
    def test_enum_matches_migration_whitelist(self) -> None:
        enum_values = {s.value for s in AuditSource}
        migration_whitelist = set(_load_migration_whitelist())
        assert enum_values == migration_whitelist, (
            f"AuditSource enum vs migration whitelist drift:\n"
            f"  only in enum: {enum_values - migration_whitelist}\n"
            f"  only in migration: {migration_whitelist - enum_values}"
        )

    def test_unknown_is_present(self) -> None:
        """`unknown` обязан быть — backfill и дефолт для старых вызовов."""
        assert AuditSource.UNKNOWN.value == "unknown"
        assert "unknown" in _load_migration_whitelist()

    def test_organic_sources_present(self) -> None:
        """Whitelist должен покрывать минимум organic-источники из ГДД §3.3.4."""
        enum_values = {s.value for s in AuditSource}
        # Организменные source-ы, на которых строится anti-cheat clamp:
        for organic in ("forest", "oracle", "referral_signup", "referral_thickness"):
            assert organic in enum_values
