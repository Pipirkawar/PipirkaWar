"""Архитектурный guard: вся прибавка длины — только через `ILengthGranter`.

Спринт 1.6.F (ГДД §3.3, см. также `application/progression/add_length.py`).

Правило:
- В domain-слое определён метод `Player.with_length(...)` — единственный
  способ изменить `Player.length` (включая, например, списание стоимости
  в `UpgradeThickness`).
- В **application**-слое прямой вызов `.with_length(...)` разрешён ТОЛЬКО
  в двух approved-use-case-ах:
  - `application/progression/add_length.py` — «прибавка длины» (через
    `ILengthGranter`, единая точка с anti-cheat hardcap-ом).
  - `application/progression/upgrade_thickness.py` — «вычет стоимости»
    (длина уменьшается, не прибавляется; cap-ы здесь не применимы).
- Любой другой production-файл (`bot/...`, `application/forest/...`,
  `application/oracle/...`, `infrastructure/...`) **не имеет права**
  напрямую вызывать `.with_length(...)`. Прибавка — через
  `ILengthGranter.grant(...)`; вычет (если когда-нибудь появится новая
  механика) — через будущий аналогичный port.

Этот тест защищает инвариант: ни один новый код не сможет «срезать угол»
в обход anti-cheat-логики `AddLength`, потому что CI зафейлится.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Корень `src/pipirik_wars/` относительно репозитория.
_SRC_ROOT = Path(__file__).resolve().parents[3] / "src" / "pipirik_wars"

# Approved-файлы — единственные production-модули, где разрешено напрямую
# вызывать `.with_length(...)`.
_ALLOWED_FILES: frozenset[Path] = frozenset(
    {
        # Определение метода (domain-слой).
        _SRC_ROOT / "domain" / "player" / "entities.py",
        # Approved-use-case: прибавка длины (Спринт 1.6.D / 1.6.F).
        _SRC_ROOT / "application" / "progression" / "add_length.py",
        # Approved-use-case: вычет стоимости при апгрейде толщины
        # (Спринт 1.4.A; не прибавка, cap-ы неприменимы).
        _SRC_ROOT / "application" / "progression" / "upgrade_thickness.py",
        # Approved-use-case: списание длины проигравшему PvP-дуэли
        # (Спринт 2.1.D, ГДД §7.1). Прибавка победителю — через
        # `ILengthGranter.grant(source=PVP_REWARD)`; вычет проигравшему
        # — прямой `with_length`, как в `UpgradeThickness`. Cap-ы 1.6
        # к вычету не применимы.
        _SRC_ROOT / "application" / "pvp" / "apply_outcome.py",
        # Approved-use-case: списание длины защитникам массового PvP-боя
        # (Спринт 2.2.E, ГДД §7.2). Симметрично `apply_outcome.py`, но
        # для N×M участников: атакующие получают через
        # `ILengthGranter.grant(source=PVP_REWARD)`, защитники теряют
        # через прямой `with_length`. Cap-ы 1.6 к вычетам неприменимы.
        _SRC_ROOT / "application" / "pvp" / "apply_mass_outcome.py",
    }
)

# Явно исключаем docstring-упоминания `length_granter.py` —
# там `with_length` встречается только в текстах документации.
_DOC_ONLY_FILES: frozenset[Path] = frozenset(
    {
        _SRC_ROOT / "domain" / "progression" / "length_granter.py",
    }
)

# Регулярка ищет вызов метода `.with_length(`, не учитывая слова, в которых
# `with_length` — часть имени (`some_with_length_thing`). Использует look-behind
# по точке.
_CALL_RE = re.compile(r"\.with_length\(")


def _iter_python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if p.is_file()]


def _is_call_in_code(file_path: Path) -> bool:
    """Есть ли в файле runtime-вызов `.with_length(...)` вне docstring-ов.

    Эвристика: ищем по сырому тексту. Файлы из `_DOC_ONLY_FILES`
    содержат `with_length` только в module-docstring, поэтому
    исключаются явно. Этого достаточно — добавление такого вызова в
    реальный код в этих файлах было бы тоже архитектурным нарушением.
    """
    content = file_path.read_text(encoding="utf-8")
    return bool(_CALL_RE.search(content))


@pytest.mark.parametrize(
    "py_file",
    _iter_python_files(_SRC_ROOT),
    ids=lambda p: str(p.relative_to(_SRC_ROOT)),
)
def test_with_length_only_in_approved_files(py_file: Path) -> None:
    """Защита: `.with_length(...)` встречается только в approved-файлах.

    Если этот тест упал на новом файле — значит, бизнес-логика прибавки
    или вычета длины переехала в обход `AddLength`. Нужно либо:
    1) перевести вызов на `ILengthGranter.grant(...)` (предпочтительно),
    2) либо явно расширить `_ALLOWED_FILES`, обосновав в PR-описании,
       почему cap-ы / soft-ban / audit здесь неприменимы.
    """
    if py_file in _ALLOWED_FILES or py_file in _DOC_ONLY_FILES:
        return
    assert not _is_call_in_code(py_file), (
        f"Запрещённое прямое использование `.with_length(...)` в {py_file}. "
        "Спринт 1.6.F: прибавка длины должна идти через ILengthGranter.grant(...). "
        "Если это вычет (как UpgradeThickness) — добавь файл в _ALLOWED_FILES "
        "и обоснуй в PR."
    )
