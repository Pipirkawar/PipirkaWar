"""Smoke-тест регистрации router-ов (Спринт 4.1-D, D.7.d).

Проверяем, что `register_routers(dispatcher)` подключает
`claim_prize_router` (наряду с прочими), и что у dispatcher-а
после регистрации router-ов есть sub_routers с именем `claim_prize`.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from aiogram import Dispatcher

from pipirik_wars.bot.handlers import register_routers


class TestRegisterRouters:
    def test_claim_prize_router_registered(self) -> None:
        dp = MagicMock(spec=Dispatcher)
        register_routers(dp)
        router_names = [call.args[0].name for call in dp.include_router.call_args_list]
        assert "claim_prize" in router_names

    def test_link_wallet_router_registered(self) -> None:
        dp = MagicMock(spec=Dispatcher)
        register_routers(dp)
        router_names = [call.args[0].name for call in dp.include_router.call_args_list]
        assert "link_wallet" in router_names

    def test_claim_prize_after_roulette_paid(self) -> None:
        """claim_prize_router идёт после roulette_paid_router."""
        dp = MagicMock(spec=Dispatcher)
        register_routers(dp)
        router_names = [call.args[0].name for call in dp.include_router.call_args_list]
        rp_idx = router_names.index("roulette_paid")
        cp_idx = router_names.index("claim_prize")
        assert cp_idx > rp_idx
