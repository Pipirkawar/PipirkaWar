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
        """0001..0010 должны быть зарегистрированы."""
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        revisions = {rev.revision for rev in script.walk_revisions()}
        assert "0001_initial" in revisions
        assert "0002_player_clan" in revisions
        assert "0003_signup_queue" in revisions
        assert "0004_forest_runs" in revisions
        assert "0005_oracle_invocations" in revisions
        assert "0006_users_locale_override" in revisions
        assert "0007_anticheat_foundation" in revisions
        assert "0008_audit_log_delta_cm" in revisions
        assert "0009_pvp_duels" in revisions
        assert "0010_pvp_global_lobby" in revisions
        assert "0011_pvp_mass_duels" in revisions
        assert "0012_daily_heads" in revisions
        assert "0013_daily_active" in revisions
        assert "0014_audit_source_daily_head" in revisions
        assert "0015_referrals" in revisions
        assert "0016_admin_audit_log" in revisions
        assert "0017_admins_totp_secret" in revisions

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

    def test_0004_descends_from_0003(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0004 = script.get_revision("0004_forest_runs")
        assert rev_0004 is not None
        assert rev_0004.down_revision == "0003_signup_queue"

    def test_0005_descends_from_0004(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0005 = script.get_revision("0005_oracle_invocations")
        assert rev_0005 is not None
        assert rev_0005.down_revision == "0004_forest_runs"

    def test_0006_descends_from_0005(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0006 = script.get_revision("0006_users_locale_override")
        assert rev_0006 is not None
        assert rev_0006.down_revision == "0005_oracle_invocations"

    def test_0007_descends_from_0006(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0007 = script.get_revision("0007_anticheat_foundation")
        assert rev_0007 is not None
        assert rev_0007.down_revision == "0006_users_locale_override"

    def test_0008_descends_from_0007(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0008 = script.get_revision("0008_audit_log_delta_cm")
        assert rev_0008 is not None
        assert rev_0008.down_revision == "0007_anticheat_foundation"

    def test_0009_descends_from_0008(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0009 = script.get_revision("0009_pvp_duels")
        assert rev_0009 is not None
        assert rev_0009.down_revision == "0008_audit_log_delta_cm"

    def test_0010_descends_from_0009(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0010 = script.get_revision("0010_pvp_global_lobby")
        assert rev_0010 is not None
        assert rev_0010.down_revision == "0009_pvp_duels"

    def test_0011_descends_from_0010(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0011 = script.get_revision("0011_pvp_mass_duels")
        assert rev_0011 is not None
        assert rev_0011.down_revision == "0010_pvp_global_lobby"

    def test_0012_descends_from_0011(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0012 = script.get_revision("0012_daily_heads")
        assert rev_0012 is not None
        assert rev_0012.down_revision == "0011_pvp_mass_duels"

    def test_0013_descends_from_0012(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0013 = script.get_revision("0013_daily_active")
        assert rev_0013 is not None
        assert rev_0013.down_revision == "0012_daily_heads"

    def test_0014_descends_from_0013(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0014 = script.get_revision("0014_audit_source_daily_head")
        assert rev_0014 is not None
        assert rev_0014.down_revision == "0013_daily_active"

    def test_0016_descends_from_0015(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0016 = script.get_revision("0016_admin_audit_log")
        assert rev_0016 is not None
        assert rev_0016.down_revision == "0015_referrals"

    def test_0017_descends_from_0016(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0017 = script.get_revision("0017_admins_totp_secret")
        assert rev_0017 is not None
        assert rev_0017.down_revision == "0016_admin_audit_log"

    def test_0018_descends_from_0017(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0018 = script.get_revision("0018_pve_runs")
        assert rev_0018 is not None
        assert rev_0018.down_revision == "0017_admins_totp_secret"

    def test_0019_descends_from_0018(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0019 = script.get_revision("0019_caravans")
        assert rev_0019 is not None
        assert rev_0019.down_revision == "0018_pve_runs"

    def test_0020_descends_from_0019(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0020 = script.get_revision("0020_boss_fights")
        assert rev_0020 is not None
        assert rev_0020.down_revision == "0019_caravans"

    def test_versions_dir_lists_only_known_files(self) -> None:
        """Если кто-то добавил миграцию мимо общего пайплайна — увидим."""
        files = sorted(p.name for p in _migrations_path().glob("*.py"))
        assert files == [
            "20260504_0001_initial_security_schema.py",
            "20260504_0002_player_clan_schema.py",
            "20260504_0003_signup_queue.py",
            "20260504_0004_forest_runs.py",
            "20260505_0005_oracle_invocations.py",
            "20260505_0006_users_locale_override.py",
            "20260505_0007_anticheat_foundation.py",
            "20260505_0008_audit_log_delta_cm.py",
            "20260505_0009_pvp_duels.py",
            "20260505_0010_pvp_global_lobby.py",
            "20260505_0011_pvp_mass_duels.py",
            "20260506_0012_daily_heads.py",
            "20260506_0013_daily_active.py",
            "20260506_0014_audit_source_daily_head.py",
            "20260506_0015_referrals.py",
            "20260507_0016_admin_audit_log.py",
            "20260507_0017_admins_totp_secret.py",
            "20260507_0018_pve_runs.py",
            "20260508_0019_caravans.py",
            "20260508_0020_boss_fights.py",
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

        # Sprint 0.2 + 1.1 + 1.2.C + 1.3.B + 1.4.B + 2.1.C + 2.1.F таблицы.
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
            "forest_runs",
            "oracle_invocations",
            "pvp_duels",
            "pvp_duel_rounds",
            "pvp_global_lobby",
            "pvp_mass_duels",
            "pvp_mass_duel_choices",
            "pvp_mass_duel_damage_entries",
            "daily_heads",
            "daily_active",
            "referrals",
            "admin_audit_log",
        }
        assert expected.issubset(table_names), f"missing tables: {expected - table_names}"

    def test_0007_adds_anticheat_columns(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Спринт 1.6.A: миграция добавляет нужные колонки + источники в whitelist."""
        db_path = tmp_path / "alembic_0007.sqlite"
        async_url = f"sqlite+aiosqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", async_url)

        cfg = _alembic_config(async_url)
        command.upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{db_path}")
        try:
            with engine.connect() as conn:
                inspector = inspect(conn)
                user_cols = {c["name"] for c in inspector.get_columns("users")}
                audit_cols = {c["name"] for c in inspector.get_columns("audit_log")}
        finally:
            engine.dispose()

        assert "anticheat_ban_until" in user_cols
        assert "source" in audit_cols
        assert "clamped_from" in audit_cols

    def test_0008_adds_delta_cm_column(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Спринт 1.6.C: миграция добавляет `audit_log.delta_cm` + composite-индекс."""
        db_path = tmp_path / "alembic_0008.sqlite"
        async_url = f"sqlite+aiosqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", async_url)

        cfg = _alembic_config(async_url)
        command.upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{db_path}")
        try:
            with engine.connect() as conn:
                inspector = inspect(conn)
                audit_cols = {c["name"] for c in inspector.get_columns("audit_log")}
                index_names = {ix["name"] for ix in inspector.get_indexes("audit_log")}
        finally:
            engine.dispose()

        assert "delta_cm" in audit_cols
        assert "ix_audit_log_target_source_occurred" in index_names

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
