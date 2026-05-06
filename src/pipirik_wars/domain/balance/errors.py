"""Доменные ошибки балансовой конфигурации."""

from __future__ import annotations


class BalanceKeyError(KeyError):
    """Dotted-path в `BalanceConfig` не разрешается.

    Используется helper-ами `application/admin/_balance_path.py` и
    `infrastructure/balance/writer.py` (Спринт 2.5-C.3 / C.4) для
    единообразной семантики ошибок навигации по pydantic-модели.

    Поля:
    - `key`: исходный dotted-path, как его передал пользователь.
    - `segment`: конкретный сегмент path-а, на котором сорвался lookup.
    - `reason`: машинный код причины:
      - ``"empty"`` — пустой `key`;
      - ``"empty_segment"`` — два подряд `.` в path-е;
      - ``"not_found"`` — сегмент не существует в pydantic-модели/dict-е,
        либо по индексу обращаются к скаляру;
      - ``"index_invalid"`` — индекс ≤ 0 или вне границ списка.
    """

    __slots__ = ("key", "reason", "segment")

    def __init__(self, *, key: str, segment: str, reason: str) -> None:
        super().__init__(f"balance key {key!r} invalid at segment {segment!r}: {reason}")
        self.key = key
        self.segment = segment
        self.reason = reason


__all__ = ["BalanceKeyError"]
