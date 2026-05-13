"""infrastructure/ai package — LLM-адаптеры и AI-template-провайдеры (Спринт 4.1-M)."""

from pipirik_wars.infrastructure.ai.duel_log_provider import AiDuelLogTemplateProvider
from pipirik_wars.infrastructure.ai.forest_log_provider import AiForestLogTemplateProvider
from pipirik_wars.infrastructure.ai.openai_generator import OpenAiTextGenerator
from pipirik_wars.infrastructure.ai.oracle_provider import AiOracleTemplateProvider

__all__ = [
    "AiDuelLogTemplateProvider",
    "AiForestLogTemplateProvider",
    "AiOracleTemplateProvider",
    "OpenAiTextGenerator",
]
