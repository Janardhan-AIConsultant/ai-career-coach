"""GroqLLM error mapping/retry with the network call replaced (no real Groq request is made)."""

from __future__ import annotations

from types import SimpleNamespace

import groq
import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import LLMServiceError
from app.services.llm import GroqLLM, usage

REQ = httpx.Request("POST", "http://groq.invalid/x")


def _status_error(cls: type[groq.APIStatusError], code: int) -> groq.APIStatusError:
    return cls("boom", response=httpx.Response(code, request=REQ), body=None)


def make_llm(retries: int) -> GroqLLM:
    s = Settings(_env_file=None, groq_api_key="gsk_test", llm_max_retries=retries)  # type: ignore[call-arg]
    return GroqLLM(s)


def test_requires_api_key() -> None:
    with pytest.raises(LLMServiceError, match="not configured"):
        GroqLLM(Settings(_env_file=None))  # type: ignore[call-arg]


def test_transient_error_retried_then_succeeds() -> None:
    llm = make_llm(retries=2)
    seq = [_status_error(groq.RateLimitError, 429), SimpleNamespace(content="answer")]
    calls: list[int] = []

    def fake_invoke(_: object) -> SimpleNamespace:
        calls.append(1)
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    llm._model = SimpleNamespace(invoke=fake_invoke)
    before = usage.calls
    assert llm.invoke("sys", "user") == "answer"
    assert len(calls) == 2 and usage.calls == before + 1


def test_auth_error_is_not_retried_and_hides_details() -> None:
    llm = make_llm(retries=3)
    calls: list[int] = []

    def fake_invoke(_: object) -> None:
        calls.append(1)
        raise _status_error(groq.AuthenticationError, 401)

    llm._model = SimpleNamespace(invoke=fake_invoke)
    failures = usage.failures
    with pytest.raises(LLMServiceError) as exc:
        llm.invoke("sys", "user")
    assert len(calls) == 1 and usage.failures == failures + 1
    assert "gsk_" not in exc.value.message and "boom" not in exc.value.message


def test_server_error_is_retryable() -> None:
    llm = make_llm(retries=1)
    calls: list[int] = []

    def fake_invoke(_: object) -> None:
        calls.append(1)
        raise _status_error(groq.InternalServerError, 503)

    llm._model = SimpleNamespace(invoke=fake_invoke)
    with pytest.raises(LLMServiceError):
        llm.invoke("sys", "user")
    assert len(calls) == 2


def _chunks(*texts: str):  # type: ignore[no-untyped-def]
    return iter([SimpleNamespace(content=t) for t in texts])


def test_stream_yields_chunks() -> None:
    llm = make_llm(retries=0)
    llm._model = SimpleNamespace(stream=lambda _: _chunks("Hel", "lo", "", " world"))
    assert list(llm.stream("sys", "user")) == ["Hel", "lo", " world"]


def test_stream_retries_before_first_chunk_only() -> None:
    llm = make_llm(retries=2)
    attempts: list[int] = []

    def fake_stream(_: object):  # type: ignore[no-untyped-def]
        attempts.append(1)
        if len(attempts) == 1:
            raise _status_error(groq.RateLimitError, 429)
        return _chunks("ok")

    llm._model = SimpleNamespace(stream=fake_stream)
    assert list(llm.stream("s", "u")) == ["ok"] and len(attempts) == 2


def test_stream_mid_answer_failure_is_not_retried() -> None:
    llm = make_llm(retries=3)
    attempts: list[int] = []

    def fake_stream(_: object):  # type: ignore[no-untyped-def]
        attempts.append(1)

        def gen():  # type: ignore[no-untyped-def]
            yield SimpleNamespace(content="partial")
            raise _status_error(groq.InternalServerError, 503)

        return gen()

    llm._model = SimpleNamespace(stream=fake_stream)
    out: list[str] = []
    try:
        out.extend(llm.stream("s", "u"))
    except LLMServiceError:
        pass
    else:
        raise AssertionError("expected LLMServiceError")
    assert out == ["partial"] and len(attempts) == 1


def test_stream_permanent_error_at_start_not_retried() -> None:
    llm = make_llm(retries=3)
    calls: list[int] = []

    def fake_stream(_: object):  # type: ignore[no-untyped-def]
        calls.append(1)
        raise _status_error(groq.AuthenticationError, 401)

    llm._model = SimpleNamespace(stream=fake_stream)
    try:
        list(llm.stream("s", "u"))
    except LLMServiceError:
        pass
    else:
        raise AssertionError("expected LLMServiceError")
    assert len(calls) == 1
