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
        assert "0018_pve_runs" in revisions
        assert "0019_caravans" in revisions
        assert "0020_boss_fights" in revisions
        assert "0021_items" in revisions
        assert "0022_scrolls" in revisions
        assert "0023_roulette_spins" in revisions
        assert "0024_audit_source_roulette_free" in revisions
        assert "0025_audit_source_oracle_tribe_bonus" in revisions
        assert "0026_payments_and_audit_source" in revisions
        assert "0027_prize_pool_balance" in revisions
        assert "0028_audit_source_prize_pool_increment" in revisions
        assert "0029_audit_source_prize_lot_generated" in revisions
        assert "0030_prize_lots" in revisions
        assert "0031_audit_source_prize_lot_refunded" in revisions
        assert "0032_audit_source_prize_lot_reserved" in revisions
        assert "0037_payout_freeze_and_prize_lot_winner_id" in revisions
        assert "0038_ton_connect_nonces" in revisions

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

    def test_0021_descends_from_0020(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0021 = script.get_revision("0021_items")
        assert rev_0021 is not None
        assert rev_0021.down_revision == "0020_boss_fights"

    def test_0022_descends_from_0021(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0022 = script.get_revision("0022_scrolls")
        assert rev_0022 is not None
        assert rev_0022.down_revision == "0021_items"

    def test_0023_descends_from_0022(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0023 = script.get_revision("0023_roulette_spins")
        assert rev_0023 is not None
        assert rev_0023.down_revision == "0022_scrolls"

    def test_0024_descends_from_0023(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0024 = script.get_revision("0024_audit_source_roulette_free")
        assert rev_0024 is not None
        assert rev_0024.down_revision == "0023_roulette_spins"

    def test_0025_descends_from_0024(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0025 = script.get_revision("0025_audit_source_oracle_tribe_bonus")
        assert rev_0025 is not None
        assert rev_0025.down_revision == "0024_audit_source_roulette_free"

    def test_0026_descends_from_0025(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0026 = script.get_revision("0026_payments_and_audit_source")
        assert rev_0026 is not None
        assert rev_0026.down_revision == "0025_audit_source_oracle_tribe_bonus"

    def test_0027_descends_from_0026(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0027 = script.get_revision("0027_prize_pool_balance")
        assert rev_0027 is not None
        assert rev_0027.down_revision == "0026_payments_and_audit_source"

    def test_0028_descends_from_0027(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0028 = script.get_revision("0028_audit_source_prize_pool_increment")
        assert rev_0028 is not None
        assert rev_0028.down_revision == "0027_prize_pool_balance"

    def test_0029_descends_from_0028(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0029 = script.get_revision("0029_audit_source_prize_lot_generated")
        assert rev_0029 is not None
        assert rev_0029.down_revision == "0028_audit_source_prize_pool_increment"

    def test_0030_descends_from_0029(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0030 = script.get_revision("0030_prize_lots")
        assert rev_0030 is not None
        assert rev_0030.down_revision == "0029_audit_source_prize_lot_generated"

    def test_0031_descends_from_0030(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0031 = script.get_revision("0031_audit_source_prize_lot_refunded")
        assert rev_0031 is not None
        assert rev_0031.down_revision == "0030_prize_lots"

    def test_0032_descends_from_0031(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0032 = script.get_revision("0032_audit_source_prize_lot_reserved")
        assert rev_0032 is not None
        assert rev_0032.down_revision == "0031_audit_source_prize_lot_refunded"

    def test_0037_descends_from_0036(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0037 = script.get_revision("0037_payout_freeze_and_prize_lot_winner_id")
        assert rev_0037 is not None
        assert rev_0037.down_revision == "0036_prize_lots_reserved_at"

    def test_0038_descends_from_0037(self) -> None:
        cfg = _alembic_config("sqlite:///:memory:")
        script = ScriptDirectory.from_config(cfg)
        rev_0038 = script.get_revision("0038_ton_connect_nonces")
        assert rev_0038 is not None
        assert rev_0038.down_revision == "0037_payout_freeze_and_prize_lot_winner_id"

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
            "20260509_0021_items.py",
            "20260509_0022_scrolls.py",
            "20260510_0023_roulette_spins.py",
            "20260510_0024_audit_source_roulette_free.py",
            "20260510_0025_audit_source_oracle_tribe_bonus.py",
            "20260510_0026_payments_and_audit_source.py",
            "20260510_0027_prize_pool_balance.py",
            "20260510_0028_audit_source_prize_pool_increment.py",
            "20260510_0029_audit_source_prize_lot_generated.py",
            "20260510_0030_prize_lots.py",
            "20260510_0031_audit_source_prize_lot_refunded.py",
            "20260511_0032_audit_source_prize_lot_reserved.py",
            "20260511_0033_audit_source_prize_lot_claimed.py",
            "20260511_0034_audit_source_wallet_linked.py",
            "20260511_0035_wallets.py",
            "20260511_0036_prize_lots_reserved_at.py",
            "20260512_0037_payout_freeze_and_prize_lot_winner_id.py",
            "20260512_0038_ton_connect_nonces.py",
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
            "items",
            "scrolls",
            "roulette_spins",
            "payments",
            "prize_pool_balance",
            "prize_lots",
            "wallets",
            "payout_freeze",
            "ton_connect_nonces",
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

    def test_0021_creates_items_table(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Спринт 3.4-B: миграция создаёт `items`-таблицу с PK + CHECK."""
        db_path = tmp_path / "alembic_0021.sqlite"
        async_url = f"sqlite+aiosqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", async_url)

        cfg = _alembic_config(async_url)
        command.upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{db_path}")
        try:
            with engine.connect() as conn:
                inspector = inspect(conn)
                items_cols = {c["name"] for c in inspector.get_columns("items")}
                pk = inspector.get_pk_constraint("items")
                fks = inspector.get_foreign_keys("items")
        finally:
            engine.dispose()

        assert items_cols == {"player_id", "item_id", "enchant_level", "acquired_at"}
        assert set(pk["constrained_columns"]) == {"player_id", "item_id"}
        # FK на users.id с каскадом.
        assert any(
            fk["referred_table"] == "users"
            and fk["constrained_columns"] == ["player_id"]
            and fk["options"].get("ondelete", "").upper() == "CASCADE"
            for fk in fks
        )

    def test_0022_creates_scrolls_table(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Спринт 3.4-C: миграция создаёт `scrolls`-таблицу с PK + FK + CHECK."""
        db_path = tmp_path / "alembic_0022.sqlite"
        async_url = f"sqlite+aiosqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", async_url)

        cfg = _alembic_config(async_url)
        command.upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{db_path}")
        try:
            with engine.connect() as conn:
                inspector = inspect(conn)
                scrolls_cols = {c["name"] for c in inspector.get_columns("scrolls")}
                pk = inspector.get_pk_constraint("scrolls")
                fks = inspector.get_foreign_keys("scrolls")
        finally:
            engine.dispose()

        assert scrolls_cols == {"player_id", "scroll_id", "qty", "acquired_at"}
        assert set(pk["constrained_columns"]) == {"player_id", "scroll_id"}
        # FK на users.id с каскадом.
        assert any(
            fk["referred_table"] == "users"
            and fk["constrained_columns"] == ["player_id"]
            and fk["options"].get("ondelete", "").upper() == "CASCADE"
            for fk in fks
        )

    def test_0023_creates_roulette_spins_table(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Спринт 3.5-B: миграция создаёт `roulette_spins`-таблицу + индексы + FK."""
        db_path = tmp_path / "alembic_0023.sqlite"
        async_url = f"sqlite+aiosqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", async_url)

        cfg = _alembic_config(async_url)
        command.upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{db_path}")
        try:
            with engine.connect() as conn:
                inspector = inspect(conn)
                spins_cols = {c["name"] for c in inspector.get_columns("roulette_spins")}
                fks = inspector.get_foreign_keys("roulette_spins")
                index_names = {ix["name"] for ix in inspector.get_indexes("roulette_spins")}
                unique_names = {
                    uc["name"] for uc in inspector.get_unique_constraints("roulette_spins")
                }
        finally:
            engine.dispose()

        assert spins_cols == {
            "id",
            "player_id",
            "occurred_at",
            "kind",
            "length_cm",
            "idempotency_key",
        }
        # FK на users.id с каскадом.
        assert any(
            fk["referred_table"] == "users"
            and fk["constrained_columns"] == ["player_id"]
            and fk["options"].get("ondelete", "").upper() == "CASCADE"
            for fk in fks
        )
        # Composite-индекс по (player_id, occurred_at) для last_free_spin_at.
        assert "ix_roulette_spins_player_id_occurred_at" in index_names
        # UNIQUE-индекс по idempotency_key для INSERT … ON CONFLICT DO NOTHING.
        assert "uq_roulette_spins_idempotency_key" in unique_names

    def test_0038_creates_ton_connect_nonces_table(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Спринт 4.1-F, F.6.a: миграция создаёт `ton_connect_nonces` с PK + индексами."""
        db_path = tmp_path / "alembic_0038.sqlite"
        async_url = f"sqlite+aiosqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", async_url)

        cfg = _alembic_config(async_url)
        command.upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{db_path}")
        try:
            with engine.connect() as conn:
                inspector = inspect(conn)
                nonce_cols = {c["name"] for c in inspector.get_columns("ton_connect_nonces")}
                pk = inspector.get_pk_constraint("ton_connect_nonces")
                index_names = {ix["name"] for ix in inspector.get_indexes("ton_connect_nonces")}
        finally:
            engine.dispose()

        assert nonce_cols == {
            "nonce",
            "scope",
            "issued_at",
            "consumed_at",
            "expires_at",
        }
        assert set(pk["constrained_columns"]) == {"nonce"}
        assert "ix_ton_connect_nonces_expires_at" in index_names
        assert "ix_ton_connect_nonces_scope_nonce_consumed_at" in index_names

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
