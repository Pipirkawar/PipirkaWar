"""Value-объекты домена «Игрок» (Спринт 1.1, ГДД §2).

Все VO — frozen-датаклассы со слотами; инварианты проверяются в
`__post_init__`. Конструктор бросает `ValueError`, никаких лишних типов
ошибок здесь не нужно — это сугубо синтаксические проверки данных.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

# Длина имени отображения и собственного имени игрока ограничена сверху,
# чтобы карточка `/profile` не разъезжалась в Telegram (rendering safety),
# а строки спокойно умещались в `VARCHAR(64)` Postgres.
_DISPLAY_NAME_MAX_LENGTH: int = 64
_PLAYER_NAME_MAX_LENGTH: int = 64
_USERNAME_MAX_LENGTH: int = 32


@dataclass(frozen=True, slots=True)
class Length:
    """Длина пипирика в сантиметрах (ГДД §2.1, §1.1).

    Стартовое значение — `2 см`. Шкала может быть условно бесконечной
    сверху, но не отрицательной: ниже нуля игрок физически уйти не может
    (правило 20 см не даёт уйти даже близко, см. §0.6 / 1.2.1).
    """

    cm: int

    def __post_init__(self) -> None:
        if self.cm < 0:
            raise ValueError(f"Length must be >= 0 cm, got {self.cm}")


@dataclass(frozen=True, slots=True)
class Thickness:
    """Уровень толщины (ГДД §3 «Прокачка толщины»).

    Стартовое значение — `1` (нулевого уровня нет). Верхней границы на
    уровне VO нет — она определяется балансом (`thickness.unlock_levels`).
    """

    level: int

    def __post_init__(self) -> None:
        if self.level < 1:
            raise ValueError(f"Thickness level must be >= 1, got {self.level}")


class Title(str, enum.Enum):
    """Титулы игрока (ГДД §2.4).

    На старте у игрока титула нет (`title=None`). Первый титул —
    `NEWBIE` — выдаётся автоматически после первого возвращения из
    леса (см. Спринт 1.3 / `1.3.8`). Остальные титулы добавим, когда
    геймдиз закроет Q12b/Q13.

    `ATAMAN` (ГДД §9.6) — «Атаман разбойников»; выдаётся одному
    случайному рейдеру после разграбления каравана (т.е. бой каравана
    завершился победой рейдеров: все караванщики и защитники погибли).
    Назначение происходит в use-case-е `FinishCaravanBattle` через
    `Player.with_title(Title.ATAMAN, now=...)` вместе с ×4-долей от
    общей разграбленной длины (см. `domain/caravan/services.py::resolve`).
    """

    NEWBIE = "newbie"
    # ── Спринт 3.2-C (караваны: «Атаман разбойников», ГДД §9.6) ──
    ATAMAN = "ataman"


@dataclass(frozen=True, slots=True)
class PlayerName:
    """Собственное имя пипирика (ГДД §2.5).

    Имя не выдаётся при регистрации — оно выбивается дропом из леса
    (Спринт 1.3 / `1.3.5`). Здесь VO просто гарантирует, что строка
    не пустая и не превышает безопасную длину рендера.
    """

    value: str

    def __post_init__(self) -> None:
        stripped = self.value.strip()
        if not stripped:
            raise ValueError("PlayerName must not be empty/whitespace")
        if len(stripped) != len(self.value):
            raise ValueError("PlayerName must not have leading/trailing whitespace")
        if len(self.value) > _PLAYER_NAME_MAX_LENGTH:
            raise ValueError(
                f"PlayerName length must be <= {_PLAYER_NAME_MAX_LENGTH}, got {len(self.value)}"
            )


@dataclass(frozen=True, slots=True)
class DisplayName:
    """«Название» — расчётное по длине из `balance.yaml` (ГДД §2.3).

    Сюда складываем результат `BalanceConfig.display_name_for(length_cm)`.
    Сам расчёт живёт в `domain/balance/config.py`; этот VO — просто
    типизированная обёртка, которую мы носим в use-case-ах и
    презентерах вместо «голой» строки.

    Инвариант: значение из таблицы балансов уже не пустое (его проверяет
    `DisplayNameRange` при загрузке). Дополнительные проверки нужны
    лишь в защитных целях — на случай, если где-то соберём `DisplayName`
    в обход балансовой таблицы.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.isspace():
            raise ValueError("DisplayName must not be empty/whitespace")
        if len(self.value) > _DISPLAY_NAME_MAX_LENGTH:
            raise ValueError(
                f"DisplayName length must be <= {_DISPLAY_NAME_MAX_LENGTH}, got {len(self.value)}"
            )


@dataclass(frozen=True, slots=True)
class Username:
    """Telegram @username игрока (без `@`).

    Может меняться без рестарта бота (Telegram это позволяет), поэтому
    в БД мы её только обновляем, а не считаем стабильным идентификатором.
    Стабильный ключ — `tg_id`.

    Telegram-ограничения: 5..32 символов, латиница / цифры / `_`. Здесь
    проверяем только верхнюю границу длины и непустоту — нижнюю
    оставляем на стороне Telegram (и на случай, если пользователь
    сменит её на 4 символа).
    """

    value: str

    def __post_init__(self) -> None:
        stripped = self.value.strip()
        if not stripped:
            raise ValueError("Username must not be empty/whitespace")
        if len(stripped) != len(self.value):
            raise ValueError("Username must not have leading/trailing whitespace")
        if self.value.startswith("@"):
            raise ValueError("Username must not include leading '@'")
        if len(self.value) > _USERNAME_MAX_LENGTH:
            raise ValueError(
                f"Username length must be <= {_USERNAME_MAX_LENGTH}, got {len(self.value)}"
            )
