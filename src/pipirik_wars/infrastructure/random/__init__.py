"""Production-реализация `IRandom`."""

from pipirik_wars.infrastructure.random.real_random import RealRandom
from pipirik_wars.infrastructure.random.seeded_random import SeededRandom

__all__ = ["RealRandom", "SeededRandom"]
