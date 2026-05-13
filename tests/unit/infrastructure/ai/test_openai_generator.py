"""Unit-тесты `OpenAiTextGenerator` (Спринт 4.1-M, шаг M.2).

Контракт:
* Адаптер дёргает `client.chat.completions.create` с системным prompt-ом
  и user-сообщением, парсит JSON-ответ и валидирует плейсхолдеры.
* На `TimeoutError` делает один retry с паузой 0.5 с; при повторной
  неудаче — `AiGenerationError`.
* При невалидном JSON / отсутствии нужного ключа / пустом списке /
  пропавшем плейсхолдере — `AiGenerationError` сразу (без retry).
* Для duel-логов prompt и список обязательных плейсхолдеров зависят
  от `kind` (both_hit/single_hit/both_blocked).

Все тесты — async, через `pytest.mark.asyncio` (см. pyproject.toml,
asyncio_mode=auto).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import pytest

from pipirik_wars.application.ai.ports import AiGenerationError, DuelLogKind
from pipirik_wars.infrastructure.ai.openai_generator import OpenAiTextGenerator

pytestmark = pytest.mark.asyncio


@dataclass(slots=True)
class _FakeMessage:
    content: str | None


@dataclass(slots=True)
class _FakeChoice:
    message: _FakeMessage


@dataclass(slots=True)
class _FakeResponse:
    choices: list[_FakeChoice]


class _FakeCompletions:
    """Подделка `client.chat.completions` — возвращает заданные ответы по очереди."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("Fake.create called more times than responses provided")
        value = self._responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self._completions = _FakeCompletions(responses)
        self.chat = _FakeChat(self._completions)

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self._completions.calls


def _response_with(payload: dict[str, list[str]]) -> _FakeResponse:
    return _FakeResponse(choices=[_FakeChoice(message=_FakeMessage(content=json.dumps(payload)))])


class TestGenerateOraclePredictionsHappyPath:
    async def test_returns_parsed_strings(self) -> None:
        client = _FakeClient(
            [
                _response_with(
                    {"predictions": ["Сегодня {user} съест арбуз.", "Завтра {user} нашёл клад."]}
                )
            ]
        )
        gen = OpenAiTextGenerator(client=client, model="gpt-4o-mini")
        result = await gen.generate_oracle_predictions(locale="ru", count=2)
        assert tuple(result) == (
            "Сегодня {user} съест арбуз.",
            "Завтра {user} нашёл клад.",
        )

    async def test_passes_model_and_format(self) -> None:
        client = _FakeClient([_response_with({"predictions": ["Hello {user}."]})])
        gen = OpenAiTextGenerator(client=client, model="gpt-4o-mini")
        await gen.generate_oracle_predictions(locale="en", count=1)
        assert len(client.calls) == 1
        call = client.calls[0]
        assert call["model"] == "gpt-4o-mini"
        assert call["response_format"] == {"type": "json_object"}
        assert call["messages"][0]["role"] == "system"
        assert call["messages"][1]["role"] == "user"
        assert "1" in call["messages"][1]["content"]

    async def test_count_zero_returns_empty(self) -> None:
        client = _FakeClient([])
        gen = OpenAiTextGenerator(client=client)
        result = await gen.generate_oracle_predictions(locale="ru", count=0)
        assert tuple(result) == ()
        assert client.calls == []


class TestGenerateForestLogsHappyPath:
    async def test_returns_parsed_strings(self) -> None:
        client = _FakeClient(
            [_response_with({"logs": ["{user} нашёл гриб.", "{user} увидел сову."]})]
        )
        gen = OpenAiTextGenerator(client=client)
        result = await gen.generate_forest_logs(locale="ru", count=2)
        assert tuple(result) == ("{user} нашёл гриб.", "{user} увидел сову.")


class TestGenerateDuelLogsByKind:
    @pytest.mark.parametrize(
        ("kind", "required_placeholders", "sample_text"),
        [
            ("both_hit", ("{p1}", "{p2}"), "{p1} и {p2} ударили одновременно."),
            ("single_hit", ("{attacker}", "{defender}"), "{attacker} пробил блок {defender}."),
            ("both_blocked", ("{p1}", "{p2}"), "{p1} и {p2} оба заблокировали."),
        ],
    )
    async def test_kind_dispatches_to_correct_prompt(
        self,
        kind: DuelLogKind,
        required_placeholders: tuple[str, ...],
        sample_text: str,
    ) -> None:
        client = _FakeClient([_response_with({"logs": [sample_text]})])
        gen = OpenAiTextGenerator(client=client)
        result = await gen.generate_duel_logs(locale="ru", count=1, kind=kind)
        assert tuple(result) == (sample_text,)
        # System-prompt должен упоминать нужные плейсхолдеры
        system_prompt = client.calls[0]["messages"][0]["content"]
        for placeholder in required_placeholders:
            assert placeholder in system_prompt

    async def test_unknown_kind_raises(self) -> None:
        client = _FakeClient([])
        gen = OpenAiTextGenerator(client=client)
        with pytest.raises(AiGenerationError):
            await gen.generate_duel_logs(locale="ru", count=1, kind="unknown")  # type: ignore[arg-type]


