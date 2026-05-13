"""DI container for admin web panel (Sprint 4.5-A, §5)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pipirik_wars.admin_web.auth.session import SessionManager
from pipirik_wars.admin_web.settings import AdminWebSettings
from pipirik_wars.domain.admin.authorization import RoleBasedAdminAuthorizationPolicy
from pipirik_wars.domain.admin.ports.admin_confirm import ITotpVerifier
from pipirik_wars.domain.admin.ports.totp_secret_generator import ITotpSecretGenerator
from pipirik_wars.domain.balance.ports import IBalanceConfig, IBalanceReloader, IBalanceWriter
from pipirik_wars.domain.shared.ports import IClock
from pipirik_wars.infrastructure.admin.pyotp_totp_secret_generator import (
    PyOtpTotpSecretGenerator,
)
from pipirik_wars.infrastructure.admin.pyotp_totp_verifier import PyOtpTotpVerifier
from pipirik_wars.infrastructure.balance.loader import YamlBalanceLoader
from pipirik_wars.infrastructure.balance.writer import YamlBalanceWriter
from pipirik_wars.infrastructure.clock.real_clock import RealClock


@dataclass(frozen=True, slots=True)
class AdminWebContainer:
    """Subset container for admin-web routes."""

    settings: AdminWebSettings
    session_factory: async_sessionmaker[AsyncSession]
    session_manager: SessionManager
    bot_username: str
    bot_token: str
    secret_key: str

    totp_verifier: ITotpVerifier
    totp_secret_generator: ITotpSecretGenerator
    clock: IClock
    authorization_policy: RoleBasedAdminAuthorizationPolicy
    bootstrap_admin_password: str | None

    balance_config: IBalanceConfig
    balance_reloader: IBalanceReloader
    balance_writer: IBalanceWriter


def build_admin_web_container(settings: AdminWebSettings) -> AdminWebContainer:
    """Create the container with all wired dependencies."""
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )
    sf: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    secret_key_str = settings.secret_key.get_secret_value()

    session_manager = SessionManager(
        secret_key=secret_key_str,
        max_age=settings.session_max_age_seconds,
    )

    balance_path = Path(settings.balance_yaml_path)
    balance_loader = YamlBalanceLoader(balance_path)
    balance_writer = YamlBalanceWriter(path=balance_path, loader=balance_loader)

    return AdminWebContainer(
        settings=settings,
        session_factory=sf,
        session_manager=session_manager,
        bot_username=settings.bot_username,
        bot_token=settings.bot_token.get_secret_value(),
        secret_key=secret_key_str,
        totp_verifier=PyOtpTotpVerifier(),
        totp_secret_generator=PyOtpTotpSecretGenerator(),
        clock=RealClock(),
        authorization_policy=RoleBasedAdminAuthorizationPolicy(),
        bootstrap_admin_password=settings.bootstrap_admin_password,
        balance_config=balance_loader,
        balance_reloader=balance_loader,
        balance_writer=balance_writer,
    )
