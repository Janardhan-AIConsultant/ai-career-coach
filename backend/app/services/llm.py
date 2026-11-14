"""LLM access (Groq via LangChain) with timeout, bounded tokens, retry and usage counters.

``LLMClient`` is a small protocol so services and tests can swap implementations. The Groq key
stays server-side. Transient failures (rate limit, timeout, connection, 5xx) are retried with
backoff; auth/bad-request errors are not. Usage counters are in-process aggregates only.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from typing import Any, Protocol

from app.core.config import Settings
from app.core.exceptions import LLMServiceError
from app.utils.retry import retry_call

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def invoke(self, system: str, user: str) -> str: ...

    def stream(self, system: str, user: str) -> Iterator[str]: ...


class UsageCounter:
    """Thread-safe aggregate counters (no prompts or user data)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.failures = 0

    def record(self, ok: bool) -> None:
        with self._lock:
            self.calls += 1
            if not ok:
                self.failures += 1


usage = UsageCounter()


class GroqLLM:
    def __init__(self, settings: Settings) -> None:
        key = settings.groq_api_key.get_secret_value()
        if not key:
            raise LLMServiceError("The AI service is not configured")
        from langchain_groq import ChatGroq

        self._model: Any = ChatGroq(
            model_name=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.api_timeout,
            max_retries=0,  # retries are handled by retry_call so policy is in one place
            api_key=settings.groq_api_key,
        )
        self._retries = settings.llm_max_retries

    def _once(self, system: str, user: str) -> str:
        import groq

        try:
            reply = self._model.invoke([("system", system), ("human", user)])
        except (groq.RateLimitError, groq.APITimeoutError, groq.APIConnectionError) as exc:
            raise LLMServiceError() from exc  # retryable
        except groq.APIStatusError as exc:
            err = LLMServiceError()
            err.retryable = exc.status_code >= 500
            raise err from exc
        return str(reply.content)

    def invoke(self, system: str, user: str) -> str:
        try:
            result = retry_call(lambda: self._once(system, user), retries=self._retries)
        except LLMServiceError:
            usage.record(False)
            logger.exception("llm call failed")
            raise
        usage.record(True)
        return result

    def _map(self, exc: Exception) -> LLMServiceError:
        import groq

        if isinstance(exc, (groq.RateLimitError, groq.APITimeoutError, groq.APIConnectionError)):
            return LLMServiceError()
        err = LLMServiceError()
        err.retryable = isinstance(exc, groq.APIStatusError) and exc.status_code >= 500
        return err

    def _open_stream(self, system: str, user: str) -> tuple[str, Iterator[Any]]:
        """Open the stream and read the first chunk; only failures here are retried."""
        import groq

        try:
            it = iter(self._model.stream([("system", system), ("human", user)]))
            first = next(it)
        except StopIteration:
            return "", iter(())
        except (groq.APIError, groq.APIStatusError) as exc:
            raise self._map(exc) from exc
        return str(first.content), it

    def stream(self, system: str, user: str) -> Iterator[str]:
        """Yield text chunks. Retries apply only before the first chunk (never mid-answer)."""
        import groq

        try:
            first, rest = retry_call(lambda: self._open_stream(system, user), retries=self._retries)
        except LLMServiceError:
            usage.record(False)
            logger.exception("llm stream failed to start")
            raise
        ok = True
        try:
            if first:
                yield first
            for chunk in rest:
                text = str(chunk.content)
                if text:
                    yield text
        except (groq.APIError, groq.APIStatusError) as exc:
            ok = False
            logger.exception("llm stream failed mid-answer")
            raise self._map(exc) from exc
        finally:
            usage.record(ok)



