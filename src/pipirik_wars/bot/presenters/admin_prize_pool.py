"""Презентер `/prize_pool` (Спринт 4.1-E, E.12, ГДД §12.6.6).

Локализует read-only снимок состояния крипто-пула + freeze-флага.
Один логический ответ — `render(...)` — собирает заголовок + строки
per-currency + блок freeze-состояния. Без I/O. Format `datetime` — UTC
ISO-8601 без микросекунд (как `/audit`-presenter), русский/английский
текст приходит из `IMessageBundle`-а.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.monetization import (
    CurrencyPoolStatus,
    GetPrizePoolStatusOutput,
)
from pipirik_wars.domain.monetization import PayoutFreeze

_KEY_NOT_AUTHORIZED: Final[MessageKey] = MessageKey("admin-prize-pool-not-authorized")
_KEY_HEADER: Final[MessageKey] = MessageKey("admin-prize-pool-header")
_KEY_ROW: Final[MessageKey] = MessageKey("admin-prize-pool-row")
_KEY_FROZEN: Final[MessageKey] = MessageKey("admin-prize-pool-frozen")
_KEY_UNFROZEN: Final[MessageKey] = MessageKey("admin-prize-pool-unfrozen")


def _format_iso(ts: datetime) -> str:
    """UTC, без микросекунд, ISO-8601 (как `/audit`-presenter)."""
    return ts.astimezone(tz=ts.tzinfo).replace(microsecond=0).isoformat()


class PrizePoolStatusPresenter:
    """Локализованные ответы `/prize_pool`."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_AUTHORIZED, locale=locale)

    def render(
        self,
        *,
        locale: Locale,
        output: GetPrizePoolStatusOutput,
    ) -> str:
        header = self._bundle.format(_KEY_HEADER, locale=locale)
        rows = [self._render_row(locale=locale, row=row) for row in output.per_currency]
        freeze_block = self._render_freeze(locale=locale, freeze=output.freeze)
        return "\n".join([header, *rows, "", freeze_block])

    def _render_row(self, *, locale: Locale, row: CurrencyPoolStatus) -> str:
        return self._bundle.format(
            _KEY_ROW,
            locale=locale,
            currency=row.currency.value,
            balance=str(row.balance_native),
            active=str(row.active_lots),
            reserved=str(row.reserved_lots),
            claimed=str(row.claimed_lots),
            refunded=str(row.refunded_lots),
        )

    def _render_freeze(self, *, locale: Locale, freeze: PayoutFreeze) -> str:
        if not freeze.is_frozen:
            return self._bundle.format(_KEY_UNFROZEN, locale=locale)
        # Frozen-state: post-init гарантирует, что все 3 nullable-поля заполнены.
        assert freeze.frozen_by_admin_id is not None
        assert freeze.frozen_at is not None
        assert freeze.reason is not None
        return self._bundle.format(
            _KEY_FROZEN,
            locale=locale,
            admin_id=str(freeze.frozen_by_admin_id),
            frozen_at=_format_iso(freeze.frozen_at),
            reason=freeze.reason,
        )
