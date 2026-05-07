"""Фабрики для тестов: собрать валидный/невалидный `BalanceConfig`.

Тесты схемы `BalanceConfig` ставят валидный baseline и точечно ломают
одно поле — это короче и устойчивее к рефакторингу YAML, чем хранить
отдельный фикстурный yaml-файл на каждый кейс.
"""

from __future__ import annotations

from typing import Any

from pipirik_wars.domain.balance.config import BalanceConfig

# Валидный каталог: ровно 40 предметов, по 5 на каждый из 8 слотов
# (с Спринта 3.1-C — плюс `right_hand`/`left_hand`), с покрытием всех
# 3 редкостей (16 common / 16 rare / 8 epic) и всех слотов.
_SLOTS = ("hat", "body", "legs", "boots", "ring", "chain", "right_hand", "left_hand")
_RARITY_PATTERN = ("common", "common", "rare", "rare", "epic")


def _build_valid_items_catalog() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for slot in _SLOTS:
        for idx, rarity in enumerate(_RARITY_PATTERN, start=1):
            items.append(
                {
                    "id": f"item.{slot}.test_{idx}",
                    "slot": slot,
                    "display_name": f"Тестовый {slot} #{idx}",
                    "rarity": rarity,
                }
            )
    return items


def _build_valid_names_catalog() -> list[str]:
    return [f"ИмяТест-{i:02d}" for i in range(1, 31)]


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
            "drop": {
                "probability_percent": 50,
                "name_share_percent": 5,
                "rarity_weights": {"common": 70, "rare": 25, "epic": 5},
                "slot_weights": {
                    "hat": 20,
                    "body": 20,
                    "legs": 20,
                    "boots": 15,
                    "ring": 12,
                    "chain": 13,
                    "right_hand": 0,
                    "left_hand": 0,
                },
            },
        },
        "mountains": {
            "outcomes": [
                {"name": "scarce_gain", "weight": 30, "sign": "gain", "min": 1, "max": 10},
                {"name": "normal_gain", "weight": 20, "sign": "gain", "min": 5, "max": 18},
                {"name": "abundant_gain", "weight": 10, "sign": "gain", "min": 10, "max": 30},
                {"name": "scarce_loss", "weight": 25, "sign": "loss", "min": 1, "max": 8},
                {"name": "heavy_loss", "weight": 15, "sign": "loss", "min": 5, "max": 18},
            ],
            "cooldown_min_minutes": 20,
            "cooldown_max_minutes": 40,
            "drop": {
                "probability_percent": 25,
                "max_drops": 1,
                "rarity_weights": {"common": 60, "rare": 30, "epic": 10},
                "slot_weights": {
                    "hat": 12,
                    "body": 12,
                    "legs": 12,
                    "boots": 12,
                    "ring": 12,
                    "chain": 12,
                    "right_hand": 14,
                    "left_hand": 14,
                },
                "scroll_drops": {
                    "regular_chance_percent": 3,
                    "blessed_chance_percent": 0,
                    "category_weights": {"weapon": 1, "armor": 1, "jewelry": 1},
                },
            },
        },
        "dungeon": {
            "outcomes": [
                {"name": "scarce_gain", "weight": 25, "sign": "gain", "min": 5, "max": 25},
                {"name": "normal_gain", "weight": 20, "sign": "gain", "min": 15, "max": 45},
                {"name": "abundant_gain", "weight": 10, "sign": "gain", "min": 30, "max": 80},
                {"name": "scarce_loss", "weight": 25, "sign": "loss", "min": 3, "max": 18},
                {"name": "heavy_loss", "weight": 20, "sign": "loss", "min": 10, "max": 35},
            ],
            "cooldown_min_minutes": 40,
            "cooldown_max_minutes": 60,
            "drop": {
                "probability_percent": 50,
                "max_drops": 3,
                "rarity_weights": {"common": 50, "rare": 35, "epic": 15},
                "slot_weights": {
                    "hat": 10,
                    "body": 10,
                    "legs": 10,
                    "boots": 10,
                    "ring": 10,
                    "chain": 10,
                    "right_hand": 20,
                    "left_hand": 20,
                },
                "scroll_drops": {
                    "regular_chance_percent": 6,
                    "blessed_chance_percent": 1,
                    "category_weights": {"weapon": 1, "armor": 1, "jewelry": 1},
                },
            },
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
                "dungeon": 6,
            },
        },
        "dau_gate": {"max_dau": 200, "alert_threshold": 0.8},
        "anticheat": {
            "daily_cap_cm": 3000,
            "weekly_cap_cm": 14000,
            "soft_ban_duration_days": 14,
            "organic_sources": [
                "forest",
                "mountains",
                "dungeon",
                "oracle",
                "referral_signup",
                "referral_thickness",
                "pvp_reward",
                "caravan_reward",
                "raid_reward",
                "admin_grant",
            ],
            "donate_sources": [
                "stars_payment",
                "ton_payment",
                "usdt_payment",
            ],
        },
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
        "pvp": {
            "duel_1v1": {
                "rounds": 3,
                "hit_pct": 10,
                "min_length_cm": 20,
                "min_thickness_level": 2,
                "global_lobby_ttl_minutes": 10,
                "chat_to_global_promotion_minutes": 3,
                "round_timer_seconds": 45,
            },
            "mass_duel": {
                "cooldown_hours": 6,
                "min_length_cm": 20,
                "min_thickness_level": 2,
                "min_clan_members": 1,
                "move_timer_seconds": 180,
            },
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
        "items_catalog": _build_valid_items_catalog(),
        "names_catalog": _build_valid_names_catalog(),
    }


def build_valid_balance() -> BalanceConfig:
    """Валидный `BalanceConfig` для использования в тестах не-balance кода."""
    return BalanceConfig.model_validate(valid_balance_payload())
