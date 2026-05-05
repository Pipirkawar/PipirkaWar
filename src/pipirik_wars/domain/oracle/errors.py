"""Domain-ошибки предсказателя."""

from __future__ import annotations

from datetime import date

from pipirik_wars.shared.errors import DomainError


class OracleError(DomainError):
    """Базовая ошибка `/oracle`."""


class OracleAlreadyUsedTodayError(OracleError):
    """Игрок уже звал `/oracle` сегодня (по Москве).

    Бросает `InvokeOracle`, когда в `oracle_invocations` уже есть запись
    на `(player_id, moscow_date)`. Handler в Спринте 1.4.B перехватывает
    эту ошибку и показывает игроку сообщение «возвращайся завтра» с
    указанием времени до сброса (00:00 МСК).
    """

    __slots__ = ("moscow_date", "player_id")

    def __init__(self, *, player_id: int, moscow_date: date) -> None:
        super().__init__(
            f"player_id={player_id} already invoked /oracle on {moscow_date.isoformat()}"
        )
        self.player_id = player_id
        self.moscow_date = moscow_date


class OracleNoTemplatesError(OracleError):
    """Каталог шаблонов пуст для запрошенной локали.

    Бросает `roll_oracle(...)`, если `templates` — пустая
    последовательность. На production это означает рассинхрон деплоя
    (templates-файл не приехал) и должно ронять use-case с алёртом
    в admin-чат, а не показывать пустую строку игроку.
    """

    __slots__ = ("locale",)

    def __init__(self, *, locale: str | None = None) -> None:
        msg = "oracle templates catalog is empty"
        if locale is not None:
            msg = f"{msg} for locale={locale!r}"
        super().__init__(msg)
        self.locale = locale


__all__ = [
    "OracleAlreadyUsedTodayError",
    "OracleError",
    "OracleNoTemplatesError",
]
