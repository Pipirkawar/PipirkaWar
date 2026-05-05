"""Каталог забавных логов раундов PvP (ГДД §15, ПД 2.1.5, Спринт 2.1.H).

`DuelLogTemplate` — иммутабельная запись каталога flavour-сообщений
PvP-раунда: стабильный `id` (используется в audit-логе и аналитике
«какой шаблон выпал чаще»), текст с опциональными плейсхолдерами и
категория `RoundOutcomeKind` (что произошло в раунде — оба пробили,
один пробил, оба заблокировали). Шаблоны хранятся в
`config/templates/duel_logs_<locale>.json` и загружаются
infrastructure-адаптером `JsonDuelLogTemplateProvider`.

Категории и допустимые плейсхолдеры:

* `BOTH_HIT` (оба атакующих пробили блок) — `{p1}`, `{p2}`.
* `SINGLE_HIT` (один пробил, другой заблокирован) — `{attacker}`,
  `{defender}`. Кто атакующий — определяется на presenter-стороне
  через `classify_round_outcome` + явные параметры `attacker_name` /
  `defender_name`.
* `BOTH_BLOCKED` (обе атаки попали в блок) — `{p1}`, `{p2}`.

`pick_duel_log_template(*, random, templates, kind)` — чистая функция
выбора одного шаблона из подкаталога нужной категории. Без I/O.
Используется bot-handler-ом / нотификатором PvP для добавления
flavour-строки к сообщению о раунде. Подстановка плейсхолдеров —
задача presenter-а: домен возвращает сырой `template.text`.

`classify_round_outcome(outcome)` — чистый помощник: преобразует
`RoundOutcome` (из `domain/pvp/entities.py`) в `RoundOutcomeKind`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from pipirik_wars.domain.pvp.entities import RoundOutcome
from pipirik_wars.domain.pvp.errors import DuelLogNoTemplatesError
from pipirik_wars.domain.shared.ports import IRandom


class RoundOutcomeKind(StrEnum):
    """Категория исхода раунда PvP (для подбора flavour-шаблона).

    * `BOTH_HIT` — оба пробили блок (обе атаки нанесли урон).
    * `SINGLE_HIT` — один пробил, другой заблокирован.
    * `BOTH_BLOCKED` — обе атаки попали в блок (взаимный 0-урон).
    """

    BOTH_HIT = "both_hit"
    SINGLE_HIT = "single_hit"
    BOTH_BLOCKED = "both_blocked"


@dataclass(frozen=True, slots=True)
class DuelLogTemplate:
    """Один шаблон забавного раунд-лога PvP (ГДД §15).

    Поля:

    * `id` — стабильный машинный идентификатор
      (например, ``"pvp.ru.both_hit.0001"``). Между деплоями не меняется.
    * `text` — текст сообщения. Может содержать плейсхолдеры в
      зависимости от `kind` (см. модуль-docstring).
    * `kind` — категория исхода раунда; используется при выборе
      шаблона `pick_duel_log_template`.
    """

    id: str
    text: str
    kind: RoundOutcomeKind

    def __post_init__(self) -> None:
        if not self.id or self.id != self.id.strip():
            raise ValueError(
                f"DuelLogTemplate.id must be non-empty/trimmed, got {self.id!r}",
            )
        if not self.text or self.text != self.text.strip():
            raise ValueError(
                f"DuelLogTemplate.text must be non-empty/trimmed, got {self.text!r}",
            )


def classify_round_outcome(outcome: RoundOutcome) -> RoundOutcomeKind:
    """Преобразовать `RoundOutcome` в `RoundOutcomeKind` для подбора шаблона.

    Чистая функция, без I/O.
    """
    p1_blocked = outcome.p1_attack_blocked
    p2_blocked = outcome.p2_attack_blocked
    if p1_blocked and p2_blocked:
        return RoundOutcomeKind.BOTH_BLOCKED
    if not p1_blocked and not p2_blocked:
        return RoundOutcomeKind.BOTH_HIT
    return RoundOutcomeKind.SINGLE_HIT


def pick_duel_log_template(
    *,
    random: IRandom,
    templates: Sequence[DuelLogTemplate],
    kind: RoundOutcomeKind,
) -> DuelLogTemplate:
    """Выбрать один шаблон из подкаталога нужной категории. Без I/O.

    Pre: общий каталог `templates` непуст (иначе `DuelLogNoTemplatesError`).
    Если для конкретной `kind` нет шаблонов — fallback на любую
    непустую категорию каталога (best-effort: лучше показать чужой
    flavour, чем падать в production).
    """
    if not templates:
        raise DuelLogNoTemplatesError()
    matching = [t for t in templates if t.kind == kind]
    if not matching:
        # Fallback: берём любой шаблон (первая непустая категория).
        matching = list(templates)
    return random.choice(matching)


__all__ = [
    "DuelLogTemplate",
    "RoundOutcomeKind",
    "classify_round_outcome",
    "pick_duel_log_template",
]
