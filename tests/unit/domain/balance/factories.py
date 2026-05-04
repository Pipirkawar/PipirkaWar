"""Фабрики для тестов: собрать валидный/невалидный `BalanceConfig`.

Тесты схемы `BalanceConfig` ставят валидный baseline и точечно ломают
одно поле — это короче и устойчивее к рефакторингу YAML, чем хранить
отдельный фикстурный yaml-файл на каждый кейс.
"""

from __future__ import annotations

from typing import Any

from pipirik_wars.domain.balance.config import BalanceConfig


def valid_balance_payload() -> dict[str, Any]:
    """Минимально валидный сырой dict (как после `yaml.safe_load`).

    Ключи — как в реальном `config/balance.yaml` (с алиасами `from`/`to`).
    """
    return {
        "version": 1,
        "display_names": [
            {"from": 0, "to": 10, "name": "Пипирик"},
            {"from": 10, "to": 30, "name": "Писюнчик"},
            {"from": 30, "to": None, "name": "Батон"},
        ],
        "forest": {
            "outcomes": [
                {"name": "scarce", "weight": 50, "min": 1, "max": 10},
                {"name": "normal", "weight": 35, "min": 5, "max": 15},
                {"name": "abundant", "weight": 15, "min": 10, "max": 20},
            ],
            "cooldown_min_minutes": 10,
            "cooldown_max_minutes": 20,
        },
        "oracle": {
            "cooldown_tz": "Europe/Moscow",
            "bonus_min": 1,
            "bonus_max": 20,
            "distribution": "uniform",
        },
        "referral": {
            "on_signup": {"newbie_bonus_cm": 5, "referrer_bonus_cm": 1},
            "on_thickness_milestones": [
                {"thickness": 3, "referrer_bonus_cm": 10},
                {"thickness": 5, "referrer_bonus_cm": 30},
            ],
        },
        "thickness": {
            "cost_base": 1000,
            "cost_exponent": 2,
            "unlock_levels": {
                "forest": 1,
                "pvp_chat": 2,
                "mountains": 3,
            },
        },
        "dau_gate": {"max_dau": 200, "alert_threshold": 0.8},
        "daily_head": {
            "bonus_min": 1,
            "bonus_max": 20,
            "cooldown_tz": "Europe/Moscow",
            "schedule_mode": "hybrid",
            "cron_random_offset_hours": 24,
            "min_active_members": 5,
            "active_within_days": 7,
            "avoid_last_n": 3,
        },
        "content_policy": {
            "clan_quotes": {
                "mild_profanity": True,
                "politics": False,
                "ethnic_insults": False,
                "violence_advocacy": False,
                "advertising": False,
                "sexual_explicit": False,
            }
        },
    }


def build_valid_balance() -> BalanceConfig:
    """Валидный `BalanceConfig` для использования в тестах не-balance кода."""
    return BalanceConfig.model_validate(valid_balance_payload())
