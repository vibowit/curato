from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base application exception for standardized error reporting."""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Any = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details


class AuthRequiredException(AppException):
    def __init__(self, message: str = "Authentication required", details: Any = None):
        super().__init__(
            message=message,
            error_code="AUTH_REQUIRED",
            status_code=401,
            details=details,
        )


class RateLimitedException(AppException):
    def __init__(self, message: str = "Rate limit exceeded", details: Any = None):
        super().__init__(
            message=message,
            error_code="RATE_LIMITED",
            status_code=429,
            details=details,
        )


class UpstreamErrorException(AppException):
    def __init__(self, message: str = "Upstream service error", details: Any = None):
        super().__init__(
            message=message,
            error_code="UPSTREAM_ERROR",
            status_code=502,
            details=details,
        )


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", details: Any = None):
        super().__init__(
            message=message,
            error_code="NOT_FOUND",
            status_code=404,
            details=details,
        )


class InvalidStateException(AppException):
    def __init__(self, message: str = "Invalid operation state", details: Any = None):
        super().__init__(
            message=message,
            error_code="INVALID_STATE",
            status_code=400,
            details=details,
        )


class ValidationException(AppException):
    def __init__(self, message: str = "Validation failed", details: Any = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=422,
            details=details,
        )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "request_id": request_id,
            "details": exc.details,
        },
    )
