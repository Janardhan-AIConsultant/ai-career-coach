"""Custom exception hierarchy.

Every ``AppError`` carries a stable ``code``, an HTTP ``status_code`` and a *client-safe*
``message``. Internal detail belongs in the chained ``__cause__`` / logs, never in ``message``.
``retryable`` marks transient failures eligible for backoff; validation/auth errors are not.
"""

from __future__ import annotations


class AppError(Exception):
    code = "app_error"
    status_code = 500
    retryable = False

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)

    default_message = "Unexpected error"


class FileValidationError(AppError):
    code, status_code, default_message = "invalid_file", 422, "The uploaded file is not valid"


class DocumentProcessingError(AppError):
    code, status_code = "document_processing_failed", 422
    default_message = "The document could not be processed"


class EmbeddingGenerationError(AppError):
    code, status_code, retryable = "embedding_failed", 502, True
    default_message = "Embedding service failed"


class VectorStoreError(AppError):
    code, status_code, retryable = "vector_store_error", 503, True
    default_message = "Vector store is unavailable"


class LLMServiceError(AppError):
    code, status_code, retryable = "llm_error", 503, True
    default_message = "The AI service is temporarily unavailable"


class DatabaseError(AppError):
    code, status_code = "database_error", 503
    default_message = "Database is temporarily unavailable"


class AuthenticationError(AppError):
    code, status_code, default_message = "unauthenticated", 401, "Authentication required"


class AuthorizationError(AppError):
    code, status_code, default_message = "forbidden", 403, "You do not have access to this resource"


class GuestSessionExpiredError(AppError):
    code, status_code = "guest_session_expired", 401
    default_message = "Guest session has expired or is invalid"


class RateLimitExceededError(AppError):
    code, status_code, retryable = "rate_limited", 429, False
    default_message = "Too many requests"


class ReportGenerationError(AppError):
    code, status_code, default_message = "report_failed", 500, "Report could not be generated"


class InputValidationError(AppError):
    code, status_code, default_message = "invalid_input", 422, "The request input is not valid"


class NotFoundError(AppError):
    code, status_code, default_message = "not_found", 404, "Resource not found"


class ServiceBusyError(AppError):
    code, status_code, default_message = "service_busy", 503, "Service is busy, please retry shortly"


class ConfigurationError(AppError):
    code, status_code, default_message = "not_configured", 503, "A required service is not configured"


class ConflictError(AppError):
    code, status_code, default_message = "conflict", 409, "The request conflicts with the current state"
