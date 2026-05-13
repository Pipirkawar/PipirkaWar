"""OpenAI-адаптер для `IAiTextGenerator` (Спринт 4.1-M).

Использует официальный async-клиент OpenAI (`openai.AsyncOpenAI`).
Адаптер строит prompt из системной инструкции (стиль, безопасность,
плейсхолдеры) + user-запрос («сгенерируй N предсказаний на локали L»).
Ответ парсится из JSON-формата (model вызывается с `response_format=json_object`).

Применяется `tenacity`-free простой ретрай: один пере-запрос при
transient-ошибках (`RateLimitError`, `APITimeoutError`). При повторной
неудаче — `AiGenerationError`, caller fallback-ится на static templates.

Промпты разделены по доменам (predictions / forest / duel) — у каждого
свой стиль + проверка плейсхолдеров (`{user}` или `{winner}/{loser}`).

Контентная безопасность: системная инструкция явно запрещает
оскорбления/политику/NSFW. OpenAI moderation API НЕ вызывается отдельно
(скоуп 4.1-M-минимум) — модель сама фильтрует unsafe-промпты на своей
стороне.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from typing import Any, Literal

from pipirik_wars.application.ai.ports import (
    AiGenerationError,
    DuelLogKind,
    IAiTextGenerator,
)

logger = logging.getLogger(__name__)

_LOCALE_NAMES: dict[str, str] = {
    "ru": "Russian",
    "en": "English",
    "pt": "Portuguese",
    "es": "Spanish",
    "tr": "Turkish",
    "id": "Indonesian",
    "fa": "Persian (Farsi)",
    "uk": "Ukrainian",
}

_ORACLE_SYSTEM_PROMPT = (
    "You are a creative text generator for 'Pipirik Wars' — a humorous Telegram game "
    "where players grow their 'pipirik' (cm length) through battles, forest expeditions, "
    "and daily fortune readings. Generate ORACLE PREDICTIONS: short mystical/witty "
    "one-liners (1-2 sentences each) addressed to the player. "
    "STYLE: light, playful, occasionally absurd; mix of fortune-cookie wisdom and gentle "
    "irony. NEVER offensive, political, or NSFW. "
    "PLACEHOLDER: every prediction MUST contain `{user}` exactly once (a literal "
    "placeholder, NOT a real name) — it will be replaced with the player's display name. "
    "OUTPUT: valid JSON object with a single key `predictions` whose value is an array "
    "of strings. No markdown, no commentary, only JSON."
)

_FOREST_SYSTEM_PROMPT = (
    "You are a creative text generator for 'Pipirik Wars'. Generate FOREST EXPEDITION "
    "LOG MESSAGES: short narrative snippets (1-3 sentences each) describing what "
    "happens to a player wandering through a magical forest looking for length crystals, "
    "ancient artifacts, or strange creatures. "
    "STYLE: fantasy-humor, micro-adventure, occasionally mysterious. NEVER offensive, "
    "political, or NSFW. "
    "PLACEHOLDER: every log MUST contain `{user}` exactly once (the player's name). "
    "OUTPUT: valid JSON object with a single key `logs` whose value is an array of "
    "strings. No markdown, no commentary, only JSON."
)

_DUEL_PROMPT_BY_KIND: dict[DuelLogKind, tuple[str, tuple[str, ...], str]] = {
    "both_hit": (
        "You are a creative text generator for 'Pipirik Wars'. Generate DUEL ROUND LOGS "
        "for the BOTH-HIT outcome: both fighters land their attacks (mutual damage). "
        "Short play-by-play snippets, 1-2 sentences each. "
        "STYLE: action-humor, mock-heroic, absurdist. NEVER offensive, political, or NSFW. "
        "PLACEHOLDERS: every log MUST contain BOTH `{p1}` and `{p2}` exactly once each. "
        "OUTPUT: valid JSON object with a single key `logs` whose value is an array of "
        "strings. No markdown, no commentary, only JSON.",
        ("{p1}", "{p2}"),
        "duel both-hit round logs",
    ),
    "single_hit": (
        "You are a creative text generator for 'Pipirik Wars'. Generate DUEL ROUND LOGS "
        "for the SINGLE-HIT outcome: the attacker lands while the defender blocks them. "
        "Short play-by-play snippets, 1-2 sentences each. "
        "STYLE: action-humor, mock-heroic, absurdist. NEVER offensive, political, or NSFW. "
        "PLACEHOLDERS: every log MUST contain BOTH `{attacker}` and `{defender}` exactly "
        "once each. "
        "OUTPUT: valid JSON object with a single key `logs` whose value is an array of "
        "strings. No markdown, no commentary, only JSON.",
        ("{attacker}", "{defender}"),
        "duel single-hit round logs",
    ),
    "both_blocked": (
        "You are a creative text generator for 'Pipirik Wars'. Generate DUEL ROUND LOGS "
        "for the BOTH-BLOCKED outcome: both fighters block each other (mutual no-damage). "
        "Short play-by-play snippets, 1-2 sentences each. "
        "STYLE: action-humor, mock-heroic, absurdist. NEVER offensive, political, or NSFW. "
        "PLACEHOLDERS: every log MUST contain BOTH `{p1}` and `{p2}` exactly once each. "
        "OUTPUT: valid JSON object with a single key `logs` whose value is an array of "
        "strings. No markdown, no commentary, only JSON.",
        ("{p1}", "{p2}"),
        "duel both-blocked round logs",
    ),
}

_OutputKind = Literal["predictions", "logs"]


class OpenAiTextGenerator(IAiTextGenerator):
    """Адаптер для OpenAI Chat Completions API (модель `gpt-4o-mini` по умолчанию).

    Конструктор принимает уже готовый клиент (DI-friendly): тесты передают
    fake-объект с тем же async-методом `chat.completions.create`.
    """

    __slots__ = ("_client", "_model", "_timeout")

    def __init__(
        self,
        *,
        client: Any,
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 60.0,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout = timeout_seconds

    async def generate_oracle_predictions(
        self,
        *,
        locale: str,
        count: int,
    ) -> Sequence[str]:
        return await self._generate(
            system_prompt=_ORACLE_SYSTEM_PROMPT,
            kind="predictions",
            locale=locale,
            count=count,
            placeholder_required=("{user}",),
            content_label="oracle predictions",
        )

    async def generate_forest_logs(
        self,
        *,
        locale: str,
        count: int,
    ) -> Sequence[str]:
        return await self._generate(
            system_prompt=_FOREST_SYSTEM_PROMPT,
            kind="logs",
            locale=locale,
            count=count,
            placeholder_required=("{user}",),
            content_label="forest log lines",
        )

    async def generate_duel_logs(
        self,
        *,
        locale: str,
        count: int,
        kind: DuelLogKind,
    ) -> Sequence[str]:
        if kind not in _DUEL_PROMPT_BY_KIND:
            raise AiGenerationError(f"unknown duel log kind: {kind!r}")
        system_prompt, placeholders, label = _DUEL_PROMPT_BY_KIND[kind]
        return await self._generate(
            system_prompt=system_prompt,
            kind="logs",
            locale=locale,
            count=count,
            placeholder_required=placeholders,
            content_label=label,
        )

    async def _generate(
        self,
        *,
        system_prompt: str,
        kind: _OutputKind,
        locale: str,
        count: int,
        placeholder_required: tuple[str, ...],
        content_label: str,
    ) -> tuple[str, ...]:
        """Один LLM-вызов с retries. На неудачу — `AiGenerationError`."""
        if count <= 0:
            return ()
        locale_name = _LOCALE_NAMES.get(locale, locale)
        user_prompt = (
            f"Generate exactly {count} {content_label} in {locale_name} "
            f"(locale code: {locale!r}). Each entry must include the required "
            f"placeholder(s): {', '.join(placeholder_required)}. "
            f'Return JSON: {{"{kind}": [..., ..., ...]}}.'
        )

        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                raw = await asyncio.wait_for(
                    self._call_openai(system_prompt=system_prompt, user_prompt=user_prompt),
                    timeout=self._timeout,
                )
                items = _parse_response(raw=raw, kind=kind)
                _validate_placeholders(items=items, required=placeholder_required)
                return items
            except AiGenerationError:
                raise
            except TimeoutError as exc:
                last_error = exc
                logger.warning(
                    "ai.openai.timeout attempt=%d locale=%s kind=%s",
                    attempt,
                    locale,
                    kind,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "ai.openai.error attempt=%d locale=%s kind=%s err=%s",
                    attempt,
                    locale,
                    kind,
                    type(exc).__name__,
                )
            if attempt == 1:
                await asyncio.sleep(0.5)

        raise AiGenerationError(
            f"OpenAI generation failed after retries (locale={locale}, kind={kind}): "
            f"{type(last_error).__name__ if last_error else 'unknown'}"
        )

    async def _call_openai(self, *, system_prompt: str, user_prompt: str) -> str:
        """Сделать один Chat Completions запрос. Вернёт content-строку."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.9,
        )
        choices = getattr(response, "choices", None)
        if not choices:
            raise AiGenerationError("OpenAI response has no choices")
        message = getattr(choices[0], "message", None)
        if message is None:
            raise AiGenerationError("OpenAI choice has no message")
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content:
            raise AiGenerationError("OpenAI message content is empty")
        return content


def _parse_response(*, raw: str, kind: _OutputKind) -> tuple[str, ...]:
    """Распарсить JSON-ответ модели в кортеж строк."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AiGenerationError(f"OpenAI returned non-JSON content: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AiGenerationError(f"OpenAI returned non-object root: {type(parsed).__name__}")
    items_raw = parsed.get(kind)
    if not isinstance(items_raw, list):
        raise AiGenerationError(f"OpenAI response missing list under key {kind!r}")
    items: list[str] = []
    for entry in items_raw:
        if not isinstance(entry, str) or not entry.strip():
            raise AiGenerationError(f"OpenAI response contains invalid item: {entry!r}")
        items.append(entry.strip())
    if not items:
        raise AiGenerationError("OpenAI response contains empty list")
    return tuple(items)


def _validate_placeholders(*, items: Sequence[str], required: tuple[str, ...]) -> None:
    """Проверить, что каждая запись содержит все необходимые плейсхолдеры."""
    for entry in items:
        for placeholder in required:
            if placeholder not in entry:
                raise AiGenerationError(
                    f"AI-generated item missing placeholder {placeholder!r}: {entry[:80]!r}..."
                )


__all__ = ["OpenAiTextGenerator"]