class TestPlaceholderValidation:
    async def test_missing_user_placeholder_raises(self) -> None:
        client = _FakeClient([_response_with({"predictions": ["Без плейсхолдера тут."]})])
        gen = OpenAiTextGenerator(client=client)
        with pytest.raises(AiGenerationError, match="placeholder"):
            await gen.generate_oracle_predictions(locale="ru", count=1)

    async def test_missing_winner_placeholder_raises(self) -> None:
        client = _FakeClient([_response_with({"logs": ["{p1} одиночка."]})])
        gen = OpenAiTextGenerator(client=client)
        with pytest.raises(AiGenerationError, match="placeholder"):
            await gen.generate_duel_logs(locale="ru", count=1, kind="both_hit")


class TestResponseParsing:
    async def test_non_json_content_raises(self) -> None:
        bad_response = _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content="not a json"))]
        )
        client = _FakeClient([bad_response])
        gen = OpenAiTextGenerator(client=client)
        with pytest.raises(AiGenerationError, match="non-JSON"):
            await gen.generate_oracle_predictions(locale="ru", count=1)

    async def test_missing_predictions_key_raises(self) -> None:
        bad = _response_with({"wrong_key": ["text"]})
        client = _FakeClient([bad])
        gen = OpenAiTextGenerator(client=client)
        with pytest.raises(AiGenerationError, match="missing list"):
            await gen.generate_oracle_predictions(locale="ru", count=1)

    async def test_empty_predictions_list_raises(self) -> None:
        bad = _response_with({"predictions": []})
        client = _FakeClient([bad])
        gen = OpenAiTextGenerator(client=client)
        with pytest.raises(AiGenerationError, match="empty list"):
            await gen.generate_oracle_predictions(locale="ru", count=1)

    async def test_empty_message_content_raises(self) -> None:
        empty_response = _FakeResponse(choices=[_FakeChoice(message=_FakeMessage(content=""))])
        client = _FakeClient([empty_response])
        gen = OpenAiTextGenerator(client=client)
        with pytest.raises(AiGenerationError, match="empty"):
            await gen.generate_oracle_predictions(locale="ru", count=1)


class TestRetryOnTimeout:
    async def test_retries_once_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`TimeoutError` на первом вызове → повторный запрос → успех."""

        # Не ждём реально 500мс между ретраями.
        async def fast_sleep(_: float) -> None:
            return None

        monkeypatch.setattr(asyncio, "sleep", fast_sleep)

        client = _FakeClient(
            [TimeoutError("network slow"), _response_with({"predictions": ["{user} ok."]})]
        )
        gen = OpenAiTextGenerator(client=client, timeout_seconds=10.0)
        result = await gen.generate_oracle_predictions(locale="ru", count=1)
        assert tuple(result) == ("{user} ok.",)
        assert len(client.calls) == 2

    async def test_two_timeouts_raise_ai_generation_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fast_sleep(_: float) -> None:
            return None

        monkeypatch.setattr(asyncio, "sleep", fast_sleep)

        client = _FakeClient([TimeoutError("t1"), TimeoutError("t2")])
        gen = OpenAiTextGenerator(client=client, timeout_seconds=10.0)
        with pytest.raises(AiGenerationError, match="after retries"):
            await gen.generate_oracle_predictions(locale="ru", count=1)
        assert len(client.calls) == 2

    async def test_unexpected_exception_retried_then_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fast_sleep(_: float) -> None:
            return None

        monkeypatch.setattr(asyncio, "sleep", fast_sleep)

        client = _FakeClient([RuntimeError("boom"), RuntimeError("boom2")])
        gen = OpenAiTextGenerator(client=client)
        with pytest.raises(AiGenerationError, match="after retries"):
            await gen.generate_oracle_predictions(locale="ru", count=1)
        assert len(client.calls) == 2
