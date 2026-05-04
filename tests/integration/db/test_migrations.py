"""Тест: alembic-миграции применяются чисто (acceptance 1.1.2).

Намеренно sync-тесты: `alembic.command.upgrade()` внутри вызывает
`asyncio.run()` (см. `migrations/env.py`), что несовместимо с уже
запущенным event-loop pytest-asyncio. Поэтому тесты не помечены
`@pytest.mark.asyncio` и выполняются вне любого активного loop.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect


def _alembic_config(db_url: str) -> Config:
    """Грузит реальный alembic.ini из корня репо и подменяет URL.

    Через `set_main_option("sqlalchemy.url", ...)` мы перекрываем
    значение из ini-файла, поэтому для теста подключения к БД
    `DatabaseSettings()` не требуется. Это позволяет гонять миграции
    на временной SQLite без `BOOTSTRAP_DATABASE_URL`-секрета в env.
    """
    repo_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _migrations_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "src/pipirik_wars/infrastructure/db/migrations/versions"


class TestAlembicMigrationsApplyCleanly:
    def test_versions_form_a_linear_chain(self) -> None:
        """Все миграции должны быть линейными (без веток): один HEAD."""
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        assert len(heads) == 1, f"expected single head, got {heads}"

    def test_expected_revisions_exist(self) -> None:
        """0001, 0002 и 0003 должны быть зарегистрированы."""
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        revisions = {rev.revision for rev in script.walk_revisions()}
        assert "0001_initial" in revisions
        assert "0002_player_clan" in revisions
        assert "0003_signup_queue" in revisions

    def test_0002_descends_from_0001(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0002 = script.get_revision("0002_player_clan")
        assert rev_0002 is not None
        assert rev_0002.down_revision == "0001_initial"

    def test_0003_descends_from_0002(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0003 = script.get_revision("0003_signup_queue")
        assert rev_0003 is not None
        assert rev_0003.down_revision == "0002_player_clan"

    def test_versions_dir_lists_only_known_files(self) -> None:
        """Если кто-то добавил миграцию мимо общего пайплайна — увидим."""
        files = sorted(p.name for p in _migrations_path().glob("*.py"))
        assert files == [
            "20260504_0001_initial_security_schema.py",
            "20260504_0002_player_clan_schema.py",
            "20260504_0003_signup_queue.py",
        ]

    def test_upgrade_head_creates_all_tables(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Прогон `alembic upgrade head` на свежей БД создаёт все таблицы.

        `migrations/env.py` берёт URL из `DatabaseSettings()`, поэтому
        `cfg.set_main_option(...)` сам по себе не помог бы — переопределяем
        через переменную окружения `DATABASE_URL` (см. `env_prefix=DATABASE_`).
        """
        db_path = tmp_path / "alembic_smoke.sqlite"
        # env.py использует async-движок (aiosqlite) — alembic сам
        # запускает event-loop через asyncio.run().
        async_url = f"sqlite+aiosqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", async_url)

        cfg = _alembic_config(async_url)
        command.upgrade(cfg, "head")

        # Чтение структуры — простой sync-движок поверх того же файла.
        engine = create_engine(f"sqlite:///{db_path}")
        try:
            with engine.connect() as conn:
                table_names = set(inspect(conn).get_table_names())
        finally:
            engine.dispose()

        # Sprint 0.2 + 1.1 + 1.2.C таблицы.
        expected = {
            "alembic_version",
            "idempotency_keys",
            "audit_log",
            "activity_locks",
            "admins",
            "users",
            "clans",
            "clan_members",
            "signup_queue",
        }
        assert expected.issubset(table_names), f"missing tables: {expected - table_names}"

    def test_downgrade_then_upgrade_round_trips(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`upgrade head` → `downgrade base` → `upgrade head` — без ошибок."""
        db_path = tmp_path / "alembic_round_trip.sqlite"
        async_url = f"sqlite+aiosqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", async_url)

        cfg = _alembic_config(async_url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
